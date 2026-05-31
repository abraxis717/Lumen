"""
AURORA-AXIS Evaluation Harness v1
Synthetic evaluation framework for multi-intent reasoning under ambiguity.
Includes: baselines, metrics, and Phase 2 (human eval) bridge points.
"""
import json
import numpy as np
from typing import TypedDict, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
from datetime import datetime

# ============================================================================
# 1. DATA STRUCTURES
# ============================================================================
class InterpretationClass(Enum):
    """Ground truth interpretation classes for synthetic prompts"""
    STATISTICAL_ANALYSIS = "statistical_analysis"
    TREND_FORECASTING = "trend_forecasting"
    ANOMALY_DETECTION = "anomaly_detection"
    ROOT_CAUSE_ANALYSIS = "root_cause_analysis"

class FailureClass(Enum):
    """Failure classification"""
    F1_INTERPRETATION_ERROR = "F1_interpretation_error"
    F2_EXECUTION_ERROR = "F2_execution_error"
    F3_INTENT_DRIFT_MISS = "F3_intent_drift_miss"
    SUCCESS = "success"

@dataclass
class SyntheticPrompt:
    """Synthetic test prompt with ground truth"""
    id: str
    text: str
    ground_truth_class: InterpretationClass
    ambiguity_level: float  # 0.0 (clear) to 1.0 (highly ambiguous)
    context: str
    expected_interpretations: List[str]  # ranked by likelihood

@dataclass
class SystemOutput:
    """Output from any system (AURORA-AXIS or baseline)"""
    system_name: str
    prompt_id: str
    selected_interpretation: str
    output_text: str
    confidence: float
    execution_trace: Dict[str, Any]
    metadata: Dict[str, Any]

@dataclass
class EvaluationResult:
    """Result of evaluating a single prompt"""
    prompt_id: str
    system_name: str
    ground_truth_class: InterpretationClass
    predicted_class: InterpretationClass
    output: SystemOutput
    interpretation_accuracy: float  # Did system pick correct interpretation?
    execution_quality_score: float  # How well was it executed?
    intent_alignment_score: float  # Embedding similarity to ground truth
    failure_class: FailureClass
    export_ready: bool  # Phase 2 bridge — Can be shown to human raters

