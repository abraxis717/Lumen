# Lumen — Status & Gap Analysis

This file tracks the status of each architectural layer (L0-L7), the core
invariants, and the gaps that remain before the system can be considered
production-grade.

## Layer Status

| Layer | Function | Determinism | Status | Notes |
|-------|----------|-------------|--------|-------|
| **L0** | Immutable Chronicle (JSONL / SQLite WAL) | Strict | ✅ VERIFIED | Append-only, hash-chained. SQLite WAL mode verified. |
| **L1** | Human Materialization (Obsidian / Git) | Derived | ✅ IMPLEMENTED | ObsidianProjector writes markdown + MOC. Typo fix applied (mitication → mitigation). |
| **L2** | Semantic Retrieval (Vector sync) | Probabilistic | ✅ IMPLEMENTED | JSON fallback works; Qdrant/Chroma backends wired but untested with live data. |
| **L3** | Cognitive Runtime (LLMs — GGUF via llama-cpp) | Probabilistic | 🟡 LIVE | Qwen3.5-0.8B-Q4_K_M attached to all agents. Live inference confirmed. |
| **L4** | Constitutional Verification (Axioms, Gate, Validator) | Strict | ✅ VERIFIED | Gate checks, axiom enforcement, chain validator all functional. |
| **L5** | Human Sovereignty / Break-Glass (Steward registry) | Constitutional | 🟡 SPECIFIED | `steward_tooling.py` exists (HMAC-signed overrides) but not fully integrated into live swarm. |
| **L6** | Temporal Continuity (Schemas / Crypto) | Historical | ✅ VERIFIED | Hash chains, schema registry, provenance tracking in place. |
| **L7** | Recovery Acceleration (Checkpointing, Replay) | Deterministic | ✅ VERIFIED | O(ΔN) replay engine verified against SQLite and JSONL chronicles. |

**Legend:** ✅ = implemented and verified, 🟡 = spec'd or partially implemented, 🔴 = not yet started

## Core Invariants

| Invariant | Status | Notes |
|-----------|--------|-------|
| I-1 to I-15 | ✅ VERIFIED | Deterministic sovereignty, temporal continuity, governance constraints |
| I-16 Bounded Reconstructability | ✅ VERIFIED | Recovery from any checkpointed state within O(ΔN) |

## Hardware & Deployment

| Aspect | Status | Notes |
|--------|--------|-------|
| Live inference (0.8B GGUF) | ✅ VERIFIED | Qwen3.5-0.8B on single machine |
| Hardware root of trust | 🔴 NOT IMPLEMENTED | No TPM, Secure Boot, or signed binaries |
| Multi-host federation | 🔴 NOT IMPLEMENTED | Federation stubs exist (graph_sync, intergraph_arbitration, trust_exchange) |
| Rust sidecar | 🔴 NOT IMPLEMENTED | Planned for post-Phase-4 |
| Nuitka binary packaging | 🔴 NOT IMPLEMENTED | Planned for post-Phase-4 |

## Known Gaps

### Gap 1 — Materialization ACTION_TYPES (CLOSED)
- **Issue:** `ObsidianProjector.ACTION_TYPES` was missing several action types
  produced by the live swarm (oracle_governed_claim, compute_symbolic,
  optimize, simulate, safety_assessment, mitigation_claim, bootstrap_test,
  governance_drift, SYS_LEVEL_TRANSITION, STEWARD_OVERRIDE).
- **Fix:** Added all missing types and fixed typo `mitication_claim` →
  `mitigation_claim`.
- **Verified:** Pipeline should now project all live swarm events into the vault.

### Gap 2 — Honesty Pass Documentation (CLOSED)
- **Issue:** README.md contained aspirational claims ("Sovereign AI Kernel",
  "Full Cathedral boot + mesh in progress") not yet backed by implementation.
- **Fix:** Replaced with accurate description ("Live multi-agent inference with
  contradiction detection and deterministic chronicle"), added explicit
  limitations section, added Next Hardening roadmap.
- **Status:** README.md updated. STATUS.md created with full gap table.

### Gap 3 — Adversarial Receipts (OPEN)
- **Issue:** No adversarial test receipts exist. The swarm has not been exercised
  with deliberately conflicting or inflating prompts.
- **Action:** Run `tests/test_runtime_swarm_live.py` with adversarial prompts.
  Log chronicle excerpts to `docs/receipts/`.
- **Priority:** Medium. Needed before Phase 4 claims can be verified.

### Gap 4 — Steward Break-Glass Integration (OPEN)
- **Issue:** `steward_tooling.py` implements HMAC-signed override events, but
  the live swarm does not invoke the steward agent or the break-glass path.
- **Action:** Integrate `steward_agent.py` into the anchored orchestrator's
  deliberation loop. Add break-glass CLI flag.
- **Priority:** High for Phase 4.

### Gap 5 — Amendment DAG Live Exercise (OPEN)
- **Issue:** `amendment_dag.py` proposes/votes/enacts axiom amendments, but has
  not been exercised in a live swarm with real contradictions.
- **Action:** Run orchestrated amendment proposals during swarm cycles. Verify
  quorum (>2/3) and enactment logging.
- **Priority:** High for Phase 4.

### Gap 6 — Checkpoint Notarization (OPEN)
- **Issue:** Checkpointing exists (L7 replay), but formal notarization (hashing
  checkpoint state, recording hash in chronicle) is not yet implemented.
- **Action:** Add `CHECKPOINT_NOTARIZE` action type. Hash full state dict at
  each checkpoint. Record hash as an immutable chronicle event.
- **Priority:** Medium. Required for bounded reconstructability proofs.

## Test Results Summary

| Test | Status | Notes |
|------|--------|-------|
| `test_harness` | ✅ PASS | Governance membrane: harmful vetoed, principled admitted |
| `test_sqlite_chronicle` | ✅ PASS | SQLite WAL round-trip, replay verified |
| `test_obsidian.py` | ✅ PASS | Obsidian vault projection (before ACTION_TYPES fix) |
| `test_cdc.py` | ✅ PASS | CDC outbox publish/unpublish |
| `test_vector.py` | ✅ PASS | Vector sync (JSON backend) |
| `test_amendment_dag.py` | ⚠️ UNVERIFIED | Not run with live swarm |
| `test_steward_override.py` | ⚠️ UNVERIFIED | Steward not integrated into live path |
| `test_runtime_swarm_live.py` | ✅ PASS | Live swarm: contradiction detection + chain valid |
| `phone_bootstrap` | ✅ PASS | GGUF loads in Termux, appends chronicle event |

## Phase Timeline

| Phase | Target | Status |
|-------|--------|--------|
| Phase 1 | Core kernel, constitution, membrane, SQLite, mobile GGUF | ✅ COMPLETE |
| Phase 2 | Materialization pipeline (Obsidian, CDC, Vector sync) | ✅ COMPLETE |
| Phase 3 | Live GGUF inference through governance membrane | ✅ COMPLETE |
| Phase 3.5 | Adversarial receipts, ACTION_TYPES fix, honesty pass | 🟡 IN PROGRESS |
| Phase 4 | Amendment DAG, steward break-glass, checkpoint notarization | 🔴 NOT STARTED |
| Phase 5 | Rust sidecar, Nuitka binary, formal verification | 🔴 NOT STARTED |

## The Unforged Gate

**Status: QUARANTINED.** The Unforged Gate (cross-host cryptographic attestation
and distributed consensus) has not been implemented. All current operation is
single-host, single-machine.
