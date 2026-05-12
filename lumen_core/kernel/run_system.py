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
