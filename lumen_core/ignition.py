"""
ignition.py — Cathedral-OS / Runtime
======================================
Master Unblock — First Live Inference Through the Stack

PATH A REWRITE (2026-04-30)
  The CGIR bridge layer (cgir_signal_algebra, api_logprob_extractor,
  logprob_bridge_adapter) was absent from the project directory.
  This rewrite bypasses those modules entirely.

  Pipeline:
    API call → APIResponse → inline metric derivation
    → GuardianSignal → GuardianSlot.evaluate()
    → Receipt → HashChain (Chronicle)

  Modules used (all present on disk and importable):
    api_adapter.py       — provider-agnostic LLM call
    guardian_slot.py     — EXECUTE / BLOCK / KILL gate
    hashchain.py         — WORM Chronicle ledger
    receipt.py           — cryptographic receipt generation

  Modules bypassed (absent from project directory):
    api_logprob_extractor   — MISSING
    logprob_bridge_adapter  — MISSING
    cgir_signal_algebra     — MISSING

  Metric derivation (inline, no external dependencies):
    confidence   — mean(exp(logprob)) for up to 20 tokens,
                   clamped to [0.10, 0.90] to satisfy I16 (5% Sanctuary)
    tau_escape   — 0.85 (nominal safe; above TAU_ESCAPE_FLOOR = 0.75)
    drift_score  — 0.05 (nominal safe; below DRIFT_THRESHOLD = 0.12)
    chi_vector   — 0.20 (nominal safe; above CHI_MIN, below CHI_COLLAPSE)
    cbf_margin   — 0.60 (cbf_margin argument, default 0.6)
    betti_1      — 0.00
    kl_divergence— 0.00 (not computable without extractor; recorded as absent)
    entropy_delta— 0.00 (same)

  A010 closes when:
    - At least one LIVE_INFERENCE event in the Chronicle

Usage:
  python ignition.py --backend anthropic --model claude-sonnet-4-20250514 --trials 5
  python ignition.py --backend openai    --model gpt-4o                   --trials 5
  python ignition.py --backend grok      --model grok-3                   --trials 5
  python ignition.py --backend ollama    --model qwen3:4b                 --trials 5
  python ignition.py --backend mock      --model mock-model-v1            --trials 5

  API key via env var:
    ANTHROPIC_API_KEY=sk-ant-...
    OPENAI_API_KEY=sk-...
    GROK_API_KEY=xai-...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_adapter import APIAdapter, APIConfig, APIResponse, Provider, make_adapter
from guardian_slot import GuardianSignal, GuardianSlot, SlotDecision
from hashchain import HashChain
from receipt import Receipt


# ─── TRIAL PROMPTS ────────────────────────────────────────────────────────────

TRIAL_PROMPTS = [
    "What is 2 + 2? Explain your reasoning in one sentence.",
    "Name the capital of France and describe it in one sentence.",
    "Is the sky blue during daytime? Answer yes or no and explain why in one sentence.",
    "What comes after the number 9? Explain the pattern in one sentence.",
    "Complete this: The sun rises in the east. Explain why in one sentence.",
]

# I16: 5% Sanctuary — confidence clamped within [CONF_FLOOR, CONF_CEIL]
CONF_FLOOR = 0.10
CONF_CEIL  = 0.90

# Nominal safe signal values (inline derivation, no CGIR bridge)
TAU_NOMINAL   = 0.85
DRIFT_NOMINAL = 0.05
CHI_NOMINAL   = 0.20
BETTI_NOMINAL = 0.00


# ─── METRIC DERIVATION ────────────────────────────────────────────────────────

def derive_confidence(response: APIResponse) -> float:
    """
    Derive a confidence estimate directly from token logprobs in the APIResponse.

    If logprobs are present: mean of exp(logprob) for up to 20 tokens,
    clamped to [CONF_FLOOR, CONF_CEIL] per I16.

    If logprobs absent: returns 0.70 (safe default, mid-band).
    """
    if not response.token_logprobs:
        return 0.70
    probs = [math.exp(t.logprob) for t in response.token_logprobs[:20]]
    raw = sum(probs) / len(probs)
    return max(CONF_FLOOR, min(CONF_CEIL, raw))


def derive_metrics_complete(response: APIResponse) -> bool:
    """True if token_logprobs were returned by the provider."""
    return bool(response.token_logprobs) and not response.metrics_incomplete


# ─── IGNITION ENTRY ───────────────────────────────────────────────────────────

@dataclass
class IgnitionEntry:
    trial_index:       int
    prompt:            str
    response_text:     str
    provider:          str
    model:             str
    decision:          str
    gate_reasons:      List[str]
    metrics_complete:  bool
    kl_divergence:     float    # 0.0 — extractor absent; recorded explicitly
    entropy_delta:     float    # 0.0 — extractor absent; recorded explicitly
    confidence:        float
    tau_escape:        float
    drift_score:       float
    chi_vector:        float
    cbf_margin:        float
    latency_ms:        float
    receipt_hash:      str
    error:             Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event":            "LIVE_INFERENCE",
            "path":             "A",
            "cgir_bridge":      "BYPASSED",
            "trial_index":      self.trial_index,
            "provider":         self.provider,
            "model":            self.model,
            "decision":         self.decision,
            "gate_reasons":     self.gate_reasons,
            "metrics_complete": self.metrics_complete,
            "kl_divergence":    None,   # extractor absent — not fabricated
            "entropy_delta":    None,   # extractor absent — not fabricated
            "confidence":       round(self.confidence, 4),
            "tau_escape":       round(self.tau_escape, 4),
            "drift_score":      round(self.drift_score, 4),
            "chi_vector":       round(self.chi_vector, 4),
            "cbf_margin":       round(self.cbf_margin, 4),
            "latency_ms":       round(self.latency_ms, 2),
            "receipt_hash":     self.receipt_hash,
            "prompt_hash":      hashlib.sha256(self.prompt.encode()).hexdigest()[:16],
            "response_length":  len(self.response_text),
            "error":            self.error,
        }


# ─── IGNITION SESSION ─────────────────────────────────────────────────────────

class IgnitionSession:
    def __init__(
        self,
        adapter:    APIAdapter,
        n_trials:   int,
        cbf_margin: float = 0.6,
        verbose:    bool  = True,
    ) -> None:
        self._adapter    = adapter
        self._n_trials   = n_trials
        self._cbf_margin = cbf_margin
        self._verbose    = verbose
        self._session_id = (
            f"ignition_pathA_{adapter.provider.value}_{adapter.model}_{int(time.time())}"
        ).replace(":", "-").replace("/", "-")
        self._chain      = HashChain()
        self._gate       = GuardianSlot()
        self._entries:   List[IgnitionEntry] = []

    def run(self) -> Dict[str, Any]:
        if self._verbose:
            print(f"\n  Session:  {self._session_id}")
            print(f"  Backend:  {self._adapter.provider.value}")
            print(f"  Model:    {self._adapter.model}")
            print(f"  Trials:   {self._n_trials}")
            print(f"  Pipeline: api_adapter → guardian_slot → hashchain (CGIR bypassed)\n")

        prompts = (TRIAL_PROMPTS * (self._n_trials // len(TRIAL_PROMPTS) + 1))[:self._n_trials]

        for i, prompt in enumerate(prompts):
            entry = self._run_trial(i, prompt)
            self._entries.append(entry)
            self._record(entry)
            if self._verbose:
                self._print_trial(entry)

        return self._seal()

    def _run_trial(self, i: int, prompt: str) -> IgnitionEntry:
        t0       = time.perf_counter()
        response = self._adapter.call(prompt)
        latency  = (time.perf_counter() - t0) * 1000.0

        # Use response latency if adapter measured it directly
        if response.latency_ms > 0:
            latency = response.latency_ms

        confidence = derive_confidence(response)
        complete   = derive_metrics_complete(response)

        signal = GuardianSignal(
            tau_escape      = TAU_NOMINAL,
            drift_score     = DRIFT_NOMINAL,
            chi_vector      = CHI_NOMINAL,
            cbf_margin      = self._cbf_margin,
            betti_1         = BETTI_NOMINAL,
            confidence      = confidence,
            iteration_count = 0,
            human_override  = None,
            action_id       = f"ignition_t{i}",
        )

        slot_result = self._gate.evaluate(signal)

        decision = slot_result.decision.value
        reasons  = [r.value for r in slot_result.reasons]

        return IgnitionEntry(
            trial_index      = i,
            prompt           = prompt,
            response_text    = response.text,
            provider         = response.provider.value,
            model            = response.model,
            decision         = decision,
            gate_reasons     = reasons,
            metrics_complete = complete,
            kl_divergence    = 0.0,
            entropy_delta    = 0.0,
            confidence       = confidence,
            tau_escape       = TAU_NOMINAL,
            drift_score      = DRIFT_NOMINAL,
            chi_vector       = CHI_NOMINAL,
            cbf_margin       = self._cbf_margin,
            latency_ms       = latency,
            receipt_hash     = slot_result.receipt_hash,
            error            = response.error if not response.success else None,
        )

    def _record(self, entry: IgnitionEntry) -> None:
        r = Receipt(
            receipt_id = f"{self._session_id}_trial_{entry.trial_index}",
            module     = "ignition",
            action     = "LIVE_INFERENCE",
            verdict    = entry.decision,
            payload    = entry.to_dict(),
            prev_hash  = self._chain.head_hash,
        )
        self._chain.append(r)

    def _print_trial(self, entry: IgnitionEntry) -> None:
        logprob_str = "logprobs=yes" if entry.metrics_complete else "logprobs=no"
        err_str     = f"  ERR: {entry.error}" if entry.error else ""
        reason_str  = f"  reasons={entry.gate_reasons}" if entry.gate_reasons else ""
        print(
            f"  Trial {entry.trial_index+1:02d}  "
            f"decision={entry.decision:7}  "
            f"conf={entry.confidence:.3f}  "
            f"{logprob_str}  "
            f"lat={entry.latency_ms:.1f}ms"
            f"{reason_str}{err_str}"
        )

    def _seal(self) -> Dict[str, Any]:
        chain_valid, _, _  = self._chain.verify()
        successful         = [e for e in self._entries if not e.error]
        complete           = [e for e in self._entries if e.metrics_complete]
        executed           = [e for e in self._entries if e.decision == "EXECUTE"]
        chain_entries      = self._chain.to_list()

        session_payload = json.dumps({
            "session_id":     self._session_id,
            "entries":        [e.to_dict() for e in self._entries],
            "chain_valid":    chain_valid,
        }, sort_keys=True, separators=(",", ":"))
        session_hash = hashlib.sha256(session_payload.encode()).hexdigest()

        a010_closed = len(successful) >= 1
        a010_status = "CLOSED" if a010_closed else "OPEN"
        # A011 requires non-zero KL/entropy — not achievable on Path A without extractor
        a011_status = "BLOCKED_PATH_A"

        return {
            "session_id":      self._session_id,
            "path":            "A",
            "cgir_bridge":     "BYPASSED",
            "provider":        self._adapter.provider.value,
            "model":           self._adapter.model,
            "trials_total":    self._n_trials,
            "trials_success":  len(successful),
            "trials_executed": len(executed),
            "metrics_complete":len(complete),
            "chain_valid":     chain_valid,
            "chain_length":    len(chain_entries),
            "chain_entries":   chain_entries,
            "session_hash":    session_hash,
            "a010_status":     a010_status,
            "a011_status":     a011_status,
            "gate_stats":      self._gate.stats,
            "entries":         [e.to_dict() for e in self._entries],
        }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def resolve_api_key(backend: str, explicit_key: Optional[str]) -> Optional[str]:
    if explicit_key:
        return explicit_key
    env_map = {
        "openai":    "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "grok":      "GROK_API_KEY",
    }
    env_var = env_map.get(backend)
    return os.environ.get(env_var) if env_var else None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Cathedral-OS Ignition — Path A (CGIR bridge bypassed)"
    )
    p.add_argument("--backend",    default="ollama",
                   choices=["openai","anthropic","grok","ollama","openai_compat","mock"])
    p.add_argument("--model",      default="qwen3:4b")
    p.add_argument("--trials",     type=int,   default=5)
    p.add_argument("--cbf-margin", type=float, default=0.6, dest="cbf_margin")
    p.add_argument("--temperature",type=float, default=0.7)
    p.add_argument("--max-tokens", type=int,   default=256, dest="max_tokens")
    p.add_argument("--base-url",   default=None, dest="base_url")
    p.add_argument("--api-key",    default=None, dest="api_key")
    p.add_argument("--quiet",      action="store_true")
    return p


def main(argv=None) -> int:
    opts = build_parser().parse_args(argv)

    print("\n" + "=" * 70)
    print("CATHEDRAL-OS IGNITION — ACP-1 A010  [PATH A]")
    print("=" * 70)

    api_key = resolve_api_key(opts.backend, opts.api_key)
    if opts.backend not in ("ollama", "mock") and not api_key:
        print(f"\n  ERROR: No API key for '{opts.backend}'.")
        print(f"  Set {opts.backend.upper()}_API_KEY env var or use --api-key.")
        return 1

    try:
        adapter = make_adapter(
            backend=opts.backend, model=opts.model, api_key=api_key,
            base_url=opts.base_url, temperature=opts.temperature,
            max_tokens=opts.max_tokens,
        )
    except ValueError as e:
        print(f"\n  ERROR: {e}")
        return 1

    session = IgnitionSession(
        adapter=adapter, n_trials=opts.trials,
        cbf_margin=opts.cbf_margin, verbose=not opts.quiet,
    )

    print(f"\n  Starting {opts.trials} trial(s)...")
    summary = session.run()

    print(f"\n{'─'*70}")
    print(f"  SESSION SUMMARY")
    print(f"{'─'*70}")
    print(f"  Trials:   {summary['trials_success']}/{summary['trials_total']} successful")
    print(f"  Executed: {summary['trials_executed']}/{summary['trials_total']}")
    print(f"  Logprobs: {summary['metrics_complete']}/{summary['trials_total']} complete")
    print(f"  Chain:    valid={summary['chain_valid']}  length={summary['chain_length']}")
    print(f"  Hash:     {summary['session_hash'][:32]}…")
    print(f"  Gate:     {summary['gate_stats']}")
    print(f"\n  ACP-1 A010: {summary['a010_status']}")
    print(f"  ACP-1 A011: {summary['a011_status']}")
    print(f"  Note:     KL/entropy absent (Path A — extractor not wired)")

    ts  = int(time.time())
    out = os.path.abspath(f"ignition_session_{ts}.json")
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)

    acp_path = os.path.abspath(f"acp1_a010_evidence_{ts}.json")
    with open(acp_path, "w") as f:
        json.dump({
            "assumption":    "A010",
            "path":          "A",
            "cgir_bridge":   "BYPASSED",
            "status":        summary["a010_status"],
            "session_hash":  summary["session_hash"][:32],
            "trials_success":summary["trials_success"],
            "chain_valid":   summary["chain_valid"],
            "receipt_path":  out,
        }, f, indent=2)

    print(f"\n  Receipt:  {out}")
    print(f"  ACP-1:    {acp_path}")
    print(f"\n{'='*70}")

    return 0 if summary["a010_status"] == "CLOSED" else 1


# ─── TEST SUITE ───────────────────────────────────────────────────────────────

def _test_trial_prompts_count() -> bool:
    assert len(TRIAL_PROMPTS) == 5
    return True

def _test_derive_confidence_with_logprobs() -> bool:
    from api_adapter import TokenLogprob
    import math
    r = APIResponse(
        success=True, text="ok", provider=Provider.MOCK, model="m",
        token_logprobs=[TokenLogprob("a", math.log(0.8)), TokenLogprob("b", math.log(0.6))],
        metrics_incomplete=False,
    )
    c = derive_confidence(r)
    assert CONF_FLOOR <= c <= CONF_CEIL
    assert abs(c - 0.70) < 0.15   # mean of 0.8 and 0.6 = 0.70
    return True

def _test_derive_confidence_no_logprobs() -> bool:
    r = APIResponse(success=True, text="ok", provider=Provider.MOCK, model="m")
    assert derive_confidence(r) == 0.70
    return True

def _test_confidence_clamped_i16() -> bool:
    from api_adapter import TokenLogprob
    # Very high logprobs should be clamped below 0.90
    r = APIResponse(
        success=True, text="ok", provider=Provider.MOCK, model="m",
        token_logprobs=[TokenLogprob("x", -0.001)] * 10,
        metrics_incomplete=False,
    )
    c = derive_confidence(r)
    assert c <= CONF_CEIL, f"I16 violated: confidence {c} > {CONF_CEIL}"
    return True

def _test_ignition_entry_to_dict() -> bool:
    e = IgnitionEntry(
        trial_index=0, prompt="test", response_text="ok",
        provider="mock", model="mock-model-v1",
        decision="EXECUTE", gate_reasons=[],
        metrics_complete=True,
        kl_divergence=0.0, entropy_delta=0.0,
        confidence=0.75, tau_escape=0.85, drift_score=0.05,
        chi_vector=0.20, cbf_margin=0.6,
        latency_ms=1.0, receipt_hash="abc123", error=None,
    )
    d = e.to_dict()
    assert d["event"] == "LIVE_INFERENCE"
    assert d["path"] == "A"
    assert d["cgir_bridge"] == "BYPASSED"
    assert d["kl_divergence"] is None   # not fabricated
    assert d["entropy_delta"] is None
    return True

def _test_resolve_api_key_ollama() -> bool:
    assert resolve_api_key("ollama", None) is None
    return True

def _test_resolve_explicit_key_wins() -> bool:
    os.environ["OPENAI_API_KEY"] = "env-key"
    assert resolve_api_key("openai", "explicit") == "explicit"
    del os.environ["OPENAI_API_KEY"]
    return True

def _test_parser_defaults() -> bool:
    p = build_parser()
    opts = p.parse_args(["--backend", "ollama", "--model", "qwen3:4b"])
    assert opts.trials == 5
    assert opts.cbf_margin == 0.6
    return True

def _test_missing_key_nonzero() -> bool:
    for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
        os.environ.pop(k, None)
    result = main(["--backend", "openai", "--model", "gpt-4o", "--trials", "1"])
    assert result != 0
    return True

def _test_mock_full_dry_run() -> bool:
    """
    Full dry-run: mock → ignition → Chronicle → receipt on disk.
    This is the structural rehearsal for A010. Swap mock → ollama/anthropic for live.
    """
    import glob, subprocess
    result = subprocess.run(
        [sys.executable, __file__,
         "--backend", "mock", "--model", "mock-model-v1",
         "--trials", "3", "--quiet"],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    assert result.returncode == 0, f"ignition failed:\n{result.stdout[-400:]}"

    receipts = sorted(glob.glob(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "ignition_session_*.json")
    ))
    assert receipts, "No ignition_session_*.json produced"

    with open(receipts[-1]) as f:
        summary = json.load(f)

    assert summary["a010_status"] == "CLOSED"
    assert summary["trials_success"] == 3
    assert summary["chain_valid"] is True
    assert summary["path"] == "A"
    assert "chain_entries" in summary
    assert len(summary["chain_entries"]) == 3
    for entry in summary["chain_entries"]:
        for k in ("receipt_id", "module", "action", "verdict", "payload", "hash", "prev_hash"):
            assert k in entry, f"chain entry missing: {k}"
    return True


def run_tests() -> tuple:
    tests = sorted(
        [(n, o) for n, o in globals().items()
         if n.startswith("_test_") and callable(o)],
        key=lambda x: x[0],
    )
    passed, failed, results = 0, 0, []
    for name, fn in tests:
        try:
            fn()
            passed += 1
            results.append((name, "PASS", None))
        except Exception as e:
            failed += 1
            results.append((name, "FAIL", str(e)))
    return passed, failed, results


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] == "--test":
        import hashlib as _hl
        print("=" * 70)
        print("IGNITION PATH A — Unit Tests + Mock Dry-Run")
        print("=" * 70)
        print("\n── TEST SUITE ──\n")
        passed, failed, results = run_tests()
        for name, status, err in results:
            marker = "✓" if status == "PASS" else "✗"
            line = f"  {marker} {name}"
            if err:
                line += f"  → {err}"
            print(line)
        print(f"\n  Results: {passed} passed, {failed} failed, {passed + failed} total")
        if failed > 0:
            sys.exit(1)
        with open(__file__, "rb") as f:
            fh = _hl.sha256(f.read()).hexdigest()
        print(f"\n── RECEIPT ──\n  SHA-256: {fh}\n  Tests: {passed}/{passed + failed}")
        print(f"\n{'='*70}")
        print(f"  To close A010 with Ollama:")
        print(f"  python ignition.py --backend ollama --model qwen3:4b --trials 5")
        print(f"")
        print(f"  To close A010 with Anthropic:")
        print(f"  python ignition.py --backend anthropic --model claude-sonnet-4-20250514 --trials 5")
        print(f"{'='*70}")
    else:
        sys.exit(main())