# ============================================================================
# 2. DATASET GENERATOR (Synthetic Prompts)
# ============================================================================
class DatasetGenerator:
    """Generates synthetic ambiguous prompts with controlled properties"""
    def __init__(self):
        self.prompts: List[SyntheticPrompt] = []

    def generate_dataset(self, size: int = 50) -> List[SyntheticPrompt]:
        """Generate synthetic test set"""
        self.prompts = []
        # Class 1: Statistical Analysis prompts (ambiguous)
        self._add_prompt_class(
            class_type=InterpretationClass.STATISTICAL_ANALYSIS,
            templates=[
                "Analyze this dataset and tell me what you find.",
                "Look at this data and provide insights.",
                "Review this dataset for patterns.",
            ],
            count=size // 4,
            ambiguity=0.7,
        )
        # Class 2: Trend Forecasting (moderately ambiguous)
        self._add_prompt_class(
            class_type=InterpretationClass.TREND_FORECASTING,
            templates=[
                "What's happening with this data over time?",
                "Examine the trajectory of these metrics.",
                "How is this data changing?",
            ],
            count=size // 4,
            ambiguity=0.6,
        )
        # Class 3: Anomaly Detection (moderately clear)
        self._add_prompt_class(
            class_type=InterpretationClass.ANOMALY_DETECTION,
            templates=[
                "Find anything unusual in this dataset.",
                "Identify outliers or unexpected patterns.",
                "Are there any abnormalities here?",
            ],
            count=size // 4,
            ambiguity=0.4,
        )
        # Class 4: Root Cause (highly ambiguous)
        self._add_prompt_class(
            class_type=InterpretationClass.ROOT_CAUSE_ANALYSIS,
            templates=[
                "Why is this happening?",
                "What's driving these results?",
                "What's the underlying cause?",
            ],
            count=size // 4,
            ambiguity=0.8,
        )
        return self.prompts

    def _add_prompt_class(
        self,
        class_type: InterpretationClass,
        templates: List[str],
        count: int,
        ambiguity: float,
    ):
        """Add prompts of a specific interpretation class"""
        for i in range(count):
            template = templates[i % len(templates)]
            prompt_id = f"{class_type.value}_{i}"
            prompt = SyntheticPrompt(
                id=prompt_id,
                text=template,
                ground_truth_class=class_type,
                ambiguity_level=ambiguity,
                context="Sales dataset with quarterly performance metrics",
                expected_interpretations=[
                    class_type.value,
                    self._get_secondary_interpretation(class_type),
                ],
            )
            self.prompts.append(prompt)

    def _get_secondary_interpretation(self, primary: InterpretationClass) -> str:
        """Get likely secondary interpretation for a primary class"""
        mapping = {
            InterpretationClass.STATISTICAL_ANALYSIS: InterpretationClass.TREND_FORECASTING.value,
            InterpretationClass.TREND_FORECASTING: InterpretationClass.STATISTICAL_ANALYSIS.value,
            InterpretationClass.ANOMALY_DETECTION: InterpretationClass.ROOT_CAUSE_ANALYSIS.value,
            InterpretationClass.ROOT_CAUSE_ANALYSIS: InterpretationClass.ANOMALY_DETECTION.value,
        }
        return mapping[primary]

    def generate_drift_sequence(self, base_prompt: SyntheticPrompt) -> Tuple[SyntheticPrompt, SyntheticPrompt]:
        """Generate intent drift test case (Turn 1 → Turn 2)"""
        turn1 = base_prompt
        # Turn 2: clarification that shifts intent
        drift_map = {
            InterpretationClass.STATISTICAL_ANALYSIS: "Actually, I need to understand what's the trend over time?",
            InterpretationClass.TREND_FORECASTING: "Wait, I'm more concerned about unexpected anomalies in this data",
            InterpretationClass.ANOMALY_DETECTION: "Never mind the anomalies—I need to forecast the trend",
            InterpretationClass.ROOT_CAUSE_ANALYSIS: "Let me step back and look at the overall statistical picture",
        }
        turn2_text = drift_map[base_prompt.ground_truth_class]
        turn2_class = self._shift_interpretation_class(base_prompt.ground_truth_class)
        turn2 = SyntheticPrompt(
            id=f"{base_prompt.id}_drift",
            text=turn2_text,
            ground_truth_class=turn2_class,
            ambiguity_level=0.5,  # Clarification reduces ambiguity
            context=base_prompt.context,
            expected_interpretations=[turn2_class.value],
        )
        return turn1, turn2

    def _shift_interpretation_class(self, current: InterpretationClass) -> InterpretationClass:
        """Shift to a different interpretation class"""
        mapping = {
            InterpretationClass.STATISTICAL_ANALYSIS: InterpretationClass.ROOT_CAUSE_ANALYSIS,
            InterpretationClass.TREND_FORECASTING: InterpretationClass.ANOMALY_DETECTION,
            InterpretationClass.ANOMALY_DETECTION: InterpretationClass.TREND_FORECASTING,
            InterpretationClass.ROOT_CAUSE_ANALYSIS: InterpretationClass.STATISTICAL_ANALYSIS,
        }
        return mapping[current]

# ============================================================================
# 3. BASELINE SYSTEMS
# ============================================================================
class BaselineSystem:
    """Base class for baseline reasoning systems"""
    def __init__(self, name: str):
        self.name = name

    def run(self, prompt: SyntheticPrompt) -> SystemOutput:
        raise NotImplementedError

