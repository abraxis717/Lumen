"""
graph_sync.py — Serialize + merge epistemic graphs between instances.

Handles:
  1. ``export()`` — serialise a subset of the graph as a JSON-ready dict.
  2. ``import_from()`` — ingest foreign nodes, logging to the Chronicle.
  3. Deduplication — nodes with existing ``node_id`` are skipped (never
     overwrite).

All federation actions are immutable events in the Chronicle.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kernel.epistemics.belief_node import BeliefNode
from kernel.memory.strata import MemoryStratum


# ── Serialization helpers ──────────────────────────────────────────────

def _serialize_node(node: BeliefNode) -> Dict[str, Any]:
    """Convert a BeliefNode to a JSON-serialisable dict."""
    raw_stratum = node.stratum
    stratum_value = raw_stratum.value if hasattr(raw_stratum, "value") else str(raw_stratum)
    return {
        "node_id": node.node_id,
        "claim": node.claim,
        "confidence": node.confidence,
        "stratum": stratum_value,
        "created_at": node.created_at,
        "supports": list(node.supports),
        "contradicts": list(node.contradicts),
        "source_event_id": node.source_event_id,
        "agent": node.agent,
        "citations": list(node.citations),
        "metadata": dict(node.metadata),
        "cached_weight": node.cached_weight,
    }


def _deserialize_node(data: Dict[str, Any]) -> BeliefNode:
    """Reconstruct a BeliefNode from a serialised dict."""
    # Rehydrate stratum
    stratum_str = data["stratum"]
    try:
        stratum = MemoryStratum(stratum_str)
    except ValueError:
        stratum = MemoryStratum.OPERATIONAL

    return BeliefNode(
        node_id=data["node_id"],
        claim=data["claim"],
        confidence=data["confidence"],
        stratum=stratum,
        created_at=data["created_at"],
        supports=list(data.get("supports", [])),
        contradicts=list(data.get("contradicts", [])),
        source_event_id=data.get("source_event_id"),
        agent=data.get("agent"),
        citations=list(data.get("citations", [])),
        metadata=dict(data.get("metadata", {})),
        cached_weight=data.get("cached_weight", -1.0),
    )


# ── GraphSync class ───────────────────────────────────────────────────

class GraphSync:
    """Serialize and merge epistemic graphs between federation instances."""

    def __init__(self, chronicle=None, instance_name: str = "local") -> None:
        """
        Args:
            chronicle:      Chronicle for immutable audit logging.
            instance_name:  Opaque identifier for this Weaver instance.
        """
        self.chronicle = chronicle
        self.instance_name = instance_name

    # ── export ──────────────────────────────────────────────────────

    def export(
        self,
        nodes: Dict[str, BeliefNode],
        strata: Optional[List[str]] = None,
        since: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Serialise a subset of the graph as a JSON-ready dict.

        Args:
            nodes:  Dict of node_id → BeliefNode (typically ``graph.nodes``).
            strata: Optional list of stratum names to include
                    (e.g. ``["operational", "policy"]``).  ``None`` means all.
            since:  Only include nodes created after this unix timestamp.

        Returns:
            A dict with ``federation_source``, ``exported_at``,
            ``instance_name``, ``node_count``, and ``nodes`` list.
        """
        now = time.time()
        serialized_nodes = []

        for nid, node in nodes.items():
            # Filter by stratum
            if strata is not None:
                raw = node.stratum
                name = raw.value if hasattr(raw, "value") else str(raw)
                if name not in strata:
                    continue

            # Filter by timestamp
            if node.created_at < since:
                continue

            serialized_nodes.append(_serialize_node(node))

        payload = {
            "federation_source": self.instance_name,
            "exported_at": now,
            "exported_by": self.instance_name,
            "node_count": len(serialized_nodes),
            "strata_filter": strata,
            "nodes": serialized_nodes,
        }

        # Log export to Chronicle
        if self.chronicle is not None:
            self.chronicle.emit(
                action="federation_export",
                payload={
                    "instance": self.instance_name,
                    "node_count": len(serialized_nodes),
                    "strata_filter": strata,
                },
                agent=self.instance_name,
            )

        return payload

    # ── import_from ─────────────────────────────────────────────────

    def import_from(
        self,
        graph,
        data: Dict[str, Any],
        provenance_override: str = "federation",
    ) -> Dict[str, Any]:
        """
        Ingest nodes from another instance into the local graph.

        - All imported nodes get ``node.metadata["federation_source"]``
          set to the originating instance name.
        - Nodes with a ``node_id`` that already exists in ``graph`` are
          skipped (never overwrite).
        - Every import attempt is logged via the Chronicle.

        Args:
            graph:                  EpistemicGraph to import into.
            data:                   Export dict (output of ``export()``).
            provenance_override:    Override tag for the chronicle event.

        Returns:
            Dict with ``imported``, ``skipped``, ``total`` counts.
        """
        source = data.get("federation_source", "unknown")
        exported_at = data.get("exported_at", 0.0)
        foreign_nodes = data.get("nodes", [])

        imported_ids = []
        skipped_ids = []

        for node_data in foreign_nodes:
            node = _deserialize_node(node_data)

            # Check for duplicate — skip if node_id already exists
            if node.node_id in graph.nodes:
                skipped_ids.append(node.node_id)
                continue

            # Mark federation provenance in metadata
            merged_meta = dict(node.metadata)
            merged_meta["federation_source"] = source
            merged_meta["imported_at"] = time.time()
            merged_meta["provenance_override"] = provenance_override
            node = node._replace(metadata=merged_meta)

            graph.add_node(node)
            imported_ids.append(node.node_id)

        result = {
            "imported": len(imported_ids),
            "skipped": len(skipped_ids),
            "total": len(foreign_nodes),
            "imported_ids": imported_ids,
            "skipped_ids": skipped_ids,
            "source_instance": source,
        }

        # Log import to Chronicle (immutable)
        if self.chronicle is not None:
            self.chronicle.emit(
                action="federation_import",
                payload=result,
                agent=f"federation_{provenance_override}",
            )

        return result
