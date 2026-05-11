# Lumen — Sovereign AI Kernel

A governed AI reasoning system with constitutional validation, epistemic graph
memory, and live GGUF model inference — all running on a single machine.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Weaver ASI Orchestrator                      │
│  (Phase 3: LLM-backed Governed Claims)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  Oracle  │  │  Euler   │  │  Gauss   │  │  Newton  │      │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │             │             │             │              │
│       │     ┌───────┴─────────────┴─────────────┴──────┐       │
│       │     │              Conductor                     │       │
│       │     │   (Simulation loop with governance)        │       │
│       │     └───────┬─────────────┬─────────────┬──────┘       │
│       │             │             │             │              │
│  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐      │
│  │Mitigation│  │  Lumen   │  │Safety    │  │Council   │      │
│  │  Agent   │  │  Agent   │  │  Agent   │  │Deliberation│     │
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
```

## Components

### kernel/

| Directory | Description |
|---|---|
| `core/` | Chronicle (JSONL/SQLite), Event dataclass, AegisKernel |
| `constitutional/` | ConstitutionalKernel — validates claims against axioms |
| `crypto/` | IngressGate, RealityRegistry, SophiacManifold, AegisKernel |
| `council/` | OracleAgent, Math/Physics agents, GovernedCouncil, MitigationAgent |
| `epistemics/` | EpistemicGraph, BeliefNode, governance relationships |
| `memory/` | MemoryGovernor, StratifiedRetriever, stratum definitions |
| `mobile/` | MobileModel (GGUF wrapper), LLM client adapter |
| `observability/` | LineageTracker, GovernanceDriftMonitor |

### lumen/

| Module | Description |
|---|---|
| `materialize/obsidian.py` | Projects chronicle → Obsidian vault (markdown + MOC) |
| `materialize/cdc.py` | CDC outbox — publishable event stream |
| `materialize/vector_sync.py` | Vector store sync (Qdrant/Chroma/JSON) |
| `materialize/run_pipeline.py` | CLI pipeline runner |

## Model Requirements

| Component | Requirement |
|---|---|
| OracleAgent (live) | `llama-cpp-python` + GGUF model |
| OracleAgent (mock) | No external deps |
| Materialize | No external deps (JSON fallback) |
| Vector sync | `qdrant-client` (optional, JSON fallback) |

## Status

- **Phase 1**: Core kernel, constitution, membrane, SQLite WAL, mobile GGUF loader ✓
- **Phase 2**: Materialization pipeline (Obsidian, CDC, Vector sync) ✓
- **Phase 3**: Live GGUF inference through governance membrane ✓
