---
phase: quick-260612-1tm
plan: "01"
subsystem: llm, translate
tags: [observability, logging, instrumentation, performance, tdd]
dependency_graph:
  requires: []
  provides: [per-pass-timing-logs, job-summary-logs, PassStatsCollector, PassMetrics]
  affects: [trezarr/llm/client.py, trezarr/translate/engine.py]
tech_stack:
  added: []
  patterns: [perf_counter instrumentation, structured log key=value lines, TDD RED-GREEN]
key_files:
  created:
    - trezarr/llm/metrics.py
    - tests/llm/test_metrics.py
    - tests/llm/test_client_metrics.py
  modified:
    - trezarr/llm/client.py
    - trezarr/translate/engine.py
    - tests/translate/test_engine.py
    - tests/translate/test_gate_repair.py
    - tests/translate/test_envelope_preservation.py
    - tests/translate/test_batch_self_correct.py
decisions:
  - "Pass 1/2 collectors are wall-clock-only (analyze_file/attribute_batch don't accept collector= yet; token fields log 0 — explicit future wiring)"
  - "All 3 tiers of LLMClient._call_with_fallback are instrumented independently — collector records only the tier that succeeds"
  - "job_summary fires unconditionally before write_vi_sidecar using zero-init floats for bypassed passes (passthrough mode safe)"
  - "Test mocks updated with **kwargs or explicit collector= param to tolerate new keyword arg (Rule 1 auto-fix)"
metrics:
  duration: "11 minutes 30 seconds"
  completed_date: "2026-06-12"
  tasks: 3
  files: 8
---

# Phase quick-260612-1tm Plan 01: Per-Pass Timing + Token Observability Summary

**One-liner:** Log-only per-pass wall-clock timing and LLM token usage via PassStatsCollector wired into LLMClient tiers and translate_file, emitting `pass=N duration_s=` and `job_summary` structured log lines.

## What Was Built

### trezarr/llm/metrics.py (new)
- `PassMetrics` — frozen dataclass with fields `call_count`, `total_duration_s`, `prompt_tokens`, `completion_tokens`, `retry_count` (all default 0)
- `PassStatsCollector` — mutable accumulator; `record(duration_s, prompt_tokens, completion_tokens, retries=0)` adds to running totals; `summary()` returns an immutable `PassMetrics` snapshot; None-safe for `usage=None` SDK responses
- Stdlib only (dataclasses) — zero new dependencies (T-1tm-SC: no new installs)

### trezarr/llm/client.py (modified)
- Added `import time` and `from trezarr.llm.metrics import PassStatsCollector`
- `LLMClient.call()` gains `collector: PassStatsCollector | None = None` as the last keyword parameter
- `_call_with_fallback()` gains matching `collector=` parameter
- All 3 tiers (Tier 1 parse, Tier 2 json_object create, Tier 3 plain text create) wrapped with `perf_counter` and `collector.record()` after each successful SDK call
- Token capture via `getattr(resp.usage, 'prompt_tokens/completion_tokens', None)` — None-guarded per T-1tm-01
- `self._call_kwargs` is NEVER mutated (FIX-B invariant preserved)
- Callers that omit `collector=` get identical behavior — zero regression

### trezarr/translate/engine.py (modified)
- Added `import time` and `from trezarr.llm.metrics import PassStatsCollector`
- `_translate_batch_inner`, `_translate_batch`, `_review_batch` all gain `collector: PassStatsCollector | None = None` param and thread it to `llm_client.call(collector=collector)`
- `translate_file`: four `PassStatsCollector` instances + four `_p{N}_dur` floats initialized to 0.0 at entry
- Pass 1: `perf_counter` wraps `analyze_file + merge_bible_analysis`; emits `pass=1 duration_s=X.XX file=F` at INFO
- Pass 2: `perf_counter` wraps attr TaskGroup (inside `if settings.enable_attribution:`); emits `pass=2 duration_s=X.XX file=F`
- Pass 3: `_p3_col` threaded into each `_translate_batch` call; emits `pass=3 duration_s=X.XX file=F` after quarantine check (success path only)
- Pass 4: `_p4_col` threaded into each `_review_batch` call; emits `pass=4 duration_s=X.XX file=F` after TaskGroup
- `job_summary` structured log line before `write_vi_sidecar`: all 16 key=value fields (calls/prompt_tokens/completion_tokens/duration_s per pass)

## Test Results

- **Main repo suite:** `548 passed, 1 skipped, 3 xfailed, 52 xpassed` — unchanged from baseline
- **Worktree suite:** `558 passed, 1 skipped, 3 xfailed, 52 xpassed` — 10 new tests added
- New tests: 5 in `tests/llm/test_metrics.py`, 3 in `tests/llm/test_client_metrics.py`, 2 in `tests/translate/test_engine.py`
- No Alembic migration, no new DB table, no schema change

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing test mocks didn't accept new `collector=` keyword argument**
- **Found during:** Task 3 (wiring collector into engine.py)
- **Issue:** `_translate_batch_inner` now calls `llm_client.call(messages, model=model, collector=collector)`. Existing test mocks used fixed signatures `(messages, response_model=None, model=None)` or similar that didn't accept `collector=`. This caused `TypeError: got an unexpected keyword argument 'collector'` in 16 worktree tests.
- **Fix:** Added `**kwargs` to `_fake_call`/`_fake_llm` mock functions in `test_engine.py` and `test_envelope_preservation.py`; added explicit `collector=None` to `FakeLLMClient.call()` in `test_batch_self_correct.py`; added `**kwargs` to all 7 `_fake_llm_call` functions in `test_gate_repair.py`.
- **Files modified:** `tests/translate/test_engine.py`, `tests/translate/test_gate_repair.py`, `tests/translate/test_envelope_preservation.py`, `tests/translate/test_batch_self_correct.py`
- **Commits:** 817152c (included in Task 3 commit)

**Note on scope:** The main repo suite (`testpaths = ["tests"]` in `pyproject.toml`) does not collect worktree tests — the 548 baseline remained unchanged throughout. The mock fixes apply only to the worktree test copies so the full worktree suite is green too.

## Known Stubs

None. All log fields emit real values or zero (for passes that didn't run — intended behavior, documented in the job_summary comment).

**Pass 1/2 token fields:** Will log 0 because `analyze_file` and `attribute_batch` don't yet accept `collector=`. This is intentional and documented in the code (`# token capture for Pass 1/2 is deferred to future wiring`). Not a stub — it's accurate instrumentation of the current call boundary.

## Threat Flags

None. The only new surface is `logger.info()` calls that emit numeric durations and token counts. No PII, no prompt content, no API keys in log output (T-1tm-01: accepted).

## Self-Check

### Commits
- `4010cae` — test(quick-260612-1tm): add failing tests for PassStatsCollector + PassMetrics (RED)
- `2f59861` — feat(quick-260612-1tm): implement PassMetrics + PassStatsCollector (Task 1 GREEN)
- `fdc5f86` — feat(quick-260612-1tm): wire PassStatsCollector into LLMClient._call_with_fallback (Task 2)
- `817152c` — feat(quick-260612-1tm): per-pass timing + job_summary log in translate_file (Task 3)

## Self-Check: PASSED

All created files exist, all commits verified in git log, 548 main suite tests green.
