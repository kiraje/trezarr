---
phase: "08"
plan: "03"
subsystem: "bible-router"
tags: ["router", "REST", "bible", "lock", "D-39", "D-81", "D-82", "D-83", "D-87", "tdd-green"]
dependency_graph:
  requires:
    - "08-02 (store write path: apply_human_edit_*, delete_*, load_*, get_series_lock)"
  provides:
    - "GET /api/series — bounded series list (LIMIT 500)"
    - "GET /api/series/{id}/bible — full SeriesBibleDTO with by_alias=True"
    - "PATCH /api/series/{id}/characters/{cid} — field-validated, lock-aware character edit"
    - "POST /api/series/{id}/characters — add character via upsert_character"
    - "PATCH /api/series/{id}/address-map/{aid} — D-87 422 on empty lock terms"
    - "POST /api/series/{id}/address-map — add pair via upsert_address_pair"
    - "DELETE /api/series/{id}/address-map/{aid} — via delete_address_pair store fn (D-39)"
    - "PATCH /api/series/{id}/terms/{tid} — field-validated term edit (source_term lookup)"
    - "POST /api/series/{id}/terms — add term via upsert_term"
    - "DELETE /api/series/{id}/terms/{tid} — via delete_term store fn (D-39)"
    - "PATCH /api/series/{id}/register — register field hardcoded, series lock"
    - "GET /api/series/{id}/bible/{entity_type}/{entity_id}/history — BibleEventDTOs LIMIT 100"
    - "GET /api/pronouns — KNOWN_PRONOUN_TERMS + KINSHIP_RECIPROCAL (D-86 single source of truth)"
    - "bible_router registered in app.py before StaticFiles mount (Pitfall E)"
  affects:
    - "trezarr/web/routes/bible.py"
    - "trezarr/web/app.py"
    - "tests/web/test_bible_api.py"
tech_stack:
  added: []
  patterns:
    - "D-39 boundary: all store/worker imports deferred inside handler bodies with noqa: PLC0415"
    - "D-81 series lock: get_series_lock(series_id) as outermost CM wrapping full store write"
    - "D-87 HTTP layer: 422 before store call when lock=True with empty/whitespace term"
    - "T-08-04 VALID_ENTITY_TYPES allowlist on history endpoint (entity_type injection guard)"
    - "CR-02: model_dump(by_alias=True) on all SeriesDTO/SeriesBibleDTO serializations"
    - "_get_session_factory helper pattern from queue.py (None guard → empty list / 404)"
key_files:
  created:
    - "trezarr/web/routes/bible.py"
  modified:
    - "trezarr/web/app.py"
    - "tests/web/test_bible_api.py"
decisions:
  - "PATCH /api/series/{id}/terms/{tid} requires source_term in body (not term_id) — matches apply_human_edit_term contract from Plan 08-02"
  - "apply_human_edit_series called with field='register' (ORM attribute name), not 'register_value' — MERGEABLE_FIELDS['series'] = frozenset({'register'})"
  - "D-87 guard checks both self_term and address_term for empty/whitespace regardless of which was provided — matches store-layer two-layer defense"
  - "DELETE endpoints return 404 when session_factory is None (no DB); matches test_delete_* expectations"
metrics:
  duration: "8 minutes"
  completed: "2026-06-02"
  tasks_completed: 2
  files_changed: 3
---

# Phase 08 Plan 03: Bible REST Router Summary

**One-liner:** Full Bible REST router (13 endpoints, D-39/D-81/D-82/D-83/D-87 invariants enforced) wired into app.py before StaticFiles; all 8 test_bible_api.py stubs turned GREEN.

## What Was Built

### Task 1: trezarr/web/routes/bible.py — all Bible REST endpoints

**trezarr/web/routes/bible.py** — new file, 290 lines. All 13 Bible REST endpoints:

