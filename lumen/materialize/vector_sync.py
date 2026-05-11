"""
vector_sync.py — Vector-sync adapter for the Lumen Chronicle

Syncs belief-producing chronicle events into a vector store (JSON file,
Qdrant, or Chroma) so that semantic search over beliefs is possible.

Backend selection:
    json     — plain-file fallback, no external deps (default)
    qdrant   — Qdrant high-performance vector database
    chroma   — Chroma embedded vector store

Belief events (filtered by ``sync_all``):
    belief_created, consensus_event, oracle_telemetry
"""

from __future__ import annotations

import hashlib
import json
import math

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Belief-producing action types ───────────────────────────────────────

BELIEF_ACTIONS = frozenset(
    {"belief_created", "consensus_event", "oracle_telemetry"},
)

# ── Hash-embedding constants ────────────────────────────────────────────

HASH_EMBED_DIM = 768
NGRAM_SIZE = 3

# ── Optional imports (backend-specific) ─────────────────────────────────

try:
    import qdrant_client  # type: ignore
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False

try:
    import chromadb  # type: ignore
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


# ── Embedding helpers ───────────────────────────────────────────────────

def _char_ngram_hash_embed(text: str, dim: int = HASH_EMBED_DIM) -> List[float]:
    """Character n-gram hash embedding (no model required).

    Splits *text* into character n-grams, hashes each n-gram, maps the hash
    modulo *dim* to an index, accumulates counts, then L2-normalises to
    unit length.

    Args:
        text: The input string to embed.
        dim:  Embedding dimension (default 768).

    Returns:
        A normalised float vector of length *dim*.
    """
    text = text.lower()
    grams = Counter(_ngrams(text, NGRAM_SIZE))
    counts: Dict[int, int] = {}
    for gram, freq in grams.items():
        idx = _hash_mod(gram, dim)
        counts[idx] = counts.get(idx, 0) + freq

    # L2 normalisation
    norm = math.sqrt(sum(v * v for v in counts.values()))
    if norm == 0.0:
        return [0.0] * dim

    vector = [0.0] * dim
    for idx, val in counts.items():
        vector[idx] = val / norm
    return vector


def _ngrams(text: str, n: int) -> List[str]:
    """Split *text* into character n-grams."""
    return [text[i : i + n] for i in range(max(0, len(text) - n + 1))]


