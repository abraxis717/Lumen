"""
claims.py — GovernedClaim schema for Phase 3 LLM-backed agents
================================================================

Phase 3 introduces structured claims that carry not just a text payload
but also a full epistemic profile: confidence, citations, and explicit
contradiction declarations.  This enables the downstream ArbitrationEngine
and GovernedCouncil to reason about the *relationship* between claims
rather than just their text content.

This dataclass is intentionally lightweight so agents (LLM-backed or
mock) can construct it from any source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class GovernedClaim:
    """A claim produced by a governed agent, carrying its epistemic metadata.

    Attributes:
        text:            The claim body (what the agent believes).
        confidence:      Agent's subjective confidence  [0.0, 1.0].
        citations:       Node IDs of BeliefNodes this claim references
                         (the *supports* edges the agent asserts).
        contradicts:     Node IDs of BeliefNodes this claim explicitly
                         contradicts (the *contradicts* edges the agent
                         declares).
        agent:           Name of the producing agent.
        metadata:        Free-form dict for extra context (e.g. LLM model,
                         prompt template, reasoning trace).
    """
    text: str
    confidence: float = 0.5
    citations: List[str] = field(default_factory=list)
    contradicts: List[str] = field(default_factory=list)
    agent: str = "unknown"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )
        if not self.text.strip():
            raise ValueError("claims.text must be non-empty")

    def to_event_payload(self) -> dict:
        """Serialize to a dict suitable for MemoryGovernor.ingest()."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "citations": self.citations,
            "contradicts": self.contradicts,
            "agent": self.agent,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return (
            f"GovernedClaim(agent={self.agent!r}, conf={self.confidence:.2f}, "
            f"text={self.text[:50]}...)"
        )
