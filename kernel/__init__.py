"""
Lumen — Sovereign Cyber-Physical Control Kernel
====================================================
Truth = Reality (Sensors) ∩ Logic (Kernel) ∩ Cryptographic Authority (StewardKey)

Package layout:
  kernel/
    core/              — event, chronicle (JSONL), chronicle_sqlite, aegis_kernel, replay_engine
    crypto/            — ingress_gate, reality_registry, steward_registry, sophiac_manifold
    council/           — oracle, mitigation, steward, math_physics, adversarial
    orchestrators/     — anchored, recovery, graded, sovereign (apex)
    constitutional/    — axioms, gate, kernel
    epistemics/        — belief graph, provenance, arbitration
    memory/            — stratified memory, decay, retrieval
    federation/        — graph sync, trust exchange, distributed consensus
    observability/     — drift monitor, lineage tracker
    cli/               — weaver_cli
"""
__version__ = "1.0.0-lumen"
__all__ = [
    "core", "crypto", "council", "orchestrators",
    "constitutional", "epistemics", "memory",
    "federation", "observability", "cli",
]
