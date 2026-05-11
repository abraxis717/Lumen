"""
mitigation_agent.py — The ASI's reflexes (Phase 3: LLM-backed governed agent)
================================================================================
Wakes only during CRITICAL or FATAL states to execute survival actions.
Does not act during NOMINAL or WARNING.

Phase 3 additions:
- Accepts optional `context` (list of BeliefNode) and `llm_client` callable.
- Returns a list of GovernedClaim objects instead of raw Intent strings.
- The mock LLM client produces plausible mitigation claims grounded in
  epistemic context.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Callable, List, Optional

from Weaver_ASI.core.event import Intent
from Weaver_ASI.council.claims import GovernedClaim
from Weaver_ASI.epistemics.belief_node import BeliefNode

logger = logging.getLogger(__name__)


def _mock_mitigation_llm(
    prompt: str,
    *,
    agent_name: str = "Mitigation",
) -> List[GovernedClaim]:
    """Generate mock GovernedClaim for mitigation actions."""
    rng = random.Random(hash(agent_name) & 0xFFFFFFFF)

    templates = {
        "WARNING": [
            "DRAIN_PRESSURE recommended: pressure trending upward. "
            "Preventive action before threshold.",
            "Preventive drain initiated: system within controlled parameters.",
        ],
        "CRITICAL": [
            "EMERGENCY_SCRAM triggered: immediate shutdown protocol.",
            "CRITICAL response: reactor scram — all safety systems engaged.",
        ],
        "FATAL": [
            "STEWARD_OVERRIDE required: physical state requires human intervention.",
            "FATAL: cannot resolve autonomously — escalate to steward.",
        ],
    }

    if "FATAL" in prompt:
        sev = "FATAL"
    elif "CRITICAL" in prompt:
        sev = "CRITICAL"
    else:
        sev = "WARNING"

    template = rng.choice(templates.get(sev, templates["WARNING"]))
    confidence = rng.uniform(0.7, 0.95)

    return [
        GovernedClaim(
            text=template,
            confidence=round(confidence, 4),
            agent=agent_name,
            metadata={"model": "mock-llm-mitigation-v0", "severity": sev},
        )
    ]


class MitigationAgent:
    """Survival reflexes with governed claim output.

    Args:
        world:      Optional world/state object (legacy).
        llm_client: Callable for structured claim generation.
        context_fn: Optional callable returning BeliefNodes for context.
    """

    name = "Mitigation"

    def __init__(
        self,
        world: Any = None,
        *,
        llm_client: Optional[Callable[[str], List[GovernedClaim]]] = None,
        context_fn: Optional[Callable[[], List[BeliefNode]]] = None,
    ) -> None:
        self._world = world
        self._issued: set[str] = set()
        self._llm = llm_client or _mock_mitigation_llm
        self._context_fn = context_fn

    def propose(self, step: int, state: dict) -> Optional[Intent]:
        """Phase 3: return first Intent from LLM claims (backward compat).

        Legacy path (no llm_client): single Intent per severity as before.
        Phase 3 path: returns the first claim as Intent; use propose_claims()
                     to get all claims as a list.
        """
        sev = state.get("severity", "NOMINAL")

        if sev == "NOMINAL":
            return None

        # Legacy path: single Intent per severity
        if self._llm is None:
            if sev == "WARNING" and "DRAIN_PRESSURE" not in self._issued:
                self._issued.add("DRAIN_PRESSURE")
                return Intent("DRAIN_PRESSURE", self.name,
                               {"step": step, "target_bar": 12.0})
            if sev == "CRITICAL" and "EMERGENCY_SCRAM" not in self._issued:
                self._issued.add("EMERGENCY_SCRAM")
                return Intent("EMERGENCY_SCRAM", self.name,
                               {"step": step, "priority": "CRITICAL"})
            if sev == "FATAL" and "STEWARD_OVERRIDE" not in self._issued:
                self._issued.add("STEWARD_OVERRIDE")
                return Intent("STEWARD_OVERRIDE", self.name,
                               {"reason": "Auto-escalated", "step": step})
            return None

        # Phase 3 path: LLM-backed claims
        context_text = self._build_context() if self._context_fn else ""
        prompt = self._format_prompt(step, state, context_text)
        claims = self._llm(prompt, agent_name=self.name)

        if claims:
            return Intent(
                action="mitigation_claim",
                agent=self.name,
                payload=claims[0].to_event_payload(),
            )
        return None

    def propose_claims(self, step: int, state: dict) -> List[GovernedClaim]:
        """Return raw GovernedClaim objects (no Intent wrapping)."""
        sev = state.get("severity", "NOMINAL")
        if sev == "NOMINAL":
            return []

        context_text = self._build_context() if self._context_fn else ""
        prompt = self._format_prompt(step, state, context_text)
        return self._llm(prompt, agent_name=self.name)

    def _build_context(self) -> str:
        try:
            nodes = self._context_fn()
            if not nodes:
                return ""
            lines = [f"Epistemic context ({len(nodes)} beliefs):"]
            for node in nodes[:5]:
                lines.append(f"  [{node.stratum.value}] w={node.effective_weight():.3f}: {node.claim}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("Context build failed: %s", exc)
            return ""

    @staticmethod
    def _format_prompt(step: int, state: dict, context: str) -> str:
        state_snippet = ", ".join(f"{k}={v}" for k, v in state.items())
        prompt = f"[Step {step}] State: {state_snippet}\n\n"
        prompt += "Propose a governed claim for the current system state.\n"
        if context:
            prompt += f"{context}\n"
        return prompt
