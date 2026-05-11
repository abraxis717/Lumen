"""
BeliefNode — Immutable belief representation with strata, decay, and metadata.

Each BeliefNode carries:
- A unique ID (hash-chained to its source event)
- Confidence score [0.0, 1.0]
- Memory stratum (ephemeral → constitutional)
- Temporal decay (exponential half-life per stratum)
- Edges: supports (list of node IDs), contradicts (list of node IDs)
- metadata: free-form dict for provenance flags, constitutional violations, etc.
- cached_weight: last computed effective weight (−1 = uncomputed)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, TYPE_CHECKING

from Weaver_ASI.memory.strata import MemoryStratum

if TYPE_CHECKING:
    from Weaver_ASI.epistemics.epistemic_graph import EpistemicGraph


# Half-lives in seconds per stratum (configurable)
HALF_LIFES = {
    MemoryStratum.EPHEMERAL: 300,            # 5 minutes
    MemoryStratum.OPERATIONAL: 3600,          # 1 hour
    MemoryStratum.POLICY: 2592000,            # 30 days
    MemoryStratum.CONSTITUTIONAL: float('inf'),  # Never decays
    MemoryStratum.DISPUTED: 86400,            # 1 day
    MemoryStratum.DEPRECATED: float('inf'),   # Never decays (archived)
    MemoryStratum.SPECULATIVE: 43200,         # 12 hours
}


@dataclass(frozen=True)
class BeliefNode:
    """Immutable belief with stratum-aware decay and metadata."""

    node_id: str
    claim: str
    confidence: float
    stratum: MemoryStratum = MemoryStratum.OPERATIONAL
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    supports: List[str] = field(default_factory=list)
    contradicts: List[str] = field(default_factory=list)
    source_event_id: Optional[str] = None
    agent: Optional[str] = None
    citations: List[str] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)
    cached_weight: float = field(default=-1.0)

    # ── Pure static helpers ──────────────────────────────────────

    @staticmethod
    def compute_decay(elapsed_seconds: float, half_life: float) -> float:
        """Exponential decay: weight *= 0.5^(elapsed/half_life)."""
        if half_life == float('inf') or half_life <= 0:
            return 1.0
        return 0.5 ** (elapsed_seconds / half_life)

    # ── Multi-factor effective weight ────────────────────────────

    def effective_weight(self, current_time: Optional[float] = None) -> float:
        """Confidence adjusted by the full multi-factor thermodynamic model.

        If cached_weight < 0 (uncomputed), delegates to refresh_weight() which
        recomputes via the multi-factor formula and returns a new node.
        Returns the cached weight if already computed.
        """
        if self.cached_weight >= 0:
            return self.cached_weight

        # Uncomputed — delegate to refresh_weight
        # Note: refresh_weight returns a NEW node; we return its weight only.
        refreshed = self.refresh_weight(current_time)
        return refreshed.cached_weight

    def refresh_weight(self, current_time: Optional[float] = None) -> "BeliefNode":
        """Recompute effective weight using the multi-factor thermodynamic model.

        Returns a new BeliefNode with cached_weight populated.

        Factors:
            1. confidence (base)
            2. temporal_decay       — exponential half-life per stratum
            3. provenance_weight    — trust of source agent (default 0.8)
            4. contradiction_penalty — 0.5 if DISPUTED/DEPRECATED
            5. reinforcement_bonus  — +10% per supporting node, cap +100%
            6. constitutional_modifier — 0.0 if axiom violation flagged
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc).timestamp()

        # Pull trust scores from metadata or default
        trust_scores = self.metadata.get("trust_scores", {})

        # Factor 1: base confidence
        w = self.confidence

        # Factor 2: temporal decay
        raw = self.stratum
        name = raw.value if hasattr(raw, "value") else str(raw)
        hl = HALF_LIFES.get(self.stratum, HALF_LIFES[MemoryStratum.OPERATIONAL])
        elapsed = max(current_time - self.created_at, 0.0)
        if hl == float('inf'):
            pass  # no decay
        else:
            w *= self.compute_decay(elapsed, hl)

        # Factor 3: provenance weight
        agent_name = self.agent or "unknown"
        w *= trust_scores.get(agent_name, 0.8)

        # Factor 4: contradiction penalty
        if name in ("disputed", "deprecated"):
            w *= 0.5

        # Factor 5: reinforcement bonus (count supports that exist in graph)
        # We can't access the graph here, so we rely on the number of supports
        # stored on the node itself (set by ArbitrationEngine at ingestion time).
        support_count = len(self.supports)
        w *= (1.0 + 0.1 * min(support_count, 10))

        # Factor 6: constitutional modifier
        if self.metadata.get("constitutional_violation", False):
            w = 0.0

        w = max(0.0, min(w, 1.0))
        return self._replace(cached_weight=w)

    # ── Back-compat helpers ──────────────────────────────────────

    def _replace(self, **kwargs):
        """Helper to create a new BeliefNode with modified fields."""
        return BeliefNode(
            node_id=self.node_id,
            claim=self.claim,
            confidence=kwargs.get("confidence", self.confidence),
            stratum=kwargs.get("stratum", self.stratum),
            created_at=self.created_at,
            supports=self.supports,
            contradicts=self.contradicts,
            source_event_id=kwargs.get("source_event_id", self.source_event_id),
            agent=kwargs.get("agent", self.agent),
            citations=kwargs.get("citations", self.citations),
            metadata=kwargs.get("metadata", self.metadata),
            cached_weight=kwargs.get("cached_weight", self.cached_weight),
        )

    def upgrade_stratum(self) -> "BeliefNode":
        """Return a new BeliefNode with stratum upgraded by one level (if allowed)."""
        stratum_order = [
            MemoryStratum.EPHEMERAL,
            MemoryStratum.OPERATIONAL,
            MemoryStratum.POLICY,
            MemoryStratum.CONSTITUTIONAL,
        ]
        try:
            idx = stratum_order.index(self.stratum)
            if idx < len(stratum_order) - 1:
                return self._replace(stratum=stratum_order[idx + 1])
        except ValueError:
            pass
        return self

    # ── Display ──────────────────────────────────────────────────

    def __repr__(self):
        raw = self.stratum
        name = raw.value if hasattr(raw, "value") else str(raw)
        return (
            f"BeliefNode(id={self.node_id[:10]}, stratum={name}, "
            f"weight={self.cached_weight:.3f}, claim={self.claim[:40]}...)"
        )
