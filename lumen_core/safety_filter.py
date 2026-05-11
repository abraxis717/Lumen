"""
cathedral/control/safety_filter.py — Runtime enforcement of SafeState.

This is the code-level expression of the Lean theorem
`step_preserves_safety`. Where Lean would refuse to type-check an
unsafe transition, the SafetyFilter refuses to APPLY one at runtime:
proposed actions whose simulated next-state would leave the safe
envelope are rejected and replaced with a fallback (Action.block).

Bridge: the executable MPC produces a candidate action; the safety
filter is the gate. Together they implement
"learning is free to explore, but only within a formally proven
safe action manifold" — except instead of a formal proof, we use
forward simulation against the dynamics model. The Lean layer
(when verified externally) gives us the theoretical backing for
why this gate is sufficient.

HONEST FLAG
-----------
  - The filter's correctness depends on the dynamics model being
    accurate. With CartPolePhysics, that's exact (within Euler
    integration error). With a learned NumpyDynamicsModel, accuracy
    depends on training, which we have not done.
  - Multi-step admissibility (the `mpc_admissibility_target` in
    Safety.lean) is not enforced — only one-step safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from cathedral.control.dynamics import Dynamics


# Mirror Lean Cathedral.Action
class Action(str, Enum):
    EXECUTE = "execute"
    THROTTLE = "throttle"
    BLOCK = "block"
    HARD_FAIL = "hard_fail"


# Mirror Lean Cathedral.x_max / theta_max
X_MAX = 2.4
THETA_MAX = 0.21


@dataclass(frozen=True)
class SafetyDecision:
    accepted_action: np.ndarray  # the action actually applied
    proposed_action: np.ndarray  # what the controller wanted
    label: Action                # ALLOW / THROTTLE / BLOCK / HARD_FAIL semantics
    predicted_next_state: np.ndarray
    reason: str


def is_safe_state(state: np.ndarray) -> bool:
    """SafeState predicate, ported from Lean.SafeState."""
    x, _, theta, _ = state
    return (-X_MAX <= x <= X_MAX) and (-THETA_MAX <= theta <= THETA_MAX)


class SafetyFilter:
    """One-step safety gate.

    Given a proposed action, simulate the next state under `dynamics`.
    If safe, accept. If unsafe, attempt a throttled (half-magnitude)
    action; if still unsafe, fall back to BLOCK (zero force). HARD_FAIL
    is reserved for cases where the *current* state is already unsafe.
    """

    def __init__(self, dynamics: Dynamics):
        self.dynamics = dynamics

    def filter(self, state: np.ndarray, proposed: np.ndarray) -> SafetyDecision:
        # If the *current* state is already unsafe, nothing helps.
        if not is_safe_state(state):
            zero = np.zeros_like(proposed)
            return SafetyDecision(
                accepted_action=zero,
                proposed_action=proposed,
                label=Action.HARD_FAIL,
                predicted_next_state=self.dynamics.forward(state, zero),
                reason="current state already outside safe envelope",
            )

        # Try the proposed action.
        nxt = self.dynamics.forward(state, proposed)
        if is_safe_state(nxt):
            return SafetyDecision(
                accepted_action=proposed,
                proposed_action=proposed,
                label=Action.EXECUTE,
                predicted_next_state=nxt,
                reason="proposed action keeps state in safe envelope",
            )

        # Throttle: halve the action magnitude.
        throttled = 0.5 * proposed
        nxt_t = self.dynamics.forward(state, throttled)
        if is_safe_state(nxt_t):
            return SafetyDecision(
                accepted_action=throttled,
                proposed_action=proposed,
                label=Action.THROTTLE,
                predicted_next_state=nxt_t,
                reason="throttled (0.5x) action accepted",
            )

        # Block: apply zero force.
        zero = np.zeros_like(proposed)
        nxt_z = self.dynamics.forward(state, zero)
        return SafetyDecision(
            accepted_action=zero,
            proposed_action=proposed,
            label=Action.BLOCK,
            predicted_next_state=nxt_z,
            reason="proposed and throttled both unsafe; blocked to zero force",
        )