def _hash_mod(s: str, mod: int) -> int:
    """SHA-256 of *s* reduced to ``[0, mod)``."""
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16) % mod


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Dot-product cosine similarity (vectors assumed unit-length)."""
    dot = sum(x * y for x, y in zip(a, b))
    return dot


# ── Embedding factory ──────────────────────────────────────────────────

def _make_embedder(model_path: Optional[str]):
    """Return an embed(text: str) -> List[float] callable.

    If *model_path* is provided the MobileModel (GGUF via llama-cpp-python)
    is used.  Otherwise the pure-Python character n-gram hasher is returned.
    """
    if model_path is not None:
        from kernel.mobile.model_loader import MobileModel

        mobile_model = MobileModel(model_path=model_path)

        def _embed(text: str) -> List[float]:
            return mobile_model.embed(str(text))

        return _embed, mobile_model
    else:
        def _embed(text: str) -> List[float]:
            return _char_ngram_hash_embed(str(text))

        return _embed, None


# ── Chronological event → belief payload ───────────────────────────────

def _extract_belief_payload(event) -> Optional[Dict[str, Any]]:
    """Return the belief payload from *event* or None.

    Extracts claim, stratum, confidence, source_agent, node_id, timestamp
    and the event hash from a Chronicle event whose action is one of the
    belief-producing types.
    """
    payload = event.payload
    if not isinstance(payload, dict):
        return None

    # Extract claim
    claim = _resolve_claim(payload)
    if not claim:
        return None

    # Extract node_id (prefer node_id, then belief_id)
    node_id = payload.get("node_id") or payload.get("belief_id")
    if node_id is None:
        node_id = event.hash  # fallback to event hash

    return {
        "node_id": str(node_id),
        "claim": str(claim),
        "stratum": str(payload.get("stratum", "operational")),
        "confidence": _safe_float(payload.get("confidence"), 0.5),
        "source_agent": str(payload.get("source_agent", payload.get("agent", "unknown"))),
        "timestamp": _safe_timestamp(payload),
        "hash": event.hash,
    }


def _resolve_claim(payload: Dict[str, Any]) -> str:
    """Pull a single claim string from the payload dict."""
    if isinstance(payload.get("claims"), list):
        return "\n".join(str(c) for c in payload["claims"]) if payload["claims"] else ""
    if payload.get("claim"):
        return str(payload["claim"])
    if payload.get("observation"):
        return str(payload["observation"])
    if payload.get("text"):
        return str(payload["text"])
    if payload.get("summary"):
        return str(payload["summary"])
    return ""


def _safe_float(value: Any, default: float = 0.5) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_timestamp(payload: Dict[str, Any]) -> str:
    """Normalise timestamp to an ISO string."""
    for key in ("timestamp", "epoch", "time", "ts"):
        val = payload.get(key)
        if val is not None:
            try:
                return str(float(val))
            except (TypeError, ValueError):
                pass
    return "0"


# ── Backend: JSON ───────────────────────────────────────────────────────

_JSON_SCHEMA_VERSION = 1
_JSON_DEFAULT_FILE = "lumen_belongs.json"


def _json_load(store_path: Path) -> Dict[str, Any]:
    """Load the JSON store, returning a fresh structure if missing."""
    if store_path.exists():
        with open(store_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return _json_empty()
        return data
    return _json_empty()


def _json_empty() -> Dict[str, Any]:
    return {"version": _JSON_SCHEMA_VERSION, "items": []}


def _json_save(data: Dict[str, Any], store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with open(store_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _json_upsert(data: Dict[str, Any], item: Dict[str, Any]) -> None:
    """Upsert *item* by hash key; replace existing entry with same hash."""
    for i, existing in enumerate(data["items"]):
        if existing.get("hash") == item["hash"]:
            data["items"][i] = item
            return
    data["items"].append(item)


def _json_query(
    data: Dict[str, Any],
    query_vec: List[float],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Return top-k most similar items to *query_vec* by cosine similarity."""
    items = data.get("items", [])
    if not items:
        return []

    scored: List[tuple[float, Dict]] = []
    for item in items:
        emb = item.get("embedding")
        if emb is None:
            continue
        score = _cosine_similarity(query_vec, emb)
        scored.append((score, item))

    scored.sort(key=lambda t: t[0], reverse=True)
    # Include the score in each result for consistency with qdrant/chroma backends
    results: List[Dict[str, Any]] = []
    for _score, item in scored[:top_k]:
        result = dict(item)  # copy to avoid mutating stored item
        result["similarity"] = round(_score, 6)
        results.append(result)
    return results


# ── Backend: Qdrant ─────────────────────────────────────────────────────

_QDRANT_COLLECTION = "lumen_beliefs"


def _qdrant_upsert(client, collection: str, items: List[Dict]) -> None:
    """Upsert *items* into the Qdrant collection."""
    points = []
    for item in items:
        points.append(
            qdrant_client.models.PointStruct(
                id=item["node_id"],
                payload={
                    "node_id": item["node_id"],
                    "claim": item["claim"],
                    "stratum": item["stratum"],
                    "confidence": item["confidence"],
                    "source_agent": item["source_agent"],
                    "timestamp": item["timestamp"],
                    "hash": item["hash"],
                },
                vector=item["embedding"],
            )
        )
    client.upsert(collection, points)


def _qdrant_query(client, collection: str, query_vec: List[float], top_k: int = 5):
    """Query the Qdrant collection and return matching results."""
    hits = client.query_points(collection, query=query_vec, limit=top_k)
    results: List[Dict[str, Any]] = []
    for hit in hits.points:
        payload = hit.payload
        results.append({
            "node_id": payload.get("node_id", ""),
            "claim": payload.get("claim", ""),
            "stratum": payload.get("stratum", ""),
            "confidence": payload.get("confidence", 0.0),
            "source_agent": payload.get("source_agent", ""),
            "timestamp": payload.get("timestamp", ""),
            "hash": payload.get("hash", ""),
            "score": hit.score if hasattr(hit, "score") else 0.0,
        })
    return results


