"""
ObsidianProjector — renders a Lumen Chronicle as Obsidian-compatible markdown notes.

Maps chronicle action types (belief_created, oracle_governed_claim,
consensus_event, oracle_telemetry, compute_symbolic, optimize, simulate,
safety_assessment, mitigation_claim, bootstrap_test, governance_drift, and
others) to individual markdown notes with YAML frontmatter, wiki-link
citations, and a Map-of-Content (MOC) index.md grouped by stratum.
"""

from __future__ import annotations

import os
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from yaml import dump as yaml_dump, safe_dump as safe_dump


class ObsidianProjector:
    """Project a Lumen Chronicle into a vault of Obsidian markdown notes."""

    # Action types that produce notes
    ACTION_TYPES = (
        "belief_created",
        "oracle_governed_claim",
        "consensus_event",
        "oracle_telemetry",
        "compute_symbolic",
        "optimize",
        "simulate",
        "safety_assessment",
        "mitigation_claim",
        "bootstrap_test",
        "governance_drift",
        "contradiction_detected",
        "safety_check",
        "SYS_LEVEL_TRANSITION",
        "STEWARD_OVERRIDE",
    )

    def __init__(self, chronicle, vault_path: str) -> None:
        self.chronicle = chronicle
        self.vault_path = Path(vault_path).resolve()
        # Ensure vault directory exists
        self.vault_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Helpers: payload extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _get_claim(payload: Dict[str, Any]) -> str:
        """Return a single claim string from the payload."""
        if isinstance(payload.get("claims"), list):
            claims = payload["claims"]
            return "\n".join(str(c) for c in claims) if claims else ""
        if payload.get("claim"):
            return str(payload["claim"])
        if payload.get("observation"):
            return str(payload["observation"])
        if payload.get("text"):
            return str(payload["text"])
        return ""

    @staticmethod
    def _get_timestamp(payload: Dict[str, Any]) -> datetime.datetime:
        """Extract a datetime from the payload; default to current time."""
        ts = payload.get("timestamp")
        if ts is not None:
            try:
                return datetime.datetime.fromtimestamp(float(ts))
            except (TypeError, ValueError, OSError):
                pass
        epoch = payload.get("epoch")
        if epoch is not None:
            try:
                return datetime.datetime.fromtimestamp(float(epoch))
            except (TypeError, ValueError, OSError):
                pass
        return datetime.datetime.now()

    @staticmethod
    def _get_stratum(payload: Dict[str, Any]) -> str:
        return str(payload.get("stratum", "operational"))

    @staticmethod
    def _get_confidence(payload: Dict[str, Any]) -> float:
        conf = payload.get("confidence")
        if conf is not None:
            try:
                return float(conf)
            except (TypeError, ValueError):
                pass
        return 0.5

    @staticmethod
    def _get_agent(payload: Dict[str, Any], event_agent: str = "") -> str:
        """Prefer payload source_agent, then agent from payload, then event_agent, then 'unknown'."""
        if payload.get("source_agent"):
            return str(payload["source_agent"])
        if payload.get("agent"):
            return str(payload["agent"])
        if event_agent:
            return str(event_agent)
        return "unknown"

    @staticmethod
    def _get_citations(payload: Dict[str, Any]) -> List[str]:
        cites = payload.get("citations", [])
        if isinstance(cites, list):
            return [str(c) for c in cites]
        if isinstance(cites, str):
            return [cites]
        return []

    @staticmethod
    def _get_lineage(payload: Dict[str, Any]) -> Dict[str, List[str]]:
        """Return {'supports': [...], 'contradicts': [...]}."""
        supports = payload.get("supports", [])
        contradicts = payload.get("contradicts", [])
        return {
            "supports": [str(n) for n in supports] if isinstance(supports, list) else [],
            "contradicts": [str(n) for n in contradicts] if isinstance(contradicts, list) else [],
        }

    @staticmethod
    def _get_node_id(payload: Dict[str, Any]) -> Optional[str]:
        nid = payload.get("node_id") or payload.get("belief_id")
        return str(nid) if nid else None

    @staticmethod
    def _make_note_id(event_hash: str) -> str:
        """YYYY-MM-DD_event-id (first 16 chars of hash)."""
        ts = datetime.datetime.now()  # fallback
        return f"{ts.strftime('%Y-%m-%d')}_{event_hash[:16]}"

    def _note_filename(self, event) -> str:
        """Build the note filename from the event."""
        ts = self._get_timestamp(event.payload)
        short_hash = event.hash[:16]
        return f"{ts.strftime('%Y-%m-%d')}_{short_hash}.md"

    # ------------------------------------------------------------------
    # Note body generation
    # ------------------------------------------------------------------

    def _render_body(self, event, note_id: str) -> str:
        """Render the markdown body for a note."""
        lines: List[str] = []
        payload = event.payload
        claim = self._get_claim(payload)
        citations = self._get_citations(payload)
        lineage = self._get_lineage(payload)
        node_id = self._get_node_id(payload)

        if claim:
            lines.append(claim)
            lines.append("")  # blank line separator

        if citations:
            lines.append("### Citations")
            for cite in citations:
                lines.append(f"[[{cite}]]")
            lines.append("")

        if lineage["supports"]:
            lines.append("### Supports")
            for nid in lineage["supports"]:
                display = nid or "unknown"
                lines.append(f"[[{nid}|{display}]]")
            lines.append("")

        if lineage["contradicts"]:
            lines.append("### Contradicts")
            for nid in lineage["contradicts"]:
                display = nid or "unknown"
                lines.append(f"[[{nid}|{display}]]")
            lines.append("")

        return "\n".join(lines)

    def _render_frontmatter(self, event) -> str:
        """Render YAML frontmatter block."""
        payload = event.payload
        meta = {
            "event_type": event.action,
            "agent": self._get_agent(payload, event_agent=event.agent),
            "timestamp": self._get_timestamp(payload).isoformat(),
            "stratum": self._get_stratum(payload),
            "confidence": self._get_confidence(payload),
            "hash": event.hash,
        }
        node_id = self._get_node_id(payload)
        if node_id:
            meta["node_id"] = node_id

        return safe_dump(meta, default_flow_style=False, sort_keys=False)

    def _write_note(self, event, content: str) -> Path:
        """Write (or overwrite) a note file. Returns the file path."""
        fname = self._note_filename(event)
        fpath = self.vault_path / fname
        fpath.write_text(content, encoding="utf-8")
        return fpath

    # ------------------------------------------------------------------
    # Core projection
    # ------------------------------------------------------------------

    def _project_events(self, events: List) -> List[Dict[str, Any]]:
        """Project a list of events into note dicts. Returns list of dicts."""
        notes = []
        for event in events:
            if event.action not in self.ACTION_TYPES:
                continue
            # Build unique note id for dedup / idempotency
            ts = self._get_timestamp(event.payload)
            short_hash = event.hash[:16]
            note_id = f"{ts.strftime('%Y-%m-%d')}_{short_hash}"

            frontmatter = self._render_frontmatter(event)
            body = self._render_body(event, note_id)
            content = f"---\n{frontmatter}---\n{body}"

            notes.append({
                "event": event,
                "note_id": note_id,
                "filename": f"{note_id}.md",
                "content": content,
                "stratum": self._get_stratum(event.payload),
                "claim": self._get_claim(event.payload),
                "hash": event.hash,
            })
        return notes

    def project_all(self) -> List[str]:
        """Project every event from the chronicle into the vault.

        Returns a list of written file paths.
        """
        all_events = self.chronicle.replay()
        notes = self._project_events(all_events)

        written = []
        for note in notes:
            fpath = self.vault_path / note["filename"]
            fpath.write_text(note["content"], encoding="utf-8")
            written.append(str(fpath))

        self._write_moc(notes)
        return written

    def project_incremental(self, since_hash: str) -> List[str]:
        """Project only events that occur after the event with *since_hash*.

        Finds the event index by matching hash and slices the replay list.
        Returns a list of written file paths.
        """
        all_events = self.chronicle.replay()

        # Find the index of the since_hash event
        target_index = None
        for i, event in enumerate(all_events):
            if event.hash == since_hash:
                target_index = i
                break

        if target_index is None:
            # Hash not found — treat as no events since
            self._write_moc([])
            return []

        events_after = all_events[target_index + 1 :]
        notes = self._project_events(events_after)

        written = []
        for note in notes:
            fpath = self.vault_path / note["filename"]
            fpath.write_text(note["content"], encoding="utf-8")
            written.append(str(fpath))

        self._write_moc(notes)
        return written

    # ------------------------------------------------------------------
    # MOC (Map of Content)
    # ------------------------------------------------------------------

    def _write_moc(self, notes: List[Dict[str, Any]]) -> None:
        """Write index.md — a Map of Content grouped by stratum."""
        # Group notes by stratum
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for note in notes:
            s = note["stratum"]
            grouped.setdefault(s, []).append(note)

        lines: List[str] = []

        # Frontmatter
        lines.append("---")
        lines.append('title: "Map of Content — Lumen Chronicle"')
        lines.append("---")
        lines.append("")

        if not notes:
            lines.append("# No notes to display.")
            lines.append("")
        else:
            lines.append("# Map of Content — Lumen Chronicle")
            lines.append("")

            for stratum in sorted(grouped.keys()):
                entries = grouped[stratum]
                lines.append(f"## {stratum.title()}")
                lines.append("")
                for note in entries:
                    fname = note["filename"]
                    claim = note["claim"] or note["note_id"]
                    lines.append(f"- [[{fname}|{claim}]]")
                lines.append("")

        moc_path = self.vault_path / "index.md"
        moc_path.write_text("\n".join(lines), encoding="utf-8")
