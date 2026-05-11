"""
lumen.materialize — Knowledge materialization pipeline.

Projects sovereign truth from the Chronicle into:
- Obsidian vault notes (markdown + MOC)
- CDC outbox for external consumers
- Vector store for semantic search
"""
from .obsidian import ObsidianProjector
from .cdc import CDCOutbox
from .vector_sync import VectorSyncer

__all__ = ["ObsidianProjector", "CDCOutbox", "VectorSyncer"]
__version__ = "1.0.0"
