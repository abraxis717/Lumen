#!/usr/bin/env python3
"""run_pipeline — Main pipeline runner for the Lumen materialize subsystem.

Usage as a module:

    python -m lumen.materialize.run_pipeline \\
        --vault-path /path/to/vault \\
        --sqlite chronicle.db \\
        --vector-backend json \\
        [--model-path /path/to/model.gguf] \\
        [--cdc-path /path/to/cdc.db] \\
        [--incremental since_hash] \\
        [--dry-run] \\
        [--quiet]

Importable as a module::

    from lumen.materialize.run_pipeline import run
    run(args)

Exit codes:
    0  Success
    1  Failure / unexpected error
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Chronicle imports
# ---------------------------------------------------------------------------
from kernel.core.chronicle_jsonl import Chronicle
from kernel.core.chronicle_sqlite import SQLiteChronicle
from kernel.core.event import Event

# ---------------------------------------------------------------------------
# Materialize component imports
# ---------------------------------------------------------------------------
from lumen.materialize.cdc import CDCOutbox
from lumen.materialize.obsidian import ObsidianProjector
from lumen.materialize.vector_sync import VectorSyncer

# ---------------------------------------------------------------------------
# Statistics tracker
# ---------------------------------------------------------------------------

@dataclass
class _Stats:
    """Accumulates pipeline run statistics."""
    events_processed: int = 0
    cdc_events_published: int = 0
    notes_written: int = 0
    vectors_synced: int = 0
    cdc_events_unpublished: int = 0
    incremental_since_hash: Optional[str] = None

    def summary_lines(self) -> List[str]:
        lines = [
            f"Events processed: {self.events_processed}",
        ]
        if self.cdc_events_published > 0:
            lines.append(f"CDC events published: {self.cdc_events_published}")
        if self.cdc_events_unpublished > 0:
            lines.append(f"CDC events unpublished: {self.cdc_events_unpublished}")
        if self.notes_written > 0:
            lines.append(f"Notes written: {self.notes_written}")
        if self.vectors_synced > 0:
            lines.append(f"Vectors synced: {self.vectors_synced}")
        if self.incremental_since_hash:
            lines.append(f"Incremental (since hash): {self.incremental_since_hash[:16]}...")
        return lines


# ---------------------------------------------------------------------------
# Chronicle loader
# ---------------------------------------------------------------------------

def _load_chronicle(
    sqlite_path: Optional[str] = None,
    jsonl_path: Optional[str] = None,
) -> Chronicle:
    """Load a Chronicle from the provided source.

    Args:
        sqlite_path: Path to an SQLite chronicle database.
        jsonl_path:  Path to a JSONL chronicle file.

    Returns:
        A Chronicle instance.

    Raises:
        ValueError: If neither or both paths are provided, or the source is
                    missing or unreadable.
    """
    if sqlite_path and jsonl_path:
        raise ValueError(
            "Cannot specify both --sqlite and --json-chronicle. "
            "Choose one source."
        )
    if not sqlite_path and not jsonl_path:
        raise ValueError(
            "Must specify either --sqlite or --json-chronicle."
        )

    # JSONL path
    if jsonl_path:
        p = Path(jsonl_path)
        if not p.exists():
            raise FileNotFoundError(f"JSONL chronicle not found: {p}")
        return Chronicle.load_from_jsonl(str(p))

    # SQLite path
    p = Path(sqlite_path)
    if not p.exists():
        raise FileNotFoundError(f"SQLite chronicle not found: {p}")
    return SQLiteChronicle(sqlite_path)


# ---------------------------------------------------------------------------
# Pipeline step implementations
# ---------------------------------------------------------------------------

def _run_cdc(
    chronicle: Chronicle,
    cdc_path: str,
    stats: _Stats,
    dry_run: bool,
    quiet: bool,
) -> None:
    """Replay all events from the chronicle into the CDC outbox."""
    outbox = CDCOutbox(cdc_path)
    try:
        new_count = 0
        dup_count = 0
        for event in chronicle.replay():
            if outbox.publish(event):
                new_count += 1
            else:
                dup_count += 1
        stats.cdc_events_published = new_count
        stats.cdc_events_unpublished = dup_count
    finally:
        outbox.close()

    if not quiet:
        if dry_run:
            print(f"  [dry-run] CDC outbox: would publish {new_count} events "
                  f"({dup_count} duplicates)")
        else:
            print(f"  CDC outbox: published {new_count} events "
                  f"({dup_count} duplicates)")


def _run_obsidian(
    chronicle: Chronicle,
    vault_path: str,
    incremental: Optional[str],
    stats: _Stats,
    dry_run: bool,
    quiet: bool,
) -> None:
    """Project chronicle events into an Obsidian vault."""
    projector = ObsidianProjector(chronicle, vault_path)

    if incremental:
        stats.incremental_since_hash = incremental
        written = projector.project_incremental(since_hash=incremental)
    else:
        written = projector.project_all()

    stats.notes_written = len(written)

    if not quiet:
        if dry_run:
            print(f"  [dry-run] Obsidian vault: would write {len(written)} notes")
        else:
            print(f"  Obsidian vault: wrote {len(written)} notes")


def _run_vectors(
    chronicle: Chronicle,
    backend: str,
    model_path: Optional[str],
    stats: _Stats,
    dry_run: bool,
    quiet: bool,
) -> None:
    """Sync belief-producing events into a vector store."""
    if dry_run:
        # We still need to build the syncer to know the event count,
        # but we don't actually write.  Unfortunately VectorSyncer
        # writes during __init__ for some backends (e.g. Qdrant
        # collection creation).  We proceed anyway and let the
        # underlying library handle idempotent operations.
        syncer = VectorSyncer(chronicle, model_path=model_path, backend=backend)
        count = syncer.sync_all()
        stats.vectors_synced = count
        if not quiet:
            print(f"  [dry-run] Vector sync ({backend}): would sync {count} vectors")
        return

    syncer = VectorSyncer(chronicle, model_path=model_path, backend=backend)
    count = syncer.sync_all()
    stats.vectors_synced = count

    if not quiet:
        print(f"  Vector sync ({backend}): synced {count} vectors")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(args: Optional[argparse.Namespace] = None) -> None:
    """Execute the full materialize pipeline.

    Args:
        args: A pre-parsed ``argparse.Namespace``.  If *None*, the CLI
              argument parser is invoked and ``sys.exit`` is called on
              error (exit 1) or after a successful run (exit 0).
    """
    if args is None:
        parser = _build_parser()
        args = parser.parse_args()
        # If no sub-actions are enabled, nothing to do.
        if not any([
            args.vault_path,
            args.cdc_path,
            args.vector_backend,
        ]):
            print("Nothing to do. "
                  "Specify --vault-path, --cdc-path, or --vector-backend.",
                  file=sys.stderr)
            sys.exit(1)

    quiet = args.quiet
    dry_run = args.dry_run

    # Resolve defaults
    sqlite_path = args.sqlite  # None unless --sqlite is explicitly provided
    jsonl_path = args.json_chronicle

    if not quiet:
        print("Lumen materialize pipeline", file=sys.stderr)
        if dry_run:
            print("  *** DRY RUN — no files will be written ***",
                  file=sys.stderr)

    # 1. Load chronicle
    try:
        chronicle = _load_chronicle(sqlite_path=sqlite_path, jsonl_path=jsonl_path)
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error loading chronicle: {exc}", file=sys.stderr)
        sys.exit(1)

    total_events = len(chronicle.replay())
    stats = _Stats(events_processed=total_events)

    if not quiet:
        print(f"  Chronical loaded: {total_events} events",
              file=sys.stderr)

    # 2. CDC outbox
    if args.cdc_path:
        if not quiet:
            print("  Processing CDC outbox...", file=sys.stderr)
        try:
            _run_cdc(
                chronicle=chronicle,
                cdc_path=args.cdc_path,
                stats=stats,
                dry_run=dry_run,
                quiet=quiet,
            )
        except Exception as exc:
            print(f"Error processing CDC outbox: {exc}", file=sys.stderr)
            sys.exit(1)

    # 3. Obsidian vault projection
    if args.vault_path:
        if not quiet:
            print("  Processing Obsidian vault...", file=sys.stderr)
        try:
            _run_obsidian(
                chronicle=chronicle,
                vault_path=args.vault_path,
                incremental=args.incremental,
                stats=stats,
                dry_run=dry_run,
                quiet=quiet,
            )
        except Exception as exc:
            print(f"Error projecting to Obsidian vault: {exc}", file=sys.stderr)
            sys.exit(1)

    # 4. Vector sync
    if args.vector_backend:
        if not quiet:
            print(f"  Processing vector sync (backend={args.vector_backend})...", file=sys.stderr)
        try:
            _run_vectors(
                chronicle=chronicle,
                backend=args.vector_backend,
                model_path=args.model_path,
                stats=stats,
                dry_run=dry_run,
                quiet=quiet,
            )
        except Exception as exc:
            print(f"Error syncing vectors: {exc}", file=sys.stderr)
            sys.exit(1)

    # 5. Summary
    print("", file=sys.stderr)
    print("=== Pipeline Summary ===", file=sys.stderr)
    for line in stats.summary_lines():
        print(f"  {line}", file=sys.stderr)
    print("", file=sys.stderr)

    sys.exit(0)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="run_pipeline",
        description="Lumen materialize pipeline runner — projects a Chronicle "
                    "into Obsidian, vector stores, and a CDC outbox.",
    )

    # Chronicle source (mutually exclusive)
    src = parser.add_argument_group("Chronicle source")
    src.add_argument(
        "--sqlite",
        default=None,
        help="Path to the SQLite chronicle database. "
             "Mutually exclusive with --json-chronicle.",
    )
    src.add_argument(
        "--json-chronicle",
        dest="json_chronicle",
        default=None,
        help="Path to a JSONL chronicle file. "
             "Mutually exclusive with --sqlite.",
    )

    # Vault (Obsidian)
    vault = parser.add_argument_group("Obsidian vault (optional)")
    vault.add_argument(
        "--vault-path",
        default=None,
        help="Path to an Obsidian vault. If provided, chronicle events will be "
             "projected into markdown notes under this directory.",
    )

    # Vector sync
    vec = parser.add_argument_group("Vector sync (optional)")
    vec.add_argument(
        "--vector-backend",
        choices=["json", "qdrant", "chroma"],
        default="json",
        help="Vector store backend (default: json).",
    )
    vec.add_argument(
        "--model-path",
        default=None,
        help="Path to a GGUF model file for embedding. "
             "When omitted, a pure-Python character n-gram hash embedding "
             "is used (768-dim).",
    )

    # CDC outbox
    cdc = parser.add_argument_group("CDC outbox (optional)")
    cdc.add_argument(
        "--cdc-path",
        default=None,
        help="Path to a CDC SQLite outbox database. If provided, all events "
             "from the chronicle will be replayed into the outbox.",
    )

    # Incremental mode
    parser.add_argument(
        "--incremental",
        default=None,
        help="Only process events that occur after the event with the given hash. "
             "Applies to the Obsidian projection step.",
    )

    # Flags
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Do not write any files; print what would happen.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress progress output (only print the final summary).",
    )

    return parser


# ---------------------------------------------------------------------------
# CLI entry point (__main__)
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point — parses args and runs the pipeline."""
    run(args=None)


if __name__ == "__main__":
    main()
