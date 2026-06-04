---
phase: 02-mechanical-translation-core-validation-gate
fixed_at: 2026-05-31T00:00:00Z
review_path: .planning/phases/02-mechanical-translation-core-validation-gate/02-REVIEW.md
iteration: 1
findings_in_scope: 12
fixed: 12
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-05-31T00:00:00Z
**Source review:** `.planning/phases/02-mechanical-translation-core-validation-gate/02-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 12 (CR: 1, WR: 7, IN: 4)
- Fixed: 12
- Skipped: 0

**Test suite:** 69 passed, 1 skipped (pre-existing `@pytest.mark.live`) — all green after fixes.

## Fixed Issues

### CR-01: Engine quarantines on `openai.APIError` and swallows all exceptions

**Files modified:** `trezarr/translate/engine.py`, `tests/translate/test_engine.py`
**Commit:** (see `fix(02): CR-01`)
**Applied fix:** Changed `except (BatchValidationError, Exception)` to `except BatchValidationError`
in the `asyncio.gather` handler. Added explanatory comment citing D-18/Pitfall 5. Added
`test_translate_file_non_batch_error_propagates` to assert that a `RuntimeError` (standing in for
`openai.APIError`) propagates out of `translate_file` without creating a quarantine ledger entry.

---

### WR-04: `read_srt` / `batch_subdoc` failures leave file stuck `in_progress`

**Files modified:** `trezarr/translate/engine.py`, `tests/translate/test_engine.py`
**Commit:** (see `fix(02): WR-04`)
**Applied fix:** Wrapped Steps 5-6 (`read_srt` + `batch_subdoc`) in an explicit
`try/except Exception` block that routes to `_write_quarantine` + `ledger.record(quarantined)`,
fulfilling the documented "on any failure → quarantined" contract. The Step 7 gather handler
continues to catch only `BatchValidationError` so `openai.APIError` still propagates per Pitfall 5.
Added `test_translate_file_read_failure_quarantines` to assert `status='quarantined'` and a
non-`in_progress` ledger entry when `read_srt` raises `PermissionError`.

---

### WR-01: Check 5 ("monotonic timestamps") does not detect backward jumps

**Files modified:** `trezarr/translate/validate.py`, `tests/translate/test_validate.py`
**Commit:** (see `fix(02): WR-01`)
**Applied fix:** Added an explicit monotonic-start guard before the overlap check in
`_check_monotonic`: `if prev_start_ms is not None and start_ms < prev_start_ms: raise GateError(5, ...)`.
Simultaneous-start cues (`start_ms == prev_start_ms`) continue to be accepted as concurrent
display lines. Added `test_gate_backward_jump` to assert `GateError(check=5)` for cues
`[5000ms, 10000ms]` followed by `[3000ms, 4000ms]`.

---

### WR-02: Numbered-line parser silently accepts over-count responses

**Files modified:** `trezarr/translate/engine.py`, `tests/translate/test_engine.py`
**Commit:** (see `fix(02): WR-02/WR-03`)
**Applied fix:** Added early rejection in `parse_numbered_response`: collect all parsed line
numbers outside `1..expected_count` into `extra`, and raise `BatchValidationError` listing them.
Added `test_numbered_line_parse_over_count_rejected`.

---

### WR-03: Numbered-line parser silently overwrites duplicate line numbers

**Files modified:** `trezarr/translate/engine.py`, `tests/translate/test_engine.py`
**Commit:** (see `fix(02): WR-02/WR-03`)
**Applied fix:** Added duplicate detection before `parsed[line_num] = text`: if
`line_num in parsed`, raise `BatchValidationError("Duplicate line number [N] in LLM response")`.
Added `test_numbered_line_parse_duplicate_rejected`.

---

### WR-05: `datetime.utcnow()` is deprecated in Python 3.12

**Files modified:** `trezarr/translate/engine.py`
**Commit:** (see `fix(02): WR-05`)
**Applied fix:** Added `timezone` to the existing `from datetime import datetime` import.
Replaced both `datetime.utcnow().isoformat() + "Z"` call sites (quarantine artifact timestamp
and ledger `translated_at`) with `datetime.now(timezone.utc).isoformat()` which produces a
proper offset-aware ISO-8601 string.

---

### WR-06: Sidecar/dest naming logic is duplicated

**Files modified:** `trezarr/output/write.py`, `trezarr/translate/engine.py`
**Commit:** (see `fix(02): WR-06`)
**Applied fix:** Extracted `derive_vi_sidecar_path(media_path) -> Path` as a public function in
`output/write.py`. Updated `write_vi_sidecar` to delegate to it. Updated `translate_file` to
import and call it, removing the inline `import re as _re2` and duplicated regex. The two sites
can no longer diverge on sidecar naming.

---

### WR-07: Corrupt-ledger fallback silently discards the entire ledger on any schema drift

**Files modified:** `trezarr/output/ledger.py`, `tests/output/test_ledger.py`
**Commit:** (see `fix(02): WR-07`)
**Applied fix:** Split `_load()` into a two-phase approach: (1) `json.loads` with
`JSONDecodeError` fallback to empty (unchanged), then (2) per-entry construction using
`valid_keys = {f.name for f in dataclasses.fields(LedgerEntry)}` to filter unknown keys before
`LedgerEntry(**...)`, with individual `try/except (TypeError, KeyError)` that logs a per-entry
warning and skips only the bad record. Added `test_ledger_schema_drift_skips_bad_entry_keeps_good`
to assert that a valid entry survives when a sibling entry in the same file is malformed.

---

### IN-01: Dead variable `cue_idx` in translated-doc assembly

**Files modified:** `trezarr/translate/engine.py`
**Commit:** (see `fix(02): IN-01`)
**Applied fix:** Removed `cue_idx = 0` initialisation and `cue_idx += 1` increment from the
Step 8 assembly loop. Both were dead code — `cue_idx` was never read.

---

### IN-02: Local `import re` statements scattered inside function bodies

**Files modified:** `trezarr/translate/engine.py`
**Commit:** (see `fix(02): IN-02`)
**Applied fix:** Added `import re` to the top-level standard-library imports. Removed the
`import re as _re` statement at module scope just before `_NUMBERED_LINE_RE` (replacing
`_re.compile` with `re.compile`). The `import re as _re2` inside `translate_file`'s body was
already removed as part of the WR-06 fix.

---

### IN-03: `extract_sentinels` uses positional `counter` keys — per-cue isolation undocumented

**Files modified:** `trezarr/translate/sentinel.py`
**Commit:** (see `fix(02): IN-03`)
**Applied fix:** Added a `CALLER INVARIANT` block to the `extract_sentinels` docstring
documenting that the sentinel counter resets per call, keys are cue-local, and maps must never
be merged across cues.

---

### IN-04: `_tc_to_ms` duplicated verbatim across `batching.py` and `validate.py`

**Files modified:** `trezarr/translate/_timecode.py` (new), `trezarr/translate/batching.py`, `trezarr/translate/validate.py`
**Commit:** (see `fix(02): IN-04`)
**Applied fix:** Created `trezarr/translate/_timecode.py` with a single `tc_to_ms` function
documenting the malformed→0 contract in both the module docstring and the function docstring.
Both `batching.py` and `validate.py` now import it as `_tc_to_ms` for call-site compatibility.
Removed the duplicated `_TC_PARSE_RE` and `_tc_to_ms` from both modules.

---

_Fixed: 2026-05-31T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
