---
phase: 04-series-bible-store-schema
plan: "03"
subsystem: bible-store
tags: [bible-store, character, term-dictionary, merge-inferred, lock-precedence, bible-event, audit-log, carry-forward, atomicity, mvp-vertical-slice, tdd]
dependency_graph:
  requires:
    - trezarr/bible/models.py (Phase 04-01 — Character, TermDictionary, BibleEvent models)
    - trezarr/bible/dto.py (Phase 04-02 — CharacterDTO, TermDTO, BibleEventDTO)
    - trezarr/bible/store.py (Phase 04-02 — get_or_create_series, load_series_bible base)
    - tests/db/conftest.py (Phase 04-01 — db_engine + session_factory fixtures)
  provides:
    - trezarr/bible/merge.py (pure-Python lock-precedence policy + accessor)
    - trezarr/bible/store.py (extended: get_character, get_term, upsert_character, upsert_term, merge_inferred + private helpers)
  affects:
    - trezarr/bible/store.py (extended, not replaced)
tech_stack:
  added: []
  patterns:
    - Pure-Python policy module (no SQLAlchemy, no async) for exhaustive unit testing
    - get_locked_fields() accessor pattern for Phase-8 bible_lock table swap (D-34)
    - _merge_inferred_in_session() re-reads DB row inside transaction (HIGH finding fix)
    - Public-function-only transaction ownership (no nested session.begin() blocks)
    - VALID_SOURCES + MERGEABLE_FIELDS whitelists enforced before any DB access
    - First-insert events: one BibleEvent per non-None field with old_value=None
    - SQLAlchemy event-listener atomicity injection for test 5 (not brittle monkey-patches)
    - Pre/post delta pattern for DB event count assertions (avoids first-insert count confusion)
    - TDD RED/GREEN per task: failing tests committed before implementation
key_files:
  created:
    - trezarr/bible/merge.py
    - tests/bible/test_merge_policy_pure.py
    - tests/bible/test_merge_inferred.py
    - tests/bible/test_carry_forward.py
    - tests/bible/test_bible_event_audit.py
  modified:
    - trezarr/bible/store.py (extended with 3 private helpers + 5 public functions + 2 constants)
decisions:
  - "Pre/post delta pattern for event count assertions avoids confusion with first-insert events from upsert_character"
  - "test_bible_event_carries_all_required_fields filters by episode_key to isolate the merge event from the first-insert event"
  - "_merge_inferred_in_session returns (DTO, []) on no-op path and (SQLA_row, events) on change path; merge_inferred normalizes this via isinstance check"
  - "MERGEABLE_FIELDS whitelist validated in BOTH _merge_inferred_in_session and public merge_inferred (fail-fast before any session is opened)"
metrics:
  duration_seconds: 498
  completed_date: "2026-06-01"
  tasks_completed: 2
  files_changed: 6
---

# Phase 4 Plan 03: Character/Term Merge Engine Summary

Pure-Python lock-precedence policy (merge.py) + store extension with get_character/get_term/upsert_character/upsert_term/merge_inferred — the atomic consistency-engine substrate that enforces human lock > prior > inference with correct old_value audit entries derived from a fresh DB re-read inside the transaction.

## What Was Built

### Task 1: Pure-Python merge policy (TDD)

**RED commit (`296be32`):** 8 failing tests in `tests/bible/test_merge_policy_pure.py` covering get_locked_fields, compute_field_changes (lock-skipping, no-op detection, genuine change, partial lock, absent attribute, clearing to None).

**GREEN commit (`946e4ef`):** `trezarr/bible/merge.py`:
- `get_locked_fields(entity_dto)`: reads `locked_fields` off any DTO/object defensively — returns `frozenset()` if attribute absent (no AttributeError). Phase 8 can swap to a `bible_lock` table by replacing this accessor without touching call sites (D-34).
- `compute_field_changes(entity_dto, inferred, locked)`: returns `[(field, old, new), ...]` for fields that actually need to change. Skips locked fields (D-34 human lock wins). Skips no-ops where `inferred == current` (D-32 / BIBLE-06 carry-forward). Treats absent attribute as `old_value=None`. Accepts `new_value=None` (clearing a field) as a genuine change.
- Strictly pure: no SQLAlchemy, no async, no IO. Verified by source inspection.
- All 8 policy tests pass.

### Task 2: Store extension with merge engine (TDD)

**RED commit (`571d039`):** 16 failing integration tests across 3 files (test_merge_inferred.py Tests 1-13, test_carry_forward.py Test 14, test_bible_event_audit.py Tests 15-16).

**GREEN commit (`27696fd`):** Extended `trezarr/bible/store.py`:

**Constants:**
- `VALID_SOURCES = frozenset({"inference", "lock", "import", "system"})` — validated before any DB write (T-04-11)
- `MERGEABLE_FIELDS = {"character": {"gender","rough_age","role"}, "term_dictionary": {"vietnamese_rendering","category"}, "series": {"register"}}` — identity columns (original_latin_name, source_term) explicitly not mergeable (T-04-10, MEDIUM finding)

**Private session-scoped helpers (no transaction ownership):**
- `_merge_inferred_in_session(session, row, entity_type, dto_cls, inferred, episode_key, source)`: Whitelist-validates inferred fields; re-reads the DB row via `session.get(type(row), row.id)` INSIDE the open transaction (HIGH finding fix — correct old_value even after concurrent writes); builds fresh DTO snapshot; derives locked+changes from fresh state; applies setattr + constructs BibleEvent rows; no nested session.begin().
- `_upsert_character_in_session(session, ...)`: SELECT-or-INSERT for Character; on INSERT emits one BibleEvent per non-None field (old_value=None); on existing row delegates to `_merge_inferred_in_session`.
- `_upsert_term_in_session(session, ...)`: Mirror for TermDictionary.