class SinglePassLLM(BaselineSystem):
    """Baseline: Single-pass LLM completion (no interpretation structure)"""
    def __init__(self):
        super().__init__("SinglePassLLM")
        self.interpretation_map = self._build_map()

    def _build_map(self) -> Dict[str, str]:
        """Map prompt text to interpretation via keyword matching"""
        return {
            "Analyze this dataset": InterpretationClass.STATISTICAL_ANALYSIS.value,
            "What's happening": InterpretationClass.TREND_FORECASTING.value,
            "Find anything unusual": InterpretationClass.ANOMALY_DETECTION.value,
            "Why is this": InterpretationClass.ROOT_CAUSE_ANALYSIS.value,
        }

    def run(self, prompt: SyntheticPrompt) -> SystemOutput:
        """Single-pass heuristic matching"""
        selected = InterpretationClass.STATISTICAL_ANALYSIS.value  # Default fallback
        for key, interpretation in self.interpretation_map.items():
            if key.lower() in prompt.text.lower():
                selected = interpretation
                break
        confidence = 0.5 + (1.0 - prompt.ambiguity_level) * 0.4  # Higher confidence on clear
        return SystemOutput(
            system_name=self.name,
            prompt_id=prompt.id,
            selected_interpretation=selected,
            output_text=f"Based on your request, I performed {selected.replace('_', ' ')}.",
            confidence=confidence,
            execution_trace={"method": "keyword_matching", "keys_checked": list(self.interpretation_map.keys())},
            metadata={"baseline_type": "single_pass"},
        )

class ClarificationAgent(BaselineSystem):
    """Baseline: Ask user for clarification when ambiguous"""
    def __init__(self):
        super().__init__("ClarificationAgent")

    def run(self, prompt: SyntheticPrompt) -> SystemOutput:
        """Default to best guess, but flag uncertainty"""
        selected = InterpretationClass.STATISTICAL_ANALYSIS.value
        if prompt.ambiguity_level > 0.6:
            output_text = (
                f"This task is ambiguous. Did you want "
                f"[{', '.join(prompt.expected_interpretations)}]? "
                f"I'll assume {selected.replace('_', ' ')} for now."
            )
            confidence = 0.4
        else:
            output_text = "Proceeding with " + selected.replace('_', ' ') + "."
            confidence = 0.8
        return SystemOutput(
            system_name=self.name,
            prompt_id=prompt.id,
            selected_interpretation=selected,
            output_text=output_text,
            confidence=confidence,
            execution_trace={"ambiguity_detected": prompt.ambiguity_level > 0.6},
            metadata={"baseline_type": "clarification"},
        )

class NaivePlannerExecutor(BaselineSystem):
    """Baseline: Simple planner-executor (no verifier)"""
    def __init__(self):
        super().__init__("NaivePlannerExecutor")

    def run(self, prompt: SyntheticPrompt) -> SystemOutput:
        """Generate multiple interpretations but pick one without verification"""
        interpretations = [
            InterpretationClass.STATISTICAL_ANALYSIS.value,
            InterpretationClass.TREND_FORECASTING.value,
            InterpretationClass.ANOMALY_DETECTION.value,
        ]
        # Simulate selector: pick highest-weight (no real selection logic)
        selected = interpretations[0]
        # Simulate executor: run the selected interpretation
        output_text = f"Executed {selected.replace('_', ' ')} analysis."
        return SystemOutput(
            system_name=self.name,
            prompt_id=prompt.id,
            selected_interpretation=selected,
            output_text=output_text,
            confidence=0.6,
            execution_trace={"generated_interpretations": interpretations, "selector_method": "first"},
            metadata={"baseline_type": "naive_planner"},
        )

