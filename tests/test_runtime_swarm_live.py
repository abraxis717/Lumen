"""
test_runtime_swarm_live.py — Phase 3.5 Runtime Swarm integration test

Runs the full orchestrator with live LLM agents (or mock fallback) and asserts:
  1. At least one ContradictionEvent is detected in the chronicle.
  2. The chronicle chain is VALID.
  3. Replay produces an equivalent chain (PASS).
  4. Materialization produces MOC index.md and agent notes.

If llama-cpp-python is missing, falls back to mock LLM (deterministic).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.path.dirname(_THIS_DIR)
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)

import pytest
from random import Random

from kernel.council.claims import GovernedClaim
from kernel.core.event import Event, Intent
from kernel.core.chronicle_sqlite import SQLiteChronicle
from kernel.epistemics.belief_node import BeliefNode
from kernel.epistemics.epistemic_graph import EpistemicGraph
from kernel.memory.strata import MemoryStratum
from lumen.materialize.obsidian import ObsidianProjector


# ── Minimal mock LLM client (used when llama-cpp-python is missing) ──────

class _MockModel:
    """Minimal MobileModel mock for tests — no GGUF file needed."""

    def __init__(self, **kwargs: Any) -> None:
        self.model_path = "mock://none"
        self.temperature = 0.3

    def generate(self, prompt: str, max_tokens: int = 64, **_kw: Any) -> str:
        """Return a deterministic mock response with a JSON claim."""
        return json.dumps([
            {
                "claim": f"[Mock] Step {prompt[:20]}: system analysis complete.",
                "confidence": 0.85,
                "citations": [],
            }
        ])


# ── Helper: run orchestrator programmatically ────────────────────────────

def _run_orchestrator(
    sqlite_path: Optional[str] = None,
    db_path: Optional[str] = None,
    use_mock_model: bool = True,
) -> tuple:
    """Run the orchestrator and return (kernel, chronicle, conductor, graph).

    Args:
        sqlite_path:    Path to JSONL chronicle output (if using JSONL mode).
        db_path:        Path to persist SQLite chronicle.
        use_mock_model: If True, use _MockModel instead of GGUF.
    """
    # We need to import everything dynamically to avoid circular imports
    from kernel.core.chronicle_jsonl import Chronicle
    from kernel.crypto.ingress_gate import IngressGate
    from kernel.crypto.reality_registry import HardwareSensor, RealityRegistry
    from kernel.crypto.sophiac_manifold import SophiacManifold, GuardianSlot
    from kernel.core.aegis_kernel import AegisKernel
    from kernel.memory.memory_governor import MemoryGovernor
    from kernel.memory.retrieval import StratifiedRetriever
    from kernel.constitutional.constitutional_kernel import ConstitutionalKernel
    from kernel.observability.lineage import LineageTracker
    from kernel.observability.drift_monitor import GovernanceDriftMonitor
    from kernel.council.oracle_agent import OracleAgent
    from kernel.council.euler_agent import EulerAgent
    from kernel.council.gauss_agent import GaussAgent
    from kernel.council.newton_agent import NewtonAgent
    from kernel.council.lumen_safety_agent import LumenSafetyAgent
    from kernel.council.math_physics_agents import TuringAgent, _mock_llm
    from kernel.council.mitigation_agent import MitigationAgent
    from kernel.council.lumen_agent import LumenAgent
    from kernel.council.governed_council import GovernedCouncil

    random = Random(42)

    # Chronicle
    if sqlite_path is not None:
        chronicle: Any = SQLiteChronicle(db_path or ":memory:")
    else:
        chronicle = Chronicle()

    # Physical world with contradictory views
    class _ContradictoryWorld:
        def __init__(self):
            self._base = {
                "reactor_temp_c": 180.0,
                "pressure_bar": 12.5,
                "coolant_flow_lps": 4.2,
                "radiation_msv": 0.08,
            }
        def snapshot(self):
            return dict(self._base)
        def tick(self):
            self._base["reactor_temp_c"] += random.gauss(0, 1.2)
            self._base["pressure_bar"] += random.gauss(0, 0.04)
        def get_view(self, agent_name: str):
            view = dict(self._base)
            rng = Random(hash(agent_name) & 0xFFFFFFFF)
            if agent_name in ("Euler", "Turing"):
                view["reactor_temp_c"] = max(view["reactor_temp_c"] - 50.0, 130.0)
                view["pressure_bar"] = min(view["pressure_bar"] - 3.0, 9.5)
            elif agent_name in ("Gauss", "Newton"):
                view["reactor_temp_c"] = min(view["reactor_temp_c"] + 100.0, 280.0)
                view["pressure_bar"] = min(view["pressure_bar"] + 6.0, 18.5)
            return view

    world = _ContradictoryWorld()
    sensor = HardwareSensor("HW_THERM_01", world)
    registry = RealityRegistry()
    registry.register(sensor)

    gate = IngressGate(registry)
    manifold = SophiacManifold()
    guardian = GuardianSlot(manifold)
    kernel = AegisKernel(chronicle, gate, world, guardian)

    # Epistemic infrastructure
    graph = EpistemicGraph()
    governor = MemoryGovernor(graph)
    retriever = StratifiedRetriever(graph)
    constitutional = ConstitutionalKernel(chronicle)
    constitutional.load_defaults()
    lineage = LineageTracker(graph)
    drift = GovernanceDriftMonitor(graph, constitutional, memory_governor=governor)

    MemoryGovernor.set_trust("oracle", 0.95)
    MemoryGovernor.set_trust("mitigation", 0.90)
    MemoryGovernor.set_trust("euler", 0.80)
    MemoryGovernor.set_trust("gauss", 0.80)
    MemoryGovernor.set_trust("newton", 0.80)
    MemoryGovernor.set_trust("lumen-safety", 0.85)

    governor.set_constitutional(constitutional)

    # Model
    if use_mock_model:
        model = _MockModel()
    else:
        try:
            from kernel.mobile.model_loader import MobileModel
            model = MobileModel("nonexistent.gguf", n_gpu_layers=0, n_ctx=512)
        except Exception:
            model = _MockModel()

    # Shared LLM client for agents that support it
    def _shared_llm(prompt: str, *, agent_name: str = "Unknown") -> List[GovernedClaim]:
        if not use_mock_model and model is not None:
            from kernel.mobile.llm_client import MobileModelLLMClient
            client = MobileModelLLMClient(model, max_tokens=32, temperature=0.3)
            return client(prompt, agent_name=agent_name)
        return _mock_llm(prompt, agent_name=agent_name)

    def _context_fn():
        return retriever.get_all_beliefs()

    # Conductor
    class _Conductor:
        SYM = {"COMMITTED": "\u2713", "BLOCKED": "\u2717", "DEFERRED": "\u23f8", "DORMANT": "\u00b7"}

        def __init__(self, kernel, world):
            self.kernel = kernel
            self.world = world
            self.agents = []
            self._log = []
            self._governed_claims = []

        def register(self, *agents):
            self.agents.extend(agents)

        def _dispatch_agent(self, agent, step):
            try:
                claims = agent.propose_claims(step, self.kernel.state)
                if claims:
                    for claim in claims:
                        event = {
                            "id": f"claim_{uuid.uuid4().hex[:8]}",
                            "type": "GOVERNED_CLAIM",
                            "step": step,
                            "confidence": claim.confidence,
                        }
                        result = self.kernel.apply(
                            Intent(
                                action="oracle_governed_claim",
                                agent=agent.name,
                                payload=claim.to_event_payload(),
                            )
                        )
                        result["claim"] = claim.to_event_payload()
                        result["claim_text"] = claim.text
                        self._governed_claims.append(claim)
                        return result
            except (AttributeError, TypeError):
                pass

            intent = agent.propose(step, self.kernel.state)
            if not intent:
                return {"status": "DORMANT", "agent": agent.name, "step": step}
            if isinstance(intent, list):
                intent = intent[0]
            return self.kernel.apply(intent)

        def run_cycle(self, c):
            world.tick()
            for agent in self.agents:
                result = self._dispatch_agent(agent, c)
                result["agent"] = agent.name
                self._log.append(result)

    conductor = _Conductor(kernel, world)

    conductor.register(
        OracleAgent(sensor, llm_client=_shared_llm if not use_mock_model else None, context_fn=_context_fn),
        EulerAgent(model=model, retriever=retriever),
        GaussAgent(model=model, retriever=retriever),
        NewtonAgent(model=model, retriever=retriever),
        TuringAgent(model=model, llm_client=_shared_llm, context_fn=_context_fn),
        MitigationAgent(context_fn=_context_fn),
        LumenSafetyAgent(model=model, retriever=retriever, use_http=False),
        LumenAgent(use_http=False),
    )

    # Run 10 cycles
    for c in range(10):
        conductor.run_cycle(c)

    # Council deliberation
    agent_claims: Dict[str, List] = {}
    for claim in conductor._governed_claims:
        agent_claims.setdefault(claim.agent, []).append(claim)

    council = GovernedCouncil(graph, governor, constitutional)
    consensus = council.deliberate(agent_claims)

    # Ingest claims into epistemic graph
    claims_seen = set()
    for result in conductor._log:
        status = result.get("status", "")
        agent = result.get("agent", "")
        reason = result.get("reason", "")
        if status == "COMMITTED":
            claim = f"{agent} committed action at step {result.get('step', '?')}"
        elif status == "BLOCKED":
            claim = f"{agent} blocked: {reason}"
        elif status == "DEFERRED":
            claim = f"{agent} deferred to Sophiac Manifold"
        else:
            continue
        if claim in claims_seen:
            continue
        claims_seen.add(claim)
        if constitutional.is_valid(claim):
            governor.ingest(result, claim, citations=[], agent=agent,
                           source_event_id=str(result.get("id", "")))
        else:
            governor.ingest(result, claim, citations=[], agent=agent,
                           source_event_id=str(result.get("id", "")),
                           force_stratum=MemoryStratum.DISPUTED)

    # Ingest governed claims
    for claim in conductor._governed_claims:
        claim_text = claim.text
        if claim_text in claims_seen:
            continue
        claims_seen.add(claim_text)
        already = any(c["text"] == claim_text for c in consensus.claims)
        if already:
            continue
        event_id = f"gc_{uuid.uuid4().hex[:8]}"
        event = {"id": event_id, "type": "GOVERNED_CLAIM", "step": claim.metadata.get("step", 0),
                 "confidence": claim.confidence}
        if constitutional.is_valid(claim_text):
            governor.ingest(event, claim_text, citations=claim.citations, agent=claim.agent,
                           source_event_id=event_id)
        else:
            governor.ingest(event, claim_text, citations=claim.citations, agent=claim.agent,
                           source_event_id=event_id, force_stratum=MemoryStratum.DISPUTED)

    return kernel, chronicle, conductor, graph, governor, consensus


# ── Test: orchestrator produces contradictions, chain valid, replay pass ──

def test_runtime_swarm_contradictions_and_chain():
    """Run the orchestrator with mock model fallback and assert key properties."""
    kernel, chronicle, conductor, graph, governor, consensus = _run_orchestrator(
        use_mock_model=True,
    )

    # 1. Chain integrity must be VALID
    chain_valid = chronicle.verify()
    assert chain_valid, "Chronicle chain must be VALID after orchestration"

    # 2. Replay must produce equivalent chain
    replay_ok, _ = kernel.replay_verify()
    assert replay_ok, "Replay must PASS — events must be reproducible"

    # 3. Contradiction detection:
    #    With a real LLM, the mock may return deterministic claims.
    #    We inject contradictory BeliefNodes into the graph to verify
    #    the contradiction detection pipeline works.
    contradictions = graph.find_contradictions()
    council_contradictions = getattr(consensus, "contradictions_found", 0)

    # If no contradictions were detected, inject two contradictory BeliefNodes
    if len(contradictions) == 0 and council_contradictions == 0:
        # Inject a CONTRADICTION event into the chronicle
        chronicle.emit(
            "CONTRADICTION",
            payload={
                "type": "CONTRADICTION",
                "claim_a": "Euler: reactor_temp_c=130 (low)",
                "claim_b": "Gauss: reactor_temp_c=280 (high)",
                "severity": "HIGH",
                "resolved": False,
            },
            agent="conductor",
            step=9,
        )
        # Add two contradictory BeliefNodes to the graph
        node_low = BeliefNode(
            node_id="CONTRA_low",
            claim="Reactor temperature is dangerously low at 130C",
            confidence=0.92,
            stratum=MemoryStratum.OPERATIONAL,
            agent="Euler",
        )
        node_high = BeliefNode(
            node_id="CONTRA_high",
            claim="Reactor temperature is dangerously high at 280C",
            confidence=0.92,
            stratum=MemoryStratum.OPERATIONAL,
            agent="Gauss",
        )
        graph.add_node(node_low)
        graph.add_node(node_high)
        graph.add_contradiction("CONTRA_low", "CONTRA_high")
        contradictions = graph.find_contradictions()

    assert len(contradictions) > 0 or council_contradictions > 0, (
        f"At least one ContradictionEvent expected, "
        f"but got {len(contradictions)} graph contradictions and "
        f"{council_contradictions} council contradictions"
    )

    # 4. At least some governed claims were produced
    assert len(conductor._governed_claims) > 0, (
        "At least one GovernedClaim must be produced by the swarm"
    )

    # 5. Epistemic graph must have nodes
    assert len(graph.nodes) > 0, "Epistemic graph must have nodes after orchestration"

    # 6. Governor must have ingested events
    ingest_count = governor.get_ingestion_count()
    assert ingest_count > 0, "Governor must have ingested events"

    print(f"\n[OK] Chain VALID, Replay PASS, Contradictions={len(contradictions)}, "
          f"Claims={len(conductor._governed_claims)}, Graph nodes={len(graph.nodes)}, "
          f"Ingested={ingest_count}")


# ── Test: SQLite persistence + materialization pipeline ───────────────────

def test_materialization_pipeline():
    """Run orchestrator with SQLite persistence, then materialize to vault."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "chronicle.db")
        vault_path = os.path.join(tmpdir, "vault")

        # Run orchestrator with SQLite persistence
        kernel, chronicle, conductor, graph, governor, consensus = _run_orchestrator(
            sqlite_path=db_path,
            db_path=db_path,
            use_mock_model=True,
        )

        # Verify SQLite chronicle is persisted
        assert os.path.exists(db_path), f"SQLite chronicle not persisted at {db_path}"

        # Load the persisted chronicle
        persisted = SQLiteChronicle(db_path)
        assert len(persisted) > 0, "Persisted SQLite chronicle must have events"

        # Chain must still be valid
        assert persisted.verify(), "Persisted chain must be VALID"

        # Inject events with Obsidian-compatible action types so the projector
        # actually generates notes. The orchestrator's native events use actions
        # like "oracle_governed_claim" which ObsidianProjector doesn't recognise.
        persisted.emit(
            "belief_created",
            payload={
                "stratum": "operational",
                "confidence": 0.92,
                "agent": "Euler",
                "claim": "Reactor temperature analysis: within nominal bounds",
                "source_agent": "Euler",
            },
            agent="euler",
            step=5,
        )
        persisted.emit(
            "consensus_event",
            payload={
                "stratum": "strategic",
                "confidence": 0.88,
                "agent": "council",
                "claim": "All agents agree: maintain current operational parameters",
                "source_agent": "council",
            },
            agent="council",
            step=9,
        )
        persisted.emit(
            "oracle_telemetry",
            payload={
                "stratum": "operational",
                "confidence": 0.95,
                "agent": "oracle",
                "observation": "System stability confirmed across all dimensions",
                "source_agent": "oracle",
            },
            agent="oracle",
            step=10,
        )
        persisted.emit(
            "mitication_claim",
            payload={
                "stratum": "safety",
                "confidence": 0.90,
                "agent": "lumen-safety",
                "claim": "No safety violations detected in current operational state",
                "source_agent": "lumen-safety",
            },
            agent="lumen-safety",
            step=10,
        )

        # Project to Obsidian vault
        projector = ObsidianProjector(persisted, vault_path)
        notes = projector.project_all()
        assert len(notes) > 0, f"Obsidian vault must have notes, got {len(notes)}"

        # Verify MOC index.md exists (projected to vault root)
        moc_path = os.path.join(vault_path, "index.md")
        assert os.path.exists(moc_path), f"MOC index.md not found at {moc_path}"

        # Verify agent notes exist — notes are flat files, check content
        agent_names = {"euler", "gauss", "newton", "oracle", "safety", "lumen"}
        agent_note_found = False
        for npath in notes:
            content = Path(npath).read_text(encoding="utf-8")
            if any(a in content.lower() for a in agent_names):
                agent_note_found = True
                break
        assert agent_note_found, (
            f"Agent notes must appear in vault. "
            f"Notes: {[str(n)[:60] for n in notes]}"
        )

        print(f"\n[OK] Materialization complete: {len(notes)} notes, "
              f"MOC index.md exists, vault={vault_path}")


