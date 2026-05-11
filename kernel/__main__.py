#!/usr/bin/env python3
"""
Weaver ASI — Package entry point
=================================
Run: python3 -m kernel sovereign|graded|recovery|anchored|cli
"""
import sys
import os

# Ensure the parent of kernel is on sys.path so kernel is importable
this_dir = os.path.dirname(os.path.abspath(__file__))
parent = os.path.dirname(this_dir)
if parent not in sys.path:
    sys.path.insert(0, parent)

# Import from absolute path (kernel is now importable because parent is on sys.path)
from kernel.orchestrators.master_orchestrator_sovereign import main as main_sovereign
from kernel.orchestrators.master_orchestrator_graded import main as main_graded
from kernel.orchestrators.master_orchestrator_recovery import main as main_recovery
from kernel.orchestrators.master_orchestrator_anchored import main as main_anchored

from kernel.cli.weaver_cli import main as main_cli

MODES = {
    "sovereign": main_sovereign,
    "graded": main_graded,
    "recovery": main_recovery,
    "anchored": main_anchored,
    "cli": main_cli,
}

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "sovereign"
    if mode not in MODES:
        print(f"Usage: python3 -m kernel [sovereign|graded|recovery|anchored|cli]")
        sys.exit(1)
    MODES[mode]()

if __name__ == "__main__":
    main()
