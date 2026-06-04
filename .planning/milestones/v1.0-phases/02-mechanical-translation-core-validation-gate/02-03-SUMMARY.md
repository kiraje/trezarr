---
phase: "02"
plan: "03"
subsystem: "translate + output"
tags: [tdd, green-phase, engine, ledger, tenacity, numbered-line, quarantine, idempotency, ENG-02, ENG-03, ENG-06, ENG-07, FMT-05, D-12, D-13, D-14, D-15, D-16, D-17, D-18, D-19, D-20]
dependency_graph:
  requires:
    - "02-01"  # RED test suite (36 stubs in place)
    - "02-02"  # sentinel, batching, validate, write, config (pure-Python transforms)
    - "trezarr/llm/client.py"  # LLMClient.call() — the sole concurrency gate
    - "trezarr/subtitles/srt.py"  # read_srt() for source input
    - "trezarr/config.py"  # TrezarrSettings with Phase-2 fields
  provides:
    - "trezarr/translate/engine.py"
    - "trezarr/output/ledger.py"
    - "pyproject.toml (tenacity 9.1.4)"
  affects:
    - "Phase 03 (first vertical slice — calls translate_file() directly)"
    - "Phase 04 (Ledger interface contract — JSON backend swapped for SQLAlchemy)"
tech_stack:
  added:
    - "tenacity 9.1.4 (batch-level retry with exponential backoff, D-18)"
  patterns:
    - "@retry(retry=retry_if_exception_type(BatchValidationError), stop=stop_after_attempt(N+1), wait=wait_exponential, reraise=True) — tenacity on BatchValidationError ONLY (Pitfall 5)"
    - "_make_translate_batch_fn(settings) builder — constructs tenacity-decorated function at runtime so stop_after_attempt uses the correct settings value"
    - "asyncio.gather(*[_translate_batch(b, llm_client, settings) for b in batches]) — fully concurrent batch dispatch under LLMClient._semaphore"
    - "build_translate_prompt(): [CONTEXT] + [LINES TO TRANSLATE] with [context] prefixes (D-13, D-15)"
    - "parse_numbered_response(): forgiving regex r'\\[(\\d+)\\][.)\\]?\\s*(.*)' handles [N], [N]. and [N]) variants (A7)"
    - "NamedTemporaryFile(dir=quarantine_dir) + os.replace() — atomic quarantine artifact write (consistent with D-19)"
    - "D-20 ledger behavior table: 7 conditions (not-in-ledger, done+match, done+mismatch, done+deleted, quarantined, in_progress, foreign)"
    - "Ledger.content_hash() SHA-256[:16] — Phase-4-compatible idempotency key"
key_files:
  created:
    - trezarr/translate/engine.py
    - trezarr/output/ledger.py
  modified:
    - pyproject.toml
    - uv.lock
decisions:
  - "_make_translate_batch_fn(settings) factory pattern — tenacity @retry stop_after_attempt must be bound at function-definition time, but settings.translate_batch_retry_attempts is only known at runtime; building the decorated function in a factory each call resolves this cleanly"
  - "translate_file path resolution uses Path(path).resolve() at entry — ensures the ledger key is always the absolute path regardless of how Phase 3 passes the argument"
  - "_write_quarantine excludes cue text from artifact — T-02-03-03 information disclosure control; source subtitles may be proprietary"
metrics:
  duration: "12 min"
  completed: "2026-05-31"
  tasks_completed: 2
  files_created: 2
  files_modified: 2
---

# Phase 02 Plan 03: Mechanical Translation Engine + Ledger Summary

End-to-end `translate_file()` engine wired: numbered-line LLM protocol over batched SubDoc, tenacity retry on BatchValidationError only, 7-check document-level gate via validate_subdoc(), quarantine artifact write (no cue text), atomic sidecar via write_vi_sidecar(), and JSON idempotency ledger (SHA-256[:16] content hash, Phase-4-compatible schema). Phase 2 pipeline is complete — all 36 RED stubs from Plan 02-01 are now GREEN.

## What Was Built

3 files created/modified:

| File | Exports | Requirements |
|------|---------|-------------|
| `trezarr/translate/engine.py` | `translate_file`, `TranslationResult`, `BatchValidationError`, `TranslationError`, `build_translate_prompt`, `parse_numbered_response`, `_translate_batch` | ENG-03, ENG-06, ENG-07, D-12..D-20 |
| `trezarr/output/ledger.py` | `Ledger`, `LedgerEntry` | ENG-07, D-20 |
| `pyproject.toml` | tenacity 9.1.4 dependency | D-18 |

