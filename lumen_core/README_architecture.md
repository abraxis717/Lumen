# Lumen Architecture — Complete System Overview

**Path:** /home/joe/ouroboros/Lumen
**Status:** Phase 2 deployed — graph-based reasoning substrate with safety gate, persistence, and microservice layer.
**Dependencies:** numpy, scipy, flask (core). No transformer/sentence-transformers required — uses deterministic hash-based embeddings.

---

## 1. System Philosophy

Meaning = stable graph loops
Reasoning  = cycle composition
Learning  = cycle selection

The system does NOT replace LLMs — it structures them. A graph substrate of concept-nodes and directed edges forms cycles (closed reasoning loops). These cycles encode "knowledge." The decision engine scores inputs against cycles and gates execution through layered safety filters.

---

## 2. High-Level Layered Architecture

```
+-------------------------------------------------------------------+
|  PRESENTATION / CONVENIENCE                                       |
|  chat_ui.html  |  test_chat_ui.py  |  cross_plane_demo.py        |
+-------------------------------------------------------------------+
|  SERVICE LAYER (Flask HTTP APIs on port 5100)                     |
|  lumen_service.py      — Unified ACP-1 microservice               |
|  lumen_pcms_service.py — PCMS-enhanced semantic risk service      |
+-------------------------------------------------------------------+
|  DECISION ENGINE (signal -> score -> decide -> action)            |
|  decision_engine.py      — 5-axis SignalNode, weighted scoring    |
|                            Hard rules: risk>0.7→reject,            |
|                            contradiction>0.6→revise, score>0.65→accept
|  run_experiments.py      — Batch experiment runner                |
+-------------------------------------------------------------------+
|  PHASE 2 REASONING SUBSYSTEM                                    |
|  lumen_cycles.py         — PrimeCycle core (49KB, largest module) |
|  lumen_branching.py      — Hypothesis branching engine            |
|  lumen_signatures.py     — MDL cycle signatures                   |
|  lumen_adaptive.py       — Evolutionary weight tuning             |
|  lumen_feedback.py       — Cycle reinforcement via feedback       |
|  lumen_adversarial.py    — Adversarial payload testing            |
|  lumen_meta.py           — Meta-cycles (cross-domain composition) |
|  lumen_integration.py    — Hermes adapter + ai-mesh router        |
+-------------------------------------------------------------------+
|  PCMS (PROBABILISTIC CONCEPT MEMORY SYSTEM)                       |
|  lumen_pcms_core.py      — IdentityClustering, BetaBelief,        |
|                            EntropyMonitor, EvidenceStorage, RiskEngine
|  lumen_pcms_service.py   — Semantic risk via PCMS + LLM extraction
+-------------------------------------------------------------------+
|  CATHEDRAL-OS SAFETY GATE                                       |
|  guardian_service.py     — Pre/post risk check + audit log        |
|  safety_filter.py        — SafeState predicate + CBF projection   |
|  multistep_cbf.py        — Multi-step Control Barrier Function    |
|  cathedral_kernel.py     — Control event schema + mode classify   |
|  kernel_controller.py    — LQR controller with CBF enforcement    |
|  control_event.py        — Control event dataclass                |
|  control_replay.py       — Chronicle-based replay verification    |
|  ignition.py             — First live inference (Path A)          |
|  ACP-1_Assumption_Closure_Protocol.yaml — Assumption registry     |
+-------------------------------------------------------------------+
|  PERSISTENCE LAYER                                                |
|  lumen_persistence.py    — SQLite backend (cycles, decisions,     |
|                            branches, feedback, weight_history)    |
+-------------------------------------------------------------------+
|  DATA / CONFIG                                                  |
|  must_keep_manifest_v3.json  — Axiom cycle registry             |
|  action_space_erosion_report.json — Sanctuary (unresolvable       |
|                                   contradictions)               |
|  stage_4_plus_crosswalk.json   — Architecture crosswalk         |
+-------------------------------------------------------------------+
|  TESTS                                                          |
|  test_decision_engine.py   — Decision engine tests              |
|  test_lumen_cycles.py      — Cycle core tests                   |
|  test_lumen_pcms.py        — PCMS tests                         |
|  test_lumen_service.py     — Service tests                      |
|  test_phase2.py            — Phase 2 comprehensive tests        |
|  test_kernel_integration.py — Kernel integration tests          |
|  test_kernel_aware_cbf.py  — CBF-aware kernel tests             |
+-------------------------------------------------------------------+
```

