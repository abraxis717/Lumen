"""
model_loader.py — GGUF-based MobileModel for Termux/Pydroid.

Uses llama-cpp-python for GGUF model inference.
Lightweight: no transformers dependency, minimal RAM footprint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


class MobileModel:
    """Lightweight GGUF model loader for mobile environments.

    Uses llama-cpp-python for inference. Designed to run on
    Termux (Android) or Pydroid with < 200 MB RAM.

    Args:
        model_path: Path to a GGUF model file.
        n_gpu_layers: Number of layers to offload to GPU (-1 for all).
        n_ctx: Context window size.
        temperature: Sampling temperature (0.0 = greedy).
    """

    def __init__(
        self,
        model_path: str,
        n_gpu_layers: int = -1,
        n_ctx: int = 512,
        temperature: float = 0.7,
    ) -> None:
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.temperature = temperature
        self._model: Any = None
        self._llm: Any = None

        # Lazy-load llama-cpp-python
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError:
            raise ImportError(
                "llama-cpp-python is required for MobileModel.\n"
                "Install with: pip install llama-cpp-python\n"
                "Or use GPU: pip install llama-cpp-python[cuda12]"
            )

        self._llm = Llama(
            model_path=model_path,
            n_gpu_layers=n_gpu_layers,
            n_ctx=n_ctx,
            verbose=False,
        )
        self._model = self._llm

    def generate(
        self,
        prompt: str,
        max_tokens: int = 64,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate text from a prompt using the GGUF model.

        Args:
            prompt: The input prompt.
            max_tokens: Maximum number of tokens to generate.
            temperature: Override model temperature.

        Returns:
            Generated text string.
        """
        temp = temperature if temperature is not None else self.temperature
        output = self._llm.create_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temp,
            echo=False,
        )
        return output["choices"][0]["text"].strip()

    def embed(self, text: str) -> List[float]:
        """Return embeddings for the given text.

        Args:
            text: Input text to embed.

        Returns:
            List of float embeddings.
        """
        embedding = self._llm.embed(text)
        return embedding

    def __del__(self) -> None:
        """Cleanup llama-cpp-python resources."""
        if hasattr(self, "_llm") and self._llm is not None:
            try:
                self._llm.close()
            except Exception:
                pass
