from enum import Enum


class MemoryStratum(Enum):
    EPHEMERAL = "ephemeral"
    OPERATIONAL = "operational"
    POLICY = "policy"
    CONSTITUTIONAL = "constitutional"
    DISPUTED = "disputed"
    DEPRECATED = "deprecated"
    SPECULATIVE = "speculative"