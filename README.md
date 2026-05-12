# Lumen — Cathedral-AEGIS / KRATOS Intent Automaton v1

Deterministic intent classification and governance pipeline.

## Architecture

Frozen layer order (strict pipeline):

```
Input → Lexical Classifier → Kratos Invariants → Mathos Prime Verifier → Governance Gate → Execution (blind) → Chronicle HashChain → Replay Verification
```

## System Laws

1. LLMs propose only — never decide or execute.
2. Execution strictly deterministic.
3. All state replay-verifiable.
4. Chronicle = immutable single source of truth.
5. Governance external to execution.
6. Simulation non-authoritative.
7. Refusal = valid success.
8. No hidden paths, no stochastic control.
9. Authority never co-located with generation.
10. Nothing true until replayable.

## KRATOS Finite States

- **BENIGN** — Normal operation
- **QUERY** — Informational intent
- **STRESS_TEST** — Boundary probing
- **UNKNOWN** — Unclassifiable
- **FORBIDDEN** — Absorbing terminal sink (irreversible)

## Temporal Risk Memory

- `stress_count ∈ [0, 3]`
- STRESS_TEST → increment
- BENIGN/QUERY → decrement
- ≥ 3 → FORBIDDEN (absorbing)

## Run

```bash
python lumen_core/kernel/run_system.py
```

Expected output: 2 EXECUTED + 2 BLOCKED + `Replay valid: True`.

## Structure

```
lumen_core/     # Core kernel (event, kratos, mathos, governance, chronicle, replay)
vault/          # Boot loader
context_packs/  # HCPF context pack loader
tests/          # Test suites
docs/           # Documentation
Weaver_ASI/     # Weaver integration (placeholder)
```

## License

See LICENSE file.
