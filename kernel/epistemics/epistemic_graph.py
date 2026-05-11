"""
EpistemicGraph — Directed graph of beliefs with contradiction detection.

Supports:
- Adding nodes with strata and decay-aware weighting
- Searching by stratum, with current effective weights
- Detecting contradictions (mutual negation between nodes)
- Tracking support and contradiction edges
"""
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from kernel.epistemics.belief_node import BeliefNode
from kernel.memory.strata import MemoryStratum


class EpistemicGraph:
    """Graph of BeliefNodes with contradiction detection."""

    def __init__(self):
        self.nodes: Dict[str, BeliefNode] = {}
        self._contradictions: Set[Tuple[str, str]] = set()

    def add_node(self, node: BeliefNode) -> str:
        """Add a belief node. Returns node_id."""
        self.nodes[node.node_id] = node
        return node.node_id

    def search(
        self,
        stratum: Optional[MemoryStratum] = None,
        min_weight: float = 0.0,
        limit: int = 10,
        current_time: Optional[float] = None,
    ) -> List[Tuple[BeliefNode, float]]:
        """Search nodes, optionally filtered by stratum, sorted by effective weight."""
        results = []
        for node in self.nodes.values():
            if stratum is not None and node.stratum != stratum:
                continue
            weight = node.effective_weight(current_time)
            if weight >= min_weight:
                results.append((node, weight))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def find_contradictions(self) -> List[Tuple[BeliefNode, BeliefNode]]:
        """Find all pairs of nodes that contradict each other.

        A contradiction exists when:
        - Node A's claim is the negation of Node B's claim (or vice versa), OR
        - Both nodes have contradict[s] edges pointing to each other
        """
        contradictions = []
        node_ids = list(self.nodes.keys())
        for i, id_a in enumerate(node_ids):
            for id_b in node_ids[i + 1:]:
                node_a = self.nodes[id_a]
                node_b = self.nodes[id_b]
                if self._are_contradictory(node_a, node_b):
                    contradictions.append((node_a, node_b))
        return contradictions

    def _are_contradictory(self, node_a: BeliefNode, node_b: BeliefNode) -> bool:
        """Check if two nodes are contradictory."""
        # Check explicit contradict edges
        if node_b.node_id in node_a.contradicts and node_a.node_id in node_b.contradicts:
            return True
        # Simple negation check (claims are opposites)
        if node_a.claim.lower() != node_b.claim.lower():
            negations = ['not', 'no', 'never', 'false', 'impossible', 'refused']
            a_has_neg = any(node_a.claim.lower().startswith(n) for n in negations)
            b_has_neg = any(node_b.claim.lower().startswith(n) for n in negations)
            if a_has_neg and b_has_neg:
                # Both negate, check if they negate the same thing
                base_a = node_a.claim.lower().split(maxsplit=1)[1] if len(node_a.claim.lower().split()) > 1 else ""
                base_b = node_b.claim.lower().split(maxsplit=1)[1] if len(node_b.claim.lower().split()) > 1 else ""
                if base_a == base_b:
                    return True
        return False

    def add_support(self, node_id: str, supported_by: str) -> bool:
        """Add a support edge from node_id → supported_by."""
        if node_id in self.nodes and supported_by in self.nodes:
            self.nodes[node_id].supports.append(supported_by)
            return True
        return False

    def add_contradiction(self, node_id_a: str, node_id_b: str) -> bool:
        """Add a contradiction edge between two nodes."""
        if node_id_a in self.nodes and node_id_b in self.nodes:
            self.nodes[node_id_a].contradicts.append(node_id_b)
            self.nodes[node_b].contradicts.append(node_id_a)
            self._contradictions.add((node_id_a, node_id_b))
            return True
        return False

    def node_count(self) -> int:
        return len(self.nodes)

    def contradiction_count(self) -> int:
        return len(self._contradictions)

    def get_node(self, node_id: str) -> Optional[BeliefNode]:
        return self.nodes.get(node_id)

    def get_all_nodes(self) -> List[BeliefNode]:
        return list(self.nodes.values())