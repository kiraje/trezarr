---
phase: 13-backend-episodes-enrichment
plan: "02"
subsystem: translate-engine,ledger
tags: [d-06, d-05, api-02, series-id, ledger, bulk-query, wave-1]
dependency_graph:
  requires:
    - "13-01 (Wave-0 RED stubs)"
  provides:
    - "D-06 fix: engine.py success-path LedgerEntry carries series_id=str(arr_series_id)"
    - "D-05 bulk helper: translated_counts_for_series in ledger_sqla.py"
  affects:
    - "trezarr/translate/engine.py"
    - "trezarr/output/ledger_sqla.py"
    - "tests/translate/test_engine.py"
    - "tests/web/test_library_api.py"
tech_stack:
  added: []
  patterns:
    - "arr_series_id extracted outside session_factory guard for Step-11 ledger access"
    - "SQLAlchemy func.count() + GROUP BY for bulk aggregate query"
    - "ProcessedFile.series_id.in_(str_ids) parameterized IN clause (T-13-02)"
    - "Early return {} guard for empty series_ids list"
key_files:
  created: []
  modified:
    - "trezarr/translate/engine.py — D-06 fix: arr_series_id extracted before 3-pass guard; Step 11 LedgerEntry carries series_id=_ledger_series_id"
    - "trezarr/output/ledger_sqla.py — add func to sqlalchemy import; append translated_counts_for_series module-level async function"
    - "tests/translate/test_engine.py — fix test stub: VI-diacritic mock text, writable quarantine_dir, check_by_output_path mock"
    - "tests/web/test_library_api.py — fix test stub: add content_hash to ProcessedFile rows"
decisions:
  - "arr_series_id extracted outside the if-eligible_item-and-session_factory block so it is in scope at Step 11 even when session_factory=None (the test-case scenario)"
  - "Redundant inner arr_series_id assignment replaced by comment referencing D-06 fix for clarity"
  - "translated_counts_for_series placed as a module-level function (not a method) because it accepts session_factory as a parameter — consistent with the 13-PATTERNS spec"
  - "Test stub bugs fixed as Rule 1 deviations: wrong mock LLM text (à is not a VI diacritic), missing check_by_output_path mock, no quarantine dir, missing content_hash in ProcessedFile rows"
metrics:
  duration: "6 min"
  completed: "2026-06-03T18:04:48Z"
  tasks: 2
  files: 4
---

# Phase 13 Plan 02: D-06 Engine Fix + D-05 Bulk Count Helper Summary

**One-liner:** D-06 series_id written to success-path LedgerEntry in engine.py (arr_series_id lifted outside session_factory guard), D-05 translated_counts_for_series one-query GROUP BY aggregate added to ledger_sqla.py.

## What Was Built

**Task 1: D-06 engine.py fix**

At the Step 11 LedgerEntry construction site, two changes were needed to correctly expose `arr_series_id`:

1. `arr_series_id` was previously assigned only inside the `if eligible_item is not None and session_factory is not None:` block. The test (and production caller with no session_factory) passes `eligible_item` without `session_factory`, so `arr_series_id` was undefined at Step 11. Fixed by extracting it unconditionally before the three-pass guard:

```python
arr_series_id = (
    getattr(eligible_item.media_item, "series_id", None) or 0
    if eligible_item is not None
    else 0
)
```

2. Step 11 LedgerEntry now carries:
```python
_ledger_series_id: str | None = (
    str(arr_series_id) if eligible_item is not None and arr_series_id else None
)
await ledger.record(LedgerEntry(
    ...
    series_id=_ledger_series_id,
))
```

The three quarantine paths (~line 812, ~911, ~1089) intentionally remain without `series_id` — they have no `eligible_item` context at those sites.

**Task 2: D-05 translated_counts_for_series in ledger_sqla.py**

Added `func` to the existing `from sqlalchemy import select` line and appended a new module-level async function:

```python
async def translated_counts_for_series(
    session_factory: async_sessionmaker,
    series_ids: list[int],
) -> dict[str, int]:
```

Body: early-return `{}` when empty, convert to `str_ids`, execute one `GROUP BY` aggregate query using `func.count().label("n")` and `ProcessedFile.series_id.in_(str_ids)`, return `{row.series_id: row.n for row in result}`.

## Verification Results

```
uv run pytest tests/translate/test_engine.py::test_ledger_records_series_id_on_success -xq
1 xpassed in 0.22s

uv run pytest tests/web/test_library_api.py::test_translated_counts_for_series -xq
1 passed in 0.29s

uv run pytest tests/ -q
364 passed, 1 skipped, 8 xfailed, 47 xpassed, 1 warning in 5.10s
```

