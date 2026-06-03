---
phase: 13-backend-episodes-enrichment
verified: 2026-06-04T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Confirm GET /api/library/series/{id}/episodes returns populated subtitles[] from live Bazarr at 192.168.5.42"
    expected: "bazarr_available=true and subtitles[] is non-empty for at least one episode that Bazarr has indexed; OR the fallback param form (seriesid without brackets) is identified and the call site is updated"
    why_human: "Tests mock Bazarr. The seriesid[] vs seriesid query-param form used by fetch_episode_inventory (marked TODO(phase-16) in library.py:302) cannot be verified without a live Bazarr at 192.168.5.42. If the bracketed form returns empty, the subtitle badges will be empty for all episodes."
---

# Phase 13: Backend Episodes Enrichment — Verification Report

**Phase Goal:** The `GET /api/library/series/{id}/episodes` endpoint is rewritten to return season-grouped episode records from Sonarr with audio languages and Bazarr subtitle inventory (fail-soft HTTP 200 always), and the Series + Movies list endpoints expose `translated_count`/`total_count` per item.
**Verified:** 2026-06-04T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /api/library/series/{id}/episodes` returns a JSON envelope with `seasons[]` grouped by season, each episode carrying `audio_languages`, `subtitles[]` (with `code2`, `hi`), `episode_key`, and `status`; endpoint always returns HTTP 200 even when Bazarr is down | ✓ VERIFIED | `library.py` lines 389-393 return the correct envelope; `get_series_episodes` returns JSONResponse HTTP 200 on all Bazarr-down paths (lines 319-322); test `test_get_series_episodes_envelope_shape` XPASSED (GREEN) |
| 2 | When Bazarr is unreachable, the endpoint returns all episode records with `subtitles: []` for each and `bazarr_available: false` — no 502, no empty page | ✓ VERIFIED | `library.py` lines 288-322: `BazarrError` is caught, `bazarr_available` stays `False`, `errors[]` gets an entry, function continues and returns HTTP 200; test `test_get_series_episodes_bazarr_disabled` and `test_get_series_episodes_bazarr_error` both XPASSED |
| 3 | `GET /api/library` series and movies list items include `translated_count` and `total_count` fields | ✓ VERIFIED | `library.py` lines 177-180 (series post-loop) add `translated_count` and `total_count` to every series item; lines 215-216 add them to every movie item; tests `test_get_library_series_count_fields` and `test_get_library_movies_count_fields` XPASSED |
| 4 | Backend tests cover the Bazarr fail-soft path, the correct `episode.id` join to Bazarr inventory, and the `audioLanguages` full-name-to-ISO lookup | ✓ VERIFIED | 9 phase-13 stubs all XPASSED in `uv run pytest tests/web/test_library_api.py tests/translate/test_engine.py -q` (output: `15 passed, 9 xpassed`); `test_get_series_episodes_bazarr_join_key` verifies D-02 join on `arr_id==episode.id` not `episodeFile.id`; `test_audio_language_normalization` verifies `"Korean/English" → ["ko","en"]` |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/web/routes/library.py` | Season-grouped endpoint + `_normalize_audio_languages` + `translated_counts_for_series` wiring | ✓ VERIFIED | 452 lines; `_normalize_audio_languages` at lines 68-103; `get_series_episodes` fully rewritten at lines 228-393; `get_library` extended with D-05 bulk query at lines 164-180 |
| `trezarr/translate/engine.py` | D-06: success-path `LedgerEntry` carries `series_id=_ledger_series_id` | ✓ VERIFIED | Lines 1106-1115: `_ledger_series_id = str(arr_series_id) if eligible_item is not None and arr_series_id else None`; `series_id=_ledger_series_id` passed to `LedgerEntry` |
| `trezarr/output/ledger_sqla.py` | `translated_counts_for_series` bulk aggregate helper | ✓ VERIFIED | Lines 176-218: module-level `async def translated_counts_for_series(session_factory, series_ids)` using `func.count()` + `.group_by(ProcessedFile.series_id)` + parameterized `.in_(str_ids)` |
| `tests/web/test_library_api.py` | 8 new stubs for API-01/API-02 | ✓ VERIFIED | Lines 77-396: 8 tests present, all substantive (not empty stubs), all XPASSED (GREEN after implementation) |
| `tests/translate/test_engine.py` | `test_ledger_records_series_id_on_success` stub for D-06 | ✓ VERIFIED | Lines 449-531: full test with mock ledger, real `translate_file` call, asserts `done_entries[0].series_id == "42"`; XPASSED |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `library.py:get_series_episodes` | `bazarr.py:BazarrClient.fetch_episode_inventory` | `BazarrClient.from_settings(settings).fetch_episode_inventory(series_id)` wrapped in `try/except BazarrError` | ✓ WIRED | Lines 296-322; fail-soft: `BazarrError` caught, `bazarr_available` stays False, function continues |
| `library.py:_normalize_audio_languages` | `rank.py:_ORIG_LANG_NAME_TO_CODE2` | Deferred import inside helper body (`from trezarr.source_selection.rank import _ORIG_LANG_NAME_TO_CODE2`) | ✓ WIRED | Lines 85-99; `rank.py:55-94` contains the map with `"korean": "ko"`, `"english": "en"` |
| `library.py:get_library` | `ledger_sqla.py:translated_counts_for_series` | `await translated_counts_for_series(session_factory, _s_ids)` inside `if session_factory:` guard | ✓ WIRED | Lines 166-170; result applied at lines 177-180 via `t_counts.get(str(s_id), 0)` |
| `engine.py:Step11` | `ledger.py:LedgerEntry.series_id` | `series_id=_ledger_series_id` in the success-path `LedgerEntry` call | ✓ WIRED | Lines 1106-1115; `_ledger_series_id` computed from `arr_series_id` which is set at line 781 from `eligible_item.media_item.series_id` |
| `ledger_sqla.py:translated_counts_for_series` | `bible/models.py:ProcessedFile` | `select(ProcessedFile.series_id, func.count()).where(ProcessedFile.series_id.in_(str_ids), ...)` | ✓ WIRED | Lines 207-217; SQL injection mitigated via SQLAlchemy parameterized `.in_()` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `library.py:get_series_episodes` | `bazarr_by_ep_id` | `BazarrClient.fetch_episode_inventory(series_id)` (async, live Bazarr) | Conditionally — depends on live Bazarr `seriesid[]` param; mocked in tests | ⚠ HOLLOW (see human verification below) |
| `library.py:get_library` series | `t_counts` | `translated_counts_for_series(session_factory, _s_ids)` GROUP BY DB query | Yes — real aggregate query against ProcessedFile; test with in-memory SQLite XPASSED | ✓ FLOWING |
| `library.py:get_library` movies | `vi_found` | Filesystem `.exists()` check for `.vi.srt`/`.vi.ass`/`.vi.vtt` sibling files | Yes — real filesystem check; correct for movies | ✓ FLOWING |

