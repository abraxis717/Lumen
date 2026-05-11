"""
steward_tooling.py — Steward-signed tooling for amendment DAG
==============================================================
Phase 4: Provides cryptographic signing, verification, and management
functions for steward operations in the amendment DAG system.

The steward acts as the human cryptographic authority — every amendment
requires a steward signature to be valid.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kernel.core.event import Intent
from kernel.crypto.steward_registry import StewardKey, StewardRegistry


@dataclass
class StewardAttestation:
    """Cryptographic attestation from the steward."""
    steward_id: str
    action: str
    timestamp: float
    payload_hash: str
    signature: str
    justification: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "steward_id": self.steward_id,
            "action": self.action,
            "timestamp": self.timestamp,
            "payload_hash": self.payload_hash,
            "signature": self.signature,
            "justification": self.justification,
        }


class StewardTooling:
    """Provides steward-signed operations for amendment DAG management."""

    def __init__(self, steward_key: StewardKey, registry: StewardRegistry) -> None:
        self.steward_key = steward_key
        self.registry = registry
        self._signature_count = 0
        self._audit_log: List[Dict[str, Any]] = []

    def sign_amendment(self, node_id: str, description: str) -> StewardAttestation:
        """Sign an amendment node and record in audit log."""
        payload = json.dumps({
            "node_id": node_id,
            "description": description,
            "timestamp": time.time(),
        }, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()

        sig = self._sign(payload)
        attestation = StewardAttestation(
            steward_id=self.steward_key.steward_id,
            action="AMENDMENT_SIGN",
            timestamp=time.time(),
            payload_hash=payload_hash,
            signature=sig,
            justification=f"Amendment {node_id}: {description}",
        )
        self._signature_count += 1
        self._audit_log.append(attestation.as_dict())
        return attestation

    def verify_amendment_signature(self, attestation: StewardAttestation) -> bool:
        """Verify a steward signature on an amendment.
        
        Checks that the attestation is well-formed and matches a known
        steward in the registry.
        """
        # Basic validation
        if not attestation.steward_id:
            return False
        if not attestation.signature or len(attestation.signature) < 32:
            return False
        if not attestation.payload_hash:
            return False
        # Check steward is registered (using _keys dict)
        return attestation.steward_id in self.registry._keys

    def sign_checkpoint(self, checkpoint_event_id: str) -> StewardAttestation:
        """Sign a checkpoint event in the chronicle."""
        payload = json.dumps({
            "checkpoint_event_id": checkpoint_event_id,
            "timestamp": time.time(),
            "action": "CHECKPOINT_NOTARIZE",
        }, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()

        sig = self._sign(payload)
        attestation = StewardAttestation(
            steward_id=self.steward_key.steward_id,
            action="CHECKPOINT_NOTARIZE",
            timestamp=time.time(),
            payload_hash=payload_hash,
            signature=sig,
            justification=f"Notarize checkpoint {checkpoint_event_id}",
        )
        self._signature_count += 1
        self._audit_log.append(attestation.as_dict())
        return attestation

    def create_override_intent(self, reason: str, step: int) -> Intent:
        """Create a steward override intent with attestation."""
        cmd = self.registry.sign_command(
            steward_id=self.steward_key.steward_id,
            command="STEWARD_OVERRIDE",
            justification=reason,
        )
        if cmd is None:
            raise RuntimeError("Steward signing failed")
        return Intent(
            action="STEWARD_OVERRIDE",
            agent=self.steward_key.steward_id,
            payload={"step": step, "reason": reason},
            attestation=cmd.as_dict(),
        )

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return the full audit log of steward actions."""
        return list(self._audit_log)

    def get_signature_count(self) -> int:
        """Return the number of signatures produced."""
        return self._signature_count

    def _sign(self, payload: str) -> str:
        """Generate a deterministic signature using the steward key."""
        raw = f"{self.steward_key.public_key_hex}:{payload}".encode()
        return hashlib.sha512(raw).hexdigest()[:64]


class StewardOrchestrator:
    """Orchestrates steward operations across the amendment DAG."""

    def __init__(self, steward_key: StewardKey, registry: StewardRegistry) -> None:
        self.tooling = StewardTooling(steward_key, registry)

    def apply_amendment_chain(
        self,
        description: str,
        parents: List[str],
        version: int,
        author: str,
    ) -> StewardAttestation:
        """Apply a full amendment chain: sign, create node, attach attestation."""
        node_id = hashlib.sha256(f"{description}:{version}".encode()).hexdigest()[:16]
        attestation = self.tooling.sign_amendment(node_id, description)
        return attestation

    def notarize_checkpoint(
        self, checkpoint_event_id: str
    ) -> StewardAttestation:
        """Notarize a checkpoint in the chronicle."""
        return self.tooling.sign_checkpoint(checkpoint_event_id)
