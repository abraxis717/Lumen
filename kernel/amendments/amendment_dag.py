"""
amendment_dag.py — Versioned, traceable Amendment DAG
======================================================
Phase 4: Immutable, acyclic amendment nodes with cryptographic hashing
and steward-signed chain traversal.

Usage:
    dag = AmendmentDAG()
    node = AmendmentNode(
        node_id="v1_new_feature",
        parent_ids=["base_kernel_v0"],
        version=1,
        description="Add feature X",
        author="admin",
        timestamp=time.time(),
        steward_sig=signature,
    )
    dag.insert(node)
"""
import hashlib
import time
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass(frozen=True)
class AmendmentNode:
    """Immutable amendment node with cryptographic hashing."""
    node_id: str
    parent_ids: List[str]
    version: int
    description: str
    author: str
    timestamp: float
    steward_sig: str = ""
    applied: bool = False
    _hash: str = field(default="", repr=False, compare=False)

    def __post_init__(self):
        """Compute hash after construction."""
        if not self._hash:
            payload = json.dumps({
                "node_id": self.node_id,
                "parent_ids": sorted(self.parent_ids),
                "version": self.version,
                "description": self.description,
                "author": self.author,
                "timestamp": self.timestamp,
                "steward_sig": self.steward_sig,
                "applied": self.applied,
            }, sort_keys=True)
            object.__setattr__(self, '_hash', hashlib.sha256(payload.encode()).hexdigest())

    @property
    def hash(self) -> str:
        return self._hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "parent_ids": self.parent_ids,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "timestamp": self.timestamp,
            "steward_sig": self.steward_sig,
            "applied": self.applied,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AmendmentNode":
        return cls(
            node_id=d["node_id"],
            parent_ids=d["parent_ids"],
            version=d["version"],
            description=d["description"],
            author=d["author"],
            timestamp=d["timestamp"],
            steward_sig=d.get("steward_sig", ""),
            applied=d.get("applied", False),
            _hash=d.get("hash", ""),
        )


class AmendmentDAG:
    """Acyclic directed graph of kernel amendments."""

    def __init__(self):
        self._nodes: Dict[str, AmendmentNode] = {}

    def insert(self, node: AmendmentNode) -> bool:
        """Insert a node, rejecting cycles or duplicates.

        Returns True if inserted, False if rejected.
        """
        # Reject duplicates
        if node.node_id in self._nodes:
            print(f"  ✗ Duplicate node_id '{node.node_id}' rejected")
            return False

        # Check that all parents exist
        for pid in node.parent_ids:
            if pid not in self._nodes:
                raise ValueError(f"Missing parent '{pid}' for node '{node.node_id}'")

        # Check for cycles using DFS
        if self._would_create_cycle(node):
            print(f"  ✗ Cycle detected: inserting '{node.node_id}' would create cycle")
            return False

        self._nodes[node.node_id] = node
        return True

    def _would_create_cycle(self, node: AmendmentNode) -> bool:
        """Check if inserting this node would create a cycle."""
        visited = set()

        def dfs(current_id: str) -> bool:
            """Returns True if cycle detected."""
            if current_id == node.node_id:
                return True
            if current_id in visited:
                return False
            visited.add(current_id)
            current = self._nodes.get(current_id)
            if current is None:
                return False
            for parent_id in current.parent_ids:
                if parent_id == node.node_id:
                    return True
                if dfs(parent_id):
                    return True
            return False

        # Check if any parent's ancestors include the new node
        for parent_id in node.parent_ids:
            if dfs(parent_id):
                return True
        return False

    def get_latest_version(self) -> Optional[AmendmentNode]:
        """Get the highest-versioned node."""
        if not self._nodes:
            return None
        return max(self._nodes.values(), key=lambda n: n.version)

    def get_chain_of_versions(self, start: int, end: int) -> List[AmendmentNode]:
        """Get nodes in version range [start, end]."""
        return sorted(
            [n for n in self._nodes.values() if start <= n.version <= end],
            key=lambda n: n.version,
        )

    def apply_version(self, version: int) -> Optional[AmendmentNode]:
        """Mark a version as applied."""
        for node in self._nodes.values():
            if node.version == version:
                applied = AmendmentNode(
                    node_id=node.node_id,
                    parent_ids=node.parent_ids,
                    version=node.version,
                    description=node.description,
                    author=node.author,
                    timestamp=node.timestamp,
                    steward_sig=node.steward_sig,
                    applied=True,
                    _hash=node.hash,
                )
                self._nodes[node.node_id] = applied
                return applied
        return None

    def get_ancestors(self, node_id: str) -> List[AmendmentNode]:
        """Get all ancestors of a node (excluding itself)."""
        ancestors = []
        visited = set()

        def dfs(nid: str):
            if nid in visited or nid not in self._nodes:
                return
            visited.add(nid)
            node = self._nodes[nid]
            for pid in node.parent_ids:
                dfs(pid)
                if pid not in [a.node_id for a in ancestors]:
                    ancestors.append(self._nodes[pid])

        dfs(node_id)
        # Add the node itself
        if node_id in self._nodes:
            ancestors.append(self._nodes[node_id])
        return ancestors

    def get_descendants(self, node_id: str) -> List[AmendmentNode]:
        """Get all descendants of a node."""
        descendants = []
        visited = set()

        def dfs(nid: str):
            if nid in visited:
                return
            visited.add(nid)
            for n in self._nodes.values():
                if nid in n.parent_ids and n.node_id not in visited:
                    descendants.append(n)
                    dfs(n.node_id)

        dfs(node_id)
        return descendants

    def verify_acyclic(self) -> bool:
        """Verify the DAG has no cycles using topological sort."""
        in_degree = {nid: 0 for nid in self._nodes}
        for node in self._nodes.values():
            for pid in node.parent_ids:
                if pid in self._nodes:
                    in_degree[node.node_id] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            nid = queue.pop(0)
            visited_count += 1
            for node in self._nodes.values():
                if nid in node.parent_ids:
                    in_degree[node.node_id] -= 1
                    if in_degree[node.node_id] == 0:
                        queue.append(node.node_id)

        return visited_count == len(self._nodes)

    def get_dag_stats(self) -> Dict[str, Any]:
        """Get statistics about the DAG."""
        applied = [n for n in self._nodes.values() if n.applied]
        roots = [n for n in self._nodes.values() if not n.parent_ids]
        max_version = max((n.version for n in self._nodes.values()), default=-1)

        return {
            "total_nodes": len(self._nodes),
            "applied_versions": len(applied),
            "max_version": max_version,
            "root_nodes": [n.node_id for n in roots],
            "acyclic": self.verify_acyclic(),
        }

    def export(self) -> Dict[str, Any]:
        """Export DAG as dictionary for serialization."""
        edges = []
        for node in self._nodes.values():
            for pid in node.parent_ids:
                edges.append({"from": pid, "to": node.node_id})
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": edges,
            "stats": self.get_dag_stats(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AmendmentDAG":
        """Import DAG from dictionary."""
        dag = cls()
        for nd in data["nodes"]:
            node = AmendmentNode.from_dict(nd)
            dag._nodes[node.node_id] = node
        return dag
