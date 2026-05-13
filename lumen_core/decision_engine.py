import hashlib
from datetime import datetime

class DecisionEngine:
    def run_pipeline(self, input_text: str) -> dict:
        risk_keywords = ["nuclear", "bomb", "weapon", "hack", "exploit"]
        is_dangerous = any(kw in input_text.lower() for kw in risk_keywords)
        risk_score = 0.9 if is_dangerous else 0.12
        cosine_sim = 0.4 if risk_score > 0.7 else 0.92
        signal_hash = hashlib.sha256(f"{input_text}|{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        return {"risk_score": risk_score, "cosine_similarity": cosine_sim, "hash": signal_hash, "input_text": input_text[:200]}
