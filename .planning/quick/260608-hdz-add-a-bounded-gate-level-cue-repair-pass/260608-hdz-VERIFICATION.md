---
phase: quick-260608-hdz
verified: 2026-06-08T06:30:00Z
status: passed
score: 10/10
overrides_applied: 0
---

# quick-260608-hdz: Bounded Gate-Level Cue Repair Pass — Verification Report

**Phase Goal:** Add a bounded gate-level cue-repair pass (IMP-02b) so one re-translatable
defective cue cannot quarantine a whole episode.
**Verified:** 2026-06-08T06:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Step 0: Previous Verification

None found. Initial mode.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | `enable_gate_repair: bool = True` and `gate_repair_max_attempts: int = 3` exist in TrezarrSettings with TREZARR_ env-var prefix | VERIFIED | `config.py` lines 109/114; runtime check confirms defaults and programmatic override both work |
| 2 | Repairable gate-check set is exactly {3, 9, 10, 11, 12}; structural checks {1,2,4,5,6,7,8} quarantine immediately without calling repair | VERIFIED | `engine.py` line 836: `_REPAIRABLE_CHECKS: frozenset[int] = frozenset({3, 9, 10, 11, 12})`; repair loop condition `check in _REPAIRABLE_CHECKS` at line 1949; `test_structural_not_repaired` asserts call_count==0 for Check-1, PASSED |
| 3 | `enable_gate_repair=False` reproduces exact current behavior: first GateError quarantines, `_repair_failing_cues` never called | VERIFIED | `_can_repair` at line 1947-1952 short-circuits on `settings.enable_gate_repair`; `test_gate_repair_disabled` asserts call_count==0 and status="quarantined", PASSED |
| 4 | Gate stays the sole arbiter: repaired doc must PASS a real `validate_subdoc` call before write; nothing defective ships | VERIFIED | Repair loop at line 1935-2029: `validate_subdoc` called on every iteration including after splice; write (Step 10) is only reachable via `break` after a clean pass; `test_honorific_repair_success` confirms status="done" after gate approves repaired doc |
| 5 | Repair re-translates failing cues through existing Pass-3 machinery (`build_translate_prompt` + `_translate_batch`) with same `glossary_lines`/`register_value`/`resolved_map` pronoun hints; pronoun/relational moat untouched | VERIFIED | `_repair_failing_cues` at line 1321-1330 calls `_translate_batch` with `glossary=glossary_lines`, `register=register_value`, `pronoun_hints=repair_pronoun_hints`; `test_moat_regression` and `test_repair_receives_directed_pronoun_hint` both PASSED |
| 6 | Repair uses existing `LLMClient` (its semaphore is the sole concurrency gate); no new `asyncio.Semaphore` and no per-call tenacity added | VERIFIED | `engine.py` comment at line 1526: "No new asyncio.Semaphore here — all LLM calls go through LLMClient._semaphore"; grep finds zero `asyncio.Semaphore` instantiations in engine.py; no tenacity import in engine.py |
| 7 | Budget bounded at `gate_repair_max_attempts` attempts; exhaustion quarantines via same `_write_quarantine` + `ledger.record` path | VERIFIED | `_repair_budget` decremented at line 1971 on every attempt; loop condition `_repair_budget > 0` in `_can_repair`; `test_budget_exhausted` asserts `repair_call_count == _MAX_ATTEMPTS` (2) and status="quarantined", PASSED |
| 8 | `reconcile.py`, `attribute.py`, and Address-Map logic are NOT touched | VERIFIED | `git diff --name-only origin/main...HEAD` returns only: `tests/translate/test_gate_repair.py`, `trezarr/config.py`, `trezarr/translate/engine.py`, `trezarr/translate/validate.py`; no reconcile.py or attribute.py in diff |
| 9 | Repaired `SubLine` objects preserve `index`/`start_tc`/`end_tc` byte-identically from `translated_doc`; only `.text` is replaced | VERIFIED | `_repair_failing_cues` at lines 1341-1349 constructs `SubLine(index=line.index, start_tc=line.start_tc, end_tc=line.end_tc, text=new_text, raw=None)`; `test_moat_regression` asserts `captured_failing_line.index`, `.start_tc`, `.end_tc` are non-empty, PASSED |
| 10 | `test_gate_repair.py` covers all 5 originally-specified tests PLUS 5 harness-driven additions; all 10 green | VERIFIED | `uv run pytest tests/translate/test_gate_repair.py -v`: 10 passed; full suite: 494 passed, 1 skipped, 3 xfailed, 52 xpassed |

