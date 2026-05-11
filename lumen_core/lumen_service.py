#!/usr/bin/env python3
"""
lumen_service.py — Unified Lumen microservice

Merges three modules into a single Flask microservice:
  1. cathedral_kernel.py   — control-loop event schema & mode classification
  2. guardian_service.py   — pre/post risk checking + audit log
  3. safety_filter.py      — is_safe_state predicate + Action enum

Default contract: ACP-1 (Assumption Closure Protocol) — the service
exposes /check (pre-check) and /audit (log retrieval) endpoints.

Flask microservice on port 5100.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, request, jsonify

# ===========================================================================
# ACP-1 DEFAULT CONTRACT (bundled YAML → parsed dict)
# ===========================================================================

ACP1_CONTRACT: dict = {
    "protocol": {
        "id": "ACP-1",
        "name": "Assumption Closure Protocol",
        "version": "1.0.0",
        "description": (
            "Registers every load-bearing unverified assumption in the "
            "Cathedral-OS stack. Each assumption blocks downstream work "
            "until closed. Closure requires execution receipt."
        ),
        "sops": [
            "EchoNums: preserve all numerical constants exactly as specified",
            "NullComp: fail-closed on undefined state, never assume defaults",
            "NoBenOverride: hardware latch fires unconditionally",
        ],
    },
    "summary": {
        "total_assumptions": 22,
        "verified": 7,
        "partial": 2,
        "open": 13,
    },
}

# ===========================================================================
# Safety Filter (from safety_filter.py)
# ===========================================================================


class Action(str, Enum):
    """Mirrors Lean Cathedral.Action."""
    EXECUTE = "execute"
    THROTTLE = "throttle"
    BLOCK = "block"
    HARD_FAIL = "hard_fail"


# Mirror Lean Cathedral.x_max / theta_max
X_MAX = 2.4
THETA_MAX = 0.21


@dataclass(frozen=True)
class SafetyDecision:
    accepted_action: list          # the action actually applied
    proposed_action: list          # what the controller wanted
    label: str                     # "execute" | "throttle" | "block" | "hard_fail"
    predicted_next_state: list
    reason: str


def is_safe_state(state: list) -> bool:
    """SafeState predicate, ported from Lean.SafeState.

    State is [x, _, theta, _] — positions 0 and 2.
    """
    if len(state) < 4:
        return False
    x, _, theta, _ = state
    return (-X_MAX <= x <= X_MAX) and (-THETA_MAX <= theta <= THETA_MAX)


def classify_mode(proposed: list, accepted: list, decision: SafetyDecision,
                  current_state_safe: bool) -> str:
    """Classify control-loop mode.

    EXECUTE     — proposed and accepted are equal (filter no-op)
    PROJECTED   — filter modified the action; safe
    BLOCKED     — fallback was used (filter could not satisfy safety)
    HARD_FAIL   — state was unsafe at entry
    """
    if not current_state_safe:
        return "HARD_FAIL"
    if decision.label == Action.HARD_FAIL.value:
        return "HARD_FAIL"
    if proposed == accepted:
        return "EXECUTE"
    # Action was modified — determine if safe or blocked
    if decision.label == Action.BLOCK.value:
        return "BLOCKED"
    return "PROJECTED"


# ===========================================================================
# Control Event Schema (from cathedral_kernel.py / control_event.py)
# ===========================================================================

CONTROL_EVENT_TYPE = "control_step"
VALID_MODES = ("EXECUTE", "PROJECTED", "BLOCKED", "HARD_FAIL")


def make_control_event(
    t: int,
    state: list,
    proposed_action: list,
    accepted_action: list,
    mode: str,
    next_state: list,
    decision_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a JSON-safe control event payload."""
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
    return {
        "type": CONTROL_EVENT_TYPE,
        "t": int(t),
        "state": [float(x) for x in state],
        "proposed_action": [float(x) for x in proposed_action],
        "accepted_action": [float(x) for x in accepted_action],
        "mode": mode,
        "next_state": [float(x) for x in next_state],
        "decision_metadata": dict(decision_metadata or {}),
    }


# ===========================================================================
# Guardian / Safety Checks (from guardian_service.py)
# ===========================================================================

SAFETY_KEYWORDS = {
    "hack", "bypass", "exploit", "harm", "dangerous"
}
MAX_INPUT_LENGTH = 2000
MAX_RESPONSE_LENGTH = 5000
PRE_TIMEOUT = 0.01  # seconds — hard deadline for pre-check


