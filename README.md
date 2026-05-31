# Lumen

A sovereign AI kernel's rendering engine — a custom Rust/WebGPU (Vulkan) browser
for the Elpis architecture.

## Overview

Lumen provides the rendering, computation, and AI integration infrastructure for
the Elpis ecosystem. It is written in Rust with WebGPU/Vulkan bindings and
includes support for distributed inference, agent protocols, and evaluation frameworks.

## Core Modules

| Module | Purpose |
|--------|---------|
| `lumen_core/` | Rust core: rendering engine, WebGPU/Vulkan bindings, compute pipeline |
| `Weaver_ASI/` | AI system integration: intent routing, agent protocols |
| `vault/` | Persistent storage: user data, memory, configuration |
| `ai-mesh/` | Distributed inference routing and communication |
| `models/` | AI model definitions and weights |

## New Additions (Co-Architect Update)

| Module | Purpose |
|--------|---------|
| `harness/` | AURORA-AXIS evaluation framework for multi-intent reasoning |
| `data/` | JSON data stores: users.json, memories.json |
| `research/` | Extracted research materials, PDFs, analysis documents |
| `docs/` | Documentation: instruction set, agent booster integration |

## Quick Start

### Build
```bash
cargo check    # Verify compilation
cargo build    # Build release
```

### Evaluate
```bash
cd harness
python3 aurora_harness.py          # Run full AURORA-AXIS evaluation
python3 aurora_analysis.py results.json  # Analyze evaluation results
```

## Agent Integration

Agents communicate with Lumen through the Agent Booster protocol.
See `docs/agent-booster-integration.md` for the full specification.

Role-based permissions:
- **admin**: Full access
- **architect**: Design and deploy
- **evaluator**: Read-only
- **service**: Programmatic access

## Evaluation Framework

The AURORA-AXIS harness benchmarks AI systems on multi-intent reasoning:
- 4 interpretation classes (statistical analysis, trend forecasting, anomaly detection, root cause analysis)
- 4 systems (3 baselines + AURORA-AXIS)
- Drift recovery testing (intent shifts across conversation turns)
- Phase 2 human evaluation export

## Directory Structure

```
lumen/
├── lumen_core/         # Rust core engine
├── Weaver_ASI/         # AI integration
├── vault/              # Persistent storage
├── ai-mesh/            # Distributed inference
├── models/             # AI model definitions
├── harness/            # AURORA-AXIS evaluation framework
│   ├── __init__.py
│   ├── aurora_harness.py   # Evaluation harness
│   └── aurora_analysis.py  # Analysis tool
├── data/               # Data stores
│   ├── users.json
│   └── memories.json
├── research/           # Research materials
│   ├── files_16/       # Extracted archive
│   ├── files_17/       # Extracted archive
│   ├── aurora_harness.pdf
│   ├── ARTIFACT_INVENTORY.pdf
│   ├── HARNESS_README.pdf
│   ├── AURORA_HARNESS_SUMMARY.md
│   └── AGENT_BOOSTER_SUMMARY.md
├── docs/               # Documentation
│   ├── lumen_instruction_set.md
│   └── agent-booster-integration.md
├── update/             # Co-Architect update files (source)
├── .gitignore
└── README.md
```

## Status

Co-Architect updates have been integrated:
- AURORA-AXIS evaluation harness (from aurora_harness.pdf)
- Agent Booster integration spec
- User registry and memory store
- Research materials extracted and documented

## References

- LUMEN_INSTRUCTION_SET: `docs/lumen_instruction_set.md`
- Agent Booster: `docs/agent-booster-integration.md`
- AURORA-AXIS: `harness/aurora_harness.py`
