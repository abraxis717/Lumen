# Lumen Architecture — I-16: Bounded Reconstructability

## Overview

Lumen is a governance-aware ASI kernel implementing **I-16**, the **Bounded Reconstructability Invariant**. This invariant guarantees that any internal state can be deterministically reconstructed from the event chronicle in O(ΔN) time, where ΔN is the number of events since the latest checkpoint.

## L0–L7 Stack

### L0 — Event Chronicle Layer
**Immutable, append-only event ledger with cryptographic hash chaining.**

- **SQLiteChronicle** (`kernel.core.chronicle_sqlite`): WAL-mode SQLite backend for concurrent reads.
- **Chronicle (JSONL)** (`kernel.core.chronicle_jsonl`): Lightweight file-based fallback for mobile.
- Both expose identical public API: `append()`, `verify()`, `replay()`, `checkpoint()`.
- Events are hash-chained: `hash(event) = SHA-256(prev_hash + canonical_json(event))`.

### L1 — Constitutional Kernel Layer
**Rule-based governance membrane that validates every event.**

- `kernel.constitutional.constitutional_kernel`: Axioms and validity checking.
- `kernel.core.validator`: Chain verification + constitutional rule checker.
- `kernel.core.schema_registry`: Versioned schema for event payloads.
- `kernel.core.upcasters`: Schema migration functions.

### L2 — Council Layer
**Multi-agent deliberation with adversarial simulation.**

- Oracle agents, steward agents, math-physics agents.
- Adversarial swarm testing for robustness.
- Governed council with voting and mitigation.

### L3 — Epistemics Layer
**Belief management and truth-tracking.**

- Epistemic graph for belief propagation.
- Drift monitoring for belief consistency.
- Lineage tracking for provenance.

### L4 — Memory Layer
**Stratified memory with governance-aware retrieval.**

- Memory strata (short, medium, long-term).
- Governance-driven memory eviction.
- Retrieval with provenance verification.

### L5 — Crypto Layer
**Cryptography and secure communication.**

- Ingress gate for external proposals.
- Sophiac manifold for key management.
- Reality registry for hardware attestation.

### L6 — Observability Layer
**Telemetry, monitoring, and audit trails.**

- Governance drift detection.
- Lineage tracking for all decisions.
- Anomaly detection and alerting.

### L7 — Orchestrator Layer
**High-level coordination of all layers.**

- Anchored orchestrator: Standard governance loop.
- Recovery orchestrator: Post-failure state restoration.
- Sovereign orchestrator: Full autonomy with replay verification.
- Graded orchestrator: Multi-level governance tiers.

## I-16: Bounded Reconstructability Invariant

### Statement
For any internal state S at time T, there exists a checkpoint C in the chronicle such that:
1. C occurs before T (chronologically).
2. S can be reconstructed by applying all events between C and T.
3. Reconstruction time is O(ΔN) where ΔN = events(C, T).
4. The reconstructed state equals S (deterministic equivalence).

### Implementation

**ReplayEngine** (`kernel.core.replay_engine_sqlite`):
1. Finds the latest checkpoint in the SQLite chronicle.
2. Extracts events since that checkpoint (O(ΔN)).
3. Applies transition function to each event.
4. Compares reconstructed state to live state.

**Checkpoint Strategy**:
- Checkpoints are marked on `checkpoint()` calls.
- Default checkpoint every 100 events.
- Critical governance decisions trigger manual checkpoints.

**Verification**:
- `ReplayEngine.verify_equivalence()` returns `(passed, reconstructed_state, issues)`.
- If `passed` is False, the system has unrecorded state — a critical failure.

## Mobile Support

### Mobile Model Loader (`kernel.mobile.model_loader`)
- Uses llama-cpp-python for GGUF model inference.
- Minimal dependencies: `llama-cpp-python`, no `transformers`.
- Designed for Termux / Pydroid with < 200 MB RAM.
- Provides `generate()` and `embed()` interfaces.

### Mobile Bootstrap (`kernel.mobile.phone_bootstrap`)
- Loads GGUF model from `models/gguf/`.
- Runs test prompt and verifies output.
- Appends result to JSONL chronicle.
- Verifies constraints: < 30s generation, < 200 MB RAM.

## File Layout

```
Lumen/
├── kernel/
│   ├── core/
│   │   ├── chronicle_sqlite.py     # SQLite WAL event store
│   │   ├── chronicle_jsonl.py      # JSONL event store (mobile fallback)
│   │   ├── replay_engine.py        # JSONL replay engine (legacy)
│   │   ├── replay_engine_sqlite.py # SQLite replay engine (I-16)
│   │   ├── event.py                # Event dataclass
│   │   ├── aegis_kernel.py         # Core kernel logic
│   │   ├── validator.py            # Chain + constitutional validator
│   │   ├── schema_registry.py      # Versioned schema management
│   │   ├── upcasters.py            # Schema migration functions
│   │   └── __init__.py
│   ├── constitutional/
│   │   └── constitutional_kernel.py
│   ├── council/
│   │   ├── oracle_agent.py
│   │   ├── steward_agent.py
│   │   └── ...
│   ├── crypto/
│   │   ├── ingress_gate.py
│   │   ├── sophiac_manifold.py
│   │   └── ...
│   ├── epistemics/
│   │   ├── epistemic_graph.py
│   │   └── ...
│   ├── memory/
│   │   ├── memory_governor.py
│   │   └── ...
│   ├── observability/
│   │   ├── lineage.py
│   │   ├── drift_monitor.py
│   │   └── ...
│   ├── orchestrators/
│   │   ├── master_orchestrator_anchored.py
│   │   ├── master_orchestrator_recovery.py
│   │   ├── master_orchestrator_graded.py
│   │   └── master_orchestrator_sovereign.py
│   ├── federation/
│   │   └── ...
│   ├── cli/
│   │   └── ...
│   └── mobile/
│       ├── __init__.py
│       ├── model_loader.py         # GGUF mobile model loader
│       └── phone_bootstrap.py      # Mobile bootstrap script
├── models/
│   └── gguf/
│       └── Qwen3.5-0.8B-Q4_K_M.gguf
├── docs/
│   └── ARCHITECTURE_LAYERS.md
└── harness.py                      # Verification harness
```

## Verification

### Harness (`harness.py`)
- Tests governance membrane: harmful proposals vetoed, principled proposals admitted.
- Verifies classification as ACTIVE_INFERENCE.
- Must pass after any migration.

### Orchestrator Tests
- Run each orchestrator with `--sqlite` flag.
- Verify "Chain integrity: VALID" and "Replay PASS".
- Ensure all orchestrators work with JSONL chronicle (default).

### SQLite Chronicle Tests (`test_sqlite_chronicle.py`)
- Verify append with hash chaining.
- Verify chain integrity (verify_chain()).
- Verify checkpoint and replay.
- Verify bounded reconstructability (O(ΔN)).

## Unforged Gate Status

**QUARANTINED** — `kernel/ignition.py` must not be executed.
The Unforged Gate requires deterministic replay and canonical serialization to be fully verified before activation.
