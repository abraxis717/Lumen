"""
Cognitive thermodynamics: multi-factor decay functions.

Each function is a pure, testable multiplier applied to a BeliefNode's
confidence to produce its effective weight.  All return 1.0 by default —
no factor should accidentally zero a belief unless explicitly configured.

Formula:
    effective_weight = confidence
        × temporal_decay
        × provenance_weight
        × contradiction_penalty
        × reinforcement_bonus
        × constitutional_modifier
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kernel.epistemics.belief_node import BeliefNode
    from kernel.epistemics.epistemic_graph import EpistemicGraph

# ── Stratum half-lives (seconds) ───────────────────────────────────────
HALF_LIFE: dict[str, float | None] = {
    "ephemeral": 300.0,           # 5 minutes
    "operational": 3600.0,        # 1 hour
    "speculative": 43200.0,       # 12 hours
    "disputed": 86400.0,          # 1 day
    "deprecated": 86400.0,        # 1 day (archived)
    "policy": 2592000.0,          # 30 days
    "constitutional": None,       # Never decays
}


def temporal_decay(node: BeliefNode, current_time: float) -> float:
    """Exponential half-life decay based on stratum.

    weight *= 0.5^(age / half_life)
    """
    raw = node.stratum
    name = raw.value if hasattr(raw, "value") else str(raw)
    hl = HALF_LIFE.get(name)
    if hl is None:
        return 1.0
    age = max(current_time - node.created_at, 0.0)
    return math.exp(-age / hl)


def provenance_weight(node: BeliefNode, trust_scores: dict[str, float]) -> float:
    """Trust score of the source agent. Unknown agents default to 0.8."""
    return trust_scores.get(node.source_agent or "unknown", 0.8)


def contradiction_penalty(node: BeliefNode) -> float:
    """Disputed / deprecated beliefs lose half their weight."""
    raw = node.stratum
    name = raw.value if hasattr(raw, "value") else str(raw)
    return 0.5 if name in ("disputed", "deprecated") else 1.0


def reinforcement_bonus(node: BeliefNode, graph: "EpistemicGraph | None" = None) -> float:
    """Each supporting node adds 10 %, capped at +100 %."""
    if graph is None:
        return 1.0
    support_count = sum(1 for nid in node.supports if nid in graph.nodes)
    return 1.0 + 0.1 * min(support_count, 10)


def constitutional_modifier(node: BeliefNode) -> float:
    """Zero weight if the belief was flagged as constitutional violation."""
    return 0.0 if node.metadata.get("constitutional_violation", False) else 1.0


def effective_weight(
    node: BeliefNode,
    current_time: float,
    trust_scores: dict[str, float],
    graph: "EpistemicGraph | None" = None,
) -> float:
    """Composite thermodynamic weight — the full cognitive-thermodynamics equation."""
    w = (
        node.confidence
        * temporal_decay(node, current_time)
        * provenance_weight(node, trust_scores)
        * contradiction_penalty(node)
        * reinforcement_bonus(node, graph)
        * constitutional_modifier(node)
    )
    return max(0.0, min(w, 1.0))
