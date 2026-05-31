#!/usr/bin/env python3
"""
Aurora Analysis — lightweight analysis of AURORA-AXIS evaluation results.
Reads phase2_export.json or raw evaluation output and produces summary statistics.

Standalone script: not a library, meant to be run directly.
Intended location: Lumen/harness/ (evaluation tool for the AURORA-AXIS system).
"""
import json
import sys
import os
from collections import Counter
from datetime import datetime

def load_results(path: str) -> dict:
    """Load evaluation results from JSON file."""
    with open(path, "r") as f:
        return json.load(f)

def analyze_phase2(path: str) -> dict:
    """Analyze a Phase 2 export for human rater review."""
    data = load_results(path)
    outputs = data.get("outputs", [])
    
    by_system = Counter()
    for out in outputs:
        by_system[out["system_name"]] += 1
    
    return {
        "total_outputs": len(outputs),
        "by_system": dict(by_system),
        "timestamp": data.get("timestamp", "unknown"),
    }

def analyze_experiment(path: str) -> dict:
    """Analyze raw experiment runner results."""
    data = load_results(path)
    summary = data.get("summary", {})
    
    results = {}
    for system_name, metrics in summary.items():
        results[system_name] = {
            "interpretation_accuracy": metrics.get("interpretation_accuracy", 0),
            "success_rate": metrics.get("success_rate", 0),
            "avg_execution_quality": metrics.get("avg_execution_quality", 0),
            "avg_intent_alignment": metrics.get("avg_intent_alignment", 0),
            "f1_error_rate": metrics.get("f1_error_rate", 0),
            "f2_error_rate": metrics.get("f2_error_rate", 0),
            "f3_error_rate": metrics.get("f3_error_rate", 0),
        }
    
    # Find best system
    best = max(results.items(), key=lambda x: x[1]["success_rate"])
    
    return {
        "systems": results,
        "best_system": best[0],
        "best_success_rate": best[1]["success_rate"],
        "n_prompts": data.get("n_prompts", 0),
        "n_systems": len(results),
        "drift_recovery": data.get("drift_recovery", {}).get("recovery_rate", 0)
            if "drift_recovery" in data else None,
    }

def compare_systems(path: str) -> str:
    """Generate a human-readable comparison of all systems."""
    data = load_results(path)
    
    if "detailed_results" in data:
        # Raw experiment output
        results = analyze_experiment(path)
        lines = [
            "=" * 70,
            "AURORA-AXIS Evaluation — System Comparison",
            "=" * 70,
            f"Prompts: {results['n_prompts']}",
            f"Systems: {results['n_systems']}",
            "",
        ]
        
        for name, metrics in results["systems"].items():
            lines.append(f"--- {name} ---")
            lines.append(f"  Interpretation Accuracy: {metrics['interpretation_accuracy']:.1%}")
            lines.append(f"  Success Rate:            {metrics['success_rate']:.1%}")
            lines.append(f"  Execution Quality:       {metrics['avg_execution_quality']:.3f}")
            lines.append(f"  Intent Alignment:        {metrics['avg_intent_alignment']:.3f}")
            lines.append(f"  F1 Errors (Interp):      {metrics['f1_error_rate']:.1%}")
            lines.append(f"  F2 Errors (Exec):        {metrics['f2_error_rate']:.1%}")
            lines.append(f"  F3 Errors (Drift):       {metrics['f3_error_rate']:.1%}")
            lines.append("")
        
        lines.append(f"Winner: {results['best_system']} ({results['best_success_rate']:.1%} success rate)")
        if results.get("drift_recovery") is not None:
            lines.append(f"Drift Recovery Rate: {results['drift_recovery']:.1%}")
        
        return "\n".join(lines)
    
    elif "outputs" in data:
        # Phase 2 export
        analysis = analyze_phase2(path)
        lines = [
            "=" * 70,
            "AURORA-AXIS Phase 2 Export — Summary",
            "=" * 70,
            f"Total outputs: {analysis['total_outputs']}",
            f"By system: {json.dumps(analysis['by_system'], indent=4)}",
            f"Timestamp: {analysis['timestamp']}",
        ]
        return "\n".join(lines)
    
    else:
        return "Unknown format. Expected experiment results or Phase 2 export."

def main():
    if len(sys.argv) < 2:
        print("Usage: aurora_analysis.py <results.json>")
        print("  Analyzes AURORA-AXIS evaluation results (experiment output or Phase 2 export)")
        sys.exit(1)
    
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"Error: {path} not found")
        sys.exit(1)
    
    print(compare_systems(path))

if __name__ == "__main__":
    main()
