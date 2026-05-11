"""
trust_exchange.py — Exchange agent trust scores between federation instances.

When two Weaver instances share trust scores, a weighted average
(0.7 local, 0.3 foreign) prevents any single instance from dominating
the federation-wide trust landscape.  All exchanges are logged via the
Chronicle.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from Weaver_ASI.memory.memory_governor import MemoryGovernor


class TrustExchange:
    """Manage bidirectional trust-score exchange across federation peers."""

    # Weights for the blended trust calculation
    LOCAL_WEIGHT = 0.7
    FOREIGN_WEIGHT = 0.3

    def __init__(
        self,
        memory_governor: Optional["MemoryGovernor"] = None,
        chronicle=None,
        instance_name: str = "local",
    ) -> None:
        """
        Args:
            memory_governor:  MemoryGovernor for reading/writing trust scores.
            chronicle:        Chronicle for immutable audit emission.
            instance_name:    Opaque identifier for this Weaver instance.
        """
        self.memory_governor = memory_governor
        self.chronicle = chronicle
        self.instance_name = instance_name

    # ── Public API ───────────────────────────────────────────────────

    def share_trust_scores(self) -> Dict[str, float]:
        """
        Export the current trust scores from MemoryGovernor.

        Returns:
            Dict mapping agent name → trust score, or empty dict if
            no MemoryGovernor is configured.
        """
        if self.memory_governor is None:
            return {}

        # Try the classmethod first (MemoryGovernor._trust_scores is class-level)
        if hasattr(self.memory_governor, "get_trust_scores"):
            return dict(self.memory_governor.get_trust_scores())

        # Fallback: access class-level registry directly
        from Weaver_ASI.memory.memory_governor import MemoryGovernor
        return dict(MemoryGovernor.get_trust_scores())

    def receive_trust_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        """
        Update local trust scores using a weighted average with foreign scores.

        Formula::

            blended(agent) = LOCAL_WEIGHT * local + FOREIGN_WEIGHT * foreign

        If a foreign agent has no local score, it is seeded with the foreign
        score (no blending needed).  If a local agent has no foreign score,
        it is left unchanged.

        Args:
            scores:  Foreign trust-score dict {agent: score}.

        Returns:
            The blended trust-score dict after the update.
        """
        if not scores:
            return {}

        from Weaver_ASI.memory.memory_governor import MemoryGovernor

        blended: Dict[str, float] = {}
        local_scores = self.share_trust_scores()

        # Union of all agents
        all_agents = set(local_scores.keys()) | set(scores.keys())

        for agent in all_agents:
            local_score = local_scores.get(agent)
            foreign_score = scores.get(agent)

            if local_score is not None and foreign_score is not None:
                # Blend both
                blended_score = (
                    self.LOCAL_WEIGHT * local_score
                    + self.FOREIGN_WEIGHT * foreign_score
                )
            elif foreign_score is not None:
                # No local score — seed with foreign (no blending)
                blended_score = foreign_score
            else:
                # No foreign score — keep local
                blended_score = local_score

            # Clamp to [0.0, 1.0]
            blended_score = max(0.0, min(1.0, blended_score))
            blended[agent] = blended_score

        # Write blended scores back to MemoryGovernor
        for agent, score in blended.items():
            MemoryGovernor.set_trust(agent, score)

        # Log to Chronicle
        if self.chronicle is not None:
            self.chronicle.emit(
                action="federation_trust_exchange",
                payload={
                    "source": scores,
                    "blended": {k: round(v, 4) for k, v in blended.items()},
                    "instance": self.instance_name,
                },
                agent="TrustExchange",
            )

        return blended