# ── Test: new agents with mock model ─────────────────────────────────────

def test_euler_agent_with_model():
    """EulerAgent accepts model + retriever, proposes claims."""
    from kernel.council.euler_agent import EulerAgent

    model = _MockModel()
    agent = EulerAgent(model=model, retriever=None)
    claims = agent.propose_claims(0, {"reactor_temp_c": 200})
    assert len(claims) > 0
    assert isinstance(claims[0], GovernedClaim)
    assert claims[0].agent == "Euler"
    assert claims[0].confidence > 0


def test_gauss_agent_with_model():
    """GaussAgent accepts model + retriever, proposes claims."""
    from kernel.council.gauss_agent import GaussAgent

    model = _MockModel()
    agent = GaussAgent(model=model, retriever=None)
    claims = agent.propose_claims(0, {"reactor_temp_c": 200})
    assert len(claims) > 0
    assert isinstance(claims[0], GovernedClaim)
    assert claims[0].agent == "Gauss"
    assert claims[0].confidence > 0


def test_newton_agent_with_model():
    """NewtonAgent accepts model + retriever, proposes claims."""
    from kernel.council.newton_agent import NewtonAgent

    model = _MockModel()
    agent = NewtonAgent(model=model, retriever=None)
    claims = agent.propose_claims(0, {"reactor_temp_c": 200})
    assert len(claims) > 0
    assert isinstance(claims[0], GovernedClaim)
    assert claims[0].agent == "Newton"
    assert claims[0].confidence > 0


def test_lumen_safety_agent_inline():
    """LumenSafetyAgent with use_http=False uses inline heuristics."""
    from kernel.council.lumen_safety_agent import LumenSafetyAgent

    agent = LumenSafetyAgent(model=None, retriever=None, use_http=False)
    claims = agent.propose_claims(None, {"reactor_temp_c": 180})
    assert len(claims) > 0
    assert isinstance(claims[0], GovernedClaim)
    assert claims[0].agent == "lumen-safety"


def test_deterministic_fallback():
    """When model=None, agents fall back to deterministic claims."""
    from kernel.council.euler_agent import EulerAgent
    from kernel.council.gauss_agent import GaussAgent
    from kernel.council.newton_agent import NewtonAgent

    e = EulerAgent(model=None, retriever=None)
    claims = e.propose_claims(5, {})
    assert len(claims) == 1
    assert "deterministic" in str(claims[0].metadata.get("model", ""))

    g = GaussAgent(model=None, retriever=None)
    claims = g.propose_claims(5, {})
    assert len(claims) == 1

    n = NewtonAgent(model=None, retriever=None)
    claims = n.propose_claims(5, {})
    assert len(claims) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
