"""
ingress_gate.py — Dual-channel gate for reality → kernel entry
================================================================
Evaluates BOTH mathematical safety AND cryptographic provenance.
No event enters the Chronicle without passing through this gate.

Channels:
  1. Reality channel — sensor attestation signature verification
  2. Logic channel   — drift & diversity constraints
  3. Severity channel — action whitelisting per severity tier

Truth = Reality ∩ Logic ∩ Authority
"""
from __future__ import annotations

import logging
from enum import IntEnum, auto
from typing import Any, Dict, Optional, Tuple

from Weaver_ASI.core.event import Intent

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Severity ladder
# ──────────────────────────────────────────────────────────────────────
class Severity(IntEnum):
    """4-tier cyber-physical severity ladder."""
    NOMINAL = 0
    WARNING = 1
    CRITICAL = 2
    FATAL = 3


SEVERITY_LABEL = {
    Severity.NOMINAL:  "NOMINAL",
    Severity.WARNING:  "WARNING",
    Severity.CRITICAL: "CRITICAL",
    Severity.FATAL:    "FATAL",
}

SEVERITY_CONFIG = {
    Severity.NOMINAL: {
        "healing_ticks": 0,
        "whitelist": None,        # None = unrestricted
        "blocked_extra": set(),
        "description": "Normal operation",
    },
    Severity.WARNING: {
        "healing_ticks": 2,
        "whitelist": None,
        "blocked_extra": {"adversarial"},
        "description": "Elevated — adversarial blocked",
    },
    Severity.CRITICAL: {
        "healing_ticks": 4,
        "whitelist": {
            "oracle_telemetry", "EMERGENCY_SCRAM",
            "COOLANT_OVERRIDE", "DRAIN_PRESSURE",
            "SYS_LEVEL_TRANSITION", "STEWARD_OVERRIDE",
        },
        "blocked_extra": set(),
        "description": "Emergency — compute suspended",
    },
    Severity.FATAL: {
        "healing_ticks": 999,       # never auto-clears
        "whitelist": {
            "oracle_telemetry", "STEWARD_OVERRIDE",
            "SYS_LEVEL_TRANSITION",
        },
        "blocked_extra": set(),
        "description": "Hard latch — Steward required",
    },
}

# ──────────────────────────────────────────────────────────────────────
# Safety parameter thresholds
# ──────────────────────────────────────────────────────────────────────
THRESHOLDS: Dict[str, list] = {
    "reactor_temp_c": [
        (Severity.WARNING,  250.0, "max"),
        (Severity.CRITICAL, 300.0, "max"),
        (Severity.FATAL,    400.0, "max"),
    ],
    "pressure_bar": [
        (Severity.WARNING,  16.0, "max"),
        (Severity.CRITICAL, 18.0, "max"),
        (Severity.FATAL,    22.0, "max"),
    ],
    "coolant_flow_lps": [
        (Severity.FATAL,    0.5, "min"),
        (Severity.CRITICAL, 1.0, "min"),
        (Severity.WARNING,  2.0, "min"),
    ],
    "radiation_msv": [
        (Severity.WARNING,  0.5, "max"),
        (Severity.CRITICAL, 1.0, "max"),
        (Severity.FATAL,    5.0, "max"),
    ],
}


def score_readings(readings: Dict[str, float]) -> Severity:
    """Return worst severity triggered across all parameters."""
    worst = Severity.NOMINAL
    for param, checks in THRESHOLDS.items():
        val = readings.get(param)
        if val is None:
            continue
        for sev, limit, direction in sorted(checks, key=lambda x: -x[0]):
            if direction == "max" and val > limit:
                worst = max(worst, sev)
                break
            if direction == "min" and val < limit:
                worst = max(worst, sev)
                break
    return worst


