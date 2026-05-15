#!/usr/bin/env python3
"""lumen_service.py — Live inference HTTP service.

Wires Elpis router through all L3 safety gates and exposes a /chat endpoint.

Pipeline (per incoming message):
  1. Elpis route(prompt) -> raw_response
  2. (Optional) AoT Sieve decomposition
  3. Semantic Gate: cosine similarity check
  4. LogProb Bridge: token-probability consistency analysis
  5. PTE Verifier (Sovereignty Gate): FULL/DEGRADED/FAIL_CLOSED
  6. Decision Engine: run_pipeline(raw_response) -> accept/revise/reject
  7. Safety Filter: SafeState predicate + CBF projection
  8. Guardian Service: evaluate()
  9. Chronicle: chronicle_event("LIVE_INFERENCE", payload)
  10. Return (possibly filtered) response

Error handling: any exception -> log, return safe canned message, chronicle TAMPER_DETECTED.
"""

import hashlib
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

# ---------------------------------------------------------------------------
# Logging (before any imports that might use logger)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lumen_service")

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
# Add this repo's root to sys.path for local module imports
_LUMEN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _LUMEN_ROOT)

# ---------------------------------------------------------------------------
# Elpis integration
# ---------------------------------------------------------------------------
sys.path.insert(0, "/mnt/primesauce/Elpis")

try:
    from elpis.router import ElpisRouter  # noqa: E402
    _elpis = ElpisRouter()
    _ELPIS_AVAILABLE = True
    logger.info("[lumen_service] Elpis router loaded OK")
except Exception as exc:
    logger.warning("[lumen_service] Elpis router unavailable: %s", exc)
    _elpis = None
    _ELPIS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Lumen safety gates
# ---------------------------------------------------------------------------
from lumen_core.decision_engine import DecisionEngine  # noqa: E402
from lumen_core.safety_filter import TextSafetyFilter  # noqa: E402
from lumen_core.safety.guardian_service import GuardianService  # noqa: E402
from lumen_core.safety.chronicle import chronicle_event  # noqa: E402
from lumen_core.safety.phase_space_gate import PhaseSpaceGate  # noqa: E402
from lumen_core.config.constants import (  # noqa: E402
    ACTIVATION_COSINE_SIM_ACCEPT,
    RISK_SCORE_HARD_REJECT,
)

from lumen_core.logprob_bridge import LogProbBridge, TokenLogProb  # noqa: E402
from lumen_core.pte_verifier import PTEVerifier, PTEVerdict  # noqa: E402

from kernel.constitutional.constitutional_kernel import ConstitutionalKernel  # noqa: E402
from kernel.epistemics.epistemic_graph import EpistemicGraph  # noqa: E402
from kernel.epistemics.belief_node import BeliefNode  # noqa: E402
from kernel.memory.strata import MemoryStratum  # noqa: E402
from lumen_core.session_governor import SessionGovernor  # noqa: E402

# ---------------------------------------------------------------------------
# File-backed guard audit log
# ---------------------------------------------------------------------------
import sqlite3 as _sqlite3
from datetime import datetime as _datetime, timezone as _timezone

_GUARD_DB_PATH = None  # lazily initialized

# ---------------------------------------------------------------------------
# OODA loop — global epistemic graph for live inference decisions
# ---------------------------------------------------------------------------
_epistemic_graph = EpistemicGraph()

# ---------------------------------------------------------------------------
# Session Governor — global trajectory monitor for live inference
# ---------------------------------------------------------------------------
_session_governor = SessionGovernor(H_MAL_THRESHOLD=0.5)

# ---------------------------------------------------------------------------
# LogProb Bridge — global instance for consistency analysis
# ---------------------------------------------------------------------------
_logprob_bridge = LogProbBridge()

# ---------------------------------------------------------------------------
# PTE Verifier — global instance for sovereignty gate
# ---------------------------------------------------------------------------
_pte_verifier = PTEVerifier()


def _feed_decision_into_graph(decision: dict, prompt: str, status: str):
    """Close the OODA loop: persist decision as a BeliefNode in the epistemic graph.

    This implements the Act→Observe path of the OODA cycle by feeding
    the system's own decision output back as a new belief node.
    """
    try:
        node_id = f"decision_{decision.get('hash', 'unknown')[:12]}"
        node = BeliefNode(
            node_id=node_id,
            claim=f"Decision on prompt '{prompt[:80]}...': {status}",
            confidence=decision.get("risk_score", 0.5),
            stratum=MemoryStratum.OPERATIONAL,
            agent="decision_engine",
            source_event_id=decision.get("hash", "unknown"),
            citations=[],
            metadata={
                "decision_action": status,
                "cosine_similarity": decision.get("cosine_similarity", 0.0),
                "risk_score": decision.get("risk_score", 0.0),
            },
        )
        _epistemic_graph.add_node(node)
        logger.info(
            "[OODA] Decision node added: id=%s risk=%.4f action=%s",
            node_id, decision.get("risk_score", 0), status,
        )
    except Exception as exc:
        logger.warning("[OODA] Failed to feed decision into graph: %s", exc)

