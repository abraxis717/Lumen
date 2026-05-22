# Lumen -- Institutional Cognition OS

A governed, safety-gated reasoning system combining epistemic memory, constitutional validation,
and layered safety filters. Lumen structures LLM outputs through a decision boundary that enforces
hard safety invariants, hash-chain provenance, and multi-agent deliberation.

**License:** Apache 2.0
**Remote:** <https://github.com/abraxis717/Lumen>
**Submodule:** ai-mesh (P2P mesh networking)

---

## Overview

Lumen is an institutional cognition operating system composed of three main subsystems:

- **Weaver_ASI** -- Governed institutional memory with multi-factor decay, constitutional
  validation, epistemic belief graphs, and council-based consensus deliberation.
- **Lumen (lumen_core/)** -- Safety filters, decision engines, cycle-based reasoning, and a
  Flask microservice layer for HTTP inference.
- **ai-mesh/** -- Distributed peer-to-peer mesh networking (git submodule).

All components are bootable via the Vault plugin manager (`vault/vault.py`).

---

## Architecture

```
+-----------------------------------------------------------------------+
|  PRESENTATION / SERVICE LAYER                                         |
|  lumen_service.py      -- Unified Flask microservice (port 5100)      |
|  guardian_service.py   -- Standalone safety guard + audit log         |
+-----------------------------------------------------------------------+
|  DECISION ENGINE                                                      |
|  decision_engine.py    -- 5-axis SignalNode, weighted scoring         |
|                          Hard rules: risk>0.7 -> reject,              |
|                          contradiction>0.6 -> revise, score>0.65->accept|
+-----------------------------------------------------------------------+
|  CYCLE REASONING SUBSYSTEM                                            |
|  lumen_cycles.py       -- PrimeCycle core (knowledge units)           |
|  lumen_branching.py    -- Hypothesis branching engine                 |
|  lumen_signatures.py   -- MDL cycle signatures                        |
|  lumen_adaptive.py     -- Evolutionary weight tuning                  |
|  lumen_meta.py         -- Meta-cycles (cross-domain reasoning)        |
|  lumen_integration.py  -- Hermes adapter + ai-mesh router             |
|  lumen_pcms_core.py    -- Probabilistic Concept Memory System         |
|  lumen_persistence.py  -- SQLite persistence layer                    |
|  E8E8_Manifold.py      -- Kuramoto coupling coherence                 |
+-----------------------------------------------------------------------+
|  SAFETY GATE (Cathedral-OS)                                           |
|  safety_filter.py      -- SafeState predicate + CBF projection        |
|  guardian_service.py   -- Pre/post risk check + audit log             |
|  ignition.py           -- First live inference path (Path A)          |
|                          [QUARANTINED: experimental, not production]  |
|  cathedral_kernel.py   -- Control event schema + mode classify        |
|  kernel_controller.py  -- LQR controller with CBF enforcement         |
|  control_event.py      -- Control event dataclass                     |
|  control_replay.py     -- Chronicle-based replay verification         |
+-----------------------------------------------------------------------+
|  WEAVER_ASI (Epistemic Memory & Governance)                           |
|  core/         -- AegisKernel, Chronicle (WORM ledger), Event         |
|  epistemics/   -- EpistemicGraph, BeliefNode, Arbitration, Provenance |
|  memory/       -- MemoryGovernor (stratum assignment & decay),        |
|                  DecayModels, Retrieval, Strata                       |
|  council/      -- GovernedCouncil, LumenAgent, Oracle/Steward/        |
|                  Mitigation/AdversarialSwarm agents                   |
|  constitutional/ -- ConstitutionalKernel, Axioms, Gate                |
|  crypto/       -- IngressGate, RealityRegistry, SophiacManifold       |
|  federation/   -- DistributedConsensus, GraphSync, TrustExchange      |
|  observability/ -- DriftMonitor, Lineage                              |
|  orchestrators/ -- MasterOrchestrators (sovereign, graded, recovery,  |
|                    anchored)                                          |
|  cli/          -- Weaver CLI                                          |
+-----------------------------------------------------------------------+
|  VAULT (Plugin Management)                                            |
|  vault.py        -- Plugin discovery, validation, topological compile |
|  plugins/        -- Plugin directories (vault.json per plugin)        |
+-----------------------------------------------------------------------+
```

---

## Directory Structure

```
Lumen/
├── lumen_core/                  # Inference microservice & safety
│   ├── lumen_service.py         # Unified Flask API (port 5100)
│   ├── decision_engine.py       # Signal scoring + decision boundary
│   ├── guardian_service.py      # Pre/post risk checking + audit
│   ├── safety_filter.py         # SafeState predicate + CBF
│   ├── ignition.py              # Live inference (experimental/quarantined)
│   ├── lumen_pcms_core.py       # Probabilistic Concept Memory System
│   ├── lumen_persistence.py     # SQLite backend
│   ├── lumen_cycles.py*         # PrimeCycle reasoning substrate
│   ├── lumen_branching.py       # Hypothesis branching
│   ├── lumen_signatures.py      # MDL cycle signatures
│   ├── lumen_adaptive.py        # Evolutionary weight tuning
│   ├── lumen_meta.py            # Meta-cycles
│   ├── lumen_integration.py     # Hermes + ai-mesh adapters
│   ├── cathedral_kernel.py      # Control event schema
│   ├── kernel_controller.py     # LQR + CBF enforcement
│   ├── control_event.py         # Control event dataclass
│   ├── control_replay.py        # Replay verification
│   ├── lumen_stability.py       # Stability analysis
│   ├── lumen_unified.py         # Unified interface
│   ├── E8E8_Manifold.py         # Kuramoto coupling coherence
│   ├── README_architecture.md   # Detailed architecture docs
│   └── CATHEDRAL_ARCHITECTURE.md# Cathedral-OS architecture
├── Weaver_ASI/                  # Governed institutional memory
│   └── Weaver_ASI/
│       ├── __main__.py          # Package entry point
│       ├── core/                # AegisKernel, Chronicle, Event
│       ├── epistemics/          # EpistemicGraph, BeliefNode, Arbitration
│       ├── memory/              # MemoryGovernor, DecayModels, Retrieval
│       ├── council/             # GovernedCouncil, Agent hierarchy
│       ├── constitutional/      # ConstitutionalKernel, Axioms
│       ├── crypto/              # IngressGate, RealityRegistry
│       ├── federation/          # DistributedConsensus, GraphSync
│       ├── observability/       # DriftMonitor, Lineage
│       ├── orchestrators/       # Master orchestrators (4 modes)
│       └── cli/                 # CLI tools
├── ai-mesh/                     # P2P mesh networking (git submodule)
├── vault/                       # Plugin management
│   └── vault.py                 # Discover, validate, compile plugins
├── .gitignore
├── .gitmodules
├── LICENSE                      # Apache 2.0
└── README.md                    # This file
```

---

## Key Components

### Lumen Core (Safety & Decision)

| Component | Purpose |
|-----------|---------|
| `SignalNode` | Five-axis signal: coherence, utility, risk, contradiction, cycle_coherence |
| `DecisionEngine` | Accepts signals, computes weighted score, enforces hard invariants |
| `GuardianService` | Pre/post risk checking with SQLite audit log |
| `SafetyFilter` | SafeState predicate + Control Barrier Function projection |
| `PrimeCycle` | Fundamental knowledge unit: nodes + edges + stability + activation energy |
| `PCMS` | Probabilistic Concept Memory: entities, Beta-beliefs, entropy, risk scoring |
| `Chronicle` | WORM (Write-Once-Read-Many) event ledger with SHA-256 chain |

### Weaver_ASI (Memory & Governance)

| Component | Purpose |
|-----------|---------|
| `EpistemicGraph` | Belief graph with contradiction detection |
| `MemoryGovernor` | Stratum assignment + multi-factor decay |
| `ConstitutionalKernel` | Axiom-based violation checking |
| `GovernedCouncil` | Multi-agent consensus deliberation |
| `Chronicle` | Append-only, hash-chained event ledger |
| `DriftMonitor` | Entropy tracking + concept drift detection |
| `MasterOrchestrators` | Four boot modes: sovereign, graded, recovery, anchored |

### Vault (Plugin Manager)

Discovers, validates, and compiles AI component plugins into launch scripts.

---

## Quick Start

### Prerequisites

- Python 3.10+
- `numpy`, `scipy`, `flask` (core dependencies -- no GPU or transformers required)
- Optional: llama.cpp server at `http://localhost:8080` for live inference

### 1. Clone and initialize

```bash
git clone https://github.com/abraxis717/Lumen.git
cd Lumen
git submodule update --init --recursive
git config core.hooksPath .githooks
```

### 2. Install dependencies

```bash
pip install numpy scipy flask requests
```

### 3. Run the Weaver_ASI orchestrator

```bash
# Sovereign mode (full deliberation)
cd Weaver_ASI && python -m Weaver_ASI sovereign

# Graded mode
python -m Weaver_ASI graded

# Recovery mode (post-failure restoration)
python -m Weaver_ASI recovery

# Anchored mode (fixed reference frame)
python -m Weaver_ASI anchored

# CLI mode
python -m Weaver_ASI cli
```

### 4. Start the Flask microservice

```bash
cd lumen_core
python lumen_service.py
# Service listens on http://localhost:5100
```

### 5. Query the service

```bash
curl -X POST http://localhost:5100/check \
  -H "Content-Type: application/json" \
  -d '{"run_id": "test-001", "intent": "analyze", "inputs": ["Explain quantum superposition."]}'
```

### 6. Compile plugins via Vault

```bash
cd vault
python vault.py list
python vault.py validate <plugin-name>
python vault.py compile
# Generates plugins/compiler-output/start_all.sh
bash plugins/compiler-output/start_all.sh
```

---

## Decision Rules

The decision engine enforces these hard invariants (applied in priority order):

1. **risk > 0.70** --> **reject** (absolute, never overridden)
2. **contradiction > 0.60** --> **revise** (conflict needs resolution)
3. **score > 0.65** --> **accept** (strong signal)
4. **else** --> **revise** (weak signal, needs more info)

---

## Constitutional Axioms

Weaver_ASI enforces the following default axioms:

- No event enters the Chronicle without cryptographic provenance.
- Reality cannot be forged by rogue actors or hallucinations.
- Physical healing does not automatically restore system trust.
- The NoBenOverride Invariant: human authorization is required to clear FATAL latches.
- The ASI degrades gracefully into wisdom rather than panicking.
- All beliefs must be traceable to their source events.
- Contradictions must be resolved through arbitration, not suppression.

---

## Current State

| Area | Status |
|------|--------|
| Decision engine | Operational -- full 5-axis scoring pipeline |
| Cycle core | Operational -- PrimeCycle, composition, contradiction detection |
| PCMS | Operational -- IdentityClustering, BetaBelief, EntropyMonitor, RiskEngine |
| Safety gate | Operational -- GuardianService keyword-based, SafetyFilter CBF |
| Lumen Service (Flask) | Operational -- /check, /audit, /cycles endpoints |
| Persistence | Operational -- SQLite with WAL mode |
| Weaver_ASI orchestrators | Operational -- 4 boot modes, constitutional validation |
| Epistemic graph | Operational -- belief graph + arbitration |
| Memory governor | Operational -- stratum assignment, multi-factor decay |
| Vault plugin manager | Operational -- discover, validate, compile |
| ai-mesh submodule | Present -- submodule initialized |
| ignition.py | **QUARANTINED** -- experimental, first live inference path, bypasses missing CGIR modules |
| E8E8_Manifold | Stub -- Kuramoto coupling coherence only |
| CGIR bridge modules | Absent -- ignition.py Path A explicitly bypasses these |

---

## Documentation

- `lumen_core/README_architecture.md` -- Complete system architecture overview
- `lumen_core/CATHEDRAL_ARCHITECTURE.md` -- Cathedral-OS layered architecture
- `LUMEN_INSTRUCTION_SET` -- Full integration plan (untracked local document)

---

## License

Apache License 2.0. See `LICENSE` for details.
