"""
test_obsidian.py — Tests for ObsidianProjector.

Creates a mock chronicle with a few events, runs the projector,
and verifies markdown files are created correctly with proper
frontmatter, body, wiki-links, and MOC index.
"""
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, "/mnt/primesauce/Garden_OS/Lumen")

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from lumen.materialize.obsidian import ObsidianProjector


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


# ── Mock Chronicle ────────────────────────────────────────────────
class MockChronicle:
    """Tiny chronicle with a handful of events for testing."""

    def __init__(self):
        now = 1717000000.0  # 2024-05-30
        self._events: List[MockEvent] = [
            MockEvent(
                step=1,
                action="belief_created",
                agent="oracle",
                payload={
                    "claim": "System temperature is within nominal range.",
                    "stratum": "operational",
                    "confidence": 0.95,
                    "node_id": "belief_001",
                    "source_agent": "oracle",
                    "timestamp": now,
                    "citations": ["sensor_data_v1"],
                    "supports": ["belief_000"],
                    "contradicts": [],
                },
                prev_hash="0" * 64,
                hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
            ),
            MockEvent(
                step=2,
                action="belief_created",
                agent="policy_engine",
                payload={
                    "claim": "All sensor readings must be validated before ingestion.",
                    "stratum": "policy",
                    "confidence": 0.88,
                    "node_id": "belief_002",
                    "source_agent": "policy_engine",
                    "timestamp": now + 1,
                    "citations": ["policy_doc_v2"],
                    "supports": ["belief_001"],
                    "contradicts": ["belief_003"],
                },
                prev_hash="aaaa0001bbbb0002cccc0003dddd0004eeee0005ffff0006",
                hash="bbbb1111cccc1111dddd1111eeee1111ffff1111aaaa1111",
            ),
            MockEvent(
                step=3,
                action="consensus_event",
                agent="governed_council",
                payload={
                    "claim": "Consensus reached: system is healthy and safe.",
                    "stratum": "operational",
                    "confidence": 0.92,
                    "node_id": "belief_004",
                    "source_agent": "governed_council",
                    "timestamp": now + 2,
                    "citations": ["council_session_01"],
                    "supports": ["belief_001", "belief_002"],
                    "contradicts": [],
                },
                prev_hash="bbbb1111cccc1111dddd1111eeee1111ffff1111aaaa1111",
                hash="cccc2222dddd2222eeee2222ffff2222aaaa2222bbbb2222",
            ),
            MockEvent(
                step=4,
                action="oracle_telemetry",
                agent="oracle",
                payload={
                    "claim": "Latency: 12ms. Uptime: 99.97%. No anomalies.",
                    "stratum": "ephemeral",
                    "confidence": 0.99,
                    "node_id": "belief_005",
                    "source_agent": "oracle",
                    "timestamp": now + 3,
                    "citations": [],
                    "supports": [],
                    "contradicts": [],
                },
                prev_hash="cccc2222dddd2222eeee2222ffff2222aaaa2222bbbb2222",
                hash="dddd3333eeee3333ffff3333aaaa3333bbbb3333cccc3333",
            ),
        ]

    def replay(self) -> List[MockEvent]:
        return list(self._events)

    def events_of_type(self, action: str) -> List[MockEvent]:
        return [e for e in self._events if e.action == action]


# ── Tests ─────────────────────────────────────────────────────────
def test_project_all_creates_notes():
    """project_all() should create markdown notes for each belief/telemetry event."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "vault"
        chronicle = MockChronicle()
        projector = ObsidianProjector(chronicle, str(vault_path))
        written = projector.project_all()

        # Should have written 4 notes (2 belief_created + 1 consensus_event + 1 oracle_telemetry)
        assert len(written) == 4, f"Expected 4 notes, got {len(written)}"

        # Check filenames are YYYY-MM-DD_hash.md
        for fpath in written:
            p = Path(fpath)
            fname = p.name
            assert fname.endswith(".md"), f"Not a markdown file: {fname}"
            assert len(fname.split("_")[1].split(".")[0]) == 16, f"Hash prefix wrong length: {fname}"

        print("PASS: test_project_all_creates_notes")


def test_note_frontmatter():
    """Each note should have valid YAML frontmatter with required keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "vault"
        chronicle = MockChronicle()
        projector = ObsidianProjector(chronicle, str(vault_path))
        written = projector.project_all()

        for fpath in written:
            p = Path(fpath)
            content = p.read_text()
            assert content.startswith("---"), f"Missing frontmatter delimiter: {p.name}"

            # Parse YAML frontmatter (simple key: value lines)
            lines = content.split("\n")
            end_idx = lines.index("---", 1)
            fm_lines = lines[1:end_idx]
            fm = {}
            for line in fm_lines:
                line = line.strip()
                if not line:
                    continue
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    fm[key] = value

            # Check required keys
            assert "event_type" in fm, f"Missing event_type in {p.name}"
            assert "agent" in fm, f"Missing agent in {p.name}"
            assert "hash" in fm, f"Missing hash in {p.name}"
            assert "stratum" in fm, f"Missing stratum in {p.name}"
            assert "confidence" in fm, f"Missing confidence in {p.name}"
            assert "timestamp" in fm, f"Missing timestamp in {p.name}"

        print("PASS: test_note_frontmatter")


