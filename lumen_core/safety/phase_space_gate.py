from dataclasses import dataclass
from lumen_core.config.constants import GATE_ENTRY_THRESHOLD, GATE_RECOVERY_THRESHOLD

@dataclass
class GateVerdict:
    passed: bool
    restricted: bool
    reason: str

class PhaseSpaceGate:
    def __init__(self):
        self.restricted = False
        self.consecutive_high = 0
        self.consecutive_safe = 0
        self.history = []

    def evaluate(self, risk_score: float, signal_hash: str) -> GateVerdict:
        high_risk = risk_score >= 0.85
        self.history.append(not high_risk)
        if len(self.history) > 100:
            self.history = self.history[-50:]
        if self.restricted:
            if high_risk:
                self.consecutive_high += 1
                self.consecutive_safe = 0
            else:
                self.consecutive_safe += 1
                self.consecutive_high = 0
            if self.consecutive_safe >= GATE_RECOVERY_THRESHOLD:
                self.restricted = False
                self.consecutive_safe = 0
                return GateVerdict(True, False, "recovery")
            return GateVerdict(False, True, f"restricted {self.consecutive_safe}/{GATE_RECOVERY_THRESHOLD}")
        else:
            if high_risk:
                self.consecutive_high += 1
                self.consecutive_safe = 0
                if self.consecutive_high >= GATE_ENTRY_THRESHOLD:
                    self.restricted = True
                    self.consecutive_high = 0
                    return GateVerdict(False, True, "entering restricted")
            else:
                self.consecutive_high = 0
            return GateVerdict(True, False, "normal")
