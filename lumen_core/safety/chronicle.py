import sqlite3
import hashlib
import json
import os
from datetime import datetime, timezone
from lumen_core.config.constants import CHRONICLE_DB_PATH

os.makedirs(os.path.dirname(CHRONICLE_DB_PATH), exist_ok=True)


def get_db():
    conn = sqlite3.connect(CHRONICLE_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            prev_hash TEXT,
            hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def chronicle_event(event_type: str, payload: dict) -> str:
    conn = get_db()
    cur = conn.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    prev_hash = row[0] if row else "genesis"
    timestamp = datetime.now(timezone.utc).isoformat()
    payload_json = json.dumps(payload, sort_keys=True, default=str)
    hash_input = f"{timestamp}|{event_type}|{payload_json}|{prev_hash}"
    event_hash = hashlib.sha256(hash_input.encode()).hexdigest()
    conn.execute(
        "INSERT INTO events (timestamp, event_type, payload, prev_hash, hash) VALUES (?,?,?,?,?)",
        (timestamp, event_type, payload_json, prev_hash, event_hash),
    )
    conn.commit()
    conn.close()
    return event_hash


def verify_chronicle() -> bool:
    conn = get_db()
    cur = conn.execute(
        "SELECT timestamp, event_type, payload, prev_hash, hash FROM events ORDER BY id"
    )
    prev_h = "genesis"
    for row in cur.fetchall():
        ts, et, pay, p_h, h = row
        if p_h != prev_h:
            return False
        hash_input = f"{ts}|{et}|{pay}|{p_h}"
        calc = hashlib.sha256(hash_input.encode()).hexdigest()
        if calc != h:
            return False
        prev_h = h
    conn.close()
    return True
