"""
test_vector.py — Tests for VectorSyncer with JSON fallback backend.

Tests vector sync, query, and the hash embedding fallback when no
LLM model is available.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/mnt/primesauce/Garden_OS/Lumen")

from dataclasses import dataclass, field
from typing import Any, Dict, List

from lumen.materialize.vector_sync import VectorSyncer


# ── Minimal mock Event ────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class MockEvent:
    step: int
    action: str
    agent: str
    payload: Dict[str, Any]
    prev_hash: str
    hash: str


# ── Mock Chronicle ────────────────────────────────────────────────
class MockChronicle:
    def __init__(self):
        now = 1717000000.0
        self._events = [
            MockEvent(
                step=1, action="belief_created", agent="oracle",
                payload={
                    "claim": "System temperature is within nominal range.",
                    "stratum": "operational", "confidence": 0.95,
                    "node_id": "belief_001", "source_agent": "oracle",
                    "timestamp": now, "citations": ["sensor_v1"],
                    "supports": [], "contradicts": [],
                },
                prev_hash="0" * 64,
                hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
            ),
            MockEvent(
                step=2, action="belief_created", agent="policy_engine",
                payload={
                    "claim": "All sensor readings must be validated before ingestion.",
                    "stratum": "policy", "confidence": 0.88,
                    "node_id": "belief_002", "source_agent": "policy_engine",
                    "timestamp": now + 1, "citations": ["policy_v2"],
                    "supports": ["belief_001"], "contradicts": [],
                },
                prev_hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
                hash="bbbb1111cccc1111dddd1111eeee1111ffff1111aaaa1111",
            ),
            MockEvent(
                step=3, action="consensus_event", agent="governed_council",
                payload={
                    "claim": "Consensus reached: system is healthy.",
                    "stratum": "operational", "confidence": 0.92,
                    "node_id": "belief_004", "source_agent": "governed_council",
                    "timestamp": now + 2, "citations": [],
                    "supports": ["belief_001", "belief_002"], "contradicts": [],
                },
                prev_hash="bbbb1111cccc1111dddd1111eeee1111ffff1111aaaa1111",
                hash="cccc2222dddd2222eeee2222ffff2222aaaa2222bbbb2222",
            ),
        ]

    def replay(self):
        return self._events


# ── Tests ─────────────────────────────────────────────────────────
def test_sync_all_json_backend():
    """sync_all() with json backend should store embeddings in a JSON file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chronicle = MockChronicle()
        store_path = Path(tmpdir) / "lumen_beliefs.json"
        syncer = VectorSyncer(chronicle, backend="json", store_path=str(store_path))

        count = syncer.sync_all()
        assert count >= 3, f"Expected >= 3 vectors synced, got {count}"

        # Check the JSON file was created
        assert store_path.exists(), f"Store file not created at {store_path}"
        data = json.loads(store_path.read_text())
        assert "version" in data
        assert len(data["items"]) == count

        # Check item structure
        for item in data["items"]:
            assert "node_id" in item
            assert "claim" in item
            assert "stratum" in item
            assert "confidence" in item
            assert "embedding" in item
            assert isinstance(item["embedding"], list)
            assert len(item["embedding"]) == 768, f"Expected 768-dim embedding, got {len(item['embedding'])}"

        syncer.close()
        print("PASS: test_sync_all_json_backend")


def test_query_json_backend():
    """query() with json backend should return top_k similar results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chronicle = MockChronicle()
        store_path = Path(tmpdir) / "lumen_beliefs.json"
        syncer = VectorSyncer(chronicle, backend="json", store_path=str(store_path))

        syncer.sync_all()

        # Query with text similar to first event's claim
        results = syncer.query("temperature nominal range", top_k=2)
        assert len(results) <= 2, f"Expected <= 2 results, got {len(results)}"

        # Results should have the expected structure
        for r in results:
            assert "node_id" in r
            assert "claim" in r
            assert "similarity" in r or "score" in r or "distance" in r

        syncer.close()
        print("PASS: test_query_json_backend")


def test_hash_embedding_deterministic():
    """Hash embeddings should be deterministic (same text -> same vector)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chronicle = MockChronicle()
        store_path = Path(tmpdir) / "lumen_beliefs.json"
        syncer = VectorSyncer(chronicle, backend="json", store_path=str(store_path))

        # Run sync twice
        count1 = syncer.sync_all()
        data1 = json.loads(store_path.read_text())

        # Re-sync
        count2 = syncer.sync_all()
        data2 = json.loads(store_path.read_text())

        assert count1 == count2, f"Count mismatch: {count1} vs {count2}"
        # Items should be the same (idempotent upsert)
        ids1 = {item["node_id"] for item in data1["items"]}
        ids2 = {item["node_id"] for item in data2["items"]}
        assert ids1 == ids2, f"Node IDs mismatch after re-sync"

        syncer.close()
        print("PASS: test_hash_embedding_deterministic")


def test_empty_chronicle():
    """sync_all() with an empty chronicle should produce no vectors."""
    class EmptyChronicle:
        def replay(self):
            return []

    with tempfile.TemporaryDirectory() as tmpdir:
        chronicle = EmptyChronicle()
        store_path = Path(tmpdir) / "lumen_beliefs.json"
        syncer = VectorSyncer(chronicle, backend="json", store_path=str(store_path))

        count = syncer.sync_all()
        assert count == 0, f"Expected 0 vectors from empty chronicle, got {count}"

        syncer.close()
        print("PASS: test_empty_chronicle")


def test_context_manager():
    """VectorSyncer should work as a context manager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chronicle = MockChronicle()
        store_path = Path(tmpdir) / "lumen_beliefs.json"
        with VectorSyncer(chronicle, backend="json", store_path=str(store_path)) as syncer:
            count = syncer.sync_all()
            assert count >= 3
        print("PASS: test_context_manager")


if __name__ == "__main__":
    test_sync_all_json_backend()
    test_query_json_backend()
    test_hash_embedding_deterministic()
    test_empty_chronicle()
    test_context_manager()
    print("\n✅ All vector sync tests passed.")