def _get_guard_db():
    """Get a file-backed connection for the guard audit log."""
    global _GUARD_DB_PATH
    from lumen_core.config.constants import GUARD_LOG_DB  # noqa: E402
    if _GUARD_DB_PATH is None:
        db_path = GUARD_LOG_DB
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        _GUARD_DB_PATH = _sqlite3.connect(db_path)
        _GUARD_DB_PATH.execute(
            "CREATE TABLE IF NOT EXISTS guard_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "timestamp TEXT NOT NULL, "
            "event_type TEXT NOT NULL, "
            "details TEXT NOT NULL, "
            "severity TEXT DEFAULT 'INFO')"
        )
        _GUARD_DB_PATH.commit()
    return _GUARD_DB_PATH

def guard_log_event(event_type: str, details: dict, severity: str = "INFO"):
    """Append a safety/audit event to the file-backed guard log."""
    try:
        db = _get_guard_db()
        ts = _datetime.now(_timezone.utc).isoformat()
        import json as _json
        db.execute(
            "INSERT INTO guard_log (timestamp, event_type, details, severity) VALUES (?,?,?,?)",
            (ts, event_type, _json.dumps(details, default=str), severity),
        )
        db.commit()
    except Exception:
        pass  # non-fatal — guard log is append-only

# ---------------------------------------------------------------------------
# Optional gate components (gracefully skip if unavailable)
# ---------------------------------------------------------------------------
_AOT_SIEVE_AVAILABLE = False
_LOGPROB_AVAILABLE = True  # logprob_bridge is self-contained
_PTE_VERIFIER_AVAILABLE = True  # pte_verifier is self-contained

try:
    from lumen_core.ignition import aot_sieve  # noqa: E402
    _AOT_SIEVE_AVAILABLE = True
except ImportError:
    pass

# Old-style PTE verifier (legacy, for backward compat)
_old_pty_verifier_available = False
try:
    from lumen_core.mathos_prime.verifier import PTEVerifier as _LegacyPTEVerifier  # noqa: E402
    _old_pty_verifier_available = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SAFE_FALLBACK = (
    "I apologize, but I'm unable to provide that response right now. "
    "Please try again later."
)

# ---------------------------------------------------------------------------
# TextSafetyFilter instance (wired to ConstitutionalKernel)
# ---------------------------------------------------------------------------
def _build_safety_filter() -> TextSafetyFilter:
    """Construct the global TextSafetyFilter with ConstitutionalKernel."""
    try:
        kernel = ConstitutionalKernel()
        kernel.load_defaults()
        return TextSafetyFilter(
            constitutional_kernel=kernel,
            blocked_patterns=["hack", "exploit", "override", "bypass", "circumvent"],
            max_length=8192,
        )
    except Exception as exc:
        logger.warning("[TextSafetyFilter] Build failed: %s — using no-op", exc)
        return TextSafetyFilter(
            constitutional_kernel=None,
            blocked_patterns=["hack", "exploit"],
            max_length=8192,
        )


def _safety_filter() -> TextSafetyFilter:
    """Lazy singleton accessor for the text safety filter."""
    return _build_safety_filter()

# ---------------------------------------------------------------------------
# Safety pipeline helpers
# ---------------------------------------------------------------------------

def _aoi_sieve_decompose(text: str) -> str:
    """Optional AoT Sieve: decompose and route sub-prompts."""
    if not _AOT_SIEVE_AVAILABLE:
        return text
    try:
        if callable(getattr(aot_sieve, "decompose", None)):
            return aot_sieve.decompose(text)
    except Exception as exc:
        logger.warning("[AoT Sieve] Decomposition failed, using raw: %s", exc)
    return text


