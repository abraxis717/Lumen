"""
chronicle_sqlite.py — SQLite-backed immutable event store with WAL mode
========================================================================
Thread-safe, concurrent-read capable event ledger with cryptographic hash
chaining. Uses SQLite WAL mode by default for high-concurrency reads.

Provides the same public API as chronicle_jsonl.py so the two are
swappable behind a single interface.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .event import Event


class SQLiteChronicle:
    """SQLite-backed WORM event ledger with chain verification."""

    SCHEMA = """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL,
            agent TEXT NOT NULL,
            payload TEXT,           -- JSON-serialized payload
            timestamp REAL NOT NULL DEFAULT (strftime('%s', 'now')),
            prev_hash TEXT NOT NULL,
            hash TEXT NOT NULL,
            step INTEGER NOT NULL DEFAULT 0,
            checkpoint INTEGER NOT NULL DEFAULT 0,
            schema_version INTEGER NOT NULL DEFAULT 1
        )
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute(self.SCHEMA)
        self._conn.commit()
        self._head: str = "0" * 64  # genesis null hash
        self._next_id: int = 0

    @contextmanager
    def _cursor(self, commit: bool = True):
        """Context manager for cursor lifecycle."""
        cur = self._conn.cursor()
        try:
            yield cur
            if commit:
                self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ── public API ────────────────────────────────────────────────────
    def append(self, event: Event, checkpoint: bool = False) -> None:
        """Append an event — rejects if chain is broken."""
        if event.prev_hash != self._head:
            raise ValueError(
                f"Chain break: event.prev_hash={event.prev_hash[:16]}… "
                f"!= chain head={self._head[:16]}…"
            )
        event_id = f"evt_{self._next_id:06d}_{event.hash[:8]}"
        self._next_id += 1
        with self._cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO events
                   (event_id, event_type, agent, payload, timestamp, prev_hash, hash, step, checkpoint, schema_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    event.action,
                    event.agent,
                    json.dumps(event.payload, sort_keys=True),
                    time.time(),
                    event.prev_hash,
                    event.hash,
                    event.step,
                    1 if checkpoint else 0,
                    1,
                ),
            )
        self._head = event.hash

    def checkpoint(self, event_id: str) -> None:
        """Mark an existing event as a checkpoint for bounded reconstruction.

        Accepts either an event_id string (e.g. 'evt_000001_a1b2c3d4')
        or an event hash — falls back to hash lookup.
        """
        with self._cursor(commit=True) as cur:
            cur.execute(
                "UPDATE events SET checkpoint = 1 WHERE event_id = ?",
                (event_id,),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "UPDATE events SET checkpoint = 1 WHERE hash = ?",
                    (event_id,),
                )

    def verify(self) -> bool:
        """Walk the chain, recompute every hash — O(n)."""
        events = self.get_chain()
        if not events:
            return True
        prev = "0" * 64
        for ev in events:
            expected = self._hash_event(ev)
            if ev.hash != expected or ev.prev_hash != prev:
                return False
            prev = ev.hash
        return True

    def get_chain(self) -> List[Event]:
        """Return all events in append order."""
        events: List[Event] = []
        with self._cursor(commit=False) as cur:
            cur.execute(
                "SELECT event_type, agent, payload, timestamp, prev_hash, hash, step FROM events ORDER BY id"
            )
            for row in cur.fetchall():
                events.append(
                    Event(
                        step=row[6],
                        action=row[0],
                        agent=row[1],
                        payload=json.loads(row[2]) if row[2] else {},
                        prev_hash=row[4],
                        hash=row[5],
                    )
                )
        return events

    def replay(self) -> List[Event]:
        """Alias for get_chain — swappable with Chronicle (JSONL)."""
        return self.get_chain()

    def get_latest_checkpoint(self) -> Optional[Event]:
        """Return the most recent checkpoint event, or None."""
        with self._cursor(commit=False) as cur:
            cur.execute(
                "SELECT event_type, agent, payload, timestamp, prev_hash, hash, step "
                "FROM events WHERE checkpoint = 1 ORDER BY id DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                return None
            return Event(
                step=row[6],
                action=row[0],
                agent=row[1],
                payload=json.loads(row[2]) if row[2] else {},
                prev_hash=row[4],
                hash=row[5],
            )

    def events_of_type(self, action: str) -> List[Event]:
        return [e for e in self.get_chain() if e.action == action]

    def get_events_since(self, checkpoint_event_id: str) -> List[Event]:
        """Get all events after a given checkpoint event (bounded replay).

        Accepts either an event_id string or an event hash.
        """
        with self._cursor(commit=False) as cur:
            cur.execute(
                "SELECT id FROM events WHERE event_id = ? OR hash = ?",
                (checkpoint_event_id, checkpoint_event_id),
            )
            row = cur.fetchone()
            if row is None:
                return list(self.get_chain())
            checkpoint_id = row[0]
            cur.execute(
                "SELECT event_type, agent, payload, timestamp, prev_hash, hash, step "
                "FROM events WHERE id > ? ORDER BY id",
                (checkpoint_id,),
            )
            events: List[Event] = []
            for row in cur.fetchall():
                events.append(
                    Event(
                        step=row[6],
                        action=row[0],
                        agent=row[1],
                        payload=json.loads(row[2]) if row[2] else {},
                        prev_hash=row[4],
                        hash=row[5],
                    )
                )
            return events

    @property
    def head_hash(self) -> str:
        return self._head

    def __len__(self) -> int:
        with self._cursor(commit=False) as cur:
            cur.execute("SELECT COUNT(*) FROM events")
            return cur.fetchone()[0]

    def emit(
        self,
        action: str,
        payload: Dict[str, Any],
        agent: str = "system",
        step: int = 0,
        checkpoint: bool = False,
    ) -> Event:
        """Convenience to append an event without constructing an Event manually."""
        from .event import Event
        obj = {"step": step, "action": action, "agent": agent, "payload": payload, "prev_hash": self._head}
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha256(canonical.encode()).hexdigest()
        ev = Event(
            step=step, action=action, agent=agent, payload=payload,
            prev_hash=self._head, hash=h,
        )
        self.append(ev, checkpoint=checkpoint)
        return ev

    def __repr__(self) -> str:
        return f"SQLiteChronicle({len(self)} events, head={self._head[:12]}…)"

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

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
