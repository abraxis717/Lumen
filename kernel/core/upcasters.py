"""
upcasters.py — Registry of schema upcast functions.

Currently empty; register upcasts here as schema versions evolve.

Example:
    def upcast_v1_to_v2(payload: dict) -> dict:
        payload["new_field"] = payload.pop("old_field")
        return payload

    from kernel.core.schema_registry import register_upcaster
    register_upcaster("decision", 1, 2, upcast_v1_to_v2)
"""

from kernel.core.schema_registry import register_upcaster

__all__: list[str] = []

# ── Future upcasts go here ──────────────────────────────────────
# Each upcast is keyed by (event_type, from_version, to_version).
