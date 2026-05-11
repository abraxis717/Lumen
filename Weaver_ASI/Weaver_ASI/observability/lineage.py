"""
LineageTracker — Build ancestry trees from the epistemic graph.

Walks the supports and contradicts edges of a BeliefNode to produce
a nested dict representing the belief's provenance chain.
"""
from typing import Dict, Any, Optional


class LineageTracker:
    """Tracks the ancestry/provenance of beliefs in the epistemic graph."""

    def __init__(self, graph):
        """
        Args:
            graph: An EpistemicGraph instance
        """
        self.graph = graph

    def ancestors(self, node_id: str, depth: int = 3) -> Dict[str, Any]:
        """
        Build an ancestry tree for a belief node.

        Args:
            node_id: The ID of the BeliefNode to trace
            depth: Maximum recursion depth

        Returns:
            Nested dict with node content and its supports/contradicts chains
        """
        node = self.graph.nodes.get(node_id)
        if not node or depth <= 0:
            return {"node_id": node_id, "status": "leaf"}

        return {
            "node_id": node_id,
            "content": node.claim[:80] if node.claim else "",
            "stratum": node.stratum.value,
            "confidence": node.confidence,
            "supports": [self.ancestors(s, depth - 1) for s in node.supports],
            "contradicts": [self.ancestors(c, depth - 1) for c in node.contradicts],
        }

    def full_tree(self, root_id: str) -> Dict[str, Any]:
        """
        Get the full ancestry tree for a belief, limited by depth.

        Args:
            root_id: The root BeliefNode ID

        Returns:
            Nested dict representing the full ancestry tree
        """
        return self.ancestors(root_id, depth=5)

    def print_lineage(self, node_id: str, depth: int = 3, indent: int = 0) -> None:
        """
        Print a formatted ancestry tree to stdout.

        Args:
            node_id: The BeliefNode ID
            depth: Maximum display depth
            indent: Current indentation level
        """
        node = self.graph.nodes.get(node_id)
        if not node:
            print("  " * indent + f"Unknown node: {node_id}")
            return

        prefix = "  " * indent
        print(f"{prefix}┌── {node_id} [{node.stratum.value}] conf={node.confidence:.3f}")
        print(f"{prefix}│   '{node.claim[:60]}...'")

        if node.supports:
            print(f"{prefix}│   supports:")
            for s in node.supports:
                self.print_lineage(s, depth - 1, indent + 2)

        if node.contradicts:
            print(f"{prefix}│   contradicts:")
            for c in node.contradicts:
                self.print_lineage(c, depth - 1, indent + 2)