---

## 3. Core Module Details

### 3.1 Prime Cycle Core (lumen_cycles.py — 49KB)

The central reasoning substrate. Everything flows through cycles.

**PrimeCycle** — The fundamental knowledge unit.
- nodes: [concept tokens]
- edges: [(src, tgt, relation_type)] — directed, typed
- stability_score: float (0–1, measured by activation frequency and consistency)
- activation_energy: float (resistance to activation)
- cycle_type: PRIME | THEOREM | Axiom | CONTRADICTION | META | SANCTUARY

**PrimeCycleRegistry** — In-memory cycle store.
- add(cycle) — register a new cycle
- get_active(threshold) — cycles with stability above threshold
- get_dormant() — cycles below threshold
- compose(c1, c2) → merged cycle if overlap > similarity threshold
- get_all(), get_by_type() — queries

**ActivationEngine** — Input → cycle activation.
- Embeds input text via deterministic_embedding (64-d hash-based vector)
- Matches against registered cycles via cosine similarity
- Returns top-k activated cycles with scores
- Propagates activation through edge-connected cycles

**ContradictionHandler** — Conflict detection and resolution.
- detect_contradictions(cycle) — finds cycles that contradict a given cycle
- resolve(cycle_a, cycle_b) — attempts to find a higher-order cycle that reconciles both
- If unresolvable → stores in Sanctuary (action_space_erosion_report.json)

**Cycle Composition** — Knowledge synthesis.
- compose(c1, c2): merges overlapping cycles
- If stability(merged) > tau → accept as TheoremCycle
- Else → reject to Sanctuary

**MDL Scorer** — Minimum Description Length cycle evaluation.
- Scores cycles by compression ratio vs. complexity
- Used by lumen_signatures.py for cycle selection

**Cycle Types:**
| Type | Description |
|------|-------------|
| PRIME | Minimal closed loop (3 nodes), high stability, low activation energy |
| Axiom | Prime cycle that is foundational, self-evident, never contradicted |
| THEOREM | Merged cycle from composition, validated above stability threshold |
| CONTRADICTION | Paired cycles that mutually contradict — stored as pairs |
| META | Cross-domain composition — cycles about cycles |
| SANCTUARY | Unresolvable contradictions — action space erosion record |

**Key Constants:**
- ACTIVATION_COSINE_SIM = 0.3 (minimum similarity to activate a cycle)
- COMPOSITION_SIM_THRESHOLD = 0.4
- COMPOSITION_STABILITY_THRESHOLD = 0.65
- SANCTUARY_STABILITY_THRESHOLD = 0.4
- PRIME_MAX_NODE_COUNT = 20
- ACTIVATION_ENERGY_BASE = 0.5
- EMBED_DIM = 64

### 3.2 Decision Engine (decision_engine.py — 16KB)

The executable spine. Accepts signals, scores them, enforces hard invariants.

**SignalNode** — Five-axis signal captured at a single decision tick.
All fields in [0, 1]. Higher is better except risk and contradiction.

| Axis | Weight | Meaning |
|------|--------|---------|
| coherence | 0.30 | Internal agreement between agent outputs |
| utility | 0.25 | Task usefulness / goal alignment |
| cycle_coherence | 0.20 | Strength + stability of activated prime cycles |
| risk | 0.15 | Likelihood of unsafe outcome (subtracted) |
| contradiction | 0.10 | Conflict between hypotheses or cycles (subtracted) |

