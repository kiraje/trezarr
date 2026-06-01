---
phase: 06-relationship-evolution-self-review
plan: 02
subsystem: bible/analyze/reconcile
tags: [bible, relationship-evolution, reconcile, dto, orm, config]
dependency_graph:
  requires:
    - "06-01 (Wave-0 RED stubs)"
    - "Phase 4 relationship_event table (schema locked)"
    - "Phase 5 reconcile_attributions base (lock check, confidence gate)"
  provides:
    - "BIBLE-07-A: record_relationship_event store writer"
    - "BIBLE-07-B: load_series_bible extended with relationship_events"
    - "BIBLE-07-C: transition-precedence branch in reconcile_attributions"
    - "BIBLE-07-D: lock beats transition (structural, D-34)"
    - "BIBLE-07-E: Phase-5 safe-default invariant preserved"
    - "BIBLE-07-F: case-insensitive name matching in merge_bible_analysis (CR-01)"
  affects:
    - "trezarr/translate/reconcile.py (precedence order changed)"
    - "trezarr/bible/analyze.py (merge_bible_analysis signature extended)"
tech_stack:
  added: []
  patterns:
    - "record_relationship_event: INSERT-only with dedup key (series_id, char_a_id, char_b_id, episode_marker)"
    - "Series.relationship_events ORM relationship + selectinload in load_series_bible"
    - "_find_transition_for_pair: undirected match, episode_marker exact filter (Pitfall 6)"
    - "_derive_transition_terms: LLM-suggested → get_safe_default fallback (D-54)"
    - "Lock-first restructuring: lock check before confidence gate in for-loop"
    - "merge_bible_analysis pre-seeding name_to_id from existing DB characters (CR-01)"
key_files:
  created: []
  modified:
    - "trezarr/bible/models.py"
    - "trezarr/bible/dto.py"
    - "trezarr/bible/analyze.py"
    - "trezarr/translate/reconcile.py"
    - "trezarr/config.py"
decisions:
  - "merge_bible_analysis signature extended to accept series_id + settings kwargs (backward compat via series_dto | None)"
  - "name_to_id pre-seeded from existing DB characters so CR-01 test works without analysis.characters populated"
  - "lock check moved to TOP of for-loop (before survivors gate) — structural guarantee of D-34"
  - "transition branch uses getattr(bible, 'relationship_events', []) guard for old-shape SeriesBibleDTO"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-06-02"
  tasks_completed: 2
  files_modified: 5
---

# Phase 6 Plan 02: Bible Store Foundation + Relationship Evolution Reconciliation Summary

BIBLE-07 delivered end-to-end — relationship transitions from Pass-1 are persisted and applied in reconciliation with correct precedence (lock > transition > confidence gate > safe default).

## Tasks Completed

### Task 1: Bible store foundation — models.py ORM relationship, dto.py DTO + SeriesBibleDTO, store.py writer + load extension, config.py Phase-6-A fields

- `models.py`: Added `Series.relationship_events` ORM relationship and `RelationshipEvent.series` back-reference — required for `selectinload(Series.relationship_events)` in `load_series_bible`.
- `dto.py`: Added `RelationshipEventDTO` (mirrors `AddressMapDTO`, `from_attributes=True`); added `suggested_self_term`/`suggested_address_term` as in-memory-only fields (not persisted, schema locked per D-31). Extended `SeriesBibleDTO` with `relationship_events: list[RelationshipEventDTO] = []` (safe additive default).
- `store.py` (committed by prior agent session as part of Phase-5 CR-01 fix): Added `RelationshipEvent` + `RelationshipEventDTO` imports; extended `load_series_bible` with `selectinload(Series.relationship_events)` and `relationship_events=[...]` in DTO construction; added `record_relationship_event` INSERT-only writer with dedup key `(series_id, char_a_id, char_b_id, episode_marker)`.
- `analyze.py`: Added `RelationshipEventInference` Pydantic model; extended `BibleAnalysis` with `relationship_events: list[RelationshipEventInference] = []` (additive, safe default); extended `_build_analysis_prompt` with `episode_key` param and relationship_events instruction block; extended `merge_bible_analysis` signature to accept `series_id`/`settings` kwargs while remaining backward compatible; pre-seeded `name_to_id` from existing DB characters (CR-01 fix); added Step 5 to merge relationship events (per-row try/except, no total-failure raise — advisory only).
- `config.py`: Added Phase-6 settings group: `enable_relationship_events`, `relationship_event_min_confidence`, `enable_self_review`, `self_review_context_lines_k`, `self_review_max_cues_per_batch`.

**BIBLE-07-A, B, F: GREEN.**

### Task 2: Analyze + Reconcile — RelationshipEventInference, merge_bible_analysis Step 5, _find_transition_for_pair, transition-precedence branch in reconcile_attributions

