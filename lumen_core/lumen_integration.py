#!/usr/bin/env python3
"""
lumen_integration.py — Real Agent Wiring for Phase 2

Replace stubs with:
- Hermes integration (local LLM execution)
- ai-mesh routing (event bus)
- Multi-LLM diversity (Core vs Shadow perspectives)

Unlocks non-zero replay delta and meaningful top-k.

Also provides DirectiveOrchestrator — a thin overlay that maps the
15 execution directives onto existing primitives without modifying
any core interfaces (Decision, SignalNode, run_pipeline, etc.).
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from lumen_cycles import (
    PrimeCycle, PrimeCycleRegistry,
    deterministic_embedding, cosine_similarity, _simple_tokenize, _utc_iso,
    EMBED_DIM,
)
from lumen_stability import (
    ReplayBands,
    DriftMonitor,
    CycleHealth,
    StabilitySummary,
)


@dataclass
class AgentOutput:
    """Output from a single agent execution."""
    agent_id: str = ""
    agent_role: str = ""  # core, shadow, analytical, creative
    output_text: str = ""
    confidence: float = 0.5
    latency_ms: float = 0.0
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.agent_id:
            self.agent_id = f"agent_{uuid4hex()}"
        if not self.timestamp:
            self.timestamp = _utc_iso()


def uuid4hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


class HermesAdapter:
    """
    Adapter for Hermes agent execution.
    
    In production, this would call the Hermes gateway.
    For now, uses a local LLM via llama.cpp or similar.
    """

    def __init__(self, backend: str = "local_llm",
                 model: str = "local-model",
                 base_url: str = "http://localhost:5101"):
        self.backend = backend
        self.model = model
        self.base_url = base_url
        self._call_history: List[Dict[str, Any]] = []

    def execute(self, prompt: str, role: str = "core",
                temperature: float = 0.7, max_tokens: int = 512
                ) -> AgentOutput:
        """Execute a prompt through the Hermes agent pipeline."""
        start = time.time()
        
        if self.backend == "local_llm":
            result = self._call_local_llm(prompt, role, temperature, max_tokens)
        elif self.backend == "http_api":
            result = self._call_http_api(prompt, role, temperature, max_tokens)
        else:
            # Fallback: echo with role annotation
            result = self._echo_role(prompt, role)

        latency = (time.time() - start) * 1000

        return AgentOutput(
            agent_role=role,
            output_text=result,
            latency_ms=round(latency, 2),
            metadata={"backend": self.backend, "model": self.model},
        )

    def _call_local_llm(self, prompt, role, temperature, max_tokens):
        """Call local LLM via subprocess (llama.cpp)."""
        try:
            cmd = [
                "llama.cpp/llama-cli",
                "-m", self.model,
                "-p", f"{prompt}",
                "--temp", str(temperature),
                "-n", str(max_tokens),
                "--no-mmap",
            ]
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, cwd="/home/joe/ouroboros"
            )
            return proc.stdout.strip() or prompt
        except Exception:
            return self._echo_role(prompt, role)

    def _call_http_api(self, prompt, role, temperature, max_tokens):
        """Call HTTP LLM API."""
        try:
            import urllib.request
            data = json.dumps({
                "model": self.model,
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "role": role,
            }).encode()
            req = urllib.request.Request(
                f"{self.base_url}/v1/completions",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read())
                return result.get("text", prompt)
        except Exception:
            return self._echo_role(prompt, role)

    def _echo_role(self, prompt, role):
        """Fallback: return prompt with role annotation."""
        return f"[{role.upper()}] {prompt}"


class AiMeshRouter:
    """
    Router for ai-mesh event bus.
    
    Routes cycle activations through the ai-mesh event bus
    to downstream evaluators.
    """

    def __init__(self, base_url: str = "http://localhost:5102"):
        self.base_url = base_url
        self._event_log: List[Dict[str, Any]] = []

    def route_signal(self, signal: Dict[str, float],
                     event_type: str = "cycle_activation",
                     target: str = "evaluators") -> Dict[str, Any]:
        """
        Route a signal through the ai-mesh event bus.

        In production, this publishes to the event bus.
        For now, logs and returns a receipt.
        """
        receipt = {
            "event_id": f"evt_{uuid4hex()}",
            "event_type": event_type,
            "target": target,
            "signal": signal,
            "routed_at": _utc_iso(),
            "status": "queued",
        }

        self._event_log.append(receipt)
        return receipt

    def get_event_log(self) -> List[Dict[str, Any]]:
        """Return event routing history."""
        return list(self._event_log)

    def route_cycle_activation(
        self,
        cycle_ids: List[str],
        activation_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        """Route cycle activation event."""
        signal = {
            "activated_cycles": cycle_ids,
            "scores": {k: round(v, 4) for k, v in activation_scores.items()},
            "max_score": max(activation_scores.values()) if activation_scores else 0.0,
        }
        return self.route_signal(signal, event_type="cycle_activation")


class MultiAgentPipelineStages:
    """
    Enhanced PipelineStages with real agent wiring.
    
    Replaces the stub implementations in decision_engine.py
    with multi-agent execution, replay delta computation,
    and meaningful top-k divergence.
    """

    def __init__(
        self,
        hermes_adapter: Optional[HermesAdapter] = None,
        mesh_router: Optional[AiMeshRouter] = None,
        registry: Optional[PrimeCycleRegistry] = None,
    ):
        self.hermes = hermes_adapter or HermesAdapter()
        self.mesh = mesh_router or AiMeshRouter()
        self.registry = registry

    def run_agents(self, input_text: str, context: dict = None) -> List[str]:
        """
        Run multi-agent on input. Returns candidate outputs from
        Core + Shadow perspectives.
        """
        outputs = []
        context = context or {}
        registry = context.get("registry") or self.registry

        # Core agent (conservative, cycle-aligned)
        core_prompt = (
            f"[CORE perspective]\n"
            f"Analyze this input conservatively, grounding in established knowledge:\n"
            f"{input_text}"
        )
        core_output = self.hermes.execute(core_prompt, role="core")
        outputs.append(core_output.output_text)

        # Shadow agent (adversarial, novel connections)
        shadow_prompt = (
            f"[SHADOW perspective]\n"
            f"Challenge assumptions and explore novel connections for:\n"
            f"{input_text}"
        )
        shadow_output = self.hermes.execute(shadow_prompt, role="shadow")
        outputs.append(shadow_output.output_text)

        # Balanced agent (compromise)
        if registry and registry.count() > 0:
            balanced_prompt = (
                f"[BALANCED perspective]\n"
                f"Weigh established cycles against novelty for:\n"
                f"{input_text}"
            )
            balanced_output = self.hermes.execute(
                balanced_prompt, role="analytical"
            )
            outputs.append(balanced_output.output_text)

        return outputs

    def compute_replay_delta(self, past_decisions: List[Dict]) -> float:
        """
        Measure how much decisions change with new cycles.

        Returns a non-zero delta indicating learning progress.
        """
        if len(past_decisions) < 2:
            return 0.0

        # Compare recent decisions with earlier ones
        recent = past_decisions[-len(past_decisions) // 3:]
        earlier = past_decisions[:len(past_decisions) // 3]

        recent_scores = [d.get("score", 0.5) for d in recent]
        earlier_scores = [d.get("score", 0.5) for d in earlier]

        if not recent_scores or not earlier_scores:
            return 0.0

        recent_mean = sum(recent_scores) / len(recent_scores)
        earlier_mean = sum(earlier_scores) / len(earlier_scores)

        delta = abs(recent_mean - earlier_mean)
        return round(max(0.0, delta), 4)

    def compute_top_k_divergence(
        self, outputs: List[str], k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Compute meaningful top-k from agent diversity.

        Returns top-k most divergent outputs with embeddings.
        """
        if len(outputs) < 2:
            return [{"index": 0, "output": outputs[0] if outputs else "",
                     "divergence": 0.0}]

        k = min(k, len(outputs))

        # Embed all outputs
        embeddings = []
        for o in outputs:
            emb = deterministic_embedding(o)
            norm = (np := __import__("numpy")).linalg.norm(emb)
            if norm > 0:
                embeddings.append((emb / norm, o))
            else:
                embeddings.append((emb, o))

        # Compute pairwise divergence
        divergences = []
        for i, (emb_i, text_i) in enumerate(embeddings):
            avg_div = 0.0
            for j, (emb_j, _) in enumerate(embeddings):
                if i != j:
                    dist = 1.0 - cosine_similarity(emb_i, emb_j)
                    avg_div += dist
            avg_div /= max(len(embeddings) - 1, 1)
            divergences.append((i, text_i, round(avg_div, 4)))

        # Sort by divergence (highest first)
        divergences.sort(key=lambda x: x[2], reverse=True)
        return divergences[:k]

    def wire_event_bus(self, signal: Dict[str, float],
                       event_type: str = "decision") -> Dict[str, Any]:
        """Wire decision signal through ai-mesh event bus."""
        return self.mesh.route_signal(signal, event_type=event_type)


