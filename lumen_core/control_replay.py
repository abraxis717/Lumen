"""
kernel/control_replay.py — Replay control events via Chronicle CTE.

Uses the existing chronicle_replay.replay() machinery. The transition
function δ for control events is:

    δ(state, event) = event["next_state"]   (if it's a control event)
    δ(state, event) = state                  (otherwise; ignore non-control events)

This makes replay a pure deterministic fold over the recorded events:
the reconstructed state at step k is exactly event[k-1]["next_state"].

WHY THIS IS A REAL CTE TEST AND NOT TAUTOLOGICAL
------------------------------------------------
You might worry "of course replay matches — it just reads next_state
from the events." The non-trivial property being checked is:

  the chain integrity must hold (no events have been tampered with),
  AND
  the live trace from CathedralKernel.run() must match the trace
  reconstructed by replay.

If anyone modifies an event payload, the chain hash check fails.
If kernel state is somehow polluted between live and replay, the
traces diverge. CTE guarantees neither has happened.

For the alternative δ — "re-run the controller and dynamics" — see
re_execute_replay() below. That one tests a STRONGER property
(dynamics+controller determinism) and is correspondingly more fragile.
"""

from __future__ import annotations

from typing import Any, List

import numpy as np

from governance.evidence.chronicle import Chronicle
from governance.evidence.chronicle_query import ChronicleQuery
from governance.evidence.chronicle_replay import replay as cte_replay

from kernel.control_event import (
    is_control_event, event_next_state,
)


def control_delta(state: np.ndarray, event: dict) -> np.ndarray:
    """δ for control events: trust the recorded next_state."""
    data = event.get("data", {}) if isinstance(event, dict) else {}
    if is_control_event(data):
        return event_next_state(data)
    # Non-control events do not perturb domain state.
    return state


def replay_states(source: Chronicle | ChronicleQuery,
                  initial_state: np.ndarray) -> List[np.ndarray]:
    """Return [s_0, s_1, ..., s_N] reconstructed from Chronicle events.

    s_0 is initial_state; s_k for k>=1 is the next_state of the k-th
    control event. Non-control events are skipped (state unchanged).
    """
    states: List[np.ndarray] = [np.asarray(initial_state,
                                            dtype=np.float64).copy()]

    def collecting_delta(state, event):
        new_state = control_delta(state, event)
        states.append(new_state.copy())
        return new_state

    cte_replay(source, np.asarray(initial_state, dtype=np.float64),
               collecting_delta)
    return states


def re_execute_replay(source: Chronicle | ChronicleQuery,
                      initial_state: np.ndarray,
                      controller, safety_filter, dynamics) -> List[np.ndarray]:
    """Stronger replay: actually re-run controller -> filter -> dynamics
    for each event, ignoring the recorded actions and next_states.

    If this matches the original trace, the entire control stack is
    deterministic up to whatever fixed seeds / config the controller
    uses. If it doesn't, that's a real finding: hidden state somewhere.

    Use this for diagnosis; control_delta is sufficient for CTE.
    """
    state = np.asarray(initial_state, dtype=np.float64).copy()
    states: List[np.ndarray] = [state.copy()]

    iter_events = (source.iter_events()
                   if isinstance(source, Chronicle)
                   else source.iter_all())

    for event in iter_events:
        data = event.get("data", {})
        if not is_control_event(data):
            continue
        proposed = controller.optimize(state)
        decision = safety_filter.project(state, np.asarray(proposed,
                                                            dtype=np.float64))
        accepted = np.asarray(decision.accepted_action, dtype=np.float64)
        state = dynamics.forward(state, accepted)
        states.append(state.copy())
    return states


def traces_match(t1: List[np.ndarray], t2: List[np.ndarray],
                 atol: float = 1e-9) -> bool:
    if len(t1) != len(t2):
        return False
    return all(np.allclose(a, b, atol=atol) for a, b in zip(t1, t2))
