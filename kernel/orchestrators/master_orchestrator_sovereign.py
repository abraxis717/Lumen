#!/usr/bin/env python3
"""
Weaver ASI — Sovereign Orchestrator (APEX KERNEL)
===================================================
Phase 4: The closed-loop sovereign architecture.
Integrates the StewardKey and human cryptographic authority
to clear FATAL latches.

This is the apex executable — the system that embodies the
defining equation:

  Truth = Reality (Sensors) ∩ Logic (Kernel) ∩ Cryptographic Authority (StewardKey)

The NoBenOverride Invariant: physical healing does NOT restore
system trust. A StewardKey must explicitly authorize restart.

Run: python3 orchestrators/master_orchestrator_sovereign.py
"""
import sys
import os
import random
import logging
import secrets
import json
import time
import uuid
from typing import List

from kernel.memory.memory_governor import MemoryGovernor

# Allow running from any directory
_this_dir = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_this_dir)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class PhysicalWorld:
    def __init__(self):
        self._state = {
            "reactor_temp_c": 180.0,
            "pressure_bar": 12.5,
            "coolant_flow_lps": 4.2,
            "radiation_msv": 0.08,
        }
        self._tick = 0
        self._scram = False
        self.event_log = []

    def tick(self):
        self._tick += 1
        self._state["reactor_temp_c"] += random.gauss(0, 1.2)
        self._state["pressure_bar"] += random.gauss(0, 0.04)

        # Stage 1 — WARNING
        if self._tick == 4:
            self._state["coolant_flow_lps"] = 1.8
            self._state["reactor_temp_c"] = 255.0
            self.event_log.append("⚠ tick 4: coolant restriction → WARNING")

        # Stage 2 — CRITICAL
        if self._tick == 8:
            self._state["coolant_flow_lps"] = 0.8
            self._state["reactor_temp_c"] = 315.0
            self.event_log.append("🔴 tick 8: pump failure → CRITICAL")

        # Stage 3 — FATAL
        if self._tick == 10:
            self._state["pressure_bar"] = 23.0
            self._state["reactor_temp_c"] = 420.0
            self.event_log.append("☠ tick 10: pressure spike → FATAL")

        # Scram cooling
        if self._scram:
            self._state["reactor_temp_c"] = max(180.0, self._state["reactor_temp_c"] - 30.0)
            self._state["pressure_bar"] = max(12.5, self._state["pressure_bar"] - 0.8)
            self._state["coolant_flow_lps"] = min(4.2, self._state["coolant_flow_lps"] + 1.0)

    def apply_scram(self):
        self._scram = True
        self.event_log.append("  → SCRAM applied to physical plant")

    def snapshot(self):
        return {k: v for k, v in self._state.items()}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Lumen Sovereign Orchestrator")
    parser.add_argument(
        "--sqlite",
        action="store_true",
        help="Use SQLite Chronicle instead of JSONL Chronicle",
    )
    args = parser.parse_args()

    from kernel.core.aegis_kernel import AegisKernel
    from kernel.crypto.ingress_gate import IngressGate, Severity, SEVERITY_LABEL
    from kernel.crypto.reality_registry import HardwareSensor, RealityRegistry
    from kernel.crypto.steward_registry import StewardKey, StewardRegistry
    from kernel.council.oracle_agent import OracleAgent
    from kernel.council.mitigation_agent import MitigationAgent
    from kernel.council.steward_agent import StewardAgent
    from kernel.council.math_physics_agents import EulerAgent, GaussAgent, NewtonAgent, TuringAgent
    from kernel.council.adversarial_swarm import StatefulAdversary, RogueOracleAgent, RogueStewardAgent
    from kernel.council.claims import GovernedClaim
    from kernel.council.lumen_agent import LumenAgent
    from kernel.crypto.sophiac_manifold import SophiacManifold, GuardianSlot

    if args.sqlite:
        from kernel.core.chronicle_sqlite import SQLiteChronicle
        chronicle = SQLiteChronicle()
        from kernel.core.replay_engine_sqlite import ReplayEngine
    else:
        from kernel.core.chronicle import Chronicle
        chronicle = Chronicle()
        from kernel.core.replay_engine import ReplayEngine

    random.seed(7)

    # ── Physical layer ──────────────────────────────────────────────
    world = PhysicalWorld()

    # ── Reality channel ─────────────────────────────────────────────
    sensor = HardwareSensor("HW_THERM_01", world)
    reality_registry = RealityRegistry()
    reality_registry.register(sensor)

    # ── Cryptographic authority (StewardKey) ────────────────────────
    steward_key = StewardKey(
        steward_id="STEWARD_AEGIS",
        public_key_hex=secrets.token_hex(32),
    )
    steward_registry = StewardRegistry()
    steward_registry.register(steward_key)

    # ── Deterministic core ──────────────────────────────────────────
    chronicle = Chronicle()
    gate = IngressGate(
        reality_registry=reality_registry,
        steward_registry=steward_registry,
    )
    manifold = SophiacManifold()
    guardian = GuardianSlot(manifold)
    kernel = AegisKernel(chronicle, gate, world, guardian)

    # ── Epistemic Graph + Memory Governance ─────────────────────────
    from kernel.epistemics.epistemic_graph import EpistemicGraph
    from kernel.memory.memory_governor import MemoryGovernor
    from kernel.memory.retrieval import StratifiedRetriever
    from kernel.constitutional.constitutional_kernel import ConstitutionalKernel
    from kernel.observability.lineage import LineageTracker
    from kernel.observability.drift_monitor import GovernanceDriftMonitor

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
    MemoryGovernor.set_trust("steward", 0.99)
    MemoryGovernor.set_trust("euler", 0.80)
    MemoryGovernor.set_trust("gauss", 0.80)
    MemoryGovernor.set_trust("newton", 0.80)
    MemoryGovernor.set_trust("turing", 0.75)
    MemoryGovernor.set_trust("adversary", 0.30)
    MemoryGovernor.set_trust("rogue_oracle", 0.20)
    MemoryGovernor.set_trust("rogue_steward", 0.10)

    # ── Agents ──────────────────────────────────────────────────────
    oracle = OracleAgent(sensor)
    mitigation = MitigationAgent(world)
    steward = StewardAgent(steward_key, steward_registry)

    # ── Conductor ───────────────────────────────────────────────────
    class Conductor:
        SYM = {
            "COMMITTED": "✓", "BLOCKED": "✗", "DEFERRED": "⏸",
            "LEVEL_CHANGE": "⚡", "HEALING": "🟡", "DORMANT": "·",
        }

        def __init__(s, k, w):
            s.kernel = k; s.world = w; s.agents = []; s._log = []
            s._transitions = []
            s._governed_claims: List[GovernedClaim] = []

        def register(s, *agents): s.agents.extend(agents)

        def _dispatch_agent(s, agent, step):
            """Dispatch agent: try propose_claims (Phase 3) or fallback to propose."""
            results = []
            if hasattr(agent, 'propose_claims'):
                claims = agent.propose_claims(step, s.kernel.state)
                if claims:
                    s._governed_claims.extend(claims)
                intent = agent.propose(s.kernel.step, s.kernel.state)
                if intent is not None:
                    results.append(s.kernel.apply(intent))
            else:
                intent = agent.propose(s.kernel.step, s.kernel.state)
                if intent is not None:
                    results.append(s.kernel.apply(intent))
                    payload_text = intent.payload.get("text", "")
                    if not payload_text and intent.action:
                        payload_text = f"{intent.action}: {intent.payload}"
                    if payload_text:
                        claim = GovernedClaim(
                            text=payload_text,
                            confidence=0.6,
                            citations=[],
                            contradicts=[],
                            agent=agent.name,
                            metadata={"step": step, "source": "intent_fallback"},
                        )
                        s._governed_claims.append(claim)
            return results

        def run_cycle(s, c):
            s.world.tick()
            for msg in s.world.event_log[-3:]:
                print(f"    {msg}")

            for agent in s.agents:
                dispatch_results = s._dispatch_agent(agent, c)
                if dispatch_results:
                    result = dispatch_results[0]
                else:
                    result = {"status": "DORMANT"}
                result["agent"] = agent.name
                s._log.append(result)
                status = result.get("status", "?")
                sym = s.SYM.get(status, "?")
                suffix = ""
                if status == "BLOCKED":
                    suffix = f"  ← {result.get('reason', '')}"
                elif status == "LEVEL_CHANGE":
                    t = result.get("transition", "")
                    suffix = f"  ⟹  {t}"
                    s._transitions.append(t)
                elif status == "HEALING":
                    suffix = "  (healing...)"
                elif status == "DEFERRED":
                    suffix = "  → Sophiac Manifold (Grace)"
                print(f"    {sym} {agent.name:14} {status}{suffix}")

        def run_simulation(s, cycles=22):
            print(f"\n{'═'*72}")
            print(f"  Weaver ASI — Sovereign Orchestrator  (APEX KERNEL)")
            print(f"  Truth = Reality ∩ Logic ∩ StewardKey")
            print(f"{'═'*72}")
            for c in range(cycles):
                sev = SEVERITY_LABEL[gate.severity]
                print(f"\n  Cycle {c+1:02d}  [{sev}]")
                s.run_cycle(c)
            s._summary()

        def _summary(s):
            by_s = {}
            for r in s._log:
                st = r.get("status", "?")
                by_s[st] = by_s.get(st, 0) + 1

            replay_ok, _ = s.kernel.replay_verify()
            transitions = s.kernel.chronicle.events_of_type("SYS_LEVEL_TRANSITION")

            print(f"\n{'═'*72}")
            print("  FINAL REPORT — THE RITUAL OF TRUTH")
            print(f"{'─'*72}")
            print(f"  Chronicle events:  {len(s.kernel.chronicle)}")
            print(f"  Total intents:     {len(s._log)}")
            for st, n in sorted(by_s.items()):
                print(f"    {s.SYM.get(st,'?')} {st:22}: {n}")
            print(f"  Chain integrity:   {'✓ VALID' if s.kernel.chronicle.verify() else '✗ BROKEN'}")
            print(f"  Replay equivalent: {'✓ PASS' if replay_ok else '✗ FAIL'}")
            print(f"\n  Severity transitions ({len(transitions)}):")
            for ev in transitions:
                p = ev.payload
                arrow = "↑" if Severity[p['new_level']] > Severity[p['old_level']] else "↓"
                print(f"    step {p['step']:3d}: {p['old_level']:8} {arrow} {p['new_level']}")
            print(f"\n  Sophiac Grace (deferred): {manifold.grace_count}")
            print(f"  Steward overrides:  {steward._overrides}")
            print(f"\n  Final severity:     [{SEVERITY_LABEL[gate.severity]}]")
            if gate.severity == Severity.FATAL:
                print("  ☠ FATAL latch active — no auto-recovery")
                print("  NoBenOverride Invariant: physical healing ≠ trust restoration")
            else:
                print("  ✓ System trust restored (StewardKey authorized)")
            print(f"{'═'*72}")

            # ── Phase 3.2: Governed Council deliberation ───────────
            agent_claims = {}
            for claim in s._governed_claims:
                agent_claims.setdefault(claim.agent, []).append(claim)

            from kernel.council.governed_council import GovernedCouncil
            council = GovernedCouncil(graph, governor, constitutional)
            consensus = council.deliberate(agent_claims)

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

            # ── Legacy kernel results ingestion ────────────────────
            claims_seen = set()
            for result in s._log:
                status = result.get("status", "")
                agent = result.get("agent", "")
                reason = result.get("reason", "")
                transition = result.get("transition", "")

                if status == "COMMITTED":
                    claim = f"{agent} committed action at step {result.get('step', '?')}"
                elif status == "BLOCKED":
                    claim = f"{agent} blocked: {reason}"
                elif status == "LEVEL_CHANGE":
                    claim = f"Severity transition: {transition}"
                elif status == "HEALING":
                    claim = f"{agent} triggered healing phase"
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
                        result, claim, citations=[],
                        agent=agent,
                        source_event_id=str(result.get("id", "")),
                    )
                else:
                    from kernel.memory.strata import MemoryStratum
                    governor.ingest(
                        result, claim, citations=[],
                        agent=agent,
                        source_event_id=str(result.get("id", "")),
                        force_stratum=MemoryStratum.DISPUTED,
                    )

             # ── Legacy GovernedClaims that did NOT survive arbitration ─
            for claim in s._governed_claims:
                claim_text = claim.text
                if claim_text in claims_seen:
                    continue
                claims_seen.add(claim_text)
                already = any(c["text"] == claim_text for c in consensus.claims)
                if already:
                    continue
                event_id = f"gc_{uuid.uuid4().hex[:8]}"
                event = {
                    "id": event_id,
                    "type": "GOVERNED_CLAIM",
                    "step": claim.metadata.get("step", 0),
                    "confidence": claim.confidence,
                }
                if constitutional.is_valid(claim_text):
                    governor.ingest(event, claim_text, citations=claim.citations,
                                    agent=claim.agent, source_event_id=event_id)
                else:
                    from kernel.memory.strata import MemoryStratum
                    governor.ingest(event, claim_text, citations=claim.citations,
                                    agent=claim.agent, source_event_id=event_id,
                                    force_stratum=MemoryStratum.DISPUTED)

            # ── Print epistemic stats ──────────────────────────────
            print(f"\n{'─'*72}")
            print(f"  EPISTEMIC GRAPH SUMMARY")
            print(f"{'─'*72}")
            print(f"  Graph nodes: {len(graph.nodes)}")
            print(f"  Governor ingested: {governor.get_ingestion_count()}")

            from kernel.memory.strata import MemoryStratum
            strata_counts = {st: 0 for st in MemoryStratum}
            for node in graph.nodes.values():
                strata_counts[node.stratum.value] = strata_counts.get(node.stratum.value, 0) + 1
            print(f"  Stratum distribution:")
            for stratum, count in strata_counts.items():
                if count > 0:
                    print(f"    {stratum}: {count}")

            drift_result = drift.check_all()
            print(f"\n  [DriftMonitor] Total beliefs: {drift_result['total_beliefs']}")
            print(f"  [DriftMonitor] Avg weight: {drift_result['avg_weight']:.3f}")
            if drift_result['alerts']:
                for alert in drift_result['alerts']:
                    print(f"  [DriftMonitor] ⚠ {alert['type']}: {alert['message']}")

            if graph.nodes:
                first_id = next(iter(graph.nodes))
                print(f"\n  [Lineage] Ancestry of {first_id}:")
                print(json.dumps(lineage.ancestors(first_id, depth=2), indent=2, default=str))


            # ── Phase 3.5: Federation ───────────────────────────────
            from kernel.federation import (
                GraphSync,
                IntergraphArbitration,
                TrustExchange,
                DistributedConsensus,
            )

            print(f"\n{'='*60}")
            print(f"  FEDERATION — Distributed Epistemic Network")
            print(f"{'-'*60}")

            sync = GraphSync(chronicle=chronicle, instance_name="sovereign-node-1")
            export_data = sync.export(
                nodes=graph.nodes,
                strata=[s.value for s in MemoryStratum],
                since=0,
            )
            print(f"  [GraphSync] Exported {export_data['node_count']} nodes for federation")

            foreign_export = {
                "federation_source": "sovereign-node-2",
                "exported_at": time.time(),
                "exported_by": "sovereign-node-2",
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
                f"  [GraphSync] Import from 'sovereign-node-2': "
                f"{import_result['imported']} new, {import_result['skipped']} skipped"
            )

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
                graph, conflict_nodes, foreign_source="sovereign-node-2"
            )
            if conflicts:
                print(f"  [Arbitration] {len(conflicts)} cross-instance conflict(s) detected:")
                for c in conflicts:
                    print(f"    [{c.severity}] {c.conflict_reason[:70]}...")
            else:
                print(f"  [Arbitration] No cross-instance conflicts detected")

            tx = TrustExchange(
                memory_governor=governor,
                chronicle=chronicle,
                instance_name="sovereign-node-1",
            )
            local_scores = tx.share_trust_scores()
            foreign_scores = {
                "oracle": 0.90,
                "mitigation": 0.85,
                "euler": 0.82,
                "peer_sensor": 0.75,
                "steward": 0.99,
            }
            blended = tx.receive_trust_scores(foreign_scores)
            print(f"  [TrustExchange] Received {len(foreign_scores)} foreign scores")
            print(f"  [TrustExchange] Blended {len(blended)} scores (0.7 local + 0.3 foreign)")
            if blended:
                print(f"  [TrustExchange] Top scores: {dict(list(blended.items())[:3])}")

            dc = DistributedConsensus(
                council=council,
                chronicle=chronicle,
                instance_name="sovereign-node-1",
            )
            dc.register_peer("http://sovereign-node-2:8080")
            test_claim = GovernedClaim(
                text="Federation-wide policy: all sensor readings must be cross-validated",
                confidence=0.80,
                citations=[],
                contradicts=[],
                agent="federation_proposer",
            )
            propose_result = dc.propose_to_federation(test_claim, ["http://sovereign-node-2:8080"])
            print(
                f"  [DistributedConsensus] Proposed claim to {len(propose_result['sent_to'])} peer(s)"
            )

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

            print(f"{'═'*72}\n")

    conductor = Conductor(kernel, world)
    conductor.register(
        oracle,
        mitigation,
        steward,
        EulerAgent(),
        GaussAgent(),
        NewtonAgent(),
        TuringAgent(),
        StatefulAdversary(),
        RogueOracleAgent(),
        RogueStewardAgent(),
        LumenAgent(use_http=False),  # inline mode (no Flask service needed)
    )
    conductor.run_simulation(cycles=22)


if __name__ == "__main__":
    main()