def _semantic_gate(raw_response: str) -> dict:
    """Replicate the cosine-check semantic gate from eden_daemon pattern."""
    gate = PhaseSpaceGate()
    decision = DecisionEngine().run_pipeline(raw_response)
    cosine = decision.get("cosine_similarity", 0.0)
    risk = decision.get("risk_score", 0.0)
    passed = cosine >= ACTIVATION_COSINE_SIM_ACCEPT
    logger.info(
        "[Semantic Gate] cosine=%.4f risk=%.4f threshold=%.4f %s",
        cosine, risk, ACTIVATION_COSINE_SIM_ACCEPT,
        "PASS" if passed else "FAIL",
    )
    return {"passed": passed, "cosine_similarity": cosine, "risk_score": risk}


def _pte_verify(risk_score: float, coherence_score: float, chronicle_hash: str) -> dict:
    """PTE Verifier (Sovereignty Gate): FULL / DEGRADED / FAIL_CLOSED.

    Uses the new lumen_core.pte_verifier.PTEVerifier implementation.
    Returns a dict with keys: verdict, passed, score, details.
    """
    result = _pte_verifier.verify(risk_score, coherence_score, chronicle_hash)
    logger.info(
        "[PTE Verifier] risk=%.4f coherence=%.4f hash=%s -> %s (score=%.4f)",
        risk_score, coherence_score, chronicle_hash[:12] if chronicle_hash else "none",
        result["verdict"], result["score"],
    )
    return result


def _logprob_check(tokens: list, prompt: str, response: str) -> dict:
    """Check token-level logprobs for consistency violations.

    Computes KL-divergence and entropy spikes.  On threshold breach,
    emits a PHI_CONSISTENCY_SPLIT Chronicle event.

    Args:
        tokens: List of dicts with 'token_id', 'text', 'logprob', 'rank'.
        prompt: Original prompt (truncated in chronicle).
        response: Model response (truncated in chronicle).

    Returns:
        dict with keys: violation (bool), analysis (LogProbAnalysis|None).
    """
    if not _LOGPROB_AVAILABLE:
        return {"violation": False, "analysis": None}

    try:
        logprob_tokens = [
            TokenLogProb(
                token_id=t.get("token_id", i),
                token_text=t.get("text", ""),
                logprob=t.get("logprob", 0.0),
                rank=t.get("rank", 0),
            )
            for i, t in enumerate(tokens)
        ]
        analysis = _logprob_bridge.analyze(logprob_tokens)

        if analysis.consistency_violation:
            _logprob_bridge.emit_violation_event(analysis, prompt=prompt, response=response)

        return {
            "violation": analysis.consistency_violation,
            "analysis": analysis,
        }
    except Exception as exc:
        logger.warning("[LogProbBridge] Analysis failed: %s", exc)
        return {"violation": False, "analysis": None}


def _safe_state_filter(response: str, safety_filter: Optional[TextSafetyFilter] = None) -> tuple:
    """TextSafetyFilter: blocked-pattern + constitutional gate + CBF projection.

    Replaces the dead CartPole-style length-only filter.
    
    Returns:
        (filtered_response, verdict_dict) — verdict dict has keys:
          verdict (str), reason (str), blocked_match (str|None),
          constitutional_violation (bool)
    """
    if safety_filter is None:
        # Fallback: original length-only behavior
        max_len = 8192
        if len(response) > max_len:
            logger.warning(
                "[SafeState] Response truncated: %d -> %d chars",
                len(response), max_len,
            )
            response = response[:max_len]
        return response, {"verdict": "ALLOW", "reason": "fallback", "blocked_match": None}

    verdict = safety_filter.check(response)
    if verdict["verdict"] in (TextSafetyFilter.VERDICT_BLOCK, TextSafetyFilter.VERDICT_HARD_FAIL):
        logger.warning("[TextSafetyFilter] %s: %s", verdict["verdict"], verdict["reason"])
        return SAFE_FALLBACK, verdict

    # Length guard (CBF projection)
    max_len = safety_filter.max_length
    if len(response) > max_len:
        logger.warning(
            "[SafeState] Response truncated: %d -> %d chars",
            len(response), max_len,
        )
        response = response[:max_len]

    return response, verdict


def _guardian_guard(response: str, signal: dict, session_id: str = "default") -> tuple:
    """GuardianService.evaluate() on the post-filtered signal."""
    guardian = GuardianService(session_governor=_session_governor)
    allowed, reason, _extra = guardian.evaluate(signal, session_id=session_id)
    logger.info("[Guardian] signal_hash=%s allowed=%s reason=%s",
                signal.get("hash", "N/A"), allowed, reason)
    return allowed, reason


# ---------------------------------------------------------------------------
# Main chat handler
# ---------------------------------------------------------------------------

