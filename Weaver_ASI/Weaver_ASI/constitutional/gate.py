"""
ConstitutionalGate — Plugin registry for constitutional validators.

Any module can register a validation function (claim_text -> bool) that
will be consulted every time a belief is checked for validity.  This is
the open dev-port for third-party safety checks (PII filtering,
injection detection, domain restrictions, etc.).

Usage:
    from Weaver_ASI.constitutional.gate import ConstitutionalGate

    def no_sql_injection(text: str) -> bool:
        banned = ["DROP ", "UNION ", "EXEC ", "TRUNCATE "]
        return not any(b in text.upper() for b in banned)

    ConstitutionalGate.register(no_sql_injection)
"""

from __future__ import annotations
from typing import Callable, List

ValidatorFn = Callable[[str], bool]   # takes claim text, returns True if valid


class ConstitutionalGate:
    """Singleton registry of constitutional validation plugins."""

    _validators: List[ValidatorFn] = []

    @classmethod
    def register(cls, fn: ValidatorFn) -> None:
        """Register a validation function."""
        cls._validators.append(fn)

    @classmethod
    def unregister(cls, fn: ValidatorFn) -> None:
        """Remove a previously registered validator."""
        if fn in cls._validators:
            cls._validators.remove(fn)

    @classmethod
    def validate(cls, claim_text: str) -> bool:
        """All registered validators must pass."""
        return all(v(claim_text) for v in cls._validators)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered validators."""
        cls._validators.clear()

    @classmethod
    def validator_count(cls) -> int:
        return len(cls._validators)

    @classmethod
    def list_validators(cls) -> List[str]:
        return [v.__name__ for v in cls._validators]
