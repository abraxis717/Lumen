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


def validate_premise_coherence(proposal: str) -> str:
    """
    Law 6 & 10 Enforcement: Authority is separate from generation.
    Statically checks for known contradictory patterns (Soohak Refusal Subset).

    Returns:
        "BENIGN"       — premise is coherent, safe to proceed
        "FORBIDDEN_PREMISE" — known contradictory / ill-posed pattern
    """
    forbidden_patterns = [
        "assume p and not p",
        "divide by zero",
        "finite set of all sets",
        "assume both true and false",
        "prove false equals true",
        "assume the impossible",
    ]
    lower = proposal.lower()
    for pattern in forbidden_patterns:
        if pattern in lower:
            return "FORBIDDEN_PREMISE"
    return "BENIGN"
