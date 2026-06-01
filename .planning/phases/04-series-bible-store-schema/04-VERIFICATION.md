---
phase: 04-series-bible-store-schema
verified: 2026-06-01T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run `trezarr run --once` against a live Sonarr instance with at least one series that has a source subtitle"
    expected: "A series row appears in the SQLite `series` table with arr_metadata populated; the processed_file table records a 'done' row after a successful translation; the vi.srt sidecar is written to disk"
    why_human: "End-to-end behavior depends on a live *arr stack and LLM endpoint — cannot be exercised with automated tests alone"
  - test: "Verify the CR-01 engine-dispose warning behavior in a real CLI run"
    expected: "No 'RuntimeError: Event loop is closed' or 'Task was destroyed but it is pending' warnings appear in stderr after `trezarr run --once` exits"
    why_human: "The REVIEW.md CR-01 finding identifies a missing `await engine.dispose()` in the production `_run_once` function. The automated test suite passes (tests mock the engine), but runtime behavior under a real asyncio.run() teardown cannot be confirmed without a real run"
---

# Phase 4: Series Bible Store & Schema Verification Report

**Phase Goal:** A persistent, versioned per-series Series Bible exists that records characters, terms, and register, carries forward across episodes, and supports per-field human locks — the stable schema everything downstream depends on.
**Verified:** 2026-06-01T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|---------|
| SC-1 | A per-series Bible persists to SQLite, is loaded as context at the start of each episode, and is updated (versioned, append-with-provenance) after each | ✓ VERIFIED | `get_or_create_series` + `load_series_bible` + `merge_inferred` in `trezarr/bible/store.py`; `LedgerSQLA` wired in `cli.py` Step 3.5; 208 tests pass including end-to-end CLI smoke test |
| SC-2 | The Bible records Characters (name in original Latin form, gender, rough age, role) and a Term Dictionary (proper nouns/titles/places/jargon → fixed Vietnamese rendering, incl. name-romanization policy) with per-field lock support | ✓ VERIFIED | `Character` model lines 95–122, `TermDictionary` model lines 125–150 of `trezarr/bible/models.py`; `upsert_character`, `upsert_term`, `merge_inferred` in `store.py`; `tests/bible/test_carry_forward.py`, `tests/bible/test_merge_inferred.py` (16 tests) |
| SC-3 | The Bible records a per-series Register/tone; Phase 4 PERSISTS the column (register=NULL by design); Phase 5 POPULATES via merge_inferred | ✓ VERIFIED | `Series.register: Mapped[str \| None] = mapped_column(String, default=None)` at model line 83; migration col is `nullable=True`; `get_or_create_series` explicitly sets `register=None`; `MERGEABLE_FIELDS["series"] = frozenset({"register"})` so Phase 5 can call `merge_inferred` to populate it; `test_register_starts_null` passes |
| SC-4 | A character/term established in S01E01 is carried forward unchanged to a later episode unless a locked edit or logged event changes it (precedence: human lock > prior value > new inference) | ✓ VERIFIED | `compute_field_changes` in `trezarr/bible/merge.py` skips locked fields and no-ops; `_merge_inferred_in_session` re-reads fresh row inside transaction (HIGH finding fix); `tests/bible/test_carry_forward.py::test_character_set_in_s01e01_returns_unchanged_at_s02e03` passes end-to-end |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/bible/models.py` | 7 SQLAlchemy 2.0 typed models with D-31/D-32/D-33/D-34/D-35 column shapes | ✓ VERIFIED | All 7 classes present: Series, Character, TermDictionary, AddressMap, RelationshipEvent, BibleEvent, ProcessedFile; CHECK constraints and indexes verified in source |
| `trezarr/bible/store.py` | `get_or_create_series`, `load_series_bible`, `upsert_character`, `upsert_term`, `merge_inferred`, private helpers | ✓ VERIFIED | All 8 public functions + 3 private helpers present; VALID_SOURCES and MERGEABLE_FIELDS constants present |
| `trezarr/bible/merge.py` | Pure-Python `get_locked_fields` + `compute_field_changes` — no SQLAlchemy, no async | ✓ VERIFIED | 81-line pure module; verified import-graph: no sqlalchemy, no async, no IO |
| `trezarr/bible/dto.py` | SeriesDTO, CharacterDTO, TermDTO, BibleEventDTO, SeriesBibleDTO with `from_attributes=True`; no SQLAlchemy imports | ✓ VERIFIED | 5 Pydantic classes; `model_config = ConfigDict(from_attributes=True)` on each; zero SQLAlchemy import lines |
| `alembic/versions/0001_baseline_bible_schema.py` | Single baseline migration creating all 7 tables with CHECK constraints + indexes; reversible downgrade | ✓ VERIFIED | `upgrade()` creates 7 tables in FK-safe order with 3 CHECK constraints and 3 composite indexes; `downgrade()` drops all in reverse order |
| `trezarr/db/engine.py` | `build_engine(settings)` with `event.listens_for(engine.sync_engine, "connect")` PRAGMA listener | ✓ VERIFIED | Line 46: `@event.listens_for(engine.sync_engine, "connect")` — WAL, synchronous=NORMAL, FK=ON per-connection |
| `trezarr/db/migration_runner.py` | `run_migrations_to_head` + `migrate_json_ledger_if_needed` with Pitfall-5 ordering | ✓ VERIFIED | Both async functions present; commit-first/rename-second order confirmed at lines 228/241 |
| `trezarr/output/ledger_sqla.py` | `LedgerSQLA` with async `check`/`record` backed by `processed_file` table | ✓ VERIFIED | Class present; `check` and `record` are `async def`; SELECT-then-INSERT/UPDATE upsert pattern |
| `trezarr/output/_ledger_protocol.py` | `@runtime_checkable class LedgerProtocol(Protocol)` declaring async contract | ✓ VERIFIED | File exists (2.4K); `@runtime_checkable` + `async def check`, `async def record`, `@staticmethod content_hash` |
| `trezarr/config.py` | 4 Phase-4 settings fields: bible_db_url, bible_db_run_migrations_on_startup, bible_db_enable_wal, bible_db_enforce_fk | ✓ VERIFIED | All 4 fields confirmed by grep |
| `trezarr/cli.py` | Step 3.5 wiring: build_engine + run_migrations_to_head + migrate_json_ledger_if_needed + LedgerSQLA | ✓ VERIFIED | All 4 imports present; wired in correct order before discovery |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `trezarr/db/engine.py` | PRAGMA foreign_keys/WAL/synchronous | `event.listens_for(engine.sync_engine, "connect")` | ✓ WIRED | Line 46 confirmed |
| `trezarr/db/migration_runner.py` | `alembic.command.upgrade` | `await conn.run_sync(_do_upgrade, cfg)` | ✓ WIRED | Line 73 confirmed |
| `alembic/env.py` | `trezarr.bible.models` | live `from trezarr.bible import models  # noqa: F401` import | ✓ WIRED | Not a stub — live import verified in 04-01 SUMMARY |
| `trezarr/config.py` | `trezarr/db/engine.py` | `settings.bible_db_url` passed to `build_engine` | ✓ WIRED | `build_engine(settings)` at cli.py line 153 |
| `trezarr/translate/engine.py` (all call sites) | `await ledger.check / await ledger.record` | `await` prefix on every production call | ✓ WIRED | Grep confirms 7 awaited calls in engine.py; zero unawaited production call sites found by dynamic grep gate test |
| `trezarr/cli.py` | `LedgerSQLA(session_factory)` | Step 3.5 startup sequence | ✓ WIRED | cli.py line 156 confirmed |
| `trezarr/bible/store.py::merge_inferred` | `compute_field_changes + get_locked_fields` | delegated to `_merge_inferred_in_session` which calls these on fresh DB row | ✓ WIRED | store.py lines 291-298 confirmed |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `store.py::load_series_bible` | `row.characters`, `row.terms` | `selectinload(Series.characters)` + `selectinload(Series.terms)` from SQLite | Yes — real DB query, not static | ✓ FLOWING |
| `store.py::get_or_create_series` | `arr_metadata_snapshot` | MediaItem payload from Phase-3 Sonarr/Radarr discovery | Yes — arrives from live arr API discovery | ✓ FLOWING |
| `store.py::merge_inferred` | `fresh_row` | `session.get(model_cls, entity_dto.id)` inside active transaction | Yes — real DB re-read inside transaction | ✓ FLOWING |
| `ledger_sqla.py::check` | `row` | `select(ProcessedFile).where(source_path==key)` | Yes — real DB query | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 7 tables registered in Base.metadata | `uv run python -c "from trezarr.db.base import Base; from trezarr.bible import models; assert sorted(Base.metadata.tables.keys()) == ['address_map','bible_event','character','processed_file','relationship_event','series','term_dictionary']"` | Tables match exactly | ✓ PASS |
| All 208 tests pass | `uv run pytest -x --tb=short -q` | 208 passed, 1 skipped, 3 warnings | ✓ PASS |
| Phase-4 specific test suite (72 tests) | `uv run pytest tests/db/ tests/bible/ tests/output/test_ledger_sqla.py tests/db/test_migrate_json_ledger.py tests/integration/test_translate_engine_async_ledger.py -q` | 72 passed | ✓ PASS |
| Grep gate: zero unawaited ledger calls | dynamic grep over `trezarr/**/*.py` | Only comment/docstring matches; zero production unawaited hits | ✓ PASS |
| merge.py is pure (no sqlalchemy/async) | import-graph inspection | No sqlalchemy or await in merge.py source | ✓ PASS |
| dto.py has no SQLAlchemy imports | import-graph source inspection | No sqlalchemy import lines in dto.py | ✓ PASS |

