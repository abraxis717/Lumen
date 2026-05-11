"""
replay_engine.py — I27 Total Replay Equivalence Verifier
=========================================================
Rebuilds the ASI's entire worldview from the Chronicle to prove
zero hidden state. If replay matches live state, the system has
no memory of unrecorded events.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Tuple

from .chronicle import Chronicle
from .event import Event


class ReplayEngine:
    """I27 verifier: total replay equivalence."""

    def __init__(self, chronicle: Chronicle):
        self.chronicle = chronicle

    def verify_equivalence(
        self,
        live_state: Dict[str, Any],
        transition_fn,  # callable(state, event) -> new_state
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Rebuild state from Chronicle. Compare to live_state.
        Returns (equivalent, reconstructed, issues).
        """
        issues: List[str] = []
        s: Dict[str, Any] = {"diversity": 100, "counter": 0, "result": 0,
                              "telemetry": {}, "severity": "NOMINAL"}

        # Phase 1: chain integrity
        if not self.chronicle.verify():
            issues.append("✗ Chronicle hash chain is BROKEN")

        # Phase 2: reconstruct
        events = self.chronicle.replay()
        for ev in events:
            s = transition_fn(s, ev)

        # Phase 3: compare
        mismatches = []
        for key in set(live_state.keys()) | set(s.keys()):
            if live_state.get(key) != s.get(key):
                mismatches.append(
                    f"  {key}: live={live_state.get(key)!r} vs replay={s.get(key)!r}"
                )

        if mismatches:
            issues.extend(mismatches)
            return False, s, issues

        issues.append("✓ Total replay equivalence: PASS")
        return True, s, issues

    def fingerprint(self) -> str:
        """SHA-256 fingerprint of the entire Chronicle."""
        h = hashlib.sha256()
        for ev in self.chronicle.replay():
            h.update(ev.hash.encode())
        return h.hexdigest()

    def describe(self) -> str:
        """Human-readable replay summary."""
        lines = [
            f"Weaver ASI Replay Engine Report",
            f"{'='*50}",
            f"Chronicle events: {len(self.chronicle)}",
            f"Chain verified:   {'YES' if self.chronicle.verify() else 'NO'}",
            f"Chain fingerprint: {self.fingerprint()}",
            f"{'='*50}",
        ]
        return "\n".join(lines)
