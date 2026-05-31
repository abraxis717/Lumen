# Lumen Instruction Set

## Overview
Lumen is a sovereign AI kernel's rendering engine — a custom Rust/WebGPU (Vulkan)
browser for the Elpis architecture.

## Core Modules
- `lumen_core/` — Rust core: rendering engine, WebGPU/Vulkan bindings, compute pipeline
- `Weaver_ASI/` — AI system integration: intent routing, agent protocols
- `vault/` — Persistent storage: user data, memory, configuration
- `ai-mesh/` — Distributed inference routing and communication
- `models/` — AI model definitions and weights

## New Additions (Co-Architect Update)
- `harness/` — AURORA-AXIS evaluation framework for multi-intent reasoning
- `data/` — JSON data stores: users.json, memories.json
- `research/` — Extracted research materials, PDFs, analysis documents

## Agent Integration
Agents interact with Lumen through the Agent Booster protocol.
Role-based permissions: admin, architect, evaluator, service.

## Evaluation
Run `harness/aurora_harness.py` to benchmark intent routing systems.
Run `harness/aurora_analysis.py results.json` to analyze results.

## Build
```bash
cargo check    # Verify compilation
cargo build    # Build release
```

## Configuration
Config files stored in `vault/config/`.
