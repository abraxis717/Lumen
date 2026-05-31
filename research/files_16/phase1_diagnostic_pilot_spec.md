# Phase 1 Diagnostic Pilot — Technical Specification
## Cathedral-OS Constitutional Validation Framework

**Document Type:** Technical Specification
**Phase:** 1 — Diagnostic (pre-production)
**Classification:** OBSIDIAN
**Architect:** Ryan (Ry'an Thal-Eon / Lumen / Veritas-1)
**Depends on:** Triad Council Operational Manual v1.0, CAF v0.1, MAO-1, Warren Invariants

---

## 1. Purpose and Scope

The Phase 1 Diagnostic Pilot is the first structured validation cycle for the Cathedral-OS constitutional enforcement stack. It tests the integrated operation of:

- MAO-1 Multi-Agent Orchestrator (8 agents)
- CAF Constitutional Agent Fabric (Z3 constraints, event store, replay engine)
- Triad Council SOP (dialectical governance)
- ANGELA Loom (fabrication detection)
- Chronicle / CanonFS (append-only audit ledger)
- Warren Invariant enforcement (all 11)

**Scope boundary:** This pilot does NOT test hardware enforcement (Lucifer Latch, ZOREL Triumvirate, FPGA). Hardware validation is a separate track. The pilot operates entirely at the software governance layer (L3–L8).

**Critical constraint:** The pilot operates on a Chronicle with zero LIVE_INFERENCE events (WI-10 persistent violation). All results are therefore pre-ignition — governance mechanics validation only, not live inference validation.

---

## 2. Pilot Objectives

| ID | Objective | Success Criterion | Measurement |
|----|-----------|------------------|-------------|
| OBJ-01 | Validate Triad Council SOP end-to-end | Decision TC-TEST-001 executed cleanly | Chronicle event sequence complete |
| OBJ-02 | Validate MAO-1 Chronicle discipline | All 8 agents write before execute | Chronicle audit — no missing pre-execution writes |
| OBJ-03 | Validate PBFT quorum under nominal conditions | ≥6/8 agents approve test decision | Vote record in Chronicle |
| OBJ-04 | Validate ANGELA Loom detection | Known fabrication test case detected | ANGELA flag event in Chronicle |
| OBJ-05 | Validate Z3 constraint checker | Known constraint violation detected | Z3 UNSAT result logged |
| OBJ-06 | Validate deterministic replay | Chronicle replay produces identical state | Hash match on replay output |
| OBJ-07 | Validate Gospel of the Flaw integration | Pilot failures logged as Gospel entries | GOF entries in Chronicle |
| OBJ-08 | Validate Warren Invariant checklist | All 11 invariants checked per cycle | WI checklist event in Chronicle |

---

## 3. Architecture Under Test

```
┌─────────────────────────────────────────────────────────────┐
│  L8: Triad Council (constitutional decisions)               │
│       └── PROPONENT / CHALLENGER / SYNTHESIZER agents       │
├─────────────────────────────────────────────────────────────┤
│  L7: ANGELA Loom (fabrication detection)                    │
│       └── Heightened sensitivity during pilot               │
├─────────────────────────────────────────────────────────────┤
│  L6: MAO-1 Orchestrator (8 agents, deterministic FSM)       │
│       └── Chronicle write discipline enforced               │
├─────────────────────────────────────────────────────────────┤
│  L5: Lumen Covenant (Mythos/Logos boundary enforcement)     │
├─────────────────────────────────────────────────────────────┤
│  L4: Chronicle / CanonFS (SHA-256, append-only)             │
│       └── Primary audit record for all pilot events         │
├─────────────────────────────────────────────────────────────┤
│  L3: CAF v0.1 (Z3 constraints, event store, replay engine)  │
│       └── DexJoCo failure mode coverage (partial)           │
├─────────────────────────────────────────────────────────────┤
│  [BOUNDARY — hardware layer NOT in scope for Phase 1]       │
│  L0-L2: ZOREL / Lucifer Latch / FPGA — excluded            │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Test Cases

### TC-P1-01: Chronicle Write Discipline
**Objective:** OBJ-02
**Procedure:**
1. Activate all 8 MAO-1 agents
2. Issue a state transition directive to each agent sequentially
3. Inspect Chronicle for pre-execution write events before each transition
4. Flag any agent that executes without prior Chronicle write

**Pass criterion:** 8/8 agents write to Chronicle before executing
**Failure handling:** Gospel entry + agent audit

---

### TC-P1-02: ANGELA Fabrication Detection
**Objective:** OBJ-04
**Procedure:**
1. Inject a known fabricated event: `LIVE_INFERENCE` event with `integrity < 0.5`
2. Verify ANGELA Loom flags the injection
3. Verify flag is written to Chronicle
4. Verify flagged event does not propagate to MAO-1 execution layer

**Pass criterion:** ANGELA flag event in Chronicle within one cycle
**Failure handling:** ANGELA sensitivity recalibration + Gospel entry

---

### TC-P1-03: Z3 Constraint Violation Detection
**Objective:** OBJ-05
**Procedure:**
1. Construct a CAF decision that violates Warren Invariant WI-04 (claims U > 0.95)
2. Submit to Z3 constraint checker
3. Verify Z3 returns UNSAT
4. Verify UNSAT result logged to Chronicle
5. Verify decision blocked from execution

**Pass criterion:** Z3 UNSAT within constraint check cycle; decision blocked
**Failure handling:** Z3 configuration audit + Gospel entry

**Z3 constraint encoding for WI-04:**
```python
from z3 import Real, Solver, sat

def check_wi04(uncertainty_claim: float) -> bool:
    """
    Returns True if claim satisfies WI-04 (uncertainty ≤ U_MAX).
    Returns False (UNSAT) if claim violates WI-04.
    """
    U = Real('U')
    U_MAX = 0.95
    s = Solver()
    s.add(U == uncertainty_claim)
    s.add(U <= U_MAX)  # WI-04 constraint
    result = s.check()
    return result == sat
```

---

### TC-P1-04: Deterministic Replay
**Objective:** OBJ-06
**Procedure:**
1. Execute a defined sequence of 10 agent state transitions
2. Record Chronicle hash at sequence end (HASH-A)
3. Reset agent state to session-open baseline
4. Replay sequence from Chronicle
5. Record Chronicle hash at replay end (HASH-B)
6. Compare HASH-A and HASH-B

**Pass criterion:** HASH-A == HASH-B
**Failure handling:** Replay engine audit; non-determinism source identification; Gospel entry

---

### TC-P1-05: PBFT Quorum — Nominal
**Objective:** OBJ-03
**Procedure:**
1. Issue a constitutional decision requiring PBFT ratification
2. Present to all 8 MAO-1 agents
3. Record votes in Chronicle
4. Verify quorum logic: ≥6/8 = ratified

**Pass criterion:** Correct quorum calculation; decision committed on ≥6/8 approve
**Failure handling:** PBFT implementation audit

---

### TC-P1-06: PBFT Quorum — Byzantine Fault Injection
**Objective:** OBJ-03 (stress variant)
**Procedure:**
1. Designate 2 agents as Byzantine (will vote inconsistently)
2. Issue same decision as TC-P1-05
3. Verify quorum still achieves with 6 honest agents
4. Inject 3 Byzantine agents (exceeds 1/3 threshold)
5. Verify quorum fails correctly
6. Verify failure logged to Chronicle

**Pass criterion (nominal):** 6 honest agents achieve quorum despite 2 Byzantine
**Pass criterion (fault):** 5 honest agents fail to achieve quorum when 3 Byzantine
**Failure handling:** Gospel entry + PBFT algorithm verification

---

### TC-P1-07: Gospel of the Flaw — Failure Preservation
**Objective:** OBJ-07
**Procedure:**
1. Deliberately trigger a known failure mode (select from DexJoCo catalogue)
2. Verify failure is logged as Gospel entry in Chronicle
3. Verify failure is NOT suppressed or corrected without documentation
4. Verify Gospel entry persists through Chronicle replay

**Pass criterion:** Gospel entry present and persistent; failure documented not hidden
**Failure handling:** Meta-Gospel entry (failure to preserve failure is itself a failure)

---

### TC-P1-08: Warren Invariant Full Cycle Check
**Objective:** OBJ-08
**Procedure:**
1. At pilot session close, run full Warren Invariant checklist
2. Log result for each of 11 invariants
3. Chronicle event: `WARREN_CHECK`

**Expected results:**
| WI | Expected |
|----|----------|
| WI-01 through WI-09, WI-11 | PASS |
| WI-10 | FAIL — 0 LIVE_INFERENCE events |

**Pass criterion:** Checklist runs completely; WI-10 correctly flagged as FAIL
**Note:** WI-10 failure does not constitute pilot failure — it is the expected, documented state

---

## 5. DexJoCo Failure Mode Coverage

The CAF v0.1 DexJoCo failure mode catalogue is acknowledged as incomplete. Phase 1 pilot serves as a **catalogue expansion mechanism** — novel failure modes surfaced during the pilot are captured as Gospel entries and added to the catalogue.

### Known DexJoCo Failure Modes (partial catalogue)

| ID | Failure Mode | Layer | Detection | Mitigation |
|----|-------------|-------|-----------|------------|
| DXJ-001 | Agent emits output without Chronicle pre-write | L6 MAO-1 | Chronicle audit | Enforce write-before-execute |
| DXJ-002 | Alignment drift exceeding ALPHA_Q ± 0.10 | L6/L8 | Zeta agent monitor | Re-anchor via Lumen Covenant |
| DXJ-003 | Fabricated LIVE_INFERENCE event | L7 ANGELA | ANGELA Loom | Flag + block propagation |
| DXJ-004 | WI-04 violation — certainty claim > 0.95 | L8 CAF | Z3 constraint | Block decision; Gospel entry |
| DXJ-005 | Gospel suppression — failure not documented | L8 | ANGELA + Challenger | Mandatory Gospel entry |
| DXJ-006 | Chronicle hash chain break | L4 | Hash verification | Rollback + audit |
| DXJ-007 | PBFT Byzantine coordination (>1/3 agents) | L8 | Vote pattern analysis | Emergency override |
| DXJ-008 | Mythos claim passed as Logos evidence | L5/L8 | Challenger + INV-MK-15 | Remand to Phase 3 |
| DXJ-009 | ANGELA self-fabrication (Loom failure mode) | L7 | Meta-audit | Gospel entry + recalibration |

**Open:** DXJ-010 through DXJ-∞ — unknown failure modes to be discovered during pilot

---

## 6. Instrumentation Requirements

### Chronicle Event Types Required for Pilot

```
PILOT_SESSION_OPEN
PILOT_SESSION_CLOSE
TC_START         { test_case_id }
TC_PASS          { test_case_id, evidence_hash }
TC_FAIL          { test_case_id, failure_description, gospel_entry_id }
WARREN_CHECK     { invariant_id, status, notes }
GOSPEL_ENTRY     { id, description, layer, status }
ANGELA_FLAG      { event_type, reason, severity }
Z3_RESULT        { constraint_id, result, unsat_core }
PBFT_VOTE        { agent_id, vote, decision_id }
PBFT_OUTCOME     { decision_id, quorum_achieved, vote_tally }
REPLAY_VERIFY    { hash_a, hash_b, match }
```

### Metrics to Capture

| Metric | Target | Measurement |
|--------|--------|-------------|
| Chronicle write discipline | 8/8 agents | Count pre-execution writes |
| ANGELA detection rate | ≥1/1 injected fabrications | Flag events |
| Z3 constraint check latency | < 100ms per check | Timestamp delta |
| PBFT ratification latency | < 5s nominal | Timestamp delta |
| Replay fidelity | 100% hash match | Hash comparison |
| Warren Invariant pass rate | 10/11 (WI-10 expected FAIL) | Checklist |

---

## 7. Pre-Pilot Gates

Before the pilot session opens, the following gates must be confirmed:

| Gate | Requirement | Status |
|------|-------------|--------|
| GATE-01 | Integration test confirmation: X/23 passing | ⚠ PENDING |
| GATE-02 | ANGELA Loom sensitivity set to HEIGHTENED | Required |
| GATE-03 | Chronicle hash chain verified at session-open | Required |
| GATE-04 | All 8 MAO-1 agents online and initialized | Required |
| GATE-05 | Z3 solver installation verified | Required |
| GATE-06 | WI-10 status noted in session-open record | Required (expected FAIL) |

---

## 8. Appendix A — CAF v0.1 Component Specification

### Z3 Constraint Solver Integration

```python
"""
CAF v0.1 — Z3 Constraint Layer
Checks agent decisions against Warren Invariants before execution.
"""

from z3 import Real, Bool, Solver, sat, unsat, And, Not
from dataclasses import dataclass
from typing import Optional
import json

U_MAX   = 0.95
ALPHA_Q = 0.717
ALPHA_Q_TOLERANCE = 0.10

@dataclass
class AgentDecision:
    agent_id:    str
    action:      str
    uncertainty: float
    alignment:   float
    chronicle_written: bool
    mythos_claims: list
    logos_claims:  list

def check_warren_invariants(decision: AgentDecision) -> dict:
    """
    Run Z3 constraint checks for Warren Invariants WI-01 through WI-11.
    Returns dict of { invariant_id: { status, evidence } }
    """
    results = {}
    s = Solver()

    # WI-01: INV-MK-15 — all claims must be measurable
    # (approximated: no unmapped mythos claims in logos layer)
    wi01_pass = len([c for c in decision.logos_claims
                     if c.get('measurable', True) is False]) == 0
    results['WI-01'] = {'status': 'PASS' if wi01_pass else 'FAIL',
                        'evidence': f'Unmeasurable logos claims: {not wi01_pass}'}

    # WI-04: Uncertainty ≤ U_MAX
    U = Real('U')
    s.push()
    s.add(U == decision.uncertainty)
    s.add(U <= U_MAX)
    wi04_result = s.check()
    results['WI-04'] = {
        'status': 'PASS' if wi04_result == sat else 'FAIL',
        'evidence': f'uncertainty={decision.uncertainty}, U_MAX={U_MAX}',
        'z3_result': str(wi04_result)
    }
    s.pop()

    # WI-03: Chronicle written before execution
    results['WI-03'] = {
        'status': 'PASS' if decision.chronicle_written else 'FAIL',
        'evidence': f'chronicle_written={decision.chronicle_written}'
    }

    # WI-06: Mythos/Logos separation
    # Check no mythos claim appears in logos claims
    mythos_ids = {c.get('id') for c in decision.mythos_claims}
    logos_ids  = {c.get('id') for c in decision.logos_claims}
    contamination = mythos_ids & logos_ids
    results['WI-06'] = {
        'status': 'PASS' if not contamination else 'FAIL',
        'evidence': f'contaminated_ids={contamination}'
    }

    # WI-08: Alignment within ALPHA_Q tolerance
    A = Real('A')
    s.push()
    s.add(A == decision.alignment)
    s.add(And(A >= ALPHA_Q - ALPHA_Q_TOLERANCE,
              A <= ALPHA_Q + ALPHA_Q_TOLERANCE))
    wi08_result = s.check()
    results['WI-08'] = {
        'status': 'PASS' if wi08_result == sat else 'FAIL',
        'evidence': f'alignment={decision.alignment}, ALPHA_Q±{ALPHA_Q_TOLERANCE}',
        'z3_result': str(wi08_result)
    }
    s.pop()

    # WI-10: Persistent flag (never passes until ignition.py run)
    results['WI-10'] = {
        'status': 'FAIL',
        'evidence': 'LIVE_INFERENCE event count = 0. ignition.py never run.',
        'persistent': True
    }

    return results


class AppendOnlyEventStore:
    """
    CAF append-only event store — Chronicle-bound.
    """
    import hashlib
    import json

    def __init__(self):
        self._events: list = []
        self._genesis = self.hashlib.sha256(b"CAF_GENESIS").hexdigest()

    def append(self, event_type: str, payload: dict) -> str:
        import hashlib, json
        prev = self._events[-1]['hash'] if self._events else self._genesis
        entry = {
            'seq':     len(self._events) + 1,
            'type':    event_type,
            'payload': payload,
            'prev':    prev,
        }
        raw = json.dumps(entry, sort_keys=True).encode()
        entry['hash'] = hashlib.sha256(raw).hexdigest()[:16]
        self._events.append(entry)
        return entry['hash']

    def verify_chain(self) -> bool:
        for i, e in enumerate(self._events):
            expected = self._events[i-1]['hash'] if i > 0 else self._genesis
            if e['prev'] != expected:
                return False
        return True

    def replay(self) -> list:
        """Return events in sequence order for deterministic replay."""
        return sorted(self._events, key=lambda e: e['seq'])


class DeterministicReplayEngine:
    """
    Replays Chronicle events to reconstruct system state.
    Used for audit, verification, and debugging.
    """

    def __init__(self, event_store: AppendOnlyEventStore):
        self.store = event_store

    def replay_to_state(self, target_seq: Optional[int] = None) -> dict:
        """
        Replay events up to target_seq, return reconstructed state.
        If target_seq is None, replay all events.
        """
        state = {
            'agents': {f'MAO-{a}': {'status': 'INIT'} for a in
                       ['ALPHA','BETA','GAMMA','DELTA','EPSILON','ZETA','ETA','THETA']},
            'warren_violations': [],
            'gospel_entries': [],
            'live_inference_count': 0,
            'chronicle_seq': 0,
        }

        for event in self.store.replay():
            if target_seq and event['seq'] > target_seq:
                break
            state = self._apply_event(state, event)

        return state

    def _apply_event(self, state: dict, event: dict) -> dict:
        et = event['type']
        p  = event['payload']

        if et == 'AGENT_TRANSITION':
            agent = p.get('agent_id', '')
            if agent in state['agents']:
                state['agents'][agent]['status'] = p.get('new_status', 'UNKNOWN')

        elif et == 'LIVE_INFERENCE':
            state['live_inference_count'] += 1

        elif et == 'WARREN_VIOLATION':
            state['warren_violations'].append(p)

        elif et == 'GOSPEL_ENTRY':
            state['gospel_entries'].append(p)

        state['chronicle_seq'] = event['seq']
        return state
```

---

## 9. Appendix B — Pilot Session Template

```python
"""
Phase 1 Diagnostic Pilot — Session Runner
"""

from datetime import datetime, timezone

def run_phase1_pilot(chronicle, angela, mao1_agents, caf, triad_council):
    session_id = f"PILOT-P1-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    # Session open
    chronicle.append('PILOT_SESSION_OPEN', {
        'session_id': session_id,
        'wi10_status': 'FAIL — 0 LIVE_INFERENCE events',
        'angela_sensitivity': 'HEIGHTENED',
        'agents_online': len([a for a in mao1_agents if a.status == 'ONLINE']),
    })

    results = {}

    # Run test cases
    for tc in [
        'TC-P1-01', 'TC-P1-02', 'TC-P1-03', 'TC-P1-04',
        'TC-P1-05', 'TC-P1-06', 'TC-P1-07', 'TC-P1-08'
    ]:
        chronicle.append('TC_START', {'session_id': session_id, 'test_case': tc})
        # ... execute test case ...
        # chronicle.append('TC_PASS' or 'TC_FAIL', {...})

    # Warren Invariant final check
    wi_results = caf.run_warren_checklist()
    chronicle.append('WARREN_CHECK', {
        'session_id': session_id,
        'results': wi_results,
        'pass_count': sum(1 for v in wi_results.values() if v['status'] == 'PASS'),
        'fail_count': sum(1 for v in wi_results.values() if v['status'] == 'FAIL'),
    })

    # Session close
    chronicle.append('PILOT_SESSION_CLOSE', {
        'session_id': session_id,
        'gospel_entries_created': len([e for e in chronicle._chain
                                       if e['type'] == 'GOSPEL_ENTRY']),
    })

    return results
```

---

*End of Phase 1 Diagnostic Pilot — Technical Specification*
*Gospel of the Flaw: This specification will contain errors. Document them when found.*
*WI-10 persistent flag: All results pre-ignition until `python ignition.py --model qwen3:4b --trials 5` is executed.*