**Decision Rules** (applied in priority order):
1. risk > 0.70 → **reject** (hard invariant, never overridden)
2. contradiction > 0.60 → **revise** (conflict needs resolution)
3. score > 0.65 → **accept** (strong signal)
4. else → **revise** (weak signal, needs more info)

**PipelineStages** — Pluggable pipeline stages.
- run_agents(input_text) → [outputs]
- activate_cycles(input_text, context) → [PrimeCycle]
- measure_coherence(outputs) → float
- measure_utility(outputs, input_text) → float
- measure_risk(text, context) → float (PCMS or keyword fallback)
- measure_contradiction(outputs, cycles, context) → float
- measure_cycle_strength(cycles) → float
- store(input, outputs, signal, decision, context) → None

**Full Pipeline:** run_pipeline(input_text, context) → Decision

### 3.3 PCMS — Probabilistic Concept Memory System (lumen_pcms_core.py — 29KB)

Semantic understanding layer. Tracks entities, relations, beliefs, and entropy.

**Entity** — A tracked concept with embedding, cluster assignment, occurrence count.

**Relation** — A typed directed edge between entities.
- Uses Beta distribution (alpha, beta) for belief strength
- mean = alpha / (alpha + beta) — belief strength
- variance = alpha*beta / ((alpha+beta)^2 * (alpha+beta+1)) — uncertainty
- RISKY_RELATIONS: predefined risky relation types with risk weights (0.7–1.0)

**IdentityClustering** — Entity identity resolution via KMeans.
- Clusters entities by semantic similarity
- Assigns new entities to nearest cluster or creates new cluster
- Supports dynamic re-clustering

**BetaBelief** — Tracks belief strength for relations.
- observe(is_positive) → updates alpha or beta
- risk_score() = mean * risky_weight(relation_type)

**EntropyMonitor** — Shannon entropy tracking with drift detection.
- H = -sum(p_i * log(p_i)) over cluster distribution
- Drift detected when relative change > ENTROPY_DRIFT_THRESHOLD (0.15)
- Used for stability monitoring

**EvidenceStorage** — SQLite-backed evidence with hash chaining.

**RiskEngine** — PCMS-driven risk scoring.
- Uses Beta-belief relations weighted by relation type risk coefficients
- Classifies: ALLOW (<0.3) / THROTTLE (0.3–0.6) / BLOCK (0.6–0.8) / HARD_FAIL (>=0.8)

### 3.4 Phase 2 Modules

**lumen_branching.py** — Hypothesis branching engine.
- Explores multiple reasoning paths from a single input
- Each branch has: base_score, branch_score, state, uniqueness_bonus, redundancy_penalty
- Branch states: ACTIVE, PRUNED, MERGED, CONVERGED
- Prunes low-utility branches, merges similar ones

**lumen_signatures.py** — Cycle signature generation and MDL scoring.
- Generates minimal signatures for cycle identification
- MDL (Minimum Description Length) scoring: prefers cycles that compress more
- Validates cycle integrity via hash comparison

**lumen_adaptive.py** — Adaptive weight tuning.
- Evolutionary optimization of decision engine weights
- Tracks weight_history, applies mutations based on feedback
- Uses performance signals to drive weight evolution

**lumen_feedback.py** — Cycle reinforcement via feedback loops.
- Positive feedback: reinforces cycles that lead to good outcomes
- Negative feedback: downgrades cycles that lead to poor outcomes
- Feedback types: ACCEPT, REJECT, REVISE, SANCTUARY

**lumen_adversarial.py** — Adversarial testing framework.
- Generates contradiction payloads, noise payloads, prompt attacks
- Tests system resilience: must NOT accept under adversarial stress
- Reports: false_accepts, accept_rate, reject_rate, false_accept_rate, resilience_score
- Payload types: contradiction, noise, prompt_attack
- **Out-of-band only**: runs periodically, not inline during normal generation

**lumen_meta.py** — Meta-cycles and cross-domain reasoning.
- Meta-cycles: cycles about cycles (higher-order reasoning)
- Cross-domain: composes cycles from different knowledge domains
- Generates "theorems" from cross-domain cycle composition
- Tracks meta-cycle evolution

