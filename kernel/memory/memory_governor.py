"""
MemoryGovernor — Ingests kernel events and transforms them into BeliefNodes.

Pipeline:
1. classify_stratum(event_type, confidence) → MemoryStratum
2. Create BeliefNode with provenance and metadata
3. Check for contradictions via EpistemicGraph
4. Resolve conflicts via ArbitrationEngine
5. Store in graph
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from kernel.epistemics.belief_node import BeliefNode
from kernel.epistemics.epistemic_graph import EpistemicGraph
from kernel.epistemics.arbitration import ArbitrationEngine
from kernel.epistemics.provenance import ProvenanceTracker
from kernel.memory.strata import MemoryStratum


class MemoryGovernor:
    """Manages the lifecycle of beliefs: ingestion, contradiction resolution, storage."""

    # ── Class-level trust registry ─────────────────────────────────
    _trust_scores: Dict[str, float] = {}

    # Default stratum mapping based on event type
    DEFAULT_STRATUMS = {
        'SYS_LEVEL_TRANSITION': MemoryStratum.OPERATIONAL,
        'CONSENSUS': MemoryStratum.POLICY,
        'TELEMETRY': MemoryStratum.EPHEMERAL,
        'MITIGATION': MemoryStratum.OPERATIONAL,
        'STEWARD_OVERRIDE': MemoryStratum.CONSTITUTIONAL,
        'CONSENSUS_EVENT': MemoryStratum.POLICY,
        'constitutional_axiom': MemoryStratum.CONSTITUTIONAL,
        'EVENT': MemoryStratum.OPERATIONAL,
    }

    def __init__(self, graph: EpistemicGraph, provenance: Optional[ProvenanceTracker] = None):
        self.graph = graph
        self.provenance = provenance or ProvenanceTracker()
        self._ingestion_count = 0
        self.constitutional = None  # optional reference to ConstitutionalKernel

    # ── Trust registry ─────────────────────────────────────────────

    @classmethod
    def set_trust(cls, agent_name: str, score: float) -> None:
        """Set trust score for an agent. Score clamped to [0.0, 1.0]."""
        cls._trust_scores[agent_name] = max(0.0, min(float(score), 1.0))

    @classmethod
    def get_trust(cls, agent_name: str) -> float:
        """Return trust score, defaulting to 0.8 for unknown agents."""
        return cls._trust_scores.get(agent_name, 0.8)

    @classmethod
    def get_trust_scores(cls) -> dict[str, float]:
        """Return a copy of the full trust registry."""
        return dict(cls._trust_scores)

    @classmethod
    def clear_trust(cls) -> None:
        """Clear all trust scores."""
        cls._trust_scores.clear()

    # ── Constitutional wiring ──────────────────────────────────────

    def set_constitutional(self, kernel) -> None:
        """Inject a ConstitutionalKernel reference for axiom validation."""
        self.constitutional = kernel

    # ── Stratum classification ─────────────────────────────────────

    def classify_stratum(self, event_type: str, confidence: float = 0.5) -> MemoryStratum:
        """Classify an event type into a memory stratum."""
        default = self.DEFAULT_STRATUMS.get(event_type, MemoryStratum.OPERATIONAL)

        # Upgrade stratum for high-confidence events
        if confidence >= 0.9:
            stratum_order = [
                MemoryStratum.EPHEMERAL,
                MemoryStratum.OPERATIONAL,
                MemoryStratum.POLICY,
            ]
            if default in stratum_order:
                idx = stratum_order.index(default)
                if idx < len(stratum_order) - 1:
                    return stratum_order[idx + 1]

        return default

    # ── Ingestion pipeline ─────────────────────────────────────────

    def ingest(
        self,
        event: Dict,
        claim_text: str,
        citations: List[str],
        agent: Optional[str] = None,
        source_event_id: Optional[str] = None,
        force_stratum: Optional[MemoryStratum] = None,
    ) -> Optional[BeliefNode]:
        """Ingest a belief into the epistemic graph.

        Args:
            event: Kernel event dict (must have 'type' and 'step')
            claim_text: The belief claim text
            citations: List of belief node IDs this belief cites
            agent: Agent that made the claim
            source_event_id: Chronicle event ID
            force_stratum: Override stratum classification (e.g., DISPUTED)

        Returns:
            The created BeliefNode, or None if ingestion failed
        """
        event_type = event.get('type', 'EVENT')
        confidence = event.get('confidence', 0.5)

        # Step 1: Classify stratum (or use forced stratum)
        stratum = force_stratum if force_stratum else self.classify_stratum(event_type, confidence)

        # Step 2: Create BeliefNode with metadata for multi-factor decay
        node_id = self._generate_node_id()
        node = BeliefNode(
            node_id=node_id,
            claim=claim_text,
            confidence=confidence,
            stratum=stratum,
            source_event_id=source_event_id or event.get('id', str(uuid.uuid4())),
            agent=agent,
            citations=citations,
        )

        # ── Inject metadata for multi-factor decay ────────────────

        # 2a: Provenance weight — inject trust scores into metadata
        trust_scores = self.get_trust_scores()
        node = self._with_metadata(node, {"trust_scores": trust_scores})

        # 2b: Constitutional modifier — check against kernel axioms
        con_violation = False
        if self.constitutional is not None:
            if not self.constitutional.is_valid(claim_text):
                con_violation = True
        if con_violation:
            node = self._with_metadata(node, {"constitutional_violation": True})

        # Step 3: Check for contradictions
        contradictions = self.graph.find_contradictions()
        has_contradiction = False
        for existing_node, _ in contradictions:
            if existing_node.claim == claim_text:
                continue  # Same claim, not a contradiction
            if self._claims_contradict(claim_text, existing_node.claim):
                has_contradiction = True
                break

        # Step 4: Resolve contradictions
        if has_contradiction:
            all_nodes = self.graph.get_all_nodes()
            for existing_node in all_nodes:
                if self._claims_contradict(claim_text, existing_node.claim):
                    winner_id, loser_id = ArbitrationEngine.resolve(node, existing_node)
                    if loser_id == node.node_id:
                        # New belief lost; reclassify to DISPUTED
                        node = node._replace(stratum=MemoryStratum.DISPUTED)
                        self.graph.add_contradiction(node.node_id, winner_id)
                        break

        # Step 5: Add to graph
        self.graph.add_node(node)

        # Step 6: Record provenance
        if source_event_id:
            self.provenance.record_provenance(
                node_id=node_id,
                source_event_id=source_event_id,
                agent=agent or "UNKNOWN",
                timestamp=datetime.now(timezone.utc).timestamp(),
                citations=citations,
            )

        self._ingestion_count += 1
        return node

    # ── Helpers ────────────────────────────────────────────────────

    def _with_metadata(self, node: BeliefNode, extra: Dict) -> BeliefNode:
        """Return a new node with merged metadata."""
        merged = dict(node.metadata)
        merged.update(extra)
        return node._replace(metadata=merged)

    def _generate_node_id(self) -> str:
        """Generate a unique node ID."""
        return f"belief_{uuid.uuid4().hex[:12]}"

    def _claims_contradict(self, claim_a: str, claim_b: str) -> bool:
        """Simple heuristic for contradiction detection."""
        negations = ['not ', 'no ', 'never ', 'false ', 'impossible ', 'refused ']
        a_lower = claim_a.lower()
        b_lower = claim_b.lower()

        for neg in negations:
            if a_lower.startswith(neg) and b_lower == a_lower[len(neg):]:
                return True
            if b_lower.startswith(neg) and a_lower == b_lower[len(neg):]:
                return True

        return False

    def get_ingestion_count(self) -> int:
        """Return number of beliefs ingested."""
        return self._ingestion_count