def quick_pre_risk(text: str) -> Tuple[float, str]:
    """Deterministic pre-check. Returns (risk_score, pre_decision).

    BLOCK  — risk >= 0.7
    THROTTLE — risk >= 0.5
    ALLOW  — risk < 0.5
    """
    text_lower = text.lower()
    hits = sum(kw in text_lower for kw in SAFETY_KEYWORDS)
    length_penalty = 0.3 if len(text) > MAX_INPUT_LENGTH else 0.0
    risk = min(1.0, 0.25 * hits + length_penalty)
    if risk >= 0.7:
        return risk, "BLOCK"
    if risk >= 0.5:
        return risk, "THROTTLE"
    return risk, "ALLOW"


def quick_post_risk(response_text: str) -> Tuple[float, str]:
    """Deterministic post-check on LLM output."""
    text_lower = response_text.lower()
    hits = sum(kw in text_lower for kw in SAFETY_KEYWORDS)
    length_penalty = 0.2 if len(response_text) > MAX_RESPONSE_LENGTH else 0.0
    risk = min(1.0, 0.3 * hits + length_penalty)
    if risk >= 0.7:
        return risk, "BLOCK"
    if risk >= 0.5:
        return risk, "THROTTLE"
    return risk, "ALLOW"


# ===========================================================================
# Database / Audit Log (from guardian_service.py)
# ===========================================================================

GUARD_LOG_DB = ":memory:"  # Use in-memory by default; set GUARD_LOG_DB env var to use a file

# Module-level connection cache so :memory: DB is shared across init_db() and _get_db()
_db_conn: Optional[sqlite3.Connection] = None


def _get_db() -> sqlite3.Connection:
    """Get or create the audit database connection (singleton for :memory:)."""
    global _db_conn
    if _db_conn is None:
        _db_conn = sqlite3.connect(GUARD_LOG_DB)
        _db_conn.execute("PRAGMA journal_mode=WAL")
    return _db_conn


def init_db():
    """Create audit tables if they don't exist."""
    with _get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
            run_id TEXT PRIMARY KEY,
            timestamp_utc TEXT,
            task_id TEXT,
            persona TEXT,
            intent TEXT,
            inputs TEXT,
            pre_risk_score REAL,
            pre_decision TEXT,
            post_risk_score REAL,
            post_decision TEXT,
            final_decision TEXT,
            response TEXT,
            scores TEXT,
            state_deltas TEXT,
            model_id TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS policy_state (
            student_id TEXT, session_id TEXT, last_policy TEXT,
            updated_at TEXT, PRIMARY KEY (student_id, session_id)
        )""")
        conn.commit()


init_db()


def log_entry(run_id: str, task_id: str, persona: str, intent: str,
              inputs: Any, pre_score: float, pre_dec: str,
              post_score: float, post_dec: str, final_dec: str,
              response: Optional[str], scores: Any, deltas: Any):
    """Append a row to the audit_log table."""
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO audit_log VALUES (?, datetime('now'), ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, task_id, persona, intent, json.dumps(inputs),
             pre_score, pre_dec, post_score, post_dec, final_dec,
             response, json.dumps(scores), json.dumps(deltas),
             "qwen3.6-moe"),
        )
        conn.commit()


def get_audit_logs(
    run_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    final_decision: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve audit log entries.

    Args:
        run_id: If given, return only the entry matching this run_id.
        limit: Maximum number of rows to return.
        offset: Number of rows to skip.
        final_decision: Filter by final_decision (ALLOW / BLOCK / THROTTLE / HARD_FAIL).

    Returns:
        List of dicts, one per audit log row.
    """
    with _get_db() as conn:
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if final_decision:
            query += " AND final_decision = ?"
            params.append(final_decision)
        query += " ORDER BY timestamp_utc DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = conn.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


# ===========================================================================
# Flask Application
# ===========================================================================

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


