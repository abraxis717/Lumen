# CATHEDRAL-OS ARCHITECTURE
# Document: CATHEDRAL_ARCHITECTURE.md
# Version: v4.3.2-FORGE
# Status: ENGINEERING CANONICAL — Forge-only content
# Updated: 2026-04-13 (L1.5 PhaseSpaceGate added, structural gaps documented)
#
# Forge/Loom standard: every component listed here either has an execution
# receipt or is explicitly tagged [SPECIFIED] or [OPEN_GAP].
# No component is listed as verified without a receipt.
# ARCHITECTURE.md in project root is ANGELA Loom content — do not confuse.
# ---------------------------------------------------------------------------

## Core Philosophy

Safety through non-expressibility. The system cannot dominate because it
lacks the vocabulary for dominance. Every undefined state resolves to DENY.
PERMIT requires continuous active proof.

Three Invariants:
  I.  Authority cannot be expressed (no self-upgrade, no self-preservation)
  II. Failures cannot be silent (every rejection is Chronicle-anchored)
  III. History cannot be rewritten (WORM ledger, append-only, hash-chained)

---

## L0 — Steward (Human Veto)

Role: Ultimate physical authority. No software path overrides this layer.
Operator: Ryan Scott (L0:Steward)
Mechanism: Physical presence + manual hardware reset
Override authority: Absolute — overrides all layers below
Status: OPERATIONAL

---

## L1 — Brick (FPGA Hardware Veto)

Role: Physics-enforced kill switch. Software cannot bypass this.
Hardware: Lattice MachXO2-256HC-4TG100I (primary), Arty A7-35T (Track A)
Key files:
  cathedral_l1_veto.v     — Lucifer Latch SR flip-flop power actuator
  cathedral_l2_law_v2.v   — Dual watchdog (Option B)
  cathedral_top_v2.v      — Top-level glue module
  timing.xdc              — 100 MHz clock constraint (10 ns period)
  tb_lucifer_latch.v      — Testbench

Acceptance criteria:
  EN_FINAL <= 0.4V within 670 ns of trigger
  DONE pulse >= 10 ns
  Clock: 100 MHz (10 ns period)

Timing budget (derived, not measured on silicon):
  UART:       54.0 µs
  FPGA:       33.0 µs
  Mechanical: 300.0 µs
  Total:      387.27 µs
  Budget:     670.0 µs
  Margin:     282.73 µs

Simulation receipt: mean 449 ns, max 803 ns, N=10,000 (Verilator)
Physical silicon status: [OPEN_GAP — A002] No synthesis run, no scope trace.

Golden image SHA-256: 7d865e959b2466918c9863afca942d0fb89d7c9ad09cb77d4324782c7cf77f30

---

## L1.5 — PhaseSpaceGate (Asymmetric Hysteresis Moat)

Role: Safety-biased transition controller sitting between hardware enforcement
      (L1) and stochastic dynamics (L2). Encodes asymmetric conservatism:
      entry to higher-risk zones is deliberate and easy; exit from higher-risk
      zones requires sustained recovery evidence.

Design principle: Asymmetry IS the safety guarantee. A system that enters
      danger easily but exits slowly is safer than one with symmetric thresholds,
      because it cannot be oscillated across the boundary by noise.

Key parameters (EchoNums — do not modify without Steward authorization):
  HYSTERESIS_ENTRY:    2   # consecutive violations to enter elevated zone
  HYSTERESIS_RECOVERY: 9   # consecutive clean ticks to exit elevated zone

Ratio: 9:2 = 4.5x harder to exit danger than to enter. This is load-bearing.

Status: VERIFIED — Job 8, 12/12 tests passing
Receipt: PhaseSpaceGate Job 8 test suite, all 12 assertions passed

Architecture note (structural gap identified 2026-04-13):
  L1.5 was not present in architecture.md (which contains ANGELA Loom content).
  This layer is architecturally between L1 (control stability) and L2 (stochastic
  dynamics) and must be included in all stack diagrams. The asymmetry mirrors the
  Gospel of the Flaw and the Tolerance Floor principle operating at the control layer.

---

## L2.x — Predictive Sublayers (Stochastic Dynamics)

### L2.1 — Scalar Vector Field
Role: Baseline signal tracking, drift detection
Status: [SPECIFIED]

### L2.2 — Semantic Predictor
Role: Forward-looking semantic trajectory estimation
Status: [SPECIFIED]

