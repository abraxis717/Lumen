#!/usr/bin/env python3
"""
lumen_stability.py — Stability Layer

Provides three monitoring subsystems:
  1. ReplayBands    — time-windowed replay stability tracking
  2. DriftMonitor   — output drift detection against baseline
  3. CycleHealth    — aggregate health score for the reasoning cycle

All subsystems produce structured telemetry compatible with
Lumen's telemetry contract (confidence, divergence_score,
resilience_score, replay_delta, status).
"""

from __future__ import annotations

import json
import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def _utc_iso(ts: Optional[float] = None) -> str:
    """Return UTC ISO-8601 string."""
    if ts is None:
        ts = time.time()
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors."""
    import numpy as np
    va, vb = np.array(a), np.array(b)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def l2_distance(a: List[float], b: List[float]) -> float:
    """L2 distance between two vectors."""
    import numpy as np
    return float(np.linalg.norm(np.array(a) - np.array(b)))


# ---------------------------------------------------------------------------
# 1. ReplayBands
# ---------------------------------------------------------------------------
@dataclass
class ReplayBand:
    """A time-windowed band of replay results."""
    band_id: str
    start_ts: float
    end_ts: float
    replay_deltas: List[float]  # replay_delta values in this band
    window_seconds: float = 300.0  # 5-minute default window

    @property
    def count(self) -> int:
        return len(self.replay_deltas)

    @property
    def mean_delta(self) -> float:
        if not self.replay_deltas:
            return 0.0
        return sum(self.replay_deltas) / len(self.replay_deltas)

    @property
    def max_delta(self) -> float:
        if not self.replay_deltas:
            return 0.0
        return max(self.replay_deltas)

    @property
    def stability(self) -> float:
        """Stability score: inverse of mean delta, clamped to [0,1]."""
        if not self.replay_deltas:
            return 1.0
        mean = self.mean_delta
        # 0 delta = stable (1.0), 1 delta = unstable (0.0)
        return max(0.0, min(1.0, 1.0 - mean))

    def add_delta(self, delta: float):
        self.replay_deltas.append(delta)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "band_id": self.band_id,
            "start_ts": _utc_iso(self.start_ts),
            "end_ts": _utc_iso(self.end_ts),
            "window_seconds": self.window_seconds,
            "count": self.count,
            "mean_delta": round(self.mean_delta, 4),
            "max_delta": round(self.max_delta, 4),
            "stability": round(self.stability, 4),
        }


class ReplayBands:
    """
    Sliding window replay stability tracker.

    Maintains a deque of ReplayBands, each covering a time window.
    New replay deltas are added and old bands expire.
    """

    def __init__(self, window_seconds: float = 300.0, max_bands: int = 12):
        self.window_seconds = window_seconds
        self.max_bands = max_bands
        self._bands: deque = deque()
        self._current_band: Optional[ReplayBand] = None
        self._band_start: Optional[float] = None

    def add_replay_delta(self, delta: float, ts: Optional[float] = None):
        """Record a replay_delta value."""
        now = ts or time.time()
        # Start new band if needed
        if self._band_start is None or now - self._band_start >= self.window_seconds:
            self._close_band(now)
            self._current_band = ReplayBand(
                band_id=str(uuid.uuid4())[:8],
                start_ts=now,
                end_ts=now + self.window_seconds,
                replay_deltas=[],
                window_seconds=self.window_seconds,
            )
            self._band_start = now
            self._bands.append(self._current_band)
            # Trim old bands
            while len(self._bands) > self.max_bands:
                self._bands.popleft()

        if self._current_band:
            self._current_band.add_delta(delta)

    def _close_band(self, now: float):
        if self._current_band:
            self._current_band.end_ts = now

    @property
    def active_band(self) -> Optional[ReplayBand]:
        return self._current_band

    @property
    def recent_bands(self) -> List[ReplayBand]:
        return list(self._bands)

    @property
    def overall_stability(self) -> float:
        """Weighted stability across all bands."""
        if not self._bands:
            return 1.0
        total_weight = 0.0
        weighted_sum = 0.0
        for band in self._bands:
            w = band.count
            total_weight += w
            weighted_sum += w * band.stability
        if total_weight == 0:
            return 1.0
        return weighted_sum / total_weight

    @property
    def trend(self) -> str:
        """Stability trend: 'improving', 'stable', or 'degrading'."""
        bands = self.recent_bands
        if len(bands) < 2:
            return "insufficient_data"
        recent = bands[-1].stability
        older = bands[-2].stability
        diff = recent - older
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "degrading"
        return "stable"

    def get_telemetry(self) -> Dict[str, Any]:
        """Return telemetry compatible with Lumen contract."""
        return {
            "replay_stability": round(self.overall_stability, 4),
            "replay_trend": self.trend,
            "active_band_count": len(self._bands),
            "active_band_stability": round(
                self._current_band.stability if self._current_band else 1.0, 4
            ),
            "recent_band_means": [
                round(b.mean_delta, 4) for b in list(self._bands)[-3:]
            ],
        }


# ---------------------------------------------------------------------------
# 2. DriftMonitor
# ---------------------------------------------------------------------------
@dataclass
class Baseline:
    """Baseline output for drift comparison."""
    embedding: List[float]
    text_signature: str  # hash or fingerprint of output text
    timestamp: float
    label: str = "baseline"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "text_signature": self.text_signature,
            "timestamp": _utc_iso(self.timestamp),
            "embedding_dim": len(self.embedding),
        }


class DriftMonitor:
    """
    Detects output drift from a baseline.

    Tracks cosine similarity and L2 distance between
    current outputs and the stored baseline.
    """

    def __init__(
        self,
        baseline_embedding: List[float],
        baseline_text_sig: str,
        drift_threshold_cosine: float = 0.85,
        drift_threshold_l2: float = 0.3,
    ):
        self.baseline = Baseline(
            embedding=baseline_embedding,
            text_signature=baseline_text_sig,
            timestamp=time.time(),
        )
        self.drift_threshold_cosine = drift_threshold_cosine
        self.drift_threshold_l2 = drift_threshold_l2
        self._history: deque = deque(maxlen=100)

    def record_output(
        self,
        embedding: List[float],
        text_sig: str,
        ts: Optional[float] = None,
    ):
        """Record an output for drift monitoring."""
        now = ts or time.time()
        cos = cosine_similarity(self.baseline.embedding, embedding)
        l2 = l2_distance(self.baseline.embedding, embedding)
        drift_status = "drift" if (cos < self.drift_threshold_cosine or l2 > self.drift_threshold_l2) else "nominal"

        entry = {
            "timestamp": now,
            "cosine_similarity": cos,
            "l2_distance": l2,
            "drift_status": drift_status,
            "text_signature": text_sig,
        }
        self._history.append(entry)

    @property
    def current_drift(self) -> Dict[str, Any]:
        """Latest drift measurement."""
        if not self._history:
            return {
                "cosine_similarity": 1.0,
                "l2_distance": 0.0,
                "drift_status": "nominal",
            }
        return self._history[-1]

    @property
    def drift_rate(self) -> float:
        """Rate of drift: mean cosine similarity decline over history."""
        if len(self._history) < 2:
            return 0.0
        cosines = [e["cosine_similarity"] for e in self._history]
        if len(cosines) < 2:
            return 0.0
        first = cosines[0]
        last = cosines[-1]
        # Negative = drifting away, positive = drifting toward
        return first - last

    @property
    def is_drifting(self) -> bool:
        """Whether current output is considered drifted."""
        return self.current_drift["drift_status"] == "drift"

    def get_telemetry(self) -> Dict[str, Any]:
        """Return telemetry compatible with Lumen contract."""
        drift = self.current_drift
        return {
            "drift_cosine": round(drift["cosine_similarity"], 4),
            "drift_l2": round(drift["l2_distance"], 4),
            "drift_status": drift["drift_status"],
            "drift_rate": round(self.drift_rate, 4),
            "is_drifting": self.is_drifting,
            "baseline": self.baseline.to_dict(),
        }


# ---------------------------------------------------------------------------
# 3. CycleHealth
# ---------------------------------------------------------------------------
@dataclass
class HealthSignal:
    """A single health signal for the reasoning cycle."""
    signal_type: str  # e.g. "contradiction", "coherence", "sanctuary_rate"
    value: float
    timestamp: float
    direction: str = "neutral"  # "up", "down", "neutral"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type,
            "value": round(self.value, 4),
            "timestamp": _utc_iso(self.timestamp),
            "direction": self.direction,
            "weight": self.weight,
        }


class CycleHealth:
    """
    Aggregate health monitoring for the Lumen reasoning cycle.

    Combines multiple signals into an overall health score.
    """

    def __init__(self):
        self._signals: deque = deque(maxlen=200)
        self._signal_history: Dict[str, List[float]] = {}

    def record_signal(
        self,
        signal_type: str,
        value: float,
        ts: Optional[float] = None,
        direction: str = "neutral",
        weight: float = 1.0,
    ):
        """Record a health signal."""
        now = ts or time.time()
        signal = HealthSignal(
            signal_type=signal_type,
            value=value,
            timestamp=now,
            direction=direction,
            weight=weight,
        )
        self._signals.append(signal)

        # Track per-signal history
        if signal_type not in self._signal_history:
            self._signal_history[signal_type] = []
        self._signal_history[signal_type].append(value)
        # Keep last 50
        if len(self._signal_history[signal_type]) > 50:
            self._signal_history[signal_type] = self._signal_history[signal_type][-50:]

    @property
    def health_score(self) -> float:
        """
        Weighted health score across all signals.

        Each signal contributes: value * weight.
        Normalized to [0, 1].
        """
        if not self._signals:
            return 1.0

        total_weight = 0.0
        weighted_sum = 0.0
        for signal in self._signals:
            w = signal.weight
            total_weight += w
            weighted_sum += signal.value * w

        if total_weight == 0:
            return 1.0
        return weighted_sum / total_weight

    @property
    def trend(self) -> str:
        """Overall health trend."""
        if len(self._signals) < 5:
            return "insufficient_data"

        recent = self.health_score
        # Compare to 5 signals ago
        older = sum(s.value * s.weight for s in list(self._signals)[-10:-5]) / \
                sum(s.weight for s in list(self._signals)[-10:-5]) if len(self._signals) >= 10 else recent

        diff = recent - older
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "degrading"
        return "stable"

    @property
    def active_signals(self) -> List[str]:
        """Types of signals currently being tracked."""
        return list(self._signal_history.keys())

    def get_signal_history(self, signal_type: str) -> List[float]:
        """Get historical values for a specific signal."""
        return self._signal_history.get(signal_type, [])

    def get_telemetry(self) -> Dict[str, Any]:
        """Return telemetry compatible with Lumen contract."""
        return {
            "health_score": round(self.health_score, 4),
            "health_trend": self.trend,
            "active_signal_types": self.active_signals,
            "signal_count": len(self._signals),
            "recent_signals": [
                s.to_dict() for s in list(self._signals)[-5:]
            ],
        }


# ---------------------------------------------------------------------------
# StabilitySummary — combined telemetry
# ---------------------------------------------------------------------------
@dataclass
class StabilitySummary:
    """Combined stability telemetry from all three subsystems."""
    replay: Optional[ReplayBands] = None
    drift: Optional[DriftMonitor] = None
    health: Optional[CycleHealth] = None

    def get_telemetry(self) -> Dict[str, Any]:
        """Return combined telemetry."""
        result = {}
        if self.replay:
            result.update(self.replay.get_telemetry())
        if self.drift:
            result.update(self.drift.get_telemetry())
        if self.health:
            result.update(self.health.get_telemetry())
        return result

    def get_health_score(self) -> float:
        """Overall health score (0-1)."""
        scores = []
        if self.replay:
            scores.append(self.replay.overall_stability)
        if self.drift:
            # 1 - drift_rate (higher = more stable)
            scores.append(1.0 - max(0, self.drift.drift_rate))
        if self.health:
            scores.append(self.health.health_score)
        if not scores:
            return 1.0
        return sum(scores) / len(scores)