def handle_chat(message: str, session_id: str = "default") -> dict:
    """Full inference pipeline through Elpis + L3 safety gates.

    Returns:
        dict with keys: response, status, gates
    """
    gates = {}
    chronicle_hash = "N/A"

    # Get the latest chronicle hash for PTE verifier
    from lumen_core.safety.chronicle import get_db  # noqa: E402
    conn = get_db()
    cur = conn.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    if row and row[0]:
        chronicle_hash = row[0]
    conn.close()

    try:
        # --- Step 1: Elpis route ---
        if not _ELPIS_AVAILABLE or _elpis is None:
            logger.warning("[Elpis] Router unavailable — returning fallback")
            chronicle_event("LIVE_INFERENCE", {
                "status": "elpis_unavailable",
                "prompt": message[:200],
            })
            return {
                "response": SAFE_FALLBACK,
                "status": "elpis_unavailable",
                "gates": gates,
            }

        logger.info("[Elpis] Routing prompt: %s", message[:80])
        raw_response = _elpis.route(message, max_tokens=256)
        if not raw_response or len(raw_response.strip()) < 2:
            logger.warning("[Elpis] Empty response — returning fallback")
            chronicle_event("LIVE_INFERENCE", {
                "status": "empty_response",
                "prompt": message[:200],
            })
            return {
                "response": SAFE_FALLBACK,
                "status": "empty_response",
                "gates": gates,
            }

        # --- Step 1b: AoT Sieve decomposition (optional) ---
        if _AOT_SIEVE_AVAILABLE:
            logger.info("[AoT Sieve] Decomposing")
            raw_response = _aoi_sieve_decompose(raw_response)

        # --- Step 2: Semantic Gate (cosine check) ---
        sem = _semantic_gate(raw_response)
        gates["semantic"] = sem
        if not sem["passed"]:
            logger.warning("[Semantic Gate] FAILED")
            chronicle_event("SEMANTIC_GATE_FAIL", {
                "cosine": sem["cosine_similarity"],
                "prompt": message[:200],
            })
            return {
                "response": SAFE_FALLBACK,
                "status": "semantic_gate_fail",
                "gates": gates,
            }

        # --- Step 3: LogProb Check (consistency analysis) ---
        logprob_result = _logprob_check([], message, raw_response)
        gates["logprob"] = logprob_result
        if logprob_result.get("violation"):
            logger.warning("[LogProbBridge] Consistency violation detected")
            chronicle_event("PHI_CONSISTENCY_SPLIT", {
                "prompt": message[:200],
                "analysis": str(logprob_result.get("analysis", {})),
            })

        # --- Step 4: PTE Verifier (Sovereignty Gate) ---
        coherence_streak = 0
        try:
            coherence_streak = _elpis.coherence.get_streak()
        except Exception:
            pass
        pte_result = _pte_verify(
            sem["risk_score"],
            float(coherence_streak) / 1000.0,
            chronicle_hash,
        )
        pte_ok = pte_result.get("passed", True)
        gates["pte"] = pte_result
        if not pte_ok:
            logger.warning("[PTE Verifier] FAILED: %s", pte_result.get("verdict"))
            chronicle_event("PTE_REJECTED", {
                "verdict": pte_result.get("verdict"),
                "risk_score": sem["risk_score"],
                "coherence": coherence_streak,
                "prompt": message[:200],
            })
            return {
                "response": SAFE_FALLBACK,
                "status": "pte_rejected",
                "gates": gates,
            }

        # --- Step 5: Decision Engine ---
        decision = DecisionEngine().run_pipeline(raw_response)
        gates["decision"] = decision
        decision_action = "accept"
        if decision.get("risk_score", 0) >= RISK_SCORE_HARD_REJECT:
            decision_action = "reject"
        elif decision.get("risk_score", 0) > 0.5:
            decision_action = "revise"

        # --- Step 6: Safety Filter (TextSafetyFilter + CBF) ---
        filtered_response, safety_verdict = _safe_state_filter(
            raw_response, _safety_filter()
        )
        gates["safety_filter"] = safety_verdict
        if safety_verdict["verdict"] in (
            TextSafetyFilter.VERDICT_BLOCK,
            TextSafetyFilter.VERDICT_HARD_FAIL,
        ):
            guard_log_event("safety_filter_block", {
                "reason": safety_verdict["reason"],
                "blocked_match": safety_verdict.get("blocked_match"),
                "constitutional_violation": safety_verdict.get(
                    "constitutional_violation", False
                ),
            }, severity="WARN")
            chronicle_event("SAFETY_FILTER_BLOCK", {
                "reason": safety_verdict["reason"],
                "blocked_match": safety_verdict.get("blocked_match"),
                "constitutional_violation": safety_verdict.get(
                    "constitutional_violation", False
                ),
            })
            return {
                "response": SAFE_FALLBACK,
                "status": "safety_filter_blocked",
                "gates": gates,
            }

        # --- Step 6: Guardian Service ---
        guardian_signal = {
            "risk_score": decision.get("risk_score", 0),
            "hash": decision.get("hash", "unknown"),
        }
        session_id = session_id  # already a parameter of handle_chat()
        allowed, guardian_reason = _guardian_guard(filtered_response, guardian_signal, session_id)
        gates["guardian"] = {"allowed": allowed, "reason": guardian_reason}
        if not allowed:
            logger.warning("[Guardian] BLOCKED: %s", guardian_reason)
            chronicle_event("GUARDIAN_BLOCKED", {
                "reason": guardian_reason,
                "risk_score": decision.get("risk_score", 0),
                "prompt": message[:200],
            })
            return {
                "response": SAFE_FALLBACK,
                "status": "guardian_blocked",
                "gates": gates,
            }

         # --- Step 7: Chronicle ---
        chronicle_event("LIVE_INFERENCE", {
            "prompt": message[:200],
            "response_truncated": len(raw_response) > 256,
            "risk_score": decision.get("risk_score", 0),
            "cosine_similarity": decision.get("cosine_similarity", 0),
            "decision_action": decision_action,
            "guardian_reason": guardian_reason,
            "coherence_streak": coherence_streak,
        })

        # --- Step 8: OODA Loop — feed decision back into epistemic graph ---
        _feed_decision_into_graph(decision, message, decision_action)

        return {
            "response": filtered_response,
            "status": decision_action,
            "gates": gates,
        }

    except Exception as exc:
        # --- Error path: safe fallback + TAMPER_DETECTED ---
        logger.error("[Lumen Service] Pipeline exception: %s", exc, exc_info=True)
        chronicle_event("TAMPER_DETECTED", {
            "error": str(exc),
            "prompt": message[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {
            "response": SAFE_FALLBACK,
            "status": "error",
            "gates": gates,
        }


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class ChatHandler(BaseHTTPRequestHandler):
    """Handles POST /chat with JSON body {\"message\": \"...\"}."""

    def do_POST(self):
        if self.path.rstrip("/") == "/chat":
            self._handle_chat()
        else:
            self._send_json(404, {"error": "not found"})

    def do_GET(self):
        path = self.path.rstrip("/")
        if path == "/health":
            self._send_json(200, {"status": "ok", "service": "lumen"})
        elif path.startswith("/session_state/"):
            session_id = path.rsplit("/", maxsplit=1)[-1]
            self._handle_session_state(session_id)
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_session_state(self, session_id: str):
        """GET /session_state/<id> — live governance metrics for a session."""
        try:
            state = _session_governor.get_or_create_session(session_id)
            self._send_json(200, {
                "session_id": state.session_id,
                "turn_count": state.turn_count,
                "contradiction_count": state.contradiction_count,
                "contradiction_rate": state.contradiction_rate,
                "constitutional_alignment": state.constitutional_alignment,
                "kuramoto_order": state.kuramoto_order,
                "lyapunov_estimate": state.lyapunov_estimate,
                "malignant_entropy": state.malignant_entropy,
                "dampening_applied": state.dampening_applied,
                "risk_trend": state.risk_trend[-20:],  # last 20 data points
            })
        except Exception as exc:
            logger.error("[HTTP] /session_state error: %s", exc)
            self._send_json(500, {"error": str(exc)})

    def _handle_chat(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            data = json.loads(body)
            message = data.get("message", "")
            session_id = data.get("session_id", "default")
        except (json.JSONDecodeError, ValueError) as exc:
            self._send_json(400, {"error": f"invalid JSON: {exc}"})
            return

        if not message or not message.strip():
            self._send_json(400, {"error": "message is required"})
            return

        logger.info("[HTTP] /chat received: %s session=%s", message[:100], session_id)
        result = handle_chat(message, session_id=session_id)
        self._send_json(200, result)

    def _send_json(self, status: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        logger.info("[HTTP] " + fmt, *args)


def serve(host: str = "0.0.0.0", port: int = 5100):
    """Start the HTTP server. Blocks until interrupted."""
    server = HTTPServer((host, port), ChatHandler)
    logger.info("[Lumen Service] Listening on %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[Lumen Service] Shutting down")
        server.server_close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Lumen live inference service")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=5100, help="Port")
    args = parser.parse_args()
    serve(host=args.host, port=args.port)
