"""
Intent — Cryptographic signed intent for constitutional operations.

Every modification to the constitutional axioms (add/remove) must be
wrapped in an Intent and signed with the operator's Ed25519 key pair.
The ConstitutionalKernel's IngressGate verifies the signature before
allowing the operation, preventing unauthorized or automated axiom
changes (e.g. from a compromised agent process).

Usage:
    from kernel.constitutional.intent import Intent
    from nacl.signing import SigningKey

    key = SigningKey.generate()
    intent = Intent(
        action="add_axiom",
        payload="No event enters without provenance.",
        operator_id="steward_1",
        signing_key=key,
    )
    assert intent.verify()  # True
    assert intent.signature.hex()[:16]  # access for logging
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.exceptions import BadSignatureError
except ImportError:
    SigningKey = None  # type: ignore
    VerifyKey = None  # type: ignore


# ---------------------------------------------------------------------------
# Intent — a signed, timestamped request to modify the constitution
# ---------------------------------------------------------------------------
@dataclass
class Intent:
    """Cryptographic signed intent for constitutional operations."""

    action: str  # "add_axiom" | "remove_axiom"
    payload: str  # the axiom text or metadata
    operator_id: str
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    # Signing key is optional at construction; can be set later.
    signing_key: Optional[SigningKey] = None  # type: ignore
    signature: Optional[bytes] = field(default=None, repr=False)

    def __post_init__(self):
        if self.signing_key is not None and self.signature is None:
            self.sign()

    # ---- signing / verification ----
    def sign(self) -> "Intent":
        """Sign the intent body with the provided SigningKey."""
        if self.signing_key is None:
            raise ValueError("Intent.sign() requires a signing_key to be set")
        body = self._canonical_body()
        self.signature = self.signing_key.sign(body).signature  # type: ignore[attr-defined]
        return self

    def verify(self) -> bool:
        """Verify the signature against the canonical body."""
        if self.signature is None or self.signing_key is None:
            return False
        try:
            body = self._canonical_body()
            self.signing_key.verify_key.verify(body, self.signature)  # type: ignore[attr-defined]
            return True
        except BadSignatureError:  # type: ignore[name-defined]
            return False
        except Exception:
            return False

    def _canonical_body(self) -> bytes:
        """Deterministic serialization for signing."""
        raw = f"{self.action}:{self.payload}:{self.operator_id}:{self.timestamp}"
        return raw.encode("utf-8")

    # ---- factory helpers ----
    @classmethod
    def from_seed(cls, action: str, payload: str, operator_id: str, seed: bytes) -> "Intent":
        """Create an Intent from a deterministic seed (useful for testing)."""
        if SigningKey is None:
            raise RuntimeError("pynacl not installed")
        key = SigningKey(seed[:32])  # NaCl requires exactly 32 bytes
        return cls(
            action=action,
            payload=payload,
            operator_id=operator_id,
            signing_key=key,
        )

    @property
    def signature_hex(self) -> str:
        return self.signature.hex() if self.signature else ""


# ---------------------------------------------------------------------------
# IngressGate — verifies Intent signatures before allowing operations
# ---------------------------------------------------------------------------
class IngressGate:
    """
    Gatekeeper for constitutional operations.

    Each authorized operator has a known Ed25519 verify key.
    An Intent is accepted only if its signature verifies against
    the operator's registered public key.
    """

    def __init__(self):
        # operator_id -> VerifyKey mapping
        self._keys: dict[str, "VerifyKey"] = {}  # type: ignore[type-arg]

    def register_operator(self, operator_id: str, verify_key: "VerifyKey") -> None:  # type: ignore[type-arg]
        """Register an authorized operator's public verify key."""
        self._keys[operator_id] = verify_key

    def verify(self, intent: Intent) -> bool:
        """
        Verify that *intent* is signed by a registered operator
        and that the signature is valid.

        Returns True only when:
          1. The operator_id has a registered VerifyKey
          2. The signature is cryptographically valid
          3. The timestamp is within 5 minutes (replay protection)
        """
        if intent.signature is None or intent.signing_key is None:
            return False
        if intent.operator_id not in self._keys:
            return False
        try:
            body = intent._canonical_body()
            self._keys[intent.operator_id].verify(body, intent.signature)  # type: ignore[attr-defined]
        except BadSignatureError:  # type: ignore[name-defined]
            return False
        except Exception:
            return False

        # Replay protection: reject intents older than 5 minutes
        age = datetime.now(timezone.utc).timestamp() - intent.timestamp
        if age > 300:
            return False

        return True

    @classmethod
    def with_steward_keys(cls) -> "IngressGate":
        """
        Convenience factory: seed-based keys for testing.

        In production, these would come from a key management system
        or hardware security module (HSM).
        """
        gate = cls()
        # Deterministic seeds for testing — NOT used in production
        steward_seed = b"steward_operator_seed_for_testing_only"
        key = SigningKey(steward_seed[:32])  # type: ignore[operator]
        gate.register_operator("steward", key.verify_key)  # type: ignore[attr-defined]
        return gate
