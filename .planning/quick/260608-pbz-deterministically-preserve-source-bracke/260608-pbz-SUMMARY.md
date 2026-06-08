---
phase: quick-260608-pbz
plan: 01
subsystem: translate/engine
tags: [envelope-preservation, tdd, deterministic, title-card, subtitle]
dependency_graph:
  requires: []
  provides: [_preserve_source_envelopes, enable_envelope_preservation]
  affects: [trezarr/translate/engine.py, trezarr/config.py]
tech_stack:
  added: []
  patterns: [pure-sync-transform, 3-step-detection, bracket-depth-scan, D-92-subdoc-carry-forward]
key_files:
  created:
    - tests/translate/test_envelope_preservation.py
  modified:
    - trezarr/config.py
    - trezarr/translate/engine.py
decisions:
  - "Test 8 fixture uses 'Được rồi.'/'Thế giới.' (U+1EXX diacritics) instead of plan's 'Xin chào.' (U+00E0 French range) to achieve diacritic ratio ≥ 0.70 for Check 3"
  - "Step 8.6 wired outside enable_self_review block so it runs whether or not Pass-4 ran"
  - "_OPENER_MAP module-level dict for the two closed bracket pairs ({ '(': ')', '[': ']' })"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-08T11:28:35Z"
  tasks_completed: 2
  files_changed: 3
---

# Phase quick-260608-pbz Plan 01: Deterministic Envelope Preservation Summary

Deterministic backstop that re-wraps bracket-enclosed title cards dropped by the LLM during Pass-3/Pass-4 translation, using a 3-step pure-Python detection algorithm with no LLM calls.

## What Was Built

`_preserve_source_envelopes(translated_doc, source_doc, settings) -> SubDoc` added to `trezarr/translate/engine.py`. Pure sync function that walks paired source/translated cues and re-wraps any cue where:

- **Step A:** stripped source first char is `(` or `[` and last char is its matching closer
- **Step B:** bracket-depth scan confirms depth returns to 0 EXACTLY at the final char (not before — "(a) and (b)" returns to 0 at index 2, SKIPPED)
- **Step C:** stripped translated text does NOT already start with opener and end with closer (idempotency guard)

Wired as Step 8.6 in `translate_file` — AFTER Pass-4 corrected_doc reassembly, BEFORE the Step-9 `validate_subdoc` gate loop. Gated by `settings.enable_envelope_preservation` (default `True`; `False` = exact pre-pbz behavior).

## Tasks Completed

| Task | Description | Commit | Status |
|------|-------------|--------|--------|
| T1 RED | Config toggle + 10 failing tests | 952a089 | Done |
| T2 GREEN | _preserve_source_envelopes + wire Step 8.6 | 495c376 | Done |

## Test Results

- All 10 tests in `tests/translate/test_envelope_preservation.py` pass GREEN
- Full suite: **504 passed** (baseline 494 + 10 new)
- ruff: zero errors on all changed files

### Test Coverage

| Test | Scenario | Result |
|------|----------|--------|
| T1 | Multi-line title card re-wrapped | PASS |
| T2 | Single-line "(Tập 142)" re-wrapped | PASS |
| T3 | Square bracket "[Note]" re-wrapped | PASS |
| T4 | Idempotency — already wrapped → no double-wrap | PASS |
| T5 | Mid-sentence aside ("Anh ấy (cười) nói") skipped via Step A | PASS |
| T6 | Source without wrapper → output unchanged | PASS |
| T7 | Raw/opaque SubLine passed through verbatim | PASS |
| T8 | Re-wrapped VI title card passes real validate_subdoc (Check 10 + 12) | PASS |
| T9 | enable_envelope_preservation=False → complete no-op | PASS |
| T10 | "(a) and (b)" — depth closes at index 2 < final → SKIP | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test 8 fixture used wrong diacritic range**
- **Found during:** Task 2 GREEN run
- **Issue:** Plan specified "Xin chào." × 4 as filler cues but "chào" uses U+00E0 (Latin-1 'à', French/Spanish range), which VN_DIACRITIC_RE (U+1E00-U+1EFF + Ơ/Ư) does NOT match. Ratio = 1/5 = 0.20 < 0.70 → Check 3 fired.
- **Fix:** Replaced with "Được rồi."/"Thế giới." which contain U+1EDD (ờ), U+1EE3 (ợ), U+1EBF (ế), U+1EED (ướ) — confirmed Vietnamese diacritics. Ratio = 5/5 = 1.0.
- **Files modified:** tests/translate/test_envelope_preservation.py
- **Note:** The plan's specification of "Xin chào." was a fixture design error, not a spec error. The gate compatibility invariant (Check 10 + Check 12) was correctly specified and passes with the fixed fixture.

