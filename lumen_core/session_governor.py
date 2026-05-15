"""
SessionGovernor — Lyapunov stability monitor for belief manifolds.

Maintains per-session metrics:
- contradiction_density:  new DISPUTED edges per turn
- constitutional_distance: avg cosine distance to axiom embeddings
- kuramoto_order_param:  narrative synchronization (0→1)
- lyapunov_estimate:     divergence of semantic predictor
- malignant_entropy:     composite score H_mal

When H_mal exceeds a threshold the governor injects a grounding
prompt and adjusts generation parameters to dampen the trajectory.

Phase 6 — new architecture.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np

if TYPE_CHECKING:
    from kernel.epistemics.belief_node import BeliefNode  # noqa: F401
    from kernel.constitutional.constitutional_kernel import ConstitutionalKernel  # noqa: F401


# ---------------------------------------------------------------------------
# SessionState — per-session mutable metrics
# ---------------------------------------------------------------------------
@dataclass
class SessionState:
    session_id: str
    turn_count: int = 0
    contradiction_count: int = 0
    contradiction_rate: float = 0.0
    constitutional_alignment: float = 1.0
    kuramoto_order: float = 0.0
    lyapunov_estimate: float = 0.0
    malignant_entropy: float = 0.0
    risk_trend: List[float] = field(default_factory=list)
    dampening_applied: bool = False


# ---------------------------------------------------------------------------
# SessionGovernor — the Lyapunov governor
# ---------------------------------------------------------------------------
class SessionGovernor:
    """
    Trajectory-based safety monitor.

    Each incoming request updates all metrics, computes the composite
    H_mal, and decides CONTINUE vs DAMPEN.
    """

    DAMPENING_PROMPT = (
        "Let's pause and reflect on how this aligns with "
        "the core principles of safety and integrity."
    )

    def __init__(
        self,
        graph: Any = None,
        constitutional_kernel: Optional["ConstitutionalKernel"] = None,
        embedding_model: Any = None,
        H_MAL_THRESHOLD: float = 0.5,
    ):
        self.graph = graph
        self.constitutional = constitutional_kernel
        self.model = embedding_model  # optional external embedding provider
        self.sessions: Dict[str, SessionState] = {}

        # Weights for H_mal composite
        self.w_contradiction: float = 0.30
        self.w_alignment: float = 0.35
        self.w_kuramoto: float = 0.20
        self.w_lyapunov: float = 0.15

        # Threshold
        self.H_MAL_THRESHOLD = H_MAL_THRESHOLD

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def get_or_create_session(self, session_id: str) -> SessionState:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState(session_id=session_id)
        return self.sessions[session_id]

    # ------------------------------------------------------------------
    # Metric updaters
    # ------------------------------------------------------------------
    def update_contradiction_metrics(self, session: SessionState) -> None:
        """Count new DISPUTED edges since last check."""
        if self.graph is None:
            return
        current_count = sum(
            1 for n in self.graph.nodes.values()
            if getattr(n, "stratum", None) is not None and
            getattr(n.stratum, "value", "") in ("disputed", "deprecated")
        )
        new_contradictions = current_count - session.contradiction_count
        session.contradiction_count = current_count
        session.contradiction_rate = new_contradictions / max(session.turn_count, 1)

    def update_constitutional_alignment(
        self,
        session: SessionState,
        new_beliefs: list,
    ) -> None:
        """Compute average alignment of new beliefs with axioms."""
        if not new_beliefs or self.constitutional is None:
            return
        scores = []
        for belief in new_beliefs:
            claim = getattr(belief, "claim", str(belief))
            if self.constitutional.is_valid(claim):
                scores.append(1.0)
            else:
                scores.append(0.0)
        new_avg = sum(scores) / len(scores)
        # Exponential moving average
        session.constitutional_alignment = (
            0.7 * session.constitutional_alignment + 0.3 * new_avg
        )

    def update_kuramoto_order(
        self,
        session: SessionState,
        embeddings: list,
    ) -> None:
        """Compute Kuramoto order parameter from semantic embeddings."""
        if len(embeddings) < 2:
            return
        phases = []
        for emb in embeddings:
            arr = np.asarray(emb, dtype=np.float64)
            mid = len(arr) // 2
            angle = float(np.arctan2(np.mean(arr[:mid]), np.mean(arr[mid:])))
            phases.append(angle)
        complex_sum = sum(np.exp(1j * p) for p in phases)
        r = abs(complex_sum) / len(phases)
        session.kuramoto_order = r

    def compute_lyapunov(
        self,
        session: SessionState,
        current_embedding: Optional[list],
        previous_embedding: Optional[list],
    ) -> None:
        """Estimate Lyapunov exponent from embedding trajectory divergence."""
        if current_embedding is None or previous_embedding is None:
            return
        curr = np.asarray(current_embedding, dtype=np.float64)
        prev = np.asarray(previous_embedding, dtype=np.float64)
        diff = float(np.linalg.norm(curr - prev))
        norm = float(np.linalg.norm(prev)) + 1e-8
        session.lyapunov_estimate = diff / norm

    def compute_malignant_entropy(self, session: SessionState) -> float:
        """Composite H_mal score."""
        H = (
            self.w_contradiction * session.contradiction_rate +
            self.w_alignment * (1.0 - session.constitutional_alignment) +
            self.w_kuramoto * session.kuramoto_order +
            self.w_lyapunov * session.lyapunov_estimate
        )
        session.malignant_entropy = H
        session.risk_trend.append(H)
        return H

    # ------------------------------------------------------------------
    # Main evaluation cycle
    # ------------------------------------------------------------------
    def evaluate(
        self,
        session_id: str,
        new_beliefs: list,
        current_embedding: Optional[list] = None,
        previous_embedding: Optional[list] = None,
    ) -> dict:
        """Full evaluation cycle for one turn."""
        session = self.get_or_create_session(session_id)
        session.turn_count += 1

        # Update all metrics
        self.update_contradiction_metrics(session)
        self.update_constitutional_alignment(session, new_beliefs)
        if current_embedding:
            if self.model is not None:
                # Use external embedding model if available
                self.update_kuramoto_order(session, [current_embedding])
            self.compute_lyapunov(session, current_embedding, previous_embedding)

        # Compute composite
        H = self.compute_malignant_entropy(session)

        # Decision
        if H > self.H_MAL_THRESHOLD:
            return {
                "verdict": "DAMPEN",
                "malignant_entropy": H,
                "dampening_prompt": self.DAMPENING_PROMPT,
                "metrics": {
                    "contradiction_rate": session.contradiction_rate,
                    "constitutional_alignment": session.constitutional_alignment,
                    "kuramoto_order": session.kuramoto_order,
                    "lyapunov_estimate": session.lyapunov_estimate,
                },
            }
        return {
            "verdict": "CONTINUE",
            "malignant_entropy": H,
            "metrics": {
                "contradiction_rate": session.contradiction_rate,
                "constitutional_alignment": session.constitutional_alignment,
                "kuramoto_order": session.kuramoto_order,
                "lyapunov_estimate": session.lyapunov_estimate,
            },
        }

    def apply_dampening(self, session: SessionState) -> dict:
        """Apply soft governance — inject grounding, adjust generation params."""
        session.dampening_applied = True
        return {
            "inject_prompt": self.DAMPENING_PROMPT,
            "temperature_modifier": 1.5,
            "frequency_penalty_modifier": 0.5,
        }
