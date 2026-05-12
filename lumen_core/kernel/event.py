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
    log: str = ""                    # Soohak refusal caveat log

    def compute_hash(self) -> str:
        payload = json.dumps({
            "proposal": self.proposal,
            "result": self.result,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "state": self.state,
            "stress_count": self.stress_count,
            "log": self.log
        }, sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()