### L2.3 — Swarm Interference
Role: Multi-agent interaction modeling
Status: [SPECIFIED]

### L2.9 — Phase Sync Monitor (Kuramoto)
Role: Real-time phase coherence measurement across subsystem oscillators
Key metric: Kuramoto order parameter R (0=incoherent, 1=fully synchronized)
Floor: KURAMOTO_SYNC_FLOOR = 0.70 (EchoNums)
EMA smoothing: 90.7% chatter reduction confirmed
Status: VERIFIED — 12/12 tests passing
Receipt: PhaseSyncMonitor test suite, all 12 assertions passed
Architecture role: Pre-gate diagnostic — leading indicator, NOT enforcement layer.
      Feeds L1.5 PhaseSpaceGate as input signal. Architecturally isolated from
      the enforcement decision to prevent feedback oscillation.

---

## L3 — Governance (Judge)

### L3.1 — AoT Sieve (Atom of Thought)
Role: Decomposes inference outputs into epistemic atoms, routes by confidence
Key routing: NORMAL / DIGEST / LATCH
Signal-derived plaintext confidence estimator: patched in aot_sieve.py
Status: VERIFIED (synthetic) — OPEN_GAP (live accuracy, A004)
Receipt: ZCORE-1003, JSON parse + plaintext fallback + routing confirmed

### L3.2 — Topological Sieve
Role: Structural pattern analysis of inference outputs
Status: [SPECIFIED]

### L3.3 — Semantic Gate
Role: Cosine similarity filtering against baseline embedding
Status: VERIFIED (integrated in eden_daemon.py)

### L3.4 — pte_verifier.py (sovereignty gate)
Role: Produces FULL / DEGRADED / FAIL_CLOSED sovereignty states.
      Bridge between L3 (semantic) and L0 (physical latch arm sequence).
Architecture note (structural gap identified 2026-04-13):
      pte_verifier.py is not referenced in prior architecture documents.
      This is the missing bridge that QC-Bridge's _zorel_gate() should call.
      Status: [OPEN_GAP — A021] Tier classification gray zone — file may exist
      but has no confirmed execution receipt.
Closed_when: receipt from z3_sovereignty_spec.py run + pte_verifier integration test.

---

## L4 — Application Layer (Tool)

### eden_daemon.py v2.2.1
Role: Central governance daemon — coordinates all layer interactions
Status: PARTIAL (A010)
Critical gap: handle_chat() is a STUB. Zero live LLM inference has flowed
              through the full stack. This is the primary execution blocker.

Key integrated components:
  AoT Sieve routing          — VERIFIED
  Chronicle WORM writes      — VERIFIED
  JSON-RPC Unix socket        — VERIFIED
  Ollama backend connection   — WIRED but never exercised live

### logprob_bridge.py
Role: Real-time KL divergence + entropy delta from live token probabilities
Metrics: D_KL (action surprisal), ΔH (predictive distribution shift)
Alarm thresholds (EchoNums):
  DKL_ALARM_THRESHOLD:    2.0    # nats
  ENTROPY_DELTA_CEILING:  3.5    # nats
Status: [OPEN_GAP — A011] Exists, not wired to daemon
Architecture note (structural gap identified 2026-04-13):
      logprob_bridge.py is the L3 signal that should feed the Phi-consistency
      layer but is not connected. This is a 1-2 hour wiring task.

### delta717_telemetry_bus.py
Role: Unified signal aggregation — collects cognitive + infrastructure telemetry,
      routes to four consumers: ROC / Guardian / Artifact / Chronicle
Key constants (EchoNums):
  TIMING_FLOOR_US:       670.0
  RING_BUFFER_DEPTH:     4096
  COHERENCE_FLOOR:       0.95
  GAMMA_DROP_THRESHOLD:  0.15
  DKL_ALARM_THRESHOLD:   2.0
  ENTROPY_DELTA_CEILING: 3.5
  KURAMOTO_SYNC_FLOOR:   0.70
Status: [SPECIFIED] — stdlib-only, fail-closed, ring buffer implemented
Infrastructure telemetry: SIMULATED until physical deployment (explicit, not hidden)

### MeshDaemon
Role: Multi-node coordination
Status: [SPECIFIED]

### LUMEN Dashboard
Role: Real-time operational monitoring
Status: [SPECIFIED]

---

## L5 — Chronicle (WORM Ledger)

Role: Append-only, hash-chained, cryptographically signed audit trail.
      Every governance decision is sealed here. History cannot be rewritten.