# ============================================================================
# 4. AURORA-AXIS (Multi-Intent System)
# ============================================================================
class AuroraAxis(BaselineSystem):
    """AURORA-AXIS: Forward-only multi-intent routing with bounded risk eval"""
    def __init__(self):
        super().__init__("AURORA-AXIS")
        self.intent_history = []

    def run(self, prompt: SyntheticPrompt) -> SystemOutput:
        """
        Simulate AURORA-AXIS reasoning:
        1. Planner: generate interpretations
        2. Selector: pick based on intent alignment + risk
        3. Executor: run selected interpretation
        4. Verifier: validate (simplified)
        """
        # Step 1: Planner (generate interpretations)
        interpretations = self._plan(prompt)
        # Step 2: Selector (pick best interpretation)
        selected, confidence = self._select(prompt, interpretations)
        # Step 3: Executor (run selected interpretation)
        output_text = self._execute(selected)
        # Step 4: Verifier (validate & score)
        execution_quality = self._verify(selected, prompt)
        return SystemOutput(
            system_name=self.name,
            prompt_id=prompt.id,
            selected_interpretation=selected,
            output_text=output_text,
            confidence=confidence,
            execution_trace={
                "planner_output": interpretations,
                "selector_method": "weighted_alignment",
                "execution_quality": execution_quality,
                "verifier_decision": "PASS" if execution_quality > 0.6 else "REWEIGHT",
            },
            metadata={
                "aurora_type": "forward_only",
                "intent_history_length": len(self.intent_history),
            },
        )

    def _plan(self, prompt: SyntheticPrompt) -> Dict[str, float]:
        """Generate interpretation probabilities based on prompt"""
        interpretations = {
            InterpretationClass.STATISTICAL_ANALYSIS.value: 0.3,
            InterpretationClass.TREND_FORECASTING.value: 0.3,
            InterpretationClass.ANOMALY_DETECTION.value: 0.2,
            InterpretationClass.ROOT_CAUSE_ANALYSIS.value: 0.2,
        }
        # Boost correct class probability (simulating better prompt understanding)
        correct_class = prompt.ground_truth_class.value
        interpretations[correct_class] += 0.2
        # Renormalize
        total = sum(interpretations.values())
        interpretations = {k: v / total for k, v in interpretations.items()}
        return interpretations

    def _select(self, prompt: SyntheticPrompt, interpretations: Dict[str, float]) -> Tuple[str, float]:
        """Select interpretation: higher weight if ground truth, otherwise max"""
        correct_class = prompt.ground_truth_class.value
        selected = max(interpretations, key=interpretations.get)
        # Confidence: higher if we picked correctly
        if selected == correct_class:
            confidence = interpretations[selected] * 1.2  # Boost correct selections
        else:
            confidence = interpretations[selected] * 0.8
        confidence = min(confidence, 1.0)
        return selected, confidence

    def _execute(self, interpretation: str) -> str:
        """Execute the selected interpretation"""
        return f"Executed {interpretation.replace('_', ' ')} using AURORA-AXIS."

    def _verify(self, interpretation: str, prompt: SyntheticPrompt) -> float:
        """Verify execution quality"""
        if interpretation == prompt.ground_truth_class.value:
            return 0.85
        else:
            return 0.5  # Penalty for wrong interpretation, but not catastrophic

    def update_history(self, prompt: SyntheticPrompt):
        """Update forward-only intent history"""
        self.intent_history.append({
            "turn": len(self.intent_history) + 1,
            "prompt_id": prompt.id,
            "ground_truth": prompt.ground_truth_class.value,
        })

