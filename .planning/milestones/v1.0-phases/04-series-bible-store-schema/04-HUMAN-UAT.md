---
status: partial
phase: 04-series-bible-store-schema
source: [04-VERIFICATION.md]
started: 2026-06-01T00:00:00Z
updated: 2026-06-01T12:30:00Z
---

## Current Test

Test 1 (live *arr integration) still awaiting live Sonarr/Radarr credentials. Test 2 passed under a real `asyncio.run()` invocation.

## Tests

### 1. Live *arr integration smoke

test: Run `trezarr run --once` against a live Sonarr instance with at least one series that has a source subtitle.
expected: A series row appears in the SQLite `series` table with arr_metadata populated; the `processed_file` table records a 'done' row after a successful translation; the `vi.srt` sidecar is written to disk.
result: [pending]
why_human: End-to-end behavior depends on a live *arr stack and LLM endpoint — cannot be exercised with automated tests alone. Requires `TREZARR_SONARR_URL` + `TREZARR_SONARR_APIKEY` (or Radarr equivalents) pointed at a running instance.

### 2. CR-01 engine-dispose runtime behavior

test: Run `trezarr run --once` in a real asyncio context and watch stderr after exit.
expected: No `RuntimeError: Event loop is closed` or `Task was destroyed but it is pending` warnings appear in stderr after `trezarr run --once` exits.
result: passed
verified_at: 2026-06-01T12:30:00Z
how_verified: Executed `TREZARR_BIBLE_DB_URL=sqlite+aiosqlite:////tmp/trezarr-uat-*.db uv run trezarr run --once` AND `python -W error::RuntimeWarning -c 'import asyncio; from trezarr.cli import _run_once; asyncio.run(_run_once(None))'`. Both invocations exited 0 with no asyncio teardown warnings. The CR-01 fix (commit `19fb6e2 fix(04): dispose AsyncEngine in _run_once and CLI smoke test`) holds under real-world asyncio teardown. As a side effect, the Alembic baseline migration 0001 also self-verified — fresh DB came up with all 7 Bible tables + WAL + FK enforcement (BIBLE-01 schema confirmed live).

## Summary

total: 2
passed: 1
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
