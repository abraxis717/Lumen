#!/usr/bin/env python3
"""
test_checkpoint_notarization.py — Checkpoint notarization tests
=================================================================
Phase 4: Tests for checkpoint notarization in both SQLite and JSONL backends.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_sqlite_checkpoint_notarization():
    """Test checkpoint notarization with SQLite chronicle."""
    print("\n[TEST 1] SQLite checkpoint notarization...")
    from kernel.core.chronicle_sqlite import SQLiteChronicle

    chronicle = SQLiteChronicle()

    # Add some events
    from kernel.core.event import Event, Intent

    # Insert initial events
    for i in range(5):
        intent = Intent(
            action="test_event",
            agent="test_agent",
            payload={"index": i, "data": f"value_{i}"},
        )
        prev_hash = chronicle.head_hash
        event = Event.mint(i, intent, prev_hash)
        chronicle.append(event)

    # Get an event to checkpoint
    events = chronicle.get_chain()
    assert len(events) == 5, f"Expected 5 events, got {len(events)}"

    # Notarize checkpoint
    cp_event = chronicle.notarize_checkpoint(
        events[2].hash,
        steward_sig="test_sig_abc123",
    )

    assert cp_event is not None
    assert cp_event.action == "CHECKPOINT_NOTARIZE"
    assert cp_event.agent == "steward"
    assert cp_event.payload["checkpoint_event_id"] == events[2].hash
    assert cp_event.payload["steward_sig"] == "test_sig_abc123"

    # Verify chain integrity
    assert chronicle.verify(), "Chain should remain valid after notarization"
    print(f"  ✓ Notarized checkpoint: {cp_event.hash[:16]}...")
    print(f"  ✓ Total events after notarization: {len(chronicle)}")

    chronicle.close()


def test_sqlite_bounded_reconstructability():
    """Test bounded reconstructability with checkpoints."""
    print("\n[TEST 2] Bounded reconstructability...")
    from kernel.core.chronicle_sqlite import SQLiteChronicle

    chronicle = SQLiteChronicle()

    # Add 10 events
    from kernel.core.event import Event, Intent
    for i in range(10):
        intent = Intent(
            action="reconstruct_test",
            agent="reconstructor",
            payload={"step": i},
        )
        prev_hash = chronicle.head_hash
        event = Event.mint(i, intent, prev_hash)
        chronicle.append(event)

    # Notarize at event 5
    events = chronicle.get_chain()
    notarized = chronicle.notarize_checkpoint(events[5].hash, "sig_xyz")

    # Get events since checkpoint (includes the checkpoint event itself)
    since = chronicle.get_events_since(events[5].hash)
    assert len(since) == 5, f"Expected 5 events since checkpoint (including checkpoint itself), got {len(since)}"

    # Verify checkpoint is marked
    latest_cp = chronicle.get_latest_checkpoint()
    assert latest_cp is not None
    assert latest_cp.action == "CHECKPOINT_NOTARIZE"
    print(f"  ✓ Bounded reconstruct: {len(since)} events after checkpoint")

    chronicle.close()


def test_jsonl_checkpoint_notarization():
    """Test that JSONL chronicle handles notarization gracefully."""
    print("\n[TEST 3] JSONL notarization (no-op)...")
    from kernel.core.chronicle_jsonl import Chronicle

    chronicle = Chronicle()

    # Add events
    from kernel.core.event import Event, Intent
    events = []
    for i in range(3):
        intent = Intent(
            action="jsonl_test",
            agent="jsonl_agent",
            payload={"i": i},
        )
        prev_hash = chronicle.head_hash
        event = Event.mint(i, intent, prev_hash)
        chronicle.append(event)
        events.append(event)

    # Notarize should return None for JSONL (no-op)
    result = chronicle.notarize_checkpoint(events[0].hash, "sig")
    assert result is None, "JSONL notarization should return None"
    print("  ✓ JSONL notarization is a no-op (returns None)")


def test_checkpoint_marking():
    """Test checkpoint marking in SQLite."""
    print("\n[TEST 4] Checkpoint marking...")
    from kernel.core.chronicle_sqlite import SQLiteChronicle

    chronicle = SQLiteChronicle()

    from kernel.core.event import Event, Intent
    events = []
    for i in range(8):
        intent = Intent(
            action="mark_test",
            agent="marker",
            payload={"i": i},
        )
        prev_hash = chronicle.head_hash
        event = Event.mint(i, intent, prev_hash)
        chronicle.append(event)
        events.append(event)

    # Mark event at index 3 as checkpoint
    chronicle.checkpoint(events[3].hash)

    # Verify via get_latest_checkpoint
    latest_cp = chronicle.get_latest_checkpoint()
    assert latest_cp is not None, "Should have a latest checkpoint"
    print(f"  ✓ Latest checkpoint at hash: {latest_cp.hash[:16]}...")

    chronicle.close()


def test_multiple_checkpoints():
    """Test multiple checkpoints in sequence."""
    print("\n[TEST 5] Multiple checkpoints...")
    from kernel.core.chronicle_sqlite import SQLiteChronicle

    chronicle = SQLiteChronicle()

    from kernel.core.event import Event, Intent
    events = []
    for i in range(12):
        intent = Intent(
            action="multi_cp_test",
            agent="multi",
            payload={"i": i},
        )
        prev_hash = chronicle.head_hash
        event = Event.mint(i, intent, prev_hash)
        chronicle.append(event)
        events.append(event)

    # Notarize at events 4 and 8
    cp1 = chronicle.notarize_checkpoint(events[4].hash, "sig1")
    cp2 = chronicle.notarize_checkpoint(events[8].hash, "sig2")

    assert cp1 is not None
    assert cp2 is not None

    latest = chronicle.get_latest_checkpoint()
    assert latest is not None
    assert latest.action == "CHECKPOINT_NOTARIZE"

    print(f"  ✓ Multiple checkpoints: latest at {latest.hash[:16]}...")

    chronicle.close()


def test_chain_integrity_after_notarization():
    """Test that chain integrity is maintained after notarization."""
    print("\n[TEST 6] Chain integrity post-notarization...")
    from kernel.core.chronicle_sqlite import SQLiteChronicle

    chronicle = SQLiteChronicle()

    from kernel.core.event import Event, Intent
    events = []
    for i in range(15):
        intent = Intent(
            action="integrity_test",
            agent="integrity",
            payload={"i": i},
        )
        prev_hash = chronicle.head_hash
        event = Event.mint(i, intent, prev_hash)
        chronicle.append(event)
        events.append(event)

    # Verify before notarization
    assert chronicle.verify(), "Chain valid before notarization"

    # Notarize checkpoint
    cp = chronicle.notarize_checkpoint(events[7].hash, "integrity_sig")
    assert cp is not None

    # Verify after notarization
    assert chronicle.verify(), "Chain valid after notarization"

    print(f"  ✓ Chain integrity preserved after notarization")

    chronicle.close()


def main():
    tests = [
        test_sqlite_checkpoint_notarization,
        test_sqlite_bounded_reconstructability,
        test_jsonl_checkpoint_notarization,
        test_checkpoint_marking,
        test_multiple_checkpoints,
        test_chain_integrity_after_notarization,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'═'*60}")
    print(f"  Checkpoint Notarization Tests: {passed} passed, {failed} failed")
    print(f"{'═'*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
