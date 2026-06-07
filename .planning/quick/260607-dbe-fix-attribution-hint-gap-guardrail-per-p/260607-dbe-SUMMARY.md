---
phase: quick-260607-dbe
plan: "01"
subsystem: translate-pipeline
tags: [fix, attribution, thinking, guardrail, pronoun-engine, llm-client]
dependency_graph:
  requires: []
  provides:
    - "per-call thinking override on LLMClient.call()"
    - "unhinted-line guardrail RULE in build_translate_prompt"
    - "thinking kwarg threaded into Pass-1 and Pass-2"
  affects:
    - trezarr/llm/client.py
    - trezarr/config.py
    - trezarr/translate/engine.py
    - trezarr/translate/attribute.py
    - trezarr/bible/analyze.py
tech_stack:
  added: []
  patterns:
    - "per-call effective_call_kwargs local variable (no mutation of self._call_kwargs)"
    - "register-aware pronoun guardrail in Pass-3 prompt"
key_files:
  created:
    - tests/llm/test_client_thinking.py (extended with 7 new per-call tests)
  modified:
    - trezarr/config.py
    - trezarr/llm/client.py
    - trezarr/translate/engine.py
    - trezarr/translate/attribute.py
    - trezarr/bible/analyze.py
    - tests/translate/test_engine.py
    - tests/translate/test_attribute.py
    - tests/bible/test_analyze.py
    - tests/translate/test_pronoun_engine.py
decisions:
  - "FIX-B uses effective_call_kwargs as a local per-call variable (T-dbe-01 mitigation); self._call_kwargs never mutated"
  - "Classical register detection in guardrail rule uses same keywords as existing register RULE block"
  - "_make_settings() in test_attribute.py extended with enable_reasoning_attribution to maintain fixture consistency"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-07T02:48:17Z"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 9
---

# Phase quick-260607-dbe Plan 01: Attribution Hint Gap + Guardrail + Per-Pass Reasoning Summary

**One-liner:** Per-call thinking override on LLMClient (FIX-B) + register-aware unhinted-line guardrail in Pass-3 prompt (FIX-A) + thinking threaded into Pass-1/Pass-2 call sites.

## What Was Built

### FIX-B — Per-call thinking override in LLMClient + new config knobs

Added `thinking: bool | None = None` to `LLMClient.call()` and `_call_with_fallback()`.

Logic:
- `thinking=True` → `effective_call_kwargs = {"extra_body": {"thinking": {"type": "enabled"}}, "reasoning_effort": self._reasoning_effort}`
- `thinking=False` → `effective_call_kwargs = {"extra_body": {"thinking": {"type": "disabled"}}}`
- `thinking=None` → `effective_call_kwargs = self._call_kwargs` (zero regression for existing callers)

`effective_call_kwargs` is a **local variable per call** — `self._call_kwargs` is never mutated (T-dbe-01 mitigation). `self._reasoning_effort` is stored once in `__init__` from `settings.llm_reasoning_effort`.

Three new config fields in `TrezarrSettings`:
- `enable_reasoning_analysis: bool = True` — gates Pass-1 thinking
- `enable_reasoning_attribution: bool = True` — gates Pass-2 thinking
- `llm_reasoning_effort: str = "high"` — DeepSeek reasoning_effort value when thinking is forced enabled

### FIX-A — Unhinted-line guardrail RULE in build_translate_prompt

Added a new numbered RULE after the mixed-gender plural rule in `build_translate_prompt()`:

> For any line WITHOUT a (speaker says / addresses as) hint: render English 'you/your/yourself' as a register-appropriate 2nd-person Vietnamese pronoun — NEVER substitute a character name. Use {pronoun_examples}.

The `_is_classical` check uses the same keywords as the existing register RULE block (classical, historical, wuxia, xianxia, cultivation, cổ trang, tiên hiệp, kiếm hiệp). Classical registers get `ngươi or các hạ`; modern gets `anh, em, or bạn`. `rule_n` is incremented correctly so numbering stays sequential.

### Threading into Pass-1 and Pass-2

- `attribute.py` → `llm_client.call(..., thinking=settings.enable_reasoning_attribution)`
- `analyze.py` → `llm_client.call(..., thinking=settings.enable_reasoning_analysis)` inside `_analyze_one_chunk()`
- `_translate_batch` and `_review_batch` in `engine.py` are **untouched** (confirmed by grep — zero occurrences of `thinking` in engine.py)

## Commits

| Hash | Type | Description |
|------|------|-------------|
| cee1204 | test (RED) | Add failing tests for per-call thinking override + config knobs |
| 802d03a | feat (GREEN) | Per-call thinking override in LLMClient + new config knobs |
| e4897c1 | test (RED) | Add failing tests for unhinted-line guardrail in build_translate_prompt |
| 3f1d2bf | feat (GREEN) | Unhinted-line guardrail RULE in build_translate_prompt |
| ee80a79 | feat | Thread thinking kwarg into Pass-1 and Pass-2; fix mock signatures |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing mock LLM call helpers didn't accept `thinking=` kwarg**

- **Found during:** Task 3 — full suite run
- **Issue:** `mock_llm_call()` in `test_engine.py` (test_merge_bible_analysis_called_with_settings_on_pass1_path) and `test_pronoun_engine.py` (test_pronoun_consistency_within_episode) had `(messages, response_model=None, model=None)` signatures. Once `thinking=` was added to attribute_batch/analyze_file calls, these mocks received an unexpected kwarg and raised `TypeError`.
- **Fix:** Added `**kwargs` to both mock function signatures with a comment documenting D-113 / FIX-B.
- **Files modified:** `tests/translate/test_engine.py`, `tests/translate/test_pronoun_engine.py`
- **Commit:** ee80a79

**2. [Rule 2 - Missing critical functionality] `_make_settings()` in test_attribute.py missing `enable_reasoning_attribution`**

- **Found during:** Task 3 — test run
- **Issue:** The existing `_make_settings()` helper in `test_attribute.py` built a `SimpleNamespace` without `enable_reasoning_attribution`, causing an `AttributeError` when `attribute_batch` accessed `settings.enable_reasoning_attribution`.
- **Fix:** Added `enable_reasoning_attribution: bool = True` parameter to `_make_settings()`.
- **Files modified:** `tests/translate/test_attribute.py`
- **Commit:** ee80a79

## Test Results

Full suite: **466 passed**, 1 skipped, 3 xfailed, 52 xpassed (previously ~451 before this fix series).

New tests added:
- 7 in `tests/llm/test_client_thinking.py` (per-call override + config defaults)
- 5 in `tests/translate/test_engine.py` (guardrail rules — classical/modern/sequential)
- 2 in `tests/translate/test_attribute.py` (thinking kwarg threading)
- 1 in `tests/bible/test_analyze.py` (thinking kwarg threading)

## Verification Checklist

- [x] `python -m pytest tests/llm/test_client_thinking.py -x -q` — 12 passed
- [x] `python -m pytest tests/translate/test_engine.py -x -q` — 29 passed, 1 xpassed
- [x] `python -m pytest tests/translate/test_attribute.py tests/bible/test_analyze.py -x -q` — 13 passed
- [x] `python -m pytest tests/ -q` — 466 passed (full suite green)
- [x] `grep -n "thinking" trezarr/translate/engine.py` — 0 matches (no thinking in _translate_batch/_review_batch)

## Known Stubs

None — all changes are fully wired.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes. The `effective_call_kwargs` local variable pattern (T-dbe-01 mitigate) is implemented correctly with no mutation of `self._call_kwargs`.

## Self-Check: PASSED

All key files exist and all commits verified in git log.
