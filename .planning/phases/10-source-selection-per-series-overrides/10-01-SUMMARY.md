---
phase: 10-source-selection-per-series-overrides
plan: "01"
subsystem: testing
tags: [pytest, xfail, tdd, red-scaffold, source-selection, bazarr, llm, migration, wave-0]

# Dependency graph
requires:
  - phase: 09-multi-format-ass-ssa-vtt
    provides: existing test infrastructure (pytest-asyncio, httpx_mock, conftest)
provides:
  - Wave 0 RED test scaffold for all Phase-10 modules (8 test files, 1 new package)
  - xfail stubs for INTG-02 (Bazarr client), SRC-01/SRC-02 (ranking), SVC-05 (overrides), D-108/D-110/D-112/D-113/D-114
  - Nyquist gate satisfied: nyquist_compliant=true, wave_0_complete=true in 10-VALIDATION.md
affects:
  - 10-02-PLAN (Wave 1 — BazarrClient + rank_sources + MediaItem.original_language implementation)
  - 10-03-PLAN (Wave 1 — migration 0003 + LLMClient.call(model=) + PATCH overrides route)
  - 10-04-PLAN (Wave 2 — Overrides UI)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "xfail(strict=False, raises=(ImportError, AssertionError, TypeError)) for new-module stubs (existing pattern)"
    - "xfail(strict=False, raises=(..., Exception)) for stubs that may hit alembic CommandError before the module exists"
    - "AsyncMock + MagicMock pattern for ledger check_by_output_path stubs (D-110 Case 1.5)"
    - "D-108 stubs appended to test_arr_discovery.py — authoritative; no separate test_sonarr.py/test_radarr.py"

key-files:
  created:
    - tests/source_selection/__init__.py
    - tests/arr/test_bazarr.py
    - tests/source_selection/test_rank.py
    - tests/source_selection/test_resolve.py
    - tests/discover/test_gap.py
    - tests/db/test_migration_0003.py
    - tests/llm/test_client.py
  modified:
    - tests/web/test_bible_api.py
    - tests/arr/test_arr_discovery.py
    - .planning/phases/10-source-selection-per-series-overrides/10-VALIDATION.md

key-decisions:
  - "D-108 stubs live in tests/arr/test_arr_discovery.py (two appended stubs) — not in separate test_sonarr.py/test_radarr.py files, consistent with existing project pattern and 10-VALIDATION.md authoritative coverage note"
  - "Migration 0003 downgrade stub uses raises=(..., Exception) to catch alembic CommandError before the migration module exists"
  - "tests/discover/test_gap.py created (new file) — plan references it as 'existing'; it did not exist; stubs added to new file following same convention as test_gap_format.py"
  - "test_foreign_vi_unchanged and test_no_loop_after_upgrade show XPASS — existing gap.py already handles Case 1 (foreign vi, no entry) and Case 2 (already done); XPASS with strict=False is not FAILED"

patterns-established:
  - "Wave 0 RED scaffold: all new Phase-10 modules get xfail stubs before implementation"
  - "D-110 Case 1.5 stubs use AsyncMock to mock check_by_output_path — the ledger method that does not exist yet"

requirements-completed: [INTG-02, SRC-01, SRC-02, SVC-05]

# Metrics
duration: 6min
completed: 2026-06-02
---

# Phase 10 Plan 01: Wave 0 RED Test Scaffold Summary

**xfail stubs for all Phase-10 modules (Bazarr client, source ranking, per-series overrides, migration 0003, LLMClient model override) establishing the Nyquist-compliant RED surface before any implementation**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-02T05:33:22Z
- **Completed:** 2026-06-02T05:39:26Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Created `tests/source_selection/` package with `__init__.py` (new test package for SRC-01/SRC-02)
- Created 5 xfail stubs in `tests/arr/test_bazarr.py` for INTG-02 (BazarrClient fetch/error/path-mapping)
- Created 6 xfail stubs in `tests/source_selection/test_rank.py` for D-107 `rank_sources` + `normalize_original_language`
- Created 4 xfail stubs in `tests/source_selection/test_resolve.py` for D-112 `resolve_effective_settings` (per-series override precedence)
- Created 3 xfail stubs in `tests/discover/test_gap.py` for D-110 Case 1.5 (source-language upgrade, no-clobber, no-loop)
- Created 2 xfail stubs in `tests/db/test_migration_0003.py` for migration 0003 up/down (SVC-05)
- Created 2 xfail stubs in `tests/llm/test_client.py` for D-113 per-call model override
- Extended `tests/web/test_bible_api.py` with 2 xfail stubs for PATCH /series/{id}/overrides (D-114)
- Extended `tests/arr/test_arr_discovery.py` with 2 xfail stubs for D-108 original_language capture (authoritative; no separate test_sonarr.py/test_radarr.py)
- Updated 10-VALIDATION.md frontmatter: `nyquist_compliant: true`, `wave_0_complete: true`

