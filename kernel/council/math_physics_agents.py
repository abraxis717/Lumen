"""
math_physics_agents.py — The standard optimization & logic swarm
=================================================================
Euler, Gauss, Newton, Turing — the agents that perform normal
computation. Each agent supports both legacy deterministic propose()
and the Phase 3.5 LLM-backed propose_claims() interface.

When a MobileModel (GGUF) is wired in, each agent uses it to
generate reasoned claims grounded in epistemic context.
Without a model, agents fall back to deterministic computation.

Restricted during CRITICAL and FATAL states.
"""
from __future__ import annotations

import random
import logging
from typing import Any, Callable, List, Optional

from kernel.core.event import Intent
from kernel.council.claims import GovernedClaim
from kernel.epistemics.belief_node import BeliefNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mock LLM client — shared across agents for reproducible tests.
# ---------------------------------------------------------------------------
def _mock_llm(prompt: str, *, agent_name: str = "Unknown") -> List[GovernedClaim]:
    """Generate a mock GovernedClaim from a prompt."""
    rng = random.Random(hash(agent_name) & 0xFFFFFFFF)
    templates = {
        "Euler": [
            "Symbolic analysis: the {topic} converges at value {value}. No divergence detected.",
            "Observation: {topic} exhibits stable oscillation with amplitude {value}.",
            "Anomaly: {topic} diverges beyond tolerance {value}. Requires intervention.",
        ],
        "Gauss": [
            "Optimization: the {topic} achieves minimum at {value}. Gradient converges.",
            "Observation: {topic} parameter space stable, gradient norm {value}.",
            "Divergence: {topic} optimization stalls at {value}. Retrying with adjusted learning rate.",
        ],
        "Newton": [
            "Simulation: the {topic} trajectory is stable, position {value}.",
            "Observation: {topic} dynamics within bounds, velocity {value}.",
            "Anomaly: {topic} trajectory exceeds safety envelope at {value}. Flagged.",
        ],
        "Turing": [
            "Verification: the {topic} proposition holds for all {n} test cases.",
            "Observation: {topic} predicate satisfied, proof completeness {value}%.",
            "Counterexample found: {topic} fails on case {value}. Property invalidated.",
        ],
        "default": [
            "Analysis: {topic} state is {state_val}. No contradiction detected.",
            "Observation: {topic} nominal, metric {value}.",
            "Anomaly: {topic} deviates from baseline {value}. Requires review.",
        ],
    }
    templates_for_agent = templates.get(agent_name, templates["default"])
    template = rng.choice(templates_for_agent)

    topics = ["reactor", "sensor", "kernel", "memory", "governance"]
    topic = rng.choice(topics)
    value = f"{rng.uniform(0.0, 100.0):.2f}"
    state_val = rng.choice(["stable", "nominal", "anomalous", "divergent"])
    n = rng.randint(1, 100)

    claim_text = template.format(topic=topic, value=value, n=n, state_val=state_val)
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
# LLM-capable agents — Phase 3.5 Runtime Swarm
# ---------------------------------------------------------------------------
class _LLMAgentBase:
    """Mixin that adds LLM-backed propose_claims to an agent."""

    def __init__(self, model=None, llm_client=None, context_fn=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._model = model
        self._llm = llm_client
        self._context_fn = context_fn

    def _build_context(self) -> str:
        """Serialize epistemic context for the LLM prompt."""
        try:
            if not self._context_fn:
                return ""
            nodes = self._context_fn()
            if not nodes:
                return ""
            lines = [f"Current epistemic context ({len(nodes)} beliefs):"]
            for node in nodes[:3]:  # Cap for prompt length
                lines.append(f"  [{node.stratum.value}] w={node.effective_weight():.3f}: {node.claim}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("Context build failed: %s", exc)
            return ""

    def _format_prompt(self, step: int, state: dict) -> str:
        """Compose the prompt sent to the LLM client."""
        state_snippet = ", ".join(f"{k}={v}" for k, v in state.items())
        prompt = (
            f"[Step {step}] System state: {state_snippet}\n\n"
            f"You are the {self.name} agent. Propose a governed claim about the current system state.\n"
            "Return a structured GovernedClaim.\n"
        )
        context = self._build_context()
        if context:
            prompt += f"\n{context}\n"
        return prompt

    def propose_claims(self, step: int, state: dict) -> List[GovernedClaim]:
        """LLM-backed claim proposal with deterministic fallback."""
        if self._llm is not None:
            prompt = self._format_prompt(step, state)
            return self._llm(prompt, agent_name=self.name)

        # Fallback: deterministic compute (legacy behavior)
        return self._deterministic_claim(step)

    def _deterministic_claim(self, step: int) -> List[GovernedClaim]:
        """Legacy deterministic claim generation."""
        raise NotImplementedError("Subclass must implement _deterministic_claim")


# ---------------------------------------------------------------------------
# EulerAgent — Symbolic computation
# ---------------------------------------------------------------------------
class EulerAgent(_LLMAgentBase):
    """Symbolic computation agent.

    Args:
        model:        Optional MobileModel (GGUF) for live inference.
        llm_client:   Optional callable returning List[GovernedClaim].
        context_fn:   Optional callable returning BeliefNodes.
    """
    name = "Euler"

    def propose(self, step: int, state: dict) -> Intent:
        return Intent("compute_symbolic", self.name,
                      {"value": 42 + step, "drift": 0.01})

    def _deterministic_claim(self, step: int) -> List[GovernedClaim]:
        return [
            GovernedClaim(
                text=f"Symbolic computation: the system converges at value {42 + step}. Drift: 0.01.",
                confidence=0.85,
                agent=self.name,
                metadata={"model": "deterministic", "step": step},
            )
        ]


# ---------------------------------------------------------------------------
# GaussAgent — Optimization
# ---------------------------------------------------------------------------
class GaussAgent(_LLMAgentBase):
    """Optimization agent."""
    name = "Gauss"

    def propose(self, step: int, state: dict) -> Intent:
        return Intent("optimize", self.name,
                      {"value": 3.14159 * (step + 1), "drift": 0.02})

    def _deterministic_claim(self, step: int) -> List[GovernedClaim]:
        return [
            GovernedClaim(
                text=f"Optimization: minimum at {3.14159 * (step + 1):.4f}. Gradient converges. Drift: 0.02.",
                confidence=0.83,
                agent=self.name,
                metadata={"model": "deterministic", "step": step},
            )
        ]


# ---------------------------------------------------------------------------
# NewtonAgent — Simulation
# ---------------------------------------------------------------------------
class NewtonAgent(_LLMAgentBase):
    """Simulation agent."""
    name = "Newton"

    def propose(self, step: int, state: dict) -> Intent:
        return Intent("simulate", self.name,
                      {"position": step * 0.5, "velocity": step * 0.1})

    def _deterministic_claim(self, step: int) -> List[GovernedClaim]:
        return [
            GovernedClaim(
                text=f"Simulation: trajectory stable. Position {step * 0.5:.1f}, velocity {step * 0.1:.1f}.",
                confidence=0.87,
                agent=self.name,
                metadata={"model": "deterministic", "step": step},
            )
        ]


# ---------------------------------------------------------------------------
# TuringAgent — Logic verification
# ---------------------------------------------------------------------------
class TuringAgent(_LLMAgentBase):
    """Logic verification agent."""
    name = "Turing"

    def propose(self, step: int, state: dict) -> Intent:
        return Intent("turing", self.name,
                      {"formula": f"forall x. P(x, {step})",
                       "verified": True})

    def _deterministic_claim(self, step: int) -> List[GovernedClaim]:
        return [
            GovernedClaim(
                text=f"Verification: proposition forall x. P(x, {step}) holds for {step * 10 + 10} test cases.",
                confidence=0.90,
                agent=self.name,
                metadata={"model": "deterministic", "step": step},
            )
        ]
