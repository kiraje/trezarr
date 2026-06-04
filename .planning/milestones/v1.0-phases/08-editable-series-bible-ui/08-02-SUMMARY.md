---
phase: "08"
plan: "02"
subsystem: "bible-store"
tags: ["store", "lock-write", "bible", "reconcile", "worker", "tdd-green"]
dependency_graph:
  requires:
    - "08-01 (RED test scaffold)"
  provides:
    - "apply_human_edit_character (D-80 lock-writer)"
    - "apply_human_edit_address_pair (D-80 lock-writer with D-87 non-None guard)"
    - "apply_human_edit_term (D-80 lock-writer, source_term lookup)"
    - "apply_human_edit_series (D-80 lock-writer, register CR-02 alias)"
    - "delete_address_pair / delete_term (D-83 safe leaf-row deletes)"
    - "load_field_history (D-82 audit history with LIMIT 100)"
    - "load_all_series (list view, no eager-load)"
    - "get_series_lock(series_id) public accessor (D-81)"
    - "KINSHIP_RECIPROCAL D-90 gap fill (bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày)"
    - "KNOWN_PRONOUN_TERMS_SELF, KNOWN_PRONOUN_TERMS_ADDRESS constants (D-86)"
  affects:
    - "trezarr/bible/store.py"
    - "trezarr/translate/reconcile.py"
    - "trezarr/web/worker.py"
    - "tests/bible/test_human_edit.py"
tech_stack:
  added: []
  patterns:
    - "D-80 lock-writer: WR-01 re-read inside txn + locked_fields reassign (not .append()) + BibleEvent(source=lock)"
    - "D-87 pre-session non-None guard for address pair lock before opening DB"
    - "D-82 load_field_history: BibleEvent query filtered + ordered desc + LIMIT 100"
    - "D-83 delete functions: series_id guard + session.delete + no BibleEvent"
    - "T-08-01 MERGEABLE_FIELDS whitelist validated before any setattr"
    - "T-08-05 cross-series delete guard: row.series_id != series_id raises ValueError"
key_files:
  created: []
  modified:
    - "trezarr/bible/store.py"
    - "trezarr/translate/reconcile.py"
    - "trezarr/web/worker.py"
    - "tests/bible/test_human_edit.py"
decisions:
  - "apply_human_edit_term accepts source_term (not term_id) to match the test contract from Plan 08-01; looks up or creates term by source_term identity key inside the transaction"
  - "apply_human_edit_series uses getattr(row, 'register') — the ORM column name is register (not register_value); MERGEABLE_FIELDS['series'] whitelist uses 'register' consistently"
  - "KINSHIP_RECIPROCAL D-90 fill done via .update() call after the dict literal — purely additive, zero existing keys changed"
  - "test_human_edit.py xfail stubs rewritten to fully passing GREEN tests with real assertions (plan-approved pattern)"
metrics:
  duration: "4 minutes"
  completed: "2026-06-02"
  tasks_completed: 2
  files_changed: 4
---

# Phase 08 Plan 02: Store Write Path + Reconcile Gap Fill Summary

**One-liner:** All 8 D-80 lock-writers + D-83 deletes + D-82 history + D-86 pronoun constants implemented and proven GREEN at the store layer before the REST router exists.

## What Was Built

### Task 1: KINSHIP_RECIPROCAL D-90 fill + KNOWN_PRONOUN_TERMS + get_series_lock

**trezarr/translate/reconcile.py:**
- `KINSHIP_RECIPROCAL.update()` call after the dict literal adds 10 new entries (5 kinship relationships × 2 directions): bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày — all round-trip correctly.
- `KNOWN_PRONOUN_TERMS_SELF` and `KNOWN_PRONOUN_TERMS_ADDRESS` module-level list constants (D-86): single source of truth for the Bible editor pronoun combo, exposed via `/api/pronouns` in Plan 08-03.