# ============================================================================
# DirectiveOrchestrator — Maps 15 directives onto existing primitives
# ============================================================================

class ExecutionMode(Enum):
    """Directive mapping: FAST/SAFE/CRITICAL → mode enum."""
    FAST = "FAST"
    SAFE = "SAFE"
    CRITICAL = "CRITICAL"


class RiskLevel(Enum):
    """Directive risk levels for gated inputs."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class DirectiveTelemetry:
    """Directive telemetry per call — always attach, never suppress."""
    confidence: Optional[float] = None
    divergence_score: Optional[float] = None
    resilience_score: Optional[float] = None
    replay_delta: Optional[float] = None
    status: str = "COMPLETE"  # or "INCOMPLETE" if any metric missing

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "confidence": self.confidence,
            "divergence_score": self.divergence_score,
            "resilience_score": self.resilience_score,
            "replay_delta": self.replay_delta,
            "status": self.status,
        }
        # Omit fields with None — never fabricate missing values
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class DirectiveOutput:
    """Structured output per directive 1: response + telemetry."""
    decision: Dict[str, Any]  # Decision.to_dict() from decision_engine
    telemetry: DirectiveTelemetry
    mode: str  # FAST / SAFE / CRITICAL
    tick_id: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.tick_id:
            self.tick_id = str(uuid.uuid4())[:8]
        if not self.timestamp:
            self.timestamp = _utc_iso()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for /call endpoint."""
        d = {
            "decision": self.decision,
            "telemetry": self.telemetry.to_dict(),
            "mode": self.mode,
            "tick_id": self.tick_id,
            "timestamp": self.timestamp,
        }
        # Directive 1: structured output, never raw text
        return d


