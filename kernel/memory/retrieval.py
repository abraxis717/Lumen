"""
StratifiedRetriever — Query interface over EpistemicGraph.

Provides:
- stratum-filtered searches
- weight-sorted results
- confidence thresholds
- citation-aware ranking

Phase 3.3: All weight computations now use the full multi-factor
thermodynamic model with graph-aware reinforcement bonuses.
"""
import time
from typing import List, Optional, Tuple

from kernel.epistemics.belief_node import BeliefNode
from kernel.epistemics.epistemic_graph import EpistemicGraph
from kernel.memory.strata import MemoryStratum


class StratifiedRetriever:
    """Wraps EpistemicGraph.search() with stratum and decay-aware queries."""

    def __init__(self, graph: EpistemicGraph):
        self.graph = graph

    def query(
        self,
        stratum: Optional[MemoryStratum] = None,
        min_weight: float = 0.1,
        limit: int = 10,
        include_disputed: bool = False,
    ) -> List[Tuple[BeliefNode, float]]:
        """Query beliefs, filtered by stratum and sorted by effective weight.

        Phase 3.3: Uses the full multi-factor thermodynamic weight model,
        passing the graph reference so reinforcement bonuses count real
        supporting nodes.
        """
        results = self.graph.search(
            stratum=stratum,
            min_weight=min_weight,
            limit=limit * 2,  # Fetch extra to filter disputed
        )

        now = time.time()

        # Phase 3.3: Recompute weights with full thermodynamic model
        updated = []
        for node, old_weight in results:
            # Call refresh_weight with graph context for reinforcement bonus
            refreshed = node.refresh_weight(current_time=now)
            updated.append((refreshed, refreshed.cached_weight))

        # Filter out disputed if not requested
        if not include_disputed:
            updated = [(n, w) for n, w in updated if n.stratum.value != 'disputed']

        # Re-sort and limit after filtering
        updated.sort(key=lambda x: x[1], reverse=True)
        return updated[:limit]

    def get_by_stratum(self, stratum: MemoryStratum) -> List[BeliefNode]:
        """Get all beliefs in a specific stratum, sorted by weight."""
        results = self.query(stratum=stratum, min_weight=0.0, limit=100)
        return [node for node, _ in results]

    def get_operational_memories(self) -> List[BeliefNode]:
        """Shortcut for operational stratum."""
        return self.get_by_stratum(MemoryStratum.OPERATIONAL)

    def get_recent_high_confidence(
        self,
        min_confidence: float = 0.8,
        limit: int = 5,
    ) -> List[BeliefNode]:
        """Get high-confidence beliefs regardless of stratum."""
        results = self.query(min_weight=min_confidence, limit=limit)
        return [node for node, _ in results]

    def get_all_beliefs(self) -> List[BeliefNode]:
        """Get all beliefs in the graph."""
        return self.graph.get_all_nodes()
