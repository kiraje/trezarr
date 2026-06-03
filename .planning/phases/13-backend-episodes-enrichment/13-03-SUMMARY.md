---
phase: 13-backend-episodes-enrichment
plan: "03"
subsystem: web-api
tags: [api-01, api-02, library, episodes, bazarr, fail-soft, audio-normalization, wave-2]
dependency_graph:
  requires:
    - "13-01 (Wave-0 RED stubs)"
    - "13-02 (D-06 engine fix + D-05 bulk helper)"
  provides:
    - "Enriched get_series_episodes: season-grouped envelope, Bazarr fail-soft, audio normalization (API-01)"
    - "get_library with translated_count + total_count for series and movies (API-02)"
    - "_normalize_audio_languages helper in library.py"
  affects:
    - "trezarr/web/routes/library.py"
    - "tests/web/test_library_api.py"
tech_stack:
  added: []
  patterns:
    - "asyncio.to_thread + asyncio.gather for concurrent blocking pyarr calls (D-01)"
    - "Bazarr fail-soft: always HTTP 200, errors[] entry on BazarrError, bazarr_available flag (D-08)"
    - "episode.id join key for Bazarr inventory (not episodeFile.id) (D-02)"
    - "episode_key from authoritative Sonarr record ints (D-03)"
    - "D-07 audio normalization: _ORIG_LANG_NAME_TO_CODE2 deferred import inside helper"
    - "D-05 bulk translated_counts_for_series post-loop applied to series_list"
    - "D-04 total_count from statistics.episodeFileCount"
    - "Movie translated_count via filesystem vi-sidecar check"
key_files:
  created: []
  modified:
    - "trezarr/web/routes/library.py — _normalize_audio_languages helper; get_series_episodes full rewrite; get_library extended with translated_count/total_count"
    - "tests/web/test_library_api.py — Rule 1 fixes: BazarrSubtitle→SubtitleEntry; MagicMock→AsyncMock for fetch_episode_inventory"
decisions:
  - "asyncio.to_thread wraps all pyarr calls in get_series_episodes to fix latent event-loop block"
  - "Bazarr fail-soft asymmetry (D-08): disabled=no errors entry; enabled+BazarrError=errors entry; both=HTTP 200"
  - "D-02 join key: bazarr_by_ep_id keyed on episode.id (arr_id), not episodeFile.id"
  - "D-05 applied as post-loop pass over series_list to avoid two-pass collection complexity"
  - "Movie vi-sidecar check only runs when raw_path exists (consistent with source_sub_found path)"
  - "TODO(phase-16) comment: verify seriesid[] vs seriesid param against live Bazarr at 192.168.5.42"
metrics:
  duration: "5 min"
  completed: "2026-06-03T18:11:12Z"
  tasks: 2
  files: 2
---

# Phase 13 Plan 03: Wave-2 Implementation Summary

**One-liner:** Enriched GET /api/library/series/{id}/episodes returns season-grouped envelope with Bazarr fail-soft (always 200), audio language normalization, and correct episode.id join; GET /api/library series/movies items carry translated_count and total_count from D-05 bulk query and episodeFileCount.

## What Was Built

**Task 1: Rewrite get_series_episodes (API-01)**

Added `_normalize_audio_languages(raw)` module-level helper:
- Handles str (slash-joined) and list input
- Dedupes preserving order
- Maps via `_ORIG_LANG_NAME_TO_CODE2` (deferred import from rank.py, D-07)
- Unknown names fall back to lowercased original

Rewrote `get_series_episodes` body:
- `asyncio.to_thread(client.episode.get, ...)` and `asyncio.to_thread(client.episode_file.get, ...)` inside `asyncio.gather` — fixes latent sync-in-async event-loop block (D-01)
- Pyarr single-dict normalization for both results (Pitfall 2)
- `ep_file_by_id` dict keyed on `episodeFile.id` for lookup
- Bazarr fail-soft block: `BazarrClient.from_settings` + `await fetch_episode_inventory`; `BazarrError` caught → `errors.append({source: "bazarr"})` + `bazarr_available` stays False; disabled path → no error entry (D-08)
- `bazarr_by_ep_id` keyed on `item.arr_id` (episode.id / sonarrEpisodeId — D-02)
- Season grouping via `defaultdict(list)` keyed on `seasonNumber`
- `episode_key = f"S{season_number:02d}E{episode_number:02d}"` from record ints (D-03)
- Status from vi-sidecar filesystem check (unchanged pattern)
- Subtitle badges: `{code2, code3, hi, forced}` only — no path field (T-13-01 mitigation)
- `_episode_key_from_file` retained in file for reference (not called from new handler)

