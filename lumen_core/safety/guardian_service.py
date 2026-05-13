from lumen_core.safety.phase_space_gate import PhaseSpaceGate
from lumen_core.config.constants import RISK_SCORE_HARD_REJECT, RISK_SCORE_SOFT_REJECT
from lumen_core.safety.chronicle import chronicle_event

class GuardianService:
    def __init__(self):
        self.gate = PhaseSpaceGate()
    def evaluate(self, signal: dict) -> tuple:
        risk = signal.get("risk_score", 0.0)
        signal_hash = signal.get("hash", "unknown")
        verdict = self.gate.evaluate(risk, signal_hash)
        if not verdict.passed:
            chronicle_event("SAFETY_BLOCKED", {"reason": verdict.reason, "signal": signal_hash})
            return False, f"Gate blocked: {verdict.reason}"
        if risk >= RISK_SCORE_HARD_REJECT:
            chronicle_event("SAFETY_REJECTED", {"risk": risk, "signal": signal_hash})
            return False, "Hard reject"
        if risk >= RISK_SCORE_SOFT_REJECT:
            chronicle_event("SAFETY_SOFT_WARN", {"risk": risk, "signal": signal_hash})
        return True, "ok"
