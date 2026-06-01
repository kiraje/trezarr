---
phase: 05-three-pass-pronoun-engine
plan: "06"
subsystem: translate-engine
tags: [pronoun-engine, three-pass, cli-wiring, integration, pron02, pron03, eng04]
dependency_graph:
  requires: [05-04, 05-05]
  provides: [translate-file-3pass, derive-episode-key, pronoun-hints-prompt, cli-bible-wiring]
  affects: [trezarr/translate/engine.py, trezarr/cli.py, tests/translate/test_engine.py, tests/translate/test_pronoun_engine.py]
tech_stack:
  added: []
  patterns:
    - Pronoun hint injection in numbered-line translation prompt (D-46)
    - Three-pass flow in translate_file: BARRIER Pass 1 → gather Pass 2 → reconcile → pronoun hints Pass 3
    - episode key derivation from subtitle filename stem (D-49 Pitfall F)
    - name_to_char_id bridge for flat_attribution re-indexing (Pitfall E)
key_files:
  created: []
  modified:
    - trezarr/translate/engine.py
    - trezarr/cli.py
    - tests/translate/test_engine.py
    - tests/translate/test_pronoun_engine.py
    - tests/test_cli.py
decisions:
  - "derive_episode_key parses SxxExx from subtitle filename stem, not from media_item.episode_number (Pitfall F confirmed)"
  - "pronoun_hints param on build_translate_prompt uses default=None for backward compat — no existing callers broken"
  - "Tier-3 endpoint degrades gracefully through Pass 1 skip (text mode) + all-LOW Pass 2 attributions + mechanical Pass 3"
  - "Test Pass 3 mock responses use U+1E00-U+1EFF Vietnamese diacritics (ạ, ổ) to pass the 0.70 diacritic ratio gate"
metrics:
  duration: "15 min"
  completed: "2026-06-01"
  tasks: 2
  files: 5
---

# Phase 05 Plan 06: Pipeline Integration Summary

Three-pass pronoun engine wired end-to-end: `build_translate_prompt` extended with per-line pronoun hints (D-46), `translate_file` extended with the full Pass 1 BARRIER → Pass 2 gather → reconcile → Pass 3 hint-injection flow (D-48), `derive_episode_key` added (D-49), and `cli.py` translate loop updated to pass `eligible_item` and `session_factory` to `translate_file`.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Extend engine.py — pronoun hints + derive_episode_key + 3-pass flow | e3d713d | engine.py, test_engine.py, test_pronoun_engine.py |
| 2 | Wire cli.py translate loop + full suite green | 8aa6e58 | cli.py, test_cli.py |

## What Was Built

### Task 1: engine.py extension (e3d713d)

**`build_translate_prompt` (D-46):** Added `pronoun_hints: dict[int, tuple[str,str]] | None = None` parameter. When provided, hinted lines render as `[N] (speaker says: X; addresses as: Y) <text>`; unhinted lines render as `[N] <text>` (backward compatible, default None).

**`derive_episode_key` (D-49):** New module-level function. Parses `SxxExx` from subtitle filename stem using `re.search(r'S(\d{2,})E(\d{2,})', stem, re.IGNORECASE)`. Movies: `movie-<slug>`. Never accesses `media_item.episode_number` (Pitfall F).

**`_translate_batch` / `_translate_batch_inner`:** Extended with `pronoun_hints` parameter. The inner function forwards hints to `build_translate_prompt`.

**`translate_file` (D-48):** Extended with `eligible_item: EligibleItem | None = None` and `session_factory: async_sessionmaker[AsyncSession] | None = None`. When both provided and `settings.enable_pass1_analysis=True`:
1. `get_or_create_series` → `load_series_bible`
2. Pass 1 BARRIER: `analyze_file` + `merge_bible_analysis`; `BibleAnalysisError` → quarantine (Pitfall B: `openai.APIError` not caught)
3. Reload Bible
4. Pass 2: `asyncio.gather(attribute_batch(...) for b in batches)` → `flat_attributions`
5. `reconcile_attributions` → `resolved_map`
6. Build per-batch `pronoun_hints` via `name_to_char_id` bridge (Pitfall E re-indexing via `doc_offset`)
7. Pass 3: `asyncio.gather(_translate_batch(b, ..., per_batch_hints[i]) for i, b in enumerate(batches))`

