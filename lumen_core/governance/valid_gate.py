def gate(invariant_ok: bool, logic_status: str, current_state: str) -> bool:
    if current_state == "FORBIDDEN":
        return False
    # VALID_REFUSAL is a successful recognition of an ill-posed problem;
    # treat it like VALID_SUCCESS at the gate level.
    if logic_status in ("VALID_SUCCESS", "VALID_REFUSAL"):
        return invariant_ok
    return False
