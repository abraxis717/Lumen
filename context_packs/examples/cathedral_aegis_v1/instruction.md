# Cathedral-AEGIS Context Pack v1

This context pack defines the Cathedral-AEGIS KRATOS Intent Automaton.

## Purpose

Deterministic intent classification and governance pipeline for AI system proposals.

## Layers

1. **Lexical Classifier** — Classifies input into finite states
2. **Kratos Invariants** — Checks forbidden actions (IPM)
3. **Mathos Prime Verifier** — Validates logic consistency
4. **Governance Gate** — Applies policy rules
5. **Execution** — Blind execution (no authority co-located)
6. **Chronicle HashChain** — Immutable event log
7. **Replay Verification** — Integrity check

## State Machine

- BENIGN → Normal operation
- QUERY → Informational intent
- STRESS_TEST → Boundary probing
- UNKNOWN → Unclassifiable
- FORBIDDEN → Absorbing terminal sink