"""
ProvenanceTracker — Attach provenance metadata to BeliefNodes.

Tracks:
- Source event ID (from Chronicle)
- Agent that created the belief
- Timestamp
- Citations (other belief IDs this belief references)
"""
from typing import Dict, List, Optional
import hashlib


class ProvenanceTracker:
    """Manages provenance metadata for BeliefNodes."""

    def __init__(self):
        self._provenance: Dict[str, Dict] = {}

    def record_provenance(
        self,
        node_id: str,
        source_event_id: str,
        agent: str,
        timestamp: float,
        citations: List[str],
    ) -> None:
        """Record provenance for a belief node."""
        self._provenance[node_id] = {
            'node_id': node_id,
            'source_event_id': source_event_id,
            'agent': agent,
            'timestamp': timestamp,
            'citations': citations,
            'provenance_hash': self._compute_hash(source_event_id, agent, timestamp),
        }

    def get_provenance(self, node_id: str) -> Optional[Dict]:
        """Get provenance metadata for a node."""
        return self._provenance.get(node_id)

    def get_provenance_chain(self, node_id: str, depth: int = 5) -> List[Dict]:
        """Trace the provenance chain backwards through citations."""
        chain = []
        visited = set()
        current_id = node_id

        while current_id and len(chain) < depth:
            provenance = self._provenance.get(current_id)
            if not provenance or current_id in visited:
                break
            visited.add(current_id)
            chain.append(provenance)
            # Follow first citation
            citations = provenance.get('citations', [])
            current_id = citations[0] if citations else None

        return chain

    def _compute_hash(self, event_id: str, agent: str, timestamp: float) -> str:
        """Compute a provenance hash."""
        data = f"{event_id}:{agent}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def verify_provenance(self, node_id: str) -> bool:
        """Verify that a node's provenance is complete and valid."""
        provenance = self._provenance.get(node_id)
        if not provenance:
            return False
        # Check all required fields
        required = ['node_id', 'source_event_id', 'agent', 'timestamp', 'provenance_hash']
        return all(field in provenance and provenance[field] for field in required)