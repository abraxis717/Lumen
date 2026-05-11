#!/usr/bin/env python3
"""
Weaver ASI — Tactile CLI Interface
====================================
Exposes the ASI's capabilities through a command-line interface.

Commands:
  /append <action> [payload_json]   — Propose an event (injects into Chronicle)
  /replay                           — Rebuild ASI worldview from Chronicle (I27)
  /verify                           — Audit hash chain integrity
  /audit                            — The Ritual of Truth (full report)
  /severity                         — Show current severity state
  /grace                            — Show Sophiac Manifold (deferred events)
  /transitions                      — Show severity transition history
  /run [cycles]                     — Run a full simulation
  /help                             — Show this help

Run: python3 cli/weaver_cli.py
"""
import json
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class WeaverCLI:
    """Interactive CLI for the Weaver ASI."""

    PROMPT = "weaver > "

    def __init__(self, kernel, gate, chronicle, manifold, world=None):
        self.kernel = kernel
        self.gate = gate
        self.chronicle = chronicle
        self.manifold = manifold
        self.world = world

    def run(self):
        """Main CLI loop."""
        print("\n" + "=" * 60)
        print("  Weaver ASI — Tactile Interface")
        print("  Truth = Reality ∩ Logic ∩ StewardKey")
        print("=" * 60)
        print("Commands: /append, /replay, /verify, /audit, /severity")
        print("          /grace, /transitions, /run, /help, /quit")
        print()

        while True:
            try:
                line = input(self.PROMPT).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not line:
                continue

            parts = line.split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if cmd == "/quit" or cmd == "/exit":
                print("Bye.")
                break

            elif cmd == "/help":
                self._show_help()

            elif cmd == "/append":
                self._cmd_append(args)

            elif cmd == "/replay":
                self._cmd_replay()

            elif cmd == "/verify":
                self._cmd_verify()

            elif cmd == "/audit":
                self._cmd_audit()

            elif cmd == "/severity":
                self._cmd_severity()

            elif cmd == "/grace":
                self._cmd_grace()

            elif cmd == "/transitions":
                self._cmd_transitions()

            elif cmd == "/run":
                cycles = int(args) if args and args.isdigit() else 22
                self._cmd_run(cycles)

            else:
                print(f"Unknown command: {cmd}")
                print("Type /help for available commands.\n")

    def _show_help(self):
        print("""
Available commands:
  /append <action> [payload_json]    Propose an event into the Chronicle
  /replay                            Rebuild worldview from Chronicle (I27)
  /verify                            Audit hash chain integrity
  /audit                             Full ritual of truth (detailed report)
  /severity                          Show current severity state
  /grace                             Show Sophiac Manifold deferred events
  /transitions                       Show severity transition history
  /run [cycles]                      Run a full simulation
  /help                              Show this help
  /quit                              Exit
""")

    def _cmd_append(self, args):
        """Propose an event."""
        from Weaver_ASI.core.event import Intent

        parts = args.split(None, 1)
        if not parts:
            print("Usage: /append <action> [payload_json]\n")
            return

        action = parts[0]
        payload = {}
        if len(parts) > 1:
            try:
                payload = json.loads(parts[1])
            except json.JSONDecodeError:
                print("Invalid JSON payload.\n")
                return

        intent = Intent(action=action, agent="CLI", payload=payload)
        result = self.kernel.apply(intent)
        status = result.get("status", "?")
        if status == "BLOCKED":
            print(f"✗ BLOCKED: {result.get('reason', '')}")
        elif status == "DEFERRED":
            print("⏸ DEFERRED → Sophiac Manifold (Grace)")
        else:
            print(f"✓ {status} — {action} committed by {intent.agent}")

    def _cmd_replay(self):
        """Rebuild state from Chronicle — I27 total replay equivalence."""
        replay_ok, replay_state = self.kernel.replay_verify()
        print("\n" + "-" * 40)
        print("  TOTAL REPLAY EQUIVALENCE (I27)")
        print("-" * 40)
        print(f"  Chain verified:   {'YES' if self.chronicle.verify() else 'NO'}")
        print(f"  Events replayed:  {len(self.chronicle)}")
        print(f"  Replay equivalent: {'✓ PASS' if replay_ok else '✗ FAIL'}")
        if not replay_ok:
            print("  Live vs Replay state differs — HIDDEN STATE DETECTED")
        print("-" * 40 + "\n")

    def _cmd_verify(self):
        """Audit hash chain."""
        valid = self.chronicle.verify()
        print(f"\n  Chronicle hash chain: {'✓ VALID' if valid else '✗ BROKEN'}")
        print(f"  Head hash: {self.chronicle.head_hash[:32]}...")
        print(f"  Events: {len(self.chronicle)}\n")

    def _cmd_audit(self):
        """The Ritual of Truth — full report."""
        replay_ok, _ = self.kernel.replay_verify()
        transitions = self.chronicle.events_of_type("SYS_LEVEL_TRANSITION")

        print("\n" + "=" * 60)
        print("  THE RITUAL OF TRUTH")
        print("=" * 60)
        print(f"  Chronicle events:  {len(self.chronicle)}")
        print(f"  Chain integrity:   {'✓ VALID' if self.chronicle.verify() else '✗ BROKEN'}")
        print(f"  Replay equivalent: {'✓ PASS' if replay_ok else '✗ FAIL'}")
        print(f"  Current severity:  [{self.gate.severity.name}]")
        print(f"  Sophiac Grace:     {self.manifold.grace_count}")
        print(f"  Diversity:         {self.kernel.state.get('diversity', 100)}")

        if transitions:
            print(f"\n  Severity transitions ({len(transitions)}):")
            for ev in transitions:
                p = ev.payload
                print(f"    step {p['step']:3d}: {p['old_level']} → {p['new_level']}")

        print(f"\n  Live state: {json.dumps(self.kernel.state, indent=4)}")
        print(f"{'=' * 60}\n")

    def _cmd_severity(self):
        print(f"\n  Current severity: [{self.gate.severity.name}]")
        print(f"  Clean ticks: {self.gate._clean_ticks}")
        print(f"  Telemetry: {self.gate.telemetry}\n")

    def _cmd_grace(self):
        deferred = self.manifold.get_deferred()
        print(f"\n  Sophiac Manifold (Grace): {len(deferred)} deferred events")
        for ev in deferred:
            print(f"    step {ev.step}: {ev.action} by {ev.agent}")
        print()

    def _cmd_transitions(self):
        transitions = self.chronicle.events_of_type("SYS_LEVEL_TRANSITION")
        print(f"\n  Severity transitions ({len(transitions)}):")
        for ev in transitions:
            p = ev.payload
            print(f"    step {p['step']:3d}: {p['old_level']} → {p['new_level']}")
        print()

    def _cmd_run(self, cycles):
        """Run a full simulation and show the result."""
        from Weaver_ASI.core.chronicle import Chronicle
        from Weaver_ASI.core.aegis_kernel import AegisKernel
        from Weaver_ASI.crypto.ingress_gate import IngressGate
        from Weaver_ASI.crypto.reality_registry import RealityRegistry, HardwareSensor
        from Weaver_ASI.council.oracle_agent import OracleAgent
        from Weaver_ASI.council.mitigation_agent import MitigationAgent
        from Weaver_ASI.council.math_physics_agents import EulerAgent, GaussAgent, NewtonAgent
        from Weaver_ASI.crypto.sophiac_manifold import SophiacManifold, GuardianSlot
        from Weaver_ASI.crypto.ingress_gate import Severity, SEVERITY_LABEL

        class PW:
            def __init__(s):
                s._state = {"reactor_temp_c": 180, "pressure_bar": 12.5,
                            "coolant_flow_lps": 4.2, "radiation_msv": 0.08}
                s._tick = 0; s._scram = False; s.event_log = []
            def tick(s):
                s._tick += 1
                import random; s._state["reactor_temp_c"] += random.gauss(0, 1.2)
                s._state["pressure_bar"] += random.gauss(0, 0.04)
                if s._tick == 4:
                    s._state["coolant_flow_lps"] = 1.8; s._state["reactor_temp_c"] = 255.0
                    s.event_log.append("⚠ coolant restriction → WARNING")
                if s._tick == 8:
                    s._state["coolant_flow_lps"] = 0.8; s._state["reactor_temp_c"] = 315.0
                    s.event_log.append("🔴 pump failure → CRITICAL")
                if s._tick == 10:
                    s._state["pressure_bar"] = 23.0; s._state["reactor_temp_c"] = 420.0
                    s.event_log.append("☠ pressure spike → FATAL")
                if s._scram:
                    s._state["reactor_temp_c"] = max(180, s._state["reactor_temp_c"] - 30)
                    s._state["pressure_bar"] = max(12.5, s._state["pressure_bar"] - 0.8)
                    s._state["coolant_flow_lps"] = min(4.2, s._state["coolant_flow_lps"] + 1)
            def apply_scram(s): s._scram = True; s.event_log.append("→ SCRAM applied")
            def snapshot(s): return dict(s._state)

        random.seed(7)
        world = PW()
        sensor = HardwareSensor("HW_THERM_01", world)
        reg = RealityRegistry()
        reg.register(sensor)
        chron = Chronicle()
        gate = IngressGate(reg)
        man = SophiacManifold()
        guard = GuardianSlot(man)
        k = AegisKernel(chron, gate, world, guard)
        agents = [OracleAgent(sensor), MitigationAgent(world),
                  EulerAgent(), GaussAgent(), NewtonAgent()]

        print(f"\n  Running simulation ({cycles} cycles)...")
        for c in range(cycles):
            world.tick()
            for agent in agents:
                intent = agent.propose(k.step, k.state)
                if intent:
                    k.apply(intent)

        replay_ok, _ = k.replay_verify()
        transitions = chron.events_of_type("SYS_LEVEL_TRANSITION")
        print(f"\n  Chronicle events: {len(chron)}")
        print(f"  Chain integrity: {'✓ VALID' if chron.verify() else '✗ BROKEN'}")
        print(f"  Replay equivalent: {'✓ PASS' if replay_ok else '✗ FAIL'}")
        print(f"  Severity transitions: {len(transitions)}")
        for ev in transitions:
            p = ev.payload
            print(f"    step {p['step']:3d}: {p['old_level']} → {p['new_level']}")
        print(f"  Final severity: [{gate.severity.name}]")
        print()


def main():
    """Interactive CLI mode."""
    # Build a minimal system for the CLI
    from Weaver_ASI.core.chronicle import Chronicle
    from Weaver_ASI.core.aegis_kernel import AegisKernel
    from Weaver_ASI.crypto.ingress_gate import IngressGate
    from Weaver_ASI.crypto.reality_registry import HardwareSensor, RealityRegistry
    from Weaver_ASI.crypto.sophiac_manifold import SophiacManifold, GuardianSlot

    class PW:
        def __init__(s):
            s._state = {"reactor_temp_c": 180, "pressure_bar": 12.5,
                        "coolant_flow_lps": 4.2, "radiation_msv": 0.08}
        def snapshot(s): return dict(s._state)

    world = PW()
    sensor = HardwareSensor("HW_THERM_01", world)
    registry = RealityRegistry()
    registry.register(sensor)
    chronicle = Chronicle()
    gate = IngressGate(registry)
    manifold = SophiacManifold()
    guardian = GuardianSlot(manifold)
    kernel = AegisKernel(chronicle, gate, world, guardian)

    cli = WeaverCLI(kernel, gate, chronicle, manifold, world)
    cli.run()


if __name__ == "__main__":
    main()
