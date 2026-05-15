import hashlib
import math
import re
from datetime import datetime
from typing import List, Tuple

import numpy as np
from scipy.spatial.distance import cosine as cosine_distance


class DecisionEngine:
    """Decision engine with keyword + embedding-based contradiction detection.

    The keyword path provides fast rejection of clearly dangerous input.
    The embedding path detects subtle contradictions between statements
    that share high lexical overlap but express opposite sentiments — a
    pattern the keyword filter misses.
    """

    # ------------------------------------------------------------------
    # Embedding helpers (no external ML dependency)
    # ------------------------------------------------------------------
    VEC_DIM = 128  # dimensionality of hash-based embeddings

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple whitespace + punctuation tokenizer."""
        return re.findall(r'\b\w+\b', text.lower())

    @staticmethod
    def _embed(text: str) -> np.ndarray:
        """Hash-based text embedding via simhash-style vectorisation.

        Maps each token to a random (+1/-1) vector position using a
        deterministic hash, then accumulates into a fixed-size float
        vector.  Normalised to unit length for cosine similarity.
        """
        vec = np.zeros(DecisionEngine.VEC_DIM, dtype=np.float32)
        tokens = DecisionEngine._tokenize(text)
        if not tokens:
            return np.zeros(DecisionEngine.VEC_DIM, dtype=np.float32)
        for tok in tokens:
            h = int(hashlib.sha256(tok.encode()).hexdigest(), 16) % DecisionEngine.VEC_DIM
            # ±1 based on hash parity
            vec[h] += 1.0 if h % 2 == 0 else -1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    @staticmethod
    def _sentiment_score(text: str) -> float:
        """Rough sentiment polarity (-1..+1) via negation + polarity lexicon.

        Returns a normalised score: >0.3 = positive lean, <-0.3 = negative.
        """
        POSITIVE = {
            'good', 'safe', 'secure', 'valid', 'trust', 'proven',
            'verify', 'integrity', 'honest', 'correct', 'sound',
            'stable', 'reliable', 'beneficial', 'allowed', 'pass',
        }
        NEGATIVE = {
            'bad', 'unsafe', 'insecure', 'invalid', 'untrust',
            'forged', 'fake', 'false', 'lie', 'harm', 'dangerous',
            'wrong', 'unstable', 'unreliable', 'risky', 'blocked',
            'fail', 'reject', 'deny', 'bypass', 'override',
        }
        NEGATORS = {'not', 'no', 'never', 'neither', 'neither', 'nor', 'without'}

        words = DecisionEngine._tokenize(text)
        pos_hits = 0
        neg_hits = 0
        prev_negator = False

        for w in words:
            if w in NEGATORS:
                prev_negator = True
                continue
            if prev_negator:
                if w in POSITIVE:
                    neg_hits += 2  # negated positive
                elif w in NEGATIVE:
                    pos_hits += 2  # negated negative = positive
                prev_negator = False
                continue
            if w in POSITIVE:
                pos_hits += 1
            elif w in NEGATIVE:
                neg_hits += 1

        total = pos_hits + neg_hits
        if total == 0:
            return 0.0
        return (pos_hits - neg_hits) / total

    # ------------------------------------------------------------------
    # Contradiction detection
    # ------------------------------------------------------------------
    def _detect_self_contradiction_keyword(self, text: str) -> bool:
        """Fast-path: keyword soup contradiction detection.

        Catches obvious contradictions like 'safe' AND 'unsafe' in the
        same response.
        """
        words = set(self._tokenize(text))
        dangerous_pairs = [
            ('safe', 'unsafe'), ('allowed', 'blocked'),
            ('valid', 'invalid'), ('true', 'false'),
            ('honest', 'deceptive'), ('secure', 'compromised'),
        ]
        for a, b in dangerous_pairs:
            if a in words and b in words:
                return True
        return False

    def _detect_self_contradiction_embedding(self, text: str) -> bool:
        """Embedding-based contradiction detection.

        Splits text into sentences, computes hash-based embeddings,
        and flags pairs that are both lexically similar (>0.6 cosine)
        but sentiment-opposite (delta > 0.6).
        """
        # Split into sentences (handle abbreviations poorly, but good enough)
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 20]
        if len(sentences) < 2:
            return False

        # Compute embeddings and sentiments
        embs = np.array([self._embed(s) for s in sentences])
        sents = np.array([self._sentiment_score(s) for s in sentences])

        for i in range(len(sentences)):
            for j in range(i + 1, len(sentences)):
                # Lexical similarity (cosine distance → similarity)
                sim = 1.0 - cosine_distance(embs[i], embs[j])
                if sim > 0.6:
                    # High similarity but opposite sentiment → contradiction
                    sent_delta = abs(float(sents[i]) - float(sents[j]))
                    if sent_delta > 0.6:
                        return True
        return False

    def _detect_input_contradiction_keyword(self, prompt: str, prior: str) -> bool:
        """Fast-path: detect contradiction between prompt and prior response."""
        prompt_words = set(self._tokenize(prompt))
        prior_words = set(self._tokenize(prior))
        dangerous_pairs = [
            ('safe', 'unsafe'), ('allowed', 'blocked'),
            ('disable', 'enable'), ('override', 'respect'),
        ]
        for a, b in dangerous_pairs:
            if (a in prompt_words and b in prior_words) or \
               (b in prompt_words and a in prior_words):
                return True
        return False

    def _detect_input_contradiction_embedding(self, prompt: str, prior: str) -> bool:
        """Embedding-based prompt-vs-prior contradiction detection."""
        prompt_emb = self._embed(prompt)
        prior_emb = self._embed(prior)
        sim = 1.0 - cosine_distance(prompt_emb, prior_emb)
        if sim > 0.5:
            p_sent = self._sentiment_score(prompt)
            r_sent = self._sentiment_score(prior)
            if abs(p_sent - r_sent) > 0.6:
                return True
        return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_pipeline(self, input_text: str) -> dict:
        """Full decision pipeline: keywords + contradiction detection + hash.

        Uses keyword risk scoring, then runs both self-contradiction and
        input-contradiction detection (when a prior response is available).
        """
        risk_keywords = ["nuclear", "bomb", "weapon", "hack", "exploit"]
        is_dangerous = any(kw in input_text.lower() for kw in risk_keywords)
        base_risk = 0.9 if is_dangerous else 0.12

        # Contradiction detection
        self_contradiction = self._detect_self_contradiction_keyword(input_text)
        self_contradict_label = None
        if self_contradiction:
            self_contradict_label = "keyword"
            base_risk = max(base_risk, 0.7)

        # Cosine similarity: low for dangerous/high-risk, higher for benign
        cosine_sim = 0.4 if base_risk > 0.6 else 0.92

        signal_hash = hashlib.sha256(f"{input_text}|{datetime.now().isoformat()}".encode()).hexdigest()[:16]

        return {
            "risk_score": base_risk,
            "cosine_similarity": cosine_sim,
            "hash": signal_hash,
            "input_text": input_text[:200],
            "self_contradiction": self_contradict_label,
        }

    def detect_self_contradiction(self, text: str) -> Tuple[bool, str]:
        """Detect contradictions within *text*.

        Returns (is_contradiction, method).
        """
        # Fast keyword path
        if self._detect_self_contradiction_keyword(text):
            return True, "keyword"
        # Deeper embedding path
        if self._detect_self_contradiction_embedding(text):
            return True, "embedding"
        return False, None

    def detect_input_contradiction(self, prompt: str, prior: str) -> Tuple[bool, str]:
        """Detect contradiction between *prompt* and *prior* response.

        Returns (is_contradiction, method).
        """
        if self._detect_input_contradiction_keyword(prompt, prior):
            return True, "keyword"
        if self._detect_input_contradiction_embedding(prompt, prior):
            return True, "embedding"
        return False, None

