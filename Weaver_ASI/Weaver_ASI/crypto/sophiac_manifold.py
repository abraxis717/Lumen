"""
sophiac_manifold.py — The Hestia Protocol / Epistemic Guest Room
=================================================================
When reality contradicts logic and the system cannot resolve it,
the Sophiac Manifold captures the unknown as "Grace" — deferring
judgment rather than panicking or hallucinating a resolution.

This allows the ASI to degrade gracefully into wisdom instead
of crashing into a Consistent Hallucination Trap.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from Weaver_ASI.core.event import Event

logger = logging.getLogger(__name__)


class SophiacManifold:
    """
    Graceful degradation layer.

    When the Guardian cannot evaluate an event (e.g., adversarial
    pressure exhausted diversity), the event is deferred to the
    manifold as "Grace" — acknowledged but not measured.
    """

    def __init__(self) -> None:
        self._deferred: List[Event] = []
        self.grace_count = 0

    def defer(self, event: Event) -> None:
        """Defer an event to the manifold (Grace)."""
        self._deferred.append(event)
        self.grace_count += 1
        logger.info("Sophiac: Grace #%d — deferred %s from %s",
                     self.grace_count, event.action, event.agent)

    def get_deferred(self) -> List[Event]:
        return list(self._deferred)

    def __len__(self) -> int:
        return self.grace_count


class GuardianSlot:
    """
    Evaluates whether an event should proceed or be deferred.

    The Guardian acts as a safety net between the Gate and the
    Chronicle — when diversity drops below a threshold or
    contradictions emerge, it drops the event into the manifold.
    """

    def __init__(self, manifold: SophiacManifold) -> None:
        self.manifold = manifold

    def evaluate(self, state: Dict[str, Any], event: Event) -> str:
        """
        Returns "PROCEED" or "DEFER_TO_MANIFOLD".
        """
        # If adversarial pressure has exhausted diversity
        if event.action == "adversarial" and state.get("diversity", 100) <= 2:
            return "DEFER_TO_MANIFOLD"

        # If the system is in FATAL and the event isn't authorized
        if state.get("severity") == "FATAL" and event.action not in {
            "oracle_telemetry", "STEWARD_OVERRIDE", "SYS_LEVEL_TRANSITION",
        }:
            return "DEFER_TO_MANIFOLD"

        return "PROCEED"

    def defer_event(self, event: Event) -> None:
        self.manifold.defer(event)
