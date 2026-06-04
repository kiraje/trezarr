---
phase: 04-series-bible-store-schema
plan: "01"
subsystem: persistence
tags: [sqlite, sqlalchemy, alembic, async, schema, series-bible, tdd]
dependency_graph:
  requires:
    - trezarr/config.py (Phase 1–3 settings foundation)
    - trezarr/db/base.py (DeclarativeBase root)
  provides:
    - trezarr/db/engine.py (build_engine with PRAGMA event listener)
    - trezarr/db/session.py (build_session_factory)
    - trezarr/db/migration_runner.py (run_migrations_to_head)
    - trezarr/bible/models.py (7 SQLAlchemy 2.0 typed models)
    - alembic/versions/0001_baseline_bible_schema.py (baseline migration)
  affects:
    - trezarr/config.py (4 Phase-4 fields added)
    - .gitignore (*.db-wal, *.db-shm added)
tech_stack:
  added:
    - sqlalchemy[asyncio]==2.0.50
    - aiosqlite==0.22.1
    - alembic==1.18.4
  patterns:
    - SQLAlchemy 2.0 async engine + connect-event PRAGMA listener (Pitfall 4)
    - Alembic run_sync bridge for async-to-sync migration (Pitfall 1)
    - DeclarativeBase typed models with Mapped[T] + mapped_column()
    - render_as_batch=True for SQLite ALTER support (Pitfall 6)
    - expire_on_commit=False on async_sessionmaker (Pitfall 2)
    - TDD RED/GREEN/REFACTOR: test-first with real Alembic migration per test
key_files:
  created:
    - trezarr/db/__init__.py
    - trezarr/db/base.py
    - trezarr/db/engine.py
    - trezarr/db/session.py
    - trezarr/db/migration_runner.py
    - trezarr/bible/__init__.py
    - trezarr/bible/models.py
    - alembic.ini
    - alembic/env.py
    - alembic/script.py.mako
    - alembic/README
    - alembic/versions/0001_baseline_bible_schema.py
    - tests/db/__init__.py
    - tests/db/conftest.py
    - tests/db/test_engine.py
    - tests/db/test_migrations.py
    - tests/bible/__init__.py
    - tests/bible/conftest.py
    - tests/bible/test_models.py
  modified:
    - pyproject.toml (3 new deps)
    - uv.lock (lockfile update)
    - .gitignore (*.db-wal, *.db-shm)
    - trezarr/config.py (4 Phase-4 settings fields)
    - alembic/env.py (pytest-isolation fix for fileConfig)
decisions:
  - "Hand-authored baseline migration (not autogenerate) to lock schema at D-31 boundary"
  - "fileConfig guarded against pytest to prevent caplog isolation breakage"
  - "tests/bible/conftest.py re-exports db_engine/session_factory from tests/db/conftest.py"
  - "SQLite server_default strings stored with surrounding single-quotes in PRAGMA table_info"
metrics:
  duration_seconds: 655
  completed_date: "2026-06-01"
  tasks_completed: 2
  files_changed: 23
---

# Phase 4 Plan 01: DB Foundation — Engine + Session + Migrations + Models Summary

SQLAlchemy 2.0 async + aiosqlite + Alembic persistence backbone with all 7 Series Bible tables, per-connection PRAGMA enforcement (WAL/FK/synchronous), and 17 passing tests including schema-drift guard, round-trips, and D-39 boundary check.

## What Was Built

### Task 1: Foundation — deps + scaffolding + models + baseline migration + conftest + PRAGMA tests

Delivered as a single atomic TDD unit (RED then GREEN):

**RED commit (`ed916f9`):** Failing PRAGMA tests in `tests/db/test_engine.py` plus package installs and `.gitignore` update. Tests fail with `ModuleNotFoundError` — modules do not exist yet.

**GREEN commit (`3e967a4`):** All foundation modules:
- `trezarr/db/base.py` — `Base(DeclarativeBase)` root
- `trezarr/db/engine.py` — `build_engine(settings)` with `event.listens_for(engine.sync_engine, "connect")` for per-connection PRAGMAs (WAL, synchronous=NORMAL, foreign_keys=ON with toggle)
- `trezarr/db/session.py` — `build_session_factory(engine)` with mandatory `expire_on_commit=False`
- `trezarr/db/migration_runner.py` — `run_migrations_to_head(engine)` via `conn.run_sync(_do_upgrade, cfg)` bridge
- `trezarr/bible/models.py` — 7 SQLAlchemy 2.0 typed models: Series, Character, TermDictionary, AddressMap, RelationshipEvent, BibleEvent, ProcessedFile
- `alembic.ini` + `alembic/env.py` + `alembic/script.py.mako` — async-aware Alembic scaffolding with `render_as_batch=True`
- `alembic/versions/0001_baseline_bible_schema.py` — hand-authored baseline creating all 7 tables with CHECK constraints and 3 performance indexes
- `trezarr/config.py` — 4 Phase-4 settings fields under `# ── Phase 4: Series Bible persistence (D-31, D-38)` header
- `tests/db/conftest.py` — `db_engine` + `session_factory` fixtures using temp-file SQLite