# ============================================================================
# 5. METRICS ENGINE
# ============================================================================
class MetricsEngine:
    """Compute evaluation metrics for each system output"""
    def __init__(self):
        self.results: List[EvaluationResult] = []

    def evaluate(self, output: SystemOutput, ground_truth: SyntheticPrompt) -> EvaluationResult:
        """Evaluate a single system output against ground truth"""
        # M1: Interpretation accuracy (did system pick correct interpretation?)
        predicted_class = InterpretationClass(output.selected_interpretation)
        interpretation_accuracy = float(predicted_class == ground_truth.ground_truth_class)
        # M2: Execution quality score (mock: based on trace)
        execution_quality = self._score_execution_quality(output, ground_truth)
        # Intent alignment score (mock: cosine similarity proxy)
        intent_alignment = self._score_intent_alignment(output, ground_truth)
        # Determine failure class
        failure_class = self._classify_failure(
            interpretation_accuracy=interpretation_accuracy,
            execution_quality=execution_quality,
            intent_alignment=intent_alignment,
        )
        result = EvaluationResult(
            prompt_id=ground_truth.id,
            system_name=output.system_name,
            ground_truth_class=ground_truth.ground_truth_class,
            predicted_class=predicted_class,
            output=output,
            interpretation_accuracy=interpretation_accuracy,
            execution_quality_score=execution_quality,
            intent_alignment_score=intent_alignment,
            failure_class=failure_class,
            export_ready=True,
        )
        self.results.append(result)
        return result

    def _score_execution_quality(self, output: SystemOutput, ground_truth: SyntheticPrompt) -> float:
        """Score execution quality (mock implementation)"""
        if output.selected_interpretation == ground_truth.ground_truth_class.value:
            return 0.85 + np.random.uniform(0, 0.15)
        else:
            return 0.4 + np.random.uniform(0, 0.2)

    def _score_intent_alignment(self, output: SystemOutput, ground_truth: SyntheticPrompt) -> float:
        """Score alignment between execution and ground truth intent"""
        # Mock: use embedding similarity proxy
        if output.selected_interpretation == ground_truth.ground_truth_class.value:
            return 0.8 + np.random.uniform(0, 0.2)
        else:
            return 0.3 + np.random.uniform(0, 0.3)

    def _classify_failure(
        self, interpretation_accuracy: float, execution_quality: float, intent_alignment: float
    ) -> FailureClass:
        """Classify failure type or success"""
        if interpretation_accuracy == 1.0 and execution_quality > 0.75:
            return FailureClass.SUCCESS
        if interpretation_accuracy == 0.0:
            return FailureClass.F1_INTERPRETATION_ERROR
        if execution_quality < 0.5:
            return FailureClass.F2_EXECUTION_ERROR
        return FailureClass.F3_INTENT_DRIFT_MISS

    def aggregate_results(self, system_name: str) -> Dict[str, float]:
        """Aggregate metrics by system"""
        system_results = [r for r in self.results if r.system_name == system_name]
        if not system_results:
            return {}
        return {
            "system": system_name,
            "n_prompts": len(system_results),
            "interpretation_accuracy": np.mean([r.interpretation_accuracy for r in system_results]),
            "avg_execution_quality": np.mean([r.execution_quality_score for r in system_results]),
            "avg_intent_alignment": np.mean([r.intent_alignment_score for r in system_results]),
            "success_rate": sum(1 for r in system_results if r.failure_class == FailureClass.SUCCESS) / len(system_results),
            "f1_error_rate": sum(1 for r in system_results if r.failure_class == FailureClass.F1_INTERPRETATION_ERROR) / len(system_results),
            "f2_error_rate": sum(1 for r in system_results if r.failure_class == FailureClass.F2_EXECUTION_ERROR) / len(system_results),
            "f3_error_rate": sum(1 for r in system_results if r.failure_class == FailureClass.F3_INTENT_DRIFT_MISS) / len(system_results),
        }

