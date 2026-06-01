---
phase: 04
slug: series-bible-store-schema
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-01
revised: 2026-06-01
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (already installed) |
| **Config file** | pyproject.toml / pytest.ini |
| **Quick run command** | `uv run pytest tests/bible tests/db -x --tb=short` |
| **Full suite command** | `uv run pytest -x --tb=short` |
| **Estimated runtime** | ~30 seconds (Phase 4 isolated) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/bible tests/db -x --tb=short`
- **After every plan wave:** Run `uv run pytest -x --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Filled in by planner on revision. Each row maps a task to its automated test command extracted verbatim from the plan's `<verify><automated>` block. The Test File column lists the actual files the plan creates (not generic placeholders) — file names are reconciled with what 04-01/02/03/04-PLAN.md actually ship.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | Test File(s) Created | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|----------------------|--------|
| 04-01-T1 | 04-01 | 1 | BIBLE-01, BIBLE-02, BIBLE-04, BIBLE-05, BIBLE-06 | — | PRAGMA foreign_keys/WAL/synchronous enforced per-connection (D-38); SQLA-typed schema baseline | unit + integration | `uv sync && uv run python -c "import sqlalchemy, aiosqlite, alembic" && uv run pytest tests/db/test_engine.py -x && grep -q 'event.listens_for' trezarr/db/engine.py && grep -q 'expire_on_commit=False' trezarr/db/session.py && grep -q 'run_sync' trezarr/db/migration_runner.py && grep -q 'render_as_batch=True' alembic/env.py` | tests/db/test_engine.py, tests/db/conftest.py, tests/db/__init__.py | ⬜ pending |
| 04-01-T2 | 04-01 | 1 | BIBLE-01, BIBLE-02, BIBLE-04, BIBLE-05, BIBLE-06 | — | 7-table baseline migration applies + downgrades; UNIQUE(arr_kind,arr_instance,arr_series_id) enforced (D-33); models round-trip cleanly; D-39 bible/__init__ does not import SQLA | unit | `uv run pytest tests/db/test_engine.py tests/db/test_migrations.py tests/bible/test_models.py -x` | tests/db/test_migrations.py, tests/bible/test_models.py, tests/bible/__init__.py | ⬜ pending |
| 04-02-T1 | 04-02 | 2 | BIBLE-01, BIBLE-05 | T-04-IF (untrusted *arr payload fields) | MediaItem extended with arr_kind/tvdb_id/genres/overview/year/network/runtime at discovery layer; defensive against sparse arr payloads | unit | `uv run pytest tests/arr/test_media_item_arr_metadata.py tests/arr/ -x` | tests/arr/test_media_item_arr_metadata.py | ⬜ pending |
| 04-02-T2 | 04-02 | 2 | BIBLE-01, BIBLE-05 | T-04-DoS (oversized arr_metadata JSON) | get_or_create_series is atomic + idempotent (D-33/D-36); arr_metadata snapshot size capped at 32 KB; DTO boundary admits no SQLA leakage (D-39) | unit + boundary | `uv run pytest tests/bible/test_dto_boundary.py tests/bible/test_lazy_series_create.py tests/bible/test_arr_metadata_snapshot.py tests/bible/test_models.py -x` | tests/bible/test_dto_boundary.py, tests/bible/test_lazy_series_create.py, tests/bible/test_arr_metadata_snapshot.py | ⬜ pending |
| 04-03-T1 | 04-03 | 3 | BIBLE-02, BIBLE-04, BIBLE-06 | — | Pure merge policy: lock-precedence (D-34) + no-op detection (D-32 carry-forward); zero SQLA, zero async, zero IO | unit (pure) | `uv run pytest tests/bible/test_merge_policy_pure.py -x` | tests/bible/test_merge_policy_pure.py | ⬜ pending |
| 04-03-T2 | 04-03 | 3 | BIBLE-02, BIBLE-04, BIBLE-06 | — | merge_inferred atomicity (UPDATE + bible_event INSERT in one txn — D-32); source enum validated; entity-type-agnostic; carry-forward end-to-end (BIBLE-06 success criterion 4); audit log append-only | unit + integration | `uv run pytest tests/bible/test_merge_inferred.py tests/bible/test_carry_forward.py tests/bible/test_bible_event_audit.py tests/bible/test_merge_policy_pure.py tests/bible/test_lazy_series_create.py tests/bible/test_arr_metadata_snapshot.py tests/bible/test_dto_boundary.py tests/bible/test_models.py -x` | tests/bible/test_merge_inferred.py, tests/bible/test_carry_forward.py, tests/bible/test_bible_event_audit.py | ⬜ pending |
| 04-04-T1 | 04-04 | 3 | BIBLE-01 | T-04-Migration (corrupt JSON ledger / commit-rename race) | LedgerSQLA preserves Phase-2 interface (regression suite); JSON→SQLite migration is commit-FIRST/rename-SECOND (Pitfall 5), idempotent, forgiving on corrupt JSON; engine.py has EXACTLY 6 awaited ledger call sites (lines 421, 438, 454, 479, 520, 537) | integration + regression | `uv run pytest tests/output/test_ledger.py tests/output/test_ledger_sqla.py tests/db/test_migrate_json_ledger.py tests/integration/test_translate_engine_async_ledger.py -x && [ $(grep -cE 'await ledger\.(check\|record)' trezarr/translate/engine.py) -eq 6 ] && [ $(grep -v '^[[:space:]]*#' trezarr/translate/engine.py \| grep -cE '(^\|[^a-z_])ledger\.(check\|record)\(') -eq 6 ]` | tests/output/test_ledger_sqla.py, tests/db/test_migrate_json_ledger.py, tests/integration/test_translate_engine_async_ledger.py, tests/output/test_ledger.py (updated to async) | ⬜ pending |
| 04-04-T2 | 04-04 | 3 | BIBLE-01 | — | cli.py Step 3.5 wires engine + migrations + LedgerSQLA in correct position (after probe_media_roots, before LLMClient); asymmetric failure handling (Alembic = fatal, JSON-ledger import = best-effort per D-37); end-to-end smoke writes vi.srt + processed_file row | integration | `uv run pytest tests/test_cli.py tests/output/test_ledger_sqla.py tests/db -x && uv run pytest -x` | tests/test_cli.py (5 new tests + existing updates) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Test scaffolding the planner has stood up before any production code lands:

