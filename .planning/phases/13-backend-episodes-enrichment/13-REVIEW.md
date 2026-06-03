---
status: issues_found
reviewer: arr-integration-specialist
commits: 3c41ed0 3f204e0 86eb616
date: 2026-06-04
---

# Phase 13 *arr Integration Review

Scope: `trezarr/web/routes/library.py`, `trezarr/translate/engine.py`,
`trezarr/output/ledger_sqla.py` — commits 3c41ed0, 3f204e0, 86eb616.

---

## Findings

---

### [HIGH] Blocking pyarr calls on the event loop in get_library (Sonarr + Radarr)

- File/Line: `trezarr/web/routes/library.py:140`, `trezarr/web/routes/library.py:186`
- Invariant: Blocking-I/O off event loop (D-03 / INTG event-loop discipline)
- Evidence:
  ```python
  raw_series = client.series.get()          # L140 — blocks
  raw_movies = client.movie.get()           # L186 — blocks
  ```
  `get_series_episodes` wraps its two pyarr calls in `asyncio.to_thread` + `asyncio.gather` (L268-270), correctly. `get_library` makes the same class of blocking pyarr call (`client.series.get()` and `client.movie.get()`) directly on the event loop without `asyncio.to_thread`. These are synchronous HTTP calls (pyarr uses `requests` underneath) that will block the FastAPI event loop for the full network round-trip.
- Impact: During a library-list request against a slow or busy Sonarr/Radarr instance, the entire FastAPI event loop is frozen — no other request (translation job status, health checks, etc.) can be served.
- Fix: Wrap both calls in `asyncio.to_thread` the same way `get_series_episodes` does:
  ```python
  raw_series = await asyncio.to_thread(client.series.get)
  raw_movies = await asyncio.to_thread(client.movie.get)
  ```
  `asyncio` must be imported at the top of the route body (already imported inside `get_series_episodes` via deferred import — add the same deferred import to `get_library`).
- Confidence: high

---

### [MEDIUM] PyarrError str() in logs and error envelope is not host-normalized (WR-01)

- File/Line: `trezarr/web/routes/library.py:159,162,219,221,282,283,285,286`
- Invariant: WR-01 — credential redaction; host in log/error must pass through `_normalize_arr_host()`
- Evidence:
  ```python
  # L159
  logger.warning("get_library: Sonarr error — %s", exc)
  # L162
  errors.append({"source": "sonarr", "error": str(exc)})
  # L282
  logger.error("get_series_episodes: Sonarr error for series_id=%d — %s", series_id, exc)
  # L283
  return JSONResponse({"error": str(exc)}, status_code=502)
  ```
  Confirmed with `uv run python3`: `str(PyarrConnectionError("connection refused to 192.168.5.42:8989"))` → `"connection refused to 192.168.5.42:8989"`. The raw host IP and port are embedded verbatim in `PyarrError` messages by pyarr itself, not by this code. The `DiscoveryError`-wrapping pattern in `discover_sonarr_items` normalizes via `_normalize_arr_host` before raising; but `get_library` and `get_series_episodes` call `build_sonarr_client`/`build_radarr_client` and the raw pyarr client directly — a `PyarrConnectionError` from a DNS-failing or TLS-failing call will include whatever host:port pyarr has, un-normalized, in `str(exc)`. If the operator embeds credentials in the host field (e.g. `user:pass@192.168.5.42`), `str(exc)` in the log and JSON response body will leak them. The `BazarrError` path is correctly redacted because `BazarrClient` builds its own normalized message before raising (L300/L312/L316 in `bazarr.py`).
- Impact: Credentials leaked to application logs and/or to the browser via the JSON `errors[]` field on any connection/authentication failure against Sonarr or Radarr.
- Fix: At the catch boundary, extract a display host before logging or forwarding:
  ```python
  from trezarr.arr import _normalize_arr_host  # already available
  display = _normalize_arr_host(settings.sonarr_host)
  logger.warning("get_library: Sonarr error at %s — %s", display, type(exc).__name__)
  errors.append({"source": "sonarr", "error": f"{type(exc).__name__} at {display}"})
  ```
  Do not pass `str(exc)` to the log formatter or the JSON response when the error originates from a pyarr call — use `type(exc).__name__` + normalized host only.
- Confidence: high

---

### [MEDIUM] Bazarr param-format hazard: `seriesid[]` is unverified against live instance; TODO present but incomplete

- File/Line: `trezarr/web/routes/library.py:299-302`, `trezarr/arr/bazarr.py:305`
- Invariant: Bazarr param-format hazard (review scope item 2)
- Evidence:
  ```python
  # bazarr.py L305
  params=[("seriesid[]", sonarr_series_id)],
  ```
  ```python
  # library.py L299-302
  # fetch_episode_inventory uses params=[("seriesid[]", id)] list form.
  # If this returns empty on live Bazarr at 192.168.5.42, fall back to
  # params={"seriesid": series_id} — ARCHITECTURE.md §8 known risk.
  # TODO(phase-16): verify seriesid[] vs seriesid against live Bazarr.
  ```
  The TODO marker is present, satisfying the "clear phase-16 verification TODO" requirement. However, the comment in `library.py` says "fall back to `params={"seriesid": series_id}`" — but there is no such fallback in the code. The fallback is described but not implemented. `fetch_episode_inventory` does not attempt a retry with alternate param format on empty result. This means the live deployment at 192.168.5.42 will silently return `bazarr_by_ep_id = {}` for every episode if Bazarr expects `seriesid` (plain) rather than `seriesid[]` (array form), and the caller will see `subtitles=[]` on all episodes with no error. `bazarr_available` will be set to `True` (HTTP 200 from Bazarr), giving the UI a false signal.