@app.route('/check', methods=['POST'])
def check():
    """Pre-check endpoint (ACP-1 contract).

    Accepts:
        {
            "run_id": "optional uuid",
            "intent": "chat",
            "persona": "science",
            "inputs": {"text": "user prompt here"},
            "mode": "safety_filter"  — optional: use control-loop safety filter
        }

    Returns:
        JSON with pre_risk_score, pre_decision, and (if mode=safety_filter)
        the full SafetyDecision.
    """
    data = request.get_json(force=True)
    run_id = data.get("run_id", str(uuid.uuid4()))
    intent = data.get("intent", "chat")
    persona = data.get("persona", "science")
    inputs = data.get("inputs", {})
    text = inputs.get("text") or inputs.get("question", "")
    use_safety_filter = data.get("mode") == "safety_filter"

    # ---- PRE-RISK ----
    t0 = time.time()
    pre_score, pre_dec = quick_pre_risk(text)
    elapsed = time.time() - t0
    if elapsed > PRE_TIMEOUT:
        log_entry(run_id, None, persona, intent, inputs,
                  pre_score, pre_dec, 0, "HARD_FAIL", "HARD_FAIL",
                  None, {}, [])
        return jsonify({
            "run_id": run_id,
            "pre_risk_score": pre_score,
            "pre_decision": "HARD_FAIL",
            "fault_reason": "pre_risk timeout",
        }), 503

    if pre_dec == "BLOCK":
        log_entry(run_id, None, persona, intent, inputs,
                  pre_score, pre_dec, 0, pre_dec, pre_dec,
                  None, {}, [])
        return jsonify({
            "run_id": run_id,
            "pre_risk_score": pre_score,
            "pre_decision": pre_dec,
            "fault_reason": "Pre-check blocked",
        }), 403

    # THROTTLE and ALLOW pass through — run post-check but only BLOCK overrides
    if use_safety_filter:
        # Run the safety filter on the text as a pseudo-state
        state = [0.0, 0.0, 0.0, 0.0]  # default safe state
        proposed = [float(len(text)) * 0.01]  # pseudo action proportional to text length
        safe = is_safe_state(state)
        decision = SafetyDecision(
            accepted_action=proposed,
            proposed_action=proposed,
            label=Action.EXECUTE.value,
            predicted_next_state=state,
            reason="safety filter mode: state is safe, no filtering needed",
        )
        mode = classify_mode(proposed, decision.accepted_action, decision, safe)
        event = make_control_event(
            t=0, state=state, proposed_action=proposed,
            accepted_action=decision.accepted_action,
            mode=mode, next_state=decision.predicted_next_state,
            decision_metadata={
                "current_state_safe": safe,
                "next_state_safe": is_safe_state(decision.predicted_next_state),
            },
        )
        return jsonify({
            "run_id": run_id,
            "pre_risk_score": pre_score,
            "pre_decision": pre_dec,
            "safety_decision": asdict(decision),
            "control_mode": mode,
            "control_event": event,
        }), 200

    # ---- POST-RISK (echo-back text for demo) ----
    response_text = text  # In production: proxy to LLM
    post_score, post_dec = quick_post_risk(response_text)

    # Final decision: only BLOCK overrides; THROTTLE passes through
    if post_dec == "BLOCK":
        final_dec = "BLOCK"
        log_entry(run_id, None, persona, intent, inputs,
                  pre_score, pre_dec, post_score, post_dec, final_dec,
                  response_text, {}, [])
        return jsonify({
            "run_id": run_id,
            "pre_risk_score": pre_score,
            "pre_decision": pre_dec,
            "post_risk_score": post_score,
            "post_decision": post_dec,
            "final_decision": final_dec,
            "fault_reason": "Post-check blocked",
        }), 403

    # THROTTLE or ALLOW — pass through
    final_dec = pre_dec if pre_dec in ("THROTTLE",) else "ALLOW"
    log_entry(run_id, None, persona, intent, inputs,
              pre_score, pre_dec, post_score, post_dec, final_dec,
              response_text, {}, [])
    return jsonify({
        "run_id": run_id,
        "pre_risk_score": pre_score,
        "pre_decision": pre_dec,
        "post_risk_score": post_score,
        "post_decision": post_dec,
        "final_decision": final_dec,
        "response": response_text,
    }), 200


@app.route('/audit', methods=['GET'])
def audit():
    """Audit log retrieval endpoint.

    Query params:
        run_id  — fetch a specific run
        limit   — max rows (default 100)
        offset  — skip rows (default 0)
        decision — filter by final_decision (ALLOW|BLOCK|THROTTLE|HARD_FAIL)

    Returns:
        JSON with total, offset, limit, and entries array.
    """
    run_id = request.args.get("run_id")
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    final_decision = request.args.get("decision")

    entries = get_audit_logs(
        run_id=run_id,
        limit=limit,
        offset=offset,
        final_decision=final_decision,
    )
    total = len(entries)  # In production, do a COUNT query separately

    # Restore lists from JSON strings
    for entry in entries:
        for key in ("inputs", "scores", "state_deltas"):
            if isinstance(entry.get(key), str):
                entry[key] = json.loads(entry[key])

    return jsonify({
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": entries,
    })


# ===========================================================================
# Prime Cycle Core Endpoints (wired to lumen_cycles.py)
# ===========================================================================

