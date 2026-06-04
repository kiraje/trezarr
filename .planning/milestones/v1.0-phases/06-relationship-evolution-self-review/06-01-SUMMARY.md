---
phase: 06
plan: 01
subsystem: tests
tags: [tdd, wave-0, red-stubs, relationship-events, self-review, bible]
dependency_graph:
  requires: []
  provides:
    - 10 pytest node IDs for Phase-6 Wave-0 test scaffold
  affects:
    - tests/bible/test_relationship_events.py
    - tests/translate/test_self_review.py
    - tests/translate/test_reconcile.py
tech_stack:
  added: []
  patterns:
    - xfail(strict=False, raises=(ImportError, AssertionError, TypeError)) for Wave-0 RED stubs
    - SimpleNamespace for DTOs not yet created in Wave-0 test helpers
key_files:
  created:
    - tests/bible/test_relationship_events.py
    - tests/translate/test_self_review.py
  modified:
    - tests/translate/test_reconcile.py
decisions:
  - "_make_bible extended with relationship_events=None parameter (safe default []) — backward compatible"
  - "3 new reconcile stubs show XPASS for BIBLE-07-D/E because Phase-5 already implements lock and safe-default paths — strict=False permits this; the stubs remain as regression guards for Wave-1 changes"
metrics:
  duration: 3 minutes
  completed: 2026-06-02
  tasks_completed: 2
  files_created: 2
  files_modified: 1
requirements:
  - BIBLE-07
  - ENG-05
---

# Phase 6 Plan 01: RED Test Scaffold (Wave 0) Summary

Wave-0 RED stubs for Phase-6 relationship-evolution + self-review: 10 xfail test nodes across 3 files, full suite exits 0.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create tests/bible/test_relationship_events.py (BIBLE-07-A, B, F stubs) | 509945d | tests/bible/test_relationship_events.py |
| 2 | Create tests/translate/test_self_review.py (ENG-05-A/B/C/D) + extend test_reconcile.py (BIBLE-07-C/D/E) | a9a8ef3 | tests/translate/test_self_review.py, tests/translate/test_reconcile.py |

## What Was Built

### Task 1: tests/bible/test_relationship_events.py

3 xfail stubs covering BIBLE-07:
- `test_relationship_event_written_to_db` (BIBLE-07-A): asserts `record_relationship_event` returns a `RelationshipEventDTO` with matching `character_a_id` and `character_b_id`.
- `test_load_series_bible_includes_events` (BIBLE-07-B): asserts `load_series_bible` returns a `SeriesBibleDTO` with `relationship_events` list length >= 1.
- `test_name_matching_case_insensitive` (BIBLE-07-F): asserts `merge_bible_analysis` resolves "ALICE" to stored "alice" via case-insensitive lookup (CR-01 contract).

Also confirmed `tests/bible/conftest.py` already present with `db_engine`/`session_factory` re-export.

### Task 2: tests/translate/test_self_review.py (new) + test_reconcile.py (extended)

4 xfail stubs in test_self_review.py covering ENG-05:
- `test_pass4_corrects_violation_before_gate` (ENG-05-A): asserts `_review_batch` returns corrected text for a pronoun violation.
- `test_pass4_failure_fallback_no_quarantine` (ENG-05-B): asserts `_review_batch` returns `None` (not raises) when LLM raises.
- `test_pass4_disabled_skips_review` (ENG-05-C): asserts `_review_batch` is not called when `enable_self_review=False`.
- `test_sentinel_failure_fallback_per_batch` (ENG-05-D): asserts `_review_batch` returns `None` when sentinel token is dropped by LLM.

3 xfail stubs appended to test_reconcile.py covering BIBLE-07-C/D/E:
- `test_transition_authorizes_terms_change` (BIBLE-07-C)
- `test_lock_beats_transition` (BIBLE-07-D)
- `test_no_transition_no_survivors_safe_default` (BIBLE-07-E)

Extensions to test_reconcile.py:
- `_make_relationship_event()` helper added (SimpleNamespace shape matching future RelationshipEventDTO)
- `_make_bible()` extended with `relationship_events=[]` parameter (additive, backward compatible)

## Verification Results

```
uv run pytest tests/bible/test_relationship_events.py tests/translate/test_self_review.py tests/translate/test_reconcile.py -x -q
# 4 passed, 8 xfailed, 2 xpassed in 0.35s (exit 0)

uv run pytest -x -q
# 226 passed, 1 skipped, 8 xfailed, 2 xpassed, 1 warning in 5.64s (exit 0)
```

All 10 Phase-6 node IDs from 06-VALIDATION.md are present and collected.

## Deviations from Plan

### Observation: 2 XPASS results for BIBLE-07-D/E stubs

**Found during:** Task 2 — test_lock_beats_transition and test_no_transition_no_survivors_safe_default ran against the real `reconcile_attributions` implementation.

**Why:** Phase-5 already implemented the lock-check branch and the safe-default-for-no-survivors path. The stubs exercise these existing paths via `_make_bible(relationship_events=[])` which is a valid `reconcile_attributions` call that exercises the pre-existing code. The new BIBLE-07 Phase-6 behavior (transition-aware branch) is NOT yet implemented — `test_transition_authorizes_terms_change` correctly stays XFAIL.

**Impact:** XPASS with `strict=False` exits 0. The stubs remain valuable as regression guards for the Wave-1 changes to `reconcile_attributions` that add the transition precedence branch.

**Fix:** None needed. `strict=False` is the project-standard for Wave-0 stubs (STATE.md D-08 / Phase-5 precedent). The two XPASS stubs will revert to XFAIL when Wave-1 changes the reconcile logic (if the transition branch interferes) and then to PASS permanently when Wave-2 completes.

## Known Stubs

All 10 test stubs are intentional Wave-0 scaffolding. Production code for the behaviors under test does not yet exist (BIBLE-07 store/analyze/reconcile extensions, ENG-05 engine pass-4). Waves 1 and 2 will implement the production code to turn these stubs GREEN.

## Threat Flags

None — test-only files, no production data, no network endpoints, no new packages.

## Self-Check: PASSED

- [x] tests/bible/test_relationship_events.py created — FOUND
- [x] tests/translate/test_self_review.py created — FOUND
- [x] tests/translate/test_reconcile.py extended — FOUND
- [x] tests/bible/conftest.py with db_engine/session_factory re-export — FOUND
- [x] Commit 509945d exists — FOUND
- [x] Commit a9a8ef3 exists — FOUND
- [x] All 10 Phase-6 node IDs collected — VERIFIED
- [x] Full suite exits 0 (226 passed) — VERIFIED
