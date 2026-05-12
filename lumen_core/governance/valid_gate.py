def gate(invariant_ok: bool, logic_status: str, current_state: str) -> bool:
    if current_state == "FORBIDDEN":
        return False
    return invariant_ok and logic_status == "VALID_SUCCESS"
