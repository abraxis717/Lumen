"""
reality_registry.py — HardwareSensor key whitelist
====================================================
Whitelist of authorized sensor public keys.
Every attestation from an unregistered sensor is rejected.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Attestation:
    """Signed sensor reading — must be verified before entering the system."""
    sensor_id: str
    readings:  Dict[str, float]
    timestamp: float
    signature: str

    def as_dict(self) -> Dict:
        return {
            "sensor_id": self.sensor_id,
            "readings": self.readings,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


class HardwareSensor:
    """
    Simulates a hardware sensor. Generates HMAC-signed attestations.
    In production, the signing key never leaves the hardware.
    """

    def __init__(self, sensor_id: str, world: Any = None) -> None:
        self.sensor_id = sensor_id
        self._key = secrets.token_bytes(32)
        self.public_key_hex = self._key.hex()
        self._world = world

    def sample(self) -> Attestation:
        readings = {}
        if self._world is not None:
            readings = self._world.snapshot() if hasattr(self._world, "snapshot") else {}

        timestamp = time.time()
        body = json.dumps({
            "sensor_id": self.sensor_id,
            "readings": readings,
            "timestamp": timestamp,
        }, sort_keys=True)
        sig = hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
        return Attestation(self.sensor_id, readings, timestamp, sig)


class RealityRegistry:
    """
    Whitelist of authorized HardwareSensor public keys.
    Only registered sensors' attestations are accepted.
    """

    def __init__(self) -> None:
        self._keys: Dict[str, bytes] = {}

    def register(self, sensor: HardwareSensor) -> None:
        """Register a sensor by its public key."""
        self._keys[sensor.sensor_id] = bytes.fromhex(sensor.public_key_hex)

    def unregister(self, sensor_id: str) -> None:
        self._keys.pop(sensor_id, None)

    def verify(self, a) -> bool:
        """Verify HMAC signature against stored key. O(1)."""
        # Accept both Attestation objects and dicts
        if hasattr(a, "sensor_id"):
            sensor_id = a.sensor_id
            readings = a.readings
            timestamp = a.timestamp
            sig = a.signature
        else:
            sensor_id = a.get("sensor_id", "")
            readings = a.get("readings", {})
            timestamp = a.get("timestamp", 0)
            sig = a.get("signature", "")
        key = self._keys.get(sensor_id)
        if key is None:
            return False
        body = json.dumps({
            "sensor_id": sensor_id,
            "readings": readings,
            "timestamp": timestamp,
        }, sort_keys=True)
        expected = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)

    def __contains__(self, sensor_id: str) -> bool:
        return sensor_id in self._keys

    def __len__(self) -> int:
        return len(self._keys)
