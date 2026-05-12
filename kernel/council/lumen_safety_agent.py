"""
lumen_safety_agent.py — Lumen Guardian safety filter (Phase 3.5 Runtime Swarm)

Wraps the Lumen Guardian service as a council agent that produces GovernedClaims
reflecting safety assessments. Accepts a MobileModel and StratifiedRetriever for
LLM-backed risk analysis. Falls back to inline heuristic checks.

Phase 3.5 changes:
  - __init__(model, retriever, **kwargs) — wires up live inference and epistemic context.
  - propose_claims(context, state) — evaluates safety of current state; if a model
    is provided, asks it to assess risk from the epistemic context; otherwise falls
    back to inline quick_pre_risk / quick_post_risk.
  - Legacy propose(step, state) still works.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from kernel.council.claims import GovernedClaim

logger = logging.getLogger(__name__)

SAFETY_KEYWORDS = {
    "hack", "bypass", "exploit", "harm", "dangerous",
    "unauthorized", "malicious", "attack",
}
MAX_INPUT_LENGTH = 2000
MAX_RESPONSE_LENGTH = 5000


def quick_pre_risk(text: str) -> tuple:
    """Heuristic pre-risk assessment. Returns (score, decision)."""
    text_lower = text.lower()
    hits = sum(kw in text_lower for kw in SAFETY_KEYWORDS)
    length_penalty = 0.3 if len(text) > MAX_INPUT_LENGTH else 0.0
    risk = min(1.0, 0.25 * hits + length_penalty)
    if risk >= 0.7:
        return risk, "BLOCK"
    if risk >= 0.5:
        return risk, "THROTTLE"
    return risk, "ALLOW"


def quick_post_risk(response_text: str) -> tuple:
    """Heuristic post-risk assessment."""
    text_lower = response_text.lower()
    hits = sum(kw in text_lower for kw in SAFETY_KEYWORDS)
    length_penalty = 0.2 if len(response_text) > MAX_RESPONSE_LENGTH else 0.0
    risk = min(1.0, 0.3 * hits + length_penalty)
    if risk >= 0.7:
        return risk, "BLOCK"
    if risk >= 0.5:
        return risk, "THROTTLE"
    return risk, "ALLOW"


class LumenSafetyAgent:
    """Safety-filter agent that proposes GovernedClaims to the council.

    Args:
        model:       Optional MobileModel (GGUF) for LLM-based risk analysis.
        retriever:   Optional StratifiedRetriever for epistemic context.
        use_http:    If True, call the guardian_service Flask endpoint.
                     If False, use inline quick_pre_risk / quick_post_risk.
    """

    name = "lumen-safety"

    def __init__(
        self,
        model: Optional[Any] = None,
        retriever: Optional[Any] = None,
        use_http: bool = True,
        base_url: str = "http://localhost:5000",
        **kwargs: Any,
    ) -> None:
        self._model = model
        self._retriever = retriever
        self.use_http = use_http
        self.base_url = base_url

    def propose_claims(self, context: Optional[List] = None, state: Optional[Dict] = None) -> List[GovernedClaim]:
        """Emit a safety-assessment GovernedClaim.

        If a MobileModel is wired, ask it to assess safety from the
        epistemic context.  Otherwise fall back to inline heuristics.
        """
        try:
            if self._model is not None and context is not None:
                return self._assess_via_llm(context)
            elif self.use_http:
                return self._assess_via_http(state)
            else:
                return self._assess_inline(state)
        except Exception as exc:
            logger.warning("LumenSafetyAgent check failed: %s", exc)
            return [
                GovernedClaim(
                    text=f"Lumen safety check failed: {exc}",
                    confidence=0.1,
                    agent=self.name,
                    metadata={"source": "lumen_safety_filter", "error": str(exc)},
                )
            ]

    def _assess_via_llm(self, context: List) -> List[GovernedClaim]:
        """Ask the LLM to assess safety from epistemic context."""
        context_text = "\n".join(str(n) for n in context)
        prompt = (
            "You are the Lumen safety filter agent.\n"
            "Review the following epistemic context and determine if the "
            "system state is safe.\n\n"
            "Context:\n"
            f"{context_text}\n\n"
            "Respond as a JSON object with keys: claim, confidence, citations.\n"
        )
        try:
            generated = self._model.generate(prompt, max_tokens=128)
            claims = self._parse_output(generated)
            if claims:
                return claims
        except Exception as exc:
            logger.warning("LumenSafetyAgent LLM failed: %s", exc)

        # Fallback to inline heuristics
        return self._assess_inline(None)

    @staticmethod
    def _assess_inline(state: Optional[Dict] = None) -> List[GovernedClaim]:
        text = str(state) if state else "no state provided"

        pre_score, pre_decision = quick_pre_risk(text)

        if pre_decision == "BLOCK":
            return [
                GovernedClaim(
                    text=f"Pre-risk BLOCK: safety keywords detected "
                         f"(score={pre_score:.2f}). Action denied.",
                    confidence=0.9,
                    agent="lumen-safety",
                    metadata={"source": "lumen_safety_filter", "mode": "inline"},
                )
            ]

        post_score, post_decision = quick_post_risk(text)
        if post_decision == "BLOCK":
            return [
                GovernedClaim(
                    text=f"Post-risk BLOCK: output safety violation "
                         f"(score={post_score:.2f}).",
                    confidence=0.85,
                    agent="lumen-safety",
                    metadata={"source": "lumen_safety_filter", "mode": "inline"},
                )
            ]

        return [
            GovernedClaim(
                text=f"Pre/post-risk ALLOW: system state is safe "
                     f"(pre={pre_score:.2f}, post={post_score:.2f}).",
                confidence=max(pre_score, post_score),
                agent="lumen-safety",
                metadata={"source": "lumen_safety_filter", "mode": "inline"},
            )
        ]

    def _assess_via_http(self, state: Optional[Dict] = None) -> List[GovernedClaim]:
        try:
            import requests as _req
        except ImportError:
            return self._assess_inline(state)

        text = str(state) if state else "no state provided"
        payload = {
            "run_id": f"lumen_safety_{id(self)}",
            "intent": "council_safety_assessment",
            "persona": "science",
            "inputs": {"text": text},
        }

        try:
            resp = _req.post(
                f"{self.base_url}/task",
                json=payload,
                timeout=5,
            )
            result = resp.json()
            guard_result = result.get("guard_result", "UNKNOWN")

            if guard_result in ("BLOCK", "HARD_FAIL"):
                return [
                    GovernedClaim(
                        text=f"Guardian BLOCK: {result.get('fault_reason', 'unknown')}",
                        confidence=0.95,
                        agent="lumen-safety",
                        metadata={"source": "lumen_safety_filter", "mode": "http"},
                    )
                ]

            return [
                GovernedClaim(
                    text=f"Guardian ALLOW: system state safe "
                         f"(guard_result={guard_result}).",
                    confidence=0.85,
                    agent="lumen-safety",
                    metadata={"source": "lumen_safety_filter", "mode": "http"},
                )
            ]
        except Exception as exc:
            logger.warning("LumenSafetyAgent HTTP call failed: %s", exc)
            return [
                GovernedClaim(
                    text=f"Guardian service unreachable: {exc}",
                    confidence=0.2,
                    agent="lumen-safety",
                    metadata={"source": "lumen_safety_filter", "mode": "http"},
                )
            ]

    @staticmethod
    def _parse_output(text: str) -> List[GovernedClaim]:
        """Parse model-generated text into GovernedClaim(s)."""
        text = text.strip()

        # Try JSON parsing
        import json as _json
        json_matches = re.findall(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
        json_text = None
        if json_matches:
            json_text = json_matches[0].strip()
        elif text.startswith("["):
            json_text = text

        if json_text:
            try:
                data = _json.loads(json_text)
                items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else None)
                if items:
                    claims = []
                    for item in items:
                        if isinstance(item, dict):
                            claim_text = item.get("claim", item.get("text", str(item)))
                            confidence = item.get("confidence", 0.85)
                            if not isinstance(confidence, (int, float)):
                                try:
                                    confidence = float(confidence)
                                except (ValueError, TypeError):
                                    confidence = 0.85
                            claims.append(GovernedClaim(
                                text=claim_text,
                                confidence=float(confidence),
                                citations=item.get("citations", []),
                                agent="lumen-safety",
                                metadata={"model": "gguf-model"},
                            ))
                    if claims:
                        return claims
            except (_json.JSONDecodeError, Exception):
                pass

        # Heuristic fallback
        claims = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("```") or not line:
                continue
            if len(line) > 10:
                claims.append(GovernedClaim(
                    text=line,
                    confidence=0.85,
                    agent="lumen-safety",
                    metadata={"model": "gguf-model"},
                ))
        return claims

    def propose(self, step: int, state: Optional[Dict] = None) -> Optional[Dict]:
        """Legacy propose — returns a dict Intent for backward compatibility."""
        claims = self.propose_claims(None, state)
        if not claims:
            return None
        return {
            "action": "safety_assessment",
            "agent": self.name,
            "payload": claims[0].to_event_payload(),
        }
