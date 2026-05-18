# Lumen Safety-Gated, Governed Inference

Lumen is a safety-gated inference microservice backed by an epistemic belief-graph
memory system (Weaver-ASI). It routes user prompts through a multi-layer safety
pipeline (keyword > embedding classifier > CartPole-like control filter > chronicle)
\nbefore allowing generation.

## Directory Structure
```
lumen_core/           # inference microservice (Flask)
lumen_service.py    # main API
guardian_service.py # standalone safety guard
decision_engine.py  # weighted signal scoring
safety_filter.py    # CartPole safety filter (control)
safety_classifier.py# embedding-based safety
inference_pipeline.py # end-to-end chat pipeline
auth.py             # API key auth
kernel_controller.py# hardware-aware control (stub)
Weaver_ASI/           # epistemic memory & governance
core/
chronicle.py      # append-only WORM event log
aegis_kernel.py   # execution engine
epistemics/
epistemic_graph.py# belief graph with contradiction detection
arbitration.py    # conflict resolution
memory/
memory_governor.py# stratum assignment & decay
decay_models.py   # temporal decay curves
council/
governed_council.py# consensus deliberation
constitutional/
constitutional_kernel.py # violation checker
vault/                # plugin management
vault.py
tests/                # unit & integration tests
```

## Quick Start
1. Clone the repo.
2. Install dependencies: `pip install -r requirements.txt`
3. Set an API key: `export LUMEN_API_KEY=your-secret-key`
4. Start the service: `cd lumen_core && python lumen_service.py`
5. In another terminal, test:
```bash
curl -X POST http://localhost:5100/infer \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Explain the Riemann hypothesis."}'}
```

6. Check the chronicle: `cat /tmp/chronicle.jsonl`

## Security Model

* All API endpoints require a valid API key (`X-API-Key` header).
* Input prompts scanned by embedding-classification/keyword fallback.
* SHA-linked-events-specific saf....end?<!--questions]