### Task 2: Model-fidelity + migration tests

**Commit `7abcd04`:**
- `tests/db/test_migrations.py` — 6 migration tests including schema-drift guard
- `tests/bible/test_models.py` — 7 round-trip + JSON-default + D-39 boundary tests
- `tests/bible/conftest.py` — fixture re-export shim
- `alembic/env.py` (patched) — pytest isolation fix for `fileConfig`

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| tests/db/test_engine.py | 4 (PRAGMA: FK, WAL, synchronous, FK-toggle) | PASSED |
| tests/db/test_migrations.py | 6 (tables, downgrade, UNIQUE, drift-guard, CHECK, indexes) | PASSED |
| tests/bible/test_models.py | 7 (round-trips, JSON-defaults, D-39 boundary) | PASSED |
| **Total new** | **17** | **PASSED** |
| Phase 1/2/3 regression | 127 + 1 skipped | PASSED |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Alembic fileConfig during tests broke caplog isolation**
- **Found during:** Task 2 (running full suite after test_engine.py)
- **Issue:** `alembic/env.py::fileConfig(config.config_file_name)` runs during migrations, which reconfigures the root Python logger (adds a StreamHandler, sets level=WARNING). This prevents pytest's `caplog` from capturing WARNING-level logs in tests that run *after* any test that triggers a migration, breaking `test_probe_warns_on_non_writable_root` in `tests/test_paths.py`.
- **Fix:** Guard `fileConfig` with `"_pytest" in sys.modules` check — skips it when running under pytest. The `_pytest` module is always present in `sys.modules` during a pytest session.
- **Files modified:** `alembic/env.py`
- **Commit:** `7abcd04`

**2. [Rule 1 - Bug] SQLite stores server_default strings with surrounding single-quotes**
- **Found during:** Task 2 (test_json_default_consistency)
- **Issue:** `PRAGMA table_info('series')` returns `"'[]'"` (with surrounding single-quotes) for the `locked_fields` server_default, not `"[]"`. The test was asserting `== "[]"`.
- **Fix:** Added `_strip_sqlite_quotes()` helper in the test to strip surrounding single/double quotes before comparing.
- **Files modified:** `tests/bible/test_models.py`
- **Commit:** `7abcd04`

**3. [Rule 1 - Bug] SQLAlchemy callable default not applied at __init__ time**
- **Found during:** Task 2 (test_json_default_consistency)
- **Issue:** In SQLAlchemy 2.0, `mapped_column(JSON, default=list)` applies the callable default at INSERT (flush) time, not at Python object construction time. The test was asserting `s.locked_fields is not None` on a pre-flush object.
- **Fix:** Removed the pre-flush assertion; the test now only checks the post-flush and post-reload state.
- **Files modified:** `tests/bible/test_models.py`
- **Commit:** `7abcd04`

**4. [Rule 2 - Missing fixture discovery] tests/bible needed conftest.py for shared fixtures**
- **Found during:** Task 2 (test_series_round_trip couldn't find session_factory fixture)
- **Issue:** pytest conftest.py files are directory-scoped. The `session_factory` fixture in `tests/db/conftest.py` was not visible to `tests/bible/` tests.
- **Fix:** Created `tests/bible/conftest.py` that re-exports `db_engine` and `session_factory` from `tests/db/conftest.py`.
- **Files modified:** `tests/bible/conftest.py` (created)
- **Commit:** `7abcd04`

## Known Stubs

None. All 7 models are fully defined. `address_map` and `relationship_event` have correct schemas per D-31 — they are intentionally empty in Phase 4 (Phase 5/6 populate them). No hardcoded empty values, no placeholder text, no TODOs in production code.

The `# TODO 04-04` comment in `trezarr/db/migration_runner.py` documents the deferred `migrate_json_ledger_if_needed()` function — this is intentional and documented in the plan.

## Threat Surface Scan

No new network endpoints, auth paths, or trust-boundary changes introduced. All changes are internal persistence infrastructure.

| Flag | File | Description |
|------|------|-------------|
| T-04-01 (mitigated) | alembic/versions/0001_baseline_bible_schema.py | Hand-authored; schema-drift guard test (test_schema_drift_guard) detects divergence at CI time |
| T-04-04 (mitigated) | trezarr/db/engine.py | PRAGMA foreign_keys=ON per-connect enforced; verified by test_foreign_keys_enabled_per_connection |

## Self-Check: PASSED

All key files exist. All commits verified in git history. 17 new tests pass, 144 total (1 skipped) with no regressions.

| Check | Result |
|-------|--------|
| All 16 key files exist on disk | PASSED |
| Commits ed916f9, 3e967a4, 7abcd04, 2f29a19 in history | PASSED |
| 17 new tests pass (tests/db/ + tests/bible/) | PASSED |
| Full suite 144 passed, 1 skipped, 0 failed | PASSED |
