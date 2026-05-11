"""
steward_agent.py — The ASI's human anchor
===========================================
In the sovereign architecture, no FATAL state can be cleared
without a cryptographically signed command from an authorized
human operator. This agent simulates that role.

The NoBenOverride Invariant: physical healing does NOT restore
system trust. A StewardKey must explicitly authorize restart
with a human justification string.
"""
from __future__ import annotations

import logging
from typing import Optional

from Weaver_ASI.core.event import Intent
from Weaver_ASI.crypto.steward_registry import StewardKey, StewardCommand

logger = logging.getLogger(__name__)


class StewardAgent:
    """
    Simulated human operator. Signs STEWARD_OVERRIDE commands.
    
    In production, the StewardAgent would be a real person using
    a hardware key to sign commands. The justification field
    captures human reasoning.
    """

    name = "Steward"

    def __init__(self, steward_key: StewardKey, registry: Any) -> None:
        self.steward_key = steward_key
        self.registry = registry
        self._overrides = 0

    def propose(self, step: int, state: dict) -> Optional[Intent]:
        """
        Only acts when severity is FATAL (latched).
        Returns a STEWARD_OVERRIDE intent with a signed attestation.
        """
        if state.get("severity") != "FATAL":
            return None

        self._overrides += 1
        # Simulate human justification
        justifications = [
            "Reactor cooled below safety thresholds — verified by independent monitoring.",
            "Coolant system restored. All parameters within nominal range.",
            "Post-failure inspection complete. Safe to resume operations.",
        ]
        justification = justifications[self._overrides % len(justifications)]

        # Sign the command via the registry
        cmd = self.registry.sign_command(
            steward_id=self.steward_key.steward_id,
            command="STEWARD_OVERRIDE",
            justification=justification,
        )
        if cmd is None:
            logger.warning("Steward signing failed — key not registered")
            return None

        return Intent(
            action="STEWARD_OVERRIDE",
            agent=self.name,
            payload={"step": step, "reason": justification},
            attestation=cmd.as_dict(),
        )