## Task Commits

1. **Task 1: RED stubs — Bazarr client, source_selection package, gap Case 1.5** - `2526800` (test)
2. **Task 2: RED stubs — migration 0003, LLMClient model override, PATCH overrides route, original_language capture** - `ddfa694` (test)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `tests/source_selection/__init__.py` — Empty package init for new source_selection test package
- `tests/arr/test_bazarr.py` — 5 xfail stubs: fetch_episodes, fetch_movies, 4xx error, connection error, path mapping (INTG-02)
- `tests/source_selection/test_rank.py` — 6 xfail stubs: k-drama, us-show, tier-order, fallback-chain, normalize English, normalize Korean (SRC-01/SRC-02 D-107)
- `tests/source_selection/test_resolve.py` — 4 xfail stubs: per-series override wins, null fallback to global source, model override, None series DTO (SVC-05 D-112)
- `tests/discover/test_gap.py` — 3 xfail stubs: source_upgrade_eligible (Case 1.5), foreign_vi_unchanged (D-26 non-regression), no_loop_after_upgrade (D-110)
- `tests/db/test_migration_0003.py` — 2 xfail stubs: upgrade adds source_lang_override/model_override columns, downgrade removes them (SVC-05)
- `tests/llm/test_client.py` — 2 xfail stubs: per-call model override wins, global model used when no override (D-113)
- `tests/web/test_bible_api.py` — Extended with 2 xfail stubs: PATCH stores source+model, PATCH clears with null (D-114 SVC-05)
- `tests/arr/test_arr_discovery.py` — Extended with 2 xfail stubs: sonarr_captures_original_language, radarr_captures_original_language (D-108)
- `.planning/phases/10-source-selection-per-series-overrides/10-VALIDATION.md` — Updated nyquist_compliant: true, wave_0_complete: true

## Decisions Made

1. D-108 stubs appended to existing `tests/arr/test_arr_discovery.py` (not separate files) — consistent with project pattern and authoritative per 10-VALIDATION.md
2. `tests/discover/test_gap.py` created as a new file (it did not previously exist); plan referenced it as "existing" but the project had only `test_gap_format.py` and `test_scan.py`
3. Migration 0003 downgrade stub uses `raises=(..., Exception)` to catch `alembic.util.exc.CommandError` when migration file doesn't exist yet
4. XPASS on `test_foreign_vi_unchanged` and `test_no_loop_after_upgrade` is expected — existing gap.py Case 1/Case 2 logic already handles these; `strict=False` permits XPASS

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Migration 0003 downgrade stub caused FAILED (not XFAIL)**
- **Found during:** Task 2 verification
- **Issue:** `raises=(ImportError, AssertionError, TypeError)` did not include `alembic.util.exc.CommandError`; the downgrade target `"0002_job_queue"` was not recognized by Alembic, causing a `CommandError` that fell outside the xfail raises tuple → FAILED
- **Fix:** Added `Exception` to the raises tuple and improved the downgrade to use dynamic revision ID lookup via `importlib.import_module`
- **Files modified:** `tests/db/test_migration_0003.py`
- **Verification:** All test_migration_0003.py stubs are XFAIL; zero FAILED
- **Committed in:** `ddfa694` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — stub caused FAILED not XFAIL)
**Impact on plan:** Necessary fix to ensure all stubs are properly XFAIL. No scope creep.

## Issues Encountered

None beyond the auto-fixed migration downgrade CommandError.

## Next Phase Readiness

- Wave 0 scaffold complete; all Phase-10 test stubs in place
- `nyquist_compliant: true` and `wave_0_complete: true` in 10-VALIDATION.md
- Wave 1 plans (10-02, 10-03) may proceed — each implementation plan has deterministic verification targets
- Full suite: 334 passed, 7 skipped, 28 xfailed, 12 xpassed, 0 failed

---
*Phase: 10-source-selection-per-series-overrides*
*Completed: 2026-06-02*