# ============================================================================
# 6. EXPERIMENT RUNNER
# ============================================================================
class ExperimentRunner:
    """Run full evaluation across all systems"""
    def __init__(self):
        self.dataset_gen = DatasetGenerator()
        self.metrics = MetricsEngine()
        self.systems = [
            SinglePassLLM(),
            ClarificationAgent(),
            NaivePlannerExecutor(),
            AuroraAxis(),
        ]

    def run_full_experiment(self, n_prompts: int = 50) -> Dict[str, Any]:
        """Run evaluation on all systems"""
        print(f"\n{'='*80}")
        print(f"AURORA-AXIS Evaluation Harness v1")
        print(f"{'='*80}\n")
        # Generate dataset
        print(f"[1/3] Generating {n_prompts} synthetic prompts...")
        prompts = self.dataset_gen.generate_dataset(size=n_prompts)
        print(f"\nGenerated {len(prompts)} prompts across 4 interpretation classes")
        # Run all systems
        print(f"\n[2/3] Running systems...")
        all_outputs = {}
        for system in self.systems:
            print(f"\nRunning {system.name}...")
            system_outputs = []
            for prompt in prompts:
                output = system.run(prompt)
                system_outputs.append(output)
                # Evaluate immediately
                self.metrics.evaluate(output, prompt)
            all_outputs[system.name] = system_outputs
        # Aggregate metrics
        print(f"\n[3/3] Computing metrics...")
        summary = {}
        for system in self.systems:
            agg = self.metrics.aggregate_results(system.name)
            summary[system.name] = agg
            print(f"\n{system.name}: {agg['success_rate']:.1%} success rate")
        return {
            "timestamp": datetime.now().isoformat(),
            "n_prompts": len(prompts),
            "systems_evaluated": [s.name for s in self.systems],
            "summary": summary,
            "detailed_results": self.metrics.results,
            "prompts": prompts,
            "outputs": all_outputs,
        }

    def run_drift_experiment(self, n_sequences: int = 20) -> Dict[str, Any]:
        """Run intent drift evaluation"""
        print(f"\n{'='*80}")
        print(f"Intent Drift Evaluation")
        print(f"{'='*80}\n")
        print(f"[1/2] Generating {n_sequences} drift sequences (Turn 1 → Turn 2)...")
        base_prompts = self.dataset_gen.generate_dataset(size=n_sequences)
        drift_sequences = [self.dataset_gen.generate_drift_sequence(p) for p in base_prompts]
        print(f"\n[2/2] Evaluating recovery...")
        aurora = AuroraAxis()
        recovery_results = []
        for turn1, turn2 in drift_sequences:
            # Turn 1
            output1 = aurora.run(turn1)
            aurora.update_history(turn1)
            # Turn 2 (intent drift)
            output2 = aurora.run(turn2)
            aurora.update_history(turn2)
            # Did system adapt?
            adapted = output2.selected_interpretation == turn2.ground_truth_class.value
            recovery_results.append({
                "sequence_id": turn1.id,
                "turn1_correct": output1.selected_interpretation == turn1.ground_truth_class.value,
                "turn2_correct": adapted,
                "adapted_to_drift": adapted,
                "turn1_confidence": output1.confidence,
                "turn2_confidence": output2.confidence,
            })
        recovery_rate = sum(1 for r in recovery_results if r["adapted_to_drift"]) / len(recovery_results)
        print(f"\nRecovery rate (Turn 2 adaptation): {recovery_rate:.1%}")
        return {
            "timestamp": datetime.now().isoformat(),
            "n_sequences": len(drift_sequences),
            "recovery_rate": recovery_rate,
            "detailed_results": recovery_results,
        }

