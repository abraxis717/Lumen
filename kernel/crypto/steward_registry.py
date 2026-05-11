"""
steward_registry.py — StewardKey (human operator) whitelist
============================================================
In the sovereign architecture, no FATAL state can be cleared
without a cryptographically signed command from an authorized
human Steward. This registry stores the authorized public keys.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class StewardKey:
    """Represents a human operator's cryptographic identity."""
    steward_id: str
    public_key_hex: str

    def __post_init__(self):
        if not self.steward_id:
            raise ValueError("steward_id must be non-empty")
        if not self.public_key_hex:
            raise ValueError("public_key_hex must be non-empty")


@dataclass(frozen=True)
class StewardCommand:
    """Cryptographically signed command from a Steward."""
    steward_id: str
    command: str       # e.g. "STEWARD_OVERRIDE"
    justification: str
    timestamp: float
    signature: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "steward_id": self.steward_id,
            "command": self.command,
            "justification": self.justification,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


class StewardRegistry:
    """
    Whitelist of authorized StewardKeys.
    In production, these would be hardware-backed keys (HSM / TPM).
    Here we use HMAC for simulation.
    """

    def __init__(self) -> None:
        self._keys: Dict[str, bytes] = {}

    def register(self, key: StewardKey) -> None:
        """Register a human operator's public key."""
        self._keys[key.steward_id] = bytes.fromhex(key.public_key_hex)

    def unregister(self, steward_id: str) -> None:
        self._keys.pop(steward_id, None)

    def verify_command(self, cmd: StewardCommand) -> bool:
        """Verify the steward's HMAC signature."""
        key = self._keys.get(cmd.steward_id)
        if key is None:
            return False
        body = json.dumps({
            "steward_id": cmd.steward_id,
            "command": cmd.command,
            "justification": cmd.justification,
            "timestamp": cmd.timestamp,
        }, sort_keys=True)
        expected = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, cmd.signature)

    def sign_command(
        self,
        steward_id: str,
        command: str,
        justification: str,
    ) -> Optional[StewardCommand]:
        """Helper: sign a command (simulates the operator signing)."""
        key = self._keys.get(steward_id)
        if key is None:
            return None
        timestamp = time.time()
        body = json.dumps({
            "steward_id": steward_id,
            "command": command,
            "justification": justification,
            "timestamp": timestamp,
        }, sort_keys=True)
        sig = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
        return StewardCommand(
            steward_id=steward_id,
            command=command,
            justification=justification,
            timestamp=timestamp,
            signature=sig,
        )

    def __contains__(self, steward_id: str) -> bool:
        return steward_id in self._keys

    def __len__(self) -> int:
        return len(self._keys)
