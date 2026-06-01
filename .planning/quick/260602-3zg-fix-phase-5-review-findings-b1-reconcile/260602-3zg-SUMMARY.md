---
phase: quick-260602-3zg
plan: "01"
subsystem: translate/reconcile, bible/store
tags: [bugfix, cr-01, pronoun-engine, series-bible, regression-test]
dependency_graph:
  requires: []
  provides: [CR-01 case/whitespace-insensitive name resolution at reconcile + DB boundaries]
  affects: [trezarr/translate/reconcile.py, trezarr/bible/store.py]
tech_stack:
  added: []
  patterns: [func.lower() SQLAlchemy identity comparison, .strip().lower() in-memory name normalization]
key_files:
  created: []
  modified:
    - trezarr/translate/reconcile.py
    - trezarr/bible/store.py
    - tests/translate/test_reconcile.py
    - tests/bible/test_lazy_series_create.py
decisions:
  - "Display-case preserved on INSERT (original_latin_name stored as-is); identity comparison normalized via func.lower() — compare normalized, store original"
metrics:
  duration: "~5 min"
  completed: "2026-06-01T19:59:04Z"
---

# Quick Task 260602-3zg: Fix Phase-5 Review Findings B1+M1 Summary

**One-liner:** `.strip().lower()` at all three reconcile.py name-lookup sites + `func.lower()` SQLAlchemy identity guard in store.py, closing the silent pronoun-pair drop (B1) and cross-episode character row-fork (M1) defects.

## What Was Built

Two targeted defect fixes addressing the verified Phase-5 review findings B1 (BLOCKER) and M1 (MEDIUM):

**B1 fix — reconcile.py (3 sites):**
- Index build (`name_to_id` dict comprehension): `.lower()` → `.strip().lower()`
- Speaker lookup: `.lower()` → `.strip().lower()`
- Addressee lookup: `.lower()` → `.strip().lower()`
- Updated inline comment to document CR-01 invariant at the fix site

**M1 fix — store.py (2 sites + import):**
- Added `func` to the `from sqlalchemy import select` line
- `_upsert_character_in_session` WHERE clause: exact match → `func.lower(...) == name.strip().lower()`
- `get_character` WHERE clause: same normalization
- Updated `get_character` docstring to reflect the new identity semantics
- Display-case is preserved on INSERT — first write wins; only the SELECT comparison is normalized

**Regression tests (4 new):**
- `test_reconcile_strips_whitespace_from_speaker_and_addressee` — whitespace-padded ` Minh`/` Lan` resolve to anh/em
- `test_reconcile_strips_casing_from_speaker_and_addressee` — ALL-CAPS `MINH`/`LAN` resolve to anh/em
- `test_upsert_character_strips_whitespace_does_not_fork` — ` Minh` after `Minh` = same DB row
- `test_upsert_character_casing_does_not_fork` — `minh` after `MINH` = same DB row

## Test Results

```
uv run pytest tests/translate tests/bible -q
96 passed, 6 xfailed, 4 xpassed in 3.52s
```

Baseline was 92 passed. Final count: **96 passed** (4 new regression tests, all green).

## Commits

| Hash | Message |
|------|---------|
| `c887a7e` | `fix(quick-260602-3zg): B1 — add .strip() to all three name-lookup sites in reconcile.py (CR-01)` |
| `754292f` | `fix(quick-260602-3zg): M1 — case/whitespace-insensitive character identity in store.py (CR-01)` |

## Deviations from Plan

None — plan executed exactly as written.

The casing regression test (`test_reconcile_strips_casing_from_speaker_and_addressee`) technically passed in the RED phase because `.lower()` already handled pure casing before the fix. This is expected: the test is a correctness guard for the casing path post-fix, not a demonstration of a casing-only bug. The whitespace test was the true RED-failing test (demonstrating B1).

## Known Stubs

None.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Both fixes are pure query-normalization changes within existing code paths. T-3zg-01 and T-3zg-02 mitigations fully applied.

## Self-Check

- [x] `trezarr/translate/reconcile.py` — three `.strip().lower()` sites present
- [x] `trezarr/bible/store.py` — `func.lower()` in both `_upsert_character_in_session` and `get_character` WHERE clauses
- [x] `tests/translate/test_reconcile.py` — 2 new regression tests present and passing
- [x] `tests/bible/test_lazy_series_create.py` — 2 new regression tests present and passing
- [x] Commits `c887a7e` and `754292f` exist in git log
- [x] 96 passed (was 92), 0 failed

## Self-Check: PASSED
