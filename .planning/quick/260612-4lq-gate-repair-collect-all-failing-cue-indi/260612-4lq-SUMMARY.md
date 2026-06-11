---
phase: quick
plan: 260612-4lq
subsystem: translate/validate
tags: [gate, repair, validate, accumulation, tdd, check-9, check-10, check-11, check-12]
dependency_graph:
  requires: []
  provides: [multi-cue-gate-accumulation]
  affects: [engine.py repair loop]
tech_stack:
  added: []
  patterns: [for-else accumulation, post-loop priority raise]
key_files:
  created:
    - tests/translate/test_validate_collect_failing.py
  modified:
    - trezarr/translate/validate.py
decisions:
  - "for...else pattern used to skip check-11/10 when check-12 fires on a cue (matches original control flow intent)"
  - "apostrophe fix: restored ASCII U+0027 possessive check alongside existing curly U+2019 — edit tool had silently upgraded both to curly, causing ASCII-apostrophe possessives like Han's to miss check-12"
  - "test design: check-10 and check-11 multi-cue tests use 7-cue SubDocs (5 VI + 2 bad) to keep Check-3 ratio at 5/7 ≈ 0.714 above 0.70 threshold; 4-cue (2 VI + 2 bad) designs hit Check-3 first"
  - "Test B designed as priority guard (passes before and after fix) since check-9 fires first in single-check-9 + single-check-10 scenario"
metrics:
  duration: "16 minutes"
  completed: "2026-06-12"
  tasks: 2
  files_changed: 2
---

# Phase quick Plan 260612-4lq: Per-cue Gate Accumulation Summary

**One-liner:** Refactor validate_subdoc per-cue loop (checks 9-12) to accumulate all failing cue indices across the full SubDoc and raise ONE GateError with a complete sorted list, replacing the fail-fast design that burned one gate-repair slot per failing cue.

## What Was Built

**trezarr/translate/validate.py** — per-cue loop (checks 9-12) refactored:

Before: each check immediately `raise GateError(GateFailure(N, ..., failing_indices=[i]))` on the first failing cue.

After:
1. Four empty accumulators declared before the loop: `_fail9`, `_fail10`, `_fail11`, `_fail12`
2. Inside the loop, each check appends to its accumulator then `continue`s (skipping lower-priority checks for that cue)
3. Check-12 uses `for...else` on the GLOSS_PAREN_RE inner loop — `break` appends to `_fail12` and skips `else`; `else` runs check-11 and check-10 for cues with no gloss-paren match
4. Post-loop priority block raises one `GateError` with `failing_indices=sorted(_failN)` in order: 9 > 11 > 12 > 10

Also fixed: restored ASCII apostrophe `\x27s` as the first possessive check (alongside existing curly U+2019) — the edit tool had silently upgraded both to curly, causing standard ASCII-apostrophe possessives to miss check-12.

**tests/translate/test_validate_collect_failing.py** — new test file (6 tests):

| Test | Check | Scenario | Status |
|------|-------|----------|--------|
| A | 9 | 5 cues, 3 CJK leaks — all 3 indices collected | RED→GREEN |
| B | 9 + 10 | check-9 wins priority over check-10 | Passes before + after |
| C | 10 | 7 cues, 2 verbatim passthroughs — both indices | RED→GREEN |
| D | 9 | Single CJK leak — single-element list unchanged | Passes before + after |
| E | 11 | 4 cues, 2 honorific bigrams — both indices | RED→GREEN |
| F | 12 | 4 cues, 2 gloss parens with possessives — both indices | RED→GREEN |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Apostrophe encoding corruption in possessive check**

- **Found during:** Task 2 (GREEN) — test F only collected `[0]` instead of `[0, 2]`
- **Issue:** When my Edit substitution rewrote the check-12 condition, the Claude Edit tool silently upgraded the ASCII apostrophe `'` (U+0027) to a right single quotation mark `'` (U+2019) in the string literal `"'s" in inner`. The original code had one ASCII check and one curly check; after edit both became curly. "Han's brother" uses ASCII apostrophe, so `"’s" in inner` returned False and the possessive trigger was broken.
- **Fix:** Changed the first possessive check to use `"\x27s"` (explicit ASCII hex escape) which the Edit tool cannot upgrade to curly, and kept `"'s"` (U+2019) as the second check. This exactly matches the original intent and code.
- **Files modified:** trezarr/translate/validate.py
- **Commit:** f22657b

**2. [Rule 1 - Test Design] Check-3 firing before Check-10/11 in multi-cue tests**

- **Found during:** Task 1 (RED test B) and Task 2 (GREEN tests C, E)
- **Issue:** 4-cue SubDocs with 2 bad cues and 2 clean VI cues have VI diacritic ratio 2/4 = 0.50 < 0.70 threshold, causing Check-3 to fire before the per-cue checks.
- **Fix:** Redesigned tests B, C, E to use 7-cue SubDocs (5 VI padding + 2 bad cues), giving ratio 5/7 ≈ 0.714 ≥ 0.70.
- **Note:** This is a test authoring correction, not a production code change. The _VI_PAD pattern from test_gate_repair.py already documents this same constraint ("Cue 1-4: properly translated Vietnamese lines... This design ensures Check-3 ratio = 4/5 = 0.80").

**3. [Rule 1 - Test Design] "Doctor" not in HONORIFIC_CAPNAME_RE word list**

- **Found during:** Task 2 — test E failing because "Doctor Zhao" didn't match HONORIFIC_CAPNAME_RE
- **Issue:** The word list `(?:Mr|Mrs|Ms|Miss|Sir|Elder|Brother|Sister|Master|Lord|Lady)` does not include "Doctor".
- **Fix:** Changed test E's second honorific from "Doctor Zhao" to "Elder Zhao" (which IS in the list). The test verifies multi-index accumulation for check-11; the specific honorific word is irrelevant.

## All Existing Skip/Exemption Rules Preserved

Verified intact (no changes):
- Raw-cue skip (`if trn_sl.raw is not None: continue`) — line 613
- Empty-text skip — line 616
- Credit-fansub exemption for check-9 (`is_credit_fansub_cue`) — line 621
- VN diacritic early-continue for check-10 — in else block
- ALLOWLIST_RE / SENTINEL_ONLY_RE skips for check-10 — in else block
- Interjection-token exemption for check-10 — in else block
- `all_in_source` and `all...in allowlist` guards for check-10 — in else block
- LATIN_DIACRITIC_RE inner check for check-12 — unchanged
- HONORIFIC_CAPNAME_RE inner check trigger for check-12 — unchanged
- Checks 1-8 — completely untouched

## TDD Gate Compliance

RED gate: commit 81309b8 (`test(quick-260612-4lq): add failing tests...`)
GREEN gate: commit f22657b (`feat(quick-260612-4lq): accumulate all failing cue indices...`)

## Known Stubs

None. All accumulation wired end-to-end.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Changes are entirely within the in-process validation gate function.

## Self-Check: PASSED

- [x] `tests/translate/test_validate_collect_failing.py` — exists, 6 tests pass
- [x] `trezarr/translate/validate.py` — modified, ruff clean
- [x] Commit 81309b8 exists (RED)
- [x] Commit f22657b exists (GREEN)
- [x] Full suite: 566 passed, 0 failed (≥560 threshold met)
