from lumen_core.kernel.event import Event
import time

class HashChain:
    def __init__(self):
        self.chain: list[Event] = []

    def add(self, event: Event):
        if self.chain:
            event.prev_hash = self.chain[-1].hash
        event.timestamp = time.time()
        event.hash = event.compute_hash()
        self.chain.append(event)

    def verify(self) -> bool:
        for i in range(1, len(self.chain)):
            prev = self.chain[i-1]
            curr = self.chain[i]
            if curr.prev_hash != prev.hash or curr.hash != curr.compute_hash():
                return False
        return True
