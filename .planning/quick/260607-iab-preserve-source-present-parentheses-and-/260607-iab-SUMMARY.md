---
phase: quick-260607-iab
plan: 01
subsystem: translate
tags: [prompt-engineering, parenthesis-preservation, h4-fix, tdd, regression-tests]
dependency_graph:
  requires: []
  provides: [h4-parenthesis-preservation-rule, validate-regression-tests]
  affects: [build_translate_prompt, validate_subdoc]
tech_stack:
  added: []
  patterns: [tdd-red-green, rule-qualified-instruction]
key_files:
  created: []
  modified:
    - trezarr/translate/engine.py
    - tests/translate/test_engine.py
    - tests/translate/test_validate.py
decisions:
  - "H4 rule reworked to two-part: PRESERVE source-present parens + forbid ADDING new ones (not a single unqualified prohibition)"
  - "Test D observed GREEN at RED phase — validator already handles Vietnamese diacritics in parentheticals correctly; no validate.py change needed (confirmed plan expectation)"
  - "Comment in engine.py preserves historical note about old behavior for future grep-based archaeology"
metrics:
  duration: "~12 min"
  completed: "2026-06-07"
  tasks: 2
  files: 3
---

# Phase quick-260607-iab Plan 01: Parenthesis Preservation (H4 Rule Fix) Summary

**One-liner:** Reworked H4 RULE in `build_translate_prompt` to PRESERVE source-present parentheses/brackets while still forbidding model-added English glosses — closes the structural benchmark gap where DeepSeek stripped title-card parens.

## What Was Done

**Root cause:** The H4 RULE at line 298 of `engine.py` read:
```
"Do NOT add parentheticals, glosses, or translator notes. Translate the dialogue only."
```
DeepSeek (a weak model) over-applied this unqualified prohibition and stripped parentheses that were ALREADY in the source cue — e.g., the Ep-142 title card `(A Record of Mortal's Journey to Immortality)` became `A Record of Mortal's Journey to Immortality` with no parens.

**Fix:** Two-part rework of the H4 RULE:
- (a) POSITIVELY instruct: if source contains `( )` or `[ ]`, TRANSLATE inside and PRESERVE the delimiters
- (b) STILL forbid: do NOT add new glosses/translator notes NOT already present in source

**validate.py:** Confirmed already correct — `LATIN_DIACRITIC_RE` exempts Vietnamese diacritics from Check 12, and `VN_DIACRITIC_RE` exempts them from Check 10. No changes needed.

## Task 1: Rework H4 RULE + Engine Tests

**TDD RED phase:** Tests A and B failed as expected against the old prompt wording:
- Test A (`test_h4_no_unqualified_do_not_add_parentheticals`): FAIL — "Do NOT add parentheticals" found in prompt
- Test B (`test_h4_preserve_instruction_present`): FAIL — no "PRESERVE" or "already present" found
- Test C (`test_h4_anti_gloss_instruction_remains`): PASS already — "glosses" was already in the old rule

**Implementation:** Replaced the unqualified rule with a qualified two-part instruction. The rule text now contains "PRESERVE" and "NOT already present in the source cue" while retaining "new glosses, translator notes" language.

**GREEN:** All 3 tests pass. Full translate suite: **145 passed** (up from 142 baseline).

**Commit:** `56c2e69`

## Task 2: Validate Gate Regression Tests

**TDD baseline observation (plan-documented expected outcome):** Both tests were GREEN immediately:
- Test D (`test_h4_vietnamese_parenthetical_passes_gate`): PASS — `(Phàm Nhân Tu Tiên Ký\nNgoại Hải Phong Vân)` correctly passes Check 10 (VN diacritics detected) and Check 12 (LATIN_DIACRITIC_RE matches → not an English gloss)
- Test E (`test_h4_verbatim_sdh_sound_cue_raises_check10`): PASS — `(WIND HOWLING)` verbatim correctly raises Check 10 (source passthrough detected)

Per the plan: "confirm GREEN if the validator already handles it correctly — either is a valid RED/GREEN baseline; record what you observe." The validator was already correct.

**Full validate suite:** 22 passed (up from 20).
**Full translate suite:** **147 passed** (up from 142 baseline, 5 new tests added).

**Commit:** `c287b91`

## Verification

All plan verification checks passed:

1. `pytest tests/translate/` — **147 passed, 10 xpassed, 0 failures** (466+ total suite clean)
2. `ruff check trezarr/translate/engine.py` — **All checks passed**
3. `grep "Do NOT add parentheticals" engine.py` — Only appears in a COMMENT (historical note), NOT in the rule text (lines 307-311 contain the new qualified rule)
4. `grep "PRESERVE" engine.py` — Appears in H4 rule text (line 308): `"TRANSLATE the text inside them and PRESERVE the surrounding…"`

## Success Criteria Check

- [x] `build_translate_prompt` emits a rule that (a) preserves source-present parentheses/brackets and (b) forbids the model from adding new ones
- [x] `(Phàm Nhân Tu Tiên Ký)` passes `validate_subdoc` without triggering Check 10 or Check 12
- [x] All 466+ existing tests remain green (full suite: 466 passed, 1 skipped, 3 xfailed, 52 xpassed)
- [x] `reconcile.py`, `attribute.py`, and Address-Map code are unmodified (git diff confirms)

## Deviations from Plan

**None.** The plan executed exactly as written. Test D was immediately GREEN (validator already correct) — this was an explicitly documented acceptable outcome in the plan.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The change is prompt-text-only in `build_translate_prompt`. validate.py Check 12 (GLOSS_PAREN_RE) remains unchanged — the hard backstop against model-added English-gloss parentheticals is intact (T-iab-01 mitigation confirmed).

## Self-Check: PASSED

- `trezarr/translate/engine.py` modified — verified via `git diff HEAD~2 -- trezarr/translate/engine.py`
- `tests/translate/test_engine.py` modified — 3 new tests added (test_h4_*)
- `tests/translate/test_validate.py` modified — 2 new tests added (test_h4_*)
- Commits `56c2e69` (Task 1) and `c287b91` (Task 2) exist in git log
- Full translate suite: 147 passed, 0 failures

## Post-execution review (trezarr-quality harness) — 1 HIGH found + fixed

The domain harness (codec-fidelity-guardian + vietnamese-linguist → finding-verifier) was run on the diff and caught a regression the plan missed: the per-line attribution hint is itself a leading parenthetical `(speaker says: …; addresses as: …)`, so the new "PRESERVE source parentheses" rule could license a weak model to echo it on-screen — re-opening the 260604/260607 scaffolding-leak class. The finding-verifier **empirically proved** the leaked hint passed all 12 gate checks (diacritic-bearing → slips Check 10/12).

**Fix `f96c125` (review-driven, this task), two layers:**
- `engine.py` H4 rule: carve-out marking the `(speaker says: …)` hint a PRIVATE instruction the model must never translate/echo/keep.
- `validate.py`: new `HINT_SCAFFOLD_RE` folded into Check 8 (defense-in-depth alongside `REVIEW_SCAFFOLD_RE`) → a leaked hint quarantines instead of shipping.

Re-verified **5/0 VERIFIED**: leak now raises `check=8` (3 variants incl. exact Ep-142 string); 0 false positives across 13 realistic Vietnamese cues; title-card win intact; no gate regression. **Full suite: 475 passed, 0 failures.** Residual (translated-label echo `(người nói:`) documented + accepted (same stance as `(source:`). Report: `.trezarr-harness/REVIEW-20260607_063814.md`. Verdict: **PASS**.
