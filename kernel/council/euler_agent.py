"""
euler_agent.py — Euler: Symbolic computation agent (Phase 3.5 Runtime Swarm)

Accepts a MobileModel (GGUF) and a StratifiedRetriever for live LLM-backed
reasoning. Falls back to deterministic symbolic computation when no model
is provided.

Phase 3.5 changes:
  - __init__(model, retriever, **kwargs) — wires up live inference and epistemic context.
  - propose_claims(step, state) — builds a prompt from the top 3 operational beliefs,
    calls model.generate(), parses into GovernedClaim with confidence.
  - Legacy propose(step, state) still works for backward compatibility.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from kernel.core.event import Intent
from kernel.council.claims import GovernedClaim

logger = logging.getLogger(__name__)


class EulerAgent:
    """Symbolic computation agent with live LLM reasoning.

    Args:
        model:       Optional MobileModel (GGUF) for live inference.
        retriever:   Optional StratifiedRetriever for epistemic context.
        max_tokens:  Maximum tokens per generate() call (default 128).
    """

    name = "Euler"

    def __init__(
        self,
        model: Optional[Any] = None,
        retriever: Optional[Any] = None,
        max_tokens: int = 128,
        **kwargs: Any,
    ) -> None:
        self._model = model
        self._retriever = retriever
        self._max_tokens = max_tokens

    def propose_claims(self, step: int, state: Dict) -> List[GovernedClaim]:
        """Propose a symbolically-grounded GovernedClaim via live LLM.

        1. Queries the retriever for the top 3 operational beliefs.
        2. Builds a prompt incorporating those beliefs.
        3. Calls model.generate() (or falls back to deterministic compute).
        4. Parses the output into a GovernedClaim, asserting confidence
           from the text or defaulting to 0.85.
        """
        context_text = self._build_context()
        prompt = self._format_prompt(step, state, context_text)

        if self._model is not None:
            try:
                generated = self._model.generate(prompt, max_tokens=self._max_tokens)
                claims = self._parse_output(generated, step)
                if claims:
                    return claims
            except Exception as exc:
                logger.warning("Euler LLM generation failed: %s", exc)

        # Fallback: deterministic symbolic computation
        return self._deterministic_claim(step)

    def propose(self, step: int, state: Dict) -> Intent:
        """Legacy propose — wraps the first claim as an Intent."""
        claims = self.propose_claims(step, state)
        if claims:
            return Intent(
                action="compute_symbolic",
                agent=self.name,
                payload=claims[0].to_event_payload(),
            )
        return Intent(
            "compute_symbolic",
            self.name,
            {"value": 42 + step, "drift": 0.01},
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _build_context(self) -> str:
        """Serialize top 3 operational beliefs for the LLM prompt."""
        if not self._retriever:
            return ""
        try:
            results = self._retriever.query(limit=10, min_weight=0.0)
            # Prefer operational stratum, fall back to any
            ops = [(n, w) for n, w in results if n.stratum.value == "operational"][:3]
            if not ops:
                ops = results[:3]
            if not ops:
                return ""
            lines = [f"Current operational beliefs ({len(ops)}):"]
            for node, weight in ops:
                lines.append(
                    f"  [{node.stratum.value}] w={weight:.3f}: {node.claim}"
                )
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("Euler context build failed: %s", exc)
            return ""

    @staticmethod
    def _format_prompt(step: int, state: Dict, context: str) -> str:
        state_snippet = ", ".join(f"{k}={v}" for k, v in state.items())
        prompt = (
            f"[Step {step}] System state: {state_snippet}\n\n"
            "You are the Euler (symbolic computation) agent.\n"
            "Propose a single GovernedClaim about the current system state.\n"
            "Respond as a JSON object with keys: claim, confidence, citations.\n"
        )
        if context:
            prompt += f"\n{context}\n"
        return prompt

    @staticmethod
    def _parse_output(text: str, step: int) -> List[GovernedClaim]:
        """Parse model-generated text into GovernedClaim(s).

        Asserts confidence from the text, or defaults to 0.85.
        """
        text = text.strip()

        # Try JSON parsing first (look for JSON array or object)
        import re
        json_matches = re.findall(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
        json_text = None
        if json_matches:
            json_text = json_matches[0].strip()
        elif text.startswith("["):
            json_text = text

        if json_text:
            try:
                data = json.loads(json_text)
                items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else None)
                if items:
                    claims = []
                    for item in items:
                        if isinstance(item, dict):
                            claim_text = item.get("claim", item.get("text", str(item)))
                            confidence = item.get("confidence", 0.85)
                            # Assert confidence in the text; if missing or invalid, default to 0.85
                            if not isinstance(confidence, (int, float)):
                                try:
                                    confidence = float(confidence)
                                except (ValueError, TypeError):
                                    confidence = 0.85
                            claims.append(GovernedClaim(
                                text=claim_text,
                                confidence=float(confidence),
                                citations=item.get("citations", []),
                                agent="Euler",
                                metadata={"model": "gguf-model", "step": step},
                            ))
                    if claims:
                        return claims
            except (json.JSONDecodeError, Exception):
                pass

        # Heuristic fallback: extract claim-like lines
        claims = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("```") or not line:
                continue
            if line.startswith("</think>") or line.startswith("<think"):
                continue
            if len(line) > 10:
                claims.append(GovernedClaim(
                    text=line,
                    confidence=0.85,  # Default confidence
                    agent="Euler",
                    metadata={"model": "gguf-model", "step": step},
                ))
        return claims

    def _deterministic_claim(self, step: int) -> List[GovernedClaim]:
        """Legacy deterministic symbolic computation."""
        return [
            GovernedClaim(
                text=f"Symbolic computation: the system converges at value "
                     f"{42 + step}. Drift: 0.01.",
                confidence=0.85,
                agent=self.name,
                metadata={"model": "deterministic", "step": step},
            )
        ]