Response envelope:
```json
{
  "series_id": 1,
  "bazarr_available": true,
  "seasons": [{"season_number": 1, "episodes": [{...}]}],
  "errors": []
}
```

**Task 2: Extend get_library with counts (API-02)**

Series items:
- `raw_series_stats` dict accumulates `episodeFileCount` during the loop (D-04)
- Post-loop: `translated_counts_for_series(session_factory, _s_ids)` one aggregate query (D-05)
- Post-loop pass applies `translated_count` and `total_count` to each `series_list` item

Movie items:
- `vi_found` filesystem check added in the `if raw_path:` branch
- `translated_count: 1 if vi_found else 0`
- `total_count: 1 if m.get("hasFile", False) else 0`

## Verification Results

```
uv run pytest tests/web/test_library_api.py -v
4 passed, 8 xpassed in 0.28s
```

All 12 tests GREEN (4 original passes + 8 xpassed from Wave-0 stubs). Zero xfailed.

```
uv run pytest tests/ -q
364 passed, 1 skipped, 3 xfailed, 52 xpassed, 1 warning in 5.00s
```

Zero hard failures. Full suite green. (3 remaining xfailed are from other phases.)

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1+2: get_series_episodes rewrite + get_library counts + test fixes | 3c41ed0 | trezarr/web/routes/library.py, tests/web/test_library_api.py |

Note: Both tasks were implemented in a single atomic commit as they both touch `trezarr/web/routes/library.py` and the implementation was done as a complete file rewrite.

## Deviations from Plan

### Auto-fixed Issues (Rule 1 — Bugs in Wave-0 Test Stubs)

**1. [Rule 1 - Bug] test_get_series_episodes_bazarr_join_key: BazarrSubtitle does not exist**
- **Found during:** Task 1 verification
- **Issue:** Test imported `BazarrSubtitle` from `trezarr.arr.bazarr` — this class does not exist. The correct class is `SubtitleEntry`.
- **Fix:** Changed import to `SubtitleEntry`; also added the required `path=""` positional arg to `SubtitleEntry(...)` which requires `path` as a field.
- **Files modified:** tests/web/test_library_api.py
- **Commit:** 3c41ed0

**2. [Rule 1 - Bug] test_get_series_episodes_bazarr_join_key: fetch_episode_inventory not AsyncMock**
- **Found during:** Task 1 verification (same run, after fix 1)
- **Issue:** `mock_bazarr.fetch_episode_inventory.return_value = bazarr_inventory` creates a sync `MagicMock`. The production code `await bazarr_client.fetch_episode_inventory(series_id)` raises `TypeError: object list can't be used in 'await' expression`.
- **Fix:** Changed to `mock_bazarr.fetch_episode_inventory = AsyncMock(return_value=bazarr_inventory)`.
- **Files modified:** tests/web/test_library_api.py
- **Commit:** 3c41ed0

## Known Stubs

None — all stubs are now implemented. The 3 remaining xfailed tests in the full suite are from other phases (not library API).

## Threat Flags

No new threat surface introduced beyond what the plan's `<threat_model>` accounts for:
- T-13-01 mitigated: subtitle badges strip path field (only code2/code3/hi/forced returned)
- T-13-02 mitigated: SQLAlchemy parameterized IN query in translated_counts_for_series (from Wave-1)
- T-13-03 accepted: BazarrError messages already redacted by _normalize_arr_host (T-10-02)
- T-13-04 accepted: FastAPI validates series_id as int (422 before handler runs)

## Self-Check: PASSED

- [x] `trezarr/web/routes/library.py` has `_normalize_audio_languages`, rewritten `get_series_episodes`, extended `get_library`
- [x] `tests/web/test_library_api.py` has Rule 1 fixes (SubtitleEntry, AsyncMock)
- [x] Commit 3c41ed0 exists in git log
- [x] All 12 test_library_api.py tests GREEN
- [x] Full suite: 364 passed, 0 failed
