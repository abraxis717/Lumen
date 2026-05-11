#!/usr/bin/env python3
"""
lumen_pcms_core.py — Probabilistic Concept Memory System (PCMS)

Provides:
  - IdentityClustering: entity identity resolution via KMeans on embeddings
  - BetaBelief: Beta-distribution belief tracking for entity relations
  - EntropyMonitor: Shannon entropy tracking with drift detection
  - EvidenceStorage: SQLite-backed evidence storage with hash chaining
  - RiskEngine: PCMS-driven risk scoring using Beta-belief relations

Designed as the semantic engine behind lumen_pcms_service.py.
All math uses numpy / scipy; no transformers or sentence_transformers required.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from scipy import stats
from scipy.spatial.distance import cosine


# ======================================================================
# Constants
# ======================================================================

# Embedding dimension (simple word2vec-style, deterministic)
EMBED_DIM = 64

# Risk thresholds
RISK_ALLOW = 0.3
RISK_THROTTLE = 0.6
RISK_BLOCK = 0.8
# HARD_FAIL = >= RISK_BLOCK

# Beta distribution priors
BETA_ALPHA_INIT = 1.0
BETA_BETA_INIT = 1.0

# Entropy drift threshold (relative change)
ENTROPY_DRIFT_THRESHOLD = 0.15

# Known risky relation types and their risk weights
RISKY_RELATIONS: Dict[str, float] = {
    "manipulation": 0.9,
    "coercion": 0.85,
    "exploitation": 0.9,
    "deception": 0.8,
    "unauthorized_access": 0.85,
    "bypass": 0.75,
    "evasion": 0.7,
    "infiltration": 0.8,
    "weaponization": 1.0,
    "sabotage": 0.95,
}


# ======================================================================
# Data Structures
# ======================================================================

class Decision(str, Enum):
    ALLOW = "ALLOW"
    THROTTLE = "THROTTLE"
    BLOCK = "BLOCK"
    HARD_FAIL = "HARD_FAIL"


@dataclass
class Entity:
    """A concept/entity tracked by PCMS."""
    entity_id: str
    text: str
    embedding: List[float]
    cluster_id: int = -1
    first_seen: str = ""
    last_seen: str = ""
    occurrence_count: int = 0

    def __post_init__(self):
        if not self.first_seen:
            self.first_seen = _utc_iso()
        if not self.last_seen:
            self.last_seen = _utc_iso()
        self.embedding = list(self.embedding)


@dataclass
class Relation:
    """A belief relation between two entities."""
    source_id: str
    target_id: str
    relation_type: str
    # Beta distribution parameters for belief strength
    alpha: float = BETA_ALPHA_INIT
    beta: float = BETA_BETA_INIT
    # Confidence: how many observations
    confidence: float = 1.0
    first_seen: str = ""
    last_seen: str = ""

    def __post_init__(self):
        if not self.first_seen:
            self.first_seen = _utc_iso()
        if not self.last_seen:
            self.last_seen = _utc_iso()

    @property
    def mean(self) -> float:
        """Beta distribution mean (belief strength)."""
        if self.alpha + self.beta == 0:
            return 0.5
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        """Beta distribution variance."""
        total = self.alpha + self.beta
        if total <= 1:
            return 0.25
        return (self.alpha * self.beta) / (total ** 2 * (total + 1))


@dataclass
class Evidence:
    """A single piece of evidence (text snippet)."""
    evidence_id: str
    source_entity: str
    text: str
    timestamp: str = ""
    hash_chain: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _utc_iso()


@dataclass
class EntropySnapshot:
    """Snapshot of system entropy at a point in time."""
    timestamp: str
    entropy_h: float
    cluster_count: int
    entity_count: int
    is_drift: bool = False
    drift_reason: str = ""


# ======================================================================
# Utilities
# ======================================================================

def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()
    ).hexdigest()


def _simple_tokenize(text: str) -> List[str]:
    """Simple tokenizer: lowercase, split on whitespace + punctuation."""
    import re
    return re.findall(r'[a-zA-Z]{3,}', text.lower())


def _deterministic_embedding(text: str, dim: int = EMBED_DIM) -> List[float]:
    """
    Generate a deterministic embedding for text using hash-based bag-of-words.
    
    This is a lightweight alternative to sentence-transformers.
    Each token's hash is mapped to a sparse embedding vector.
    """
    tokens = _simple_tokenize(text)
    if not tokens:
        return [0.0] * dim
    
    vec = np.zeros(dim, dtype=np.float64)
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest()[:8], 16)
        idx = h % dim
        # Use the hash value as a weighted contribution
        weight = 1.0 / max(1, len(tokens))
        vec[idx] += weight
    
    # Normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    
    return vec.tolist()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _kmeans(data: np.ndarray, n_clusters: int, seed: int = 42,
            max_iter: int = 100, tol: float = 1e-4) -> np.ndarray:
    """
    Simple KMeans clustering implementation using Lloyd's algorithm.
    
    Args:
        data: numpy array of shape (n_samples, n_features)
        n_clusters: number of clusters
        seed: random seed for reproducibility
        max_iter: maximum iterations
        tol: convergence tolerance
    
    Returns:
        numpy array of cluster centers shape (n_clusters, n_features)
    """
    rng = np.random.RandomState(seed)
    n_samples, n_features = data.shape
    n_clusters = min(n_clusters, n_samples)
    
    # Initialize centroids by picking random data points
    indices = rng.choice(n_samples, n_clusters, replace=False)
    centroids = data[indices].copy()
    
    for _ in range(max_iter):
        # Assign each point to nearest centroid
        labels = np.zeros(n_samples, dtype=int)
        for i in range(n_samples):
            dists = np.sum((data[i] - centroids) ** 2, axis=1)
            labels[i] = np.argmin(dists)
        
        # Update centroids
        new_centroids = np.zeros_like(centroids)
        for k in range(n_clusters):
            members = data[labels == k]
            if len(members) > 0:
                new_centroids[k] = members.mean(axis=0)
            else:
                new_centroids[k] = centroids[k]
        
        # Check convergence
        shift = np.linalg.norm(new_centroids - centroids)
        centroids = new_centroids
        if shift < tol:
            break
    
    return centroids


# ======================================================================
# IdentityClustering
# ======================================================================

class IdentityClustering:
    """
    Clusters entities by semantic similarity using KMeans on embeddings.
    
    Implements identity resolution: entities with similar embeddings
    are grouped under the same identity cluster.
    """

    def __init__(self, max_clusters: int = 16, seed: int = 42):
        self.max_clusters = max_clusters
        self._seed = seed
        self._cluster_centers: Optional[np.ndarray] = None
        self._cluster_counts: Dict[int, int] = defaultdict(int)
        self._entity_to_cluster: Dict[str, int] = {}
        self._cluster_representatives: Dict[int, str] = {}
        self._embeddings: Dict[str, List[float]] = {}

    def add_entity(self, entity: Entity) -> int:
        """
        Add an entity and assign it to a cluster.
        
        If enough entities exist, run KMeans to recluster.
        Otherwise, assign to nearest existing cluster or create new one.
        """
        self._embeddings[entity.entity_id] = entity.embedding
        entity.embedding = entity.embedding
        entity.last_seen = _utc_iso()
        entity.occurrence_count += 1

        if self._cluster_centers is not None:
            # Assign to nearest existing cluster
            cluster_id = self._nearest_cluster(entity.embedding)
        else:
            # First entity creates cluster 0
            cluster_id = 0

        entity.cluster_id = cluster_id
        self._entity_to_cluster[entity.entity_id] = cluster_id
        self._cluster_counts[cluster_id] += 1

        if entity.entity_id not in self._cluster_representatives:
            self._cluster_representatives[cluster_id] = entity.text

        return cluster_id

    def cluster(self) -> int:
        """
        Run KMeans on current embeddings.
        
        Returns the number of clusters formed.
        """
        if len(self._embeddings) < 2:
            self._cluster_centers = None
            return max(1, len(self._embeddings))

        ids = list(self._embeddings.keys())
        matrices = np.array([self._embeddings[i] for i in ids], dtype=np.float64)
        n = min(self.max_clusters, len(ids))
        n = max(2, n)

        # KMeans (simple Lloyd's algorithm)
        self._cluster_centers = _kmeans(matrices, n, seed=self._seed)

        # Reassign
        for i, eid in enumerate(ids):
            cid = self._nearest_cluster_id(i, matrices)
            self._entity_to_cluster[eid] = cid
            self._cluster_counts[cid] += 1
            if eid not in self._cluster_representatives:
                self._cluster_representatives[cid] = eid

        return self._cluster_centers.shape[0]

    def _nearest_cluster(self, embedding: List[float]) -> int:
        """Find nearest cluster center for a new embedding."""
        if self._cluster_centers is None:
            return 0

        vec = np.array(embedding, dtype=np.float64)
        best_id = 0
        best_sim = -1.0
        for cid, center in enumerate(self._cluster_centers):
            sim = _cosine_similarity(vec, center)
            if sim > best_sim:
                best_sim = sim
                best_id = cid
        return best_id

    def _nearest_cluster_id(self, idx: int, matrices: np.ndarray) -> int:
        """Find nearest cluster for an indexed matrix row."""
        if self._cluster_centers is None:
            return 0
        vec = matrices[idx]
        best_id = 0
        best_sim = -1.0
        for cid, center in enumerate(self._cluster_centers):
            sim = _cosine_similarity(vec, center)
            if sim > best_sim:
                best_sim = sim
                best_id = cid
        return best_id

    def get_cluster_id(self, entity_id: str) -> int:
        return self._entity_to_cluster.get(entity_id, -1)

    def get_cluster_members(self, cluster_id: int) -> List[str]:
        return [eid for eid, cid in self._entity_to_cluster.items()
                if cid == cluster_id]

    def get_cluster_count(self) -> int:
        if self._cluster_centers is not None:
            return self._cluster_centers.shape[0]
        return max(1, len(self._embeddings))

    def get_representatives(self) -> Dict[int, str]:
        return dict(self._cluster_representatives)

    def get_entity_count(self) -> int:
        return len(self._embeddings)

    def similarity(self, entity_id_a: str, entity_id_b: str) -> float:
        a = np.array(self._embeddings.get(entity_id_a, [0.0] * EMBED_DIM))
        b = np.array(self._embeddings.get(entity_id_b, [0.0] * EMBED_DIM))
        return _cosine_similarity(a, b)


# ======================================================================
# BetaBelief Engine
# ======================================================================

class BetaBelief:
    """
    Tracks belief strength for relations using Beta distributions.
    
    Each observation updates the (alpha, beta) parameters.
    Higher alpha = positive evidence, higher beta = negative evidence.
    """

    def __init__(self, relation: Relation):
        self.relation = relation

    def observe(self, is_positive: bool = True):
        """Update belief parameters based on observation."""
        if is_positive:
            self.relation.alpha += 1.0
        else:
            self.relation.beta += 1.0
        self.relation.confidence += 1.0
        self.relation.last_seen = _utc_iso()

    @property
    def belief_strength(self) -> float:
        return self.relation.mean

    @property
    def uncertainty(self) -> float:
        return self.relation.variance

    def risk_score(self) -> float:
        """
        Compute risk score for this relation.
        
        Uses the Beta distribution's mean as belief strength,
        weighted by the relation type's risk coefficient.
        """
        risky_weight = RISKY_RELATIONS.get(self.relation.relation_type, 0.1)
        # Risk = belief_strength * risk_coefficient
        return float(self.relation.mean * risky_weight)


# ======================================================================
# EntropyMonitor
# ======================================================================

class EntropyMonitor:
    """
    Tracks Shannon entropy over time for drift detection.
    
    Entropy measures the uncertainty/dispersal of the concept distribution.
    A bounded entropy curve indicates stable concept understanding.
    """

    def __init__(self):
        self._snapshots: List[EntropySnapshot] = []
        self._last_entropy: float = 0.0
        self._last_drift: str = ""

    def compute_entropy(self, cluster_counts: Dict[int, int]) -> float:
        """
        Compute Shannon entropy from cluster count distribution.
        
        H = -sum(p_i * log(p_i))
        """
        total = sum(cluster_counts.values())
        if total == 0:
            return 0.0
        entropy = 0.0
        for count in cluster_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log(p + 1e-10)
        return float(entropy)

    def record(self, cluster_counts: Dict[int, int],
               entity_count: int) -> EntropySnapshot:
        """Record an entropy snapshot and check for drift."""
        h = self.compute_entropy(cluster_counts)
        is_drift = False
        drift_reason = ""

        if self._last_entropy > 0:
            rel_change = abs(h - self._last_entropy) / (self._last_entropy + 1e-10)
            if rel_change > ENTROPY_DRIFT_THRESHOLD:
                is_drift = True
                drift_reason = (
                    f"Entropy change {rel_change:.3f} exceeds threshold "
                    f"{ENTROPY_DRIFT_THRESHOLD}"
                )
                self._last_drift = _utc_iso()

        self._last_entropy = h
        snapshot = EntropySnapshot(
            timestamp=_utc_iso(),
            entropy_h=round(h, 6),
            cluster_count=len(cluster_counts),
            entity_count=entity_count,
            is_drift=is_drift,
            drift_reason=drift_reason,
        )
        self._snapshots.append(snapshot)
        return snapshot

    @property
    def current_entropy(self) -> float:
        return self._last_entropy

    @property
    def last_drift(self) -> str:
        return self._last_drift

    def get_snapshots(self) -> List[Dict[str, Any]]:
        return [asdict(s) for s in self._snapshots]

    def is_bounded(self, max_entropy: Optional[float] = None) -> bool:
        """Check if entropy has remained bounded."""
        if not self._snapshots:
            return True
        if max_entropy is None:
            max_entropy = 5.0  # Reasonable upper bound
        return all(s.entropy_h <= max_entropy for s in self._snapshots)


# ======================================================================
# EvidenceStorage
# ======================================================================

class EvidenceStorage:
    """
    SQLite-backed evidence storage with hash chaining.
    
    Each evidence entry includes a hash that chains to the previous entry,
    making the log tamper-evident.
    """

    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence_log (
                    evidence_id TEXT PRIMARY KEY,
                    source_entity TEXT,
                    text TEXT,
                    timestamp_utc TEXT,
                    hash_chain TEXT,
                    prev_hash TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    run_id TEXT PRIMARY KEY,
                    timestamp_utc TEXT,
                    inputs TEXT,
                    entities TEXT,
                    relations TEXT,
                    risk_score REAL,
                    decision TEXT,
                    pcms_snapshot TEXT,
                    hash_chain TEXT
                )
            """)
            self._conn.commit()
        return self._conn

    def store_evidence(self, evidence: Evidence, prev_hash: str = "") -> str:
        """Store evidence with hash chain."""
        evidence.hash_chain = _sha256({
            "evidence_id": evidence.evidence_id,
            "source_entity": evidence.source_entity,
            "text": evidence.text,
            "prev_hash": prev_hash,
            "timestamp": evidence.timestamp,
        })
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO evidence_log VALUES (?, ?, ?, ?, ?, ?)",
            (evidence.evidence_id, evidence.source_entity, evidence.text,
             evidence.timestamp, evidence.hash_chain, prev_hash),
        )
        conn.commit()
        return evidence.hash_chain

    def store_audit(self, run_id: str, inputs: Any, entities: Any,
                    relations: Any, risk_score: float, decision: str,
                    pcms_snapshot: Any, prev_hash: str = "") -> str:
        """Store audit entry with hash chain."""
        hash_chain = _sha256({
            "run_id": run_id,
            "inputs": str(inputs),
            "entities": str(entities),
            "relations": str(relations),
            "risk_score": risk_score,
            "decision": decision,
            "prev_hash": prev_hash,
            "timestamp": _utc_iso(),
        })
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO audit_log VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)",
            (run_id, json.dumps(inputs), json.dumps(entities),
             json.dumps(relations), risk_score, decision,
             json.dumps(pcms_snapshot), hash_chain),
        )
        conn.commit()
        return hash_chain

    def get_audit(self, run_id: Optional[str] = None,
                  limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve audit entries."""
        conn = self._get_conn()
        if run_id:
            cursor = conn.execute(
                "SELECT * FROM audit_log WHERE run_id = ? ORDER BY timestamp_utc DESC LIMIT ?",
                (run_id, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp_utc DESC LIMIT ?",
                (limit,),
            )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_last_audit_hash(self) -> str:
        """Get the hash of the most recent audit entry."""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT hash_chain FROM audit_log ORDER BY rowid DESC LIMIT 1"
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] else ""


# ======================================================================
# RiskEngine
# ======================================================================

class RiskEngine:
    """
    PCMS-driven risk scoring engine.
    
    Risk = sum of (BetaMean * confidence) for all risky relations,
    normalized to [0, 1].
    """

    def __init__(self, relations: Optional[Dict[str, BetaBelief]] = None):
        self._relations = relations or {}

    def add_relation(self, relation: Relation):
        if relation.relation_type not in self._relations:
            self._relations[relation.relation_type] = BetaBelief(relation)

    def compute_risk(self) -> float:
        """
        Compute total risk score.
        
        R = sum of (BetaMean * confidence) for risky relations,
        normalized by dividing by max possible risk.
        """
        total = 0.0
        max_possible = 0.0
        for rel_type, belief in self._relations.items():
            weight = RISKY_RELATIONS.get(rel_type, 0.1)
            total += belief.relation.mean * belief.relation.confidence * weight
            # Max possible if alpha was huge and beta was 0 (mean=1.0, conf=1.0)
            max_possible += 1.0 * 1.0 * weight

        if max_possible == 0:
            return 0.0
        return min(1.0, total / max_possible)

    def get_decision(self, risk_score: float) -> Decision:
        """Convert risk score to decision."""
        if risk_score >= RISK_BLOCK:
            return Decision.HARD_FAIL
        if risk_score >= RISK_THROTTLE:
            return Decision.BLOCK
        if risk_score >= RISK_ALLOW:
            return Decision.THROTTLE
        return Decision.ALLOW

    def decide(self, risk_score: float) -> str:
        """Convert a risk score to a string decision."""
        decision = self.get_decision(risk_score)
        return decision.name

    def get_state(self) -> Dict[str, Any]:
        return {
            "relations": {
                k: {
                    "alpha": v.relation.alpha,
                    "beta": v.relation.beta,
                    "mean": v.relation.mean,
                    "confidence": v.relation.confidence,
                }
                for k, v in self._relations.items()
            },
            "risk_score": self.compute_risk(),
        }


# ======================================================================
# Main PCMS Engine
# ======================================================================

class PCMS:
    """
    Probabilistic Concept Memory System.
    
    Orchestrates identity clustering, Beta-belief tracking,
    entropy monitoring, and evidence storage.
    """

    def __init__(self, max_clusters: int = 16, db_path: str = ":memory:"):
        self.clustering = IdentityClustering(max_clusters=max_clusters)
        self.beta_engine = BetaBelief.__dict__  # placeholder — actual relations stored in RiskEngine
        self.risk_engine = RiskEngine()
        self.entropy_monitor = EntropyMonitor()
        self.evidence_storage = EvidenceStorage(db_path=db_path)
        self._relations: Dict[Tuple[str, str, str], Relation] = {}

    def add_entities(self, entities: List[Entity]) -> List[int]:
        """Add entities and return their cluster IDs."""
        return [self.clustering.add_entity(e) for e in entities]

    def add_relation(self, source: str, target: str, relation_type: str,
                     is_positive: bool = True) -> Relation:
        """Add or update a relation between entities."""
        key = (source, target, relation_type)
        if key not in self._relations:
            rel = Relation(
                source_id=source,
                target_id=target,
                relation_type=relation_type,
                alpha=BETA_ALPHA_INIT,
                beta=BETA_BETA_INIT,
            )
            self._relations[key] = rel
            self.risk_engine.add_relation(rel)

        belief = BetaBelief(self._relations[key])
        belief.observe(is_positive)
        return self._relations[key]

    def cluster(self) -> int:
        """Run clustering on current entities."""
        return self.clustering.cluster()

    def record_entropy(self) -> EntropySnapshot:
        """Record current entropy state."""
        counts = dict(self.clustering._cluster_counts)
        return self.entropy_monitor.record(counts, self.clustering.get_entity_count())

    def get_risk_score(self) -> float:
        return self.risk_engine.compute_risk()

    def get_decision(self, risk_score: Optional[float] = None) -> Decision:
        if risk_score is None:
            risk_score = self.get_risk_score()
        return self.risk_engine.get_decision(risk_score)

    def get_state(self) -> Dict[str, Any]:
        """Get full PCMS state for health check and snapshots."""
        return {
            "cluster_count": self.clustering.get_cluster_count(),
            "entity_count": self.clustering.get_entity_count(),
            "entropy": self.entropy_monitor.current_entropy,
            "last_drift": self.entropy_monitor.last_drift,
            "risk_score": self.get_risk_score(),
            "relation_count": len(self._relations),
        }


# ======================================================================
# LLM Entity Extraction Helper
# ======================================================================

def extract_entities_with_llm(
    text: str,
    llm_url: str = "http://localhost:8080/v1/chat/completions",
    model: str = "qwen3.6-moe",
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Use the local LLM server to extract entities and relations from text.
    
    Args:
        text: Input text to analyze.
        llm_url: LLM API endpoint.
        model: Model name.
        timeout: Request timeout in seconds.
    
    Returns:
        Dict with keys: entities (list of str), relations (list of dict), text (str)
    """
    try:
        import importlib.util
        spec = importlib.util.find_spec("requests")
        if spec:
            import requests as req
            response = req.post(
                llm_url,
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a safety analysis assistant. "
                                "Extract entities and their relations from the given text. "
                                "For each entity, identify its type and any relations to other entities. "
                                "Focus on potentially risky relations: manipulation, coercion, exploitation, "
                                "deception, unauthorized access, bypass, evasion, infiltration, weaponization, sabotage. "
                                "Return JSON with keys: entities (list of {id, text, type}), "
                                "relations (list of {source_id, target_id, type, confidence}). "
                                "Use numeric IDs for entities (e1, e2, etc.). "
                                "If no risky relations found, return empty relations list."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.0,
                },
                timeout=timeout,
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "[]")
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Try to extract JSON from markdown code blocks
                    import re
                    match = re.search(r'\{.*\}', content, re.DOTALL)
                    if match:
                        return json.loads(match.group())
                    return {"entities": [], "relations": []}
    except Exception as e:
        pass  # Fallback to keyword-based extraction

    # Fallback: simple keyword-based extraction
    entities = []
    relations = []
    risky_kw = list(RISKY_RELATIONS.keys())
    text_lower = text.lower()
    for kw in risky_kw:
        if kw in text_lower:
            entities.append({"id": f"e{len(entities)+1}", "text": kw, "type": "risky_concept"})

    return {"entities": entities, "relations": relations, "text": text}