**trezarr/web/worker.py:**
- `get_series_lock(series_id: int) -> asyncio.Lock` public accessor added after `_series_locks` declaration. Uses `_series_locks.setdefault(series_id, asyncio.Lock())` — same pattern as the internal `_execute_job` acquire. No -1 sentinel (Bible endpoints always have real series_id).

### Task 2: Eight store functions in store.py

**trezarr/bible/store.py** — eight new public functions added in the Phase 08 block before `record_relationship_event`:

1. `apply_human_edit_character(session_factory, *, character_id, series_id, field, new_value, lock=False)`: T-08-01 field whitelist → WR-01 re-read → setattr → locked_fields reassign → BibleEvent(source="lock") → (CharacterDTO, BibleEventDTO).

2. `apply_human_edit_address_pair(session_factory, *, address_map_id, series_id, self_term, address_term, lock=False)`: D-87 non-None guard before session → WR-01 re-read → per-field BibleEvent → pair-level locked_fields reassign → (AddressMapDTO, list[BibleEventDTO]).

3. `apply_human_edit_term(session_factory, *, series_id, source_term, field, new_value, lock=False)`: looks up term by source_term (creates on INSERT path if field="vietnamese_rendering") → same WR-01/reassign/event pattern → (TermDTO, BibleEventDTO).

4. `apply_human_edit_series(session_factory, *, series_id, field, new_value, lock=False)`: uses `getattr(row, field)` where field="register" matches the ORM column name → same pattern → (SeriesDTO, BibleEventDTO).

5. `delete_address_pair(session_factory, *, address_map_id, series_id)`: T-08-05 series_id guard → `session.delete(row)` → `{"deleted": address_map_id}`.

6. `delete_term(session_factory, *, term_id, series_id)`: mirror of delete_address_pair for TermDictionary.

7. `load_field_history(session_factory, series_id, entity_type, entity_id, field=None, limit=100)`: read-only BibleEvent query filtered by entity, optionally field, ordered created_at DESC, LIMIT 100 (T-08-02).

8. `load_all_series(session_factory)`: `select(Series).order_by(Series.id)` → `[SeriesDTO.model_validate(r, from_attributes=True) for r in rows]`. No eager-load (list view).

**tests/bible/test_human_edit.py:**
- Rewritten from 8 xfail stubs to 8 fully passing GREEN tests covering all BIBLE-08/09 invariants at the store layer.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: KINSHIP_RECIPROCAL + KNOWN_PRONOUN_TERMS + get_series_lock | 7f7ae49 | trezarr/translate/reconcile.py, trezarr/web/worker.py |
| Task 2: 8 store functions + GREEN test_human_edit.py | a8957ce | trezarr/bible/store.py, tests/bible/test_human_edit.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Signature mismatch] apply_human_edit_term uses source_term not term_id**
- **Found during:** Task 2 — the Plan 08-01 test stub calls `apply_human_edit_term(..., source_term="hello", ...)` but the plan's `<behavior>` spec says `term_id`.
- **Fix:** Implemented `apply_human_edit_term` with `source_term` parameter (identity key lookup). Function selects by `(series_id, source_term)` and creates the term row on INSERT path if field="vietnamese_rendering". This matches the test contract written in Plan 08-01.
- **Files modified:** trezarr/bible/store.py
- **Commit:** a8957ce

## Known Stubs

None — all 8 functions are fully implemented. No `assert False` placeholders remain in test_human_edit.py.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. All threat register mitigations (T-08-01 through T-08-05) are implemented as specified.

## Self-Check: PASSED

- trezarr/bible/store.py modified: FOUND
- trezarr/translate/reconcile.py modified: FOUND
- trezarr/web/worker.py modified: FOUND
- tests/bible/test_human_edit.py modified: FOUND
- 8 store functions grep check: FOUND (count=8)
- Commit 7f7ae49 (Task 1): FOUND
- Commit a8957ce (Task 2): FOUND
- test_kinship_reciprocal_bac_chau: XPASS (GREEN)
- All 8 test_human_edit.py tests: PASSED
- Full suite: 282 passed, 0 failures
