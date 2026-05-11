"""
kernel/cathedral_kernel.py — Cross-plane control loop façade.

Ties the control plane (cathedral.control) to the evidence plane
(governance.evidence) through Chronicle. Every closed-loop step
produces one Chronicle event; the chain is the auditable record of
the system's behavior.

CROSS-PLANE BOUNDARY
--------------------
This module is the ONLY module that imports from both planes.
cathedral.control does not know about governance.
governance.evidence does not know about cathedral.control.
The boundary is enforced by the architectural-boundary tests in
test_orchestrator.py and test_prosecutor.py.

CONTROLLER / FILTER PROTOCOL
----------------------------
The kernel does not depend on a specific MPC or filter type. It
expects:

    controller.optimize(state) -> proposed_action: np.ndarray
    safety_filter.project(state, proposed_action) -> decision

where decision has attributes:
    accepted_action: np.ndarray
    used_fallback:   bool   (optional; defaults to False if absent)

This matches CBFQPFilter and MultiStepCBFFilter directly, and can wrap
SafetyFilter via a small adapter (provided below).

MODE ASSIGNMENT
---------------
EXECUTE     proposed and accepted actions are equal (filter no-op)
PROJECTED   filter modified the action; CBF satisfied
BLOCKED     fallback was used (filter could not satisfy CBF)
HARD_FAIL   reserved for future: state was unsafe at entry
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from cathedral.control.dynamics import Dynamics
from cathedral.control.safety_filter import is_safe_state
from governance.evidence.chronicle import Chronicle
from governance.evidence.eden_append import verified_append

from kernel.control_event import (
    CONTROL_EVENT_TYPE, VALID_MODES, make_control_event,
)


def _classify_mode(proposed: np.ndarray, accepted: np.ndarray,
                   decision: Any, current_state_safe: bool) -> str:
    if not current_state_safe:
        return "HARD_FAIL"
    if getattr(decision, "used_fallback", False):
        return "BLOCKED"
    if np.allclose(proposed, accepted, atol=1e-9):
        return "EXECUTE"
    return "PROJECTED"


class CathedralKernel:
    """Closed-loop step with auditable provenance.

    Each call to step() emits exactly one Chronicle event (Trace
    Bijection invariant from the v1 manifest).
    """

    def __init__(self, dynamics: Dynamics, controller, safety_filter,
                 chronicle: Chronicle, *,
                 verified_appends: bool = False):
        self.dynamics = dynamics
        self.controller = controller
        self.safety_filter = safety_filter
        self.chronicle = chronicle
        self._t = 0
        # If True, every append re-verifies the chain. Honest cost:
        # O(n) per step. Default False; enable for high-stakes runs.
        self._verified_appends = verified_appends

    @property
    def t(self) -> int:
        return self._t

    def step(self, state: np.ndarray) -> tuple[np.ndarray, dict]:
        """Run one closed-loop step. Returns (next_state, event_payload).

        Order of operations is fixed:
          1. controller proposes action
          2. safety filter projects
          3. dynamics integrates
          4. event appended to Chronicle
        """
        state = np.asarray(state, dtype=np.float64).copy()
        cur_safe = is_safe_state(state)

        proposed = np.asarray(
            self.controller.optimize(state), dtype=np.float64
        )
        decision = self.safety_filter.project(state, proposed)
        accepted = np.asarray(decision.accepted_action, dtype=np.float64)
        next_state = self.dynamics.forward(state, accepted)

        mode = _classify_mode(proposed, accepted, decision, cur_safe)

        # Decision metadata: small, JSON-safe; no controller internals.
        meta = {
            "current_state_safe": bool(cur_safe),
            "next_state_safe": bool(is_safe_state(next_state)),
            "used_fallback": bool(getattr(decision, "used_fallback", False)),
            "cbf_satisfied": bool(getattr(decision, "cbf_satisfied", True)),
        }

        payload = make_control_event(
            t=self._t,
            state=state,
            proposed_action=proposed,
            accepted_action=accepted,
            mode=mode,
            next_state=next_state,
            decision_metadata=meta,
        )

        if self._verified_appends:
            verified_append(self.chronicle, payload)
        else:
            self.chronicle.append(payload)

        self._t += 1
        return next_state, payload

    def run(self, initial_state: np.ndarray, n_steps: int) -> list[dict]:
        """Convenience: run n_steps from initial_state. Returns the
        list of event payloads emitted."""
        state = np.asarray(initial_state, dtype=np.float64).copy()
        events: list[dict] = []
        for _ in range(n_steps):
            state, payload = self.step(state)
            events.append(payload)
        return events