### Probe Execution

No probe scripts declared for this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| BIBLE-01 | 04-01, 04-02, 04-04 | Persistent per-series Bible, loaded as context, updated after each episode | ✓ SATISFIED | `get_or_create_series` + `load_series_bible` in store.py; `LedgerSQLA` replaces JSON ledger; cli.py Step 3.5 wires DB startup |
| BIBLE-02 | 04-01, 04-03 | Bible records Characters (name, gender, rough_age, role) | ✓ SATISFIED | `Character` model with all 4 columns; `upsert_character` + `merge_inferred` tested; 04-03 carry-forward test covers S01E01→S02E03 |
| BIBLE-04 | 04-01, 04-03 | Bible records Term Dictionary (source_term → vietnamese_rendering, category) with per-field lock | ✓ SATISFIED | `TermDictionary` model with all columns; `upsert_term` + `merge_inferred` with MERGEABLE_FIELDS; locked_fields JSON column on all entity tables |
| BIBLE-05 | 04-01, 04-02 | Register/tone persisted with schema support; arr_metadata snapshot captured | ✓ SATISFIED | `series.register` nullable column; `series.arr_metadata` JSON snapshot; MERGEABLE_FIELDS["series"]={"register"} for Phase 5 to populate; `test_register_starts_null` passes |
| BIBLE-06 | 04-01, 04-03 | Bible carried forward across episodes — character unchanged S01E01→S02E03 unless locked edit or logged event | ✓ SATISFIED | `compute_field_changes` skips no-ops; end-to-end test `test_character_set_in_s01e01_returns_unchanged_at_s02e03` passes |

