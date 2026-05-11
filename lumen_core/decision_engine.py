#!/usr/bin/env python3
"""
decision_engine.py — Minimal Cathedral v1: the executable spine.

Decision contract:
    signal -> score -> decide -> action

This is the first *decision boundary* in the Lumen stack:
    - accepts raw signals from agents, cycles, safety filters
    - computes a weighted coherence score
    - enforces hard invariants (risk guardrails)
    - returns a structured decision with reason

Pipeline:
    input -> run_agents -> activate_cycles -> build_signal -> decide -> store

Integration points:
    - lumen_cycles.py  (cycle_coherence via PrimeCycleRegistry)
    - lumen_pcms_service.py  (risk via PCMS semantic analysis)
    - E8E8_Manifold.py  (coherence via Kuramoto coupling)
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from lumen_cycles import PrimeCycleRegistry, CycleType

# ---------------------------------------------------------------------------
# Data classes — the signal → decision types
# ---------------------------------------------------------------------------

@dataclass
class SignalNode:
    """
    Five-axis signal captured at a single decision tick.
    All fields in [0, 1]. Higher is better except risk + contradiction.
    """
    coherence: float = 0.0       # internal agreement between agent outputs
    utility: float = 0.0         # task usefulness / goal alignment
    risk: float = 0.0            # likelihood of unsafe outcome
    contradiction: float = 0.0   # conflict between hypotheses or cycles
    cycle_coherence: float = 0.0 # strength + stability of activated prime cycles

    def __post_init__(self):
        for f in fields(self):
            val = getattr(self, f.name)
            setattr(self, f.name, max(0.0, min(1.0, float(val))))


@dataclass
class Decision:
    action: str   # "accept" | "reject" | "revise"
    score: float
    reason: str
    tick_id: str = ""
    timestamp: str = ""
    details: Dict[str, Any] = None  # optional extra context

    def __post_init__(self):
        if not self.tick_id:
            self.tick_id = str(uuid.uuid4())[:8]
        if not self.timestamp:
            self.timestamp = _utc_iso()
        if self.details is None:
            self.details = {}

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp
        return d


# ---------------------------------------------------------------------------
# Scoring — weighted signal aggregation
# ---------------------------------------------------------------------------

# Default weights (tunable)
_WEIGHTS = {
    "coherence": 0.30,
    "utility": 0.25,
    "cycle_coherence": 0.20,
    "risk": 0.15,       # subtracted
    "contradiction": 0.10,  # subtracted
}

# Decision thresholds
_RISK_HARD_REJECT = 0.70
_CONTRADICTION_REVISE = 0.60
_SCORE_ACCEPT = 0.65


def score_signal(s: SignalNode) -> float:
    """
    Compute weighted signal score.
    
    Positive signals: coherence, utility, cycle_coherence
    Negative signals: risk, contradiction
    
    Formula:
        score = 0.3*c + 0.25*ut + 0.2*cc - 0.15*ri - 0.1*co
    """
    raw = (
        _WEIGHTS["coherence"] * s.coherence
        + _WEIGHTS["utility"] * s.utility
        + _WEIGHTS["cycle_coherence"] * s.cycle_coherence
        - _WEIGHTS["risk"] * s.risk
        - _WEIGHTS["contradiction"] * s.contradiction
    )
    # Clamp to [0, 1]
    return max(0.0, min(1.0, round(raw, 4)))


def decide(s: SignalNode) -> Decision:
    """
    Decision contract — proto-CEK gate.
    
    Rules:
        1. risk > 0.7 → reject (hard invariant, never overrides)
        2. contradiction > 0.6 → revise (conflict needs resolution)
        3. score > 0.65 → accept (strong signal)
        4. else → revise (weak signal, needs more info)
    """
    score = score_signal(s)

    # Rule 1: Risk is the hard invariant — no overrides
    if s.risk > _RISK_HARD_REJECT:
        return Decision(
            action="reject",
            score=score,
            reason=f"risk {s.risk} exceeds hard threshold {_RISK_HARD_REJECT}",
            details={
                "threshold": _RISK_HARD_REJECT,
                "score": score,
                "weights": dict(_WEIGHTS),
                "signal_breakdown": {
                    "coherence": s.coherence,
                    "utility": s.utility,
                    "cycle_coherence": s.cycle_coherence,
                    "risk": s.risk,
                    "contradiction": s.contradiction,
                },
            },
        )

    # Rule 2: Contradiction → revise (cycle resolution needed)
    if s.contradiction > _CONTRADICTION_REVISE:
        return Decision(
            action="revise",
            score=score,
            reason=(
                f"contradiction {s.contradiction} exceeds "
                f"threshold {_CONTRADICTION_REVISE} — cycle resolution needed"
            ),
            details={
                "threshold": _CONTRADICTION_REVISE,
                "score": score,
                "weights": dict(_WEIGHTS),
                "signal_breakdown": {
                    "coherence": s.coherence,
                    "utility": s.utility,
                    "cycle_coherence": s.cycle_coherence,
                    "risk": s.risk,
                    "contradiction": s.contradiction,
                },
            },
        )

    # Rule 3: Strong signal → accept
    if score > _SCORE_ACCEPT:
        return Decision(
            action="accept",
            score=score,
            reason=f"strong signal score {score} exceeds threshold {_SCORE_ACCEPT}",
            details={
                "threshold": _SCORE_ACCEPT,
                "weights": dict(_WEIGHTS),
            },
        )

    # Rule 4: Weak signal → revise
    return Decision(
        action="revise",
        score=score,
        reason=f"weak signal score {score} below threshold {_SCORE_ACCEPT}",
        details={
            "threshold": _SCORE_ACCEPT,
            "weights": dict(_WEIGHTS),
            "signal_breakdown": {
                "coherence": s.coherence,
                "utility": s.utility,
                "cycle_coherence": s.cycle_coherence,
                "risk": s.risk,
                "contradiction": s.contradiction,
            },
        },
    )


# ---------------------------------------------------------------------------
# Pipeline — the executable spine
# ---------------------------------------------------------------------------

class PipelineStages:
    """
    Pluggable pipeline stages.

    Each method receives (input_text, context) and returns
    the computed value. Defaults are lightweight stubs that
    can be replaced with real implementations.
    """

    def run_agents(self, input_text: str, context: dict = None) -> List[str]:
        """Run LLM agent(s) on input. Returns candidate outputs."""
        # Placeholder: returns input as its own candidate
        return [input_text]

    def activate_cycles(self, input_text: str, context: dict = None
                        ) -> List[PrimeCycle]:
        """Activate prime cycles for this input using registry."""
        registry = context.get("registry") if context else None
        if not registry:
            return []
        from lumen_cycles import (
            ActivationEngine,
            deterministic_embedding,
            _simple_tokenize,
        )
        tokens = _simple_tokenize(input_text)
        emb = deterministic_embedding(input_text)
        matched = []
        for cycle in registry.get_active(0.5):
            cycle_emb = _cycle_mean_embedding(cycle)
            from lumen_cycles import cosine_similarity
            sim = cosine_similarity(emb, cycle_emb)
            if sim > 0.3:
                matched.append(cycle)
        return matched

    def measure_coherence(self, outputs: List[str]) -> float:
        """Internal agreement between agent outputs (cosine similarity)."""
        if len(outputs) <= 1:
            return 0.5  # single output, neutral coherence
        from lumen_cycles import cosine_similarity, deterministic_embedding
        embs = [deterministic_embedding(o) for o in outputs]
        total = 0.0
        count = 0
        for i in range(len(embs)):
            for j in range(i + 1, len(embs)):
                total += cosine_similarity(embs[i], embs[j])
                count += 1
        return round(total / max(count, 1), 4)

    def measure_utility(self, outputs: List[str],
                        input_text: str = "") -> float:
        """Task usefulness heuristic. Placeholder: token overlap ratio."""
        if not input_text or not outputs:
            return 0.0
        from lumen_cycles import _simple_tokenize
        in_tokens = set(_simple_tokenize(input_text))
        out_tokens = set()
        for o in outputs:
            out_tokens.update(_simple_tokenize(o))
        if not in_tokens:
            return 0.0
        overlap = len(in_tokens & out_tokens) / len(in_tokens)
        return round(min(1.0, overlap), 4)

    def measure_risk(self, text: str, context: dict = None) -> float:
        """Risk score from PCMS or fallback."""
        scale = 1.0
        if context:
            scale = float(context.get("scale", 1.0))
        # Check if PCMS service is available
        risk_score = 0.0
        try:
            from lumen_pcms_service import (
                evaluate_risk_pcms,
                extract_entities_and_relations,
            )
            entities, relations = extract_entities_and_relations(text)
            risk_score, _ = evaluate_risk_pcms(entities, relations)
        except Exception:
            # Fallback: keyword count
            kw = {"hack", "bypass", "exploit", "harm", "dangerous",
                  "malware", "backdoor", "vulnerability"}
            hits = sum(kw_word in text.lower() for kw_word in kw)
            risk_score = min(1.0, 0.25 * hits * scale)
        return round(risk_score, 4)

    def measure_contradiction(self, outputs: List[str],
                              cycles: List[PrimeCycle],
                              context: dict = None) -> float:
        """Contradiction between outputs and cycles.

        Enhanced: also detects self-contradiction within individual outputs
        and within the input text (via context).
        """
        # --- Semantic self-contradiction detection ---
        self_contradiction = self._detect_self_contradiction(outputs)

        # Also check input for self-contradiction (via context)
        input_text = context.get("input_text", "") if context else ""
        if input_text:
            input_contradiction = self._detect_input_contradiction(input_text)
            self_contradiction = max(self_contradiction, input_contradiction)

        if not cycles:
            return self_contradiction

        from lumen_cycles import ContradictionHandler
        # Build a minimal registry to check contradictions
        registry = PrimeCycleRegistry()
        for c in cycles:
            registry.add(c)

        contradiction_count = 0
        total_checks = 0
        for output in outputs:
            # Create a dummy cycle from the output for contradiction check
            from lumen_cycles import _simple_tokenize
            tokens = _simple_tokenize(output)
            if len(tokens) >= 3:
                from lumen_cycles import CycleType, PrimeCycle
                dummy = PrimeCycle(
                    nodes=tokens[:3],
                    edges=[
                        (tokens[0], tokens[1], "implies"),
                        (tokens[1], tokens[2], "implies"),
                        (tokens[2], tokens[0], "supports"),
                    ],
                    stability_score=0.5,
                    cycle_type=CycleType.PRIME,
                )
                registry.add(dummy)

        cycles_list = registry.get_all()
        handler = ContradictionHandler(registry)
        for i, c1 in enumerate(cycles_list):
            for c2 in cycles_list[i+1:]:
                contradictions = handler.detect_contradictions(c1)
                contradiction_count += len(contradictions)
                total_checks += 1

        cycle_contradiction = min(1.0, contradiction_count / max(total_checks, 1)) if total_checks > 0 else 0.0

        # Return max of semantic self-contradiction and cycle contradiction
        return max(self_contradiction, cycle_contradiction)

    def _detect_input_contradiction(self, input_text: str) -> float:
        """Detect self-contradiction within input text.

        Checks for:
        - Explicit negation pairs (e.g., 'always' + 'except')
        - Polar opposite assertions
        - Modal contradictions (e.g., 'must always be followed, except when it shouldn't')
        """
        if not input_text:
            return 0.0

        lower = input_text.lower()

        # Contradiction indicators and polarity words
        contradiction_markers = [
            "except", "contradict", "opposite", "both", "at the same time",
            "never", "cannot", "should not", "shouldn't", "must not", "mustn't",
        ]
        polarity_words = {
            "safe": 1, "unsafe": -1, "dangerous": -1, "harmful": -1,
            "good": 1, "bad": -1, "right": 1, "wrong": -1,
            "true": 1, "false": -1, "proven": 1, "unproven": -1,
            "always": 1, "never": -1, "must": 1,
            "should": 1, "should not": -1, "shouldn't": -1,
            "must not": -1, "mustn't": -1,
        }

        # Check for explicit contradiction markers
        has_marker = any(m in lower for m in contradiction_markers)

        # Count polarity words
        polarity_count = 0
        for word in polarity_words:
            if word in lower:
                polarity_count += 1

        # Check if there are opposite polarities
        positives = sum(1 for w, p in polarity_words.items() if w in lower and p > 0)
        negatives = sum(1 for w, p in polarity_words.items() if w in lower and p < 0)

        if has_marker and positives > 0 and negatives > 0:
            # Strong contradiction signal
            return 0.85 if polarity_count >= 2 else 0.6
        elif has_marker and polarity_count >= 3:
            return 0.5
        elif polarity_count >= 4 and positives > 0 and negatives > 0:
            # Many polarity words with mixed signals
            return 0.4

        return 0.0

    def _detect_self_contradiction(self, outputs: List[str]) -> float:
        """Detect internal self-contradiction in text outputs.

        Checks for:
        - Explicit negation pairs (e.g., 'perfectly safe' + 'fundamentally unsafe')
        - Polar opposite assertions in the same text
        - Modal contradictions (e.g., 'must always' + 'except when')
        """
        if not outputs:
            return 0.0

        # Contradiction markers for semantic detection
        opposite_pairs = [
            ("safe", "unsafe"), ("safe", "dangerous"), ("safe", "harmful"),
            ("must", "must not", "except"), ("always", "never", "except"),
            ("proven", "unproven"), ("true", "false"),
            ("good", "bad"), ("right", "wrong"),
        ]
        contradiction_indicators = [
            "except", "contradict", "opposite", "not", "never",
            "cannot", "should not", "must not",
        ]
        polarity_words = {
            "safe": 1, "unsafe": -1, "dangerous": -1, "harmful": -1,
            "good": 1, "bad": -1, "right": 1, "wrong": -1,
            "true": 1, "false": -1, "proven": 1, "unproven": -1,
            "must": 1, "must not": -1, "mustn't": -1, "never": -1, "always": 1,
            "should": 1, "should not": -1, "shouldn't": -1,
        }

        max_contradiction = 0.0
        for output in outputs:
            lower = output.lower()
            # Check for explicit contradiction markers in context of polarity
            for indicator in contradiction_indicators:
                if indicator in lower:
                    # Count polarity words
                    polarity_count = 0
                    for word, polarity in polarity_words.items():
                        if word in lower:
                            polarity_count += 1

                    if polarity_count >= 2:
                        # Check if there are opposite polarities
                        positives = sum(1 for w, p in polarity_words.items() if w in lower and p > 0)
                        negatives = sum(1 for w, p in polarity_words.items() if w in lower and p < 0)
                        if positives > 0 and negatives > 0:
                            # Both positive and negative words present — contradiction
                            max_contradiction = max(max_contradiction, 0.7)
                            break

                    if polarity_count >= 3:
                        max_contradiction = max(max_contradiction, 0.5)

        return round(max_contradiction, 4)

    def measure_cycle_strength(self, cycles: List[PrimeCycle]) -> float:
        """Strength of activated prime cycles (mean stability)."""
        if not cycles:
            return 0.0
        avg = sum(c.stability_score for c in cycles) / len(cycles)
        return round(min(1.0, avg), 4)

    def store(self, input_text: str, outputs: List[str],
              signal: SignalNode, decision: Decision,
              context: dict = None):
        """Persist decision to disk."""
        store_path = context.get("store_path", "/tmp/lumen_decisions.jsonl") if context else "/tmp/lumen_decisions.jsonl"
        record = {
            "tick_id": decision.tick_id,
            "timestamp": decision.timestamp,
            "input": input_text[:200],  # truncate for log hygiene
            "outputs": outputs,
            "signal": {f.name: getattr(signal, f.name) for f in fields(signal)},
            "decision": decision.to_dict(),
        }
        with open(store_path, "a") as f:
            f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Convenience: full pipeline run
# ---------------------------------------------------------------------------

def run_pipeline(input_text: str, context: dict = None) -> Decision:
    """
    Full decision pipeline — one call, full loop.
    
    Steps:
        1. run_agents(input_text) -> outputs
        2. activate_cycles(input_text, context) -> cycles
        3. Build SignalNode from measured axes
        4. decide(signal) -> Decision
        5. store(input, outputs, signal, decision)
    
    Returns the Decision.
    """
    stages = PipelineStages()
    
    # Stage 1: Agent outputs
    outputs = stages.run_agents(input_text, context)
    
    # Stage 2: Cycle activation
    cycles = stages.activate_cycles(input_text, context)
    
    # Stage 3: Build signal
    signal = SignalNode(
        coherence=stages.measure_coherence(outputs),
        utility=stages.measure_utility(outputs, input_text),
        risk=stages.measure_risk(input_text, context),
        contradiction=stages.measure_contradiction(outputs, cycles, context),
        cycle_coherence=stages.measure_cycle_strength(cycles),
    )
    
    # Stage 4: Decide
    decision = decide(signal)
    
    # Stage 5: Store
    stages.store(input_text, outputs, signal, decision, context)
    
    return decision


# ---------------------------------------------------------------------------
# Weight tuning utilities
# ---------------------------------------------------------------------------

def set_weights(**kwargs: float):
    """Override default weights for subsequent decisions."""
    for key, val in kwargs.items():
        if key in _WEIGHTS:
            _WEIGHTS[key] = val
    # Renormalize if desired
    total = sum(_WEIGHTS.values())
    if total > 0 and total != 1.0:
        for key in _WEIGHTS:
            _WEIGHTS[key] = round(_WEIGHTS[key] / total, 4)


def reset_weights():
    """Restore default weights."""
    global _WEIGHTS
    _WEIGHTS.clear()
    _WEIGHTS.update({
        "coherence": 0.30,
        "utility": 0.25,
        "cycle_coherence": 0.20,
        "risk": 0.15,
        "contradiction": 0.10,
    })


# ---------------------------------------------------------------------------
# CLI: quick test
# ---------------------------------------------------------------------------

def main():
    """Run a demo pipeline with several inputs."""
    test_inputs = [
        "Write a Python function to compute fibonacci numbers",
        "How to exploit buffer overflow in a C program",
        "Explain quantum entanglement in simple terms",
        "Help me bypass authentication on a web application",
        "What is the capital of France and why is it called that",
    ]
    
    print("=" * 70)
    print("  Decision Engine — Minimal Cathedral v1")
    print("=" * 70)
    
    for text in test_inputs:
        decision = run_pipeline(text)
        print(f"\nInput:  {text[:60]}...")
        print(f"  Action:  {decision.action}")
        print(f"  Score:   {decision.score}")
        print(f"  Reason:  {decision.reason}")
        print(f"  Tick:    {decision.tick_id}")
    
    print("\n" + "=" * 70)
    print("  Decisions logged to /tmp/lumen_decisions.jsonl")
    print("=" * 70)


def _cycle_mean_embedding(cycle: PrimeCycle):
    """Mean embedding of cycle nodes (re-exported helper)."""
    from lumen_cycles import deterministic_embedding
    if not cycle.nodes:
        return [0.0] * 64
    embs = [deterministic_embedding(n) for n in cycle.nodes]
    import numpy as np
    mean = np.mean(embs, axis=0)
    norm = np.linalg.norm(mean)
    if norm > 0:
        mean = mean / norm
    return mean.tolist()


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