- Impact: Silent subtitle inventory miss — no error surfaced, `bazarr_available=True` but all episodes show `subtitles=[]`. The comment creates a false impression that a runtime fallback exists. This is exploitable only by misconfiguration, not an attacker.
- Fix: Either implement the param fallback (retry with `{"seriesid": id}` when result is empty), or tighten the TODO comment to be explicit that no fallback currently exists and that empty-result is indistinguishable from "no subtitles". A positive-result cross-check during Phase 16 testing is needed before this endpoint is considered production-verified.
- Confidence: high

---

### [LOW] `_s_ids` built from `raw_series` not `series_list` — redundant source but not a bug

- File/Line: `trezarr/web/routes/library.py:169`
- Invariant: N/A (code clarity)
- Evidence:
  ```python
  if series_list:
      ...
      _s_ids = [s.get("id") for s in raw_series if s.get("id") is not None]
      t_counts = await translated_counts_for_series(session_factory, _s_ids)
  ```
  `series_list` is populated from `raw_series` in the same loop; if `series_list` is non-empty, `raw_series` is guaranteed non-empty and contains the same series records. The IDs from `series_list` would be equivalent. Building `_s_ids` from `raw_series` instead of `series_list` is not incorrect — the IDs are identical — but it requires a reader to mentally track two parallel structures. If `series_list` is ever pre-populated from a different source in a future refactor, the two sources would silently diverge.
- Impact: None currently; reader confusion and future divergence risk.
- Fix: Derive `_s_ids` from `series_list` to use a single authoritative source:
  ```python
  _s_ids = [item.get("id") for item in series_list if item.get("id") is not None]
  ```
- Confidence: high

---

## Domain-correct items (no issues)

**Bazarr fail-soft (D-08):** `get_series_episodes` returns HTTP 200 in all Bazarr failure paths. `BazarrError` is caught specifically (L319), `bazarr_available` stays `False`, and the error is appended to `errors[]`. Bazarr disabled → silent `bazarr_available=False` with no error entry. The Sonarr failure path correctly returns 502 (Sonarr data is not optional for the episodes view). Confirmed.

**Bazarr error credential redaction:** `BazarrClient` raises `BazarrError` with a message that uses `_normalize_arr_host(self._host)` exclusively (L176, L192, L217, L300) — API key is never included. The `get_series_episodes` catch at L319 passes `str(exc)` to the log and `errors[]`, which is safe because `BazarrError` messages are already sanitized at the source.

**pyarr error wrapping:** The Sonarr block in `get_series_episodes` catches `PyarrError` specifically before the bare `Exception` fallback (L281 before L284). `get_library` catches `(PyarrError, DiscoveryError, Exception)` — redundant (Exception swallows the others) but functionally equivalent and not a bug for this read-only library route.

**asyncio.to_thread in get_series_episodes:** Both `client.episode.get` and `client.episode_file.get` are dispatched via `asyncio.to_thread` and awaited via `asyncio.gather` (L268-270). Correct.

**Join-key correctness (D-02):** The lookup map is `ep_file_by_id: dict[int, dict] = {ef["id"]: ef for ef in ep_files_raw}` (L279) — keyed on `episodeFile.id`. The join at L333 uses `ep_file_by_id.get(ep_file_id)` where `ep_file_id = ep.get("episodeFileId")` (L329) — the episode record's reference to its file, not the episode's own ID. Bazarr join at L370 uses `ep_id` (episode.id == sonarrEpisodeId). Both joins are correct per D-02.

**SQL safety (T-13-02):** `translated_counts_for_series` uses `ProcessedFile.series_id.in_(str_ids)` — SQLAlchemy parameterized IN clause. No raw SQL interpolation. Confirmed.

**Radarr uses video-file path (Pitfall 2):** `movie_file.get("path", "")` at L192 reads from `m.get("movieFile")`, the embedded file record — not the movie directory. Correct.

**D-06 series_id on LedgerEntry:** `arr_series_id` is extracted outside the `session_factory` guard (engine.py, post-diff L775-783) and assigned as `_ledger_series_id = str(arr_series_id) if eligible_item is not None and arr_series_id else None` at the Step 11 `ledger.record()` call. Correct; test xPASSes.

**translated_counts_for_series early return:** Empty `series_ids` → `{}` immediately (L in ledger_sqla.py), avoiding a degenerate `IN ()` clause that would be a SQL syntax error on some backends. Correct.

---

## Test results

```
tests/arr + tests/test_paths* + tests/output:  55 passed, 10 xpassed
tests/web/test_library_api.py:                  4 passed,  8 xpassed
tests/translate/test_engine.py -k series_id:   1 xpassed (GREEN)
```

All tests pass. The xpassed entries are expected — Phase 13 moved previously-xfail tests to green.

---

## Verdict

**BLOCK** on the HIGH finding (blocking pyarr calls on the event loop in `get_library`). The MEDIUM credential-redaction issue for PyarrError in the Sonarr/Radarr catch blocks should be fixed in the same pass.

The Bazarr param-format MEDIUM is tracked; the TODO marker is present, but the comment's claim of a "fall back" that does not exist should be corrected.