**Public API (only transaction owners):**
- `get_character(session_factory, series_id, original_latin_name) -> CharacterDTO | None`
- `get_term(session_factory, series_id, source_term) -> TermDTO | None`
- `upsert_character(session_factory, *, series_id, original_latin_name, ...) -> (CharacterDTO, list[BibleEventDTO])`: Opens single transaction, delegates to `_upsert_character_in_session`.
- `upsert_term(...)`: Mirror for TermDictionary.
- `merge_inferred(session_factory, entity_dto, inferred, episode_key, source) -> (entity_dto, list[BibleEventDTO])`: Source enum + whitelist validated BEFORE any session opened; determines entity type via isinstance (CharacterDTO/TermDTO/SeriesDTO); opens single transaction; delegates to `_merge_inferred_in_session` which re-reads the row for fresh state.

## Test Results

| Suite | Tests | Status |
|-------|-------|--------|
| tests/bible/test_merge_policy_pure.py | 8 | PASSED |
| tests/bible/test_merge_inferred.py | 13 | PASSED |
| tests/bible/test_carry_forward.py | 1 | PASSED |
| tests/bible/test_bible_event_audit.py | 2 | PASSED |
| **Total new (04-03)** | **24** | **PASSED** |
| tests/bible/ full (04-01 + 04-02 + 04-03) | 43 | PASSED |
| Full project suite | 184 passed, 1 skipped | PASSED |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DB event count assertions counted first-insert events from upsert_character**
- **Found during:** Task 2 GREEN (test failures after first test run)
- **Issue:** Plan's Test 1, 2, 3, 4 used absolute event counts (e.g. `evt_count == 0`, `evt_count == 1`), but `upsert_character` on a new row emits first-insert events (e.g. one for role). Tests that expected 0 events found 1 (the first-insert event), tests expecting 1 found 2.
- **Fix:** 
  - Tests 1 and 3 (no-op / lock): switched to pre/post delta assertion (`post_count == pre_count`).
  - Tests 2 and 4 (expected changes): switched to filtered query by `(entity_id, episode_key, field)` to isolate exactly the merge-created event.
  - Test 15 (`test_bible_event_carries_all_required_fields`): added `episode_key == "S01E02"` filter so `scalar_one()` returns the specific merge event rather than raising MultipleResultsFound.
- **Files modified:** `tests/bible/test_merge_inferred.py`, `tests/bible/test_bible_event_audit.py`
- **Commit:** `27696fd`

This is a test-design deviation (the implementation is correct), not an implementation bug. The plan's example event counts assumed direct `session.add(c)` character creation (no events), but the test helper uses `upsert_character` which correctly emits first-insert events.

## TDD Gate Compliance

| Gate | Commit | Message Pattern |
|------|--------|-----------------|
| Task 1 RED | `296be32` | `test(04-03): add failing tests for pure merge policy` |
| Task 1 GREEN | `946e4ef` | `feat(04-03): implement pure merge policy` |
| Task 2 RED | `571d039` | `test(04-03): add failing tests for merge_inferred, carry-forward, and bible_event audit` |
| Task 2 GREEN | `27696fd` | `feat(04-03): extend store.py with character/term upsert + merge_inferred engine` |

Both RED/GREEN gates present for both tasks. REFACTOR not needed — code is clean on first pass.

## Known Stubs

None. All functions are fully implemented. No hardcoded empty values, no placeholder text, no TODO/FIXME in production code.

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundaries introduced. All changes are internal persistence logic.

| Flag | File | Description |
|------|------|-------------|
| T-04-08 (mitigated) | trezarr/bible/store.py | `_merge_inferred_in_session` re-reads row inside transaction; old_value always reflects actual pre-write state (HIGH finding fix, verified by Test 9) |
| T-04-09 (mitigated) | trezarr/bible/store.py | No nested session.begin() blocks; public functions own the only transactions (HIGH finding fix, verified by Test 10) |
| T-04-10 (mitigated) | trezarr/bible/store.py | MERGEABLE_FIELDS whitelist enforced before any DB write; identity columns rejected with ValueError (MEDIUM finding, verified by Test 11) |
| T-04-11 (mitigated) | trezarr/bible/store.py | VALID_SOURCES check before DB write; invalid source raises ValueError before any session is opened (verified by Test 7) |
| T-04-12 (mitigated) | trezarr/bible/store.py | Atomicity via single session.begin() block; event INSERT failure rolls back UPDATE (verified by Test 5 using SQLAlchemy event listener injection) |
| T-04-SC (accepted) | — | No new package installs — inherits from 04-01 |

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| trezarr/bible/merge.py exists | PASSED |
| trezarr/bible/store.py extended (not replaced) | PASSED |
| tests/bible/test_merge_policy_pure.py exists | PASSED |
| tests/bible/test_merge_inferred.py exists | PASSED |
| tests/bible/test_carry_forward.py exists | PASSED |
| tests/bible/test_bible_event_audit.py exists | PASSED |
| Commits 296be32, 946e4ef, 571d039, 27696fd in history | PASSED |
| merge.py has no SQLAlchemy/async/IO imports (source inspection) | PASSED |
| VALID_SOURCES == frozenset({'inference','lock','import','system'}) | PASSED |
| 'original_latin_name' not in MERGEABLE_FIELDS['character'] | PASSED |
| Private helpers _merge_inferred_in_session, _upsert_character_in_session, _upsert_term_in_session present | PASSED |
| 24 new tests pass | PASSED |
| Full suite 184 passed, 1 skipped, 0 failed | PASSED |
