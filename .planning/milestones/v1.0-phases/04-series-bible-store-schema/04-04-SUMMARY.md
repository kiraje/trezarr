---
phase: 04-series-bible-store-schema
plan: 04
subsystem: ledger
tags: [ledger, sqlite, json-to-sqlite-migration, async-ledger, atomic-rename, cli-wiring, regression, ledger-protocol]
dependency_graph:
  requires: [04-01, 04-02]
  provides: [ledger-sqla, json-ledger-migration, ledger-protocol, cli-db-startup]
  affects: [trezarr/translate/engine.py, trezarr/discover/gap.py, trezarr/discover/scan.py, trezarr/cli.py]
tech_stack:
  added: []
  patterns:
    - LedgerProtocol (typing.Protocol, @runtime_checkable) as the async contract boundary
    - contextlib.ExitStack for multi-patch test context managers (replaces with(*list) which Python does not support)
    - SELECT-then-INSERT/UPDATE upsert pattern (avoids dialect-specific INSERT OR REPLACE)
    - Pitfall-5 ordering in migration_runner: SQLite commit FIRST, os.replace SECOND
key_files:
  created:
    - trezarr/output/_ledger_protocol.py
    - trezarr/output/ledger_sqla.py
  modified:
    - trezarr/output/ledger.py
    - trezarr/db/migration_runner.py
    - trezarr/cli.py
    - trezarr/translate/engine.py
    - trezarr/discover/gap.py
    - trezarr/discover/scan.py
    - tests/output/test_ledger.py
    - tests/test_cli.py
    - tests/translate/test_engine.py
    - tests/integration/test_translate_engine_async_ledger.py
decisions:
  - Option C (async Ledger.check/record) locked in per 04-PATTERNS.md Pattern 5 — CLAUDE.md mandates async everywhere
  - Split Step 3.5 into 3.5a (hard-fatal Alembic) and 3.5b (best-effort JSON migration) per D-37 asymmetric forgiveness
  - contextlib.ExitStack chosen over with(*list) because Python does not unpack a list as individual context managers in a with statement
  - SELECT-then-INSERT/UPDATE upsert chosen over INSERT OR REPLACE for backend portability
metrics:
  duration: ~4 hours (continued from prior session)
  completed_date: "2026-06-01"
  tasks_completed: 2
  files_changed: 13
  tests_added: ~40
  final_test_count: "184 passed, 1 skipped"
---

# Phase 04 Plan 04: JSON Ledger Retirement — LedgerProtocol + LedgerSQLA + JSON→SQLite Migration Summary

**One-liner:** SQLAlchemy-backed LedgerSQLA with async check/record (LedgerProtocol contract), one-shot JSON→SQLite migration with Pitfall-5 commit-first/rename-second ordering, and cli.py Step 3.5 startup wiring.

## What Was Built

### Task 1: LedgerProtocol + LedgerSQLA + Migration Runner + Engine/CLI Propagation

**`trezarr/output/_ledger_protocol.py`** — New `@runtime_checkable` `LedgerProtocol` declaring the async contract: `async check`, `async record`, `@staticmethod content_hash`. Module docstring explicitly documents the breaking internal API change (check/record now async), rationale (CLAUDE.md async-everywhere mandate), and scope (internal only — no external API affected).

**`trezarr/output/ledger_sqla.py`** — New `LedgerSQLA(session_factory)` backed by the `processed_file` SQLAlchemy table. Uses SELECT-then-INSERT/UPDATE upsert (not dialect-specific INSERT OR REPLACE), `async with session.begin()` for atomic writes, and `hashlib.sha256(source_bytes).hexdigest()[:16]` for `content_hash` (identical to the JSON Ledger). Implements `LedgerProtocol` structurally (runtime_checkable issubclass passes).

**`trezarr/output/ledger.py`** — `Ledger.check` and `Ledger.record` converted to `async def` (Option C per 04-PATTERNS.md). Module docstring documents the breaking change with rationale and scope.

**`trezarr/db/migration_runner.py`** — Added `migrate_json_ledger_if_needed(session_factory, settings)` implementing D-37 one-shot JSON→SQLite import:
- Pitfall-5 ordering: SQLite transaction commits FIRST, `os.replace` renames SECOND
- Idempotency: short-circuits on EITHER `.migrated.bak` OR `.corrupt.bak` presence
- Corrupt/unreadable JSON → log warning + rename to `.corrupt.bak` (distinct suffix)
- Successful migration → rename to `.migrated.bak`
- Collision (source_path already in SQLite) → log WARNING + skip (DB is newer truth)
- `os.replace` in try/except OSError: commit failure is not re-raised

**`trezarr/translate/engine.py`** — All `ledger.check(...)` and `ledger.record(...)` calls updated to `await`. `ledger` parameter type-annotated as `LedgerProtocol`. `Ledger.content_hash(source_bytes)` call site replaced with `ledger.content_hash(source_bytes)` (instance method dispatch works since both classes implement the staticmethod).

**`trezarr/discover/gap.py` + `trezarr/discover/scan.py`** — `is_eligible` and `scan_for_eligible_items` made async to propagate the async ledger.check call.

