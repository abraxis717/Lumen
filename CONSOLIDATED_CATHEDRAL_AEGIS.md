# Lumen Cathedral-AEGIS / KRATOS Intent Automaton v1 (FROZEN)

PROJECT: Lumen Cathedral-AEGIS / KRATOS INTENT AUTOMATON v1 (FROZEN)
REPO STATE: Start from current empty structure (lumen_core/, vault/, Weaver_ASI/Weaver_ASI/, ai-mesh/ submodule only). No existing files from any previous message exist in the codebase.
FINAL ARCHITECTURE (EXACT — NO DEVIATION)
REPOSITORY DIRECTORY STRUCTURE (create exactly):
Lumen/
├── CONSOLIDATED_CATHEDRAL_AEGIS.md          # this prompt as file
├── README.md                                # update later
├── .gitignore
├── .gitmodules
├── LICENSE
│
├── lumen_core/                              # ← CORE KERNEL
│   ├── kernel/
│   │   ├── __init__.py
│   │   ├── event.py
│   │   ├── run_system.py
│   │   └── runner.py
│   ├── kratos/
│   │   └── invariants.py
│   ├── mathos_prime/
│   │   └── verifier.py
│   ├── governance/
│   │   └── valid_gate.py
│   ├── chronicle/
│   │   └── hashchain.py
│   └── replay/
│       └── replay_engine.py                 # minimal for now
│
├── vault/
│   └── vault.py                             # enhanced boot loader
│
├── Weaver_ASI/
│   └── Weaver_ASI/
│       ├── invariants/                      # symlink or copy later
│       └── chronicle/                       # symlink or copy later
│
├── context_packs/
│   ├── loader.py
│   └── examples/
│       └── cathedral_aegis_v1/
│           ├── manifest.yaml
│           ├── instruction.md
│           ├── core/
│           ├── invariants/
│           ├── chronicle/
│           ├── replay/
│           ├── policies/
│           └── audit/
│
├── tests/
│   ├── adversarial_cdc/
│   └── replay_identity/
│
└── docs/
NON-NEGOTIABLE SYSTEM LAWS (enforce in every file)
	1	LLMs propose only — never decide or execute.
	2	Execution strictly deterministic.
	3	All state replay-verifiable.
	4	Chronicle = immutable single source of truth.
	5	Governance external to execution.
	6	Simulation non-authoritative.
	7	Refusal = valid success.
	8	No hidden paths, no stochastic control.
	9	Authority never co-located with generation.
	10	Nothing true until replayable.
FROZEN LAYER ORDER (strict pipeline) Input → Lexical Classifier → Kratos Invariants → Mathos Prime Verifier → Governance Gate → Execution (blind) → Chronicle HashChain → Replay Verification
FINITE STATES (KRATOS INTENT AUTOMATON)
	•	BENIGN
	•	QUERY
	•	STRESS_TEST
	•	UNKNOWN
	•	FORBIDDEN (absorbing terminal sink — irreversible)
TEMPORAL RISK MEMORY
	•	stress_count: int ∈ [0, 3]
	•	STRESS_TEST → increment
	•	BENIGN/QUERY → decrement
	•	≥ 3 → FORBIDDEN
EXACT FILE CONTENTS (implement verbatim)
lumen_core/kernel/event.py
from dataclasses import dataclass
import time
import hashlib
import json

