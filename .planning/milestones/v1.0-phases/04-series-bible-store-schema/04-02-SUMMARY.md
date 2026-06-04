---
phase: 04-series-bible-store-schema
plan: "02"
subsystem: bible-store
tags: [bible-store, series, register, arr-metadata, dto-boundary, lazy-creation, mvp-vertical-slice, tdd]
dependency_graph:
  requires:
    - trezarr/bible/models.py (Phase 04-01 — 7 SQLAlchemy models)
    - trezarr/db/engine.py + session.py + migration_runner.py (Phase 04-01 — DB foundation)
    - tests/db/conftest.py (Phase 04-01 — db_engine + session_factory fixtures)
    - trezarr/arr/sonarr.py (Phase 03 — MediaItem dataclass base shape)
    - trezarr/arr/radarr.py (Phase 03 — Radarr discovery)
  provides:
    - trezarr/bible/dto.py (SeriesDTO, CharacterDTO, TermDTO, BibleEventDTO, SeriesBibleDTO)
    - trezarr/bible/store.py (get_or_create_series, load_series_bible)
    - trezarr/arr/sonarr.py (MediaItem extended with 8 Phase-4 fields)
  affects:
    - trezarr/arr/radarr.py (discovery populates arr_metadata fields at creation site)
tech_stack:
  added: []
  patterns:
    - Pydantic v2 from_attributes=True ORM bridge (dto.py → store.py boundary)
    - SELECT+INSERT in single session.begin() block (D-32 atomic get-or-create)
    - selectinload for eager relationship loading in load_series_bible()
    - json.dumps(ensure_ascii=False).encode('utf-8') for Vietnamese UTF-8 byte cap
    - TDD RED/GREEN/REFACTOR: failing tests committed before implementation
key_files:
  created:
    - trezarr/bible/dto.py
    - trezarr/bible/store.py
    - tests/arr/test_media_item_arr_metadata.py
    - tests/bible/test_dto_boundary.py
    - tests/bible/test_lazy_series_create.py
    - tests/bible/test_arr_metadata_snapshot.py
  modified:
    - trezarr/arr/sonarr.py (MediaItem + discover_sonarr_items)
    - trezarr/arr/radarr.py (discover_radarr_items)
decisions:
  - "MediaItem extended at discovery layer (Phase 4 owns the extension per RESEARCH Open Question 1)"
  - "DTO register field shadows ABCMeta.register method — accepted cosmetic warning; field name must match column 1:1 per D-39"
  - "No new package installs — inherits sqlalchemy[asyncio]/aiosqlite/alembic from Phase 04-01"
metrics:
  duration_seconds: 900
  completed_date: "2026-06-01"
  tasks_completed: 2
  files_changed: 8
---

# Phase 4 Plan 02: Lazy Series Creation + arr_metadata Snapshot + DTO Boundary Summary

Lazy per-series Bible persistence with arr_metadata snapshot, Pydantic DTO boundary at the store surface, and MediaItem extended at the Sonarr/Radarr discovery layer — first vertical slice enabling Phase 5's register inference without re-calling *arr APIs.

## What Was Built

### Task 1: MediaItem arr_metadata Extension (TDD)

**RED commit (`f1235f8`):** Failing tests in `tests/arr/test_media_item_arr_metadata.py` — 4 tests verifying arr_kind/tvdb_id/tmdb_id/genres/overview/year/network/runtime field presence and population. All failed with `AttributeError: 'MediaItem' object has no attribute 'arr_kind'`.

**GREEN commit (`8c57657`):** MediaItem extended in `trezarr/arr/sonarr.py` and discovery sites updated in both `sonarr.py` and `radarr.py`:
- 8 new fields appended after the Phase-3 fields: `arr_kind`, `tvdb_id`, `tmdb_id`, `genres`, `overview`, `year`, `network`, `runtime` — all default `None` (backwards compatible)
- `discover_sonarr_items` populates `arr_kind="sonarr"`, `tvdb_id=series.get("tvdbId")`, and the 5 metadata fields via defensive `.get()` access
- `discover_radarr_items` populates `arr_kind="radarr"`, `tmdb_id=movie.get("tmdbId")`, `tvdb_id=movie.get("tvdbId")` (defensive), and metadata fields; `network` intentionally omitted (movies have none)
- All 4 new tests pass; all 11 existing `tests/arr/` tests continue to pass (15 total)

### Task 2: Bible DTO Boundary + Store (TDD)

**RED commit (`3dcac2b`):** 3 test files committed with 12 failing tests:
- `test_dto_boundary.py` (Tests 1, 2, 12): D-39 import-graph contract, SeriesDTO ORM bridge, BibleEventDTO datetime coercion
- `test_lazy_series_create.py` (Tests 3, 4, 5, 6, 9, 10): lazy creation, idempotency, distinct arr_kind rows, tvdb/tmdb capture, single-transaction atomicity, 32 KB size cap
- `test_arr_metadata_snapshot.py` (Tests 7, 8, 11): dict round-trip, register=NULL invariant, Vietnamese UTF-8 byte cap

