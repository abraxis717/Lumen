# Lumen — Sovereign AI Kernel

A governed AI reasoning system with constitutional validation, epistemic graph
memory, and live GGUF model inference — all running on a single machine.

**Current state:** Live multi-agent inference with contradiction detection and
deterministic chronicle. See [STATUS.md](STATUS.md) for detailed gap analysis.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              Lumen Kernel — Live Inference Layer                │
│  (Multi-agent deliberation with constitutional gates)           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  Oracle  │  │  Euler   │  │  Gauss   │  │  Newton  │      │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │             │             │             │              │
│       │     ┌───────┴─────────────┴─────────────┴──────┐       │
│       │     │              GovernedCouncil              │       │
│       │     │   (Contradiction detection + arbitration) │       │
│       │     └───────┬─────────────┬─────────────┬──────┘       │
│       │             │             │             │              │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐      │
│  │Mitigation│  │  Lumen   │  │Safety    │  │Steward   │      │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │      │
│  └────┬─────┘  └──────────┘  └──────────┘  └────┬─────┘      │
│       │                                          │            │
│       └──────────┬───────────────────────────────┘            │
│                  │                                             │
│       ┌──────────┴──────────────────────────────────┐         │
│       │         Memory Governor                     │         │
│       │  (Epistemic Graph + Constitutional Kernel)  │         │
│       └──────────┬──────────────────────────────────┘         │
│                  │                                             │
│       ┌──────────┴──────────────────────────────────┐         │
│       │          Chronicle                          │         │
│       │  (SQLite WAL / JSONL append-only log)       │         │
│       └─────────────────────────────────────────────┘         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │ Live GGUF Model  │    │ Materialize      │                  │
│  │ (Qwen3.5-0.8B)   │    │ Pipeline         │                  │
│  │ 512MB quantized  │    │ (Obsidian/CDC/   │                  │
│  │ llama-cpp-python │    │  Vector Sync)    │                  │
│  └──────────────────┘    └──────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Run the anchored orchestrator (live GGUF)

```bash
cd /mnt/primesauce/Garden_OS/Lumen
python3 kernel/orchestrators/master_orchestrator_anchored.py
```

This loads the Qwen3.5-0.8B GGUF model and runs 10 simulated cycles
with the OracleAgent producing claims via live inference.

### Run with SQLite chronicle

```bash
python3 kernel/orchestrators/master_orchestrator_anchored.py --sqlite
```

### Run the materialization pipeline

```bash
python3 -m lumen.materialize.run_pipeline \
    --vault-path /tmp/lumen-vault \
    --sqlite chronicle.db \
    --vector-backend json
```

### Run tests

```bash
python3 test_live_inference.py
python3 test_obsidian.py
python3 test_cdc.py
python3 test_vector.py
python3 -m kernel.test_harness
python3 -m kernel.core.test_sqlite_chronicle
```

## Components

### kernel/

| Directory | Description |
|---|---|
| `core/` | Chronicle (JSONL/SQLite), Event dataclass, AegisKernel, replay engine |
| `constitutional/` | ConstitutionalKernel — validates claims against axioms, amendment DAG |
| `crypto/` | IngressGate, SophiacManifold, steward registry |
| `council/` | OracleAgent, EulerAgent, GaussAgent, NewtonAgent, GovernedCouncil, safety agents |
| `epistemics/` | EpistemicGraph, BeliefNode, ArbitrationEngine, contradiction detection |
| `memory/` | MemoryGovernor, StratifiedRetriever, multi-factor decay model |
| `mobile/` | MobileModel (GGUF via llama-cpp), phone bootstrap |
| `observability/` | LineageTracker, GovernanceDriftMonitor |
| `federation/` | (Phase 3.5 stubs: graph sync, intergraph arbitration, trust exchange) |

### lumen/

| Module | Description |
|---|---|
| `materialize/obsidian.py` | Projects chronicle events → Obsidian vault (markdown + MOC) |
| `materialize/cdc.py` | CDC outbox — publishable event stream to SQLite |
| `materialize/vector_sync.py` | Vector store sync (Qdrant/Chroma/JSON) for semantic search |
| `materialize/run_pipeline.py` | CLI pipeline runner (vault + CDC + vectors) |

## Model Requirements

| Component | Requirement |
|---|---|
| OracleAgent (live) | `llama-cpp-python` + GGUF model (`Qwen3.5-0.8B-Q4_K_M.gguf`) |
| OracleAgent (mock) | No external deps |
| Materialize | No external deps (JSON fallback) |
| Vector sync | `qdrant-client` (optional, JSON fallback) |

## Known Limitations

This system is a research prototype running on trusted hardware. The following
limitations are explicit and intentional:

- **Python-only safety.** Safety checks (constitutional validation, ingress gate)
  are pure Python and can be bypassed by a privileged process with filesystem
  access. They do not provide cryptographic or memory-safety guarantees.

- **No hardware root of trust.** There is no TPM, Secure Boot, or signed-binary
  enforcement. The chronicle's append-only property relies on application-level
  discipline, not hardware attestation.

- **Decision thresholds are gameable.** In adversarial settings, a sufficiently
  motivated agent can produce claims that fall below the constitutional gate's
  rejection threshold. The gate is a heuristic, not a proof.

- **Simulation-only on current hardware.** Live inference uses a 0.8B GGUF model
  quantized to Q4_K_M (512 MB). Larger models (7B+) and real distributed
  deployments are not yet supported.

- **No formal verification.** Decision rules, axiom interpretations, and
  arbitration logic have not been formally verified against a specification.

See [STATUS.md](STATUS.md) for the full gap table and phase-by-phase status.

## Next Hardening Phase

The following hardening measures are planned for post-Phase-4:

| Area | Approach | Priority |
|---|---|---|
| Rust sidecar | Move critical safety checks (gate, validator) to Rust WASM/eBPF for memory safety | High |
| Signed binaries | Package kernel as Nuitka-compiled binary to prevent trivial code tampering | Medium |
| Formal verification | Integrate Z3 or similar for decision-rule proofs | Low |
| FPGA future | Hardware-rooted chronicle notarization (TPM/FPGA hybrid) | Long-term |

## Testing

The test suite covers the governance membrane, SQLite chronicle, materialization,
and live swarm inference. Run from the project root:

```bash
python3 -m kernel.test_harness          # Governance membrane (veto + admit)
python3 -m kernel.core.test_sqlite_chronicle   # SQLite WAL round-trip
python3 -m lumen.materialize.run_pipeline --vault-path /tmp/vault --sqlite chronicle.db --vector-backend json
```

## License

All code in this repository is provided as-is for research and evaluation.