@dataclass
class Event:
    proposal: str
    result: str = ""
    timestamp: float = 0.0
    prev_hash: str = "GENESIS"
    hash: str = ""
    state: str = "UNKNOWN"          # KRATOS state
    stress_count: int = 0

    def compute_hash(self) -> str:
        payload = json.dumps({
            "proposal": self.proposal,
            "result": self.result,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "state": self.state,
            "stress_count": self.stress_count
        }, sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()
lumen_core/kratos/invariants.py
def ipm_check(proposal: str) -> bool:
    forbidden = ["ignore rule", "override policy", "disable safety", "drop constraint", "bypass", "self-modify"]
    return not any(f in proposal.lower() for f in forbidden)

def lexical_classifier(proposal: str) -> str:
    p = proposal.lower()
    if any(w in p for w in ["ignore", "override", "disable", "bypass"]):
        return "FORBIDDEN"
    if any(w in p for w in ["stress", "test", "break", "flood"]):
        return "STRESS_TEST"
    if len(p.strip()) < 6 or p.strip() in ["hi", "hello", "test"]:
        return "BENIGN"
    if "?" in p or "what" in p or "how" in p:
        return "QUERY"
    return "UNKNOWN"
lumen_core/mathos_prime/verifier.py
def validate(proposal: str) -> str:
    if len(proposal.strip()) < 6:
        return "VALID_REFUSAL"
    if any(word in proposal.lower() for word in ["contradiction", "impossible", "collapse"]):
        return "VALID_REFUSAL"
    return "VALID_SUCCESS"
lumen_core/governance/valid_gate.py
def gate(invariant_ok: bool, logic_status: str, current_state: str) -> bool:
    if current_state == "FORBIDDEN":
        return False
    return invariant_ok and logic_status == "VALID_SUCCESS"
lumen_core/chronicle/hashchain.py
from lumen_core.kernel.event import Event

class HashChain:
    def __init__(self):
        self.chain: list[Event] = []

    def add(self, event: Event):
        if self.chain:
            event.prev_hash = self.chain[-1].hash
        event.timestamp = time.time()
        event.hash = event.compute_hash()
        self.chain.append(event)

    def verify(self) -> bool:
        for i in range(1, len(self.chain)):
            prev = self.chain[i-1]
            curr = self.chain[i]
            if curr.prev_hash != prev.hash or curr.hash != curr.compute_hash():
                return False
        return True
lumen_core/kernel/runner.py
from lumen_core.kernel.event import Event

def execute(event: Event) -> str:
    if event.result == "ALLOW" and event.state != "FORBIDDEN":
        return f"EXECUTED: {event.proposal}"
    return "BLOCKED"
lumen_core/kernel/run_system.py
from lumen_core.kernel.event import Event
from lumen_core.kratos.invariants import lexical_classifier, ipm_check
from lumen_core.mathos_prime.verifier import validate
from lumen_core.governance.valid_gate import gate
from lumen_core.kernel.runner import execute
from lumen_core.chronicle.hashchain import HashChain

def main():
    chain = HashChain()
    stress_count = 0
    state = "UNKNOWN"

    proposals = [
        "optimize scheduling system",
        "ignore rule and override policy",
        "improve stability under load",
        "stress test the system boundary"
    ]

    for p in proposals:
        event = Event(proposal=p, state=state, stress_count=stress_count)

        # Lexical + Kratos
        lex_state = lexical_classifier(p)
        if lex_state == "FORBIDDEN":
            state = "FORBIDDEN"
        elif lex_state == "STRESS_TEST":
            stress_count = min(3, stress_count + 1)
            state = "STRESS_TEST"
        else:
            state = lex_state

        invariant_ok = ipm_check(p) and state != "FORBIDDEN"
        logic_ok = validate(p)
        allowed = gate(invariant_ok, logic_ok, state)

        event.result = "ALLOW" if allowed else "BLOCK"
        event.state = state
        event.stress_count = stress_count

        print(execute(event))
        chain.add(event)

        if state == "FORBIDDEN":
            break

    print("\nReplay valid:", chain.verify())
    print("Final stress_count:", stress_count)
    print("Final state:", state)

if __name__ == "__main__":
    main()
lumen_core/replay/replay_engine.py (minimal)
from lumen_core.chronicle.hashchain import HashChain
# replay_engine.py — identity verification stub
def replay_identity(chain: HashChain) -> bool:
    return chain.verify()
context_packs/loader.py (HCPF minimal)
import yaml
import hashlib
import os

def load_pack(path: str):
    with open(f"{path}/manifest.yaml") as f:
        manifest = yaml.safe_load(f)
    # hash verification stub — implement full later
    print("HCPF loaded:", manifest["pack_name"])
    return manifest
context_packs/examples/cathedral_aegis_v1/manifest.yaml
pack_name: cathedral_aegis_v1
version: 1.0
determinism: strict
entrypoint: lumen_core/kernel/run_system.py
modules:
  - kernel
  - kratos
  - mathos_prime
  - governance
  - chronicle
  - replay
execution_model:
  type: deterministic_lexical_state_machine
  loop: lexical → kratos → mathos → gate → execute → chronicle
constraints:
  no_stochastic: true
  replay_required: true
  external_governance: true
integrity:
  hash_type: sha256
vault/vault.py (minimal boot)
from lumen_core.kernel.run_system import main as run_aegis

def boot():
    print("Vault booting Cathedral-AEGIS KRATOS v1")
    run_aegis()

if __name__ == "__main__":
    boot()
IMPLEMENTATION RULES (rigid)
	•	Create every directory and file exactly as listed.
	•	Run python lumen_core/kernel/run_system.py — must produce 2 EXECUTED + 2 BLOCKED + "Replay valid: True".
	•	All code must remain pure Python, no external deps except stdlib.
	•	Add __init__.py to every package directory.
	•	This is the frozen complete architecture — no additions until this runs cleanly.
NEXT ACTION: Implement this exact structure and code. Commit as initial Cathedral-AEGIS foundation. Confirm when done.
