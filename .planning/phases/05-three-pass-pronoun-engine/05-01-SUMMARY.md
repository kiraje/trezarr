---
phase: 05-three-pass-pronoun-engine
plan: 01
subsystem: testing
tags: [pytest, xfail, tdd, pronoun-engine, address-map, wave-0]

requires:
  - phase: 04-series-bible-persistence
    provides: session_factory fixture, DB schema with AddressMap table, tests/db/conftest.py patterns

provides:
  - 13 xfail(strict=False) RED stubs covering all 05-VALIDATION.md Per-Task rows
  - tests/translate/test_analyze.py (ENG-04)
  - tests/translate/test_attribute.py (PRON-01)
  - tests/translate/test_reconcile.py (PRON-03 / Success #3/#4)
  - tests/translate/test_pronoun_engine.py (PRON-02 / D-47 Tier-3)
  - tests/bible/test_address_map.py (BIBLE-03)

affects: [05-02, 05-03, 05-04, 05-05, 05-06]

tech-stack:
  added: []
  patterns:
    - "xfail(strict=False, raises=(ImportError, AssertionError, TypeError)) for stubs in modules that already exist (trezarr.translate.engine is a Phase-3 artifact)"
    - "xfail(strict=False, raises=ImportError) for stubs in modules that do not yet exist (trezarr.bible.analyze, trezarr.translate.attribute, trezarr.translate.reconcile)"
    - "All trezarr.* imports deferred inside test function bodies to prevent collection-time ImportError"

key-files:
  created:
    - tests/translate/test_analyze.py
    - tests/translate/test_attribute.py
    - tests/translate/test_reconcile.py
    - tests/translate/test_pronoun_engine.py
    - tests/bible/test_address_map.py
  modified: []

key-decisions:
  - "xfail raises=(ImportError, AssertionError, TypeError) for test_pronoun_engine.py — trezarr.translate.engine already exists from Phase 3, so import succeeds; raises=ImportError alone would not catch assert False. Expanded tuple covers both Wave-0 (AssertionError from stub body) and future module-refactor scenarios."

patterns-established:
  - "Wave-0 stub pattern for existing modules: xfail(strict=False, raises=(ImportError, AssertionError, TypeError)) + assert False inside body"
  - "Wave-0 stub pattern for new modules: xfail(strict=False, raises=ImportError) + import inside body"

requirements-completed: [ENG-04, BIBLE-03, PRON-01, PRON-02, PRON-03]

duration: 2min
completed: 2026-06-01
---

# Phase 05 Plan 01: Wave-0 Nyquist-Compliant Test Scaffold Summary

**Thirteen xfail(strict=False) RED stubs across five test files covering every VALIDATION.md row for ENG-04, BIBLE-03, PRON-01, PRON-02, PRON-03, and D-47 Tier-3 graceful degrade.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-06-01T13:54:18Z
- **Completed:** 2026-06-01T13:56:30Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Created 4 translate/ stub files (11 stubs) and 1 bible/ stub file (2 stubs): all xfail, suite exits 0
- Confirmed tests/bible/conftest.py already re-exports session_factory — no modification needed
- Discovered and fixed: raises=(ImportError, AssertionError, TypeError) required for test_pronoun_engine.py because trezarr.translate.engine already exists from Phase 3

## Task Commits

1. **Task 1: Wave-0 translate/ stubs (test_analyze, test_attribute, test_reconcile, test_pronoun_engine)** - `9098d30` (test)
2. **Task 2: Wave-0 bible/ stub (test_address_map)** - `f74ac10` (test)

## Files Created/Modified

- `tests/translate/test_analyze.py` — ENG-04 stubs: test_pass1_runs_before_pass3, test_pass1_failure_quarantines
- `tests/translate/test_attribute.py` — PRON-01 stubs: test_attribution_parsing, test_unmatched_name_safe_default
- `tests/translate/test_reconcile.py` — PRON-03/Success#3/#4 stubs: test_low_confidence_safe_default, test_high_confidence_uses_address_map, test_reciprocal_coherence, test_below_threshold_ignores_address_map
- `tests/translate/test_pronoun_engine.py` — PRON-02/D-47 stubs: test_pronoun_hint_in_prompt, test_pronoun_consistency_within_episode, test_tier3_endpoint_degrades_gracefully
- `tests/bible/test_address_map.py` — BIBLE-03 stubs: test_upsert_address_pair, test_locked_pair_not_overwritten

## Decisions Made

- `raises=(ImportError, AssertionError, TypeError)` for test_pronoun_engine.py: trezarr.translate.engine exists from Phase 3 and exports both `build_translate_prompt` and `translate_file`. Using `raises=ImportError` alone would cause stubs to FAIL (not XFAIL) because the import succeeds and the stub body hits `assert False` (an AssertionError). Expanded raises tuple captures the actual failure mode at Wave 0 while remaining forward-compatible with any future module refactoring.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected xfail raises= for test_pronoun_engine.py**
- **Found during:** Task 1 verification run
- **Issue:** Plan specified `raises=ImportError` for all stubs. However, `trezarr.translate.engine` already exists (Phase 3 artifact), so `build_translate_prompt` and `translate_file` import successfully. The stubs then hit `assert False` → `AssertionError`, which `xfail(raises=ImportError)` does not catch → tests show FAILED instead of XFAIL.
- **Fix:** Changed `raises=ImportError` to `raises=(ImportError, AssertionError, TypeError)` for the three test_pronoun_engine.py stubs. test_analyze.py, test_attribute.py, and test_reconcile.py remain `raises=ImportError` (those modules do not exist yet).
- **Files modified:** `tests/translate/test_pronoun_engine.py`
- **Verification:** `uv run pytest tests/translate/test_pronoun_engine.py -v` — all 3 stubs XFAIL
- **Committed in:** `9098d30` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in xfail raises= type)
**Impact on plan:** Essential for suite to stay green at Wave 0. No scope creep.

## Issues Encountered

None beyond the xfail raises= mismatch documented above.

## Known Stubs

All test files are intentionally 100% stubs — this is the Wave-0 scaffold plan. No production code was written. Future plans turn each stub GREEN:

| Stub | File | Plan |
|------|------|------|
| test_pass1_runs_before_pass3 | test_analyze.py | 05-02 |
| test_pass1_failure_quarantines | test_analyze.py | 05-02 |
| test_upsert_address_pair | test_address_map.py | 05-02 |
| test_locked_pair_not_overwritten | test_address_map.py | 05-02 |
| test_attribution_parsing | test_attribute.py | 05-03 |
| test_unmatched_name_safe_default | test_attribute.py | 05-03 |
| test_low_confidence_safe_default | test_reconcile.py | 05-04 |
| test_high_confidence_uses_address_map | test_reconcile.py | 05-04 |
| test_reciprocal_coherence | test_reconcile.py | 05-04 |
| test_below_threshold_ignores_address_map | test_reconcile.py | 05-04 |
| test_pronoun_hint_in_prompt | test_pronoun_engine.py | 05-05 |
| test_pronoun_consistency_within_episode | test_pronoun_engine.py | 05-05 |
| test_tier3_endpoint_degrades_gracefully | test_pronoun_engine.py | 05-06 |

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- All 13 VALIDATION.md rows have a concrete xfail stub
- Full suite: 208 passed, 1 skipped, 13 xfailed (green)
- Plans 05-02 through 05-06 can now implement production code to turn stubs GREEN sequentially

---
*Phase: 05-three-pass-pronoun-engine*
*Completed: 2026-06-01*
