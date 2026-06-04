---
phase: 13
fixed_at: 2026-06-04T00:00:00Z
review_path: .planning/phases/13-backend-episodes-enrichment/13-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 13: Code Review Fix Report

**Fixed at:** 2026-06-04
**Source review:** .planning/phases/13-backend-episodes-enrichment/13-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### [HIGH] Blocking pyarr calls on the event loop in get_library

**Files modified:** `trezarr/web/routes/library.py`
**Commit:** 20bfc72
**Applied fix:** Added `import asyncio` (deferred, PLC0415 pattern) to `get_library`. Wrapped `client.series.get` and `client.movie.get` in `await asyncio.to_thread(...)`, exactly matching the pattern already used in `get_series_episodes` for its two pyarr calls. No other changes to call signatures.

---

### [MEDIUM] PyarrError str() leaks host/credentials into logs and error envelope (WR-01)

**Files modified:** `trezarr/web/routes/library.py`
**Commit:** 20bfc72
**Applied fix:** At every `except PyarrError` / `except (PyarrError, DiscoveryError, Exception)` boundary in `get_library` (Sonarr and Radarr catch blocks) and `get_series_episodes` (PyarrError and bare Exception catch blocks):

- Replaced `str(exc)` in log messages with `type(exc).__name__`
- Replaced `str(exc)` in JSON error fields with `f"{type(exc).__name__} at {display}"` where `display = _normalize_arr_host(settings.sonarr_host)` or `settings.radarr_host`
- Added `_normalize_arr_host` to the existing `from trezarr.arr import DiscoveryError` import in `get_library`
- Added a deferred `from trezarr.arr import _normalize_arr_host as _nh` inside the `except PyarrError` block in `get_series_episodes` (matches the PLC0415 deferred-import pattern)

The bare `Exception` catch in `get_series_episodes` uses only `type(exc).__name__` (no host context, since a non-pyarr exception may not involve the *arr host).

---

### [MEDIUM] Misleading comment about non-existent param fallback in Bazarr fetch

**Files modified:** `trezarr/web/routes/library.py`
**Commit:** 20bfc72
**Applied fix:** Corrected the comment block at the `fetch_episode_inventory` call (L299-302). Removed the false claim "fall back to `params={"seriesid": series_id}`" and replaced it with an explicit NOTE that no runtime fallback is implemented and that a silent empty result is the consequence if Bazarr requires plain `seriesid`. Retained the `TODO(phase-16)` marker. Did NOT implement a live fallback — risk of untested live behavior against 192.168.5.42 outweighs benefit before Phase 16 verification.

---

### [LOW] `_s_ids` derived from raw_series instead of series_list

**Files modified:** `trezarr/web/routes/library.py`
**Commit:** 20bfc72
**Applied fix:** Changed `_s_ids = [s.get("id") for s in raw_series if s.get("id") is not None]` to `_s_ids = [item.get("id") for item in series_list if item.get("id") is not None]`. Uses the authoritative `series_list` (already populated from `raw_series` in the loop above) as the single source for IDs, eliminating the parallel-structure tracking risk.

---

## Skipped Issues

None.

---

## Test results after fixes

```
364 passed, 1 skipped, 3 xfailed, 52 xpassed, 1 warning in 5.08s
```

Zero hard failures. Zero collection errors. The 1 skip and 3 xfailed are pre-existing and unrelated to these fixes. All 52 xpassed are expected (Phase 13 moved previously-xfail tests to green).

---

_Fixed: 2026-06-04_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
