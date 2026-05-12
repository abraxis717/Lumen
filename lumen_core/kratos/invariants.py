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
