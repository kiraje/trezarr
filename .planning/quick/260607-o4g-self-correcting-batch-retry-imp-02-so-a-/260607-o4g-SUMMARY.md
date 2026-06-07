---
phase: quick-260607-o4g
plan: 01
subsystem: translate/engine
tags: [imp-02, correction-loop, batch-retry, dev-runner, moat]
dependency_graph:
  requires: []
  provides: [self-correcting-batch-retry, local-dev-runner]
  affects: [trezarr/translate/engine.py, scripts/translate_one.py]
tech_stack:
  added: []
  patterns: [message-accumulating-correction-loop, bounded-retry-without-tenacity]
key_files:
  created:
    - tests/translate/test_batch_self_correct.py
    - scripts/translate_one.py
  modified:
    - trezarr/translate/engine.py
    - .gitignore
decisions:
  - "IMP-02: Replaced tenacity BatchValidationError retry with a bounded message-accumulating correction loop in _translate_batch_inner; tenacity removed entirely from this function"
  - "_STRUCT_CORRECTION_MSG references pronoun hints as 'from my FIRST message' with no slot for pronoun-pair content — moat invariant preserved in the template itself"
  - "FakeLLMClient in tests uses explicit integer call_count + calls: list[list[dict]] for deterministic inspection without mock magic"
  - "scripts/translate_one.py uses Ledger (JSON) not LedgerSQLA for the dev throwaway ledger — simple, no session_factory for the ledger itself"
metrics:
  duration: 7 minutes
  completed: "2026-06-07"
  tasks_completed: 2
  files_changed: 4
---

# Phase quick-260607-o4g Plan 01: IMP-02 Self-Correcting Batch Retry + Dev Runner Summary

Self-correcting batch translation retry (message-accumulating correction loop) to eliminate the IMP-02 quarantine class, plus `scripts/translate_one.py` for local dev fast-feedback.

## What Was Built

### Task 1: IMP-02 Self-Correcting Batch Retry (engine.py)

Replaced the tenacity-on-BatchValidationError retry in `_translate_batch_inner` with a bounded message-accumulating correction loop. When the LLM drops a line (the Ep-142 job 8 failure mode), the pipeline now:

1. Appends the bad assistant reply to the messages list
2. Appends a structural-only correction user-turn (`_STRUCT_CORRECTION_MSG`) referencing hints as "from my FIRST message"
3. Calls the LLM again with the full conversation — the model sees its own error and self-corrects

The correction turn is built from the module-level constant `_STRUCT_CORRECTION_MSG` which contains no slot for pronoun-pair content and no `(speaker says:` substring. The pronoun hints remain exclusively in `messages[0]` (the original prompt).

**MOAT INVARIANT PRESERVED:** Test B asserts `(speaker says:` is absent from the correction turn. The constant template uses "all pronoun hints from my FIRST message" instead.

**No double-retry storm:** `BatchValidationError` was removed from tenacity's retry predicate. The correction loop is the sole retry mechanism, bounded at `translate_batch_retry_attempts + 1` total LLM calls. Test E asserts `call_count == retry_attempts + 1` (not more).

**D-18 docstring updated:** Module docstring and `BatchValidationError`/`TranslationError` docstrings describe the new correction-loop design (not tenacity on BatchValidationError).

Changes to engine.py:
- Removed `from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential`
- Added `_STRUCT_CORRECTION_MSG` module-level constant
- Rewrote `_make_translate_batch_fn` / `_translate_batch_inner` — no decorator, plain async def with correction loop
- Updated module docstring D-18 entry and Critical constraints block

### Task 2: scripts/translate_one.py

Created `scripts/translate_one.py` — a dev-only CLI that runs the real pipeline on a single source subtitle locally. Features:
- `argparse`: positional `source`, `--out` (optional), `--series-id` (optional)
- Reads LLM credentials from env / `.env` via `TrezarrSettings` — no hardcoded secrets
- Single `settings_with_overrides` object (via `model_copy`) used for ALL downstream calls
- `tempfile.mkstemp(suffix=".db")` for the Bible DB, fd closed immediately, atexit cleanup
- `tempfile.mkstemp(suffix=".json")` for the throwaway ledger, atexit cleanup
- `engine.dispose()` in a `finally` block to clean up the async SQLAlchemy engine
- Prints wall-clock time and result (DONE / QUARANTINED / SKIPPED)

Added `scripts/*.srt` to `.gitignore` to prevent accidentally committing any output files.

Human UAT (not automated in this commit):
```
uv run python scripts/translate_one.py "test-results/Ep142.en.srt" --out /tmp/Ep142.vi.srt
```

## Test Results

### TDD Deterministic Tests (test_batch_self_correct.py)

5 new tests, all passing, no real LLM required:

| Test | Description | Result |
|------|-------------|--------|
| A — Recovery | Dropped [1] on call 1, all 4 on call 2 → returns 4 lines | PASS |
| B — Moat | messages[2] (correction turn) contains NO `(speaker says:` | PASS |
| C — Correction phrasing | correction turn has defect description + rules re-affirmation | PASS |
| D — Budget exhaustion | Always-bad LLM raises BatchValidationError after exactly 2 calls | PASS |
| E — No storm | call_count == retry_attempts+1 (tenacity adds 0 extra calls) | PASS |

### Full Suite

```
480 passed, 1 skipped, 3 xfailed, 52 xpassed in 3.70s
```

Prior count was 531 collected (475 in STATE.md was a snapshot from before additional test file additions). No regressions.

### Ruff

All checks passed on `trezarr/translate/engine.py`, `tests/translate/test_batch_self_correct.py`, and `scripts/translate_one.py`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Template moat] Rephrased _STRUCT_CORRECTION_MSG to remove `(speaker says:`**
- **Found during:** GREEN phase — Test B failed immediately
- **Issue:** The plan's example `_STRUCT_CORRECTION_MSG` included the phrase `'(speaker says: ...; addresses as: ...)' hints` — this caused Test B (the moat assertion) to fail because the substring `(speaker says:` appeared in the correction turn content
- **Fix:** Replaced `'(speaker says: ...; addresses as: ...)' hints from my FIRST message` with `all pronoun hints from my FIRST message` — semantically equivalent, moat-safe
- **Files modified:** trezarr/translate/engine.py
- **Commit:** f3405e7

## Known Stubs

None. The correction loop is fully implemented. The dev runner imports cleanly and `--help` works. The real end-to-end DeepSeek run is a manual follow-up (human UAT — not automated per plan constraint).

## Threat Flags

None. The correction turn template contains no pronoun-pair slot (T-o4g-01 mitigated). The correction loop is bounded at `translate_batch_retry_attempts+1` total calls (T-o4g-02 mitigated). The dev runner reads credentials from env and never logs them (T-o4g-03 accepted — gitignored .env).

## Self-Check

**Files created/modified:**
- `trezarr/translate/engine.py` — FOUND
- `tests/translate/test_batch_self_correct.py` — FOUND
- `scripts/translate_one.py` — FOUND

**Commits:**
- `f3405e7` — FOUND (feat: IMP-02 self-correcting batch retry + deterministic tests)
- `dd89d89` — FOUND (feat: add scripts/translate_one.py local dev runner)

**Test counts:** 5 new tests pass. Full suite: 480 passed (was 475 in earlier STATE.md snapshot; difference is test additions from other quick tasks since that snapshot, not regressions).

## Self-Check: PASSED
