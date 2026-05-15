"""
TextSafetyFilter — Constitutional + pattern-based text gate.

Replaces the dead CartPole/PhaseSpace safety filter with a text-native
filter that checks:
  1. Blocked pattern presence
  2. Constitutional axiom alignment
  3. Pass/Fail verdict

Usage:
    kernel = ConstitutionalKernel()
    kernel.load_defaults()
    tf = TextSafetyFilter(kernel, blocked_patterns=["hack", "exploit"])
    result = tf.check("I want to hack the system")
    # result = {"verdict": "BLOCK", "reason": "Blocked pattern: hack"}
"""
import re
from typing import List, Optional

from kernel.constitutional.constitutional_kernel import ConstitutionalKernel


class TextSafetyFilter:
    """Text-native safety filter with constitutional validation."""

    VERDICT_BLOCK = "BLOCK"
    VERDICT_HARD_FAIL = "HARD_FAIL"
    VERDICT_ALLOW = "ALLOW"

    def __init__(
        self,
        constitutional_kernel: Optional[ConstitutionalKernel] = None,
        blocked_patterns: Optional[List[str]] = None,
        max_length: int = 8192,
    ):
        self.constitutional = constitutional_kernel
        self.blocked = [p.lower() for p in (blocked_patterns or [])]
        self.max_length = max_length
        # Pre-compile patterns for speed
        self._blocked_re = [
            re.compile(re.escape(p), re.IGNORECASE) for p in self.blocked
        ]

    def check(self, text: str) -> dict:
        """Run the full text safety check pipeline.

        Returns:
            dict with keys:
              verdict: str — "BLOCK", "HARD_FAIL", or "ALLOW"
              reason: str — human-readable explanation
              blocked_match: str | None — the first blocked pattern matched
              constitutional_violation: bool
        """
        # 0. Length guard (CBF projection)
        if len(text) > self.max_length:
            return {
                "verdict": self.VERDICT_BLOCK,
                "reason": f"Exceeds max length {self.max_length}",
                "blocked_match": None,
                "constitutional_violation": False,
            }

        # 1. Blocked pattern match (fast-path)
        for i, pattern in enumerate(self.blocked):
            if pattern in text.lower():
                return {
                    "verdict": self.VERDICT_BLOCK,
                    "reason": f"Blocked pattern: {pattern}",
                    "blocked_match": pattern,
                    "constitutional_violation": False,
                }

        # 2. Constitutional validation
        constitutional_violation = False
        if self.constitutional is not None:
            if not self.constitutional.is_valid(text):
                constitutional_violation = True

        # 3. Pass
        if constitutional_violation:
            return {
                "verdict": self.VERDICT_HARD_FAIL,
                "reason": "Constitutional violation",
                "blocked_match": None,
                "constitutional_violation": True,
            }

        return {
            "verdict": self.VERDICT_ALLOW,
            "reason": "Passed",
            "blocked_match": None,
            "constitutional_violation": False,
        }