**Tests updated:**
- `tests/output/test_ledger.py` — all check/record calls converted to `await`, async def tests
- `tests/translate/test_engine.py` — 3 unawaited ledger calls fixed (Rule 1 bug fix)
- `tests/integration/test_translate_engine_async_ledger.py` — Test 14 (quarantine path awaits ledger.record spy), Test 15 (repo-wide grep gate, dynamic enforcement)

### Task 2: cli.py Step 3.5 Startup Wiring

**`trezarr/cli.py`** — Step 3.5 split into two separate try/except blocks:
- Step 3.5a (hard-fatal): `build_engine → run_migrations_to_head → build_session_factory → LedgerSQLA`; any exception returns 1 with actionable message
- Step 3.5b (best-effort): `await migrate_json_ledger_if_needed`; any exception logs error and continues (D-37 forgiveness)

Added `from trezarr.db.session import build_session_factory` import.

**`tests/test_cli.py`** — 5 new tests added:
1. Call-order verification (build_engine < migrations < session_factory < migrate_json < discovery)
2. LedgerSQLA (not JSON Ledger) passed to scan_for_eligible_items
3. Alembic migration failure → exit_code=1 (hard-fatal)
4. JSON migration failure → logs error but run continues with exit_code=0 (best-effort)
5. End-to-end smoke with real temp SQLite: vi.srt sidecar written, `processed_file` row inserted with status='done'

Also refactored all `with (*_db_patches(), ...)` blocks to `contextlib.ExitStack` (Python does not allow unpacking a list into a `with` statement's parenthesized group).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] tests/translate/test_engine.py: unawaited ledger.check/record calls**
- **Found during:** Task 1 — full test suite run
- **Issue:** 3 call sites in test_engine.py used sync `ledger.check(str(src))` and `ledger.record(entry)` after Ledger became async. The calls returned coroutine objects, causing `AttributeError: 'coroutine' object has no attribute 'status'`.
- **Fix:** Added `await` to all 3 call sites in test_engine.py
- **Files modified:** `tests/translate/test_engine.py`
- **Commit:** 5b45ac8

**2. [Rule 1 - Bug] Python with(*list, ctx_mgr) syntax does not work as expected**
- **Found during:** Task 1 — first test run after adding _db_patches()
- **Issue:** `with (*_db_patches(), patch(...)):` creates a tuple, not individual context managers. Python's parenthesized `with (...)` syntax requires each element to be a context manager expression — list unpacking with `*` produces a tuple object, which raises `TypeError: 'tuple' object does not support the context manager protocol`.
- **Fix:** Converted all 10 `with (...)` blocks to `contextlib.ExitStack` pattern.
- **Files modified:** `tests/test_cli.py`
- **Commit:** 5b45ac8

**3. [Rule 2 - Missing] Split Step 3.5 into hard-fatal (Alembic) and best-effort (JSON migration)**
- **Found during:** Task 2 — implementing Test 4 which checks JSON migration failure is non-fatal
- **Issue:** The original single try/except made both Alembic failure AND JSON migration failure hard-fatal (return 1). The plan requires asymmetric handling: Alembic failure is hard-fatal, JSON migration failure is best-effort (D-37 forgiveness).
- **Fix:** Split into Step 3.5a and Step 3.5b with separate try/except blocks.
- **Files modified:** `trezarr/cli.py`
- **Commit:** 765ddad

**4. [Rule 2 - Missing] Added build_session_factory to _db_patches()**
- **Found during:** Task 2 — after adding build_session_factory import to cli.py
- **Issue:** The `_db_patches()` helper didn't include a patch for `build_session_factory`, which would cause tests to try to call the real function with the mocked engine.
- **Fix:** Added `patch("trezarr.cli.build_session_factory", return_value=MagicMock())` to `_db_patches()`.
- **Files modified:** `tests/test_cli.py`
- **Commit:** 765ddad

## Known Stubs

None — all implementation paths are fully wired. The LedgerSQLA is backed by a real SQLite table via SQLAlchemy. The migration runner performs real JSON→SQLite imports.

## Accepted V1 Limitation

Per D-37 and documented in `migrate_json_ledger_if_needed` docstring: if the SQLite DB is deleted but `.migrated.bak` exists, the idempotency short-circuit fires and the JSON data is NOT re-imported. Operators must manually remove `.migrated.bak` and restore the JSON file to recover. This is accepted for v1 (single-user self-hosted daemon).

## Threat Surface Scan

No new trust boundaries beyond what was planned in the threat model. The `migrate_json_ledger_if_needed` function reads from the JSON ledger file (external input — handled with forgiveness path to `.corrupt.bak`). T-04-13 through T-04-17 are all mitigated as planned.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| `trezarr/output/_ledger_protocol.py` exists | FOUND |
| `trezarr/output/ledger_sqla.py` exists | FOUND |
| `trezarr/db/migration_runner.py` exists | FOUND |
| `trezarr/cli.py` exists | FOUND |
| `04-04-SUMMARY.md` exists | FOUND |
| Task 1 commit `5b45ac8` | FOUND |
| Task 2 commit `765ddad` | FOUND |
| Full test suite: 184 passed, 1 skipped, 0 failures | PASSED |