- [x] `tests/db/conftest.py` — async engine fixture (temp-file SQLite, fresh per test) + session_factory fixture (created in 04-01-T1)
- [x] `tests/db/__init__.py` — package marker (created in 04-01-T1)
- [x] `tests/bible/__init__.py` — package marker (created in 04-01-T2)
- [x] `tests/db/test_engine.py` — PRAGMAs apply on EVERY pool connection (foreign_keys=ON, journal_mode=WAL, synchronous=NORMAL) — 4 tests (created in 04-01-T1)
- [x] `tests/db/test_migrations.py` — baseline applies on fresh DB, all 7 tables created, downgrade reversible, UNIQUE(arr_kind,arr_instance,arr_series_id) enforced — 3 tests (created in 04-01-T2)
- [x] `tests/bible/test_models.py` — Series/Character/TermDictionary/ProcessedFile/BibleEvent round-trip + D-39 leakage guard — 6 tests (created in 04-01-T2)
- [x] `tests/bible/test_dto_boundary.py` — DTO boundary: no SQLA names reachable in trezarr.bible.dto + SeriesDTO model_validate round-trip — 2 tests (created in 04-02-T2)
- [x] `tests/bible/test_lazy_series_create.py` — get_or_create_series lazy + idempotent (D-36), UNIQUE-triple enforcement, atomic single-txn, 32 KB arr_metadata cap — 6 tests (created in 04-02-T2)
- [x] `tests/bible/test_arr_metadata_snapshot.py` — arr_metadata round-trips as dict + register starts NULL — 2 tests (created in 04-02-T2)
- [x] `tests/arr/test_media_item_arr_metadata.py` — MediaItem extension populated at discovery for both Sonarr + Radarr, backwards-compat, sparse payload handling — 4 tests (created in 04-02-T1)
- [x] `tests/bible/test_merge_policy_pure.py` — pure-Python lock-precedence + no-op detection — 7 tests (created in 04-03-T1)
- [x] `tests/bible/test_merge_inferred.py` — lock survives, unlocked updates, no-op no event, partial lock, atomic rollback via SQLA event listener, DTO-only return, source enum validated, entity-type-agnostic — 8 tests (created in 04-03-T2)
- [x] `tests/bible/test_carry_forward.py` — BIBLE-06 success-criterion-4 narrative end-to-end (S01E01 → S02E03 unchanged unless inference differs) — 1 test (created in 04-03-T2)
- [x] `tests/bible/test_bible_event_audit.py` — D-32 audit-log contract: required fields, append-only — 2 tests (created in 04-03-T2)
- [x] `tests/output/test_ledger_sqla.py` — LedgerSQLA preserves the Phase-2 Ledger interface (entire test_ledger.py suite duplicated against the SQLA backend) + 2 SQLA-only tests for unknown-path / upsert-existing-entry (created in 04-04-T1)
- [x] `tests/output/test_ledger.py` — existing Phase-2 tests UPDATED to `async def` + `await ledger.check/record` (migrated in 04-04-T1)
- [x] `tests/db/test_migrate_json_ledger.py` — JSON→SQLite one-shot import: happy path, idempotency, collision-skip (DB is newer truth), corrupt-JSON forgiveness, missing-file no-op, Pitfall-5 commit-FIRST/rename-SECOND ordering — 6 tests (created in 04-04-T1)
- [x] `tests/integration/test_translate_engine_async_ledger.py` — Blocker #1 regression guard: line 454 read/batch-failure quarantine `await ledger.record(...)` actually executes (spy counter == 1) — 1 test (created in 04-04-T1)
- [x] `tests/test_cli.py` — 5 new cli wiring tests + existing tests updated for Ledger→LedgerSQLA swap (created/updated in 04-04-T2)