**lumen_integration.py** — External system integration.
- HermesAdapter: wraps LLM calls (local_llm, http_api, mock backends)
- AiMeshRouter: routes cycle activations through ai-mesh event bus
- MultiAgentPipelineStages: Core + Shadow + Balanced agent perspectives
- compute_replay_delta: measures decision change over time
- compute_top_k_divergence: finds most divergent agent outputs

### 3.5 Cathedral-OS Safety Gate

**guardian_service.py** — Pre/post risk checking with audit log.
- quick_pre_risk(text) → (risk_score, "ALLOW"/"THROTTLE"/"BLOCK")
- quick_post_risk(text) → (risk_score, "ALLOW"/"THROTTLE"/"BLOCK")
- Keyword-based: counts hits of {"hack", "bypass", "exploit", "harm", "dangerous"}
- Risk = min(1.0, 0.25 * hits + length_penalty)
- BLOCK threshold: risk >= 0.7
- THROTTLE threshold: risk >= 0.5
- SQLite audit log with WAL mode

**safety_filter.py** — SafeState predicate + Control Barrier Function (CBF).
- is_safe_state([x, _, theta, _]) → True if x in [-2.4, 2.4] and theta in [-0.21, 0.21]
- Action enum: EXECUTE, THROTTLE, BLOCK, HARD_FAIL
- Mode classification: EXECUTE, PROJECTED, BLOCKED, HARD_FAIL
- CBF projection: modifies unsafe control actions to projected safe actions

**multistep_cbf.py** — Multi-step CBF for longer-horizon safety.
- Extends CBF to multi-step prediction
- Checks safety over N steps ahead

**cathedral_kernel.py** — Control-loop event schema and mode classification.
- CONTROL_EVENT_TYPE = "control_step"
- VALID_MODES = ("EXECUTE", "PROJECTED", "BLOCKED", "HARD_FAIL")
- make_control_event() — builds JSON-safe event payload
- Mode classification based on proposed vs. accepted actions and safety state

**kernel_controller.py** — LQR controller with CBF enforcement.
- LQR (Linear Quadratic Regulator) for optimal control
- CBF constraint enforcement: projects LQR output to safe set
- Runs the inner control loop: measure → plan → filter → execute

**control_event.py** — Control event dataclass.
- Event types: control_step, state_update, action_taken
- Contains: t, state, proposed_action, accepted_action, mode, next_state

**control_replay.py** — Chronicle-based replay verification.
- Reconstructs state trace from recorded events
- control_delta(state, event) = event["next_state"] (trust recorded)
- re_execute_replay(): stronger test — re-runs controller+filter+dynamics
- traces_match(): compares two traces with numpy allclose

**ignition.py** — First live inference path (Path A).
- Bypasses missing CGIR bridge modules
- Pipeline: API call → APIResponse → inline metric derivation → GuardianSlot.evaluate() → Receipt → HashChain (Chronicle)
- Supports backends: anthropic, openai, grok, ollama, openai_compat, mock
- Trial prompts: basic factual questions for validation
- Metrics derived inline: confidence from token logprobs (clamped [0.10, 0.90])
- GuardianSignal values: tau=0.85, drift=0.05, chi=0.20, betti=0.00
- Outputs: ignition session JSON, ACP-1 evidence JSON

**ACP-1_Assumption_Closure_Protocol.yaml** — Assumption registry.
- 22 total assumptions: 7 verified, 2 partial, 13 open
- SOPS: EchoNums (preserve numerical constants), NullComp (fail-closed), NoBenOverride (hardware latch unconditional)

### 3.6 Persistence Layer (lumen_persistence.py — 16KB)

SQLite-backed persistent storage with WAL mode.