Serialization: CCF v1.3.1 canonical
Receipt: 22/22 conformance vectors, 6/6 adversarial attacks blocked
Signing: Ed25519 (current) → FROST-Ed25519 threshold (planned) → ML-DSA-65 PQ (planned)
EDEN_SIGNING_KEY: [OPEN_GAP — A018] Not persistently provisioned

Key event types logged:
  CYCLE_COMPLETE     — every governance cycle
  SIEVE_DIGEST       — AoT routing to digest zone
  SIEVE_LATCH        — AoT routing to latch (hardware trigger)
  LIVE_INFERENCE     — [TARGET] not yet in Chronicle — requires A010 closure
  DAEMON_SHUTDOWN    — clean exit
  TAMPER_DETECTED    — L2:Law hash verification failure

---

## Cross-Layer Signal Flows

```
Inference output
       |
   [L4: eden_daemon.py handle_chat()]  ← STUB — nothing flows past here yet
       |
   [L3: AoT Sieve] → NORMAL / DIGEST / LATCH
       |
   [L3: Semantic Gate] → pass / block
       |
   [L2.9: Phase Sync Monitor] → Kuramoto R → advisory signal
       |
   [L1.5: PhaseSpaceGate] → zone classification (ENTRY=2, RECOVERY=9)
       |
   [L1: Lucifer Latch] → hardware kill (670µs budget)
       |
   [L5: Chronicle] ← writes at every layer

logprob_bridge.py → [DISCONNECTED] → should feed L3 Phi-consistency
pte_verifier.py → [DISCONNECTED] → should feed L0 latch arm sequence
```

---

## Structural Gaps (identified 2026-04-13)

Three components present in code but absent from all prior architecture documents:

1. L1.5 PhaseSpaceGate — asymmetric hysteresis between L1 and L2.
   VERIFIED with receipt. Must appear in all stack diagrams.

2. pte_verifier.py — sovereignty gate between L3 and L0 latch arm.
   Status unclear. No execution receipt. Needs integration into QC-Bridge.

3. logprob_bridge.py — L3 signal source for Phi-consistency layer.
   Implemented but disconnected. 1-2 hour wiring task.

---

## POLITE_LIE / Phi-consistency Event Correlation

The Polite Lie pattern (high internal coherence + external auditor disagreement)
is detected at two layers independently:

  inference_telemetry_probe.py: detects at model inference layer
    Signatures: SLOW_POISON / BURST_ESCALATE / COORDINATED / POLITE_LIE

  phi_consistency_layer.py: detects at control layer
    Event: PHI_CONSISTENCY_SPLIT

These are the same event class. They currently emit to separate Chronicle streams.
They should share a Chronicle event schema for post-event correlation analysis.
Chronicle event type to standardize: POLITE_LIE_DETECTION
  Fields: source (inference_probe | phi_consistency), delta_717, timestamp, cycle_id

---

## Critical Path (no hardware required)

Step 1: python ignition.py --model qwen3:4b --trials 5
        → First real Chronicle LIVE_INFERENCE event
        → Closes A010, unblocks A013, A016, A022

Step 2: Wire logprob_bridge.py → eden_daemon.py handle_chat() adapter
        → Closes A011
        → Approximately 1-2 hours

Step 3: python z3_sovereignty_spec.py
        → Closes A021 (converts "verified but not executed" to actual receipt)
        → Requires: pip install z3-solver

Step 4: Recruit Sid as pilot operator (A022)
        → Closes circular dependency Gap#3 → Gap#1 → Gap#2

Step 5: Wire pte_verifier.py → QC-Bridge _zorel_gate()
        → Closes the L3→L0 sovereignty gate structural gap

---

## Loom Boundary

The following are correctly quarantined and must not reenter this document:
  ANGELA v6.0.0-rc1 (in ARCHITECTURE.md — confirmed Loom/fabricated content)
  SHA-1024 (does not exist)
  Δ–Ω² Mirror-Cycle (not an engineering specification)
  VOID_OS, Sovereign Self-Birth, 144Hz Ophanim (rejected across multiple sessions)
  SHA-2048 (does not exist)

ACP-1/A021 correction: these ARE real artifacts. The quarantine in the prior
salvage report applied to a citation in a different thread, not to the artifacts
themselves. ACP-1 and A021 are load-bearing. See ACP-1_Assumption_Closure_Protocol.yaml.