- `reconcile.py`: Added `RelationshipEventDTO` to TYPE_CHECKING imports; added `_find_transition_for_pair` (undirected match, exact `episode_marker == episode_key` filter — Pitfall 6); added `_derive_transition_terms` (LLM-suggested terms → `get_safe_default` fallback, D-54); restructured for-loop to put lock check FIRST (before confidence gate — structural guarantee of D-34); inserted transition check after lock and before survivors gate; transition branch calls `upsert_address_pair` with `valid_from_episode=episode_key` (D-53).

**BIBLE-07-C, D, E: GREEN.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] merge_bible_analysis signature updated for backward compatibility**

- **Found during:** Task 1 — test uses `series_id` kwarg, existing code used positional `series_dto`
- **Issue:** The Wave-0 test calls `merge_bible_analysis(analysis=..., session_factory=..., series_id=..., episode_key=..., settings=...)` but the existing signature was `(session_factory, series_dto, analysis, episode_key)`.
- **Fix:** Made `series_dto` optional (defaults to `None`); added `series_id` and `settings` as keyword-only parameters. `series_dto.id` is used if `series_dto` is provided (backward compat with engine.py), otherwise `series_id` is used directly.
- **Files modified:** `trezarr/bible/analyze.py`

**2. [Rule 2 - Missing Critical Functionality] name_to_id pre-seeded from existing DB characters (CR-01)**

- **Found during:** Task 1 — `test_name_matching_case_insensitive` XFAIL after initial implementation
- **Issue:** Step 2 builds `name_to_id` only from `analysis.characters`. When the test passes a `BibleAnalysis` with NO characters (only `relationship_events`), `name_to_id` is empty and the CR-01 case-insensitive lookup fails silently.
- **Fix:** Added a pre-seeding step that loads existing Bible characters from the DB before Step 2, populating `name_to_id` with all known characters. Analysis characters upserted in Step 2 then override/add to the map.
- **Files modified:** `trezarr/bible/analyze.py`

**3. [Rule 1 - Bug] Lock check moved to top of for-loop (structural D-34 guarantee)**

- **Found during:** Task 2 — reviewing existing code structure before inserting transition branch
- **Issue:** The existing lock check was inside the `else` (below-threshold) branch. This means it was NOT the first check — a high-confidence attribution would bypass the lock check via the `if survivors:` branch. While existing tests passed (because high-confidence with a locked entry uses the existing entry anyway), adding the transition branch AFTER the lock check in the `else` branch would allow transitions to override locks.
- **Fix:** Moved lock check to the very top of the for-loop body, before the survivors gate and before the transition check. Both `if survivors:` and `else` branches now correctly follow: lock → transition → confidence gate → safe default.
- **Files modified:** `trezarr/translate/reconcile.py`

**4. [Note] store.py changes already present from prior agent session**

- A prior quick-fix session (`754292f`) had already added the `RelationshipEvent`/`RelationshipEventDTO` imports, `selectinload(Series.relationship_events)`, and `record_relationship_event` to store.py as part of a CR-01 fix for character identity in the store. These changes were committed before this plan executed. No duplicate work was done; my store.py edits merged cleanly with what was already there.

## Verification Results

All BIBLE-07 target test node IDs GREEN:

```
tests/bible/test_relationship_events.py::test_relationship_event_written_to_db   XPASS
tests/bible/test_relationship_events.py::test_load_series_bible_includes_events  XPASS
tests/bible/test_relationship_events.py::test_name_matching_case_insensitive     XPASS
tests/translate/test_reconcile.py::test_transition_authorizes_terms_change       XPASS
tests/translate/test_reconcile.py::test_lock_beats_transition                    XPASS
tests/translate/test_reconcile.py::test_no_transition_no_survivors_safe_default  XPASS
```

Full suite: `230 passed, 1 skipped, 4 xfailed, 6 xpassed` — all 226 pre-existing tests green.

D-39 boundary: `tests/bible/test_dto_boundary.py` PASSED (no SQLAlchemy leakage).

No `asyncio.Semaphore(...)` instantiations outside `llm/client.py`.

No `from trezarr.bible.models import` in `analyze.py` or `reconcile.py`.

## Self-Check: PASSED

Files created/modified exist:
- `trezarr/bible/models.py` — FOUND
- `trezarr/bible/dto.py` — FOUND (RelationshipEventDTO + SeriesBibleDTO.relationship_events)
- `trezarr/bible/analyze.py` — FOUND (RelationshipEventInference, Step 5, episode_key param)
- `trezarr/translate/reconcile.py` — FOUND (_find_transition_for_pair, transition branch)
- `trezarr/config.py` — FOUND (enable_relationship_events, enable_self_review)

Commits:
- `4409e0c`: Task 1 — Bible store foundation + analyze extension (BIBLE-07-A/B/F)
- `e3972b0`: Task 2 — transition-precedence branch in reconcile_attributions (BIBLE-07-C/D/E)
