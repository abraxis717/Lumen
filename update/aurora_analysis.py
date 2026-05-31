"""
AURORA-AXIS Evaluation Analysis

Tools for interpreting results and making decisions about whether
semantic alignment is necessary (Option 2) or current system is sufficient.
"""

import json
import numpy as np
from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class DecisionCriteria:
    """Decision thresholds for interpreting results"""
    AURORA_ADVANTAGE_THRESHOLD = 0.15  # 15% improvement over best baseline
    DRIFT_RECOVERY_THRESHOLD = 0.70    # 70% successful recovery
    F1_ERROR_THRESHOLD = 0.25          # < 25% interpretation errors acceptable


class ResultAnalyzer:
    """Analyze evaluation results and recommend next steps"""

    def __init__(self, results: Dict[str, Any]):
        self.results = results
        self.summary = results["summary"]
        self.criteria = DecisionCriteria()

    def analyze(self) -> Dict[str, Any]:
        """Run full analysis and generate recommendation"""
        analysis = {
            "timestamp": self.results["timestamp"],
            "interpretation_accuracy_gap": self._gap_analysis(),
            "baseline_comparison": self._baseline_comparison(),
            "failure_mode_analysis": self._failure_mode_analysis(),
            "drift_handling": self._drift_analysis(),
            "recommendation": self._generate_recommendation(),
        }
        return analysis

    def _gap_analysis(self) -> Dict[str, float]:
        """Compute AURORA-AXIS advantage over baselines"""
        aurora_accuracy = self.summary["AURORA-AXIS"]["interpretation_accuracy"]
        baseline_accuracies = {
            name: metrics["interpretation_accuracy"]
            for name, metrics in self.summary.items()
            if name != "AURORA-AXIS"
        }
        best_baseline = max(baseline_accuracies.values())

        return {
            "aurora_accuracy": aurora_accuracy,
            "best_baseline_accuracy": best_baseline,
            "absolute_gap": aurora_accuracy - best_baseline,
            "relative_improvement": (aurora_accuracy - best_baseline) / best_baseline if best_baseline > 0 else 0,
            "is_significant": (aurora_accuracy - best_baseline) > self.criteria.AURORA_ADVANTAGE_THRESHOLD,
        }

    def _baseline_comparison(self) -> Dict[str, Any]:
        """Compare each baseline to AURORA-AXIS"""
        comparison = {}
        aurora_metrics = self.summary["AURORA-AXIS"]

        for baseline_name, baseline_metrics in self.summary.items():
            if baseline_name == "AURORA-AXIS":
                continue

            comparison[baseline_name] = {
                "accuracy_vs_aurora": baseline_metrics["interpretation_accuracy"]
                - aurora_metrics["interpretation_accuracy"],
                "quality_vs_aurora": baseline_metrics["avg_execution_quality"]
                - aurora_metrics["avg_execution_quality"],
                "is_competitive": (
                    baseline_metrics["interpretation_accuracy"] > aurora_metrics["interpretation_accuracy"] * 0.9
                ),
            }

        return comparison

    def _failure_mode_analysis(self) -> Dict[str, Any]:
        """Analyze which failure modes dominate"""
        aurora = self.summary["AURORA-AXIS"]

        return {
            "f1_interpretation_error_rate": aurora["f1_error_rate"],
            "f2_execution_error_rate": aurora["f2_error_rate"],
            "f3_drift_miss_rate": aurora["f3_error_rate"],
            "dominant_failure_mode": max(
                [("F1", aurora["f1_error_rate"]), ("F2", aurora["f2_error_rate"]), ("F3", aurora["f3_error_rate"])],
                key=lambda x: x[1],
            )[0],
            "interpretation_errors_acceptable": aurora["f1_error_rate"] < self.criteria.F1_ERROR_THRESHOLD,
        }

    def _drift_analysis(self) -> Dict[str, Any]:
        """Analyze intent drift handling"""
        # Note: drift_results would come from separate drift experiment
        return {
            "note": "Drift recovery measured separately via run_drift_experiment()",
            "criterion": f"Recovery rate should exceed {self.criteria.DRIFT_RECOVERY_THRESHOLD:.0%}",
        }

    def _generate_recommendation(self) -> Dict[str, Any]:
        """Generate actionable recommendation"""
        gap = self._gap_analysis()
        failures = self._failure_mode_analysis()

        if gap["is_significant"]:
            recommendation = "OPTION 1: Productionize (Forward-Only is Sufficient)"
            reasoning = [
                f"AURORA-AXIS shows {gap['relative_improvement']:.1%} improvement over best baseline",
                "Interpretation errors are within acceptable threshold",
                "System demonstrates advantage in multi-intent disambiguation",
            ]
            next_steps = [
                "1. Wire in real embeddings (not random)",
                "2. Generate interpretations from actual LLM (not hardcoded)",
                "3. Deploy and measure real-world performance",
            ]
        elif failures["dominant_failure_mode"] == "F1":
            recommendation = "OPTION 2: Implement Semantic Alignment Layer"
            reasoning = [
                f"Interpretation errors dominate ({failures['f1_interpretation_error_rate']:.1%})",
                "Forward-only system cannot distinguish intent drift from noise",
                "Need explicit semantic alignment to catch wrong interpretations",
            ]
            next_steps = [
                "1. Implement intent embedding + cosine similarity (not threshold)",
                "2. Add execution quality scorer (match trace to interpretation)",
                "3. Implement verifier feedback loop to re-plan on semantic mismatch",
            ]
        elif failures["dominant_failure_mode"] == "F2":
            recommendation = "OPTION 1 + Execution Quality Improvement"
            reasoning = [
                "System picks correct interpretations but executes poorly",
                "Problem is not semantic alignment but execution fidelity",
                "Interpretations are correct; implementation is the issue",
            ]
            next_steps = [
                "1. Improve executor implementation (more detailed planning)",
                "2. Add execution validation (does output match interpretation?)",
                "3. Consider specialized executors per interpretation type",
            ]
        else:
            recommendation = "OPTION 3: Investigate Further"
            reasoning = [
                "Results are mixed or inconclusive",
                "System performs similarly to baselines",
                "May need larger dataset or different test cases",
            ]
            next_steps = [
                "1. Increase dataset size to n=200+",
                "2. Add adversarial drift cases",
                "3. Consider human evaluation to validate metrics",
            ]

        return {
            "recommendation": recommendation,
            "reasoning": reasoning,
            "next_steps": next_steps,
            "confidence": "high" if gap["is_significant"] or not failures["interpretation_errors_acceptable"] else "medium",
        }


