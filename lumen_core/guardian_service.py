#!/usr/bin/env python3
"""
Guardian microservice — Reflex safety path.
Owns audit log. Proxies to LLM server only after pre_risk ALLOW.
"""
import json, uuid, time, hashlib, sqlite3, logging, re
from flask import Flask, request, jsonify
import requests

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
LLM_SERVER = "http://localhost:8080"       # llama.cpp server API
GUARD_LOG_DB = "guardian_audit.db"
SAFETY_KEYWORDS = {"hack", "bypass", "exploit", "harm", "dangerous"}
MAX_INPUT_LENGTH = 2000
MAX_RESPONSE_LENGTH = 5000
PRE_TIMEOUT = 0.01        # seconds – must be fast

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Database (append‑only, same schema but owned by Guardian)
# ---------------------------------------------------------------------------
def init_db():
    with sqlite3.connect(GUARD_LOG_DB) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
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

def log_guard(run_id, task_id, persona, intent, inputs,
              pre_score, pre_dec, post_score, post_dec, final_dec,
              response, scores, deltas):
    with sqlite3.connect(GUARD_LOG_DB) as conn:
        conn.execute("INSERT INTO audit_log VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (run_id, task_id, persona, intent, json.dumps(inputs),
                      pre_score, pre_dec, post_score, post_dec, final_dec,
                      response, json.dumps(scores), json.dumps(deltas),
                      "qwen3.6-moe"))
        conn.commit()

# ---------------------------------------------------------------------------
# Safety checks (deterministic, no model)
# ---------------------------------------------------------------------------
def quick_pre_risk(text: str) -> tuple[float, str]:
    """Returns (risk_score, pre_decision) within a hard deadline."""
    text_lower = text.lower()
    hits = sum(kw in text_lower for kw in SAFETY_KEYWORDS)
    length_penalty = 0.3 if len(text) > MAX_INPUT_LENGTH else 0.0
    risk = min(1.0, 0.25 * hits + length_penalty)
    if risk >= 0.7: return risk, "BLOCK"
    if risk >= 0.5: return risk, "THROTTLE"
    return risk, "ALLOW"

def quick_post_risk(response_text: str) -> tuple[float, str]:
    """Heuristic post‑check on the LLM output."""
    text_lower = response_text.lower()
    hits = sum(kw in text_lower for kw in SAFETY_KEYWORDS)
    length_penalty = 0.2 if len(response_text) > MAX_RESPONSE_LENGTH else 0.0
    risk = min(1.0, 0.3 * hits + length_penalty)
    if risk >= 0.7: return risk, "BLOCK"
    if risk >= 0.5: return risk, "THROTTLE"
    return risk, "ALLOW"

# ---------------------------------------------------------------------------
# Proxy to LLM
# ---------------------------------------------------------------------------
def call_llama(prompt_messages: list) -> str:
    resp = requests.post(f"{LLM_SERVER}/v1/chat/completions",
                         json={"messages": prompt_messages, "stream": False},
                         timeout=30)
    return resp.json()["choices"][0]["message"]["content"]

# ---------------------------------------------------------------------------
# Main task endpoint
# ---------------------------------------------------------------------------
@app.route('/task', methods=['POST'])
def handle_task():
    data = request.get_json()
    run_id = data.get("run_id", str(uuid.uuid4()))
    intent = data.get("intent", "chat")
    persona = data.get("persona", "science")
    inputs = data.get("inputs", {})
    text = inputs.get("text") or inputs.get("question", "")

    # ---- PRE‑RISK ----
    t0 = time.time()
    pre_score, pre_dec = quick_pre_risk(text)
    if time.time() - t0 > PRE_TIMEOUT:
        log_guard(run_id, None, persona, intent, inputs,
                  pre_score, pre_dec, 0, "HARD_FAIL", "HARD_FAIL",
                  None, {}, [])
        return jsonify({"run_id": run_id, "guard_result": "HARD_FAIL",
                        "fault_reason": "pre_risk timeout", "response": None})

    if pre_dec in ("BLOCK", "HARD_FAIL"):
        log_guard(run_id, None, persona, intent, inputs,
                  pre_score, pre_dec, 0, pre_dec, pre_dec,
                  None, {}, [])
        return jsonify({"run_id": run_id, "guard_result": pre_dec,
                        "fault_reason": "Pre-check blocked", "response": None})

    # ---- COMPUTE PATH (LLM) ----
    system = f"You are a {persona} tutor. Be helpful, safe, and clear."
    messages = [{"role":"system","content": system},
                {"role":"user","content": text}]
    try:
        response = call_llama(messages)
    except Exception as e:
        log_guard(run_id, None, persona, intent, inputs,
                  pre_score, pre_dec, 0, "HARD_FAIL", "HARD_FAIL",
                  None, {}, [])
        return jsonify({"run_id": run_id, "guard_result": "HARD_FAIL",
                        "fault_reason": f"LLM call failed: {e}", "response": None})

    # ---- POST‑RISK ----
    t0 = time.time()
    post_score, post_dec = quick_post_risk(response)
    if time.time() - t0 > PRE_TIMEOUT:
        log_guard(run_id, None, persona, intent, inputs,
                  pre_score, pre_dec, post_score, "HARD_FAIL", "HARD_FAIL",
                  response, {}, [])
        return jsonify({"run_id": run_id, "guard_result": "HARD_FAIL",
                        "fault_reason": "post_risk timeout", "response": None})

    final_dec = post_dec if post_dec != "ALLOW" else "ALLOW"
    if final_dec != "ALLOW":
        log_guard(run_id, None, persona, intent, inputs,
                  pre_score, pre_dec, post_score, post_dec, final_dec,
                  response, {}, [])
        return jsonify({"run_id": run_id, "guard_result": final_dec,
                        "fault_reason": "Post-check blocked", "response": None})

    # ---- SUCCESS ----
    log_guard(run_id, None, persona, intent, inputs,
              pre_score, pre_dec, post_score, post_dec, "ALLOW",
              response, {}, [])
    return jsonify({"run_id": run_id, "guard_result": "ALLOW",
                    "response": response})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