**GREEN commit (`ee6d73d`):**

`trezarr/bible/dto.py`:
- 5 Pydantic BaseModel classes: `SeriesDTO`, `CharacterDTO`, `TermDTO`, `BibleEventDTO`, `SeriesBibleDTO`
- Each with `model_config = ConfigDict(from_attributes=True)` for ORM bridge
- `BibleEventDTO.created_at: datetime | None` (not `Any`) — Pydantic v2 coerces ISO-8601 strings
- Zero SQLAlchemy imports (D-39); verified by import-graph contract test

`trezarr/bible/store.py`:
- `get_or_create_series()`: SELECT+INSERT in single `session.begin()` block (D-32 atomicity); arr_metadata size cap using `json.dumps(ensure_ascii=False).encode('utf-8')`; register=None on creation (D-35)
- `load_series_bible()`: `selectinload(Series.characters, Series.terms)` for eager loading; returns `SeriesBibleDTO` with fully-populated lists
- `MAX_ARR_METADATA_BYTES = 32 * 1024` exported constant
- `processed_file.source_path` case-sensitivity caveat documented in module docstring

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| tests/arr/test_media_item_arr_metadata.py | 4 | PASSED |
| tests/arr/ (full) | 15 | PASSED |
| tests/bible/test_dto_boundary.py | 3 | PASSED |
| tests/bible/test_lazy_series_create.py | 6 | PASSED |
| tests/bible/test_arr_metadata_snapshot.py | 3 | PASSED |
| tests/bible/test_models.py | 7 | PASSED |
| tests/db/ | 10 | PASSED |
| **Total new tests** | **16** | **PASSED** |
| Phase 1/2/3 + 04-01 regression | 144 + 1 skipped | PASSED |
| **Full suite** | **160 passed, 1 skipped** | **PASSED** |

## Deviations from Plan

### Auto-fixed Issues

None. Plan executed exactly as specified.

### Accepted Warnings

**1. [Cosmetic] Pydantic UserWarning: `register` field shadows ABCMeta.register method**
- **Found during:** Task 2 (first test run)
- **Issue:** `SeriesDTO.register` and `SeriesBibleDTO.register` produce `UserWarning: Field name "register" in "SeriesDTO" shadows an attribute in parent "BaseModel"` because `ABCMeta.register()` is a metaclass method on the Python ABCMeta → BaseModel hierarchy.
- **Decision:** Accepted. The field name must match the SQLAlchemy column name 1:1 per D-39 (column is `series.register`). The warning is cosmetic — Pydantic handles the field definition correctly, `model_validate()` works, and the tests pass. Renaming the field would break the D-39 no-rename contract. Documented here.
- **Impact:** Zero functional impact. 2 warnings appear in `pytest --w` output.

## Known Stubs

None. All 5 DTO classes are fully defined. `get_or_create_series()` and `load_series_bible()` are complete implementations. No hardcoded empty values, no placeholder text, no TODO/FIXME in production code.

## TDD Gate Compliance

| Gate | Commit | Message Pattern |
|------|--------|-----------------|
| Task 1 RED | `f1235f8` | `test(04-02): add failing tests for MediaItem arr_metadata extension` |
| Task 1 GREEN | `8c57657` | `feat(04-02): extend MediaItem with arr_metadata fields + populate at discovery` |
| Task 2 RED | `3dcac2b` | `test(04-02): add failing tests for DTO boundary + store lazy creation` |
| Task 2 GREEN | `ee6d73d` | `feat(04-02): add Bible DTO boundary + store with get_or_create_series + load_series_bible` |

Both RED/GREEN gates present. REFACTOR not needed — code is clean on first pass.

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundaries introduced. All changes are internal persistence and discovery-layer field extensions.

| Flag | File | Description |
|------|------|-------------|
| T-04-05 (mitigated) | trezarr/bible/store.py | 32 KB arr_metadata cap enforced before INSERT; uses ensure_ascii=False for Vietnamese UTF-8 correctness |
| T-04-06 (accepted) | trezarr/bible/store.py | source_path uniqueness caveat documented in module docstring; v1 trade-off |
| T-04-07 (mitigated) | trezarr/bible/dto.py | import-graph contract test (test_no_sqlalchemy_in_bible_dto_namespace) verifies D-39 boundary |

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| trezarr/bible/dto.py exists | PASSED |
| trezarr/bible/store.py exists | PASSED |
| tests/arr/test_media_item_arr_metadata.py exists | PASSED |
| tests/bible/test_dto_boundary.py exists | PASSED |
| tests/bible/test_lazy_series_create.py exists | PASSED |
| tests/bible/test_arr_metadata_snapshot.py exists | PASSED |
| All 4 commits (f1235f8, 8c57657, 3dcac2b, ee6d73d) in git history | PASSED |
| 160 tests pass, 1 skipped, 0 failed (full suite) | PASSED |
| No SQLAlchemy import lines in dto.py | PASSED |
| ensure_ascii=False in store.py size cap | PASSED |
| BibleEventDTO.created_at is datetime | PASSED |
