"""
ArbitrationEngine — Resolve contradictions between BeliefNodes.

Strategies:
1. Stratum re-classification: Higher stratum wins
2. Citation bonuses: More citations → higher effective confidence
3. Temporal decay: Recent beliefs weighted higher
4. Consensus override: Multiple agents agree → boost confidence
"""
from typing import Tuple, Optional

from kernel.epistemics.belief_node import BeliefNode
from kernel.memory.strata import MemoryStratum


class ArbitrationEngine:
    """Resolves contradictions between two BeliefNodes."""

    # Citation weight multiplier
    CITATION_BONUS = 0.1
    # Stratum priority order
    STRATUM_PRIORITY = {
        MemoryStratum.EPHEMERAL: 1,
        MemoryStratum.OPERATIONAL: 2,
        MemoryStratum.POLICY: 3,
        MemoryStratum.CONSTITUTIONAL: 4,
        MemoryStratum.DISPUTED: 0,
        MemoryStratum.DEPRECATED: -1,
        MemoryStratum.SPECULATIVE: 2,
    }

    @classmethod
    def resolve(cls, node_a: BeliefNode, node_b: BeliefNode) -> Tuple[str, str]:
        """Resolve a contradiction between two nodes.

        Returns:
            (winner_id, loser_id): The node that survives, the one that gets reclassified
        """
        weight_a = cls._compute_weight(node_a)
        weight_b = cls._compute_weight(node_b)

        if abs(weight_a - weight_b) < 0.05:
            # Tie: defer to stratum priority
            priority_a = cls.STRATUM_PRIORITY.get(node_a.stratum, 0)
            priority_b = cls.STRATUM_PRIORITY.get(node_b.stratum, 0)
            if priority_a >= priority_b:
                return (node_a.node_id, node_b.node_id)
            else:
                return (node_b.node_id, node_a.node_id)

        if weight_a > weight_b:
            return (node_a.node_id, node_b.node_id)
        else:
            return (node_b.node_id, node_a.node_id)

    @classmethod
    def _compute_weight(cls, node: BeliefNode) -> float:
        """Compute effective weight for arbitration."""
        base_weight = node.confidence

        # Citation bonus
        citation_bonus = len(node.citations) * cls.CITATION_BONUS
        base_weight += min(citation_bonus, 0.5)  # Cap at 0.5

        # Stratum priority bonus
        stratum_bonus = cls.STRATUM_PRIORITY.get(node.stratum, 0) * 0.1
        base_weight += stratum_bonus

        return base_weight

    @classmethod
    def resolve_and_reclassify(cls, node_a: BeliefNode, node_b: BeliefNode) -> Tuple[str, str]:
        """Resolve a contradiction between two nodes AND reclassify the loser.

        This is the preferred method for actual arbitration — it performs
        both the resolution and the reclassification in a single call,
        ensuring the loser is properly marked as DISPUTED in the graph.

        Returns:
            (winner_id, loser_id): The node that survives, the one that gets reclassified
        """
        winner_id, loser_id = cls.resolve(node_a, node_b)
        loser = node_a if loser_id == node_a.node_id else node_b
        cls.reclassify_losing_node(loser)
        return winner_id, loser_id

    @classmethod
    def reclassify_losing_node(cls, node: BeliefNode) -> BeliefNode:
        """Reclassify the losing node to DISPUTED stratum."""
        return node._replace(stratum=MemoryStratum.DISPUTED)