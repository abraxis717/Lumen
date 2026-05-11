#!/usr/bin/env python3
"""
lumen_meta.py — Meta-Control (Proto PhaseEngine) for Phase 2

Dynamically shift:
- Core weight ↑ in low-risk
- Shadow weight ↑ in high-uncertainty
alpha = f(risk, contradiction)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from lumen_cycles import _utc_iso


class Phase(str, Enum):
    """Processing phase — determines Core/Shadow balance."""
    STABLE = "stable"       # Low risk, high certainty → Core dominant
    EXPLORING = "exploring"  # Medium risk → balanced
    ADVERSARIAL = "adversarial"  # High risk, high uncertainty → Shadow dominant
    CONVERGING = "converging"  # Resolving contradiction → blend
    CRYSTALLIZING = "crystallizing"  # Finalizing decision → Core dominant


class PhaseEngine:
    """
    Meta-control layer: dynamically shifts the system's processing phase
    based on risk and contradiction signals.

    alpha = f(risk, contradiction) controls the Core/Shadow balance.
    alpha = 1.0 → pure Core (conservative)
    alpha = 0.0 → pure Shadow (adversarial)
    alpha = 0.5 → balanced
    """

    # Phase transition thresholds
    RISK_STABLE_MAX = 0.3
    RISK_EXPLORING_MAX = 0.6
    RISK_ADVERSARIAL_MAX = 1.0

    CONTRADICTION_STABLE_MAX = 0.2
    CONTRADICTION_EXPLORING_MAX = 0.5
    CONTRADICTION_ADVERSARIAL_MAX = 1.0

    def __init__(self, default_alpha: float = 0.5):
        self.default_alpha = default_alpha
        self._current_phase = Phase.STABLE
        self._alpha = default_alpha
        self._phase_history: List[Dict[str, Any]] = []
        self._transition_count = 0

    def compute_alpha(self, risk: float, contradiction: float) -> float:
        """
        Compute alpha from risk and contradiction.

        alpha = f(risk, contradiction)
        - Low risk → alpha ↑ (Core dominant, stable reasoning)
        - High risk → alpha ↓ (Shadow dominant, exploratory reasoning)
        - High contradiction → alpha ↓ (need adversarial stress testing)
        """
        # Weighted combination of risk and contradiction
        # Risk has slightly more influence than contradiction
        alpha = 0.6 * (1.0 - risk) + 0.4 * (1.0 - contradiction)

        # Clamp to [0, 1]
        return max(0.0, min(1.0, round(alpha, 4)))

    def determine_phase(self, risk: float, contradiction: float) -> Phase:
        """
        Determine current phase based on risk and contradiction.

        Phase transitions:
        - STABLE: low risk, low contradiction
        - EXPLORING: medium risk or medium contradiction
        - ADVERSARIAL: high risk or high contradiction
        - CONVERGING: contradiction decreasing (resolving)
        - CRYSTALLIZING: risk decreasing after high uncertainty
        """
        if risk <= self.RISK_STABLE_MAX and contradiction <= self.CONTRADICTION_STABLE_MAX:
            return Phase.STABLE
        elif risk >= self.RISK_ADVERSARIAL_MAX or contradiction >= self.CONTRADICTION_ADVERSARIAL_MAX:
            return Phase.ADVERSARIAL
        elif risk <= self.RISK_EXPLORING_MAX and contradiction <= self.CONTRADICTION_EXPLORING_MAX:
            return Phase.EXPLORING
        else:
            # Default to exploring for intermediate states
            return Phase.EXPLORING

    def update(self, risk: float, contradiction: float,
               previous_phase: Optional[Phase] = None) -> Dict[str, Any]:
        """
        Update meta-control state with current risk/contradiction.

        Returns phase transition info.
        """
        old_phase = self._current_phase
        new_phase = self.determine_phase(risk, contradiction)
        new_alpha = self.compute_alpha(risk, contradiction)

        transition = {
            "previous_phase": old_phase.value,
            "new_phase": new_phase.value,
            "risk": risk,
            "contradiction": contradiction,
            "alpha": new_alpha,
            "timestamp": _utc_iso(),
        }

        if old_phase != new_phase:
            transition["phase_changed"] = True
            self._transition_count += 1
        else:
            transition["phase_changed"] = False

        self._current_phase = new_phase
        self._alpha = new_alpha
        self._phase_history.append(transition)

        return transition

    def get_alpha(self) -> float:
        """Return current alpha (Core/Shadow balance)."""
        return self._alpha

    def get_phase(self) -> Phase:
        """Return current phase."""
        return self._current_phase

    def get_phase_weight(self, perspective: str) -> float:
        """
        Return the weight for a perspective given current phase.

        perspective: "core", "shadow", "balanced"
        """
        alpha = self._alpha

        if perspective == "core":
            return alpha
        elif perspective == "shadow":
            return 1.0 - alpha
        else:  # balanced
            return 0.5

    def should_fork(self) -> bool:
        """
        Should we fork into parallel hypotheses?

        True when contradiction is high enough to warrant branching.
        """
        return self._current_phase in (
            Phase.ADVERSARIAL, Phase.EXPLORING
        )

    def should_merge(self, branch_scores: List[float]) -> bool:
        """
        Should we merge branches?

        True when branches have converged (similar scores).
        """
        if len(branch_scores) < 2:
            return True

        spread = max(branch_scores) - min(branch_scores)
        return spread < 0.05

    def get_context(self) -> Dict[str, Any]:
        """Return current meta-control context for pipeline use."""
        return {
            "phase": self._current_phase.value,
            "alpha": self._alpha,
            "should_fork": self.should_fork(),
            "phase_weight_core": self.get_phase_weight("core"),
            "phase_weight_shadow": self.get_phase_weight("shadow"),
            "transition_count": self._transition_count,
            "phase_history_length": len(self._phase_history),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return meta-control statistics."""
        phases = [h["new_phase"] for h in self._phase_history]
        phase_counts = {}
        for p in phases:
            phase_counts[p] = phase_counts.get(p, 0) + 1

        return {
            "current_phase": self._current_phase.value,
            "current_alpha": self._alpha,
            "alpha_range": self._get_alpha_range(),
            "transition_count": self._transition_count,
            "phase_distribution": phase_counts,
            "total_updates": len(self._phase_history),
        }

    def _get_alpha_range(self) -> Dict[str, float]:
        """Get alpha min/max from history."""
        if not self._phase_history:
            return {"min": 0.5, "max": 0.5, "mean": 0.5}
        alphas = [h["alpha"] for h in self._phase_history]
        return {
            "min": round(min(alphas), 4),
            "max": round(max(alphas), 4),
            "mean": round(sum(alphas) / len(alphas), 4),
        }

    def reset(self):
        """Reset meta-control state."""
        self._current_phase = Phase.STABLE
        self._alpha = self.default_alpha
        self._phase_history.clear()
        self._transition_count = 0