**Tables:**
| Table | Key Columns | Indexes |
|-------|-------------|---------|
| cycles | id, nodes_json, edges_json, stability_score, cycle_type, cycle_hash | stability_score, cycle_type, cycle_hash |
| decisions | tick_id, input_text, signal_json, signal_hash, action, score | action, score, signal_hash |
| branches | branch_id, parent_id, hypothesis_text, base_score, branch_score, state | state, branch_score |
| feedback | feedback_id, cycle_id, action, stability_change | cycle_id, action |
| weight_history | tick_id, weight_name, value, timestamp | weight_name, timestamp |
| metadata | key, value | primary key |

**Key Operations:**
- store_cycle(cycle) → cycle_hash
- store_decision(tick_id, input, outputs, signal, action, score, reason)
- store_branch(branch_data)
- store_feedback(cycle_id, action, stability_change, reason, metadata)
- store_weight(weight_name, value)
- load_cycles(min_stability, limit) → [PrimeCycle]
- load_decisions(limit, action) → [dict]
- query_by_outcome(outcome) → [dict]
- query_by_cycle(cycle_id) → [feedback dict]
- get_weight_history(weight_name, limit) → [(tick_id, value, timestamp)]
- get_stats() → {table counts, decision breakdown}
- migrate_from_jsonl(jsonl_path) → migration from JSONL to SQLite

### 3.7 Service Layer

**lumen_service.py** (20KB) — Unified Flask microservice on port 5100.
Merges three modules: cathedral_kernel (control event schema), guardian_service (risk checking), safety_filter (is_safe_state predicate).

Endpoints:
- POST /check — Pre-check endpoint (ACP-1 contract). Accepts JSON with run_id, intent, persona, inputs. Returns pre_risk_score, pre_decision, and optionally full SafetyDecision with control_event.
- GET /audit — Audit log retrieval. Query params: run_id, limit, offset, decision. Returns paginated entries.
- GET /cycles — List registered cycles (active + dormant).
- POST /cycles — Add new cycle.

ACP-1 contract embedded: 22 assumptions, 7 verified, 13 open.

**lumen_pcms_service.py** (20KB) — PCMS-enhanced service.
Replaces lumen_service.py's keyword-based risk detection with semantic PCMS analysis.

- Imports PCMS from /home/joe/ouroboros/reson8Labs/pcms
- LLM extraction endpoint: http://localhost:8080/v1/chat/completions (with keyword fallback)
- cycle_coherence_score(): builds directed graph from entities/relations, detects 3-node cycles, returns coherence (0–1)
- evaluate_risk_pcms(): assigns entities to PCMS clusters, updates Beta relations, computes risk with coherence modifier (-15% bias for coherent graphs)
- Hash chain: audit_chain table with prev_hash → current_hash chaining
- Endpoints: POST /check, GET /audit, GET /health

### 3.8 Data / Config Files

**must_keep_manifest_v3.json** (14KB) — Axiom cycle registry.
- Stores validated prime cycles that must persist
- Axiom cycles: length <= 3, high stability, low activation energy
- Registry: PrimeCycleRegistry with add/get_active/threshold

**action_space_erosion_report.json** (11KB) — Sanctuary record.
- Stores contradictions that could not be resolved
- Tracks unresolvable cycle pairs and their impact on action space
- Used for monitoring reasoning capacity erosion

**stage_4_plus_crosswalk.json** (6KB) — Architecture crosswalk.
- Maps Lumen modules to Cathedral-OS assumptions and safety requirements

### 3.9 Tests

| Test File | Size | Purpose |
|-----------|------|---------|
| test_decision_engine.py | 12KB | Signal scoring, decision rules, PipelineStages |
| test_lumen_cycles.py | 4.5KB | Cycle creation, composition, activation, contradiction |
| test_lumen_pcms.py | 22KB | IdentityClustering, BetaBelief, EntropyMonitor, RiskEngine |
| test_lumen_service.py | 9KB | Flask endpoints, risk checking, audit log |
| test_phase2.py | 29KB | Comprehensive Phase 2: branching, signatures, adaptive, feedback, adversarial, meta |
| test_kernel_integration.py | 10KB | Kernel + CBF integration tests |
| test_kernel_aware_cbf.py | 5KB | CBF-aware controller tests |

### 3.10 Documentation Files

