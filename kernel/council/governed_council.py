"""
governed_council.py — GovernedCouncil consensus engine (Phase 3.2)

Collects GovernedClaims from agents, resolves contradictions via the
EpistemicGraph + ArbitrationEngine, and emits a single canonical
consensus event whose payload is a structured, multi-claim synthesis
with full lineage.

Usage pattern:
    council = GovernedCouncil(graph, governor, constitutional)
    agent_claims = {"Oracle": [...], "Mitigation": [...]}
    consensus_event = council.deliberate(agent_claims)
    kernel.emit(consensus_event["type"], consensus_event, agent="governed_council")
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from kernel.council.claims import GovernedClaim
from kernel.epistemics.belief_node import BeliefNode
from kernel.epistemics.epistemic_graph import EpistemicGraph
from kernel.epistemics.arbitration import ArbitrationEngine
from kernel.memory.memory_governor import MemoryGovernor
from kernel.memory.strata import MemoryStratum
from kernel.constitutional.constitutional_kernel import ConstitutionalKernel

logger = logging.getLogger(__name__)


@dataclass
class ConsensusResult:
    """Canonical consensus event emitted by the GovernedCouncil."""
    council_id: str
    claims: List[Dict]          # canonical claim dicts
    resolution: str             # "arbitrated", "no_claims", "all_disputed"
    timestamp: float
    total_in: int               # claims fed in before arbitration
    total_out: int              # canonical claims surviving
    contradictions_found: int   # number of contradicting pairs found
    disputed_count: int         # claims reclassified to DISPUTED


class GovernedCouncil:
    """
    Collects claims from agents, reconciles contradictions via the
    epistemic graph, and builds a single canonical consensus event.

    The council operates in three phases:
      1. TEMPORARY — create BeliefNodes for all claims in an isolated
         graph; detect contradictions within this batch (and optionally
         against the real graph).
      2. ARBITRATE — pairwise resolve contradictions using
         ArbitrationEngine. Winners stay, losers are reclassified to
         DISPUTED.
      3. INGEST — canonical (non-disputed) claims are permanently
         ingested into the real graph via MemoryGovernor.
    """

    def __init__(
        self,
        graph: EpistemicGraph,
        governor: MemoryGovernor,
        constitutional: ConstitutionalKernel,
        *,
        cross_check: bool = True,
    ) -> None:
        """
        Args:
            graph:            The real EpistemicGraph (for final ingestion
                              and optional cross-checking against existing
                              knowledge).
            governor:         MemoryGovernor used to permanently ingest the
                              canonical consensus claims.
            constitutional:   ConstitutionalKernel for validity checks.
            cross_check:      If True, also check each claim against the
                              real graph before arbitration.
        """
        self.graph = graph
        self.governor = governor
        self.constitutional = constitutional
        self.cross_check = cross_check

    def deliberate(
        self,
        agent_claims: Dict[str, List[GovernedClaim]],
    ) -> ConsensusResult:
        """
        Run the full deliberation pipeline.

        Args:
            agent_claims: mapping agent_name -> list of GovernedClaim

        Returns:
            ConsensusResult with canonical claims and metadata.
        """
        # Flatten
        all_claims: List[GovernedClaim] = []
        for agent, claims in agent_claims.items():
            for c in claims:
                all_claims.append(c)

        if not all_claims:
            return ConsensusResult(
                council_id=str(uuid.uuid4()),
                claims=[],
                resolution="no_claims",
                timestamp=time.time(),
                total_in=0,
                total_out=0,
                contradictions_found=0,
                disputed_count=0,
            )

        # ---- Phase 1: Create temporary nodes in an isolated graph ----
        temp_graph = EpistemicGraph()
        node_by_idx: Dict[int, BeliefNode] = {}  # index -> node

        for i, claim in enumerate(all_claims):
            node = self._build_temp_node(claim)
            temp_graph.add_node(node)
            node_by_idx[i] = node

        # Also add existing real-graph nodes if cross-checking
        if self.cross_check:
            for existing in self.graph.get_all_nodes():
                if existing.stratum not in (
                    MemoryStratum.DEPRECATED, MemoryStratum.DISPUTED
                ):
                    temp_graph.add_node(existing)

        # ---- Phase 2: Arbitrate contradictions within the batch ----
        contradictions_found = 0
        batch_nodes = list(node_by_idx.values())

        for a, b in combinations(batch_nodes, 2):
            if self._are_contradictory(a, b):
                contradictions_found += 1
                ArbitrationEngine.resolve(a, b)

        # Also check claims against existing real-graph knowledge
        for i, claim in enumerate(all_claims):
            node = node_by_idx[i]
            for existing in self.graph.get_all_nodes():
                if existing.stratum in (
                    MemoryStratum.DEPRECATED, MemoryStratum.DISPUTED
                ):
                    continue
                if self._are_contradictory(node, existing):
                    ArbitrationEngine.resolve(node, existing)
                    contradictions_found += 1
                    break

        # ---- Phase 3: Extract canonical claims (non-DISPUTED) ----
        canonical_claims: List[GovernedClaim] = []
        disputed_count = 0
        for i, claim in enumerate(all_claims):
            node = node_by_idx[i]
            if node.stratum == MemoryStratum.DISPUTED:
                disputed_count += 1
            else:
                canonical_claims.append(claim)

        # ---- Phase 4: Build canonical claim dicts for the event payload ----
        canonical_dicts = []
        canonical_set = set(id(c) for c in canonical_claims)
        for i, claim in enumerate(all_claims):
            if id(claim) in canonical_set:
                node = node_by_idx[i]
                canonical_dicts.append({
                    "text": claim.text,
                    "confidence": claim.confidence,
                    "citations": claim.citations,
                    "contradicts": claim.contradicts,
                    "stratum": node.stratum.value,
                    "node_id": node.node_id,
                    "source_agent": claim.agent,
                })

        # ---- Phase 5: Permanently ingest via MemoryGovernor ----
        council_id = str(uuid.uuid4())
        timestamp = time.time()

        for cd in canonical_dicts:
            event = {
                "id": f"cons_{council_id[:8]}",
                "type": "consensus_inner",
                "step": cd.get("step", 0),
                "confidence": cd["confidence"],
            }
            self.governor.ingest(
                event,
                claim_text=cd["text"],
                citations=cd.get("citations", []),
                agent=cd.get("source_agent", "governed_council"),
                source_event_id=f"gc_{council_id[:8]}",
            )

        # ---- Phase 6: Emit final consensus event ----
        resolution = "arbitrated"
        if not canonical_dicts:
            resolution = "all_disputed"

        return ConsensusResult(
            council_id=council_id,
            claims=canonical_dicts,
            resolution=resolution,
            timestamp=timestamp,
            total_in=len(all_claims),
            total_out=len(canonical_dicts),
            contradictions_found=contradictions_found,
            disputed_count=disputed_count,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_temp_node(claim: GovernedClaim) -> BeliefNode:
        """Create a BeliefNode from a GovernedClaim for arbitration."""
        # Classify stratum based on confidence
        if claim.confidence >= 0.9:
            stratum = MemoryStratum.OPERATIONAL
        elif claim.confidence >= 0.6:
            stratum = MemoryStratum.EPHEMERAL
        else:
            stratum = MemoryStratum.SPECULATIVE

        return BeliefNode(
            node_id=f"temp_{uuid.uuid4().hex[:8]}",
            claim=claim.text,
            confidence=claim.confidence,
            stratum=stratum,
            source_event_id=f"gc_{uuid.uuid4().hex[:6]}",
            agent=claim.agent,
            citations=claim.citations,
        )

    @staticmethod
    def _are_contradictory(node_a: BeliefNode, node_b: BeliefNode) -> bool:
        """Check if two BeliefNodes are semantically contradictory."""
        # Check explicit contradict edges
        if node_b.node_id in node_a.contradicts:
            return True
        if node_a.node_id in node_b.contradicts:
            return True

        # Negation heuristic: if one claim starts with a negation prefix
        # and the other claim equals the remainder, they contradict.
        negations = ("not ", "no ", "never ", "false ", "impossible ")
        a = node_a.claim.lower().strip()
        b = node_b.claim.lower().strip()

        for neg in negations:
            if a.startswith(neg) and b == a[len(neg):]:
                return True
            if b.startswith(neg) and a == b[len(neg):]:
                return True

        return False

    def __repr__(self) -> str:
        return (
            f"GovernedCouncil(cross_check={self.cross_check}, "
            f"graph_nodes={len(self.graph.nodes)})"
        )
