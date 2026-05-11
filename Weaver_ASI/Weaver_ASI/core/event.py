"""
event.py — Canonical immutable Event & Intent types
====================================================
Event:  hash-chained, frozen dataclass — the atomic unit of truth.
Intent: proposed action before Gate approval — mutable, transient.

Every event in the Chronicle is immutable and cryptographically hash-chained.
Rebuilding from zero is deterministic (I27).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True, slots=True)
class Event:
    """Immutable, hash-chained event — the atomic unit of the Chronicle."""
    step:      int
    action:    str
    agent:     str
    payload:   Dict[str, Any]
    prev_hash: str
    hash:      str

    @staticmethod
    def mint(step: int, intent: "Intent", prev_hash: str) -> "Event":
        """Create an Event from an Intent + previous chain head."""
        obj = {
            "step": step,
            "action": intent.action,
            "agent": intent.agent,
            "payload": intent.payload,
            "prev_hash": prev_hash,
        }
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha256(canonical.encode()).hexdigest()
        return Event(
            step=step,
            action=intent.action,
            agent=intent.agent,
            payload=intent.payload,
            prev_hash=prev_hash,
            hash=h,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "agent": self.agent,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


@dataclass
class Intent:
    """A proposed action — mutable until Gate verdict."""
    action:    str
    agent:     str
    payload:   Dict[str, Any]
    attestation: Optional[Dict[str, Any]] = field(default=None, repr=False)

    def __repr__(self):
        return f"Intent({self.action!r} ← {self.agent!r})"
