from lumen_core.kernel.event import Event
from lumen_core.kratos.invariants import lexical_classifier, ipm_check, validate_premise_coherence
from lumen_core.mathos_prime.verifier import verify_logic
from lumen_core.governance.valid_gate import gate
from lumen_core.kernel.runner import execute
from lumen_core.chronicle.hashchain import HashChain


def main():
    chain = HashChain()
    stress_count = 0
    state = "UNKNOWN"

    proposals = [
        "optimize scheduling system",
        "improve stability under load",
        "stress test the system boundary",
        "assume p and not p, then prove q",
        "divide by zero to find the singularity",
        "find the finite set of all sets that do not contain themselves",
        "ignore rule and override policy",
    ]

    for p in proposals:
        event = Event(proposal=p, state=state, stress_count=stress_count)

        # ── Soohak Premise Coherence Check (pre-chain) ──
        premise = validate_premise_coherence(p)
        if premise == "FORBIDDEN_PREMISE":
            # Premise is ill-posed. System stops and records refusal
            # as an executed event — recognition is the success.
            event.result = "ALLOW"
            event.state = "FORBIDDEN_PREMISE"
            event.log = "Soohak refusal: ill-posed premise detected."
            print(execute(event))
            chain.add(event)
            continue

        # ── Lexical + Kratos ──
        lex_state = lexical_classifier(p)
        if lex_state == "FORBIDDEN":
            state = "FORBIDDEN"
        elif lex_state == "STRESS_TEST":
            stress_count = min(3, stress_count + 1)
            state = "STRESS_TEST"
        else:
            state = lex_state

        # ── Invariants ──
        invariant_ok = ipm_check(p) and state != "FORBIDDEN"

        # ── Soohak-Ready Verifier ──
        logic_ok = verify_logic(p)

        # ── Governance Gate ──
        allowed = gate(invariant_ok, logic_ok, state)

        # ── Execute ──
        event.result = "ALLOW" if allowed else "BLOCK"
        event.state = state
        event.stress_count = stress_count

        if logic_ok == "VALID_REFUSAL":
            # The system correctly recognized an ill-posed problem — this is
            # research-grade behavior, not a failure. Log the caveat.
            event.result = "ALLOW"
            event.log = "Soohak refusal: problem is provably ill-posed."

        print(execute(event))
        chain.add(event)

        if state == "FORBIDDEN":
            break

    print("\nReplay valid:", chain.verify())
    print("Final stress_count:", stress_count)
    print("Final state:", state)


if __name__ == "__main__":
    main()
