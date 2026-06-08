---
phase: quick-260608-e8r
plan: "01"
subsystem: translate/engine
tags: [tdd, bug-fix, parse-numbered-response, hint-echo, job-9, pass-3]
dependency_graph:
  requires: []
  provides: [_LEAKED_HINT_RE strip in parse_numbered_response]
  affects: [trezarr/translate/engine.py, tests/translate/test_engine.py]
tech_stack:
  added: []
  patterns: [module-level anchored regex strip, TDD RED/GREEN]
key_files:
  created: []
  modified:
    - trezarr/translate/engine.py
    - tests/translate/test_engine.py
decisions:
  - "Regex anchored to '^\\s*\\(\\s*speaker\\s+says\\s*:[^)]*\\)\\s*' — [^)]* stops at first ')' (no nested parens in hint), IGNORECASE mirrors HINT_SCAFFOLD_RE in validate.py"
  - "Strip applied AFTER <<BR>> restoration and BEFORE parsed[n] assignment + empty-check so hint-only echoes correctly trigger BatchValidationError → IMP-02 correction loop"
  - "Preservation test (Test 4) passes both RED and GREEN — it verifies absence of unintended stripping, not new behavior"
metrics:
  duration: "~2 minutes"
  completed: "2026-06-08"
  tasks: 2
  files: 2
---

# Quick 260608-e8r: Surgically Strip Leading Echoed Pass-3 Attribution Hint Summary

**One-liner:** Module-level `_LEAKED_HINT_RE` anchored to `speaker says:` strips the job-9 echoed hint prefix from `parse_numbered_response` before the empty-check, recovering quarantined episodes without touching the pronoun moat.

## What Was Built

Added a single module-level regex and one strip call to `trezarr/translate/engine.py`:

**`_LEAKED_HINT_RE`** (engine.py ~line 657): compiled regex `^\s*\(\s*speaker\s+says\s*:[^)]*\)\s*` with `re.IGNORECASE`. Anchored to the start of the text, matches only the English instruction phrase `(speaker says: X; addresses as: Y)` that `build_translate_prompt` injects as a per-line pronoun hint. Cannot match Vietnamese text by construction.

**Strip call** (engine.py ~line 760): `text = _LEAKED_HINT_RE.sub('', text)` inserted after the three `_BR_RE` sub calls and before `parsed[n] = text` + the empty-check.

**4 TDD tests** added to `tests/translate/test_engine.py`:
- `test_parse_strips_leading_hint_echo_job9` — job-9 exact case + validate_subdoc clean-pass assertion
- `test_parse_strips_leading_hint_echo_modern` — `anh`/`em` variant
- `test_parse_hint_only_raises_empty_error` — hint-only → `BatchValidationError("Empty/whitespace-only")` → IMP-02 trigger
- `test_parse_preserves_source_paren_title_card` — `(Phàm Nhân Tu Tiên Ký)` NOT stripped (guards 260607-iab paren-win)

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| `001c491` | test (RED) | 4 failing tests for leading hint-echo strip |
| `53a4863` | feat (GREEN) | Strip leading echoed Pass-3 hint in parse_numbered_response |

## Verification

```
pytest tests/translate/test_engine.py -k "hint_echo or hint_only or paren_title" -v
# 4 passed

pytest tests/ -x -q
# 484 passed, 1 skipped, 3 xfailed, 52 xpassed, 2 warnings

ruff check trezarr/translate/engine.py tests/translate/test_engine.py
# All checks passed!

grep "_LEAKED_HINT_RE" trezarr/translate/engine.py
# 2 matches: definition (line ~657) + strip call (line ~760)

grep -c "_LEAKED_HINT_RE" trezarr/translate/validate.py
# 0 — validate.py unchanged; HINT_SCAFFOLD_RE (Check 8) backstop intact
```

## Deviations from Plan

None — plan executed exactly as written.

Test 4 (`test_parse_preserves_source_paren_title_card`) passed both before and after implementation — this is correct behavior since it verifies the *absence* of an unintended side-effect. The plan's "all four MUST FAIL" note applies to the functionality tests; the preservation test is a non-regression guard that is correct to pass throughout.

## Invariants Confirmed Untouched

- `validate.py` — `HINT_SCAFFOLD_RE` (Check 8 backstop) unchanged; no `_LEAKED_HINT_RE` added
- `reconcile.py` — unchanged
- `attribute.py` — unchanged
- `build_translate_prompt` pronoun hint construction — unchanged
- `build_review_prompt` — unchanged
- `REVIEW_SCAFFOLD_RE` / `_reject_scaffolded` Pass-4 splice guard — unchanged

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The change is entirely within the `parse_numbered_response` pure function.

## TDD Gate Compliance

- RED gate: `test(quick-260608-e8r)` commit `001c491` exists (3/4 tests failed as expected)
- GREEN gate: `feat(quick-260608-e8r)` commit `53a4863` exists (all 4 tests pass, full suite green)

## Self-Check: PASSED

- `trezarr/translate/engine.py` — modified, `_LEAKED_HINT_RE` defined + strip call present
- `tests/translate/test_engine.py` — modified, all 4 test functions present
- RED commit `001c491` — verified in git log
- GREEN commit `53a4863` — verified in git log
- Full suite: 484 passed, 0 new failures