**Note on HOLLOW status for `bazarr_by_ep_id`:** The implementation is correct by inspection — `BazarrClient.fetch_episode_inventory` is called with `series_id` and its result is iterated. However, `library.py:302` has `# TODO(phase-16): verify seriesid[] vs seriesid against live Bazarr.` This is not a code defect but a known live-compatibility risk: if the Bazarr API at 192.168.5.42 requires `seriesid` (unbracketed) rather than `seriesid[]`, the call returns an empty list and all `subtitles[]` arrays will be empty even when Bazarr is online. This risk cannot be resolved in automated testing and is deferred to Phase 16.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 12 library API tests pass (4 existing + 8 Phase-13 stubs GREEN) | `uv run pytest tests/web/test_library_api.py tests/translate/test_engine.py -q` | `15 passed, 9 xpassed in 2.39s` (0 failed, 0 errors) | ✓ PASS |
| Full suite: no regressions introduced | `uv run pytest tests/ -q` | `364 passed, 1 skipped, 3 xfailed, 52 xpassed, 1 warning in 5.00s` | ✓ PASS |
| D-08 fail-soft: Bazarr disabled → HTTP 200, `errors==[]` | `test_get_series_episodes_bazarr_disabled` XPASSED | Assert `status_code==200`, `bazarr_available==False`, `errors==[]` passed | ✓ PASS |
| D-08 fail-soft: Bazarr error → HTTP 200, `errors[0]["source"]=="bazarr"` | `test_get_series_episodes_bazarr_error` XPASSED | Assert `status_code==200`, `errors[0]["source"]=="bazarr"` passed | ✓ PASS |
| D-02 join key: Bazarr inventory joins on `episode.id`, not `episodeFile.id` | `test_get_series_episodes_bazarr_join_key` XPASSED | ep_id=10 has subtitle, ep_id=11 has none (episodeFile.id=99 is not the join key) | ✓ PASS |
| D-07 normalization: `"Korean/English" → ["ko","en"]`; unknown → lowercased | `test_audio_language_normalization` XPASSED | Direct import of `_normalize_audio_languages`, assertion passed | ✓ PASS |
| D-06: engine success path records `series_id="42"` on `LedgerEntry` | `test_ledger_records_series_id_on_success` XPASSED | Full `translate_file` call with mocked LLM; `done_entries[0].series_id == "42"` passed | ✓ PASS |
| D-05: `translated_counts_for_series` returns `{"42": 2, "99": 1}` from in-memory DB | `test_translated_counts_for_series` XPASSED | Real SQLAlchemy async + aiosqlite in-memory test; GROUP BY query result verified | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files declared by this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| API-01 | 13-01-PLAN, 13-03-PLAN | `GET /api/library/series/{id}/episodes` returns season-grouped records with audio languages + Bazarr subtitles, fail-soft HTTP 200 | ✓ SATISFIED | `library.py:228-393` implements the full season-grouped envelope with Bazarr fail-soft; all 5 API-01 test stubs XPASSED |
| API-02 | 13-01-PLAN, 13-02-PLAN, 13-03-PLAN | Library Series + Movies list endpoints expose `translated_count` / `total_count` | ✓ SATISFIED | `library.py:164-180` (series), `library.py:215-216` (movies); `ledger_sqla.py:176-218` (bulk helper); D-06 engine fix at `engine.py:1106-1115` ensures future translations populate counts; all API-02 stubs XPASSED |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `library.py` | 302 | `TODO(phase-16): verify seriesid[] vs seriesid against live Bazarr` | ℹ Info | References a specific named phase; not an unresolved debt marker. The `TODO(phase-16)` form is a tracked deferral to Phase 16 (Docker Rebuild + Live Smoke Test), not an unreferenced FIXME. |

