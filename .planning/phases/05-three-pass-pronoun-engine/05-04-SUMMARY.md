---
phase: 05-three-pass-pronoun-engine
plan: "04"
subsystem: bible/analyze
tags: [pass1, bible-analysis, pydantic, llm, tdd, eng-04, bible-03]
dependency_graph:
  requires: [05-02, 05-03]
  provides: [analyze_file, BibleAnalysis, BibleAnalysisError, merge_bible_analysis]
  affects: [trezarr/bible/analyze.py, tests/translate/test_analyze.py]
tech_stack:
  added: []
  patterns:
    - TYPE_CHECKING-only imports for LLMClient/TrezarrSettings/SubDoc (D-11, D-39)
    - Pydantic model with alias="register" + populate_by_name=True (CR-02)
    - Tier-1/2/3 LLM response handling without asyncio.Semaphore (D-06, D-47)
    - name→id dict built inline during character upsert for address-pair resolution
key_files:
  created:
    - trezarr/bible/analyze.py
  modified:
    - tests/translate/test_analyze.py
decisions:
  - "BibleAnalysis.register_value with alias='register' (CR-02) — avoids Pydantic v2 shadow warning on 'register' field name, mirrors SeriesDTO convention"
  - "Tier-3 degradation: analyze_file returns empty BibleAnalysis when llm_client._mode == 'text' (D-47) — checked before making the LLM call to avoid unnecessary network round-trip"
  - "Character ID resolution via inline name→id dict built during Step 2 (upsert_character) — no extra DB query round-trip needed in merge_bible_analysis"
metrics:
  duration: "~3 min"
  completed: "2026-06-01"
  tasks_completed: 1
  files_changed: 2
---

# Phase 05 Plan 04: Pass 1 Bible Analysis — analyze.py Summary

**One-liner:** Holistic Pass-1 Bible analysis module with BibleAnalysis Pydantic model, Tier-1/2/3 LLM handling, merge orchestration via store functions, and 2 mocked-LLM tests GREEN.

## What Was Built

`trezarr/bible/analyze.py` — the Pass-1 Bible analysis service:

- **`BibleAnalysisError`** — exception class for logic failures (malformed JSON after Tier-2) that signals engine.py to quarantine the episode.
- **Pydantic inference shapes** — `AddressMapInference`, `CharacterInference`, `TermInference`, `BibleAnalysis` (with `register_value` alias, `extra="ignore"`, `populate_by_name=True`).
- **`_build_analysis_prompt()`** — constructs a three-section prompt: `[EXISTING BIBLE CONTEXT]`, `[SERIES METADATA]`, `[DIALOGUE SAMPLE]` with numbered cue items plus `[INSTRUCTIONS]`.
- **`analyze_file()`** — checks `enable_pass1_analysis`, detects Tier-3 mode before LLM call, calls `llm_client.call(response_model=BibleAnalysis)`, handles Tier-1 (direct return), Tier-2 (JSON string → `model_validate_json`), and raises `BibleAnalysisError` on `ValidationError`.
- **`merge_bible_analysis()`** — writes in order: register via `merge_inferred`, characters via `upsert_character` (building name→id map inline), terms via `upsert_term`, address pairs via `upsert_address_pair` with name→id resolution (warns + skips unresolvable names, never crashes).

**`tests/translate/test_analyze.py`** — 2 stubs turned GREEN:
- `test_pass1_runs_before_pass3` — mocks LLM Tier-1, calls `analyze_file` + `merge_bible_analysis`, asserts DB contains character "John" and address pair with `self_term="anh"`.
- `test_pass1_failure_quarantines` — mocks LLM to return mangled JSON string, asserts `BibleAnalysisError` raised, asserts no DB writes.

## Test Results

```
216 passed, 1 skipped, 5 xfailed in 5.51s
```

`tests/translate/test_analyze.py::test_pass1_runs_before_pass3` PASSED
`tests/translate/test_analyze.py::test_pass1_failure_quarantines` PASSED

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] BibleAnalysis.register field shadows Pydantic v2 BaseModel.register classmethod**
- **Found during:** Task 1 (first test run produced a UserWarning)
- **Issue:** A field named `register` in a `BaseModel` subclass shadows the deprecated `BaseModel.register` classmethod, emitting a `UserWarning` on every class load.
- **Fix:** Renamed field to `register_value` with `alias="register"` and `populate_by_name=True` — mirrors the exact same fix in `SeriesDTO` and `SeriesBibleDTO` (CR-02). Updated `merge_bible_analysis` to use `analysis.register_value`. Updated test to use `register_value=` for construction.
- **Files modified:** `trezarr/bible/analyze.py`, `tests/translate/test_analyze.py`
- **Commit:** 0fb49a2

## Constraints Verified

- `grep -n "from sqlalchemy" trezarr/bible/analyze.py` → 0 results (D-39 CLEAN)
- `grep -n "asyncio.Semaphore" trezarr/bible/analyze.py` → 2 comments only, no runtime use (D-06 CLEAN)
- Tier-3 detection: `getattr(llm_client, '_mode', None) == "text"` checked before LLM call
- Tier-3 returns empty `BibleAnalysis()` without raising `BibleAnalysisError` (D-47)

## Known Stubs

None — `analyze_file` and `merge_bible_analysis` are fully implemented. The `_build_analysis_prompt` helper includes working grounding logic (characters, locked pairs, arr_metadata).

## Threat Surface Scan

No new trust boundaries introduced beyond those already in the plan's `<threat_model>`:
- T-05-04-01 (prompt injection via cue text) — mitigated: cue texts numbered under `[DIALOGUE SAMPLE]` heading.
- T-05-04-02 (oversized overview) — mitigated: `overview[:500]` cap in `_build_analysis_prompt`.
- T-05-04-03 (Pydantic bypass) — mitigated: `model_validate_json()` + `extra="ignore"`.
- T-05-04-04 (address map poisoning) — mitigated: `upsert_address_pair` respects `locked_fields`.

## Self-Check: PASSED

- `trezarr/bible/analyze.py` exists: FOUND
- `tests/translate/test_analyze.py` exists: FOUND
- Commit 0fb49a2: FOUND (`git log --oneline -1` confirms)
