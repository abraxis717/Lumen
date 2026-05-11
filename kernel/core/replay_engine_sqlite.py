"""
replay_engine_sqlite.py — SQLite-backed replay engine with bounded reconstructability
======================================================================================
Rebuilds state from a SQLite Chronicle to prove zero hidden state.
If replay matches live state, the system has no memory of unrecorded events.
Implements I-16 bounded reconstructability: replay is O(ΔN) where ΔN
is the number of events since the latest checkpoint.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List, Tuple

from .chronicle_sqlite import SQLiteChronicle


class ReplayEngine:
    """I-16 verifier: bounded total replay equivalence."""

    def __init__(self, chronicle: SQLiteChronicle):
        self.chronicle = chronicle

    def verify_equivalence(
        self,
        live_state: Dict[str, Any],
        transition_fn: Callable[[Dict[str, Any], Any], Dict[str, Any]],
    ) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Rebuild state from SQLite Chronicle using bounded reconstructability.

        1. Find latest checkpoint event.
        2. Replay events from checkpoint to target.
        3. Compare reconstructed state to live_state.

        Returns (equivalent, reconstructed, issues).
        """
        issues: List[str] = []
        s: Dict[str, Any] = {
            "diversity": 100,
            "counter": 0,
            "result": 0,
            "telemetry": {},
            "severity": "NOMINAL",
        }

        # Phase 1: chain integrity
        if not self.chronicle.verify():
            issues.append("✗ Chronicle hash chain is BROKEN")

        # Phase 2: bounded reconstructability
        checkpoint = self.chronicle.get_latest_checkpoint()
        if checkpoint:
            events = self.chronicle.get_events_since(checkpoint.hash)
        else:
            events = self.chronicle.get_chain()

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
        """SHA-256 fingerprint of the entire Chronicle chain."""
        h = hashlib.sha256()
        for ev in self.chronicle.get_chain():
            h.update(ev.hash.encode())
        return h.hexdigest()

    def describe(self) -> str:
        """Human-readable replay summary."""
        events = self.chronicle.get_chain()
        return "\n".join(
            [
                "Lumen ASI Replay Engine Report",
                "=" * 50,
                f"Chronicle events: {len(events)}",
                f"Chain verified:   {'YES' if self.chronicle.verify() else 'NO'}",
                f"Chain fingerprint: {self.fingerprint()}",
                "=" * 50,
            ]
        )