# ── Backend: Chroma ─────────────────────────────────────────────────────

_CHROMA_COLLECTION = "lumen_beliefs"


def _chroma_upsert(
    chroma_client,
    collection_name: str,
    items: List[Dict],
    embed_fn,
) -> None:
    """Upsert *items* into a Chroma collection (creates if absent)."""
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        embedding_function=None,
        metadata={"hnsw:space": "cosine"},
    )
    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict] = []
    for item in items:
        ids.append(item["node_id"])
        documents.append(item["claim"])
        metadatas.append({
            "node_id": item["node_id"],
            "claim": item["claim"],
            "stratum": item["stratum"],
            "confidence": str(item["confidence"]),
            "source_agent": item["source_agent"],
            "timestamp": item["timestamp"],
            "hash": item["hash"],
        })
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def _chroma_query(
    chroma_client,
    collection_name: str,
    query_text: str,
    embed_fn,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Query Chroma by embedding *query_text* and returning top-k results."""
    collection = chroma_client.get_collection(name=collection_name)
    query_emb = embed_fn(query_text)
    results = collection.query(
        query_embeddings=[query_emb],
        n_results=top_k,
    )
    out: List[Dict[str, Any]] = []
    for idx in range(len(results.get("ids", [[]])[0])):
        meta = results.get("metadatas", [[]])[0][idx] or {}
        out.append({
            "node_id": meta.get("node_id", ""),
            "claim": meta.get("claim", ""),
            "stratum": meta.get("stratum", ""),
            "confidence": meta.get("confidence", "0.0"),
            "source_agent": meta.get("source_agent", ""),
            "timestamp": meta.get("timestamp", ""),
            "hash": meta.get("hash", ""),
            "score": results.get("distances", [[0.0]])[0][idx],
        })
    return out


# ── VectorSyncer ────────────────────────────────────────────────────────

class VectorSyncer:
    """Sync belief-producing Chronicle events into a vector store.

    Args:
        chronicle:  A Chronicle instance (must provide ``replay()``).
        model_path: Optional path to a GGUF model for MobileModel embeddings.
                    When *None*, a pure-Python character n-gram hash
                    embedding (768-dim, unit-normalised) is used.
        backend:    Storage backend — ``"json"``, ``"qdrant"``, or ``"chroma"``.
        store_path: For ``"json"`` backend, the JSON file path.
                    Defaults to ``{vault_path}/lumen_belongs.json`` or
                    ``{cwd}/lumen_belongs.json``.
        qdrant_url: Qdrant server URL (default ``http://localhost:6333``).
        chroma_persist_dir: Chroma data directory (default ``.chroma_store``).

    Raises:
        ImportError: If ``backend`` is ``"qdrant"`` or ``"chroma"`` but the
                     respective package is not installed.
    """

    def __init__(
        self,
        chronicle,
        model_path: Optional[str] = None,
        backend: str = "json",
        store_path: Optional[str] = None,
        qdrant_url: str = "http://localhost:6333",
        chroma_persist_dir: str = ".chroma_store",
    ) -> None:
        self.chronicle = chronicle
        self.backend = backend.lower()

        # Validate backend
        if self.backend not in ("json", "qdrant", "chroma"):
            raise ValueError(
                f"Unknown backend {self.backend!r}. "
                "Must be 'json', 'qdrant', or 'chroma'."
            )

        # Check optional deps
        if self.backend == "qdrant" and not HAS_QDRANT:
            raise ImportError(
                "qdrant-client is required for backend='qdrant'.\n"
                "Install with: pip install qdrant-client"
            )
        if self.backend == "chroma" and not HAS_CHROMA:
            raise ImportError(
                "chromadb is required for backend='chroma'.\n"
                "Install with: pip install chromadb"
            )

        # Determine store path (JSON backend)
        if store_path is not None:
            self._store_path = Path(store_path)
        else:
            vault_path = getattr(chronicle, "vault_path", None)
            if vault_path is not None:
                self._store_path = Path(vault_path) / _JSON_DEFAULT_FILE
            else:
                self._store_path = Path.cwd() / _JSON_DEFAULT_FILE

        # Qdrant client
        if self.backend == "qdrant":
            import qdrant_client  # type: ignore
            self._qdrant_client = qdrant_client.QdrantClient(url=qdrant_url)
            # Ensure collection exists
            self._qdrant_client.recreate_collection(
                collection_name=_QDRANT_COLLECTION,
                vectors_config=qdrant_client.models.VectorParams(
                    size=HASH_EMBED_DIM,
                    distance=qdrant_client.models.Distance.COSINE,
                ),
            )

        # Chroma client
        if self.backend == "chroma":
            import chromadb  # type: ignore
            self._chroma_client = chromadb.PersistentClient(
                path=chroma_persist_dir,
            )

        # Embedding function
        self._embed_fn, self._mobile_model = _make_embedder(model_path)

    # ── Core API ──────────────────────────────────────────────────────

    def sync_all(self) -> int:
        """Sync all belief events from the chronicle into the vector store.

        Returns:
            The number of items inserted / updated.
        """
        events = self.chronicle.replay()
        belief_events = [e for e in events if e.action in BELIEF_ACTIONS]

        # Extract payloads
        payloads: List[Dict[str, Any]] = []
        for event in belief_events:
            bp = _extract_belief_payload(event)
            if bp is None:
                continue
            # Embed
            embedding = self._embed_fn(bp["claim"])
            bp["embedding"] = embedding
            payloads.append(bp)

        # Upsert into the appropriate backend
        if self.backend == "json":
            self._sync_json(payloads)
        elif self.backend == "qdrant":
            self._sync_qdrant(payloads)
        elif self.backend == "chroma":
            self._sync_chroma(payloads)

        return len(payloads)

    def query(self, text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for the most similar beliefs to *text*.

        Args:
            text:   The query string.
            top_k:  Number of results to return (default 5).

        Returns:
            List of dicts with belief payloads, one per result.
        """
        query_vec = self._embed_fn(text)

        if self.backend == "json":
            return self._query_json(query_vec, top_k)
        elif self.backend == "qdrant":
            return _qdrant_query(self._qdrant_client, _QDRANT_COLLECTION, query_vec, top_k)
        elif self.backend == "chroma":
            return _chroma_query(
                self._chroma_client,
                _CHROMA_COLLECTION,
                text,
                self._embed_fn,
                top_k,
            )
        else:
            raise RuntimeError(f"Unsupported backend: {self.backend}")

    # ── JSON backend ──────────────────────────────────────────────────

    def _sync_json(self, payloads: List[Dict[str, Any]]) -> None:
        data = _json_load(self._store_path)
        for item in payloads:
            _json_upsert(data, item)
        _json_save(data, self._store_path)

    def _query_json(self, query_vec: List[float], top_k: int = 5) -> List[Dict]:
        data = _json_load(self._store_path)
        return _json_query(data, query_vec, top_k)

    # ── Qdrant backend ────────────────────────────────────────────────

    def _sync_qdrant(self, payloads: List[Dict[str, Any]]) -> None:
        if not payloads:
            return
        _qdrant_upsert(self._qdrant_client, _QDRANT_COLLECTION, payloads)

    # ── Chroma backend ────────────────────────────────────────────────

    def _sync_chroma(self, payloads: List[Dict[str, Any]]) -> None:
        if not payloads:
            return
        _chroma_upsert(self._chroma_client, _CHROMA_COLLECTION, payloads, self._embed_fn)

    # ── Lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        """Clean up resources (e.g. MobileModel handle)."""
        if self._mobile_model is not None:
            try:
                delattr(self._mobile_model, "_llm")
            except Exception:
                pass

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> "VectorSyncer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