class ReportGenerator:
    """Generate human-readable evaluation report"""

    def __init__(self, results: Dict[str, Any], analysis: Dict[str, Any]):
        self.results = results
        self.analysis = analysis

    def generate_text_report(self, output_file: str = "aurora_evaluation_report.txt") -> str:
        """Generate text report"""
        report = []
        report.append("=" * 80)
        report.append("AURORA-AXIS EVALUATION REPORT")
        report.append("=" * 80)
        report.append("")

        # Executive Summary
        report.append("EXECUTIVE SUMMARY")
        report.append("-" * 80)
        report.append(f"Recommendation: {self.analysis['recommendation']['recommendation']}")
        report.append(f"Confidence: {self.analysis['recommendation']['confidence'].upper()}")
        report.append("")

        # Reasoning
        report.append("REASONING:")
        for point in self.analysis["recommendation"]["reasoning"]:
            report.append(f"  • {point}")
        report.append("")

        # Results
        report.append("QUANTITATIVE RESULTS")
        report.append("-" * 80)
        gap = self.analysis["interpretation_accuracy_gap"]
        report.append(f"AURORA-AXIS Interpretation Accuracy: {gap['aurora_accuracy']:.1%}")
        report.append(f"Best Baseline Accuracy:             {gap['best_baseline_accuracy']:.1%}")
        report.append(f"Absolute Improvement:              {gap['absolute_gap']:+.1%}")
        report.append(f"Relative Improvement:              {gap['relative_improvement']:+.1%}")
        report.append("")

        # Baseline Comparison
        report.append("BASELINE COMPARISON")
        report.append("-" * 80)
        for baseline_name, comparison in self.analysis["baseline_comparison"].items():
            competitive = "✓ COMPETITIVE" if comparison["is_competitive"] else "✗ NOT COMPETITIVE"
            report.append(f"{baseline_name}: {competitive}")
            report.append(f"  Accuracy vs AURORA: {comparison['accuracy_vs_aurora']:+.1%}")
        report.append("")

        # Failure Modes
        report.append("FAILURE MODE ANALYSIS")
        report.append("-" * 80)
        failures = self.analysis["failure_mode_analysis"]
        report.append(f"F1 (Interpretation Error): {failures['f1_interpretation_error_rate']:.1%}")
        report.append(f"F2 (Execution Error):      {failures['f2_execution_error_rate']:.1%}")
        report.append(f"F3 (Drift Miss):           {failures['f3_drift_miss_rate']:.1%}")
        report.append(f"Dominant Failure Mode:     {failures['dominant_failure_mode']}")
        report.append("")

        # Next Steps
        report.append("RECOMMENDED NEXT STEPS")
        report.append("-" * 80)
        for step in self.analysis["recommendation"]["next_steps"]:
            report.append(step)
        report.append("")

        # Closing
        report.append("=" * 80)
        report.append("END REPORT")
        report.append("=" * 80)

        text_report = "\n".join(report)

        # Write to file
        with open(output_file, "w") as f:
            f.write(text_report)

        print(f"\n✓ Report written to {output_file}")
        return text_report


def interpret_results(results_file: str = "phase1_results.json"):
    """Load results and generate analysis + report"""
    with open(results_file, "r") as f:
        results = json.load(f)

    analyzer = ResultAnalyzer(results)
    analysis = analyzer.analyze()

    reporter = ReportGenerator(results, analysis)
    report = reporter.generate_text_report()

    print("\n" + report)

    return analysis


if __name__ == "__main__":
    print("\nTo generate analysis report, run:")
    print("  python aurora_harness.py > phase1_results.json")
    print("  python aurora_analysis.py")