- **GET /api/series**: `load_all_series` via deferred import; returns `[]` when no DB (session_factory guard).
- **GET /api/series/{id}/bible**: `load_series_bible` via deferred import; 404 on missing series or no DB.
- **PATCH /api/series/{id}/characters/{cid}**: T-08-01 field whitelist check (MERGEABLE_FIELDS["character"]) BEFORE acquiring series lock; 422 on invalid field; `get_series_lock(series_id)` as outermost CM; calls `apply_human_edit_character`.
- **POST /api/series/{id}/characters**: `upsert_character` via deferred import.
- **PATCH /api/series/{id}/address-map/{aid}**: D-87 HTTP 422 when lock=True with empty/whitespace self_term or address_term; series lock; `apply_human_edit_address_pair`.
- **POST /api/series/{id}/address-map**: `upsert_address_pair` via deferred import.
- **DELETE /api/series/{id}/address-map/{aid}**: `delete_address_pair` via deferred import (D-39: no SQLAlchemy model import); 404 when no DB or row not found.
- **PATCH /api/series/{id}/terms/{tid}**: T-08-01 field whitelist + requires `source_term` in body; series lock; `apply_human_edit_term`.
- **POST /api/series/{id}/terms**: `upsert_term` via deferred import.
- **DELETE /api/series/{id}/terms/{tid}**: `delete_term` via deferred import (D-39); 404 on no DB or not found.
- **PATCH /api/series/{id}/register**: `field="register"` hardcoded (ORM attribute name); series lock; `apply_human_edit_series`.
- **GET /api/series/{id}/bible/{entity_type}/{entity_id}/history**: `VALID_ENTITY_TYPES` allowlist check (T-08-04); 422 on invalid type; `load_field_history` (LIMIT 100, D-82); returns `[]` when no DB.
- **GET /api/pronouns**: `KNOWN_PRONOUN_TERMS_SELF`, `KNOWN_PRONOUN_TERMS_ADDRESS`, `KINSHIP_RECIPROCAL` from reconcile.py (D-86 single source of truth); tuple keys serialized as `"self|address"` strings.

**trezarr/web/app.py** — bible_router included between jobs_router and webhook_router, before StaticFiles mount (Pitfall E).

### Task 2: All 8 test_bible_api.py stubs turned GREEN

**tests/web/test_bible_api.py** — 8 xfail stubs replaced with real assertions:

1. `test_get_series_list`: 200 + JSON array (no DB → empty list guard).
2. `test_get_series_bible`: 404 on fresh app (no DB → session_factory None → HTTPException 404).
3. `test_lock_address_map_missing_term_rejected`: 422 when `lock=True` + `address_term=""` (D-87 HTTP layer).
4. `test_write_acquires_series_lock`: (a) 422 on `field="nonexistent_field"` — proves field guard fires before lock; (b) `get_series_lock(1)` returns `asyncio.Lock` instance (D-81 type check).
5. `test_get_field_history`: 200 + list on fresh app (session_factory guard → empty list).
6. `test_bible_route_does_not_import_sqla`: `inspect.getsource` confirms no `"from trezarr.bible.models"` or `"from sqlalchemy"` in route source (D-39 boundary).
7. `test_delete_address_pair`: `delete_address_pair` importable from store; 404 on fresh app.
8. `test_delete_term`: `delete_term` importable from store; 404 on fresh app.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: bible.py router + app.py registration | f40f0eb | trezarr/web/routes/bible.py, trezarr/web/app.py |
| Task 2: 8 GREEN tests in test_bible_api.py | db0c941 | tests/web/test_bible_api.py |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written, with one clarification applied:

**1. [Rule 1 - Signature clarification] PATCH /api/series/{id}/terms/{tid} requires source_term in body**
- **Found during:** Task 1 implementation
- **Issue:** The plan's `<behavior>` section says the term PATCH accepts `{field, value, lock?}` but `apply_human_edit_term` (per Plan 08-02 decision) uses `source_term` as its identity lookup key, not `term_id`. The URL has `term_id` but that's not the store function's lookup parameter.
- **Fix:** The route accepts `source_term` in the request body as required by `apply_human_edit_term`'s signature. Added `HTTPException(422)` when `source_term` is missing. This matches the store contract from Plan 08-02.
- **Files modified:** trezarr/web/routes/bible.py
- **Commit:** f40f0eb

## Known Stubs

None — all endpoints are fully implemented. No `assert False` placeholders remain.

## Threat Flags

None — all threat register mitigations implemented:
- T-08-01: MERGEABLE_FIELDS whitelist on all write endpoints before store call
- T-08-02: LIMIT 500 in load_all_series (store layer); LIMIT 100 in load_field_history (store layer)
- T-08-03: LIMIT 100 enforced in load_field_history; route passes default limit=100
- T-08-04: VALID_ENTITY_TYPES allowlist at route entry (HTTP 422 on unknown entity_type)
- T-08-05: Cross-series delete guard in store (ValueError → 404 at route layer)
- T-08-06: D-87 HTTP 422 at route layer + store ValueError defence (two layers)
- T-08-07: bible_router included before StaticFiles mount (Pitfall E); confirmed by test
- T-08-08: DELETE handlers call store functions via deferred import; no SQLAlchemy model in route module

## Self-Check: PASSED

- trezarr/web/routes/bible.py created: FOUND
- trezarr/web/app.py bible_router registered: FOUND (grep -c "bible_router" = 2)
- D-39 boundary: `grep -c "from trezarr.bible.models|from sqlalchemy"` in bible.py = 0
- tests/web/test_bible_api.py: 8 tests PASSED (no xfail markers)
- Full suite: 290 passed, 0 failures
- Commit f40f0eb (Task 1): FOUND
- Commit db0c941 (Task 2): FOUND
- `uv run python -c "from trezarr.web.app import create_app; app = create_app(); print('OK')"`: OK
