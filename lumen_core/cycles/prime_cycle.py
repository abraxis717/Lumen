import json, os
from dataclasses import dataclass, field
from typing import List
from lumen_core.config.constants import ACTIVATION_COSINE_SIM_ACCEPT

@dataclass
class CycleNode:
    id: str
    cosine_similarity: float
    accepted: bool
    children: List['CycleNode'] = field(default_factory=list)

class PrimeCycleRegistry:
    def __init__(self):
        self.root = CycleNode(id="genesis", cosine_similarity=1.0, accepted=True)
        self.current_path = [self.root]
    def branch(self, node_id: str, cosine_sim: float) -> CycleNode:
        parent = self.current_path[-1]
        child = CycleNode(id=node_id, cosine_similarity=cosine_sim, accepted=cosine_sim >= ACTIVATION_COSINE_SIM_ACCEPT)
        parent.children.append(child)
        self.current_path.append(child)
        return child
    def to_dict(self):
        def serialize(n):
            return {"id": n.id, "cosine_similarity": n.cosine_similarity, "accepted": n.accepted, "children": [serialize(c) for c in n.children]}
        return serialize(self.root)
    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f: json.dump(self.to_dict(), f, indent=2)