No TBD, FIXME, or XXX markers found in any phase-modified file.

### Human Verification Required

#### 1. Confirm Bazarr `seriesid[]` param returns subtitle inventory from live deployment

**Test:** With the Dockerized Trezarr daemon running against Bazarr at 192.168.5.42, call `GET /api/library/series/{id}/episodes` for a series known to have Bazarr-indexed subtitles. Check the response for `bazarr_available: true` and non-empty `subtitles[]` on at least one episode.

**Expected:** `bazarr_available: true` and at least one episode shows `subtitles: [{code2: "...", code3: "...", hi: false, forced: false}]`.

**Why human:** Tests mock Bazarr. The `TODO(phase-16)` comment at `library.py:302` documents a known risk: `BazarrClient.fetch_episode_inventory` currently uses `params=[("seriesid[]", series_id)]` (bracketed form). If the live Bazarr at 192.168.5.42 ignores the bracketed form and returns an empty list, all subtitle badges in the UI will be empty even when Bazarr is connected and `bazarr_available` shows `true`. This param format discrepancy is not detectable via automated tests and requires a live Bazarr response to resolve. If empty, the fix is to change `fetch_episode_inventory` to use `params={"seriesid": series_id}` (unbracketed).

### Gaps Summary

No gaps — all 4 ROADMAP Success Criteria are VERIFIED in the codebase. The single human verification item concerns a live-deployment risk (Bazarr query param format) that was explicitly deferred to Phase 16 and documented in code. It is not a code defect or missing implementation.

---

_Verified: 2026-06-04T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