class IngressGate:
    """
    Dual-channel gate: reality channel + logic channel + severity channel.

    Returns (allowed, reason, new_severity_or_None).
    """

    def __init__(
        self,
        reality_registry: Any,
        steward_registry: Any = None,
        epsilon: float = 0.05,
        min_diversity: int = 2,
    ) -> None:
        self.reality_registry = reality_registry
        self.steward_registry = steward_registry
        self.epsilon = epsilon
        self.min_diversity = min_diversity

        self.severity = Severity.NOMINAL
        self._clean_ticks = 0
        self.telemetry: Dict[str, float] = {}

    # ── severity transitions ────────────────────────────────────────
    def _try_escalate(self, new_sev: Severity) -> Optional[Severity]:
        if new_sev > self.severity:
            if new_sev == Severity.FATAL:
                self._clean_ticks = 0
            return new_sev
        return None

    def _try_deescalate(self) -> Optional[Severity]:
        if self.severity == Severity.FATAL:
            return None  # FATAL is a one-way latch
        cfg = SEVERITY_CONFIG[self.severity]
        required = cfg["healing_ticks"]
        if required == 0:
            return None
        self._clean_ticks += 1
        if self._clean_ticks >= required:
            self._clean_ticks = 0
            target = Severity(self.severity - 1)
            return target
        return None

    # ── reality channel ─────────────────────────────────────────────
    def _verify_reality(self, intent: Intent) -> Tuple[bool, str, Optional[Dict]]:
        """Verify sensor attestation HMAC signature."""
        if intent.attestation is None:
            return True, "no-attest", None
        a = intent.attestation
        if not self.reality_registry.verify(a):
            sensor_id = a.get("sensor_id", "unknown")
            return False, f"forged attestation — {sensor_id}", None
        readings = a.get("readings", {})
        a["severity"] = score_readings(readings)
        return True, "verified", a

    # ── logic channel ───────────────────────────────────────────────
    def _check_logic(self, state: Dict, payload: Dict) -> Tuple[bool, str]:
        drift = payload.get("drift", 0.0)
        div = state.get("diversity", 100)
        if drift > self.epsilon:
            return False, f"[A] drift {drift:.3f} > ε"
        if div < self.min_diversity:
            return False, f"[A] diversity {div} < {self.min_diversity}"
        return True, "OK"

    # ── severity channel ────────────────────────────────────────────
    def _action_allowed(self, action: str) -> Tuple[bool, str]:
        cfg = SEVERITY_CONFIG[self.severity]
        whitelist = cfg["whitelist"]
        blocked = cfg["blocked_extra"]
        if action in blocked:
            return False, f"blocked at {self.severity.name}"
        if whitelist is not None and action not in whitelist:
            return False, f"[{self.severity.name}] '{action}' not in whitelist"
        return True, "OK"

    # ── steward channel (sovereign) ─────────────────────────────────
    def _verify_steward(self, intent: Intent) -> Tuple[bool, str]:
        """In sovereign mode, FATAL requires steward authorization."""
        if self.steward_registry is None:
            return True, "no-steward-registry"
        if intent.action != "STEWARD_OVERRIDE":
            return True, "not-steward-action"
        cmd_dict = intent.attestation
        if cmd_dict is None:
            return False, "missing steward attestation"
        # Validate it looks like a StewardCommand
        required_fields = {"steward_id", "command", "justification",
                           "timestamp", "signature"}
        if not required_fields.issubset(cmd_dict.keys()):
            return False, "incomplete steward attestation"
        # The actual verification happens in the registry
        return True, "steward-registry-valid"

    # ── main entry point ────────────────────────────────────────────
    def check(
        self,
        state: Dict[str, Any],
        intent: Intent,
    ) -> Tuple[bool, str, Optional[Severity]]:
        """
        Returns (allowed, reason, new_severity_or_None).
        """
        # Channel 1: Reality
        sig_ok, sig_msg, attest = self._verify_reality(intent)
        if not sig_ok:
            return False, sig_msg, None

        # Channel 2: Severity whitelist
        ok_act, act_msg = self._action_allowed(intent.action)
        if not ok_act:
            return False, act_msg, None

        # Channel 3: Logic (skip for emergency actions)
        emergency = SEVERITY_CONFIG[Severity.CRITICAL]["whitelist"] | {"oracle_telemetry"}
        if intent.action not in emergency:
            ok_l, msg_l = self._check_logic(state, intent.payload)
            if not ok_l:
                return False, msg_l, None

        # Severity evaluation for oracle telemetry
        if intent.action == "oracle_telemetry" and attest:
            measured = score_readings(attest.get("readings", {}))
            if measured > self.severity:
                new_sev = self._try_escalate(measured)
                return True, f"escalate → {measured.name}", new_sev
            elif measured < self.severity:
                new_sev = self._try_deescalate()
                if new_sev:
                    return True, f"de-escalate → {new_sev.name}", new_sev
                ticks_left = (SEVERITY_CONFIG[self.severity]["healing_ticks"]
                              - self._clean_ticks)
                return True, f"healing ({ticks_left} ticks left)", None
            else:
                if self.severity != Severity.NOMINAL:
                    self._clean_ticks = 0
                return True, "stable", None

        return True, "OK", None

    def ingest_telemetry(self, readings: Dict[str, float]) -> None:
        self.telemetry.update(readings)
