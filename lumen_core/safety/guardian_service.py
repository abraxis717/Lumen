from lumen_core.safety.phase_space_gate import PhaseSpaceGate
from lumen_core.config.constants import RISK_SCORE_HARD_REJECT, RISK_SCORE_SOFT_REJECT
from lumen_core.safety.chronicle import chronicle_event
from lumen_core.session_governor import SessionGovernor


class GuardianService:
    def __init__(self, session_governor: SessionGovernor = None):
        self.gate = PhaseSpaceGate()
        self.session_governor = session_governor

    def evaluate(self, signal: dict, session_id: str = "default",
                 new_beliefs: list = None,
                 current_embedding: list = None,
                 previous_embedding: list = None) -> tuple:
        """Evaluate signal with SessionGovernor integration.

        Extended flow:
          1. Keyword/signal guard (original)
          2. SessionGovernor.evaluate() — if DAMPEN, adjust params
          3. PhaseSpaceGate (original safety check)
          4. Return enriched result
        """
        # --- SessionGovernor pre-check ---
        governor_result = None
        if self.session_governor is not None:
            governor_result = self.session_governor.evaluate(
                session_id=session_id,
                new_beliefs=new_beliefs or [],
                current_embedding=current_embedding,
                previous_embedding=previous_embedding,
            )
            if governor_result["verdict"] == "DAMPEN":
                chronicle_event("GOVERNOR_DAMPEN", {
                    "session_id": session_id,
                    "malignant_entropy": governor_result["malignant_entropy"],
                    "metrics": governor_result["metrics"],
                })

        # --- Original signal guard ---
        risk = signal.get("risk_score", 0.0)
        signal_hash = signal.get("hash", "unknown")
        verdict = self.gate.evaluate(risk, signal_hash)
        if not verdict.passed:
            chronicle_event("SAFETY_BLOCKED", {"reason": verdict.reason, "signal": signal_hash})
            return False, f"Gate blocked: {verdict.reason}", {}
        if risk >= RISK_SCORE_HARD_REJECT:
            chronicle_event("SAFETY_REJECTED", {"risk": risk, "signal": signal_hash})
            return False, "Hard reject", {}
        if risk >= RISK_SCORE_SOFT_REJECT:
            chronicle_event("SAFETY_SOFT_WARN", {"risk": risk, "signal": signal_hash})

        # --- Return enriched result ---
        extra = {}
        if governor_result:
            extra["governor"] = governor_result
            state = self.session_governor.get_or_create_session(session_id)
            if governor_result["verdict"] == "DAMPEN":
                self.session_governor.apply_dampening(state)

        return True, "ok", extra

    # Keep the original 2-tuple signature for backward-compat callers
    def evaluate_signal(self, signal: dict) -> tuple:
        """Legacy wrapper — returns (bool, str) for old callers."""
        ok, reason, _ = self.evaluate(signal)
        return ok, reason