## Verification Results

```
uv run pytest tests/output/test_ledger.py -x -q
→ 6 passed in 0.02s

uv run pytest tests/translate/test_engine.py -x -q
→ 5 passed in 2.36s

uv run pytest tests/translate/ tests/output/ -x -q
→ 36 passed in 2.30s

uv run pytest -q (full suite)
→ 63 passed, 1 skipped in 2.65s
(1 skip = Phase-1 live LLM test marked with @pytest.mark.live — always skipped without a real endpoint)

grep -c "asyncio.Semaphore(" trezarr/translate/engine.py
→ 0 (no second Semaphore)

grep -n "retry_if_exception_type" trezarr/translate/engine.py (actual decorator line)
→ retry=retry_if_exception_type(BatchValidationError) only

All Phase-2 requirement IDs covered:
- ENG-02 (test_batching): PASS
- ENG-03 (test_engine::test_context_window_prompt): PASS
- ENG-06 (test_validate + test_engine retry/quarantine): PASS
- ENG-07 (test_ledger + test_engine::test_translate_file_skip_unchanged): PASS
- FMT-05 (test_write): PASS
```

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: tenacity + ledger.py | 8fae5fd | pyproject.toml, uv.lock, trezarr/output/ledger.py |
| Task 2: engine.py | 9a4b277 | trezarr/translate/engine.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] _make_translate_batch_fn() factory for runtime-bound tenacity stop_after_attempt**
- **Found during:** Task 2 — tenacity @retry decorators are applied at function definition time; `stop_after_attempt(settings.translate_batch_retry_attempts + 1)` cannot refer to `settings` at definition time since it's a parameter
- **Issue:** PATTERNS.md shows `stop_after_attempt(3)` as a hardcoded value, but the plan requires `settings.translate_batch_retry_attempts + 1` so the retry count is configurable
- **Fix:** Added `_make_translate_batch_fn(settings)` factory that builds the tenacity-decorated function at runtime with the correct `stop_after_attempt` value. `_translate_batch()` module-level function calls the factory. Tests pass `settings_factory(translate_batch_retry_attempts=2)` and verify 2 calls for a 1-retry scenario
- **Files modified:** trezarr/translate/engine.py
- **Commit:** 9a4b277

## Known Stubs

None. All created files are full implementations. The Phase-2 pipeline is complete:
- `trezarr/translate/sentinel.py` — TAG_RE + extract_sentinels + reinsert_sentinels
- `trezarr/translate/batching.py` — Batch + batch_subdoc
- `trezarr/translate/validate.py` — GateFailure + GateError + validate_subdoc
- `trezarr/translate/engine.py` — translate_file + full pipeline
- `trezarr/output/write.py` — write_vi_sidecar
- `trezarr/output/ledger.py` — Ledger + LedgerEntry

No `pytest.importorskip` skips remain for Phase-2 modules.

## Threat Flags

None. This plan implements:
- T-02-03-01 (LLM response validation): validate_subdoc() called before write_vi_sidecar() — V5 Input Validation control
- T-02-03-02 (prompt injection): extract_sentinels() removes inline tags before LLM; parse_numbered_response() uses structural regex (not eval)
- T-02-03-03 (quarantine info disclosure): _write_quarantine() records reason + failing_cue_indices + timestamp + source_path; NO cue text included; verified by grep check
- T-02-03-04 (foreign vi.srt clobber): Ledger authority — dest.exists() AND not in ledger → skip + log
- T-02-03-05 (ledger corruption): JSONDecodeError → empty ledger + warning; foreign-file check belt-and-suspenders
- T-02-03-06 (path traversal): Path(path).resolve() at translate_file() entry
- T-02-03-07 (double retry storm): retry_if_exception_type(BatchValidationError) only; no tenacity on openai.APIError
- T-02-03-08 (second Semaphore): grep confirms 0 asyncio.Semaphore() calls in engine.py

No new network endpoints, auth paths, or schema changes introduced beyond what was planned.

## Self-Check: PASSED

Files exist check:
- trezarr/translate/engine.py: FOUND
- trezarr/output/ledger.py: FOUND

Commits exist check:
- 8fae5fd (Task 1 — tenacity + ledger): FOUND
- 9a4b277 (Task 2 — engine): FOUND

Full suite check:
- uv run pytest -q: 63 passed, 1 skipped (live LLM test)
- No Phase-2 skips remaining
