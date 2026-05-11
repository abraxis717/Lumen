"""
test_cdc.py — Tests for CDCOutbox.

Tests event publishing, unpublished retrieval, marking published,
and replay from a chronicle.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/mnt/primesauce/Garden_OS/Lumen")

from dataclasses import dataclass, field
from typing import Any, Dict, List

from lumen.materialize.cdc import CDCOutbox


# ── Minimal mock Event ────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class MockEvent:
    step: int
    action: str
    agent: str
    payload: Dict[str, Any]
    prev_hash: str
    hash: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "agent": self.agent,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


# ── Tests ─────────────────────────────────────────────────────────
def test_publish_inserts_row():
    """publish() should insert a row into the outbox table."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        outbox = CDCOutbox(db_path)
        event = MockEvent(
            step=1,
            action="belief_created",
            agent="oracle",
            payload={"claim": "test claim"},
            prev_hash="0" * 64,
            hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
        )
        result = outbox.publish(event)
        assert result is True, f"publish() should return True for new event, got {result}"

        # Verify row exists
        rows = outbox.get_unpublished()
        assert len(rows) == 1, f"Expected 1 unpublished row, got {len(rows)}"
        assert rows[0]["event_id"] == event.hash

        outbox.close()
        print("PASS: test_publish_inserts_row")
    finally:
        os.unlink(db_path)


def test_publish_duplicate_returns_false():
    """publish() should return False for duplicate event_id."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        outbox = CDCOutbox(db_path)
        event = MockEvent(
            step=1,
            action="belief_created",
            agent="oracle",
            payload={"claim": "test claim"},
            prev_hash="0" * 64,
            hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
        )
        assert outbox.publish(event) is True
        assert outbox.publish(event) is False, "Duplicate publish should return False"

        outbox.close()
        print("PASS: test_publish_duplicate_returns_false")
    finally:
        os.unlink(db_path)


def test_get_unpublished():
    """get_unpublished() should return only rows where published=0."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        outbox = CDCOutbox(db_path)

        ev1 = MockEvent(
            step=1, action="belief_created", agent="oracle",
            payload={"claim": "claim 1"},
            prev_hash="0" * 64,
            hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
        )
        ev2 = MockEvent(
            step=2, action="consensus_event", agent="council",
            payload={"claim": "claim 2"},
            prev_hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
            hash="bbbb1111cccc1111dddd1111eeee1111ffff1111aaaa1111",
        )

        outbox.publish(ev1)
        outbox.publish(ev2)

        # Both should be unpublished
        unpublished = outbox.get_unpublished()
        assert len(unpublished) == 2

        # Mark one as published
        outbox.mark_published([ev1.hash])

        # Only ev2 should remain unpublished
        unpublished = outbox.get_unpublished()
        assert len(unpublished) == 1
        assert unpublished[0]["event_id"] == ev2.hash

        outbox.close()
        print("PASS: test_get_unpublished")
    finally:
        os.unlink(db_path)


def test_mark_published():
    """mark_published() should set published=1 for the given event_ids."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        outbox = CDCOutbox(db_path)

        events = [
            MockEvent(
                step=i, action="belief_created", agent="oracle",
                payload={"claim": f"claim {i}"},
                prev_hash="0" * 64 if i == 0 else f"{'a' * 64}",
                hash=f"{'b' * 16}{i:048d}",  # unique hash per event
            )
            for i in range(5)
        ]
        for ev in events:
            outbox.publish(ev)

        # Mark first 3 as published
        outbox.mark_published([ev.hash for ev in events[:3]])

        unpublished = outbox.get_unpublished()
        assert len(unpublished) == 2, f"Expected 2 unpublished, got {len(unpublished)}"
        assert all(r["event_id"] in {ev.hash for ev in events[3:]} for r in unpublished)

        outbox.close()
        print("PASS: test_mark_published")
    finally:
        os.unlink(db_path)


def test_replay_from_chronicle():
    """replay_from(chronicle) should publish all chronicle events."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    class MockChronicle:
        def __init__(self):
            self._events = [
                MockEvent(
                    step=i, action="belief_created", agent="oracle",
                    payload={"claim": f"chronicle claim {i}"},
                    prev_hash="0" * 64 if i == 0 else f"{'c' * 64}",
                    hash=f"{'d' * 16}{i:048d}",
                )
                for i in range(3)
            ]

        def replay(self):
            return self._events

    try:
        outbox = CDCOutbox(db_path)
        chronicle = MockChronicle()
        outbox.replay_from(chronicle)

        rows = outbox.get_unpublished()
        assert len(rows) == 3, f"Expected 3 rows from replay, got {len(rows)}"

        outbox.close()
        print("PASS: test_replay_from_chronicle")
    finally:
        os.unlink(db_path)


def test_context_manager():
    """CDCOutbox should work as a context manager."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        event = MockEvent(
            step=1, action="belief_created", agent="oracle",
            payload={"claim": "test"},
            prev_hash="0" * 64,
            hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
        )
        with CDCOutbox(db_path) as outbox:
            assert outbox.publish(event) is True
            rows = outbox.get_unpublished()
            assert len(rows) == 1
        # After exit, connection should be closed
        print("PASS: test_context_manager")
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    test_publish_inserts_row()
    test_publish_duplicate_returns_false()
    test_get_unpublished()
    test_mark_published()
    test_replay_from_chronicle()
    test_context_manager()
    print("\n✅ All CDC tests passed.")
