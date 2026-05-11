"""
schema_registry.py — Versioned schema registry for event payloads.

Maps event_type → schema_version → JSON schema (dict description).
Supports upcasting events from old to current schema versions.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

# Global registry: {(event_type, from_ver, to_ver): upcast_fn}
_UPCASTERS: dict[tuple[str, int, int], Callable] = {}

# Schema definitions: {event_type: {version: dict}}
_SCHEMAS: dict[str, dict[int, dict]] = {}


def register_upcaster(
    event_type: str,
    from_version: int,
    to_version: int,
    fn: Callable[[dict], dict],
) -> None:
    """Register an upcast function for a specific event type and version range."""
    _UPCASTERS[(event_type, from_version, to_version)] = fn


def register_schema(event_type: str, version: int, schema: dict) -> None:
    """Register a schema definition for an event type."""
    if event_type not in _SCHEMAS:
        _SCHEMAS[event_type] = {}
    _SCHEMAS[event_type][version] = schema


def get_schema(event_type: str, version: int) -> Optional[dict]:
    """Retrieve a schema by event type and version."""
    return _SCHEMAS.get(event_type, {}).get(version)


def get_current_version(event_type: str) -> int:
    """Return the current (latest) schema version for an event type."""
    versions = _SCHEMAS.get(event_type, {})
    if not versions:
        return 1
    return max(versions.keys())


def upcast(event: dict, target_version: int) -> dict:
    """
    Transform an event payload from its current schema version to
    the target version by chaining registered upcast functions.

    Raises ValueError if no upcast path exists.
    """
    event_type = event.get("event_type", "unknown")
    current_version = event.get("schema_version", 1)

    if current_version == target_version:
        return event

    # Walk version steps, applying upcasters
    step = 1 if target_version > current_version else -1
    ver = current_version
    payload = dict(event.get("payload", event))

    while ver != target_version:
        key = (event_type, ver, ver + step)
        if key not in _UPCASTERS:
            raise ValueError(
                f"No upcast path from {event_type} v{ver} to v{ver + step}"
            )
        payload = _UPCASTERS[key](payload)
        ver += step

    result = dict(event)
    result["payload"] = payload
    result["schema_version"] = target_version
    return result