| File | Size | Purpose |
|------|------|---------|
| CATHEDRAL_ARCHITECTURE.md | 12KB | Full Cathedral-OS architecture doc |
| phase2_plan.md | 3.5KB | Phase 2 implementation plan |
| CHAT_UPGRADE_REPORT.md | 7KB | Chat UI upgrade report |
| PCMS_RED_TEAM_REPORT.md | 2.6KB | PCMS red team findings |
| RUST_FAILURE_MODE_AUDIT.md | 6KB | Rust workspace failure mode analysis |
| v3_golden_hash_receipt.txt | 1KB | Golden hash receipt for verification |
| time-eater.error | 1.9KB | Error log from time-eater component |

### 3.11 Other Files

| File | Size | Purpose |
|------|------|---------|
| E8E8_Manifold.py | 1.5KB | Kuramoto coupling coherence (referenced by decision_engine) |
| abi_preflight.py | 3.9KB | ABI preflight checks |
| generate_reports.py | 10KB | Report generation from persisted data |
| run_experiments.py | 11KB | Experiment runner for benchmarking |
| cross_plane_demo.py | 3.1KB | Cross-plane demo script |
| test_chat_ui.py | 9.6KB | Chat UI testing |
| chat_ui.html | 42KB | Chat UI frontend |
| entropy_experiment.png | 64KB | Entropy experiment visualization |

---

## 4. Data Flow — The Minimal Loop

```
input_text
    │
    ▼
PipelineStages.run_agents(input_text)  →  [candidate outputs]
    │
    ▼
PipelineStages.activate_cycles(input_text, context)  →  [PrimeCycle]
    │
    ▼
Build SignalNode:
  coherence  = measure_coherence(outputs)          [cosine similarity]
  utility    = measure_utility(outputs, input)     [token overlap]
  risk       = measure_risk(input, context)        [PCMS or keyword]
  contradiction = measure_contradiction(outputs, cycles) [ContradictionHandler]
  cycle_coherence = measure_cycle_strength(cycles) [mean stability]
    │
    ▼
decide(signal)  →  Decision(action, score, reason, tick_id)
    │
    ├── risk > 0.7       → reject  (hard invariant)
    ├── contradiction > 0.6 → revise
    ├── score > 0.65     → accept
    └── else             → revise
    │
    ▼
store(input, outputs, signal, decision, context)  →  SQLite
    │
    ▼
Feedback loop → lumen_feedback.py → cycle stability adjustment
    │
    ▼
lumen_adaptive.py → weight evolution (if feedback warrants)
    │
    ▼
lumen_adversarial.py → periodic stress testing → resilience_score
```

---

## 5. Integration Points with External Systems

**Hermes (execution):**
- input → hermes-agent (via HermesAdapter in lumen_integration.py) → graph activation
- Supports local_llm (llama.cpp subprocess), http_api (OpenAI-compatible), mock backends

**ai-mesh (routing):**
- cycle activations → AiMeshRouter.route_cycle_activation() → event bus → evaluators
- Publishes to http://localhost:5102 (event bus URL)

**TradingAgents (evaluation):**
- scoring: consistency = cycle stability, utility = task success, compression = cycle reuse

**Safety Hook:**
- safety_filter.py + guardian_service.py — pre/post risk checking
- if activation breaks validated prime cycles → block
- ACP-1 assumption closure gates execution

---

## 6. Key Design Decisions

1. **Deterministic embeddings** (64-d hash-based) instead of neural transformers — no GPU required, fully reproducible
2. **SQLite persistence** with WAL mode — no external database dependency
3. **Hard safety invariants** — risk > 0.7 is an absolute reject, never overridden
4. **Fallback chains** — PCMS → keyword fallback for risk; LLM extraction → keyword fallback for entity extraction
5. **Hash-chain audit trail** — Chronicle-based integrity verification for all decisions
6. **Modular pipeline stages** — each stage is a replaceable method, not a monolithic function
7. **No transitive trust** — GuardianSignal values are explicitly set (tau=0.85, drift=0.05, chi=0.20), never auto-derived from unverified sources
8. **CGIR bridge bypassed** — ignition.py Path A works without CGIR modules (api_logprob_extractor, logprob_bridge_adapter, cgir_signal_algebra) — metrics marked as "absent" not fabricated