class PhaseSignalAggregator:
    """
    Aggregate signals across multiple ticks to determine
    sustained risk/contradiction levels for phase transitions.
    """

    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self._risk_history: List[float] = []
        self._contradiction_history: List[float] = []

    def push(self, risk: float, contradiction: float):
        """Push a new signal tick."""
        self._risk_history.append(risk)
        self._contradiction_history.append(contradiction)

        # Keep window
        if len(self._risk_history) > self.window_size:
            self._risk_history.pop(0)
        if len(self._contradiction_history) > self.window_size:
            self._contradiction_history.pop(0)

    def get_aggregated(self) -> Tuple[float, float]:
        """
        Get aggregated (sustained) risk and contradiction.

        Uses exponential weighted average with more weight on recent values.
        """
        if not self._risk_history:
            return 0.0, 0.0

        # Exponential weighted average
        n = len(self._risk_history)
        weights = [2.0 ** i for i in range(n)]
        total_weight = sum(weights)

        risk = sum(
            r * w for r, w in zip(self._risk_history, weights)
        ) / total_weight

        contradiction = sum(
            c * w for c, w in zip(self._contradiction_history, weights)
        ) / total_weight

        return risk, contradiction

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregation statistics."""
        if not self._risk_history:
            return {"window_size": self.window_size, "samples": 0}

        return {
            "window_size": self.window_size,
            "samples": len(self._risk_history),
            "mean_risk": round(sum(self._risk_history) / len(self._risk_history), 4),
            "max_risk": round(max(self._risk_history), 4),
            "mean_contradiction": round(
                sum(self._contradiction_history) / len(self._contradiction_history), 4
            ),
            "max_contradiction": round(max(self._contradiction_history), 4),
        }
