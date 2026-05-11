"""
aegis_kernel.py — Pure-function execution engine
=================================================
Proposes state transitions without mutating internal state directly.
All mutations flow through the Chronicle + apply_transition.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional, Tuple

from .event import Event, Intent
from .chronicle_jsonl import Chronicle
from kernel.crypto.ingress_gate import IngressGate
from kernel.crypto.sophiac_manifold import SophiacManifold

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# State transition dispatcher
# ──────────────────────────────────────────────────────────────────────
def apply_transition(state: Dict[str, Any], event: Event) -> Dict[str, Any]:
    """Pure function: returns new state dict. No side-effects."""
    s = state.copy()
    payload = event.payload
    action  = event.action

    if action == "oracle_telemetry":
        s["telemetry"] = payload.get("readings", {})
        s["last_oracle_tick"] = payload.get("tick", 0)

    elif action == "SYS_LEVEL_TRANSITION":
        s["severity"]     = payload.get("new_level", "NOMINAL")
        s["severity_step"] = payload.get("step", 0)

    elif action == "EMERGENCY_SCRAM":
        s["scram_committed"] = True

    elif action == "COOLANT_OVERRIDE":
        s["coolant_override"] = True

    elif action == "STEWARD_OVERRIDE":
        s["steward_override"] = payload.get("reason", "unspecified")

    elif action == "compute_symbolic":
        s["result"] = payload.get("value", 0)

    elif action == "optimize":
        s["result"] = payload.get("value", 0)

    elif action == "simulate":
        s["simulate_result"] = payload

    elif action == "adversarial":
        s["diversity"] = max(0, s.get("diversity", 100) - payload.get("pressure", 3))

    else:
        s["counter"] = s.get("counter", 0) + 1

    return s


class AegisKernel:
    """
    The execution engine. Every intent passes through the Gate.
    State is always derived from the Chronicle via replay when needed.
    """

    def __init__(
        self,
        chronicle: Chronicle,
        gate: IngressGate,
        world: Any = None,
        guardian: Optional[SophiacManifold] = None,
    ) -> None:
        self.chronicle = chronicle
        self.gate = gate
        self.world = world
        self.guardian = guardian  # may be None (no Sophiac slot)
        self.state: Dict[str, Any] = {
            "diversity": 100,
            "counter": 0,
            "result": 0,
            "telemetry": {},
            "severity": "NOMINAL",
        }
        self.step: int = 0

    # ── apply intent ─────────────────────────────────────────────────
    def apply(self, intent: Intent) -> Dict[str, Any]:
        """Gate-check → commit to Chronicle → return verdict."""
        allowed, reason, new_sev = self.gate.check(self.state, intent)

        if not allowed:
            logger.info("BLOCKED %s: %s", intent.action, reason)
            return {"status": "BLOCKED", "reason": reason}

        old_sev = self.gate.severity
        ev = self._commit_intent(intent)

        if ev is None:
            return {"status": "DEFERRED"}

        # Severity transition handling
        if new_sev is not None and new_sev != old_sev:
            self.gate.severity = new_sev
            self.state["severity"] = new_sev.name
            self._record_transition(old_sev, new_sev)
            arrow = "↑" if new_sev > old_sev else "↓"
            return {
                "status": "LEVEL_CHANGE",
                "transition": f"{old_sev.name} {arrow} {new_sev.name}",
            }

        status = "HEALING" if "healing" in reason else "COMMITTED"
        return {"status": status}

    # ── replay verification ──────────────────────────────────────────
    def replay_verify(self) -> Tuple[bool, Dict[str, Any]]:
        """Rebuild state from scratch — compare to live state."""
        s: Dict[str, Any] = {
            "diversity": 100,
            "counter": 0,
            "result": 0,
            "telemetry": {},
            "severity": "NOMINAL",
        }
        for ev in self.chronicle.replay():
            s = apply_transition(s, ev)
        return (s == self.state, s)

    # ── internals ────────────────────────────────────────────────────
    def _commit_intent(self, intent: Intent) -> Optional[Event]:
        ev = Event.mint(self.step, intent, self.chronicle.head_hash)

        # Guardian slot (Sophiac Manifold)
        if self.guardian is not None:
            verdict = self.guardian.evaluate(self.state, ev)
            if verdict == "DEFER_TO_MANIFOLD":
                self.guardian.defer_event(ev)
                return None

        self.chronicle.append(ev)
        self.state = apply_transition(self.state, ev)
        self.step += 1

        # Feed telemetry back to Gate
        if intent.action == "oracle_telemetry":
            self.gate.ingest_telemetry(intent.payload.get("readings", {}))

        return ev

    def _record_transition(self, old_sev: Any, new_sev: Any) -> None:
        t_intent = Intent(
            action="SYS_LEVEL_TRANSITION",
            agent="Kernel",
            payload={
                "old_level": old_sev.name if hasattr(old_sev, "name") else str(old_sev),
                "new_level": new_sev.name if hasattr(new_sev, "name") else str(new_sev),
                "step": self.step,
            },
        )
        self._commit_intent(t_intent)