**2. [Rule 1 - Bug] Test 9 called _preserve_source_envelopes with wrong keyword arg**
- **Found during:** Task 2 GREEN run
- **Issue:** Test 9 used `trn_doc=` but function signature parameter is `translated_doc=`
- **Fix:** Changed to positional call `_preserve_source_envelopes(translated_doc, source_doc, settings)`
- **Files modified:** tests/translate/test_envelope_preservation.py

## Harness Fix (2026-06-08, post-trezarr-quality review)

**Finding (codec MEDIUM / pipeline LOW):** `_preserve_source_envelopes` (Step 8.6) ran once before the Step-9 IMP-02b gate-repair `while True` loop. If a wrapped title-card cue landed in `failing_indices` and `_repair_failing_cues` re-translated it, the repaired text arrived without the source envelope. The splice that built the new `translated_doc` did not re-apply `_preserve_source_envelopes`, so the repaired cue could ship without its `( )`/`[ ]` wrapper.

**Fix:** One line added immediately after the repair splice (lines ~2149-2153 in engine.py): `translated_doc = _preserve_source_envelopes(translated_doc, source_doc, settings)`. Step-C idempotency guard no-ops already-wrapped cues; `enable_envelope_preservation=False` short-circuits the call. No changes to `_preserve_source_envelopes` itself, the Step-8.6 call, config, validate.py, or any moat file.

**RED test added:** `test_envelope_survives_gate_repair_loop` (Test 11) in `tests/translate/test_envelope_preservation.py`. Drives `translate_file()` end-to-end: source cue 1 is `(Episode Title)`, Pass-3 LLM returns `Miss Episode Title` (drops parens, HONORIFIC defect), Step 8.6 wraps it, gate fires, `_repair_failing_cues` mock returns `Tiêu đề tập` (clean VI, still no parens). Without fix: shipped cue 1 = `Tiêu đề tập`. With fix: shipped cue 1 = `(Tiêu đề tập)`.

**Note on Check-12 (LOW, pipeline):** The pipeline reviewer flagged this as fail-safe behavior — Check 12 exempts diacritic-bearing parens via `LATIN_DIACRITIC_RE`. No change needed; behavior is intentional.

**Commit:** 31952da — fix(260608-pbz): re-apply envelope preservation after gate-repair splice

**Test count:** 505 passed (was 504; +1 new test).

## Known Stubs

None — this plan adds a complete deterministic transformation with no placeholders.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

- [x] `trezarr/config.py` — enable_envelope_preservation field present, TrezarrSettings(**{}) constructs without error
- [x] `trezarr/translate/engine.py` — _preserve_source_envelopes function present, Step 8.6 wired, harness fix re-application added
- [x] `tests/translate/test_envelope_preservation.py` — 11 tests present, all PASS
- [x] Commits 952a089 (RED) and 495c376 (GREEN) and 31952da (harness fix) exist in git log
- [x] reconcile.py, attribute.py, validate.py NOT modified (moat intact)
- [x] Full suite: 505 passed, 0 failures