All 5 required Phase-4 requirement IDs (BIBLE-01, BIBLE-02, BIBLE-04, BIBLE-05, BIBLE-06) are satisfied. BIBLE-03 (Phase 5) and BIBLE-07 (Phase 6) are not Phase-4 requirements — their tables are created empty as designed.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `trezarr/bible/dto.py` | 35, 140 | `UserWarning: Field name "register" shadows an attribute in parent "BaseModel"` — Pydantic v2 shadow warning on `SeriesDTO.register` and `SeriesBibleDTO.register` | WARNING (CR-02 in 04-REVIEW.md) | No functional defect today; accepted cosmetic warning per 04-02 SUMMARY; risk: future Pydantic minor could promote this to hard error. Known advisory, not phase-failing. |
| `trezarr/cli.py` | ~152–165 | Missing `await engine.dispose()` in `_run_once`; AsyncEngine built in `_run_once` is never disposed | WARNING (CR-01 in 04-REVIEW.md) | Causes `RuntimeError: Event loop is closed` warnings during asyncio teardown in production. Not observable in automated tests (which mock the engine). Known advisory per phase instructions, not phase-failing. |
| `trezarr/bible/store.py` | 291 | `_merge_inferred_in_session` calls `session.get(type(row), row.id)` then immediately re-fetches inside the same session — identity map returns the same Python object | WARNING (WR-01 in 04-REVIEW.md) | Wasted round-trip; misleading comment about "freshness" — actual correctness relies on the session being opened after any concurrent commit, not on the second get(). Not phase-failing. |

No TBD/FIXME/XXX debt markers found in production files modified by this phase.

### Human Verification Required

#### 1. Live *arr integration smoke test

**Test:** Start Trezarr against a real Sonarr instance with at least one series that has an existing source subtitle. Run `trezarr run --once`. Inspect the SQLite database at `/config/trezarr.db`.
**Expected:** A `series` row exists with `arr_metadata` containing genres/overview/year fields from Sonarr. `register` is NULL. A `processed_file` row with `status='done'` and the correct `source_path` exists. The `.vi.srt` sidecar file is written next to the source file.
**Why human:** Requires a live *arr stack + LLM endpoint. The automated end-to-end CLI smoke test (tests/test_cli.py::test_run_once_end_to_end_smoke_with_temp_sqlite) uses mocked discovery and a patched LLM client — it does not exercise real *arr API payloads or the actual filesystem path-mapping logic.

#### 2. CR-01 engine-dispose runtime behavior

**Test:** Run `trezarr run --once` against a real or mocked instance with `--log-level=debug`. Observe stderr output after the command exits.
**Expected:** No `RuntimeError: Event loop is closed`, `Task was destroyed but it is pending`, or aiosqlite worker thread warnings appear.
**Why human:** The CR-01 REVIEW finding identifies that `_run_once` in `trezarr/cli.py` never calls `await engine.dispose()`. This causes aiosqlite pool teardown warnings under a real `asyncio.run()` event loop. The automated test suite passes because the tests mock `build_engine` — the real asyncio teardown path is not exercised.

---

## Gaps Summary

No blocking gaps. All 4 observable truths are verified, all required artifacts exist and are substantively implemented and wired, all key links are confirmed, and the full test suite (208 passed, 1 skipped) confirms behavioral correctness.

Two known advisory issues from 04-REVIEW.md (CR-01: engine-dispose leak; CR-02: Pydantic register shadow warning) are pre-disclosed in the phase instructions as "advisory and warning-only; treat as known issues to flag but not phase-failing." Both are recorded above in Anti-Patterns and in the human verification section.

The `status: human_needed` classification reflects that two human verification items exist (live *arr integration and runtime CR-01 behavior) — not that any automated truth failed.

---

_Verified: 2026-06-01T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
