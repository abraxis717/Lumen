"""
cdc.py - Change-Data-Capture Outbox for the Chronicle

The CDCOutbox is a lightweight SQLite-backed table that every chronicle event
is published into.  External consumers poll it for new (unpublished) events and
acknowledge delivery by marking rows as published.

Schema::

    CREATE TABLE outbox (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id      TEXT    UNIQUE NOT NULL,
        event_type    TEXT    NOT NULL,
        payload_json  TEXT,
        created_at    REAL    DEFAULT (strftime('%s', 'now')),
        published     INTEGER DEFAULT 0
    )
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event_id(event) -> str:
    """Derive a stable unique key from an Event (hash field)."""
    return event.hash


def _event_type(event) -> str:
    """Derive a human-readable event type from the event's action+agent."""
    return f"{event.agent}.{event.action}"


def _payload_json(event) -> str:
    """Serialize an Event's payload to JSON."""
    return json.dumps(asdict(event), sort_keys=True)


# ---------------------------------------------------------------------------
# CDCOutbox
# ---------------------------------------------------------------------------

class CDCOutbox:
    """SQLite-backed change-data-capture outbox.

    Every event emitted by a Chronicle is inserted here so that external
    consumers can poll for new (unpublished) events and acknowledge delivery
    by marking rows as published.

    Thread-safe: SQLite connections are created per-call with
    ``check_same_thread=False`` so the outbox can be used across threads.
    """

    SCHEMA = (
        "CREATE TABLE IF NOT EXISTS outbox ("
        "  id            INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  event_id      TEXT    UNIQUE NOT NULL,"
        "  event_type    TEXT    NOT NULL,"
        "  payload_json  TEXT,"
        "  created_at    REAL    DEFAULT (strftime('%s', 'now')),"
        "  published     INTEGER DEFAULT 0"
        ")"
    )

    def __init__(self, db_path: str) -> None:
        """Open (or create) the SQLite database and ensure the schema."""
        self._db_path = db_path
        # check_same_thread=False is safe here because we create a fresh
        # connection per method call and guard writes with an internal lock.
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(self.SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(self, event) -> bool:
        """Insert an event into the outbox.

        Returns:
            True  — event was inserted (new).
            False — event already existed (duplicate event_id).
        """
        event_id = _event_id(event)
        event_type = _event_type(event)
        payload = _payload_json(event)

        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO outbox (event_id, event_type, payload_json) "
                    "VALUES (?, ?, ?)",
                    (event_id, event_type, payload),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                # UNIQUE constraint on event_id — already exists.
                self._conn.rollback()
                return False

    def get_unpublished(self) -> List[Dict]:
        """Return all rows where published=0.

        Each row is returned as a dict with keys:
            id, event_id, event_type, payload_json, created_at
        """
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id, event_id, event_type, payload_json, created_at "
                "FROM outbox WHERE published = 0 "
                "ORDER BY id ASC"
            )
            columns = ["id", "event_id", "event_type", "payload_json", "created_at"]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def mark_published(self, event_ids: List[str]) -> None:
        """Set published=1 for every event_id in the given list."""
        if not event_ids:
            return
        with self._lock:
            placeholders = ",".join("?" for _ in event_ids)
            self._conn.execute(
                f"UPDATE outbox SET published = 1 "
                f"WHERE event_id IN ({placeholders})",
                event_ids,
            )
            self._conn.commit()

    def replay_from(self, chronicle) -> None:
        """Replay all events from *chronicle* into the outbox.

        Calls ``chronicle.replay()`` to get the full event list, then calls
        ``publish()`` for each event.  Duplicates are silently ignored
        (publish returns False).
        """
        for event in chronicle.replay():
            self.publish(event)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