Zero hard failures. Both target stubs are GREEN (XPASSED). Full suite baseline: Wave-0 had 10 xfailed, 45 xpassed; Wave-1 has 8 xfailed, 47 xpassed — 2 stubs promoted from XFAIL to XPASS.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: D-06 engine fix + test stub fix | 3f204e0 | trezarr/translate/engine.py, tests/translate/test_engine.py |
| Task 2: D-05 bulk helper + test stub fix | 86eb616 | trezarr/output/ledger_sqla.py, tests/web/test_library_api.py |

## Deviations from Plan

### Auto-fixed Issues (Rule 1 — Bugs in Wave-0 Test Stubs)

**1. [Rule 1 - Bug] test_ledger_records_series_id_on_success: mock LLM response not VI-diacritic**
- **Found during:** Task 1 verification
- **Issue:** Mock returned `"[1] Xin chào\n[2] Thế giới"`. "Xin chào" uses `à` (U+00E0, Latin Extended-A / French range), NOT in the Vietnamese diacritic range (U+1E00-U+1EFF). `validate_subdoc` check 3 got ratio 0.50 < threshold 0.70, quarantined before Step 11.
- **Fix:** Changed mock to `"[1] Được rồi\n[2] Thế giới"`. Both "Được" (ợ = U+1EE3) and "rồi" (ồ = U+1ED3) are in the VI range; ratio = 2/2 = 1.0.
- **Files modified:** tests/translate/test_engine.py
- **Commit:** 3f204e0

**2. [Rule 1 - Bug] test_ledger_records_series_id_on_success: no writable quarantine_dir**
- **Found during:** Task 1 verification (same test run)
- **Issue:** Test used `TrezarrSettings()` which defaults `translate_quarantine_dir=/config/quarantine`. On macOS test runner, `/config` is read-only → `OSError: Read-only file system`. This prevented the test from running at all.
- **Fix:** Changed to `TrezarrSettings(translate_quarantine_dir=str(tmp_path / "quarantine"))`.
- **Files modified:** tests/translate/test_engine.py
- **Commit:** 3f204e0

**3. [Rule 1 - Bug] test_ledger_records_series_id_on_success: missing check_by_output_path mock**
- **Found during:** Task 1 implementation analysis
- **Issue:** Engine Step 3 calls `ledger.check_by_output_path()` when `check()` returns None and dest exists. MagicMock auto-creates it as a sync MagicMock, but the engine `await`s it.
- **Fix:** Added `mock_ledger.check_by_output_path = AsyncMock(return_value=None)` to the test setup.
- **Files modified:** tests/translate/test_engine.py
- **Commit:** 3f204e0

**4. [Rule 1 - Bug] test_translated_counts_for_series: ProcessedFile rows missing content_hash**
- **Found during:** Task 2 verification
- **Issue:** Test created `ProcessedFile(...)` without `content_hash`. The column is `nullable=False` → `sqlalchemy.exc.IntegrityError: NOT NULL constraint failed: processed_file.content_hash`.
- **Fix:** Added `content_hash="a1b2c3d4e5f6000N"` (unique 16-char hex) to each row.
- **Files modified:** tests/web/test_library_api.py
- **Commit:** 86eb616

**5. [Rule 1 - Bug] engine.py: arr_series_id undefined when session_factory=None**
- **Found during:** Task 1 analysis
- **Issue:** `arr_series_id` was only set inside `if eligible_item is not None and session_factory is not None:`. When the test passes `eligible_item` but no `session_factory`, `arr_series_id` was undefined at Step 11.
- **Fix:** Extracted `arr_series_id` outside the three-pass guard (see "What Was Built" above). Removed the redundant inner assignment.
- **Files modified:** trezarr/translate/engine.py
- **Commit:** 3f204e0

## Known Stubs

None introduced by this plan. The 8 remaining XFAIL stubs in test_library_api.py (for `get_series_episodes`, envelope shape, audio language, etc.) are intentional — Wave 2 / Wave 3 will implement them.

## Threat Flags

None — changes are limited to server-side Sonarr ID int→str conversion and parameterized SQLAlchemy IN queries. No new network endpoints or auth paths introduced.

## Self-Check: PASSED

- [x] trezarr/translate/engine.py modified with _ledger_series_id + series_id= in LedgerEntry
- [x] trezarr/output/ledger_sqla.py has translated_counts_for_series function
- [x] Commit 3f204e0 exists: `git log --oneline | grep 3f204e0`
- [x] Commit 86eb616 exists: `git log --oneline | grep 86eb616`
- [x] Full suite: 364 passed, 0 failed
- [x] test_ledger_records_series_id_on_success: XPASSED
- [x] test_translated_counts_for_series: XPASSED
