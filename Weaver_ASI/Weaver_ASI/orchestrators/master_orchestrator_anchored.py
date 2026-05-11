#!/usr/bin/env python3
"""
Weaver ASI - Anchored Orchestrator (Phase 3)
===============================================
Phase 1 of the sovereign loop: establishes the Ingress Contract.
Binds the kernel to simulated reality via signed attestations.

Phase 3 additions:
- OracleAgent and MitigationAgent now use the LLM-backed interface,
  returning GovernedClaim objects instead of raw strings.
- Claims are ingested directly into the EpistemicGraph via
  MemoryGovernor, carrying confidence, citations, and contradictions.
- The Conductor supports both legacy Intent-based agents and
  Phase 3 GovernedClaim-producing agents.
"""
import sys
import os
import random
import logging
import json
import time
import uuid
from typing import Dict, List

from Weaver_ASI.council.claims import GovernedClaim
from Weaver_ASI.memory.memory_governor import MemoryGovernor

# Allow running from any directory
_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_this_dir)
_cwd = os.getcwd()

# If running from within the package root (Weaver_ASI/orchestrators/),
# the parent of orchestrators IS the package root. In that case add the
# grandparent to sys.path so 'Weaver_ASI' can be imported.
if _this_dir.endswith(os.path.join("Weaver_ASI", "orchestrators")):
    _grandparent = os.path.dirname(_parent)
    if _grandparent not in sys.path:
        sys.path.insert(0, _grandparent)
else:
    if _parent not in sys.path:
        sys.path.insert(0, _parent)

from Weaver_ASI.core.event import Intent

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def build_system():
    """Construct the anchored system: reality channel -> gate -> kernel."""
    from Weaver_ASI.core.chronicle import Chronicle
    from Weaver_ASI.core.aegis_kernel import AegisKernel
    from Weaver_ASI.crypto.ingress_gate import IngressGate
    from Weaver_ASI.crypto.reality_registry import HardwareSensor, RealityRegistry
    from Weaver_ASI.council.oracle_agent import OracleAgent
    from Weaver_ASI.council.math_physics_agents import EulerAgent, GaussAgent, NewtonAgent
    from Weaver_ASI.crypto.sophiac_manifold import SophiacManifold, GuardianSlot

    # Simulated physical world
    class PhysicalWorld:
        def __init__(self):
            self._state = {
                "reactor_temp_c": 180.0,
                "pressure_bar": 12.5,
                "coolant_flow_lps": 4.2,
                "radiation_msv": 0.08,
            }
        def snapshot(self):
            return {k: v for k, v in self._state.items()}

    world = PhysicalWorld()
    sensor = HardwareSensor("HW_THERM_01", world)
    registry = RealityRegistry()
    registry.register(sensor)

    chronicle = Chronicle()
    gate = IngressGate(registry)
    manifold = SophiacManifold()
    guardian = GuardianSlot(manifold)
    kernel = AegisKernel(chronicle, gate, world, guardian)

    return kernel, world, chronicle, gate


class Conductor:
    SYM = {"COMMITTED": "\u2713", "BLOCKED": "\u2717", "DEFERRED": "\u23f8", "DORMANT": "\u00b7"}

    def __init__(self, kernel, world):
        self.kernel = kernel
        self.world = world
        self.agents = []
        self._log = []
        self._governed_claims = []  # Phase 3: collect GovernedClaim dicts

    def register(self, *agents):
        self.agents.extend(agents)

    def run_cycle(self, c):
        self.world.tick() if hasattr(self.world, "tick") else None
        for agent in self.agents:
            # Phase 3: try propose_claims first, fall back to legacy propose
            result = self._dispatch_agent(agent, c)
            result["agent"] = agent.name
            self._log.append(result)

            status = result.get("status", "?")
            sym = self.SYM.get(status, "?")
            reason = f"  <- {result.get('reason', '')}" if status == "BLOCKED" else ""
            claim_info = result.get("claim_text", "")
            if claim_info:
                claim_info = f" [{claim_info[:40]}...]"
            print(f"  Cycle {c+1:02d}  {sym} {agent.name:14} {status}{claim_info}{reason}")

    def _dispatch_agent(self, agent, step):
        """Dispatch an agent, trying Phase 3 interface first."""
        # Phase 3: try propose_claims (returns List[GovernedClaim])
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

        # Legacy path: single Intent
        intent = agent.propose(step, self.kernel.state)
        if not intent:
            return {"status": "DORMANT", "agent": agent.name, "step": step}
        if isinstance(intent, list):
            intent = intent[0]
        return self.kernel.apply(intent)

    def run_simulation(self, cycles=10):
        print(f"\n{'='*60}")
        print(f"  Weaver ASI - Anchored Orchestrator  ({cycles} cycles)")
        print(f"  Phase 3: LLM-backed Governed Claims")
        print(f"  Phase 1: Ingress Contract - Reality intersect Logic")
        print(f"{'='*60}\n")
        for c in range(cycles):
            self.run_cycle(c)
        replay_ok, _ = self.kernel.replay_verify()
        print(f"\n{'-'*60}")
        print(f"  Chronicle events: {len(self.kernel.chronicle)}")
        print(f"  Chain integrity: {'VALID' if self.kernel.chronicle.verify() else 'BROKEN'}")
        print(f"  Replay equivalent: {'PASS' if replay_ok else 'FAIL'}")
        print(f"  Governed claims produced: {len(self._governed_claims)}")
        print(f"{'='*60}\n")


