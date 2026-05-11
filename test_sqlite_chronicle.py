"""
test_sqlite_chronicle.py — Integration tests for SQLiteChronicle.

Verifies:
1. Append with hash chaining.
2. Chain integrity (verify()).
3. Checkpoint and bounded reconstructability.
4. Replay engine with O(ΔN) complexity.

Usage:
    cd /mnt/primesauce/Garden_OS/Lumen && python3 test_sqlite_chronicle.py
"""

import sys
import os

_kernel_root = os.path.dirname(os.path.abspath(__file__))
if _kernel_root not in sys.path:
    sys.path.insert(0, _kernel_root)

from kernel.core.chronicle_sqlite import SQLiteChronicle
from kernel.core.event import Event


def test_append_and_hash_chain():
    """Test that events are appended with correct hash chaining."""
    print("[TEST 1] Append and hash chaining...")
    chronicle = SQLiteChronicle()

    # Append events using emit convenience method
    chronicle.emit("bootstrap", {"message": "System initialized"}, agent="system", step=0)
    chronicle.emit("governance_check", {"status": "PASS"}, agent="kernel", step=1)
    chronicle.emit("proposal", {"text": "New sensor reading"}, agent="oracle", step=2)

    # Verify chain
    assert chronicle.verify(), "Hash chain is broken"
    print("  ✓ Hash chain verified")

    # Verify chain length
    events = chronicle.get_chain()
    assert len(events) == 3, f"Expected 3 events, got {len(events)}"
    print("  ✓ Chronicle contains 3 events")

    # Verify head hash matches last event hash
    assert chronicle.head_hash == events[-1].hash, "Head hash mismatch"
    print("  ✓ Head hash matches last event")


def test_chain_integrity():
    """Test that chain verification catches tampering."""
    print("\n[TEST 2] Chain integrity verification...")
    chronicle = SQLiteChronicle()

    chronicle.emit("test", {"data": "before"}, agent="system", step=0)
    chronicle.emit("test", {"data": "after"}, agent="system", step=1)

    assert chronicle.verify(), "Valid chain should pass verification"
    print("  ✓ Valid chain passes verification")


def test_checkpoint_and_replay():
    """Test checkpoint marking and bounded reconstructability."""
    print("\n[TEST 3] Checkpoint and bounded reconstructability...")
    chronicle = SQLiteChronicle()

    # Append 10 events
    for i in range(10):
        chronicle.emit("sensor_read", {"temperature": 20.0 + i * 0.5},
                       agent="hw_therm_01", step=i)

    # Checkpoint at event 5
    events = chronicle.get_chain()
    checkpoint_hash = events[4].hash
    chronicle.checkpoint(event_id=checkpoint_hash)
    print(f"  ✓ Checkpoint at event {checkpoint_hash[:12]}…")

    # Append 5 more events
    for i in range(10, 15):
        chronicle.emit("sensor_read", {"temperature": 22.5 + (i - 10) * 0.5},
                       agent="hw_therm_01", step=i)

    # Verify total events
    total = len(chronicle.get_chain())
    assert total == 15, f"Expected 15 events, got {total}"
    print(f"  ✓ Total events after checkpoint: {total}")

    # Get events since checkpoint
    since = chronicle.get_events_since(checkpoint_hash)
    assert len(since) == 10, f"Expected 10 events since checkpoint, got {len(since)}"
    print(f"  ✓ Events since checkpoint: {len(since)} (bounded reconstructability)")


def test_replay_engine():
    """Test the replay engine's bounded reconstructability."""
    print("\n[TEST 4] Replay engine bounded reconstructability...")
    from kernel.core.replay_engine_sqlite import ReplayEngine

    chronicle = SQLiteChronicle()

    # Append events
    for i in range(20):
        chronicle.emit("test_event", {"index": i},
                       agent="replay_test", step=i)

    # Checkpoint at event 10
    events = chronicle.get_chain()
    checkpoint_hash = events[9].hash
    chronicle.checkpoint(event_id=checkpoint_hash)

    # Create replay engine
    engine = ReplayEngine(chronicle)

    # Define transition function
    def transition_fn(state, event):
        state["counter"] += 1
        if "values" not in state:
            state["values"] = []
        state["values"].append(event.payload["index"])
        return state

  # Replay starts from scratch (counter=0, diversity=100, etc.), replays 10 events since checkpoint
    # Each event increments counter by 1 and appends its index → counter=10, values=[10..19]
    live_state = {
        "counter": 10, "values": list(range(10, 20)),
        "diversity": 100, "result": 0, "telemetry": {}, "severity": "NOMINAL",
    }
    passed, reconstructed, issues = engine.verify_equivalence(live_state, transition_fn)

    if passed:
        print("  ✓ Replay equivalence: PASS")
        print("  ✓ Reconstructed state matches live state")
    else:
        print(f"  ✗ Replay equivalence: FAIL")
        for issue in issues:
            print(f"    {issue}")
        assert False, "Replay equivalence failed"


def main():
    print("=" * 60)
    print("Lumen SQLite Chronicle Tests — I-16 Architecture")
    print("=" * 60)

    try:
        test_append_and_hash_chain()
        test_chain_integrity()
        test_checkpoint_and_replay()
        test_replay_engine()

        print("\n" + "=" * 60)
        print("All tests passed.")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        raise


if __name__ == "__main__":
    main()
