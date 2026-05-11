"""
kernel/control_event.py — Control-loop event schema.

Represents one closed-loop step:

    proposed_action  := controller's desired action (e.g. MPC output)
    accepted_action  := what the safety filter actually allowed
    mode             := EXECUTE | PROJECTED | BLOCKED | HARD_FAIL
    next_state       := dynamics.forward(state, accepted_action)

The event is a plain dict (JSON-serializable) for two reasons:
  1. Chronicle requires JSON-serializable payloads.
  2. Replay needs deterministic canonical encoding; dicts with
     stable key sets achieve that without a class hierarchy.

Importantly: this module imports NOTHING from cathedral.control or
governance.evidence. It defines the shape; the kernel (which is
cross-plane by design) translates between the two.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

import numpy as np


CONTROL_EVENT_TYPE = "control_step"


VALID_MODES = ("EXECUTE", "PROJECTED", "BLOCKED", "HARD_FAIL")


def make_control_event(
    t: int,
    state: np.ndarray,
    proposed_action: np.ndarray,
    accepted_action: np.ndarray,
    mode: str,
    next_state: np.ndarray,
    decision_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a JSON-safe event payload."""
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
    return {
        "type": CONTROL_EVENT_TYPE,
        "t": int(t),
        "state": [float(x) for x in np.asarray(state).flatten()],
        "proposed_action": [float(x) for x in
                            np.asarray(proposed_action).flatten()],
        "accepted_action": [float(x) for x in
                            np.asarray(accepted_action).flatten()],
        "mode": mode,
        "next_state": [float(x) for x in np.asarray(next_state).flatten()],
        "decision_metadata": dict(decision_metadata or {}),
    }


def is_control_event(payload: Dict[str, Any]) -> bool:
    return isinstance(payload, dict) and payload.get("type") == CONTROL_EVENT_TYPE


def event_state(payload: Dict[str, Any]) -> np.ndarray:
    return np.asarray(payload["state"], dtype=np.float64)


def event_accepted_action(payload: Dict[str, Any]) -> np.ndarray:
    return np.asarray(payload["accepted_action"], dtype=np.float64)


def event_next_state(payload: Dict[str, Any]) -> np.ndarray:
    return np.asarray(payload["next_state"], dtype=np.float64)


def filter_by_mode(events: Iterable[Dict[str, Any]],
                   mode: str) -> List[Dict[str, Any]]:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}")
    return [e for e in events
            if is_control_event(e) and e.get("mode") == mode]
