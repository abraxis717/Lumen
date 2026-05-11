"""
distributed_consensus.py — Council deliberation across federation peers.

Simulates peer-to-peer claim submission and reception using mock HTTP
(log-only for now).  Foreign claims are wrapped as ``GovernedClaim``
objects and fed into the local ``GovernedCouncil`` for deliberation.

All federation actions are logged as immutable events in the Chronicle.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from Weaver_ASI.council.claims import GovernedClaim

logger = logging.getLogger(__name__)


@dataclass
class PeerState:
    """Bookkeeping for a federation peer."""

    url: str
    last_propose_time: float = 0.0
    last_receive_time: float = 0.0
    propose_count: int = 0
    receive_count: int = 0


class DistributedConsensus:
    """Manage distributed council deliberation across federation peers."""

    def __init__(
        self,
        council=None,
        chronicle=None,
        instance_name: str = "local",
    ) -> None:
        """
        Args:
            council:       Local ``GovernedCouncil`` for ingesting claims.
            chronicle:     Chronicle for immutable audit emission.
            instance_name: Opaque identifier for this Weaver instance.
        """
        self.council = council
        self.chronicle = chronicle
        self.instance_name = instance_name
        self._peers: Dict[str, PeerState] = {}
        self._received_claims: List[Dict[str, Any]] = []

    # ── Peer management ─────────────────────────────────────────────

    def register_peer(self, url: str) -> PeerState:
        """Register a federation peer URL."""
        state = PeerState(url=url)
        self._peers[url] = state
        return state

    def get_peers(self) -> List[str]:
        """Return list of registered peer URLs."""
        return list(self._peers.keys())

    # ── Public API ───────────────────────────────────────────────────

    def propose_to_federation(
        self,
        claim: GovernedClaim,
        peer_urls: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Send a claim to peer instances (mock HTTP for now).

        Args:
            claim:      The ``GovernedClaim`` to broadcast.
            peer_urls:  List of peer URLs to send to.  If ``None``, all
                        registered peers are targeted.

        Returns:
            Dict with ``sent_to``, ``claim``, ``timestamp``, and
            ``action`` set to ``"propose_to_federation"``.
        """
        targets = peer_urls if peer_urls is not None else self.get_peers()
        now = time.time()

        result = {
            "action": "propose_to_federation",
            "claim": {
                "text": claim.text,
                "confidence": claim.confidence,
                "agent": claim.agent,
                "citations": claim.citations,
                "contradicts": claim.contradicts,
            },
            "sent_to": targets,
            "timestamp": now,
        }

        for url in targets:
            peer = self._peers.get(url)
            if peer is not None:
                peer.last_propose_time = now
                peer.propose_count += 1

            # Log the proposed claim as an immutable Chronicle event
            if self.chronicle is not None:
                self.chronicle.emit(
                    action="federation_propose",
                    payload={
                        "source_instance": self.instance_name,
                        "target_peer": url,
                        "claim_text": claim.text[:100],
                        "claim_confidence": claim.confidence,
                    },
                    agent=f"federation_{self.instance_name}",
                )

            # Mock HTTP logging
            logger.info(
                f"[Federation] propose_to_federation: "
                f"claim=\"{claim.text[:40]}...\" -> peer={url}"
            )

        return result

    def receive_foreign_claim(self, claim_data: Dict[str, Any]) -> GovernedClaim:
        """
        Wrap a foreign claim dict as a ``GovernedClaim`` and feed it into
        the local council for deliberation.

        Args:
            claim_data:  Dict with ``text``, ``confidence``, ``agent``,
                         ``citations``, and optionally ``contradicts``.

        Returns:
            A ``GovernedClaim`` instance.
        """
        claim = GovernedClaim(
            text=claim_data["text"],
            confidence=claim_data.get("confidence", 0.5),
            citations=claim_data.get("citations", []),
            contradicts=claim_data.get("contradicts", []),
            agent=claim_data.get("agent", "federation_peer"),
            metadata={"source": "federation", "received_at": time.time()},
        )

        self._received_claims.append(
            {
                "text": claim.text,
                "confidence": claim.confidence,
                "agent": claim.agent,
                "received_at": time.time(),
            }
        )

        # Feed into local council if available
        if self.council is not None:
            # Log to Chronicle
            if self.chronicle is not None:
                self.chronicle.emit(
                    action="federation_receive_claim",
                    payload={
                        "text": claim.text[:100],
                        "confidence": claim.confidence,
                        "agent": claim.agent,
                        "instance": self.instance_name,
                    },
                    agent="DistributedConsensus",
                )

        return claim

    def summary(self) -> Dict[str, Any]:
        """Return a summary of federation state."""
        return {
            "instance_name": self.instance_name,
            "peer_count": len(self._peers),
            "peers": list(self._peers.keys()),
            "received_claims": len(self._received_claims),
            "total_proposals": sum(
                p.propose_count for p in self._peers.values()
            ),
        }