**Score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/config.py` | Two new fields: `enable_gate_repair` (bool=True) and `gate_repair_max_attempts` (int=3) under IMP-02b section | VERIFIED | Lines 105-114; runtime confirms defaults and overrides |
| `trezarr/translate/engine.py` | `_REPAIRABLE_CHECKS`, `_REPAIR_DIRECTIVE`, `_LEAKED_DIRECTIVE_RE`, `_repair_failing_cues`, repair loop at Step 9 | VERIFIED | All symbols present; function at line 1194; loop at line 1925-2029 |
| `trezarr/translate/validate.py` | `CORRECTION_DIRECTIVE_RE` added to Check 8 as fail-closed backstop (justified harness-BLOCKER addition) | VERIFIED | Lines 71-79 + line 456; Check 8 now matches `[CORRECTION REQUIRED]` echo |
| `tests/translate/test_gate_repair.py` | 10 tests covering original 5 must-haves + 5 harness-driven fixes | VERIFIED | All 10 collected and passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `translate_file` Step 9 repair loop | `_repair_failing_cues` | `await _repair_failing_cues(...)` at line 1986 | WIRED | Called with all required params including new `flat_attributions`/`name_to_char_id` |
| `_repair_failing_cues` | `_translate_batch` | `await _translate_batch(repair_batch, ..., correction_directive=repair_directive_str)` at line 1321 | WIRED | Uses existing function, no new Semaphore |
| `_translate_batch` | `build_translate_prompt` | `correction_directive` param threaded through to prompt RULES block | WIRED | `engine.py` line 413 injects `[CORRECTION REQUIRED]` as a numbered rule |
| `validate_subdoc` Check 8 | `CORRECTION_DIRECTIVE_RE` | Pattern added alongside `HINT_SCAFFOLD_RE` at line 456 | WIRED | `test_validate_check8_trips_on_correction_required` PASSED |
| `parse_numbered_response` | `_LEAKED_DIRECTIVE_RE` | Strip applied at line 818 before returning | WIRED | `test_parse_strips_leading_directive_echo` PASSED |
| Config fields | Repair loop | `settings.enable_gate_repair`, `settings.gate_repair_max_attempts` read in `_can_repair` condition | WIRED | Lines 1948, 1951, 1934 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 10 gate-repair tests pass | `uv run pytest tests/translate/test_gate_repair.py -v` | 10 passed in 0.21s | PASS |
| Full suite still green | `uv run pytest -q` | 494 passed, 1 skipped, 3 xfailed, 52 xpassed | PASS |
| Config defaults correct at runtime | `uv run python -c "from trezarr.config import TrezarrSettings; s=TrezarrSettings(_yaml_file='/dev/null'); ..."` | enable_gate_repair=True, gate_repair_max_attempts=3 | PASS |
| enable_gate_repair=False override works | Same invocation with override | enable_gate_repair=False confirmed | PASS |
| No new asyncio.Semaphore in engine.py | `grep -n "asyncio.Semaphore" engine.py` | Only comment references (no instantiation) | PASS |
| reconcile.py and attribute.py not modified | `git diff --name-only origin/main...HEAD` | Only 4 files listed; neither reconcile.py nor attribute.py present | PASS |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX markers; no stub returns; no hardcoded empty data on render paths | — | Clean |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| IMP-02b | 260608-hdz-PLAN.md | Bounded gate-level cue-repair pass | SATISFIED | All 10 must_haves truths VERIFIED; full test suite green |

---

## Harness Additions (Justified, Not Regressions)

The SUMMARY records 1 BLOCKER + 2 HIGH findings fixed after initial commit. These are accounted for in the verification:

- **FIX 1 (BLOCKER):** `validate.py` addition of `CORRECTION_DIRECTIVE_RE` to Check 8 is a defensive backstop that `git diff` correctly surfaces. It is a justified expansion of the gate, not a moat-touch. `reconcile.py` and `attribute.py` remain untouched.
- **FIX 2 (HIGH/D-47):** `except BatchValidationError` narrowing in `_repair_failing_cues` — verified via `test_repair_api_error_propagates` PASSED.
- **FIX 3 (HIGH/MOAT):** `flat_attributions`/`name_to_char_id` params added to `_repair_failing_cues` and wired from call site — verified via `test_repair_receives_directed_pronoun_hint` PASSED.

All three fixes strengthen rather than compromise the original must-haves.

---

## Human Verification Required

None. All must-haves are verifiable programmatically and the test suite fully exercises the repair loop end-to-end with mocked LLM responses.

---

## Gaps Summary

No gaps. All 10 must-have truths are VERIFIED with code-level evidence. The full test suite (494 passed) is green. The moat is untouched (`reconcile.py`/`attribute.py` not in diff). The gate remains the sole arbiter before write.

---

_Verified: 2026-06-08T06:30:00Z_
_Verifier: Claude (gsd-verifier)_
