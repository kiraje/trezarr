---
status: partial
phase: 04-series-bible-store-schema
source: [04-VERIFICATION.md]
started: 2026-06-01T00:00:00Z
updated: 2026-06-01T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live *arr integration smoke

test: Run `trezarr run --once` against a live Sonarr instance with at least one series that has a source subtitle.
expected: A series row appears in the SQLite `series` table with arr_metadata populated; the `processed_file` table records a 'done' row after a successful translation; the `vi.srt` sidecar is written to disk.
result: [pending]
why_human: End-to-end behavior depends on a live *arr stack and LLM endpoint — cannot be exercised with automated tests alone.

### 2. CR-01 engine-dispose runtime behavior

test: Run `trezarr run --once` in a real asyncio context and watch stderr after exit.
expected: No `RuntimeError: Event loop is closed` or `Task was destroyed but it is pending` warnings appear in stderr after `trezarr run --once` exits.
result: [pending]
why_human: The 04-REVIEW.md CR-01 finding identifies a missing `await engine.dispose()` in the production `_run_once` function. The automated test suite passes because tests mock `build_engine` — the real asyncio teardown path is not exercised.

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