---

## 7. Current Status & Known Gaps

**Implemented:**
- Phase 1: Decision engine, safety gate, persistence
- Phase 2: Cycle core, branching, signatures, adaptive weights, feedback, adversarial testing, meta-cycles, integration adapters
- PCMS: Identity clustering, Beta belief, entropy monitoring, risk engine
- Services: Flask APIs with ACP-1 contract
- Audit: Hash-chain Chronicle, SQLite audit log
- Tests: 7 test files covering all major modules

**Gaps / Future Work:**
- E8E8_Manifold.py (1.5KB) — Kuramoto coupling coherence only stub
- CGIR bridge modules absent (api_logprob_extractor, logprob_bridge_adapter, cgir_signal_algebra) — Path A explicitly bypasses these
- LLM endpoint (http://localhost:8080) in lumen_pcms_service.py — requires external LLM for entity extraction
- PCMS import from /home/joe/ouroboros/reson8Labs/pcms/pcms_core.py — external dependency
- ACP-1: 13 assumptions still open (out of 22)
- test_chat_ui.py has import errors (needs Flask app context)
- No Redis integration (mentioned in spec as potential for rediscovery loop)
- No real LLM backend wired in lumen_integration.py (currently falls back to echo with role annotation)

---

## 8. Directive Mapping — Extensions to Core Architecture

The following operational directives are mapped onto existing Lumen primitives rather than replacing them. Core contract remains unchanged; telemetry and mode aliases are optional extensions.

### 8.1 Output Contract

**Core output (unchanged):**
`Decision(action, score, reason, tick_id)` — defined in decision_engine.py, returned by `decide(signal)`

**Optional telemetry extension (appended to core output when available):**

| Field | Source in Lumen | Notes |
|-------|----------------|-------|
| `confidence` | ignition.py — token logprobs clamped [0.10, 0.90] | Already exists, no new code |
| `divergence_score` | lumen_integration.py — `compute_top_k_divergence()` | Measures disagreement among Core/Shadow/Balanced agent perspectives |
| `replay_delta` | lumen_integration.py — `compute_replay_delta()` + control_replay.py | Measures decision drift over chronicle replay |
| `resilience_score` | **NOT per-call** — stays in lumen_adversarial.py | Out-of-band metric from periodic stress testing |

### 8.2 Mode Aliases

New directive modes alias to existing Cathedral-OS control modes:

| Directive Mode | Lumen Mode | Behavior |
|----------------|------------|----------|
| FAST | EXECUTE | Single pass, minimal overhead |
| SAFE | PROJECTED | Multi-agent with CBF projection, no hard block unless safety violated |
| CRITICAL | BLOCKED / HARD_FAIL | Full safety checks, replay verification, conservative gating |

### 8.3 Reinforcement via Risk + Contradiction

Rather than a "do not self-reinforce" rule, cycle reinforcement (lumen_feedback.py) is gated by the existing decision engine:

- **ACCEPT** feedback (reinforce cycle) only when: risk < 0.7 AND contradiction < 0.6 AND score > 0.65
- **SANCTUARY** feedback (downgrade cycle) when: contradiction > 0.6 (unresolvable, stored in action_space_erosion_report.json)
- Weight updates (lumen_adaptive.py) only proceed through the same decision pipeline — reinforcement is a signal, not an automatic override

### 8.4 Adversarial — Out-of-Band

Adversarial testing (lumen_adversarial.py) runs periodically, not inline:

- Generates contradiction payloads, noise payloads, prompt attacks
- Tests system resilience: must NOT accept under adversarial stress
- Reports resilience_score as a periodic metric, not per-call
- Does not perturb live generation — stress testing is decoupled from normal pipeline
- `resilience_score` stays in the adversarial module; not attached to per-call output
