#!/usr/bin/env python3
"""
lumen_branching.py — Branching Engine for Phase 2

Branch on contradiction > 0.5, maintain N=3-5 parallel hypotheses.
branch_score = base_score + uniqueness_bonus - redundancy_penalty
Exit condition: branching produces meaningful divergence (>0.1 spread).
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from lumen_cycles import (
    PrimeCycle, PrimeCycleRegistry, CycleType,
    deterministic_embedding, cosine_similarity, _simple_tokenize, _utc_iso,
)


class BranchState(str, Enum):
    ACTIVE = "active"
    PRUNED = "pruned"
    MERGED = "merged"
    FAILED = "failed"


@dataclass
class Branch:
    """A single hypothesis branch in the branching engine."""
    hypothesis_text: str
    parent_id: Optional[str] = None
    base_score: float = 0.5
    uniqueness_bonus: float = 0.0
    redundancy_penalty: float = 0.0
    branch_score: float = 0.5
    state: BranchState = BranchState.ACTIVE
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    branch_id: str = ""

    def __post_init__(self):
        if not self.branch_id:
            self.branch_id = f"br_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = _utc_iso()
        self.branch_score = self._compute_score()

    def _compute_score(self) -> float:
        score = self.base_score + self.uniqueness_bonus - self.redundancy_penalty
        return max(0.0, min(1.0, round(score, 4)))


class BranchingEngine:
    """
    Fork on contradiction > 0.5.
    Maintain N=3-5 parallel hypotheses.
    Exit when meaningful divergence (>0.1 spread) is achieved.
    """

    def __init__(self, max_branches: int = 5,
                 min_divergence: float = 0.1,
                 dead_threshold: float = 0.2):
        self.max_branches = max_branches
        self.min_divergence = min_divergence
        self.dead_threshold = dead_threshold
        self._branches: Dict[str, Branch] = {}
        self._history: List[Dict[str, Any]] = []

    def fork(self, input_text: str, registry: PrimeCycleRegistry,
             base_score: float = 0.5,
             contradiction: float = 0.0,
             max_branches: Optional[int] = None,
             perspective: str = "default") -> List[Branch]:
        """
        Fork hypotheses when contradiction > threshold.

        Generates multiple perspectives on the same input:
        - Conservative (Core): emphasizes stability, existing cycles
        - Exploratory (Shadow): emphasizes novelty, new connections
        - Balanced: compromise between Core and Shadow
        - Analytical: focuses on evidence and signal
        - Creative: focuses on unexpected connections

        Returns list of Branch objects.
        """
        if max_branches is None:
            max_branches = self.max_branches

        # Don't fork if contradiction is low
        if contradiction < 0.3 and base_score > 0.7:
            # Strong signal, no need to branch
            single = Branch(
                hypothesis_text=input_text,
                base_score=base_score,
                branch_score=base_score,
                metadata={"perspective": "unified", "forked": False},
            )
            self._branches[single.branch_id] = single
            return [single]

        perspectives = self._generate_perspectives(
            input_text, registry, base_score, contradiction,
            max_branches, perspective
        )

        branches = []
        for i, (text, score, bonus, penalty) in enumerate(perspectives):
            branch = Branch(
                hypothesis_text=text,
                base_score=score,
                uniqueness_bonus=bonus,
                redundancy_penalty=penalty,
                metadata={
                    "perspective": f"perspective_{i}",
                    "parent_input": input_text[:100],
                    "forked": True,
                    "contradiction_at_fork": contradiction,
                },
            )
            self._branches[branch.branch_id] = branch
            branches.append(branch)

        self._history.append({
            "event": "fork",
            "num_branches": len(branches),
            "contradiction": contradiction,
            "base_score": base_score,
            "timestamp": _utc_iso(),
        })

        return branches

    def _generate_perspectives(
        self, input_text: str, registry: PrimeCycleRegistry,
        base_score: float, contradiction: float,
        max_branches: int, perspective: str
    ) -> List[Tuple[str, float, float, float]]:
        """Generate N perspective hypotheses on the same input."""
        tokens = _simple_tokenize(input_text)
        active_cycles = registry.get_active(STABILITY_THRESHOLD := 0.6)

        perspectives = []

        # Core perspective: conservative, cycle-aligned
        core_score = base_score * 0.9
        core_text = self._core_perspective(input_text, active_cycles, tokens)
        perspectives.append((core_text, core_score, 0.0, 0.0))

        # Shadow perspective: adversarial, novel
        shadow_score = base_score * (0.6 + contradiction * 0.3)
        shadow_text = self._shadow_perspective(input_text, active_cycles, tokens)
        uniqueness = min(1.0, contradiction * 0.5)
        perspectives.append((shadow_text, shadow_score, uniqueness, 0.1))

        # Balanced perspective
        balanced_score = base_score
        balanced_text = self._balanced_perspective(input_text, active_cycles, tokens)
        perspectives.append((balanced_text, balanced_score, 0.05, 0.05))

        # If we have room, add more perspectives
        if max_branches > 3:
            # Analytical: evidence-based
            analysis_score = base_score * 0.85
            analysis_text = self._analytical_perspective(input_text, active_cycles, tokens)
            perspectives.append((analysis_text, analysis_score, 0.1, 0.05))

            if max_branches > 4:
                # Creative: unexpected connections
                creative_score = base_score * 0.7
                creative_text = self._creative_perspective(input_text, active_cycles, tokens)
                perspectives.append((creative_text, creative_score, 0.15, 0.08))

        return perspectives[:max_branches]

    def _core_perspective(self, text, cycles, tokens):
        return f"[CORE] Aligning with existing cycles: {text}"

    def _shadow_perspective(self, text, cycles, tokens):
        return f"[SHADOW] Challenging assumptions: {text}"

    def _balanced_perspective(self, text, cycles, tokens):
        return f"[BALANCED] Weighing evidence: {text}"

    def _analytical_perspective(self, text, cycles, tokens):
        return f"[ANALYTICAL] Evidence analysis: {text}"

    def _creative_perspective(self, text, cycles, tokens):
        return f"[CREATIVE] Novel connections: {text}"

    def score_hypotheses(self, outputs: List[str]) -> List[Tuple[Branch, float, float, float]]:
        """Score each hypothesis for uniqueness vs redundancy."""
        results = []
        for bid, branch in self._branches.items():
            if branch.state != BranchState.ACTIVE:
                continue
            if not branch.hypothesis_text:
                results.append((branch, 0.5, 0.0, 0.0))
                continue

            # Compute redundancy against other branches
            emb = deterministic_embedding(branch.hypothesis_text)
            redundancy = 0.0
            uniqueness = 0.0

            if len(self._branches) > 1:
                sim_scores = []
                for other_bid, other in self._branches.items():
                    if other_bid == bid or other.state != BranchState.ACTIVE:
                        continue
                    other_emb = deterministic_embedding(other.hypothesis_text)
                    sim = cosine_similarity(emb, other_emb)
                    sim_scores.append(sim)
                    redundancy += sim

                if sim_scores:
                    redundancy = redundancy / (len(sim_scores) * 1.0)
                    uniqueness = max(0.0, 1.0 - redundancy)

            results.append((branch, branch.base_score, uniqueness, redundancy))

        return results

    def prune_dead_branches(self, dead_threshold: Optional[float] = None) -> List[str]:
        """Prune branches below dead_threshold score."""
        if dead_threshold is None:
            dead_threshold = self.dead_threshold

        pruned = []
        for bid, branch in self._branches.items():
            if branch.state != BranchState.ACTIVE:
                continue
            if branch.branch_score < dead_threshold:
                branch.state = BranchState.PRUNED
                pruned.append(bid)
                self._history.append({
                    "event": "prune",
                    "branch_id": bid,
                    "score": branch.branch_score,
                    "timestamp": _utc_iso(),
                })

        return pruned

    def merge_winners(self) -> Optional[Branch]:
        """Merge surviving branches into a single consensus hypothesis."""
        active = [b for b in self._branches.values() if b.state == BranchState.ACTIVE]
        if not active:
            return None

        active.sort(key=lambda b: b.branch_score, reverse=True)
        if len(active) == 1:
            return active[0]

        # Merge: take highest-scoring, blend unique parts
        winner = active[0]
        merged_hints = []
        for b in active[1:]:
            if b.uniqueness_bonus > 0.1:
                merged_hints.append(b.hypothesis_text)
                b.state = BranchState.MERGED

        if merged_hints:
            winner.hypothesis_text += f"\n[merged:{' '.join(merged_hints[:3])}]"
            winner.uniqueness_bonus = min(1.0, winner.uniqueness_bonus + 0.05)
            winner.branch_score = winner._compute_score()

        # Mark non-winner active branches as merged
        for b in active[1:]:
            if b.state == BranchState.ACTIVE:
                b.state = BranchState.MERGED

        self._history.append({
            "event": "merge",
            "winner": winner.branch_id,
            "merged_count": len(active) - 1,
            "timestamp": _utc_iso(),
        })

        return winner

    def get_active_branches(self) -> List[Branch]:
        """Return active branches sorted by score."""
        active = [b for b in self._branches.values() if b.state == BranchState.ACTIVE]
        active.sort(key=lambda b: b.branch_score, reverse=True)
        return active

    def has_meaningful_divergence(self, threshold: Optional[float] = None) -> bool:
        """Check if branches have meaningful divergence (>0.1 score spread)."""
        if threshold is None:
            threshold = self.min_divergence

        active = self.get_active_branches()
        if len(active) < 2:
            return False

        scores = [b.branch_score for b in active]
        spread = max(scores) - min(scores)
        return spread > threshold

    def get_stats(self) -> Dict[str, Any]:
        """Return branching engine statistics."""
        all_branches = list(self._branches.values())
        active = [b for b in all_branches if b.state == BranchState.ACTIVE]
        pruned = [b for b in all_branches if b.state == BranchState.PRUNED]
        merged = [b for b in all_branches if b.state == BranchState.MERGED]

        scores = [b.branch_score for b in all_branches] if all_branches else [0.0]
        spread = max(scores) - min(scores) if len(scores) > 1 else 0.0

        return {
            "total_branches": len(all_branches),
            "active": len(active),
            "pruned": len(pruned),
            "merged": len(merged),
            "mean_score": round(sum(scores) / len(scores), 4),
            "score_spread": round(spread, 4),
            "meaningful_divergence": spread > self.min_divergence,
            "fork_count": sum(1 for h in self._history if h.get("event") == "fork"),
        }

    def reset(self):
        """Clear all branches and history."""
        self._branches.clear()
        self._history.clear()