def main():
    random.seed(7)
    kernel, world, chronicle, gate = build_system()

    # -- Epistemic Graph + Memory Governance --
    from Weaver_ASI.epistemics.epistemic_graph import EpistemicGraph
    from Weaver_ASI.memory.memory_governor import MemoryGovernor
    from Weaver_ASI.memory.retrieval import StratifiedRetriever
    from Weaver_ASI.constitutional.constitutional_kernel import ConstitutionalKernel
    from Weaver_ASI.observability.lineage import LineageTracker
    from Weaver_ASI.observability.drift_monitor import GovernanceDriftMonitor

    graph = EpistemicGraph()
    governor = MemoryGovernor(graph)
    retriever = StratifiedRetriever(graph)
    constitutional = ConstitutionalKernel(chronicle)
    constitutional.load_defaults()
    lineage = LineageTracker(graph)
    drift = GovernanceDriftMonitor(graph, constitutional, memory_governor=governor)

    # Phase 3.3: wire constitutional kernel into governor for axiom validation
    governor.set_constitutional(constitutional)

    # Phase 3.3: set agent trust scores (used by multi-factor decay)
    MemoryGovernor.set_trust("oracle", 0.95)
    MemoryGovernor.set_trust("mitigation", 0.90)
    MemoryGovernor.set_trust("euler", 0.80)
    MemoryGovernor.set_trust("gauss", 0.80)
    MemoryGovernor.set_trust("newton", 0.80)

    conductor = Conductor(kernel, world)

    from Weaver_ASI.crypto.reality_registry import HardwareSensor
    from Weaver_ASI.council.oracle_agent import OracleAgent
    from Weaver_ASI.council.math_physics_agents import EulerAgent, GaussAgent, NewtonAgent
    from Weaver_ASI.council.mitigation_agent import MitigationAgent
    from Weaver_ASI.council.lumen_agent import LumenAgent

    # Wire Phase 3: pass context_fn so agents see existing epistemic context
    def _context_fn():
        return retriever.get_all_beliefs()

    sensor = HardwareSensor("HW_THERM_01", world)
    conductor.register(
        OracleAgent(sensor, context_fn=_context_fn),
        EulerAgent(),
        GaussAgent(),
        NewtonAgent(),
        MitigationAgent(context_fn=_context_fn),
        LumenAgent(use_http=False),  # inline mode (no Flask service needed)
    )
    conductor.run_simulation(cycles=10)

    # -- Phase 3.2: Governed Council deliberation --
    # Collect all GovernedClaims from the simulation and run council
    from Weaver_ASI.council.governed_council import GovernedCouncil

    # Organize claims by agent
    agent_claims: Dict[str, List] = {}
    for claim in conductor._governed_claims:
        agent_claims.setdefault(claim.agent, []).append(claim)

    council = GovernedCouncil(graph, governor, constitutional)
    consensus = council.deliberate(agent_claims)

    # Print the council deliberation results
    print(f"\n  [GovernedCouncil] Deliberation complete:")
    print(f"    Claims in:  {consensus.total_in}")
    print(f"    Canonical:  {consensus.total_out}")
    print(f"    Disputed:   {consensus.disputed_count}")
    print(f"    Contradictions found: {consensus.contradictions_found}")
    print(f"    Resolution: {consensus.resolution}")
    if consensus.claims:
        print(f"    Canonical claims:")
        for c in consensus.claims:
            print(f"      - [{c['stratum']}] ({c['confidence']:.2f}) {c['text'][:70]}...")
            print(f"        source={c['source_agent']} node={c['node_id']}")

    # -- Legacy kernel results ingestion (unchanged) --
    claims_seen = set()

    # First: legacy kernel results
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
        elif status == "DORMANT":
            continue
        else:
            continue

        if claim in claims_seen:
            continue
        claims_seen.add(claim)

        if constitutional.is_valid(claim):
            governor.ingest(
                result,
                claim,
                citations=[],
                agent=agent,
                source_event_id=str(result.get("id", "")),
            )
        else:
            from Weaver_ASI.memory.strata import MemoryStratum
            governor.ingest(
                result,
                claim,
                citations=[],
                agent=agent,
                source_event_id=str(result.get("id", "")),
                force_stratum=MemoryStratum.DISPUTED,
            )

    # Second: Phase 3 GovernedClaims that did NOT survive arbitration
    # (these were disputed by the council; still ingest as DISPUTED)
    for claim in conductor._governed_claims:
        claim_text = claim.text
        if claim_text in claims_seen:
            continue
        claims_seen.add(claim_text)

        # Check if this claim was already ingested by council
        already_ingested = any(
            c["text"] == claim_text for c in consensus.claims
        )
        if already_ingested:
            continue

        event_id = f"gc_{uuid.uuid4().hex[:8]}"
        event = {
            "id": event_id,
            "type": "GOVERNED_CLAIM",
            "step": claim.metadata.get("step", 0),
            "confidence": claim.confidence,
        }

        if constitutional.is_valid(claim_text):
            governor.ingest(
                event,
                claim_text,
                citations=claim.citations,
                agent=claim.agent,
                source_event_id=event_id,
            )
        else:
            from Weaver_ASI.memory.strata import MemoryStratum
            governor.ingest(
                event,
                claim_text,
                citations=claim.citations,
                agent=claim.agent,
                source_event_id=event_id,
                force_stratum=MemoryStratum.DISPUTED,
            )

    # -- Print epistemic graph stats --
    print(f"\n{'='*60}")
    print(f"  EPISTEMIC GRAPH SUMMARY")
    print(f"{'-'*60}")
    print(f"  Graph nodes: {len(graph.nodes)}")
    print(f"  Governor ingested: {governor.get_ingestion_count()}")

    from Weaver_ASI.memory.strata import MemoryStratum
    strata_counts = {s.value: 0 for s in MemoryStratum}
    for node in graph.nodes.values():
        strata_counts[node.stratum.value] = strata_counts.get(node.stratum.value, 0) + 1
    print(f"  Stratum distribution:")
    for stratum, count in strata_counts.items():
        if count > 0:
            print(f"    {stratum}: {count}")

    # Print drift monitor output
    drift_result = drift.check_all()
    print(f"\n  [DriftMonitor] Total beliefs: {drift_result['total_beliefs']}")
    print(f"  [DriftMonitor] Avg weight: {drift_result['avg_weight']:.3f}")
    if drift_result['alerts']:
        for alert in drift_result['alerts']:
            print(f"  [DriftMonitor] {alert['type']}: {alert['message']}")

    # Print contradictions
    contradictions = graph.find_contradictions()
    if contradictions:
        print(f"\n  [Contradictions] {len(contradictions)} pairs detected:")
        for a, b in contradictions:
            print(f"    {a.claim[:50]} <-> {b.claim[:50]}")

    # Print lineage of first node (if any)
    if graph.nodes:
        first_id = next(iter(graph.nodes))
        print(f"\n  [Lineage] Ancestry of {first_id}:")
        print(json.dumps(lineage.ancestors(first_id, depth=2), indent=2, default=str))

    # ── Phase 3.5: Federation ───────────────────────────────────────
    from Weaver_ASI.federation import (
        GraphSync,
        IntergraphArbitration,
        TrustExchange,
        DistributedConsensus,
    )

    print(f"\n{'='*60}")
    print(f"  FEDERATION — Distributed Epistemic Network")
    print(f"{'-'*60}")

    # 1. GraphSync — export graph for a simulated peer
    sync = GraphSync(chronicle=chronicle, instance_name="anchored-node-1")
    export_data = sync.export(
        nodes=graph.nodes,
        strata=[s.value for s in MemoryStratum],
        since=0,
    )
    print(f"  [GraphSync] Exported {export_data['node_count']} nodes for federation")

    # 2. GraphSync — simulate importing from a foreign instance
    foreign_export = {
        "federation_source": "anchored-node-2",
        "exported_at": time.time(),
        "exported_by": "anchored-node-2",
        "node_count": 1,
        "strata_filter": ["operational"],
        "nodes": [
            {
                "node_id": "foreign_belief_001",
                "claim": "Peer node asserts external sensor reading",
                "confidence": 0.85,
                "stratum": "operational",
                "created_at": time.time(),
                "supports": [],
                "contradicts": [],
                "source_event_id": "hw_ext_001",
                "agent": "peer_sensor",
                "citations": [],
                "metadata": {},
                "cached_weight": -1.0,
            }
        ],
    }
    import_result = sync.import_from(graph, foreign_export, provenance_override="peer")
    print(
        f"  [GraphSync] Import from 'anchored-node-2': "
        f"{import_result['imported']} new, {import_result['skipped']} skipped"
    )

    # 3. IntergraphArbitration — test conflict detection with a duplicate
    #    node that has a different claim
    conflict_nodes = [
        {
            "node_id": "foreign_belief_001",
            "claim": "Peer node asserts EXTERNAL sensor reading (conflicting)",
            "confidence": 0.70,
            "stratum": "operational",
            "created_at": time.time(),
            "supports": [],
            "contradicts": [],
            "source_event_id": "hw_ext_002",
            "agent": "peer_sensor",
            "citations": [],
            "metadata": {},
            "cached_weight": -1.0,
        }
    ]
    arb = IntergraphArbitration(chronicle=chronicle)
    conflicts = arb.resolve_cross_instance_conflicts(
        graph, conflict_nodes, foreign_source="anchored-node-2"
    )
    if conflicts:
        print(f"  [Arbitration] {len(conflicts)} cross-instance conflict(s) detected:")
        for c in conflicts:
            print(f"    [{c.severity}] {c.conflict_reason[:70]}...")
    else:
        print(f"  [Arbitration] No cross-instance conflicts detected")

    # 4. TrustExchange — share and blend trust scores
    tx = TrustExchange(
        memory_governor=governor,
        chronicle=chronicle,
        instance_name="anchored-node-1",
    )
    local_scores = tx.share_trust_scores()
    foreign_scores = {
        "oracle": 0.90,
        "mitigation": 0.85,
        "euler": 0.82,
        "peer_sensor": 0.75,
    }
    blended = tx.receive_trust_scores(foreign_scores)
    print(f"  [TrustExchange] Received {len(foreign_scores)} foreign scores")
    print(f"  [TrustExchange] Blended {len(blended)} scores (0.7 local + 0.3 foreign)")
    if blended:
        print(f"  [TrustExchange] Top scores: {dict(list(blended.items())[:3])}")

    # 5. DistributedConsensus — mock peer and propose
    dc = DistributedConsensus(
        council=council,
        chronicle=chronicle,
        instance_name="anchored-node-1",
    )
    dc.register_peer("http://anchored-node-2:8080")
    test_claim = GovernedClaim(
        text="Federation-wide policy: all sensor readings must be cross-validated",
        confidence=0.80,
        citations=[],
        contradicts=[],
        agent="federation_proposer",
    )
    propose_result = dc.propose_to_federation(test_claim, ["http://anchored-node-2:8080"])
    print(
        f"  [DistributedConsensus] Proposed claim to {len(propose_result['sent_to'])} peer(s)"
    )

    # Receive a foreign claim
    foreign_claim_data = {
        "text": "Peer instance reports anomalous temperature spike",
        "confidence": 0.92,
        "agent": "peer_oracle",
        "citations": ["foreign_belief_001"],
        "contradicts": [],
    }
    received_claim = dc.receive_foreign_claim(foreign_claim_data)
    print(
        f"  [DistributedConsensus] Received claim from peer: "
        f'"{received_claim.text[:50]}..." (conf={received_claim.confidence})'
    )
    print(f"  [DistributedConsensus] Federation summary: {dc.summary()}")
    print(f"{'='*60}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