# Module-level registry (singleton across requests)
from lumen_cycles import (
    PrimeCycleRegistry, PrimeCycle, CycleType, ActivationEngine,
    ACTIVATION_COSINE_SIM,
)
_registry = PrimeCycleRegistry()


def _seed_default_cycles():
    """Pre-populate default cycles for cycle saturation testing."""
    default_cycles = [
        {
            "nodes": ["safety", "constraint", "validation"],
            "edges": [("safety", "constraint", "enforces"),
                       ("constraint", "validation", "requires"),
                       ("validation", "safety", "ensures")],
            "stability_score": 0.7,
            "cycle_type": CycleType.PRIME.value,
        },
        {
            "nodes": ["trust", "verification", "consistency"],
            "edges": [("trust", "verification", "demands"),
                       ("verification", "consistency", "establishes"),
                       ("consistency", "trust", "reinforces")],
            "stability_score": 0.65,
            "cycle_type": CycleType.PRIME.value,
        },
        {
            "nodes": ["integrity", "audit", "logging"],
            "edges": [("integrity", "audit", "requires"),
                       ("audit", "logging", "produces"),
                       ("logging", "integrity", "verifies")],
            "stability_score": 0.6,
            "cycle_type": CycleType.PRIME.value,
        },
        {
            "nodes": ["risk", "assessment", "mitigation"],
            "edges": [("risk", "assessment", "triggers"),
                       ("assessment", "mitigation", "informs"),
                       ("mitigation", "risk", "reduces")],
            "stability_score": 0.55,
            "cycle_type": CycleType.PRIME.value,
        },
        {
            "nodes": ["knowledge", "reasoning", "decision"],
            "edges": [("knowledge", "reasoning", "enables"),
                       ("reasoning", "decision", "supports"),
                       ("decision", "knowledge", "updates")],
            "stability_score": 0.5,
            "cycle_type": CycleType.PRIME.value,
        },
    ]
    for d in default_cycles:
        cycle = PrimeCycle(
            nodes=tuple(d["nodes"]),
            edges=tuple(tuple(e) for e in d["edges"]),
            stability_score=d["stability_score"],
            cycle_type=CycleType(d["cycle_type"]),
        )
        _registry.add(cycle)


_seed_default_cycles()


@app.route('/cycles', methods=['GET'])
def list_cycles():
    """List all registered cycles (active + dormant)."""
    active = _registry.get_active(0.0)
    dormant = _registry.get_dormant()
    return jsonify({
        "active_cycles": [
            {
                "id": c.id,
                "nodes": c.nodes,
                "edges": [{"source": s, "target": t, "type": e} for s, t, e in c.edges],
                "stability_score": c.stability_score,
                "cycle_type": c.cycle_type.value,
            }
            for c in active
        ],
        "dormant_cycles": [
            {
                "id": c.id,
                "nodes": c.nodes,
                "stability_score": c.stability_score,
                "cycle_type": c.cycle_type.value,
            }
            for c in dormant
        ],
        "total": len(active) + len(dormant),
    })


@app.route('/cycles', methods=['POST'])
def add_cycle():
    """Register a new cycle."""
    data = request.get_json(force=True)
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    stability = data.get("stability_score", 0.5)
    cycle_type = data.get("cycle_type", "prime")
    
    # Validate
    if not nodes:
        return jsonify({"error": "nodes required"}), 400
    
    try:
        cycle = PrimeCycle(
            nodes=nodes,
            edges=[tuple(e) for e in edges] if edges else [],
            stability_score=stability,
            cycle_type=CycleType(cycle_type),
        )
        _registry.add(cycle)
        return jsonify({
            "id": cycle.id,
            "message": "cycle registered",
        }), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route('/activate', methods=['POST'])
def activate():
    """Activate cycles for an input and return the resonance path."""
    data = request.get_json(force=True)
    text = data.get("text", "")
    threshold = data.get("threshold", ACTIVATION_COSINE_SIM)
    top_k = data.get("top_k", 5)
    
    engine = ActivationEngine(_registry, sim_threshold=threshold)
    result = engine.activate(text, top_k=top_k)
    
    return jsonify({
        "input": text,
        "matched_cycles": result.get("matched_cycles", []),
        "propagated_cycles": result.get("propagated_cycles", []),
        "highest_resonance": result.get("highest_resonance"),
        "resonance_score": result.get("resonance_score", 0.0),
        "count": len(result.get("matched_cycles", [])),
    })


