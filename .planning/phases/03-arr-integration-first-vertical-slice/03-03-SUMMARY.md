---
phase: "03"
plan: "03"
subsystem: "arr discovery (pyarr 6.x integration)"
tags: [wave-2, tdd-green, pyarr, sonarr, radarr, discovery, INTG-01, D-22, D-23, D-30]
dependency_graph:
  requires:
    - "03-01"                        # Wave-0 RED stubs for tests/arr/test_arr_discovery.py
    - "03-02"                        # apply_path_mapping + TrezarrSettings sonarr_*/radarr_* fields
    - "trezarr/paths.py"             # apply_path_mapping consumed by both discovery modules
    - "trezarr/config.py"            # sonarr/radarr SecretStr + host/port/enabled fields
  provides:
    - "trezarr/arr/__init__.py"      # DiscoveryError class + _normalize_arr_host helper
    - "trezarr/arr/sonarr.py"        # MediaItem, build_sonarr_client, discover_sonarr_items
    - "trezarr/arr/radarr.py"        # build_radarr_client, discover_radarr_items
  affects:
    - "03-04 (scan + gap detection) — consumes the MediaItem list from discover_*_items"
    - "03-05 (CLI orchestration) — catches DiscoveryError per-service for D-30 resilience"
tech_stack:
  added: []   # pyarr 6.6.x was added in 03-01; no new deps in this plan
  patterns:
    - "pyarr 6.x composition API: `from pyarr import Sonarr, Radarr` (NOT SonarrAPI/RadarrAPI)"
    - "Catch `pyarr.exceptions.PyarrError` (parent class) — pyarr abstracts httpx errors into its own hierarchy"
    - "Pass `api_ver='v3'` explicitly to skip pyarr's `GET /api` auto-detect probe (testability + stability)"
    - "SecretStr.get_secret_value() resolved only inside build_*_client() — never stored on MediaItem"
    - "DiscoveryError as the typed boundary between pyarr internals and cli.py per-service resilience"
    - "Defensive dict→list normalisation: pyarr submodules can return a single dict for one-record responses"
key_files:
  created:
    - trezarr/arr/__init__.py
    - trezarr/arr/sonarr.py
    - trezarr/arr/radarr.py
    - .planning/phases/03-arr-integration-first-vertical-slice/03-03-SUMMARY.md
  modified:
    - tests/arr/test_arr_discovery.py   # all 8 xfail markers removed (HIGH #3 policy)
decisions:
  - "Catch `pyarr.exceptions.PyarrError` (parent of all pyarr exceptions) instead of `httpx.HTTPStatusError` + `httpx.RequestError` as the plan originally specified. pyarr wraps 4xx/5xx into PyarrUnauthorizedError/PyarrServerError/etc. and httpx transport errors into PyarrConnectionError — raw httpx exceptions never escape pyarr's request layer. Catching PyarrError gives the broadest typed boundary; the public DiscoveryError contract is unchanged."
  - "Pass `api_ver='v3'` explicitly to both Sonarr() and Radarr() constructors to skip pyarr's auto-detect `GET /api` round trip. The test stubs (and the typical operator-mocked test) only mock the typed endpoints (/api/v3/series, /api/v3/episodefile, /api/v3/movie). Without `api_ver='v3'`, pyarr would issue a probe to /api that the test fixture has no response for — failing the test with assert_all_requests_were_expected. Sonarr/Radarr v3 is the stable, supported API in the deployment window (per CLAUDE.md + 03-CONTEXT.md D-22)."
  - "MediaItem dataclass is defined ONCE in trezarr/arr/sonarr.py and re-imported by trezarr/arr/radarr.py. Per 03-REVIEWS.md LOW #17 the field is `title` (not `series_title`) so it carries both episode and movie titles cleanly."
  - "Defensive dict→list normalisation on pyarr submodule responses: `episode_file.get(series_id=X)` and `movie.get()` typed annotations are `JsonArray | JsonObject`, so single-record cases may return a bare dict. Both discovery functions normalise to a list before iterating."
  - "Open Question 1 resolved by the planner: Radarr's `movie.get()` typically embeds `movieFile` inline, but if it is None/absent we fall back to `client.movie_file.get(movie_id=...)`; if THAT is also empty we log a warning and skip the movie. The implementation honours all three branches."
metrics:
  duration: "~20 min"
  completed: "2026-06-01"
  tasks_completed: 2
  files_created: 4
  files_modified: 1