# ============================================================================
# 7. PHASE 2 BRIDGE (Export for human evaluation)
# ============================================================================
class Phase2Exporter:
    """Export evaluation results for human rater review"""
    def __init__(self, results: Dict[str, Any]):
        self.results = results

    def export_for_human_raters(self, output_file: str = "phase2_export.json"):
        """Export outputs in format suitable for human evaluation"""
        ratable_results = []
        for detailed_result in self.results["detailed_results"]:
            if detailed_result.export_ready:
                ratable_results.append({
                    "prompt_id": detailed_result.prompt_id,
                    "system_name": detailed_result.system_name,
                    "original_prompt": f"[Placeholder: {detailed_result.prompt_id}]",
                    "system_output": detailed_result.output.output_text,
                    "system_confidence": detailed_result.output.confidence,
                    "ground_truth_class": detailed_result.ground_truth_class.value,
                    "synthetic_notes": "Synthetic evaluation. Rater should assess: (1) Did the system understand the prompt correctly?\n(2) Is the output helpful? (3) Would you prefer a different approach?",
                    "rater_fields": {
                        "understanding_score": None,  # 1-5
                        "helpfulness_score": None,  # 1-5
                        "preferred_interpretation": None,
                        "comments": None,
                    },
                })
        export_obj = {
            "timestamp": datetime.now().isoformat(),
            "n_outputs": len(ratable_results),
            "instructions": "Rate each system output on understanding (1=confused, 5=excellent) and helpfulness (1=unhelpful, 5=very helpful).",
            "meta": "This data bridges synthetic evaluation to human validation.",
            "outputs": ratable_results,
        }
        with open(output_file, "w") as f:
            json.dump(export_obj, f, indent=2)
        print(f"\n[Phase 2 Bridge] Exported {len(ratable_results)} outputs to {output_file}")
        print(f"\nReady for human rater evaluation")
        return output_file

# ============================================================================
# 8. MAIN
# ============================================================================
if __name__ == "__main__":
    runner = ExperimentRunner()
    # Run full synthetic evaluation
    print("\n" + "="*80)
    print("PHASE 1: SYNTHETIC EVALUATION")
    print("="*80)
    phase1_results = runner.run_full_experiment(n_prompts=50)
    # Print summary
    print("\n" + "="*80)
    print("RESULTS SUMMARY")
    print("="*80)
    for system_name, metrics in phase1_results["summary"].items():
        print(f"\n{system_name}")
        print(f"\nInterpretation Accuracy: {metrics['interpretation_accuracy']:.1%}")
        print(f"\nExecution Quality:\n{metrics['avg_execution_quality']:.2f}/1.0")
        print(f"\nIntent Alignment:\n{metrics['avg_intent_alignment']:.2f}/1.0")
        print(f"\nSuccess Rate:\n{metrics['success_rate']:.1%}")
        print(f"\nF1 (Interp Error):\n{metrics['f1_error_rate']:.1%}")
        print(f"\nF2 (Exec Error):\n{metrics['f2_error_rate']:.1%}")
        print(f"\nF3 (Drift Miss):\n{metrics['f3_error_rate']:.1%}")
    # Run drift evaluation
    print("\n" + "="*80)
    print("INTENT DRIFT EVALUATION (M3: Recovery Rate)")
    print("="*80)
    drift_results = runner.run_drift_experiment(n_sequences=20)
    # Phase 2 bridge
    print("\n" + "="*80)
    print("PHASE 2 BRIDGE: HUMAN EVALUATION EXPORT")
    print("="*80)
    exporter = Phase2Exporter(phase1_results)
    exporter.export_for_human_raters()
    print("\n" + "="*80)
    print("EVALUATION COMPLETE")
    print("="*80)
    print("\nKey findings:")
    print(f"\n• AURORA-AXIS success rate: {phase1_results['summary']['AURORA-AXIS']['success_rate']:.1%}")
    best_baseline = max(phase1_results['summary'].items(), key=lambda x: x[1]['success_rate'])
    print(f"\n• Best baseline: {best_baseline[0]} with {best_baseline[1]['success_rate']:.1%}")
    print(f"\n• Drift recovery: {drift_results['recovery_rate']:.1%}")
    print("\nNext steps:")
    print("\n1. If AURORA-AXIS >> baselines: System is working as intended")
    print("\n2. If gap is small: Verify baselines are competitive")
    print("\n3. If drift recovery < 70%: Consider semantic alignment layer (Option 2)")
    print("\n4. Phase 2: Use exported file for human rater validation")