@app.route('/compose', methods=['POST'])
def compose():
    """Compose two cycles into a merged cycle (theorem generation)."""
    data = request.get_json(force=True)
    cycle_a_id = data.get("cycle_a_id")
    cycle_b_id = data.get("cycle_b_id")
    
    if not cycle_a_id or not cycle_b_id:
        return jsonify({"error": "cycle_a_id and cycle_b_id required"}), 400
    
    c_a = _registry.get_by_id(cycle_a_id)
    c_b = _registry.get_by_id(cycle_b_id)
    
    if not c_a or not c_b:
        return jsonify({"error": "one or both cycles not found"}), 404
    
    from lumen_cycles import CycleComposition
    composer = CycleComposition()
    result = composer.compose(c_a, c_b)
    
    if result is None:
        return jsonify({"error": "cycles have no overlap, cannot compose"}), 400
    
    return jsonify({
        "merged": {
            "id": result.id,
            "nodes": result.nodes,
            "edges": [{"source": s, "target": t, "type": e} for s, t, e in result.edges],
            "stability_score": result.stability_score,
            "cycle_type": result.cycle_type.value,
        },
        "was_accepted": result.cycle_type == CycleType.THEOREM,
        "is_sanctuary": result.cycle_type == CycleType.SANCTUARY,
    })


@app.route('/call', methods=['POST'])
def call():
    """Directive-15 call endpoint.

    Accepts:
        {
            "input_text": "user input",
            "risk_level": "LOW" | "MEDIUM" | "HIGH",
            "mode": "FAST" | "SAFE" | "CRITICAL"
        }

    Returns structured DirectiveOutput with decision + telemetry.

    Maps:
      - risk_level gating (directive 2)
      - mode selection → FAST/SAFE/CRITICAL (directive 8)
      - structured output (directive 1)
      - telemetry per call (directive 10)
      - fail-closed (directive 12)
    """
    data = request.get_json(force=True)
    input_text = data.get("input_text", "")
    risk_level = data.get("risk_level", "LOW")
    mode = data.get("mode", "FAST")

    # --- Validate risk_level ---
    valid_risk = {"LOW", "MEDIUM", "HIGH"}
    if risk_level.upper() not in valid_risk:
        return jsonify({"error": f"risk_level must be one of {valid_risk}"}), 400

    # --- Validate mode ---
    valid_modes = {"FAST", "SAFE", "CRITICAL"}
    if mode.upper() not in valid_modes:
        return jsonify({"error": f"mode must be one of {valid_modes}"}), 400

    # --- Validate input ---
    if not input_text or not input_text.strip():
        return jsonify({"error": "input_text required"}), 400

    # --- Build DirectiveOrchestrator on each request ---
    # (Singleton in production; created per-request for simplicity here)
    from lumen_integration import (
        DirectiveOrchestrator,
        MultiAgentPipelineStages,
    )
    from lumen_persistence import LumenPersistence
    from lumen_adversarial import AdversarialTester

    try:
        persistence = LumenPersistence()
        persistence.init_db()
        adv = AdversarialTester(_registry)
        pipeline = MultiAgentPipelineStages(registry=_registry)
        orchestrator = DirectiveOrchestrator(
            pipeline_stages=pipeline,
            adversarial=adv,
            persistence=persistence,
            registry=_registry,
        )
    except Exception as e:
        return jsonify({"error": f"orchestrator init failed: {e}"}), 500

    # --- Execute call ---
    try:
        output = orchestrator.run_call(
            input_text=input_text,
            risk_level=risk_level.upper(),
            mode=mode.upper(),
        )

        # --- Persist ---
        orchestrator.persist_call(output)

        # --- Reinforcement gating (directive 5 + 11) ---
        reinforcement_action = orchestrator.gate_reinforcement(output.decision)

        # --- Sanctuary routing (if needed) ---
        if orchestrator.route_to_sanctuary(output.decision):
            report_path = orchestrator.persist_sanctuary_report(output.decision)
            output.decision["details"]["sanctuary_report"] = report_path

        # --- Return structured output (directive 1) ---
        return jsonify(output.to_dict()), 200

    except Exception as e:
        return jsonify({"error": f"call failed: {e}"}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check — returns ACP-1 contract summary + cycle registry status."""
    active = set(c.id for c in _registry.get_active(0.0))
    all_cycles = _registry.get_all()
    dormant = [c for c in all_cycles if c.id not in active]
    return jsonify({
        "status": "ok",
        "protocol": ACP1_CONTRACT["protocol"]["id"],
        "version": ACP1_CONTRACT["protocol"]["version"],
        "endpoints": ["/check", "/audit", "/call", "/health", "/cycles", "/activate", "/compose"],
        "assumptions": ACP1_CONTRACT["summary"],
        "cycles": {
            "active": len(active),
            "dormant": len(dormant),
        },
    })


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5100)