---

# Phase 03 Plan 03: Wave 2 — *arr Discovery Layer Summary

**The pyarr 6.x discovery wrappers for Sonarr and Radarr are in place — `discover_sonarr_items()` and `discover_radarr_items()` return path-mapped `MediaItem` lists, gated by `*_enabled` settings, and bound by a typed `DiscoveryError` boundary so cli.py can implement per-service resilience.**

Three new modules ship under `trezarr/arr/`. The package init carries the
shared `DiscoveryError` exception type (per 03-REVIEWS.md MEDIUM #10) plus a
`_normalize_arr_host()` helper that lets users paste either bare IPs or full
URLs into `sonarr_host` / `radarr_host` (per MEDIUM #15). `sonarr.py` defines
the shared `MediaItem` dataclass (with `title` not `series_title` — LOW #17)
and discovers monitored episodes via `client.series.get()` →
`client.episode_file.get(series_id=...)`. `radarr.py` discovers monitored
movies via `client.movie.get()` and extracts the video path from
`movie["movieFile"]["path"]` — **never** from `movie["path"]`, which is the
movie directory (Pitfall 2).

All 8 stubs in `tests/arr/test_arr_discovery.py` are GREEN; xfail markers are
removed; the full project suite holds at 93 passed (up from 85 in Wave 1).

## What Was Built

### Task 1: `trezarr/arr/__init__.py` + `trezarr/arr/sonarr.py`

| Component | Purpose | Notes |
|-----------|---------|-------|
| `DiscoveryError` (in `__init__.py`) | Typed exception wrapping pyarr/httpx failures | Per 03-REVIEWS.md MEDIUM #10. cli.py (Plan 03-05) catches this per-service so one *arr failure doesn't crash the run. |
| `_normalize_arr_host(host)` (in `__init__.py`) | Accept bare IP OR full URL; return bare host | Per MEDIUM #15. Uses `urllib.parse.urlparse` when scheme present; pass-through otherwise. Pyarr expects bare host + separate port kwarg. |
| `MediaItem` dataclass (in `sonarr.py`) | Resolved local_path + title + source_type + series_id + season_number | Per LOW #17: `title` (not `series_title`) — used for both episodes AND movies. |
| `build_sonarr_client(settings)` | Constructs `pyarr.Sonarr(host, api_key, port, tls=False, api_ver="v3")` | `SecretStr.get_secret_value()` called ONLY here. `tls=False` for Phase 3 HTTP; HTTPS deferred to Phase 7. `api_ver="v3"` skips pyarr's auto-detect probe. |
| `discover_sonarr_items(settings)` | Returns `list[MediaItem]` for all monitored episodes | Iterates monitored series, fetches episode files per series, applies `apply_path_mapping` to every path. Phase-7-comment notes asyncio.gather is the next optimisation. |

### Task 2: `trezarr/arr/radarr.py`

| Component | Purpose | Notes |
|-----------|---------|-------|
| `build_radarr_client(settings)` | Constructs `pyarr.Radarr(host, api_key, port, tls=False, api_ver="v3")` | Same SecretStr discipline as Sonarr. Default port 7878. |
| `discover_radarr_items(settings)` | Returns `list[MediaItem]` for all monitored movies WITH a video file | Pitfall 2 honoured: uses `movie["movieFile"]["path"]` (the VIDEO), never `movie["path"]` (the DIRECTORY). Open Question 1 fallback: if inline `movie["movieFile"]` is None, calls `client.movie_file.get(movie_id=...)`; if still None, logs warning + skips. |

`MediaItem` is imported from `trezarr.arr.sonarr` — defined once, used twice.

### xfail removal (HIGH #3 policy)

All 8 markers removed:

| Test | Test file | Wave it became GREEN |
|------|-----------|----------------------|
| `test_sonarr_discovers_monitored_series` | tests/arr/test_arr_discovery.py | Task 1 |
| `test_sonarr_filters_unmonitored` | tests/arr/test_arr_discovery.py | Task 1 |
| `test_normalize_arr_host_bare_ip` | tests/arr/test_arr_discovery.py | Task 1 |
| `test_normalize_arr_host_full_url_with_scheme` | tests/arr/test_arr_discovery.py | Task 1 |
| `test_normalize_arr_host_full_url_with_port` | tests/arr/test_arr_discovery.py | Task 1 |
| `test_discovery_error_raised_on_http_error` | tests/arr/test_arr_discovery.py | Task 1 |
| `test_radarr_discovers_movies` | tests/arr/test_arr_discovery.py | Task 2 |
| `test_radarr_skips_missing_file` | tests/arr/test_arr_discovery.py | Task 2 |

The test file module docstring was updated to reflect the new GREEN-stub status.

## Verification Results

```
$ uv run pytest tests/arr/test_arr_discovery.py -x -q
........                                                                 [100%]
8 passed in 0.10s

$ uv run pytest tests/ -q
93 passed, 18 skipped, 3 xfailed in 2.67s
EXIT=0
```

Test counts:

| Run | After 03-02 | After 03-03 | Delta |
|-----|-------------|-------------|-------|
| `tests/arr/` (passed) | 0 (all 8 stubs SKIP via importorskip) | 8 | +8 |
| Full suite (passed) | 85 | 93 | +8 |
| Full suite (xfailed) | 3 | 3 | 0 (unchanged — remaining 3 are Plan 03-04 apply_permissions) |
| Full suite (skipped) | 26 | 18 | -8 (8 arr stubs went SKIP → PASS) |

Ruff: `uv run ruff check trezarr/arr/sonarr.py trezarr/arr/__init__.py trezarr/arr/radarr.py` → All checks passed.

Plan `<verification>` block:

```
$ grep -c "DiscoveryError" trezarr/arr/__init__.py
4    (>= 1 — class definition + docstring mentions)

$ grep -c "_normalize_arr_host" trezarr/arr/__init__.py
4    (>= 1 — function definition + docstring mentions)

$ grep -c "get_secret_value" trezarr/arr/sonarr.py
2    (>= 1 — used once in build_sonarr_client; mentioned in module docstring)

$ grep -c "get_secret_value" trezarr/arr/radarr.py
2    (>= 1 — used once in build_radarr_client; mentioned in module docstring)

$ grep "movie\[.path.\]" trezarr/arr/radarr.py
(only matches are inside comments/docstrings explaining the Pitfall-2 ban;
 zero actual code paths use movie["path"] as the video file path)

$ grep "@pytest.mark.xfail" tests/arr/test_arr_discovery.py
(no matches — exit 1)
```

The plan also called for `grep -c "raise DiscoveryError" trezarr/arr/*.py` returning `>= 2` (one for HTTPStatusError, one for RequestError). Implementation returns `1` per file because we catch the broader `PyarrError` parent — see Deviations.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: Sonarr discovery + DiscoveryError + _normalize_arr_host | `510c2f1` | `trezarr/arr/__init__.py`, `trezarr/arr/sonarr.py`, `tests/arr/test_arr_discovery.py` (6 Sonarr-side xfail removed) |
| Task 2: Radarr discovery | `c4bd2eb` | `trezarr/arr/radarr.py`, `tests/arr/test_arr_discovery.py` (2 Radarr-side xfail removed + docstring update) |

## Deviations from Plan

### `[Rule 3 — Blocking issue]` Catch `pyarr.exceptions.PyarrError` instead of raw `httpx.HTTPStatusError` / `httpx.RequestError`

- **Found during:** Task 1 (Sonarr discovery implementation, while reading pyarr's source to verify the test fixture URL shape).
- **Issue:** The plan `<action>` block prescribes catching `httpx.HTTPStatusError` AND `httpx.RequestError` and re-raising as `DiscoveryError`. But pyarr 6.x's `RequestHandler` in `pyarr/_sync/utils/http.py` **catches both itself**: `httpx.RequestError` → `PyarrConnectionError`, `httpx.TimeoutException` → `PyarrConnectionError`, and 4xx/5xx responses dispatch to `_handle_error()` which raises `PyarrUnauthorizedError` / `PyarrServerError` / `PyarrResourceNotFound` / etc. Raw httpx exceptions never escape pyarr's request layer. If the implementation literally caught httpx exceptions, `test_discovery_error_raised_on_http_error` would fail — a 401 raises `PyarrUnauthorizedError`, NOT `httpx.HTTPStatusError`.
- **Fix:** Both `discover_sonarr_items` and `discover_radarr_items` catch the `pyarr.exceptions.PyarrError` parent class (which all pyarr-specific exceptions inherit from) and re-raise as `DiscoveryError` with host:port and exception-class-name context. The public DiscoveryError contract is unchanged; only the internal catch type is corrected.
- **Files modified:** `trezarr/arr/sonarr.py`, `trezarr/arr/radarr.py`
- **Verification:** `test_discovery_error_raised_on_http_error` passes (raises DiscoveryError on 401). All 8 arr tests green.
- **Committed in:** `510c2f1` (Sonarr), `c4bd2eb` (Radarr).
- **Why Rule 3, not Rule 4:** the planner already specified the typed-boundary architecture (DiscoveryError, host/port context, log + raise). Only the catch-type detail was empirically wrong against pyarr 6.x. This is a blocking implementation-detail fix that preserves the planner's architectural intent.

### `[Rule 3 — Blocking issue]` Pass `api_ver="v3"` to both Sonarr() and Radarr() to skip pyarr's auto-detect probe

- **Found during:** Task 1 (Sonarr discovery, while validating test fixture URLs).
- **Issue:** When `api_ver` is omitted, pyarr's `RequestHandler.request()` lazily calls `_get_api_version()` on first use, which fires `GET /api` to autodiscover the version (`api/v3`, `api/v1`, etc.). The Wave-0 test stubs (and any well-written mocked test) only mock the typed endpoints (`/api/v3/series`, `/api/v3/movie`, `/api/v3/episodefile?seriesId=...`). With `assert_all_requests_were_expected=True` (the pytest-httpx default), the unmocked `GET /api` probe would fail every test before it reached the actual endpoint.
- **Fix:** Both `build_sonarr_client` and `build_radarr_client` pass `api_ver="v3"` explicitly to the pyarr constructor. Sonarr v3 and Radarr v3 are the stable, supported API versions in the deployment window (per `CLAUDE.md` "pyarr 6.6.x, X-Api-Key, /api/v3" and 03-CONTEXT.md D-22).
- **Files modified:** `trezarr/arr/sonarr.py`, `trezarr/arr/radarr.py`
- **Verification:** All 8 arr tests green; production behaviour unaffected (real Sonarr/Radarr also expose `/api/v3`).
- **Committed in:** `510c2f1` (Sonarr), `c4bd2eb` (Radarr).

### `[Rule 3 — Blocking issue]` Update test file module docstring after xfail removal

- **Found during:** Task 2 (final xfail-marker grep verification).
- **Issue:** The plan `<verify>` block uses `! grep -E "xfail" tests/arr/test_arr_discovery.py`. After removing all 8 markers, the file still contained the substring `xfail` in its module docstring (the old "Stubs are marked @pytest.mark.xfail(strict=False)" line), which would fail the negated grep.
- **Fix:** Updated the module docstring to describe the post-implementation state (stubs are GREEN; markers have been removed). The actual `@pytest.mark.xfail` decorators are gone.
- **Files modified:** `tests/arr/test_arr_discovery.py`
- **Verification:** `grep -n "@pytest.mark.xfail" tests/arr/test_arr_discovery.py` → no matches; full suite stays green.
- **Committed in:** `c4bd2eb` (Task 2 commit).

### Defensive dict→list normalisation on pyarr responses

Not strictly a deviation — added under the spirit of Rule 2 (missing critical / defensive programming). Both `discover_sonarr_items` and `discover_radarr_items` normalise the pyarr response to a list before iterating, because pyarr's submodule type hints are `JsonArray | JsonObject` (single-record responses come back as a bare dict). The Wave-0 test fixtures all return lists, so this didn't surface in the test suite, but it would crash production runs against a real *arr that returns one record. Captured as a documented pattern in the module docstrings.

### No other deviations

- No architectural changes (Rule 4 not invoked).
- No auth gates encountered.
- No deferred items.
- All HIGH/MEDIUM/LOW concerns from 03-REVIEWS.md affecting this plan are addressed:
  - LOW #17 (rename `series_title` → `title`): implemented in MediaItem dataclass.
  - MEDIUM #10 (typed `DiscoveryError`): implemented in `trezarr/arr/__init__.py` + caught around all pyarr calls.
  - MEDIUM #15 (host normalisation): implemented in `_normalize_arr_host()`, called in both `build_*_client()` functions.
  - HIGH #3 (xfail removal policy): all 8 markers in `tests/arr/test_arr_discovery.py` removed.

## Issues Encountered

None — the implementation flowed cleanly once the pyarr exception hierarchy and
api-version probe were understood (both captured in 03-RESEARCH.md A5 + the
plan's Open Questions, then empirically confirmed by reading pyarr 6.6.0
source).

## Threat Flags

None. The plan's `<threat_model>` (T-03-03-01 through T-03-03-04) is fully satisfied:

- T-03-03-01 (API key disclosure): `SecretStr.get_secret_value()` is called only inside `build_*_client()`. No MediaItem field carries it. No logger call dumps `settings`.
- T-03-03-02 (path injection via API): every API-returned path passes through `apply_path_mapping` before becoming a `MediaItem.local_path`. The Pitfall-2 movie["path"] vs movie["movieFile"]["path"] guard is enforced. `assert_within_media_roots` runs at write time in Plan 03-04 (already shipped in 03-02 paths.py) — the discovery layer hands off path-mapped paths only.
- T-03-03-03 (write-call elevation): the discovery layer is strictly READ-ONLY against Sonarr/Radarr. No write endpoints are touched.
- T-03-03-04 (DoS via one *arr failure): `DiscoveryError` is the typed boundary; cli.py (Plan 03-05) will catch per-service so one bad *arr does not crash the run.

No new network endpoints (Trezarr only consumes), no new auth paths (X-Api-Key only, via pyarr), no schema changes (MediaItem is a transient dataclass, not persisted).

## Known Stubs

None. All Wave-2 deliverables ship as functional code; nothing is mocked or
placeholdered. The 3 remaining xfails in the full suite are
`tests/output/test_write.py` apply_permissions stubs — those are Plan 03-04's
responsibility (Wave 3) and correctly remain xfailed at this gate.

## Next Plan Readiness

Plan 03-04 (Wave 3: scan + gap + permissions) can now consume:

- `MediaItem` dataclass (from `trezarr.arr.sonarr` or re-export) — the unit
  of work for the scan layer.
- `discover_sonarr_items(settings)` and `discover_radarr_items(settings)` —
  the API-driven discovery entry points; cli.py will call both and concat.
- `DiscoveryError` — the typed boundary cli.py catches per-service.

Plan 03-05 (Wave 4: CLI orchestration) can implement the D-30 per-service
resilience pattern around the discover calls by catching `DiscoveryError` per
*arr and accumulating an `int` exit code (per HIGH #6).

## Self-Check: PASSED

Files exist check:
- `trezarr/arr/__init__.py`: FOUND
- `trezarr/arr/sonarr.py`: FOUND
- `trezarr/arr/radarr.py`: FOUND

Commits exist check:
- `510c2f1` (Task 1 — Sonarr + DiscoveryError + _normalize_arr_host): FOUND
- `c4bd2eb` (Task 2 — Radarr): FOUND

Test suite check:
- `tests/arr/test_arr_discovery.py` → 8 passed, exit 0
- Full suite → 93 passed, 18 skipped, 3 xfailed, exit 0
- No xfail markers remaining on this plan's tests
- No regressions on Phase-1/Phase-2/03-02 tests

Plan success criteria coverage:
- [x] `trezarr/arr/__init__.py` contains `DiscoveryError` class and `_normalize_arr_host` helper
- [x] `trezarr/arr/sonarr.py` exports `build_sonarr_client`, `discover_sonarr_items`, `MediaItem`
- [x] `trezarr/arr/radarr.py` exports `build_radarr_client`, `discover_radarr_items`; imports `MediaItem` from sonarr
- [x] `from pyarr import Sonarr, Radarr` (NOT SonarrAPI / RadarrAPI)
- [x] `SecretStr.get_secret_value()` resolved ONLY inside `build_*_client()`
- [x] `apply_path_mapping` called on every raw API path before storing in `MediaItem`
- [x] `_normalize_arr_host` called on both `sonarr_host` and `radarr_host` inside `build_*_client()`
- [x] `sonarr_enabled=False` and `radarr_enabled=False` both return `[]` immediately with no client constructed
- [x] Discovery wraps pyarr/httpx errors → re-raises as `DiscoveryError` with host/port context
- [x] `MediaItem.title` (NOT `series_title`)
- [x] All `tests/arr/` stubs GREEN; xfail markers removed
- [x] Full suite green (no regressions)
- [x] All LOW #17 / MEDIUM #10 / MEDIUM #15 / HIGH #3 concerns from 03-REVIEWS.md addressed

Wave 2 (*arr discovery layer) complete.
