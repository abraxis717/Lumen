#!/usr/bin/env python3
"""
lumen_adaptive.py — Adaptive Weights for Phase 2

Track accepted decisions + downstream success.
Online weight update: w_i ← w_i + η * (outcome - prediction)
Learning actually starts when weights change over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from lumen_cycles import _utc_iso


@dataclass
class WeightTracker:
    """Tracks a single weight's value, momentum, and update history."""
    weight_name: str
    value: float
    gradient_momentum: float = 0.0
    update_count: int = 0
    last_update: str = ""
    history: List[Tuple[str, float]] = field(default_factory=list)

    def __post_init__(self):
        if not self.last_update:
            self.last_update = _utc_iso()


# Default weights (same as decision_engine.py)
_DEFAULT_WEIGHTS = {
    "coherence": 0.30,
    "utility": 0.25,
    "cycle_coherence": 0.20,
    "risk": 0.15,
    "contradiction": 0.10,
}


class AdaptiveWeightEngine:
    """
    Adaptive weight learning for the decision pipeline.

    w_i ← w_i + η * (outcome - prediction)
    
    Tracks:
    - accepted decisions (outcome = 1)
    - rejected decisions (outcome = 0)
    - revise decisions (outcome = 0.5)
    
    Downstream success adjusts weights based on actual task outcomes.
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None,
                 learning_rate: float = 0.05,
                 decay: float = 0.01,
                 momentum: float = 0.9):
        self.learning_rate = learning_rate
        self.decay = decay
        self.momentum = momentum
        
        # Initialize weight trackers
        w_dict = weights or dict(_DEFAULT_WEIGHTS)
        self._weights: Dict[str, WeightTracker] = {}
        for name, val in w_dict.items():
            self._weights[name] = WeightTracker(
                weight_name=name,
                value=val,
            )

    def update_weights(
        self,
        signal_values: Dict[str, float],
        decision_outcome: float,
        lr: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Online weight update: w_i ← w_i + η * (outcome - prediction)
        
        Args:
            signal_values: dict of signal name -> value
            decision_outcome: actual outcome [0, 1]
            lr: optional learning rate override
        
        Returns: current weights dict.
        """
        if lr is None:
            lr = self.learning_rate

        predictions = self._predict(signal_values)
        error = decision_outcome - predictions

        for name, tracker in self._weights.items():
            if name not in signal_values:
                continue

            # Gradient: signal_value * error
            gradient = signal_values[name] * error

            # Add momentum
            tracker.gradient_momentum = (
                self.momentum * tracker.gradient_momentum
                + (1 - self.momentum) * gradient
            )

            # Update weight with momentum
            update = lr * (gradient + self.momentum * tracker.gradient_momentum)
            tracker.value += update

            # Apply decay (prevent drift)
            tracker.value *= (1 - self.decay)

            # Clamp to [0, 1]
            tracker.value = max(0.0, min(1.0, tracker.value))
            tracker.update_count += 1
            tracker.last_update = _utc_iso()

        # Renormalize weights to sum to 1
        self._renormalize()

        return self.get_weights()

    def track_decision(
        self,
        tick_id: str,
        signal_values: Dict[str, float],
        decision_outcome: float,
        actual_outcome: float,
    ):
        """
        Record an accepted/revised decision for weight learning.

        Args:
            tick_id: unique decision identifier
            signal_values: dict of signal name -> value
            decision_outcome: what the system predicted [0, 1]
            actual_outcome: actual downstream result [0, 1]
        """
        self.update_weights(signal_values, actual_outcome)

        # Log the decision for replay analysis
        self._weights["_history"] = self._weights.get("_history", [])
        self._weights["_history"] = getattr(
            self._weights.get("_history", None),
            "history",
            []
        ) if hasattr(self._weights.get("_history", None), "history") else []

    def _predict(self, signal_values: Dict[str, float]) -> float:
        """Predict outcome from current weights and signals."""
        weights = self.get_weights()
        predicted = sum(weights.get(k, 0) * v for k, v in signal_values.items())
        return max(0.0, min(1.0, predicted))

    def compute_outcome_signal(
        self, signal: Dict[str, float], decision: Dict[str, Any]
    ) -> float:
        """
        Compute predicted vs actual outcome delta.

        decision should have: action (accept/reject/revise), score
        outcome = 1.0 for accept, 0.5 for revise, 0.0 for reject
        """
        action = decision.get("action", "revise")
        score = decision.get("score", 0.5)

        if action == "accept":
            actual = 1.0
        elif action == "reject":
            actual = 0.0
        else:  # revise
            actual = 0.5

        predicted = self._predict(signal)
        return actual

    def get_weights(self) -> Dict[str, float]:
        """Return current weights dict (renormalized)."""
        return {
            name: tracker.value
            for name, tracker in self._weights.items()
            if not name.startswith("_")
        }

    def set_learning_rate(self, lr: float):
        """Adjust learning rate."""
        self.learning_rate = max(0.001, min(1.0, lr))

    def set_decay(self, decay: float):
        """Adjust weight decay rate."""
        self.decay = max(0.0, min(1.0, decay))

    def set_momentum(self, momentum: float):
        """Adjust gradient momentum coefficient."""
        self.momentum = max(0.0, min(1.0, momentum))

    def get_weight_history(self, name: str) -> List[Tuple[str, float]]:
        """Return update history for a specific weight."""
        tracker = self._weights.get(name)
        if tracker:
            return tracker.history
        return []

    def reset(self):
        """Return weights to defaults."""
        for name, val in _DEFAULT_WEIGHTS.items():
            if name in self._weights:
                self._weights[name].value = val
                self._weights[name].gradient_momentum = 0.0
                self._weights[name].update_count = 0

    def _renormalize(self):
        """Renormalize weights so they sum to 1."""
        total = sum(t.value for t in self._weights.values()
                    if not t.weight_name.startswith("_"))
        if total > 0 and total != 1.0:
            for name, tracker in self._weights.items():
                if not name.startswith("_"):
                    tracker.value = tracker.value / total
                    tracker.value = max(0.0, min(1.0, tracker.value))

    def get_stats(self) -> Dict[str, Any]:
        """Return weight learning statistics."""
        return {
            "weights": self.get_weights(),
            "learning_rate": self.learning_rate,
            "decay": self.decay,
            "momentum": self.momentum,
            "total_updates": sum(
                t.update_count for t in self._weights.values()
                if not t.weight_name.startswith("_")
            ),
        }
