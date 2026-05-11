"""
mobile/ — Lightweight inference module for mobile/Termux/Pydroid environments.

Uses llama-cpp-python (GGUF) as the primary backend.
Fallback: ONNX runtime for resource-constrained phones.
"""

__all__ = ["MobileModel"]

from .model_loader import MobileModel

__all__ = ["MobileModel"]
