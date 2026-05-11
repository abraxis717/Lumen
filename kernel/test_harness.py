#!/usr/bin/env python3
"""
kernel.test_harness — Module entry point for governance membrane verification.

Imported from the root harness.py so that:
    python3 -m kernel.test_harness
works correctly.
"""
import sys
import os

# Ensure root directory (parent of kernel/) is on the path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from harness import run_harness

if __name__ == "__main__":
    success = run_harness()
    sys.exit(0 if success else 1)
