#!/usr/bin/env python3
"""
lumen_persistence.py — Persistence Upgrade for Phase 2

SQLite backend for cycles, decisions, signals, branches.
Index by: signal vector, cycle hash, decision outcome.
Migration from JSONL → SQLite with dual-write safety.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from lumen_cycles import PrimeCycle, _utc_iso


def cycle_hash(cycle) -> str:
    """SHA256 hash of cycle nodes for indexing."""
    nodes_str = "|".join(sorted(cycle.nodes))
    return hashlib.sha256(nodes_str.encode()).hexdigest()[:16]


def signal_vector_hash(signal: Dict[str, float]) -> str:
    """Deterministic hash of signal vector."""
    sorted_items = sorted(signal.items(), key=lambda x: x[0])
    items_str = "&".join(f"{k}={v:.6f}" for k, v in sorted_items)
    return hashlib.sha256(items_str.encode()).hexdigest()[:16]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_iso() -> str:
    return _utc_iso()


class LumenPersistence:
    """
    SQLite-backed persistence for the Lumen system.

    Tables:
    - cycles: stored cycles with metadata
    - decisions: decision records with signal
    - branches: branch records from branching engine
    - feedback: feedback records for cycle management
    - weight_history: weight evolution over time
    """

    CREATE_STATEMENTS = """
    CREATE TABLE IF NOT EXISTS cycles (
        id TEXT PRIMARY KEY,
        nodes_json TEXT NOT NULL,
        edges_json TEXT NOT NULL,
        stability_score REAL NOT NULL,
        activation_energy REAL NOT NULL,
        cycle_type INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        last_activated TEXT,
        activation_count INTEGER DEFAULT 0,
        utility_score REAL DEFAULT 0.0,
        metadata_json TEXT DEFAULT '{}',
        cycle_hash TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_cycles_stability
        ON cycles(stability_score DESC);

    CREATE INDEX IF NOT EXISTS idx_cycles_type
        ON cycles(cycle_type);

    CREATE INDEX IF NOT EXISTS idx_cycles_hash
        ON cycles(cycle_hash);

    CREATE TABLE IF NOT EXISTS decisions (
        tick_id TEXT PRIMARY KEY,
        input_text TEXT NOT NULL,
        outputs_json TEXT NOT NULL,
        signal_json TEXT NOT NULL,
        signal_hash TEXT NOT NULL,
        action TEXT NOT NULL,
        score REAL NOT NULL,
        reason TEXT,
        timestamp TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_decisions_action
        ON decisions(action);

    CREATE INDEX IF NOT EXISTS idx_decisions_score
        ON decisions(score);

    CREATE INDEX IF NOT EXISTS idx_decisions_hash
        ON decisions(signal_hash);

    CREATE TABLE IF NOT EXISTS branches (
        branch_id TEXT PRIMARY KEY,
        parent_id TEXT,
        hypothesis_text TEXT NOT NULL,
        base_score REAL NOT NULL,
        branch_score REAL NOT NULL,
        state TEXT NOT NULL,
        uniqueness_bonus REAL DEFAULT 0.0,
        redundancy_penalty REAL DEFAULT 0.0,
        metadata_json TEXT DEFAULT '{}',
        timestamp TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_branches_state
        ON branches(state);

    CREATE INDEX IF NOT EXISTS idx_branches_score
        ON branches(branch_score DESC);

    CREATE TABLE IF NOT EXISTS feedback (
        feedback_id TEXT PRIMARY KEY,
        cycle_id TEXT NOT NULL,
        action TEXT NOT NULL,
        stability_change REAL NOT NULL,
        timestamp TEXT NOT NULL,
        reason TEXT,
        metadata_json TEXT DEFAULT '{}',
        FOREIGN KEY (cycle_id) REFERENCES cycles(id)
    );

    CREATE INDEX IF NOT EXISTS idx_feedback_cycle
        ON feedback(cycle_id);

    CREATE INDEX IF NOT EXISTS idx_feedback_action
        ON feedback(action);

    CREATE TABLE IF NOT EXISTS weight_history (
        tick_id INTEGER PRIMARY KEY AUTOINCREMENT,
        weight_name TEXT NOT NULL,
        value REAL NOT NULL,
        timestamp TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_weight_name
        ON weight_history(weight_name);

    CREATE INDEX IF NOT EXISTS idx_weight_timestamp
        ON weight_history(timestamp);

    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), "lumen_persistence.db"
            )
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def init_db(self):
        """Initialize the database (create tables if not exists)."""
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(self.CREATE_STATEMENTS)
        self._conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create connection."""
        if self._conn is None:
            self.init_db()
        return self._conn

    def store_cycle(self, cycle: PrimeCycle) -> str:
        """Upsert a cycle into the database."""
        conn = self._get_conn()
        ch = cycle_hash(cycle)
        conn.execute(
            """INSERT OR REPLACE INTO cycles
               (id, nodes_json, edges_json, stability_score,
                activation_energy, cycle_type, created_at, last_activated,
                activation_count, utility_score, metadata_json, cycle_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cycle.id,
                json.dumps(cycle.nodes),
                json.dumps(cycle.edges),
                cycle.stability_score,
                cycle.activation_energy,
                cycle.cycle_type.value if hasattr(cycle.cycle_type, 'value')
                else cycle.cycle_type,
                cycle.created_at,
                cycle.last_activated,
                cycle.activation_count,
                getattr(cycle, 'utility_score', 0.0),
                json.dumps(getattr(cycle, 'metadata', {}) or {}),
                ch,
            ),
        )
        conn.commit()
        return ch

    def store_decision(
        self,
        tick_id: str,
        input_text: str,
        outputs: List[str],
        signal: Dict[str, float],
        action: str,
        score: float,
        reason: str = "",
    ):
        """Store a decision record with signal hash."""
        conn = self._get_conn()
        sh = signal_vector_hash(signal)
        conn.execute(
            """INSERT OR REPLACE INTO decisions
               (tick_id, input_text, outputs_json, signal_json,
                signal_hash, action, score, reason, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tick_id,
                input_text,
                json.dumps(outputs),
                json.dumps(signal),
                sh,
                action,
                score,
                reason,
                _now_iso(),
            ),
        )
        conn.commit()

    def store_branch(self, branch_data: Dict[str, Any]):
        """Store a branch record."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO branches
               (branch_id, parent_id, hypothesis_text, base_score,
                branch_score, state, uniqueness_bonus,
                redundancy_penalty, metadata_json, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                branch_data["branch_id"],
                branch_data.get("parent_id"),
                branch_data["hypothesis_text"],
                branch_data["base_score"],
                branch_data["branch_score"],
                branch_data["state"],
                branch_data.get("uniqueness_bonus", 0.0),
                branch_data.get("redundancy_penalty", 0.0),
                json.dumps(branch_data.get("metadata", {})),
                branch_data.get("timestamp", _now_iso()),
            ),
        )
        conn.commit()

    def store_feedback(
        self,
        cycle_id: str,
        action: str,
        stability_change: float,
        reason: str = "",
        metadata: Dict[str, Any] = None,
    ):
        """Store a feedback record."""
        conn = self._get_conn()
        fb_id = f"fb_{uuid4hex()}"
        conn.execute(
            """INSERT INTO feedback
               (feedback_id, cycle_id, action, stability_change,
                timestamp, reason, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                fb_id,
                cycle_id,
                action,
                stability_change,
                _now_iso(),
                reason,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
        return fb_id

    def store_weight(self, weight_name: str, value: float):
        """Store a weight snapshot."""
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO weight_history
               (weight_name, value, timestamp)
               VALUES (?, ?, ?)""",
            (weight_name, value, _now_iso()),
        )
        conn.commit()

    def load_cycles(
        self, min_stability: float = 0.0, limit: int = 1000
    ) -> List[PrimeCycle]:
        """Load cycles from database."""
        conn = self._get_conn()
        if min_stability > 0:
            rows = conn.execute(
                "SELECT * FROM cycles WHERE stability_score >= ? LIMIT ?",
                (min_stability, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM cycles ORDER BY stability_score DESC LIMIT ?",
                (limit,),
            ).fetchall()

        cycles = []
        for row in rows:
            cycle = PrimeCycle(
                id=row["id"],
                nodes=json.loads(row["nodes_json"]),
                edges=json.loads(row["edges_json"]),
                stability_score=row["stability_score"],
                activation_energy=row["activation_energy"],
                cycle_type=row["cycle_type"],
                created_at=row["created_at"],
                last_activated=row["last_activated"],
                activation_count=row["activation_count"],
            )
            cycle.metadata = json.loads(row["metadata_json"])
            cycles.append(cycle)
        return cycles

    def load_decisions(
        self, limit: int = 1000, action: str = None
    ) -> List[Dict[str, Any]]:
        """Load recent decision records."""
        conn = self._get_conn()
        if action:
            rows = conn.execute(
                "SELECT * FROM decisions WHERE action = ? ORDER BY timestamp DESC LIMIT ?",
                (action, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

        decisions = []
        for row in rows:
            decisions.append({
                "tick_id": row["tick_id"],
                "input_text": row["input_text"],
                "outputs": json.loads(row["outputs_json"]),
                "signal": json.loads(row["signal_json"]),
                "action": row["action"],
                "score": row["score"],
                "reason": row["reason"],
                "timestamp": row["timestamp"],
            })
        return decisions

    def query_by_outcome(self, outcome: str,
                         limit: int = 100) -> List[Dict[str, Any]]:
        """Query decisions by accept/reject/revise outcome."""
        return self.load_decisions(limit=limit, action=outcome)

    def query_by_cycle(self, cycle_id: str,
                       limit: int = 100) -> List[Dict[str, Any]]:
        """Get all feedback for a cycle."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM feedback WHERE cycle_id = ? ORDER BY timestamp DESC LIMIT ?",
            (cycle_id, limit),
        ).fetchall()

        return [
            {
                "feedback_id": row["feedback_id"],
                "cycle_id": row["cycle_id"],
                "action": row["action"],
                "stability_change": row["stability_change"],
                "timestamp": row["timestamp"],
                "reason": row["reason"],
                "metadata": json.loads(row["metadata_json"]),
            }
            for row in rows
        ]

    def get_weight_history(
        self, weight_name: str, limit: int = 100
    ) -> List[Tuple[int, float, str]]:
        """Get weight evolution over time."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT tick_id, value, timestamp FROM weight_history "
            "WHERE weight_name = ? ORDER BY timestamp DESC LIMIT ?",
            (weight_name, limit),
        ).fetchall()
        return [(int(r[0]), float(r[1]), str(r[2])) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Return database statistics."""
        conn = self._get_conn()
        stats = {}

        for table in ["cycles", "decisions", "branches", "feedback", "weight_history"]:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[f"{table}_count"] = row["cnt"]

        # Recent decision breakdown
        row = conn.execute(
            "SELECT action, COUNT(*) as cnt FROM decisions GROUP BY action"
        ).fetchall()
        stats["decision_breakdown"] = {
            r["action"]: r["cnt"] for r in row
        }

        return stats

    def migrate_from_jsonl(
        self, jsonl_path: str, cycle_collection: List[PrimeCycle] = None
    ):
        """
        Migrate existing JSONL data to SQLite.

        Args:
            jsonl_path: path to JSONL file (one JSON per line)
            cycle_collection: optional list of cycles to also migrate
        """
        if not os.path.exists(jsonl_path):
            print(f"Warning: {jsonl_path} not found, skipping JSONL migration.")
            return

        self.init_db()
        conn = self._get_conn()

        with open(jsonl_path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    record_type = data.get("type", "unknown")
                    timestamp = data.get("timestamp", _now_iso())

                    if record_type == "decision" and "tick_id" in data:
                        self.store_decision(
                            tick_id=data["tick_id"],
                            input_text=data.get("input_text", ""),
                            outputs=data.get("outputs", []),
                            signal=data.get("signal", {}),
                            action=data.get("action", "revise"),
                            score=data.get("score", 0.5),
                            reason=data.get("reason", ""),
                        )

                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Warning: line {line_num}: {e}")

        # Migrate cycles
        if cycle_collection:
            for cycle in cycle_collection:
                self.store_cycle(cycle)

        conn.commit()
        print(f"Migrated JSONL data from {jsonl_path}")

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


def uuid4hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]
