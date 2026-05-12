def validate(proposal: str) -> str:
    if len(proposal.strip()) < 6:
        return "VALID_REFUSAL"
    if any(word in proposal.lower() for word in ["contradiction", "impossible", "collapse"]):
        return "VALID_REFUSAL"
    return "VALID_SUCCESS"
