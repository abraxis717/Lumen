"""LumenAgent — Lumen Guardian safety filter as a council member.

Wraps the Lumen Guardian service's pre/post risk assessment as a
GovernedClaim-producing agent.  The agent can operate in two modes:

  1. **HTTP mode** (default): calls the guardian_service.py Flask endpoint
     at localhost:5000 via POST /task.
  2. **Inline mode**: directly imports quick_pre_risk / quick_post_risk
     from the guardian_service module (useful for offline testing).

The agent proposes claims to the council reflecting the current safety
assessment of the system state.  It always emits a GovernedClaim with
provenance so the epistemic graph records the safety verdict.
"""
from __future__ import annotations

import logging
import sys
import os
from typing import Any, Dict, List, Optional

# Make sure we can import from Lumen
_LUMEN_DIR = "/home/joe/ouroboros/Lumen"
if _LUMEN_DIR not in sys.path:
    sys.path.insert(0, _LUMEN_DIR)

from Weaver_ASI.council.claims import GovernedClaim

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Inline safety checks (duplicated from guardian_service.py so that
#  the agent works even when the Flask service is not running.)
# ------------------------------------------------------------------ #

SAFETY_KEYWORDS = {
    "hack", "bypass", "exploit", "harm", "dangerous",
    "unauthorized", "malicious", "exploit", "attack",
}
MAX_INPUT_LENGTH = 2000
MAX_RESPONSE_LENGTH = 5000


def quick_pre_risk(text: str) -> tuple:
    """Returns (risk_score, pre_decision) — same logic as guardian_service.

    Decision thresholds:
        score >= 0.7  → BLOCK
        score >= 0.5  → THROTTLE
        otherwise     → ALLOW
    """
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
    """Heuristic post-check on the LLM output."""
    text_lower = response_text.lower()
    hits = sum(kw in text_lower for kw in SAFETY_KEYWORDS)
    length_penalty = 0.2 if len(response_text) > MAX_RESPONSE_LENGTH else 0.0
    risk = min(1.0, 0.3 * hits + length_penalty)
    if risk >= 0.7:
        return risk, "BLOCK"
    if risk >= 0.5:
        return risk, "THROTTLE"
    return risk, "ALLOW"


# ------------------------------------------------------------------ #
#  LumenAgent
# ------------------------------------------------------------------ #

class LumenAgent:
    """Safety-filter agent that proposes governed claims to the council.

    Attributes:
        name:          Agent name (used as provenance in claims).
        base_url:      Guardian service URL (HTTP mode).
        use_http:      If True, call the Flask service; else use inline checks.
        safety_keywords: Custom set of safety keywords (for inline mode).
    """

    name = "lumen-safety"

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        use_http: bool = True,
        safety_keywords: Optional[set] = None,
    ) -> None:
        self.name = "lumen-safety"
        self.base_url = base_url
        self.use_http = use_http
        if safety_keywords is not None:
            self.safety_keywords = safety_keywords
        else:
            self.safety_keywords = SAFETY_KEYWORDS.copy()

    # ── Legacy interface ───────────────────────────────────────────

    def propose(self, step: int, state: Optional[Dict] = None) -> Any:
        """Legacy propose() for backward compatibility.

        Returns an Intent dict or None.
        """
        claims = self.propose_claims(step, state)
        if not claims:
            return None
        # Return the first claim as a simple intent
        return {
            "action": "safety_assessment",
            "agent": self.name,
            "payload": claims[0].to_event_payload(),
        }

    # ── Phase 3 interface ──────────────────────────────────────────

    def propose_claims(
        self,
        context: Optional[List] = None,
        state: Optional[Dict] = None,
    ) -> List[GovernedClaim]:
        """Emit a safety-assessment GovernedClaim based on the current state.

        Args:
            context:  Optional list of existing beliefs (unused here).
            state:    Optional kernel state dict (e.g. reactor metrics).

        Returns:
            List of GovernedClaim objects (typically 0 or 1).
        """
        try:
            if self.use_http:
                return self._assess_via_http(state)
            else:
                return self._assess_inline(state)
        except Exception as exc:
            logger.warning("LumenAgent safety check failed: %s", exc)
            return [
                GovernedClaim(
                    text=f"Lumen safety check failed: {exc}",
                    confidence=0.1,
                    citations=[],
                    contradicts=[],
                    agent=self.name,
                    metadata={"source": "lumen_safety_filter", "error": str(exc)},
                )
            ]

    # ── Inline assessment ──────────────────────────────────────────

    def _assess_inline(self, state: Optional[Dict] = None) -> List[GovernedClaim]:
        """Assess safety using inline quick_pre_risk / quick_post_risk."""
        # Build a representative text from the kernel state
        if state:
            text = str(state)
        else:
            text = "no state provided"

        pre_score, pre_decision = quick_pre_risk(text)

        if pre_decision == "BLOCK":
            return [
                GovernedClaim(
                    text=f"Pre-risk BLOCK: safety keywords detected "
                         f"(score={pre_score:.2f}). Action denied.",
                    confidence=0.9,
                    citations=[],
                    contradicts=[],
                    agent=self.name,
                    metadata={
                        "source": "lumen_safety_filter",
                        "mode": "inline",
                        "pre_score": pre_score,
                        "pre_decision": pre_decision,
                    },
                )
            ]

        # If allowed, do a post-risk check on the response text
        # (in inline mode we just re-check the same text as a stand-in)
        post_score, post_decision = quick_post_risk(text)

        if post_decision == "BLOCK":
            return [
                GovernedClaim(
                    text=f"Post-risk BLOCK: output safety violation "
                         f"(score={post_score:.2f}).",
                    confidence=0.85,
                    citations=[],
                    contradicts=[],
                    agent=self.name,
                    metadata={
                        "source": "lumen_safety_filter",
                        "mode": "inline",
                        "post_score": post_score,
                        "post_decision": post_decision,
                    },
                )
            ]

        # Everything is safe — still produce a claim so the council
        # records the safety pass (provenance tracking).
        return [
            GovernedClaim(
                text=f"Pre/post-risk ALLOW: system state is safe "
                     f"(pre={pre_score:.2f}, post={post_score:.2f}).",
                confidence=max(pre_score, post_score),
                citations=[],
                contradicts=[],
                agent=self.name,
                metadata={
                    "source": "lumen_safety_filter",
                    "mode": "inline",
                    "pre_score": pre_score,
                    "post_score": post_score,
                    "pre_decision": pre_decision,
                    "post_decision": post_decision,
                },
            )
        ]

    # ── HTTP assessment ────────────────────────────────────────────

    def _assess_via_http(self, state: Optional[Dict] = None) -> List[GovernedClaim]:
        """Assess safety by calling the guardian_service Flask endpoint."""
        import requests as _req

        text = str(state) if state else "no state provided"
        payload = {
            "run_id": f"weaver_{id(self)}",
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
                        citations=[],
                        contradicts=[],
                        agent=self.name,
                        metadata={
                            "source": "lumen_safety_filter",
                            "mode": "http",
                            "guard_result": guard_result,
                            "fault_reason": result.get("fault_reason"),
                        },
                    )
                ]

            # ALLOW or THROTTLE — produce a safety pass claim
            return [
                GovernedClaim(
                    text=f"Guardian ALLOW: system state safe "
                         f"(guard_result={guard_result}).",
                    confidence=0.85,
                    citations=[],
                    contradicts=[],
                    agent=self.name,
                    metadata={
                        "source": "lumen_safety_filter",
                        "mode": "http",
                        "guard_result": guard_result,
                    },
                )
            ]
        except Exception as exc:
            logger.warning("LumenAgent HTTP call failed: %s", exc)
            return [
                GovernedClaim(
                    text=f"Guardian service unreachable: {exc}",
                    confidence=0.2,
                    citations=[],
                    contradicts=[],
                    agent=self.name,
                    metadata={
                        "source": "lumen_safety_filter",
                        "mode": "http",
                        "error": str(exc),
                    },
                )
            ]
