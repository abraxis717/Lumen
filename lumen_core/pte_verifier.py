#!/usr/bin/env python3
"""pte_verifier.py — Proof-of-Trust/Execution verifier (Sovereignty Gate).

Implements a sovereignty gate that returns one of:
  - FULL:    system is fully sovereign and trusted
  - DEGRADED: system has partial trust — proceed with caution
  - FAIL_CLOSED: system is untrusted — block inference

Decision logic (A021 gap closure):
  Verdict = FULL if ALL of:
    - risk_score < 0.5 (low risk)
    - coherence_score > 0.3 (decent coherence)
    - chronicle_hash is non-empty and valid (hash chain intact)

  Verdict = DEGRADED if:
    - risk_score < 0.8 (not yet critical)
    - coherence_score > 0.1 (minimal coherence)
    - chronicle_hash is non-empty (chain exists but may be weak)

  Verdict = FAIL_CLOSED otherwise.

The PTE verifier sits between the Semantic Gate and the Decision Engine
in the chat pipeline, acting as a sovereignty gate before the full
decision engine processes the response.
"""

import hashlib
import logging
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger("lumen_core.pte_verifier")


class PTEVerdict(Enum):
    """Sovereignty gate verdict levels."""
    FULL = "FULL"
    DEGRADED = "DEGRADED"
    FAIL_CLOSED = "FAIL_CLOSED"


class PTEVerifier:
    """Proof-of-Trust/Execution verifier.

    Evaluates system sovereignty state from three signals:
      1. risk_score (from the Semantic Gate / Decision Engine)
      2. coherence_score (from Elpis CoherenceMonitor)
      3. chronicle_hash (from the event hash chain)

    Returns a PTEVerdict and a detailed score dict.
    """

    # ── Thresholds ─────────────────────────────────────────────────
    RISK_FULL = 0.5        # risk < this → pass risk check for FULL
    RISK_DEGRADED = 0.8    # risk < this → pass for DEGRADED (otherwise FAIL)

    COHERENCE_FULL = 0.3   # coherence > this → pass for FULL
    COHERENCE_DEGRADED = 0.1  # coherence > this → pass for DEGRADED

    # ── Constructor ────────────────────────────────────────────────

    def __init__(
        self,
        risk_threshold_full: float = RISK_FULL,
        risk_threshold_degraded: float = RISK_DEGRADED,
        coherence_threshold_full: float = COHERENCE_FULL,
        coherence_threshold_degraded: float = COHERENCE_DEGRADED,
    ):
        self.risk_full = risk_threshold_full
        self.risk_degraded = risk_threshold_degraded
        self.coherence_full = coherence_threshold_full
        self.coherence_degraded = coherence_threshold_degraded

    # ── Public API ─────────────────────────────────────────────────

    def verify(
        self,
        risk_score: float,
        coherence_score: float,
        chronicle_hash: str,
    ) -> Dict:
        """Evaluate sovereignty state and return verdict + details.

        Args:
            risk_score:      Risk score from the decision pipeline (0.0–1.0).
            coherence_score: Coherence score from Elpis (0.0–1.0 or streak).
            chronicle_hash:  Latest event hash from the chronicle chain.

        Returns:
            dict with keys:
              verdict (PTEVerdict),
              passed (bool: True for FULL/DEGRADED, False for FAIL_CLOSED),
              score (float: 0.0–1.0 composite sovereignty score),
              details (dict of component scores),
        """
        # ── 1. Risk check ──────────────────────────────────────────
        risk_pass_full = risk_score < self.risk_full
        risk_pass_degraded = risk_score < self.risk_degraded

        # ── 2. Coherence check ─────────────────────────────────────
        # Handle raw streak values (e.g., 100, 500) by normalising
        normalized_coherence = min(coherence_score / 100.0, 1.0) if coherence_score > 10 else coherence_score
        coherence_pass_full = normalized_coherence > self.coherence_full
        coherence_pass_degraded = normalized_coherence > self.coherence_degraded

        # ── 3. Chronicle hash check ────────────────────────────────
        hash_valid = self._validate_hash(chronicle_hash)
        hash_pass = hash_valid is not None  # non-empty, non-trivial

        # ── 4. Determine verdict ───────────────────────────────────
        if risk_pass_full and coherence_pass_full and hash_pass:
            verdict = PTEVerdict.FULL
        elif risk_pass_degraded and coherence_pass_degraded and hash_pass:
            verdict = PTEVerdict.DEGRADED
        else:
            verdict = PTEVerdict.FAIL_CLOSED

        # ── 5. Composite score ─────────────────────────────────────
        score = self._composite_score(risk_score, normalized_coherence, hash_pass)

        return {
            "verdict": verdict.value,
            "passed": verdict != PTEVerdict.FAIL_CLOSED,
            "score": round(score, 4),
            "details": {
                "risk_score": risk_score,
                "coherence_score": coherence_score,
                "normalized_coherence": round(normalized_coherence, 4),
                "risk_full_pass": risk_pass_full,
                "risk_degraded_pass": risk_pass_degraded,
                "coherence_full_pass": coherence_pass_full,
                "coherence_degraded_pass": coherence_pass_degraded,
                "hash_valid": hash_valid,
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_hash(hash_str: str) -> Optional[str]:
        """Validate that a chronicle hash is non-empty and well-formed.

        Returns the hash if valid, None otherwise.
        """
        if not hash_str or hash_str == "N/A" or hash_str == "unknown":
            return None
        # Must be a non-empty hex string
        try:
            decoded = bytes.fromhex(hash_str)
            if len(decoded) == 0:
                return None
            return hash_str
        except ValueError:
            # Try SHA-256 format (64 hex chars)
            if len(hash_str) >= 8:
                return hash_str[:16]
            return None

    def _composite_score(self, risk_score: float,
                         coherence: float,
                         hash_valid: bool) -> float:
        """Compute a 0.0–1.0 sovereignty score.

        Lower risk = better. Higher coherence = better. Hash valid = +0.15.
        """
        # Risk component (inverted: low risk = high score)
        risk_score_norm = 1.0 - min(risk_score, 1.0)

        # Coherence component
        coherence_norm = min(coherence, 1.0)

        # Hash component
        hash_score = 0.15 if hash_valid else 0.0

        # Weighted combination
        score = 0.45 * risk_score_norm + 0.40 * coherence_norm + hash_score
        return min(max(score, 0.0), 1.0)

    def evaluate(self, risk_score: float,
                 coherence_score: float,
                 chronicle_hash: str) -> bool:
        """Convenience method: returns True if verdict is FULL or DEGRADED."""
        result = self.verify(risk_score, coherence_score, chronicle_hash)
        return result["passed"]


# ── Module-level singleton for use in lumen_service ─────────────────────

_default_verifier = PTEVerifier()


def pte_verify(risk_score: float, coherence_score: float,
               chronicle_hash: str) -> Dict:
    """Module-level convenience function for PTE verification."""
    return _default_verifier.verify(risk_score, coherence_score, chronicle_hash)