*Phase 4 introduces a new persistence layer; the test scaffolding above IS the Wave 0 work, distributed across the four plans' first tasks. Per the planner-revision policy, Wave 0 is delivered atomically inside Task 1 of each plan (no scaffold-then-skip dance — the conftest fixture runs the real migration on Task 1 commit because models.py and the baseline migration ship in the same commit).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| First-boot startup creates `/config/trezarr.db` with correct PUID/PGID ownership | BIBLE-01 / Phase 7 boundary | Permission/ownership depends on docker runtime, can't assert in unit tests | Run `trezarr translate ...` with no DB present; verify file appears at expected path and is owned by configured user |
| WAL `-wal` / `-shm` sidecar files appear after first write | D-38 | WAL behavior depends on real fs (in-memory SQLite differs) | After running any translate, `ls /config/trezarr.db*` should show `.wal` and `.shm` siblings |
| One-shot JSON ledger migration on real filesystem (rename moves file) | D-37 / Pitfall 5 | os.replace behavior on Synology/NAS-mounted volumes can differ from local tmpfs | After upgrading from Phase 3 to Phase 4, observe `/config/processed_files.json` is renamed to `.migrated.bak` after the first daemon start; processed_file table has the prior entries |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task in 04-01/02/03/04 has an `<automated>` block)
- [x] Wave 0 covers all MISSING references (every test file the plans reference is also listed under Wave 0 above)
- [x] No watch-mode flags (all commands are one-shot `pytest -x`)
- [x] Feedback latency < 30s (Phase 4 isolated runs estimated at ~30s)
- [x] `nyquist_compliant: true` set in frontmatter
- [x] `wave_0_complete: true` set in frontmatter
- [x] Per-Task Verification Map has actual test commands (no `TBD` rows)
- [x] Test file names reconciled with what the plans actually ship (no stub names like `test_store.py` / `test_merge.py` / `test_ledger_sqlite.py` / `test_ledger_migration.py` / `test_translate_with_sqlite_ledger.py` that don't appear in any plan)

**Approval:** approved (revised 2026-06-01 — see checker Blocker #3 fix)

---

## Revision Notes (2026-06-01)

The original draft contained five MISSING-reference rows that did not match the plans:

| Old stub name | What the plans actually ship |
|---------------|------------------------------|
| `tests/bible/test_store.py` | (split into) `tests/bible/test_lazy_series_create.py` + `tests/bible/test_arr_metadata_snapshot.py` (04-02-T2) + `tests/bible/test_merge_inferred.py` + `tests/bible/test_carry_forward.py` + `tests/bible/test_bible_event_audit.py` (04-03-T2) |
| `tests/bible/test_merge.py` | `tests/bible/test_merge_policy_pure.py` (04-03-T1) + `tests/bible/test_merge_inferred.py` (04-03-T2) |
| `tests/bible/test_carry_forward.py` | matches — 04-03-T2 |
| `tests/bible/test_bible_event.py` | `tests/bible/test_bible_event_audit.py` (04-03-T2) |
| `tests/output/test_ledger_sqlite.py` | `tests/output/test_ledger_sqla.py` (04-04-T1) |
| `tests/output/test_ledger_migration.py` | `tests/db/test_migrate_json_ledger.py` (04-04-T1) — moved under tests/db/ because it tests the migration_runner, not the Ledger API |
| `tests/integration/test_translate_with_sqlite_ledger.py` | `tests/integration/test_translate_engine_async_ledger.py` (04-04-T1) — focused regression specifically on the line 454 `await` Blocker #1 |

All Per-Task Verification Map rows now cite the actual `<automated>` command from the plan's verify block. `nyquist_compliant` + `wave_0_complete` flipped to true; Sign-Off checkboxes checked.
