# AURORA-AXIS Evaluation Harness — Summary

## Source
Extracted from `update/aurora_harness.pdf` (772 lines PDF) via `pdftotext`.

## What It Is
A synthetic evaluation framework for testing **multi-intent reasoning under ambiguity**.
It benchmarks AI systems that must interpret ambiguous user prompts across four
interpretation classes:

1. **statistical_analysis** — Analyze datasets for patterns
2. **trend_forecasting** — Predict trajectories over time
3. **anomaly_detection** — Identify outliers and unexpected patterns
4. **root_cause_analysis** — Determine underlying causes

## Architecture
The harness is structured in 8 sections:

| Section | Description |
|---------|-------------|
| 1. Data Structures | Enums and dataclasses for prompts, outputs, and evaluation results |
| 2. Dataset Generator | Generates 50 synthetic prompts across 4 classes with controlled ambiguity |
| 3. Baseline Systems | 3 baselines: SinglePassLLM, ClarificationAgent, NaivePlannerExecutor |
| 4. AURORA-AXIS | The target system: Planner → Selector → Executor → Verifier pipeline |
| 5. Metrics Engine | Computes interpretation accuracy, execution quality, intent alignment, failure classification |
| 6. Experiment Runner | Runs full evaluation across all systems + drift recovery experiments |
| 7. Phase 2 Bridge | Exports results for human rater evaluation |
| 8. Main | Orchestrates synthetic evaluation → drift testing → human export |

## Baselines vs AURORA-AXIS
- **SinglePassLLM**: Keyword-based interpretation, no structure
- **ClarificationAgent**: Flags ambiguity but defaults to statistical_analysis
- **NaivePlannerExecutor**: Generates interpretations without verification
- **AuroraAxis**: Full pipeline with planner, selector, executor, verifier

## Key Metrics
- Interpretation accuracy (correct class selection)
- Execution quality score (0-1)
- Intent alignment score (0-1)
- Failure rates: F1 (interpolation), F2 (execution), F3 (drift)
- Drift recovery rate (Turn 2 adaptation after intent shift)

## Dependencies
- Python 3.8+
- numpy (for scoring functions)
- No external LLM required (all systems are simulated)

## Usage
```bash
cd harness
python aurora_harness.py          # Run full evaluation
python aurora_analysis.py results.json  # Analyze results
```

## Files
- `aurora_harness.py` — The harness itself (cleaned from PDF)
- `aurora_analysis.py` — Standalone analysis script for results

## Notes
- The PDF extraction had significant formatting artifacts (page breaks, line wraps)
- All fixes were applied to produce valid, compilable Python
- The harness is designed to run without GPU or LLM dependencies
- Phase 2 export creates `phase2_export.json` for human rater review
