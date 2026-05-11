"""
oracle_agent.py — The ASI's eyes (Phase 3: LLM-backed governed agent)
========================================================================
Continuously injects cryptographically signed physical telemetry
into the system. Every sample is an Attestation — provenance is
verified at the IngressGate before entering the Chronicle.

Phase 3 additions:
- Accepts optional `context` (list of BeliefNode) and `llm_client` callable.
- Returns a list of GovernedClaim objects instead of raw Intent strings.
- The mock LLM client produces plausible claims grounded in epistemic context.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from Weaver_ASI.core.event import Intent
from Weaver_ASI.council.claims import GovernedClaim
from Weaver_ASI.epistemics.belief_node import BeliefNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock LLM client — replaces real LLM until one is wired in.
# ---------------------------------------------------------------------------
def _mock_llm(
    prompt: str,
    *,
    agent_name: str = "Oracle",
) -> List[GovernedClaim]:
    """Generate a mock GovernedClaim from a prompt.

    In production this function would call an external LLM API (OpenAI,
    local vLLM, etc.) and parse the structured response.
    """
    # Deterministic seed per agent so output is reproducible in tests.
    rng = random.Random(hash(agent_name) & 0xFFFFFFFF)

    templates = [
        "Physical telemetry: sensor reading stable at {value}. No anomaly detected.",
        "Observed: {value}. System within nominal parameters.",
        "Anomaly detected: {value}. Flagged for steward review.",
        "Sensor drift noted: {value}. Calibration recommended.",
    ]
    template = rng.choice(templates)
    value = f"{rng.uniform(0.0, 100.0):.2f}"

    claim_text = template.format(value=value)
    confidence = rng.uniform(0.6, 0.95)

    return [
        GovernedClaim(
            text=claim_text,
            confidence=round(confidence, 4),
            agent=agent_name,
            metadata={"model": "mock-llm-v0", "prompt_hash": hash(prompt) & 0xFFFFFFFF},
        )
    ]


# ---------------------------------------------------------------------------
# OracleAgent — Phase 3
# ---------------------------------------------------------------------------
class OracleAgent:
    """The Oracle observes physical reality and proposes telemetry.

    In production, this agent reads from real hardware sensors and
    queries an LLM for structured claims.

    Args:
        sensor:     HardwareSensor for raw readings (legacy compatibility).
        llm_client: Callable[[str], List[GovernedClaim]] — LLM interface.
                     Defaults to _mock_llm.
        context_fn: Optional callable returning BeliefNodes from the graph.
                    Passed to the LLM client as epistemic context.
    """

    name = "Oracle"

    def __init__(
        self,
        sensor: Any,
        *,
        llm_client: Optional[Callable[[str], List[GovernedClaim]]] = None,
        context_fn: Optional[Callable[[], List[BeliefNode]]] = None,
    ) -> None:
        self._sensor = sensor
        self.tick = 0
        self._llm = llm_client or _mock_llm
        self._context_fn = context_fn

    def propose(self, step: int, state: dict) -> Optional[Intent]:
        """Sample sensors, query LLM, return first GovernedClaim as Intent.

        Legacy path (no llm_client): returns a single Intent as before.
        Phase 3 path: returns the first GovernedClaim wrapped as Intent.
        Use propose_claims() to get all claims as a list.
        """
        self.tick += 1

        # --- Phase 3 path: LLM-backed structured claims ---
        if self._llm is not None:
            # Build epistemic context string
            context_text = self._build_context() if self._context_fn else ""
            prompt = self._format_prompt(step, state, context_text)
            claims = self._llm(prompt, agent_name=self.name)

            if claims:
                return Intent(
                    action="oracle_governed_claim",
                    agent=self.name,
                    payload=claims[0].to_event_payload(),
                )
            return None

        # --- Legacy path: raw telemetry ---
        a = self._sensor.sample()
        return Intent(
            action="oracle_telemetry",
            agent=self.name,
            payload={"tick": self.tick, "readings": a.readings},
            attestation=a.as_dict(),
        )

    def propose_claims(self, step: int, state: dict) -> List[GovernedClaim]:
        """Directly return GovernedClaim objects (no Intent wrapping).

        Useful for the GovernedCouncil consensus pipeline.
        """
        if self._llm is None:
            # Fallback: produce a trivial claim from sensor data
            a = self._sensor.sample()
            return [
                GovernedClaim(
                    text=f"Sensor reading: {a.readings}",
                    confidence=0.5,
                    agent=self.name,
                )
            ]

        context_text = self._build_context() if self._context_fn else ""
        prompt = self._format_prompt(step, state, context_text)
        return self._llm(prompt, agent_name=self.name)

    # ------------------------------------------------------------------
    # Context building helpers
    # ------------------------------------------------------------------
    def _build_context(self) -> str:
        """Serialize epistemic context for the LLM prompt."""
        try:
            nodes = self._context_fn()
            if not nodes:
                return ""
            lines = [f"Current epistemic context ({len(nodes)} beliefs):"]
            for node in nodes[:5]:  # Cap for prompt length
                lines.append(f"  [{node.stratum.value}] w={node.effective_weight():.3f}: {node.claim}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("Context build failed: %s", exc)
            return ""

    @staticmethod
    def _format_prompt(step: int, state: dict, context: str) -> str:
        """Compose the prompt sent to the LLM client."""
        state_snippet = ", ".join(f"{k}={v}" for k, v in state.items())
        prompt = (
            f"[Step {step}] System state: {state_snippet}\n\n"
            "Propose a governed claim about the current system state.\n"
            "Return a structured GovernedClaim.\n"
        )
        if context:
            prompt += f"\n{context}\n"
        return prompt
