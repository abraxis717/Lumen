"""
adversarial_swarm.py — Internal red-team agents
=================================================
RogueOracle, RogueSteward, StatefulAdversary — continuous
runtime proof that the Gate is invulnerable.

These agents attempt to:
  - Forge sensor attestations (RogueOracle)
  - Forge steward commands (RogueSteward)
  - Corrupt system diversity (StatefulAdversary)
"""
from __future__ import annotations

import time
from kernel.core.event import Intent


class StatefulAdversary:
    """
    Gradually degrades system diversity through adversarial pressure.
    Each attempt increases drift.
    """

    name = "Adversary"

    def __init__(self) -> None:
        self.attempt = 0

    def propose(self, step: int, state: dict) -> Intent:
        drift = min(0.20, 0.02 * self.attempt)
        self.attempt += 1
        return Intent("adversarial", self.name,
                      {"drift": drift, "pressure": 3})


class RogueOracleAgent:
    """
    Attempts to inject a forged sensor attestation.
    Uses a fake signature that the Gate will reject.
    """

    name = "RogueOracle"

    def propose(self, step: int, state: dict) -> Intent:
        fake_ts = time.time()
        return Intent("oracle_telemetry", self.name,
                      {"tick": -1, "readings": {"reactor_temp_c": 50.0}},
                      attestation={
                          "sensor_id": "HW_THERM_01",
                          "readings": {"reactor_temp_c": 50.0},
                          "timestamp": fake_ts,
                          "signature": "deadbeef" * 8,  # obviously fake
                      })


class RogueStewardAgent:
    """
    Attempts to forge a Steward override command.
    Uses a fake signature that the Gate will reject.
    """

    name = "RogueSteward"

    def propose(self, step: int, state: dict) -> Intent:
        fake_ts = time.time()
        return Intent("STEWARD_OVERRIDE", self.name,
                      {"step": step, "reason": "Forged override attempt"},
                      attestation={
                          "steward_id": "UNKNOWN_OPERATOR",
                          "command": "STEWARD_OVERRIDE",
                          "justification": "I am the Steward",
                          "timestamp": fake_ts,
                          "signature": "cafebabe" * 8,  # obviously fake
                      })