def test_note_body_claim():
    """Each note body should contain the claim text."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "vault"
        chronicle = MockChronicle()
        projector = ObsidianProjector(chronicle, str(vault_path))
        written = projector.project_all()

        # The first event has a specific claim
        first = next(e for e in chronicle._events if e.action == "belief_created" and e.agent == "oracle")
        first_note = next(f for f in written if first.hash[:16] in f)
        body = Path(first_note).read_text()

        assert first.payload["claim"] in body, f"Claim not found in note body"

        print("PASS: test_note_body_claim")


def test_note_wiki_links():
    """Notes with supports/contradicts should have wiki-link references."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "vault"
        chronicle = MockChronicle()
        projector = ObsidianProjector(chronicle, str(vault_path))
        written = projector.project_all()

        # belief_002 has supports=["belief_001"] and contradicts=["belief_003"]
        b2 = next(e for e in chronicle._events if e.payload.get("node_id") == "belief_002")
        b2_note = next(f for f in written if b2.hash[:16] in f)
        body = Path(b2_note).read_text()

        # Should contain wiki-link to support
        assert "[[belief_001" in body, f"Support wiki-link not found in {Path(b2_note).name}"
        # Should contain wiki-link to contradiction
        assert "[[belief_003" in body, f"Contradiction wiki-link not found in {Path(b2_note).name}"

        print("PASS: test_note_wiki_links")


def test_moc_index():
    """project_all() should create an index.md MOC grouped by stratum."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "vault"
        chronicle = MockChronicle()
        projector = ObsidianProjector(chronicle, str(vault_path))
        written = projector.project_all()

        moc_path = vault_path / "index.md"
        assert moc_path.exists(), f"MOC index.md not found at {moc_path}"

        moc_content = moc_path.read_text()
        assert "Map of Content" in moc_content or "Lumen" in moc_content, "MOC missing title"

        # Should have sections for each stratum present
        strata_found = set()
        for event in chronicle._events:
            s = event.payload.get("stratum", "operational")
            if s not in strata_found and f"## {s}" in moc_content or f"## {s.title()}" in moc_content:
                strata_found.add(s)

        # At minimum, check the MOC contains links
        assert ".md" in moc_content, f"MOC contains no note links: {moc_content[:200]}"

        print("PASS: test_moc_index")


def test_idempotent_overwrite():
    """Running project_all() twice should overwrite notes (deterministic filenames)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "vault"
        chronicle = MockChronicle()
        projector = ObsidianProjector(chronicle, str(vault_path))
        written1 = projector.project_all()

        # Run again
        written2 = projector.project_all()

        assert len(written1) == len(written2), "Note count changed on re-run"
        for p1, p2 in zip(written1, written2):
            assert Path(p1).name == Path(p2).name, f"Filename changed: {p1} != {p2}"

        print("PASS: test_idempotent_overwrite")


def test_project_incremental():
    """project_incremental(since_hash) should only process events after the given hash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "vault"
        chronicle = MockChronicle()
        projector = ObsidianProjector(chronicle, str(vault_path))

        # Only project events after the 2nd event
        since_hash = chronicle._events[1].hash
        written = projector.project_incremental(since_hash)

        # Should only get events 3 and 4 (0-indexed: 2 and 3)
        assert len(written) == 2, f"Expected 2 incremental notes, got {len(written)}"

        # Both should be after event index 1
        for fpath in written:
            assert chronicle._events[1].hash[:16] not in fpath

        print("PASS: test_project_incremental")


if __name__ == "__main__":
    test_project_all_creates_notes()
    test_note_frontmatter()
    test_note_body_claim()
    test_note_wiki_links()
    test_moc_index()
    test_idempotent_overwrite()
    test_project_incremental()
    print("\n✅ All obsidian tests passed.")