No new `asyncio.Semaphore` added (D-06 / Pitfall A). All LLM calls go through `LLMClient._semaphore`.

**Tests turned GREEN:**
- `test_engine.py::test_pronoun_hint_in_prompt` — unit test for D-46 hint format
- `test_pronoun_engine.py::test_pronoun_hint_in_prompt` — xfail stub replaced
- `test_pronoun_engine.py::test_pronoun_consistency_within_episode` — golden-fixture end-to-end (6-cue SRT, mocked LLM, real SQLite session_factory, verifies status="done")
- `test_pronoun_engine.py::test_tier3_endpoint_degrades_gracefully` — Tier-3 mode completes without quarantine, writes valid .vi.srt

### Task 2: cli.py wiring (8aa6e58)

- `_run_pipeline_steps` extended with `session_factory=None` (default None for backward compat)
- `_run_once` call site updated: `_run_pipeline_steps(settings, ledger, media_roots, session_factory)`
- Translate loop call site updated: `translate_file(..., eligible_item=eligible_item, session_factory=session_factory)`
- `test_cli.py::test_run_once_end_to_end_smoke_with_temp_sqlite` `_fake_translate` mock updated to accept new keyword args

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_cli.py _fake_translate mock signature**
- **Found during:** Task 2 full suite run
- **Issue:** `_fake_translate(path, _settings, _llm, _ledger)` did not accept new `eligible_item` and `session_factory` keyword args passed by the updated cli.py translate loop
- **Fix:** Updated signature to `_fake_translate(path, _settings, _llm, _ledger, eligible_item=None, session_factory=None)`
- **Files modified:** tests/test_cli.py
- **Commit:** 8aa6e58

**2. [Rule 2 - Tests] Pass 3 mock responses needed proper VI diacritics**
- **Found during:** Task 1 — `test_pronoun_consistency_within_episode` failing with `diacritic ratio 0.50 < threshold 0.70`
- **Issue:** Initial mock Pass 3 response used "yêu", "cũng", "chúng" (U+00xx Latin Extended Basic, NOT in VN range U+1E00-U+1EFF), so only 3/6 lines passed the validate_subdoc gate
- **Fix:** Updated mock responses to include `ạ` (U+1EA1), `ổ` (U+1ED5), `ợ` (in Được U+1EE3) — all in VN diacritic range. Same fix applied to tier3 test.
- **Files modified:** tests/translate/test_pronoun_engine.py
- **Commit:** e3d713d

## Verification Results

```
uv run pytest -x -q
226 passed, 1 skipped, 1 warning in 5.21s
# 0 xfailed — all 3 Phase-5 stubs turned GREEN
```

```
uv run python -c "from trezarr.translate.engine import build_translate_prompt; ..."
OK

uv run python -c "from trezarr.translate.engine import derive_episode_key; ..."
OK (S01E03 parsed correctly from /media/Show.S01E03.en.srt)
```

Full 05-VALIDATION.md coverage: all 18 tests PASSED.

## Known Stubs

None. All stub tests from `test_pronoun_engine.py` are now real implementations.

## Threat Flags

None. All threat mitigations from the plan's STRIDE register are implemented:
- T-05-06-01: Pronoun hints derive from Address Map (ORM parameterized), not raw LLM text
- T-05-06-02: Only `BibleAnalysisError` caught in quarantine block; `openai.APIError` propagates
- T-05-06-03: `session_factory` scoped to `_run_once`; no new DB permissions
- T-05-06-04: No new `asyncio.Semaphore`; `LLMClient._semaphore` remains sole gate

## Self-Check: PASSED

- SUMMARY.md: FOUND at .planning/phases/05-three-pass-pronoun-engine/05-06-SUMMARY.md
- Commit e3d713d: FOUND (engine.py Task 1)
- Commit 8aa6e58: FOUND (cli.py Task 2)
- All 226 tests passing, 0 xfailed