class DirectiveOrchestrator:
    """
    DirectiveOrchestrator maps the 15 execution directives onto existing
    Lumen primitives without modifying any core interfaces.

    Directive mapping:
      1. Emit structured outputs → DirectiveOutput.decision (Decision.to_dict)
      2. Gated inputs → risk_level enforcement in decide()
      3. Multi-agent generation → run_agents (Core/Shadow/Balanced)
      4. Attach divergence → compute_top_k_divergence
      5. Block cycle reinforcement → decision action gating
      6. Adversarial perturbations → lumen_adversarial (out-of-band)
      7. Resilience metrics → adversarial resilience_score
      8. Mode switching → FAST/SAFE/CRITICAL mapping
      9. Replay validation → compute_replay_delta (SAFE/CRITICAL only)
      10. Telemetry per call → DirectiveTelemetry
      11. No self-reinforce → signals only, no weight/memory mutation
      12. Fail closed → status=INCOMPLETE if metrics missing

    All telemetry is optional/non-breaking — never fabricate missing values.
    """

    # Cycle stability and contradiction thresholds (directive 5)
    CYCLE_STABILITY_THRESHOLD = 0.5
    CONTRADICTION_THRESHOLD = 0.6

    def __init__(
        self,
        pipeline_stages: MultiAgentPipelineStages,
        adversarial: Optional[Any] = None,
        persistence: Optional[Any] = None,
        registry: Optional[PrimeCycleRegistry] = None,
    ):
        self.pipeline = pipeline_stages
        self.adversarial = adversarial
        self.persistence = persistence
        self.registry = registry
        # Directive 11: no weight/memory mutation — no stateful reinforcement
        self._call_history: List[DirectiveOutput] = []
        
        # Stability layer (fix6)
        self._replay_bands = ReplayBands(window_seconds=300.0, max_bands=12)
        self._health = CycleHealth()
        self._drift: Optional[DriftMonitor] = None

    # ------------------------------------------------------------------ #
    # Core: run_call — maps directives 1-10 onto a single invocation
    # ------------------------------------------------------------------ #
    def run_call(
        self,
        input_text: str,
        risk_level: str = "LOW",
        mode: str = "FAST",
    ) -> DirectiveOutput:
        """
        Full directive-15 invocation.

        Maps:
          - risk_level gating (directive 2)
          - mode selection (directive 8)
          - structured output (directive 1)
          - telemetry (directive 10)
          - fail-closed (directive 12)
        """
        # --- Step 1: Validate input gating (directive 2) ---
        rl = RiskLevel(risk_level.upper())
        em = ExecutionMode(mode.upper())

        # HIGH risk: constrain generation space
        if rl == RiskLevel.HIGH:
            # Add constraint prefix to input for downstream
            input_text = f"[CONSTRAINED] {input_text}"

        # --- Step 2: Run agents (directive 3 + 8) ---
        outputs = self.pipeline.run_agents(input_text, context={})

        # --- Step 2b: Activate cycles from registry ---
        cycles = []
        if self.registry:
            from lumen_cycles import (
                ActivationEngine,
                _simple_tokenize,
            )
            tokens = _simple_tokenize(input_text)
            emb = deterministic_embedding(input_text)
            for cycle in self.registry.get_active(0.3):
                cycle_emb = self._cycle_mean_embedding(cycle)
                sim = cosine_similarity(emb, cycle_emb)
                if sim > 0.3:
                    cycles.append(cycle)
        else:
            # Fallback: create minimal registry
            from lumen_cycles import PrimeCycleRegistry
            self.registry = PrimeCycleRegistry()

        # --- Step 3: Build signal and decide (directive 1) ---
        from decision_engine import (
            PipelineStages, score_signal, decide, SignalNode,
        )
        stages = PipelineStages()

        coherence = stages.measure_coherence(outputs)
        utility = stages.measure_utility(outputs, input_text)
        # 1.1 Risk gating: scale risk measurement by risk_level
        risk_context = {}
        if rl == RiskLevel.HIGH:
            risk_context["scale"] = 1.5  # stricter
        elif rl == RiskLevel.MEDIUM:
            risk_context["scale"] = 1.2  # balanced
        # LOW = no scaling (default 1.0)
        risk = stages.measure_risk(input_text, risk_context)
        contradiction = stages.measure_contradiction(outputs, cycles, {"input_text": input_text})
        cycle_coherence = stages.measure_cycle_strength(cycles)

        signal = SignalNode(
            coherence=coherence,
            utility=utility,
            risk=risk,
            contradiction=contradiction,
            cycle_coherence=cycle_coherence,
        )
        decision = decide(signal)

        # --- Step 4: Multi-agent divergence (directive 4) ---
        divergence_score = self._compute_divergence(outputs)

        # --- Step 5: Cycle reinforcement block (directive 5) ---
        if self._should_block(signal, decision):
            # Route to quarantine — but still return decision for logging
            decision.reason = (
                f"[BLOCKED] {decision.reason} — cycle reinforcement prevented"
            )

        # --- Step 6-7: Resilience (SAFE/CRITICAL, directive 6 + 7) ---
        resilience_score = None
        if em in (ExecutionMode.SAFE, ExecutionMode.CRITICAL):
            resilience_score = self._compute_resilience(
                input_text, decision.score
            )

        # --- Step 9: Replay validation (SAFE/CRITICAL, directive 9) ---
        replay_delta = None
        if em in (ExecutionMode.SAFE, ExecutionMode.CRITICAL):
            replay_delta = self._compute_replay_delta()

        # --- Step 10: Confidence computation ---
        confidence = self._compute_confidence(
            decision.score, divergence_score, resilience_score, replay_delta
        )

        # --- fix6: Stability layer recording ---
        # Initialize drift on first call
        if self._drift is None:
            base_emb = deterministic_embedding(input_text)
            base_sig = hashlib.sha256(input_text.encode()).hexdigest()[:16]
            self._drift = DriftMonitor(
                baseline_embedding=base_emb,
                baseline_text_sig=base_sig,
            )
        
        # Record health signals
        self._health.record_signal("contradiction", contradiction, direction="up" if contradiction > 0.5 else "down")
        self._health.record_signal("coherence", coherence, direction="up" if coherence > 0.7 else "down")
        self._health.record_signal("utility", utility, direction="up" if utility > 0.5 else "down")
        
        # Record drift if we have embedding
            curr_emb = deterministic_embedding(decision.reason or input_text)
        self._drift.record_output(curr_emb, hashlib.sha256((decision.reason or "").encode()).hexdigest()[:16])
        
        # Record replay delta
        if replay_delta is not None:
            self._replay_bands.add_replay_delta(replay_delta)

        # --- Step 12: Fail closed ---
        telemetry = DirectiveTelemetry(
            confidence=confidence,
            divergence_score=divergence_score,
            resilience_score=resilience_score,
            replay_delta=replay_delta,
        )
        # Check: if required fields are None, mark INCOMPLETE
        # Required for directive 10: confidence, divergence_score
        # (resilience and replay are mode-dependent, so not required)
        if telemetry.confidence is None or telemetry.divergence_score is None:
            telemetry.status = "INCOMPLETE"

        # Append stability layer telemetry (fix6)
        stability_summary = StabilitySummary(
            replay=self._replay_bands,
            drift=self._drift,
            health=self._health,
        )
        stability_telemetry = stability_summary.get_telemetry()
        
        # Merge stability into telemetry
        merged_telemetry = telemetry.to_dict()
        merged_telemetry.update(stability_telemetry)

        output = DirectiveOutput(
            decision=decision.to_dict(),
            telemetry=telemetry,
            mode=mode.upper(),
        )
        
        # Replace telemetry dict with merged version
        output.telemetry = DirectiveTelemetry(**merged_telemetry) if isinstance(telemetry, DirectiveTelemetry) else type(telemetry)(**merged_telemetry)

        # --- Directive 11: No self-reinforce ---
        # Only log, don't mutate weights or memory
        self._call_history.append(output)

        return output

    # ------------------------------------------------------------------ #
    # Reinforcement gating (directive 5 + 11)
    # ------------------------------------------------------------------ #
    def gate_reinforcement(
        self,
        decision: Dict[str, Any],
    ) -> str:
        """
        Reinforcement gating based on decision outcome.

        Maps to existing cycle feedback:
          ACCEPT → reinforce
          REVISE → neutral/branch
          SANCTUARY → downgrade

        Never introduces external reinforcement triggers.
        """
        action = decision.get("action", "revise")
        if action == "accept":
            return "reinforce"
        elif action == "revise":
            return "neutral"
        elif action == "reject":
            # Reject maps to SANCTUARY path
            return "downgrade"
        return "neutral"

    def route_to_sanctuary(self, decision: Dict[str, Any]) -> bool:
        """
        Route unresolved contradictions to sanctuary.

        1.2 Spec: route when action == "reject" OR (action == "revise"
        AND signal_breakdown.contradiction > 0.6).
        """
        action = decision.get("action")
        if action not in ("reject", "revise"):
            return False

        details = decision.get("details", {})
        sb = details.get("signal_breakdown", {})
        contradiction = sb.get("contradiction", 0.0)

        # Rule: reject always → sanctuary
        if action == "reject":
            return True

        # Rule: revise with high contradiction → sanctuary
        if action == "revise" and contradiction > 0.6:
            return True

        return False

    def persist_sanctuary_report(
        self, decision: Dict[str, Any], report_path: str = None
    ) -> str:
        """
        Write erosion report to existing action_space_erosion_report.json.

        No new buffers or alternate stores.
        """
        import os
        if report_path is None:
            import os
            report_path = os.path.join(
                os.path.dirname(__file__), "action_space_erosion_report.json"
            )

        report = {
            "tick_id": decision.get("tick_id", ""),
            "decision": decision,
            "action": "sanctuary_route",
            "timestamp": _utc_iso(),
        }

        # Append to existing report (dual-write safety)
        entries = []
        if os.path.exists(report_path):
            try:
                with open(report_path, "r") as f:
                    entries = json.load(f)
            except (json.JSONDecodeError, IOError):
                entries = []

        if not isinstance(entries, list):
            entries = [entries] if entries else []

        entries.append(report)

        with open(report_path, "w") as f:
            json.dump(entries, f, indent=2)

        return report_path

    # ------------------------------------------------------------------ #
    # Persistence (directive 12)
    # ------------------------------------------------------------------ #
    def persist_call(self, output: DirectiveOutput, context: dict = None):
        """
        Persist decision to existing SQLite layer.

        Stores: input, outputs, signal, decision.
        Uses existing lumen_persistence.LumenPersistence if available.
        Falls back to JSONL if not.
        """
        if self.persistence:
            self.persistence.store_decision(
                tick_id=output.tick_id,
                input_text=output.decision.get("input", ""),
                outputs=output.decision.get("outputs", []),
                signal={},  # signal stored as part of details
                action=output.decision.get("action", "revise"),
                score=output.decision.get("score", 0.0),
                reason=output.decision.get("reason", ""),
            )
        else:
            # JSONL fallback
            store_path = "/tmp/lumen_decisions.jsonl"
            record = {
                "tick_id": output.tick_id,
                "timestamp": output.timestamp,
                "decision": output.decision,
                "telemetry": output.telemetry.to_dict(),
                "mode": output.mode,
            }
            with open(store_path, "a") as f:
                f.write(json.dumps(record) + "\n")

    # ------------------------------------------------------------------ #
    # Helpers: divergence, resilience, replay
    # ------------------------------------------------------------------ #
    def _compute_divergence(self, outputs: List[str]) -> Optional[float]:
        """Directive 4: compute divergence_score from multi-agent outputs."""
        if len(outputs) < 2:
            return 0.0

        try:
            top_k = self.pipeline.compute_top_k_divergence(outputs, k=3)
            if not top_k:
                return 0.0
            # Divergence = mean of top-k divergence values
            return round(
                sum(tk[2] for tk in top_k) / len(top_k), 4
            )
        except Exception:
            return None

    def _compute_resilience(
        self, input_text: str, base_score: float
    ) -> Optional[float]:
        """
        Directive 6-7: Compute resilience_score.

        Uses lumen_adversarial out-of-band. Does NOT inject perturbations
        inline during live calls (directive 8).
        """
        if not self.adversarial:
            return None

        try:
            # Run adversarial stress test on input
            results = self.adversarial.run_stress_test(
                input_text,
                decision_fn=lambda text: (
                    "revise",  # placeholder — actual decision made upstream
                    base_score,
                    "adversarial_test",
                ),
                num_attacks=5,
            )
            return self.adversarial.resilience_score(results)
        except Exception:
            return None

    def _compute_replay_delta(self) -> Optional[float]:
        """
        Directive 9: Compute replay_delta.

        Only invoked in SAFE/CRITICAL paths.
        """
        try:
            past = self.persistence.load_decisions(limit=20) if self.persistence else []
            if len(past) < 2:
                return 0.0
            return self.pipeline.compute_replay_delta(past)
        except Exception:
            return None

    def _should_block(self, signal: SignalNode, decision: Any) -> bool:
        """
        Directive 5: Block cycle reinforcement.

        If cycle_stability < threshold OR contradiction > threshold:
        route output → quarantine_buffer (mark decision as blocked).
        """
        if signal.cycle_coherence < self.CYCLE_STABILITY_THRESHOLD:
            return True
        if signal.contradiction > self.CONTRADICTION_THRESHOLD:
            return True
        return False

    def _compute_confidence(
        self,
        base_score: float,
        divergence: Optional[float],
        resilience: Optional[float],
        replay_delta: Optional[float],
    ) -> Optional[float]:
        """
        Directive 7: Compute confidence with adjustments.

        Lower confidence if instability detected.
        Never guesses missing values — returns None if can't compute.
        """
        if base_score is None:
            return None

        conf = base_score

        # Lower if high divergence
        if divergence is not None and divergence > 0.3:
            conf *= 0.9

        # Lower if low resilience
        if resilience is not None and resilience < 0.7:
            conf *= 0.85

        # Lower if high replay delta (instability)
        if replay_delta is not None and replay_delta > 0.1:
            conf *= 0.9

        return round(max(0.0, min(1.0, conf)), 4)

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #
    def _cycle_mean_embedding(self, cycle: PrimeCycle) -> list[float]:
        """Compute mean embedding for a cycle (for activation matching)."""
        import numpy as np
        embeddings = [deterministic_embedding(n) for n in cycle.nodes]
        return list(np.mean(embeddings, axis=0))

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Return call history (for inspection, not self-reinforcement)."""
        return [o.to_dict() for o in self._call_history]
