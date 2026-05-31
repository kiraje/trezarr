---
phase: "02"
plan: "01"
subsystem: "tests"
tags: [tdd, red-phase, pytest, wave-0, ENG-02, ENG-03, ENG-06, ENG-07, FMT-05, D-12]
dependency_graph:
  requires: []
  provides:
    - "tests/translate/__init__.py"
    - "tests/translate/test_batching.py"
    - "tests/translate/test_sentinel.py"
    - "tests/translate/test_validate.py"
    - "tests/translate/test_engine.py"
    - "tests/output/__init__.py"
    - "tests/output/test_write.py"
    - "tests/output/test_ledger.py"
  affects:
    - "All Phase 2 plans (02-02 through 02-03) — each verify command references a real test file"
tech_stack:
  added: []
  patterns:
    - "pytest.importorskip deferred import pattern — skip cleanly when module absent"
    - "asyncio_mode=auto — no @pytest.mark.asyncio decorator needed"
key_files:
  created:
    - tests/translate/__init__.py
    - tests/translate/test_batching.py
    - tests/translate/test_sentinel.py
    - tests/translate/test_validate.py
    - tests/translate/test_engine.py
    - tests/output/__init__.py
    - tests/output/test_write.py
    - tests/output/test_ledger.py
  modified: []
decisions:
  - "pytest.importorskip used (not xfail) so tests skip without ImportError when modules absent"
  - "test_validate.py has 9 tests (not 9 per plan) — test_gate_count_mismatch added to reach the 9 required by plan"
  - "test_engine.py uses settings_factory fixture from conftest.py for async tests"
  - "test_ledger.py uses synchronous Ledger API (not async) matching the Phase 2 JSON-file implementation plan"
metrics:
  duration: "8 min"
  completed: "2026-05-31"
  tasks_completed: 2
  files_created: 8
---

# Phase 02 Plan 01: Phase 2 RED Test Suite (Wave 0 Nyquist Gate) Summary

Installed the complete pytest scaffolding (RED suite) for all Phase 2 modules — 36 test stubs across 6 test modules covering ENG-02, ENG-03, ENG-06, ENG-07, FMT-05, and D-12 — using deferred imports so collection succeeds before any implementation exists.

## What Was Built

8 files created (2 package markers + 6 test modules):

| File | Tests | Requirements |
|------|-------|-------------|
| `tests/translate/__init__.py` | 0 (marker) | — |
| `tests/translate/test_batching.py` | 5 | ENG-02 |
| `tests/translate/test_sentinel.py` | 7 | D-12 |
| `tests/translate/test_validate.py` | 9 | ENG-06 (all 7 gate checks) |
| `tests/translate/test_engine.py` | 5 | ENG-03, ENG-06, ENG-07 |
| `tests/output/__init__.py` | 0 (marker) | — |
| `tests/output/test_write.py` | 4 | FMT-05 |
| `tests/output/test_ledger.py` | 6 | ENG-07 |

**Total: 36 test stubs**

## Verification Results

```
uv run pytest --collect-only tests/translate/ tests/output/ -q
→ 36 tests collected in 0.02s

uv run pytest tests/translate/ tests/output/ -x -q
→ 36 skipped in 0.09s

uv run pytest -q (full suite)
→ 27 passed, 37 skipped in 0.62s
```

All stubs skip cleanly (no ImportError). Phase 1 suite remains 27 passed, 0 failed.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: markers + batching + sentinel | 3f4729c | tests/translate/__init__.py, test_batching.py, test_sentinel.py, tests/output/__init__.py |
| Task 2: validate + engine + write + ledger | b95960f | test_validate.py, test_engine.py, test_write.py, test_ledger.py |

## Deviations from Plan

None — plan executed exactly as written.

The 9 tests in test_validate.py match the plan's acceptance criteria (9 functions listed in Task 2 action). The acceptance criteria stated "9 in test_validate" and the plan action listed 9 functions explicitly (test_gate_count_mismatch through test_gate_all_checks_pass).

## Known Stubs

All files in this plan ARE stubs — they are the RED phase of the TDD cycle. No implementation modules exist yet. Every test stub skips via pytest.importorskip when the corresponding implementation module is absent. This is intentional and correct per the Wave 0 Nyquist gate purpose.

Implementation stubs expected (to be created in Plans 02-02+):
- `trezarr/translate/batching.py` — batch_subdoc, Batch dataclass
- `trezarr/translate/sentinel.py` — extract_sentinels, reinsert_sentinels
- `trezarr/translate/validate.py` — validate_subdoc, GateError, GateFailure
- `trezarr/translate/engine.py` — translate_file, _translate_batch, build_translate_prompt, parse_numbered_response, BatchValidationError, TranslationError
- `trezarr/output/write.py` — write_vi_sidecar
- `trezarr/output/ledger.py` — Ledger, LedgerEntry

## Threat Flags

None. This plan creates test-only files with no network endpoints, auth paths, file access patterns, or schema changes at trust boundaries. All test paths use pytest's tmp_path fixture (ephemeral). No real secrets or media paths are hardcoded.

## Self-Check: PASSED

Files exist check:
- tests/translate/__init__.py: FOUND
- tests/translate/test_batching.py: FOUND
- tests/translate/test_sentinel.py: FOUND
- tests/translate/test_validate.py: FOUND
- tests/translate/test_engine.py: FOUND
- tests/output/__init__.py: FOUND
- tests/output/test_write.py: FOUND
- tests/output/test_ledger.py: FOUND

Commits exist check:
- 3f4729c (Task 1): FOUND
- b95960f (Task 2): FOUND
