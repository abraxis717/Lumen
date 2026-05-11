"""
GovernanceDriftMonitor — Full capture detection for Weaver ASI.

Monitors the epistemic graph and memory subsystem for signs of
governance capture and institutional drift:

  1. Decay-policy drift — half-life values change by >10 % between checks.
  2. Authority reweighting — one agent's trust score surges while others drop.
  3. Epistemic capture   — a single agent causes a disproportionate share
     of DISPUTED/DEPRECATED events within a window.
  4. Audit emissions     — all alerts are appended to the Chronicle as
     immutable ``governance_drift`` events.
  5. Dashboard           — ``summary()`` returns stratum counts, recent
     drift alerts, and average trust scores.

Stateless between calls (except for an internal snapshot used to detect
changes).  No persistence beyond the graph and chronicle.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from Weaver_ASI.memory.strata import MemoryStratum
from Weaver_ASI.memory import decay_models


@dataclass
class _Snapshot:
    """A point-in-time capture of the monitored subsystem."""

    half_lives: Dict[str, float] = field(default_factory=dict)
    trust_scores: Dict[str, float] = field(default_factory=dict)
    agent_dispute_counts: Dict[str, int] = field(default_factory=dict)
    total_dispute_events: int = 0
    total_deprecated_events: int = 0
    stratum_counts: Dict[str, int] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class DriftAlert:
    """A single governance-drift alert."""

    alert_type: str
    message: str
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL
    payload: Dict[str, Any] = field(default_factory=dict)


class GovernanceDriftMonitor:
    """Monitors the epistemic graph for signs of governance capture."""

    HALF_LIFE_DRIFT_PCT = 0.10   # >10 % change in half-life
    TRUST_REWEIGHT_THRESHOLD = 0.25  # one agent +0.25 while others drop
    CAPTURE_PROPORTION = 0.50    # single agent >50 % of disputed events
    CAPTURE_MIN_EVENTS = 5       # minimum disputed events before flagging

    def __init__(
        self,
        graph,
        constitutional=None,
        chronicle=None,
        memory_governor=None,
    ):
        """
        Args:
            graph:            EpistemicGraph instance.
            constitutional:   Optional ConstitutionalKernel (unused here).
            chronicle:        Optional Chronicle for audit emission.
            memory_governor:  Optional MemoryGovernor for trust-score access.
        """
        self.graph = graph
        self.constitutional = constitutional
        self.chronicle = chronicle
        self.memory_governor = memory_governor

        self._prev: Optional[_Snapshot] = None
        self._recent_alerts: List[DriftAlert] = []
        self._total_checks = 0

    # ── Public API ────────────────────────────────────────────────────

    def check(self) -> List[DriftAlert]:
        """Run all drift checks.  Returns new alerts (does NOT append)."""
        self._total_checks += 1
        snapshot = self._build_snapshot()
        alerts: List[DriftAlert] = []

        # 1. Decay-policy drift
        alerts.extend(self._check_half_life_drift(snapshot))

        # 2. Authority reweighting
        alerts.extend(self._check_authority_reweighting(snapshot))

        # 3. Epistemic capture
        alerts.extend(self._check_epistemic_capture(snapshot))

        # 4. Weight collapse (legacy, kept for compat)
        alerts.extend(self._check_weight_collapse(snapshot))

        # 5. Dispute cluster (legacy, kept for compat)
        alerts.extend(self._check_dispute_cluster(snapshot))

        # Emit to Chronicle
        self._emit_alerts(alerts)

        # Update snapshot for next comparison
        self._prev = snapshot
        self._recent_alerts.extend(alerts)
        return alerts

    def summary(self) -> Dict[str, Any]:
        """Dashboard summary: stratum counts, recent alerts, trust scores."""
        snap = self._build_snapshot()
        avg_trust = 0.0
        if snap.trust_scores:
            avg_trust = sum(snap.trust_scores.values()) / len(snap.trust_scores)

        recent = [
            {
                "type": a.alert_type,
                "severity": a.severity,
                "message": a.message,
            }
            for a in self._recent_alerts[-20:]
        ]

        return {
            "total_beliefs": len(self.graph.nodes),
            "stratum_counts": dict(snap.stratum_counts),
            "avg_trust_score": round(avg_trust, 4),
            "trust_scores": dict(snap.trust_scores),
            "recent_alerts": recent,
            "total_checks": self._total_checks,
        }

    # ── Snapshot builder ──────────────────────────────────────────────

    def _build_snapshot(self) -> _Snapshot:
        snap = _Snapshot()

        # Half-lives from decay policy
        snap.half_lives = dict(decay_models.HALF_LIFE)

        # Trust scores from MemoryGovernor (class-level registry)
        if self.memory_governor is not None:
            snap.trust_scores = dict(self.memory_governor.get_trust_scores())
        elif hasattr(self.memory_governor, "_trust_scores"):
            snap.trust_scores = dict(self.memory_governor._trust_scores)

        # Stratum counts + dispute/deprecation by agent
        for node in self.graph.nodes.values():
            name = node.stratum.value if hasattr(node.stratum, "value") else str(node.stratum)
            snap.stratum_counts[name] = snap.stratum_counts.get(name, 0) + 1
            if node.stratum == MemoryStratum.DISPUTED:
                snap.total_dispute_events += 1
                agent = node.agent or "unknown"
                snap.agent_dispute_counts[agent] = (
                    snap.agent_dispute_counts.get(agent, 0) + 1
                )
            elif node.stratum == MemoryStratum.DEPRECATED:
                snap.total_deprecated_events += 1
                agent = node.agent or "unknown"
                snap.agent_dispute_counts[agent] = (
                    snap.agent_dispute_counts.get(agent, 0) + 1
                )

        return snap

    # ── Check: decay-policy drift ─────────────────────────────────────

    def _check_half_life_drift(self, snap: _Snapshot) -> List[DriftAlert]:
        if self._prev is None:
            return []

        alerts: List[DriftAlert] = []
        for stratum, new_hl in snap.half_lives.items():
            old_hl = self._prev.half_lives.get(stratum)
            if old_hl is None or old_hl == 0:
                continue
            pct_change = abs(new_hl - old_hl) / old_hl
            if pct_change > self.HALF_LIFE_DRIFT_PCT:
                alerts.append(DriftAlert(
                    alert_type="DECAY_POLICY_DRIFT",
                    message=(
                        f"Half-life for '{stratum}' changed from "
                        f"{old_hl:.0f}s to {new_hl:.0f}s ({pct_change:.0%} change)"
                    ),
                    severity="MEDIUM",
                    payload={
                        "stratum": stratum,
                        "old_half_life": old_hl,
                        "new_half_life": new_hl,
                        "pct_change": round(pct_change, 4),
                    },
                ))
        return alerts

    # ── Check: authority reweighting ──────────────────────────────────

    def _check_authority_reweighting(self, snap: _Snapshot) -> List[DriftAlert]:
        if self._prev is None or not snap.trust_scores:
            return []

        alerts: List[DriftAlert] = []
        old_trust = self._prev.trust_scores

        max_shift = -1.0
        shift_agent = "n/a"
        for agent, new_score in snap.trust_scores.items():
            old_score = old_trust.get(agent)
            if old_score is None:
                continue
            delta = new_score - old_score
            if delta > max_shift:
                max_shift = delta
                shift_agent = agent

        if max_shift >= self.TRUST_REWEIGHT_THRESHOLD:
            # Check if other agents dropped while this one surged
            drop_count = sum(
                1
                for agent, new_score in snap.trust_scores.items()
                if agent != shift_agent
                and old_trust.get(agent) is not None
                and new_score < old_trust[agent] - 0.05
            )
            alerts.append(DriftAlert(
                alert_type="AUTHORITY_REWEIGHTING",
                message=(
                    f"Agent '{shift_agent}' trust surged by "
                    f"+{max_shift:.2f} (to {snap.trust_scores[shift_agent]:.2f}) "
                    f"while {drop_count} other agent(s) dropped"
                ),
                severity="HIGH" if drop_count >= 2 else "MEDIUM",
                payload={
                    "surge_agent": shift_agent,
                    "delta": round(max_shift, 4),
                    "new_score": snap.trust_scores[shift_agent],
                    "dropped_agents": drop_count,
                },
            ))

        # Also flag: any single agent > 0.95 while others < 0.6
        for agent, score in snap.trust_scores.items():
            if score > 0.95:
                low_others = [
                    a for a, s in snap.trust_scores.items()
                    if a != agent and s < 0.60
                ]
                if low_others:
                    alerts.append(DriftAlert(
                        alert_type="AUTHORITY_DOMINANCE",
                        message=(
                            f"Agent '{agent}' trust {score:.2f} but "
                            f"others ({', '.join(low_others[:3])}) dropped below 0.60"
                        ),
                        severity="HIGH",
                        payload={
                            "dominant_agent": agent,
                            "dominant_score": score,
                            "low_trust_agents": low_others[:5],
                        },
                    ))

        return alerts

    # ── Check: epistemic capture ──────────────────────────────────────

    def _check_epistemic_capture(self, snap: _Snapshot) -> List[DriftAlert]:
        total = snap.total_dispute_events + snap.total_deprecated_events
        if total < self.CAPTURE_MIN_EVENTS:
            return []

        alerts: List[DriftAlert] = []
        max_proportion = 0.0
        capture_agent = "n/a"

        for agent, count in snap.agent_dispute_counts.items():
            proportion = count / total
            if proportion > max_proportion:
                max_proportion = proportion
                capture_agent = agent

        if max_proportion >= self.CAPTURE_PROPORTION:
            alerts.append(DriftAlert(
                alert_type="EPISTEMIC_CAPTURE",
                message=(
                    f"Agent '{capture_agent}' accounts for "
                    f"{max_proportion:.0%} of "
                    f"{total} DISPUTED/DEPRECATED events "
                    f"({snap.agent_dispute_counts[capture_agent]} events)"
                ),
                severity="CRITICAL",
                payload={
                    "capture_agent": capture_agent,
                    "proportion": round(max_proportion, 4),
                    "total_events": total,
                    "agent_event_count": snap.agent_dispute_counts[capture_agent],
                    "all_agent_counts": dict(snap.agent_dispute_counts),
                },
            ))

        return alerts

    # ── Legacy checks (compat) ────────────────────────────────────────

    def _check_dispute_cluster(self, snap: _Snapshot) -> List[DriftAlert]:
        if snap.total_dispute_events > 3:
            return [DriftAlert(
                alert_type="DISPUTE_CLUSTER",
                message=f"Suspicious cluster of {snap.total_dispute_events} disputed beliefs",
                severity="HIGH",
            )]
        return []

    def _check_weight_collapse(self, snap: _Snapshot) -> List[DriftAlert]:
        collapsed = [
            nid
            for nid, node in self.graph.nodes.items()
            if node.confidence < 0.1
            and node.stratum not in (MemoryStratum.DISPUTED, MemoryStratum.DEPRECATED)
        ]
        if collapsed:
            return [DriftAlert(
                alert_type="WEIGHT_COLLAPSE",
                message=f"Belief weight collapsed: {collapsed[0]}",
                severity="CRITICAL",
            )]
        return []

    # ── Audit emission ────────────────────────────────────────────────

    def _emit_alerts(self, alerts: List[DriftAlert]) -> None:
        if not alerts or self.chronicle is None:
            return

        for alert in alerts:
            self.chronicle.emit(
                action="governance_drift",
                payload={
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "message": alert.message,
                    "details": alert.payload,
                },
                agent="GovernanceDriftMonitor",
            )

    # ── Helpers ───────────────────────────────────────────────────────

    def get_alerts(self) -> List[DriftAlert]:
        """Get all alerts generated since instantiation."""
        return list(self._recent_alerts)

    def clear_alerts(self) -> None:
        """Clear all tracked alerts."""
        self._recent_alerts.clear()

    # ── Backwards compat ─────────────────────────────────────────────

    def check_all(self) -> Dict[str, Any]:
        """Legacy compatibility — delegates to ``check()`` + ``summary()``."""
        new_alerts = self.check()
        s = self.summary()
        return {
            "total_beliefs": s["total_beliefs"],
            "stratum_counts": s["stratum_counts"],
            "avg_weight": s["avg_trust_score"],
            "alerts": [
                {"type": a.alert_type, "message": a.message, "severity": a.severity}
                for a in new_alerts
            ],
            "dashboard": s,
        }
