"""
chronicle_jsonl.py — JSONL-backed immutable event store
=========================================================
Lightweight, file-based event ledger for mobile / resource-constrained
environments. The same public API as chronicle_sqlite.py so the two are
swappable.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from .event import Event


class Chronicle:
    """Write-Once-Read-Many event ledger with chain verification.

    JSONL-backed — suitable for mobile / resource-constrained environments.
    Swap with SQLiteChronicle by using lumen.core.chronicle_sqlite instead.
    """

    def __init__(self) -> None:
        self._events: List[Event] = []
        self._head: str = "0" * 64  # genesis null hash

    @classmethod
    def load_from_jsonl(cls, filepath: str) -> "Chronicle":
        """Load events from a JSONL file into a new Chronicle instance.

        Args:
            filepath: Path to the JSONL file.

        Returns:
            A Chronicle instance populated with the events from the file.
        """
        chronicle = cls()
        with open(filepath, "r") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Invalid JSON on line {line_num} in {filepath}: {exc}"
                    ) from exc
                chronicle._events.append(
                    Event(
                        step=data["step"],
                        action=data["action"],
                        agent=data["agent"],
                        payload=data["payload"],
                        prev_hash=data.get("prev_hash", "0" * 64),
                        hash=data.get("hash", ""),
                    )
                )
        return chronicle

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
        obj = {"step": step, "action": action, "agent": agent, "payload": payload, "prev_hash": self._head}
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha256(canonical.encode()).hexdigest()
        self.append(Event(step=step, action=action, agent=agent, payload=payload, prev_hash=self._head, hash=h))

    def __repr__(self) -> str:
        return f"Chronicle({len(self)} events, head={self._head[:12]}…)"

    # ── swappable API (SQLiteChronicle compatibility) ─────────────────
    def checkpoint(self, event_id: str) -> None:
        """No-op for JSONL — checkpoints are implicit."""

    def notarize_checkpoint(self, event_id: str, steward_sig: str = "") -> Optional[Event]:
        """No-op for JSONL — checkpoints are implicit. Returns None."""
        return None

    def get_latest_checkpoint(self) -> Optional[Event]:
        """Return the last event as implicit checkpoint, or None."""
        if self._events:
            return self._events[-1]
        return None

    def get_events_since(self, checkpoint_event_id: str) -> List[Event]:
        """Return events after the given checkpoint (JSONL always replays all)."""
        idx = -1
        for i, ev in enumerate(self._events):
            if ev.hash == checkpoint_event_id or ev.action == checkpoint_event_id:
                idx = i
                break
        if idx == -1:
            return list(self._events)
        return self._events[idx + 1:]

    def close(self) -> None:
        """No-op for JSONL."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    # ── internals ─────────────────────────────────────────────────────
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
