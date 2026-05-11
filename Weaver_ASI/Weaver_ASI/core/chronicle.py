"""
chronicle.py — Event-sourced WORM ledger
=========================================
Sole source of system memory. Append-only, hash-chained, verified.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from Weaver_ASI.core.event import Event


class Chronicle:
    """Write-Once-Read-Many event ledger with chain verification."""

    def __init__(self) -> None:
        self._events: List[Event] = []
        self._head: str = "0" * 64  # genesis null hash

    # ── public API ───────────────────────────────────────────────────
    def append(self, event: Event) -> None:
        """Append an event — rejects if chain is broken."""
        if event.prev_hash != self._head:
            raise ValueError(
                f"Chain break: event.prev_hash={event.prev_hash[:16]}… "
                f"!= chain head={self._head[:16]}…"
            )
        self._events.append(event)
        self._head = event.hash

    def verify(self) -> bool:
        """Walk the chain, recompute every hash — O(n)."""
        prev = "0" * 64
        for ev in self._events:
            expected = self._hash_event(ev)
            if ev.hash != expected or ev.prev_hash != prev:
                return False
            prev = ev.hash
        return True

    def replay(self) -> List[Event]:
        return list(self._events)

    def events_of_type(self, action: str) -> List[Event]:
        return [e for e in self._events if e.action == action]

    @property
    def head_hash(self) -> str:
        return self._head

    def __len__(self) -> int:
        return len(self._events)

    def emit(self, action: str, payload: Dict[str, Any], agent: str = "system", step: int = 0) -> None:
        """Convenience to append an event without constructing an Event manually."""
        from Weaver_ASI.core.event import Event
        obj = {"step": step, "action": action, "agent": agent, "payload": payload, "prev_hash": self._head}
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha256(canonical.encode()).hexdigest()
        self.append(Event(step=step, action=action, agent=agent, payload=payload, prev_hash=self._head, hash=h))

    def __repr__(self) -> str:
        return f"Chronicle({len(self)} events, head={self._head[:12]}…)"

    # ── internals ────────────────────────────────────────────────────
    @staticmethod
    def _hash_event(ev: Event) -> str:
        obj = {
            "step": ev.step,
            "action": ev.action,
            "agent": ev.agent,
            "payload": ev.payload,
            "prev_hash": ev.prev_hash,
        }
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
