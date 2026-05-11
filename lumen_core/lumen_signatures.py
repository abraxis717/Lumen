#!/usr/bin/env python3
"""
lumen_signatures.py — Signature Extraction for Phase 2

Split outputs into shared_core (Mythos bleed) + agent_signature (delta).
Score ONLY on agent_signature for divergence.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from lumen_cycles import (
    deterministic_embedding, cosine_similarity, _simple_tokenize, _utc_iso,
    EMBED_DIM,
)


@dataclass
class Signature:
    """Extracted agent signature: unique delta from shared core."""
    signature_id: str = ""
    agent_signature: str = ""
    shared_core: str = ""
    divergence_score: float = 0.0
    shared_embedding: List[float] = field(default_factory=list)
    agent_embedding: List[float] = field(default_factory=list)
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.signature_id:
            self.signature_id = f"sig_{uuid4hex()}"
        if not self.timestamp:
            self.timestamp = _utc_iso()
        if not self.shared_embedding:
            self.shared_embedding = [0.0] * EMBED_DIM
        if not self.agent_embedding:
            self.agent_embedding = [0.0] * EMBED_DIM
        self.shared_embedding = normalize_embedding(self.shared_embedding)
        self.agent_embedding = normalize_embedding(self.agent_embedding)


def uuid4hex() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


def normalize_embedding(emb: List[float]) -> List[float]:
    if not emb:
        return [0.0] * EMBED_DIM
    norm = np.linalg.norm(emb)
    if norm > 0:
        return (np.array(emb) / norm).tolist()
    return emb


class SignatureExtractor:
    """
    Extract shared_core and agent_signature from multiple outputs.

    shared_core: common semantic content (Mythos bleed across agents)
    agent_signature: unique delta for each agent's perspective
    """

    def __init__(self, mdls_compression_min: float = 1.5):
        self.mdls_compression_min = mdls_compression_min

    def extract_shared_core(self, outputs: List[str]) -> Tuple[str, List[float]]:
        """
        Find common semantic content across outputs.

        Uses embedding space analysis:
        1. Embed all outputs
        2. Find centroid direction (shared signal)
        3. Extract common tokens via agreement threshold
        """
        if not outputs:
            return "", [0.0] * EMBED_DIM

        if len(outputs) == 1:
            return outputs[0], normalize_embedding(
                deterministic_embedding(outputs[0])
            )

        # Embed all outputs
        embeddings = [deterministic_embedding(o) for o in outputs]

        # Compute centroid (shared core direction)
        centroid = np.mean(embeddings, axis=0)
        centroid_norm = np.linalg.norm(centroid)
        if centroid_norm > 0:
            centroid = centroid / centroid_norm

        # Find tokens that appear in majority of outputs
        token_lists = [_simple_tokenize(o) for o in outputs]
        max_len = max(len(tl) for tl in token_lists)
        shared_tokens = set()
        for i, token in enumerate(token_lists[0]):
            if all(i < len(tl) and tl[i] == token for tl in token_lists):
                shared_tokens.add(token)

        # Also find high-agreement tokens (appear in >50% of outputs)
        token_counts: Dict[str, int] = {}
        for tl in token_lists:
            seen = set()
            for t in tl:
                if t not in seen:
                    token_counts[t] = token_counts.get(t, 0) + 1
                    seen.add(t)

        agreement_threshold = len(outputs) * 0.5
        for token, count in token_counts.items():
            if count >= agreement_threshold:
                shared_tokens.add(token)

        # Build shared core from agreement tokens
        if shared_tokens:
            shared_core = " ".join(sorted(shared_tokens))
        else:
            shared_core = outputs[0]  # fallback

        return shared_core, normalize_embedding(centroid.tolist())

    def extract_agent_signature(
        self, output: str, shared_core: str
    ) -> Tuple[str, List[float]]:
        """
        Extract unique delta from an output relative to shared core.

        Returns (signature_text, agent_embedding).
        """
        if not shared_core or not output:
            return output, normalize_embedding(deterministic_embedding(output))

        shared_tokens = set(_simple_tokenize(shared_core))
        output_tokens = _simple_tokenize(output)

        # Token-level delta: tokens in output but not in shared core
        unique_tokens = [t for t in output_tokens if t not in shared_tokens]

        # Deduplicate while preserving order
        seen = set()
        unique_tokens_dedup = []
        for t in unique_tokens:
            if t not in seen:
                unique_tokens_dedup.append(t)
                seen.add(t)

        if not unique_tokens_dedup:
            return output, normalize_embedding(deterministic_embedding(output))

        agent_signature = " ".join(unique_tokens_dedup)

        # Compute agent-specific embedding
        agent_emb = normalize_embedding(deterministic_embedding(agent_signature))

        return agent_signature, agent_emb

    def split_and_score(
        self, outputs: List[str]
    ) -> List[Signature]:
        """
        Split all outputs into shared_core + agent_signatures.
        Score each for divergence.

        Returns list of Signature objects.
        """
        if not outputs:
            return []

        # Extract shared core from all outputs
        shared_core, shared_embedding = self.extract_shared_core(outputs)

        signatures = []
        for i, output in enumerate(outputs):
            sig_text, agent_embedding = self.extract_agent_signature(
                output, shared_core
            )

            sig = Signature(
                agent_signature=sig_text,
                shared_core=shared_core,
                shared_embedding=shared_embedding,
                agent_embedding=agent_embedding,
                metadata={"output_index": i},
            )
            sig.divergence_score = self._compute_divergence(sig, signatures)
            signatures.append(sig)

        return signatures

    def _compute_divergence(self, sig: Signature, others: List[Signature]) -> float:
        """
        Compute divergence score for a signature against others.
        Higher = more unique/distinct.
        """
        if not others:
            return 0.5  # baseline for single signature

        # Average distance to all other signatures
        dists = []
        for other in others:
            if other.signature_id == sig.signature_id:
                continue
            dist = 1.0 - cosine_similarity(
                sig.agent_embedding, other.agent_embedding
            )
            dists.append(dist)

        if not dists:
            return 0.5
        return round(np.mean(dists), 4)

    def score_divergence(self, signatures: List[Signature]) -> Dict[str, Any]:
        """
        MDL-based divergence scoring on agent_signatures ONLY.

        Returns stats on divergence landscape.
        """
        if not signatures:
            return {
                "mean_divergence": 0.0,
                "max_divergence": 0.0,
                "min_divergence": 0.0,
                "std_divergence": 0.0,
                "divergence_spread": 0.0,
                "signatures": [],
            }

        scores = [sig.divergence_score for sig in signatures]
        mean_div = round(np.mean(scores), 4)
        max_div = round(max(scores), 4)
        min_div = round(min(scores), 4)
        std_div = round(float(np.std(scores)), 4)

        return {
            "mean_divergence": mean_div,
            "max_divergence": max_div,
            "min_divergence": min_div,
            "std_divergence": std_div,
            "divergence_spread": round(max_div - min_div, 4),
            "num_signatures": len(signatures),
            "signatures": [
                {
                    "id": sig.signature_id,
                    "divergence_score": sig.divergence_score,
                    "signature_length": len(sig.agent_signature),
                }
                for sig in signatures
            ],
        }

    def compress_signature(self, text: str) -> Tuple[str, float]:
        """
        Lossy compression of signature via MDL criterion.

        Returns (compressed_text, compression_ratio).
        """
        tokens = _simple_tokenize(text)
        if not tokens:
            return "", 0.0

        # Compute frequency of each token
        freq: Dict[str, int] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1

        # Keep high-frequency tokens, replace low-frequency with [GEN]
        threshold = max(1, len(tokens) // 10)  # keep tokens appearing >= 10%
        compressed_tokens = []
        for t in tokens:
            if freq[t] >= threshold:
                compressed_tokens.append(t)
            else:
                compressed_tokens.append("[GEN]")

        compressed = " ".join(compressed_tokens)
        ratio = len(compressed_tokens) / max(len(tokens), 1)
        return compressed, round(ratio, 4)
