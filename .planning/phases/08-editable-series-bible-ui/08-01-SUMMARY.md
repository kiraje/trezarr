---
phase: "08"
plan: "01"
subsystem: "test-scaffold"
tags: ["tdd", "xfail", "bible", "web-api", "reconcile"]
dependency_graph:
  requires: []
  provides:
    - "RED test surface for BIBLE-08/09 store-layer behaviors (8 xfail stubs)"
    - "RED test surface for BIBLE-08 API-layer behaviors and D-39 boundary (8 xfail stubs)"
    - "D-90 H1 regression stub for KINSHIP_RECIPROCAL bác/cháu gap (1 xfail stub)"
  affects:
    - "tests/bible/test_human_edit.py"
    - "tests/web/test_bible_api.py"
    - "tests/translate/test_reconcile.py"
tech_stack:
  added: []
  patterns:
    - "xfail(raises=(ImportError, AssertionError, TypeError), strict=False) — Wave-0 RED scaffold pattern"
    - "All trezarr imports deferred into test bodies to trigger ImportError on xfail"
key_files:
  created:
    - "tests/bible/test_human_edit.py"
    - "tests/web/test_bible_api.py"
  modified:
    - "tests/translate/test_reconcile.py"
decisions:
  - "xfail(strict=False) with raises=(ImportError, AssertionError, TypeError) for new-module stubs — prevents FAILED when module doesn't exist yet"
  - "xfail(raises=(AssertionError,)) for test_kinship_reciprocal_bac_chau — module exists; only the dict key is missing"
  - "Added import pytest to test_reconcile.py (was missing; needed for @pytest.mark.xfail)"
metrics:
  duration: "5 minutes"
  completed: "2026-06-02"
  tasks_completed: 2
  files_changed: 3
---

# Phase 08 Plan 01: Wave-0 RED Test Scaffold Summary

**One-liner:** 17 xfail stubs across 3 test files creating the Nyquist-compliant RED surface for BIBLE-08/09 store writes, REST API layer, and D-90 kinship reciprocal fix.

## What Was Built

Wave-0 RED test scaffold for Phase 8. Two new test files and one extension to an existing test file establish the automated verification surface that Plans 02-04 will turn GREEN incrementally.

### tests/bible/test_human_edit.py (new — 8 stubs)

Store-layer behavioral tests targeting `apply_human_edit_character`, `apply_human_edit_term`, and `apply_human_edit_series` (Plan 08-02 targets):

1. `test_lock_state_in_dto` — BIBLE-08 c1: locked_fields visible in DTO
2. `test_locked_field_survives_merge` — BIBLE-08 c2: locked field not overwritten by merge_inferred
3. `test_locked_fields_persisted` — BIBLE-08 c2: JSON dirty-tracking reassign-not-append (D-80)
4. `test_bible_event_emitted_on_lock` — BIBLE-08 c2: BibleEvent(source="lock") in same txn (D-32)
5. `test_locked_pair_survives_reconcile` — BIBLE-09 c3: locked pair survives reconcile_attributions
6. `test_locked_pair_propagates_to_next_episode` — BIBLE-09 c3: carry-forward + lock combo
7. `test_locked_term_survives_merge` — BIBLE-08 c1: Term entity type lockable
8. `test_locked_register_survives` — BIBLE-08 c1: Series register lockable (CR-02 register_value alias)

### tests/web/test_bible_api.py (new — 8 stubs)

API-layer tests targeting `trezarr.web.routes.bible` (Plan 08-03 target):

1. `test_get_series_list` — BIBLE-08 c1: GET /api/series returns bounded list (LIMIT 500)
2. `test_get_series_bible` — BIBLE-08 c1: GET /api/series/{id}/bible full Bible response
3. `test_lock_address_map_missing_term_rejected` — BIBLE-08 c2 / T-08-01: empty address_term → HTTP 422
4. `test_write_acquires_series_lock` — D-81: per-series asyncio.Lock acquired on write
5. `test_get_field_history` — D-82 / T-08-02: GET .../history returns BibleEventDTOs (LIMIT 100)
6. `test_bible_route_does_not_import_sqla` — D-39: bible route must not import SQLAlchemy
7. `test_delete_address_pair` — D-83: DELETE /api/series/{id}/address-map/{aid}
8. `test_delete_term` — D-83: DELETE /api/series/{id}/terms/{tid}

### tests/translate/test_reconcile.py (appended — 1 stub)

1. `test_kinship_reciprocal_bac_chau` — D-90 H1: bác/cháu forward+reverse keys in KINSHIP_RECIPROCAL

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: store-layer stubs | 9229e15 | tests/bible/test_human_edit.py |
| Task 2: API stubs + D-90 stub | 52274b8 | tests/web/test_bible_api.py, tests/translate/test_reconcile.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing import] Added `import pytest` to tests/translate/test_reconcile.py**
- **Found during:** Task 2
- **Issue:** test_reconcile.py had no `import pytest` at module level; the new `@pytest.mark.xfail` decorator on the appended stub requires it
- **Fix:** Added `import pytest` after `from __future__ import annotations` — same pattern as all other test files in the project
- **Files modified:** tests/translate/test_reconcile.py
- **Commit:** 52274b8

## Known Stubs

All 17 tests are intentional xfail stubs — this is a RED-scaffold plan. They will be promoted to GREEN in Plans 08-02 and 08-03.

## Threat Flags

None — test-only scaffold; no new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

- tests/bible/test_human_edit.py: FOUND
- tests/web/test_bible_api.py: FOUND
- tests/translate/test_reconcile.py (appended): FOUND
- Commit 9229e15 (Task 1): FOUND
- Commit 52274b8 (Task 2): FOUND
