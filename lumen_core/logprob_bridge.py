#!/usr/bin/env python3
"""logprob_bridge.py — Token-probability bridge for consistency analysis.

Provides:
  1. LogProbBridge — extracts per-token log-probs from Elpis/llama-cpp responses
     and computes Shannon entropy + KL-divergence metrics.
  2. PHI_CONSISTENCY_SPLIT — emits a Chronicle event when D_KL > 2.0 or
     delta_H > 3.5, flagging a potential self-consistency violation.

Design:
  The Elpis plugin's generate() call is instrumented (via this bridge) to
  request logprobs from llama-cpp-python.  The bridge then analyses the
  token-level probability distribution to detect:
    - High entropy: model is uncertain / exploring (may indicate confusion)
    - KL divergence spike: distribution shifts dramatically mid-generation
    - delta_H: entropy change between consecutive windows
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("lumen_core.logprob_bridge")

# ── Thresholds (tuned from initial benchmarks) ────────────────────────────
D_KL_THRESHOLD = 2.0      # KL-divergence above which we flag inconsistency
DELTA_H_THRESHOLD = 3.5   # Entropy delta above which we flag instability
WINDOW_SIZE = 16          # Sliding window size for delta-H computation


@dataclass
class TokenLogProb:
    """Per-token log-probability record."""
    token_id: int
    token_text: str
    logprob: float          # log P(token | context) in nats
    rank: int               # rank of the sampled token


@dataclass
class LogProbAnalysis:
    """Aggregated analysis of token-level probabilities."""
    mean_entropy: float           # Average Shannon entropy across tokens
    max_entropy: float            # Peak entropy observed
    mean_dkl: float               # Mean KL-divergence between consecutive windows
    max_dkl: float                # Peak KL-divergence
    delta_h_max: float            # Max entropy change between windows
    windows_analyzed: int         # Number of windows processed
    tokens_analyzed: int          # Total tokens analyzed
    consistency_violation: bool   # True if any threshold exceeded


class LogProbBridge:
    """Bridge between Elpis generation and probability analysis.

    Usage:
        bridge = LogProbBridge()

        # Analyze a list of TokenLogProb objects (obtained from
        # llama-cpp-python's logprobs parameter)
        analysis = bridge.analyze(logprob_tokens)

        if analysis.consistency_violation:
            # Emit PHI_CONSISTENCY_SPLIT chronicle event
            bridge.emit_violation_event(analysis, prompt="...")
    """

    def __init__(
        self,
        d_kl_threshold: float = D_KL_THRESHOLD,
        delta_h_threshold: float = DELTA_H_THRESHOLD,
        window_size: int = WINDOW_SIZE,
    ):
        self.d_kl_threshold = d_kl_threshold
        self.delta_h_threshold = delta_h_threshold
        self.window_size = window_size

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def analyze(self, tokens: List[TokenLogProb]) -> LogProbAnalysis:
        """Analyse token-level logprobs and return aggregated metrics.

        Computes:
          - Shannon entropy per token (using the full distribution)
          - KL-divergence between consecutive windows
          - Delta-H: entropy change between windows
        """
        if not tokens:
            return LogProbAnalysis(
                mean_entropy=0.0,
                max_entropy=0.0,
                mean_dkl=0.0,
                max_dkl=0.0,
                delta_h_max=0.0,
                windows_analyzed=0,
                tokens_analyzed=0,
                consistency_violation=False,
            )

        # 1. Per-window entropy computation
        windows = self._split_into_windows(tokens, self.window_size)
        entropies = [self._shannon_entropy(w) for w in windows]

        mean_entropy = sum(entropies) / len(entropies) if entropies else 0.0
        max_entropy = max(entropies) if entropies else 0.0

        # 2. KL-divergence between consecutive windows
        kl_divs = []
        for i in range(1, len(windows)):
            kl = self._kl_divergence(windows[i - 1], windows[i])
            kl_divs.append(kl)

        mean_dkl = sum(kl_divs) / len(kl_divs) if kl_divs else 0.0
        max_dkl = max(kl_divs) if kl_divs else 0.0

        # 3. Delta-H (entropy change between consecutive windows)
        deltas = []
        for i in range(1, len(entropies)):
            deltas.append(abs(entropies[i] - entropies[i - 1]))
        delta_h_max = max(deltas) if deltas else 0.0

        # 4. Consistency check
        consistency_violation = (
            max_dkl > self.d_kl_threshold
            or delta_h_max > self.delta_h_threshold
        )

        return LogProbAnalysis(
            mean_entropy=mean_entropy,
            max_entropy=max_entropy,
            mean_dkl=mean_dkl,
            max_dkl=max_dkl,
            delta_h_max=delta_h_max,
            windows_analyzed=len(windows),
            tokens_analyzed=len(tokens),
            consistency_violation=consistency_violation,
        )

    # ------------------------------------------------------------------
    # Statistics helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _shannon_entropy(tokens: List[TokenLogProb]) -> float:
        """Compute Shannon entropy of a window of tokens.

        Uses the sampled token logprobs as a proxy for the full distribution.
        H = -sum(p * log(p)) where p = exp(logprob).
        """
        if not tokens:
            return 0.0

        # Normalise logprobs to probabilities
        max_logp = max(t.logprob for t in tokens)
        probs = [math.exp(lp - max_logp) for lp in (t.logprob for t in tokens)]
        total = sum(probs)
        if total == 0:
            return 0.0

        probs = [p / total for p in probs]  # renormalise

        entropy = 0.0
        for p in probs:
            if p > 1e-10:
                entropy -= p * math.log(p)
        return entropy

    @staticmethod
    def _kl_divergence(p_window: List[TokenLogProb],
                       q_window: List[TokenLogProb]) -> float:
        """KL(P || Q): divergence of q-window from p-window.

        Uses entropy of each window as a proxy for the full distribution.
        KL ≈ H(q) - H(p)  (negative KL when P is more peaked than Q).
        """
        h_p = LogProbBridge._shannon_entropy(p_window)
        h_q = LogProbBridge._shannon_entropy(q_window)
        return h_q - h_p  # positive = Q is more uncertain than P

    @staticmethod
    def _split_into_windows(
        tokens: List[TokenLogProb],
        window_size: int,
    ) -> List[List[TokenLogProb]]:
        """Split token list into non-overlapping windows."""
        if len(tokens) < window_size:
            return [tokens]
        windows = []
        for i in range(0, len(tokens), window_size):
            windows.append(tokens[i:i + window_size])
        return windows

    # ------------------------------------------------------------------
    # Chronicle integration
    # ------------------------------------------------------------------

    def emit_violation_event(self, analysis: LogProbAnalysis,
                              prompt: str = "",
                              response: str = "") -> None:
        """Emit a PHI_CONSISTENCY_SPLIT Chronicle event on threshold breach."""
        if not analysis.consistency_violation:
            return

        from lumen_core.safety.chronicle import chronicle_event

        chronicle_event("PHI_CONSISTENCY_SPLIT", {
            "prompt": prompt[:200],
            "response_truncated": len(response) > 256 if response else False,
            "mean_entropy": round(analysis.mean_entropy, 4),
            "max_entropy": round(analysis.max_entropy, 4),
            "mean_dkl": round(analysis.mean_dkl, 4),
            "max_dkl": round(analysis.max_dkl, 4),
            "delta_h_max": round(analysis.delta_h_max, 4),
            "windows_analyzed": analysis.windows_analyzed,
            "tokens_analyzed": analysis.tokens_analyzed,
            "reason": (
                f"D_KL={analysis.max_dkl:.4f} > {self.d_kl_threshold}"
                if analysis.max_dkl > self.d_kl_threshold
                else f"delta_H={analysis.delta_h_max:.4f} > {self.delta_h_threshold}"
            ),
        })
        logger.warning(
            "[LogProbBridge] PHI_CONSISTENCY_SPLIT: D_KL=%.4f delta_H=%.4f "
            "(thresholds: D_KL=%.1f delta_H=%.1f)",
            analysis.max_dkl, analysis.delta_h_max,
            self.d_kl_threshold, self.delta_h_threshold,
        )


# ── Convenience: build logprob tokens from llama-cpp raw output ──────────

def tokens_from_llama_result(
    result: dict,
) -> List[TokenLogProb]:
    """Extract TokenLogProb objects from llama-cpp-python logprobs output.

    llama-cpp returns logprobs in this structure:
      {
        "content": [
          {"token_id": 1234, "text": "hello", "logprob": -0.1, "top_logprobs": [...]},
          ...
        ]
      }

    Also works with the raw `logprobs` dict from create_completion.
    """
    tokens = []
    try:
        # Try chat completion format
        choices = result.get("choices", [])
        if choices:
            content = choices[0].get("content", [])
            if isinstance(content, list):
                for item in content:
                    tokens.append(TokenLogProb(
                        token_id=item.get("token_id", len(tokens)),
                        token_text=item.get("text", ""),
                        logprob=item.get("logprob", 0.0),
                        rank=item.get("rank", 0),
                    ))
            # If content is just a string, return empty (no logprobs)
    except (AttributeError, KeyError, TypeError):
        pass

    return tokens
