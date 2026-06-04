# Phase 13: Backend Episodes Enrichment - Research

**Researched:** 2026-06-03
**Domain:** FastAPI route rewrite + SQLAlchemy aggregate query + pyarr episode API
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Enriched Episodes Endpoint (API-01)**
- D-01: Rewrite per `research/ARCHITECTURE.md §4`. Call `client.episode.get(series_id=N)` for episode records alongside `client.episode_file.get(series_id=N)`. Build `episodeFile.id → episodeFile` lookup. Group by `seasonNumber` server-side. Return `{ series_id, bazarr_available, seasons, errors }` envelope. Wrap every pyarr call in `asyncio.to_thread`. Season 0 (Specials) included.
- D-02: Each subtitle badge carries `code2`, `code3`, `hi`, AND `forced`. Strip subtitle file paths from badges. Join Bazarr inventory to episodes by `BazarrInventoryItem.arr_id == episode.id` (sonarrEpisodeId) — NOT episodeFile.id.

**Episode Key**
- D-03: `episode_key = f"S{seasonNumber:02d}E{episodeNumber:02d}"` from authoritative Sonarr episode-record ints. Retire `_episode_key_from_file` for this endpoint. Status stays filesystem-based.

**Progress Counts (API-02)**
- D-04: `total_count` = `statistics.episodeFileCount` from `series.get()` (no extra call). Movie: `total_count = 1 if hasFile else 0`.
- D-05: `translated_count` = COUNT(ProcessedFile) WHERE `series_id = str(series_id)` AND `status = 'done'`. Add bulk helper `translated_counts_for_series(ids) -> {series_id: n}`. Key by `str(series_id)`.
- D-06 (CRITICAL): Verify `ProcessedFile.series_id` population. Planner must not ship count assuming series_id is set without checking.

**Audio Language Normalization (API-01)**
- D-07: Normalize `mediaInfo.audioLanguages` full names → ISO-639-1 `code2` in backend. Reuse/extend `trezarr/source_selection/rank.py` constants. Split `/`-joined values, dedupe preserving order, map unknowns to lowercased original or `'und'`.

**Fail-Soft Contract**
- D-08: Bazarr → always HTTP 200 (`bazarr_available: false` on BazarrError + errors[] entry; `bazarr_available: false` on disabled, no errors entry). Sonarr → stays non-200 (400/502 as today).

### Claude's Discretion
- Exact name/signature of the new count helper (bulk vs per-series)
- Whether the language map reuses `rank.py` constants or a new dict
- Movie `translated_count` via filesystem vs ledger
- Envelope field ordering
- Test fixture shapes

### Deferred Ideas (OUT OF SCOPE)
- Frontend `Series.tsx` / `SeriesDetail.tsx` / `Movies.tsx` consuming this contract → Phase 14
- NAV-03 sidebar count badge + LIVE badge → Phase 14
- React Query / SWR on the frontend
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | `GET /api/library/series/{id}/episodes` returns episodes from Sonarr episode records grouped by season, each carrying `audio_languages` (Sonarr mediaInfo) + `subtitles[]` (Bazarr inventory incl. `hi`/`forced`) + Trezarr status; Bazarr failures degrade fail-soft (endpoint still returns HTTP 200 without subtitle badges) | Full handler code in ARCHITECTURE.md §4; D-01/D-02/D-03/D-07/D-08 locked; see "Enriched Episodes Handler" code example below |
| API-02 | Library Series + Movies list endpoints expose per-item `translated_count` / `total_count` for progress indicators and nav badges | D-04/D-05/D-06 locked; D-06 resolution below; bulk count helper design in "Count Helper" section |
</phase_requirements>

---

## Summary

Phase 13 rewrites one FastAPI route (`get_series_episodes`) and extends another (`get_library`) with count fields. The endpoint design is fully settled in `ARCHITECTURE.md §4` and the CONTEXT.md decisions. Research focused exclusively on the three open implementation risks the planner needs to resolve before coding: (1) whether `ProcessedFile.series_id` is reliably populated (D-06 CRITICAL), (2) where to place the new count helper and what session access pattern the web layer uses, and (3) what audio-language constants already exist in `rank.py` and whether they cover the `mediaInfo.audioLanguages` full-name space.

**D-06 CRITICAL finding:** `ProcessedFile.series_id` is **NOT reliably populated** at translation completion time. The engine's `ledger.record(LedgerEntry(...))` call at Step 11 (engine.py:1097–1103) omits `series_id` entirely — it is not passed to the `LedgerEntry` constructor in the success path. The field will be `None` for all completed translations. A `COUNT(*) WHERE series_id = str(id) AND status = 'done'` will return **zero for every series** until this is fixed. The planner must include a remediation task. See the D-06 section below for the exact fix location.

**Primary recommendation:** Fix the engine's success-path `ledger.record` call first (add `series_id=str(media_item.series_id)` when `eligible_item` is not None), then implement the bulk count helper in `ledger_sqla.py`, then the web layer consumes it.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Episode record enrichment (audio + subtitles + status) | API / Backend | — | Sonarr/Bazarr API calls; filesystem checks; data all on server |
| Season grouping | API / Backend | — | Server-level grouping per D-01; client gets pre-grouped contract |
| Audio full-name → ISO-639-1 lookup | API / Backend | — | Normalization at the boundary; UI receives clean `code2` strings |
| Bazarr fail-soft envelope | API / Backend | — | Error isolation; client reads `bazarr_available` flag |
| translated_count / total_count | API / Backend + Database / Storage | — | count is an aggregate DB query; total comes from Sonarr stats |
| Series_id population at translate time | API / Backend (engine) | — | Fix lives in engine.py Step 11; prerequisite for count correctness |

---

## D-06 CRITICAL: series_id Population Audit

### What was found

`ProcessedFile.series_id` (type `str | None`) is documented as "reserved for Phase-4 FK" in `ledger.py`. The column exists in the SQLAlchemy model (`bible/models.py:304`) and in `LedgerEntry`. The `record()` call in the engine's **success path** (engine.py:1097–1103) does NOT pass `series_id`:

```python
# engine.py Step 11 — CURRENT (series_id MISSING)
await ledger.record(LedgerEntry(
    source_path=str(path),
    output_path=str(output_path),
    status="done",
    content_hash=content_hash,
    translated_at=datetime.now(timezone.utc).isoformat(),
    # series_id is omitted → defaults to None
))
```

Three quarantine paths (engine.py:812, 911, 1080) also omit `series_id`. The `eligible_item.media_item.series_id` (int) is available in scope at Step 11 because the engine reads `arr_series_id = getattr(media_item, "series_id", None) or 0` at line 786. [VERIFIED: trezarr/translate/engine.py lines 786, 1097-1103]

### Impact

A `COUNT(*) WHERE series_id = str(series_id_int) AND status = 'done'` will return **0 for every series** under current code — the count feature is entirely broken until fixed.

### Exact remediation

The planner must add a task in Wave 0 (before implementing the count helper) that adds `series_id` to the success-path `ledger.record` call:

```python
# engine.py Step 11 — AFTER FIX
_ledger_series_id: str | None = (
    str(arr_series_id) if eligible_item is not None and arr_series_id else None
)
await ledger.record(LedgerEntry(
    source_path=str(path),
    output_path=str(output_path),
    status="done",
    content_hash=content_hash,
    translated_at=datetime.now(timezone.utc).isoformat(),
    series_id=_ledger_series_id,      # <-- add this
))
```

`arr_series_id` is already in scope at Step 11 (it is set at line 786 and used at line 796 to call `get_or_create_series`). When `eligible_item is None` (mechanical path), `series_id` correctly stays `None`. [VERIFIED: trezarr/translate/engine.py]

### Type alignment

Sonarr series id is `int` from the `series_id` column in `Job` and `series_id` field in `MediaItem`. The ledger stores it as `str` (both `LedgerEntry.series_id: str | None` and `ProcessedFile.series_id: Mapped[str | None]`). The count query must use `str(series_id_int)`. [VERIFIED: trezarr/bible/models.py:304, trezarr/output/ledger.py:81]

---

## Standard Stack

No new packages are required for this phase. All work uses the project's existing stack.

| Component | Version | Purpose | Already Used |
|-----------|---------|---------|-------------|
| FastAPI | 0.136.x | Route handler | Yes |
| SQLAlchemy 2.0 async | 2.0.x | New aggregate count query | Yes |
| aiosqlite | 0.22.x | Async SQLite driver | Yes |
| pyarr (Sonarr) | 6.6.x | `episode.get()` + `episode_file.get()` | Yes |
| httpx / BazarrClient | 0.28.x | `fetch_episode_inventory` | Yes |
| pytest + pytest-asyncio | — | Tests | Yes |

[VERIFIED: trezarr/CLAUDE.md stack table, pyproject.toml]

### Package Legitimacy Audit

No new packages are installed in this phase. Section not applicable.

---

## Architecture Patterns

### System Architecture Diagram

```
GET /api/library/series/{id}/episodes
        │
        ├─ sonarr_enabled? No → HTTP 400
        │
        ├─ asyncio.gather(
        │     to_thread(episode.get(series_id)),
        │     to_thread(episode_file.get(series_id))
        │  )
        │    │
        │    └── ep_file_by_id = {ef["id"]: ef for ef in ep_files}
        │
        ├─ bazarr_enabled? ──────── No ─────────────── bazarr_available=False
        │       │                                             │
        │       Yes                                           │
        │       │                                             │
        │  fetch_episode_inventory(series_id)                 │
        │       │                                             │
        │  BazarrError? ─── Yes ─── bazarr_available=False ──┤
        │       │                   errors[].append(...)      │
        │       No                                            │
        │       │                                             │
        │  bazarr_by_ep_id = {item.arr_id: subtitles}        │
        │  bazarr_available = True                            │
        │                                                     │
        └─ for each episode record: ──────────────────────────┘
              ep_file = ep_file_by_id.get(episode.episodeFileId)
              local_path = apply_path_mapping(ep_file.path)
              audio_languages = normalize_audio_langs(mediaInfo.audioLanguages)
              source_sub = find_source_sub(local_path)
              status = "translated" | "has_source" | "nothing"
              subtitles = bazarr_by_ep_id.get(episode.id, [])
              seasons[seasonNumber].append(episode_row)
        │
        └─ HTTP 200 JSON { series_id, bazarr_available, seasons, errors }


GET /api/library
        │
        ├─ [existing Sonarr/Radarr calls — unchanged]
        │
        ├─ series_ids = [s["id"] for s in raw_series]
        │
        ├─ translated_counts = await translated_counts_for_series(
        │       session_factory, series_ids
        │  )  ← one aggregate SQL GROUP BY query
        │
        ├─ for each series:
        │       series_item["translated_count"] = translated_counts.get(str(s_id), 0)
        │       series_item["total_count"] = s.get("statistics", {}).get("episodeFileCount", 0)
        │
        ├─ for each movie:
        │       movie_item["translated_count"] = 1 if vi_sidecar_exists else 0
        │       movie_item["total_count"] = 1 if m.get("hasFile") else 0
        │
        └─ HTTP 200 JSON { series, movies, errors }
```

### Recommended Project Structure

No structural changes needed. Modifications to existing files only:

```
trezarr/
  translate/engine.py          ← FIX series_id in success-path ledger.record (D-06)
  output/ledger_sqla.py        ← ADD translated_counts_for_series() helper
  web/routes/library.py        ← REWRITE get_series_episodes; EXTEND get_library
  source_selection/rank.py     ← READ-ONLY: reuse _ORIG_LANG_NAME_TO_CODE2

tests/
  web/test_library_api.py      ← ADD: enriched envelope, Bazarr fail-soft, audio lookup, counts
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async blocking pyarr | call pyarr directly in async def | `asyncio.to_thread(client.episode.get, ...)` | pyarr is synchronous; blocks event loop |
| Parallel Sonarr calls | sequential await calls | `asyncio.gather(episodes_coro, ep_files_coro)` | Two calls, no ordering dependency |
| Bazarr subtitle path exposure | expose subtitle paths in badges | strip paths, return only code2/code3/hi/forced | D-02; paths are container-internal |
| Language mapping | new full lookup table | extend `_ORIG_LANG_NAME_TO_CODE2` from `rank.py` | 40+ entries already exist; avoid divergence |
| Per-series count loop | N individual SELECT COUNT queries | one GROUP BY aggregate | O(N) → O(1) DB roundtrips |

---

## Count Helper: Placement and Query Design

### Where it lives

Place `translated_counts_for_series` in `trezarr/output/ledger_sqla.py` as a **module-level async function** (not a method on `LedgerSQLA`). Rationale: it is a read aggregate that the web route needs, not a check/record operation on the ledger protocol. The web route can call it directly alongside the ledger.

### Session access in the web layer

The web route retrieves `session_factory` from `request.app.state.session_factory` (the pattern already used by `post_translate` at library.py:265). The count helper must accept `session_factory` and open its own session. [VERIFIED: trezarr/web/routes/library.py:265]

### Bulk count query

```python
# trezarr/output/ledger_sqla.py — new function
from sqlalchemy import func, select
from trezarr.bible.models import ProcessedFile

async def translated_counts_for_series(
    session_factory: async_sessionmaker,
    series_ids: list[int],
) -> dict[str, int]:
    """Return {str(series_id): count} of status='done' ProcessedFile rows.

    Uses one GROUP BY aggregate. Returns 0 for series_ids with no records.
    Key type is str because ProcessedFile.series_id is Mapped[str | None].
    """
    if not series_ids:
        return {}
    str_ids = [str(sid) for sid in series_ids]
    async with session_factory() as session:
        result = await session.execute(
            select(ProcessedFile.series_id, func.count().label("n"))
            .where(
                ProcessedFile.series_id.in_(str_ids),
                ProcessedFile.status == "done",
            )
            .group_by(ProcessedFile.series_id)
        )
        return {row.series_id: row.n for row in result}
```

[VERIFIED: trezarr/bible/models.py — ProcessedFile.series_id is Mapped[str | None]; trezarr/output/ledger_sqla.py — uses async_sessionmaker pattern throughout]

---

## Audio Language Normalization

### Existing constant: `_ORIG_LANG_NAME_TO_CODE2` in `rank.py`

`trezarr/source_selection/rank.py` already contains `_ORIG_LANG_NAME_TO_CODE2: dict[str, str]` with 40+ lowercase full-name → ISO-639-1 entries. [VERIFIED: trezarr/source_selection/rank.py:55-105]

Entries include all common East Asian, European, Middle Eastern, and Southeast Asian languages. Notable entries present: Korean→ko, Japanese→ja, Chinese→zh, Thai→th, English→en, French→fr, German→de, Russian→ru, Arabic→ar, Hindi→hi, Indonesian→id.

### Sonarr `mediaInfo.audioLanguages` format

`mediaInfo.audioLanguages` from Sonarr episode files returns a single string with `/`-joined values when multiple audio tracks exist (e.g. `"Korean/English"`). Single-track files return just the name (e.g. `"Korean"`). This is the authoritative format Sonarr uses. [ASSUMED — from standard Sonarr API behavior; verified by ARCHITECTURE.md §4 which uses `media_info.get("audioLanguages") or []` and treats it as a list already]

**Correction:** Looking at ARCHITECTURE.md §4 code, `audio_languages = media_info.get("audioLanguages") or []` suggests Sonarr may return a list directly rather than a `/`-joined string. The plan code should handle both (list passthrough; string split on `/`).

### Normalization function (Claude's Discretion — D-07)

```python
# Suggested implementation inside library.py route handler
from trezarr.source_selection.rank import _ORIG_LANG_NAME_TO_CODE2

def _normalize_audio_languages(raw: list | str | None) -> list[str]:
    """Full-name list → ISO-639-1 code2 list. Dedupes, preserves order."""
    if not raw:
        return []
    if isinstance(raw, str):
        names = [n.strip() for n in raw.split("/") if n.strip()]
    else:
        # Sonarr may return a list; each entry may itself be slash-joined
        names = []
        for item in raw:
            names.extend(n.strip() for n in str(item).split("/") if n.strip())
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        code = _ORIG_LANG_NAME_TO_CODE2.get(name.lower(), name.lower())
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result
```

Unknown names fall back to `name.lower()` (the original as a fallback, not `'und'`) per D-07. [ASSUMED — D-07 says "map unknown languages to the lowercased original (or 'und')"; using lowercased original is more informative]

---

## Sonarr `statistics.episodeFileCount` Verification

D-04 requires `total_count = statistics.episodeFileCount`. The `statistics` block is present on Sonarr v3 `series.get()` responses. [ASSUMED — standard Sonarr v3 API; not directly verified against the live instance in this session. The CONTEXT.md notes "verify the field is present in the live payload" as an integration step]

The field names within `statistics` are: `previousAiring`, `episodeFileCount`, `episodeCount`, `totalEpisodeCount`, `sizeOnDisk`, `percentOfEpisodes`. [ASSUMED based on Sonarr v3 API docs knowledge]

In `get_library`, the current code reads `s.get("statistics", {}).get("episodeFileCount", 0)` — this is safe because `statistics` may be absent on series with no files.

---

## Bazarr `fetch_episode_inventory` Parameter Risk

`fetch_episode_inventory` in `bazarr.py:305` uses `params=[("seriesid[]", sonarr_series_id)]` (list-form). ARCHITECTURE.md §8 flags that this may return empty on the live Bazarr instance (192.168.5.42). The unbracketed form `{"seriesid": N}` is used by `fetch_episodes`. [VERIFIED: trezarr/arr/bazarr.py:305]

The planner must include a live integration verification step: call `fetch_episode_inventory` against the live Bazarr at 192.168.5.42 and confirm `data` is non-empty. If empty, fall back to `params={"seriesid": N}` or try `params=[("seriesid", N)]`.

---

## Movie translated_count

D-05 notes movie `translated_count` can use filesystem vi check (consistent with `source_sub_found` cost). `get_library` already calls `find_source_sub` per movie. The cheapest correct approach is to add a parallel vi-sidecar check:

```python
# In the movie loop (after existing source_sub_found check):
vi_found = False
if raw_path and source_sub_found:
    vi_exts = (".vi.srt", ".vi.ass", ".vi.vtt")
    vi_found = any((local_path.parent / (local_path.stem + ext)).exists()
                   for ext in vi_exts)
movies_list.append({
    ...,
    "translated_count": 1 if vi_found else 0,
    "total_count": 1 if m.get("hasFile", False) else 0,
})
```

This is consistent with how `get_series_episodes` determines `status == "translated"` and requires no additional DB query. [VERIFIED: trezarr/web/routes/library.py — find_source_sub already called; vi_found pattern mirrors existing code at library.py:199-203]

---

## Common Pitfalls

### Pitfall 1: episode.get() vs episode_file.get() join key confusion

**What goes wrong:** Joining Bazarr inventory on `episodeFile.id` instead of `episode.id`. Bazarr's `arr_id` field is `sonarrEpisodeId` — the Sonarr episode RECORD id, not the episode file id.
**Why it happens:** The current endpoint uses `episode_file.get()` and is indexed on file IDs. Natural confusion when adding the new `episode.get()` call.
**How to avoid:** Always join `bazarr_item.arr_id == ep["id"]` (episode record). Never join on `ep_file["id"]`.
**Warning signs:** All episodes return `subtitles: []` even when Bazarr shows subs — the join is wrong.

### Pitfall 2: pyarr returns single dict on single-item results

**What goes wrong:** `client.episode.get(series_id=N)` returns a plain dict (not a list) when only one episode exists. Iterating it as a list fails.
**Why it happens:** pyarr v6.x normalizes results inconsistently.
**How to avoid:** Always normalize: `if isinstance(episodes_raw, dict): episodes_raw = [episodes_raw]` — this pattern is already used in the existing handler.

### Pitfall 3: asyncio.to_thread omitted on pyarr calls

**What goes wrong:** Calling sync pyarr inside `async def` blocks the FastAPI event loop. Causes UI unresponsiveness during library loads.
**How to avoid:** Wrap all three calls (`episode.get`, `episode_file.get`, any fallback) in `asyncio.to_thread`. Use `asyncio.gather` for the two Sonarr calls in parallel.

### Pitfall 4: `statistics` field absent from series

**What goes wrong:** `KeyError` or `None` when accessing `statistics.episodeFileCount` on a series with no episodes yet indexed.
**How to avoid:** `s.get("statistics", {}).get("episodeFileCount", 0)` — always default to 0.

### Pitfall 5: `translated_count` silently 0 due to missing series_id

**What goes wrong:** The count query returns 0 for all series because `ProcessedFile.series_id` is `NULL` for all rows (engine never set it).
**How to avoid:** Fix engine.py Step 11 FIRST (see D-06 section) before implementing and testing the count endpoint. Add a test that confirms the count returns > 0 after a mock translation.

### Pitfall 6: `_ORIG_LANG_NAME_TO_CODE2` is private

**What goes wrong:** Importing `_ORIG_LANG_NAME_TO_CODE2` from `rank.py` with a leading underscore is technically accessing a private symbol. Future refactors could rename or move it.
**How to avoid:** Either import it directly (acceptable for an intra-project private symbol) or add a small `AUDIO_LANG_MAP` alias to `rank.py`'s `__all__`. The planner can choose either approach.

---

## Code Examples

### Enriched Episode Handler (ARCHITECTURE.md §4 pattern, updated for D-02 `forced` field)

```python
# trezarr/web/routes/library.py — get_series_episodes (rewritten)
import asyncio
from collections import defaultdict
from pathlib import Path

@router.get("/library/series/{series_id}/episodes")
async def get_series_episodes(series_id: int, request: Request) -> JSONResponse:
    from trezarr.config import TrezarrSettings
    from trezarr.arr.sonarr import build_sonarr_client
    from trezarr.arr.bazarr import BazarrClient, BazarrError
    from trezarr.discover.scan import find_source_sub
    from trezarr.paths import apply_path_mapping
    from pyarr.exceptions import PyarrError
    from trezarr.source_selection.rank import _ORIG_LANG_NAME_TO_CODE2

    settings = getattr(request.app.state, "settings", None) or TrezarrSettings()

    if not settings.sonarr_enabled:
        return JSONResponse({"error": "sonarr_disabled"}, status_code=400)

    errors: list[dict] = []

    try:
        client = build_sonarr_client(settings)
        episodes_coro = asyncio.to_thread(client.episode.get, series_id=series_id)
        ep_files_coro = asyncio.to_thread(client.episode_file.get, series_id=series_id)
        episodes_raw, ep_files_raw = await asyncio.gather(episodes_coro, ep_files_coro)
    except PyarrError as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)

    if isinstance(episodes_raw, dict): episodes_raw = [episodes_raw]
    if isinstance(ep_files_raw, dict): ep_files_raw = [ep_files_raw]
    ep_file_by_id = {ef["id"]: ef for ef in ep_files_raw}

    # Bazarr — fail-soft (D-08)
    bazarr_by_ep_id: dict[int, list] = {}
    bazarr_available = False
    if settings.bazarr_enabled:
        try:
            bazarr_client = BazarrClient.from_settings(settings)
            bazarr_items = await bazarr_client.fetch_episode_inventory(series_id)
            bazarr_by_ep_id = {
                item.arr_id: [
                    {"code2": s.code2, "code3": s.code3, "hi": s.hi, "forced": s.forced}
                    for s in item.subtitles
                ]
                for item in bazarr_items
            }
            bazarr_available = True
        except BazarrError as exc:
            logger.warning("get_series_episodes: Bazarr unavailable — %s", exc)
            errors.append({"source": "bazarr", "error": str(exc)})

    seasons: dict[int, list[dict]] = defaultdict(list)
    for ep in episodes_raw:
        ep_id = ep.get("id")
        ep_file_id = ep.get("episodeFileId")
        has_file = bool(ep.get("hasFile", False))
        ep_file = ep_file_by_id.get(ep_file_id) if ep_file_id else None

        raw_path = ep_file.get("path", "") if ep_file else ""
        local_path = str(apply_path_mapping(raw_path, settings.path_mappings)) if raw_path else None
        media_info = (ep_file or {}).get("mediaInfo") or {}
        audio_raw = media_info.get("audioLanguages") or []
        audio_languages = _normalize_audio_languages(audio_raw, _ORIG_LANG_NAME_TO_CODE2)

        season_number = ep.get("seasonNumber", 0)
        episode_number = ep.get("episodeNumber", 0)
        episode_key = f"S{season_number:02d}E{episode_number:02d}"

        source_path = source_lang = None
        status = "nothing"
        if local_path:
            lp = Path(local_path)
            src = find_source_sub(lp, settings.source_lang_priority) if lp.exists() else None
            if src:
                source_path, source_lang = str(src[0]), src[1]
                vi_found = any(
                    (lp.parent / (lp.stem + ext)).exists()
                    for ext in (".vi.srt", ".vi.ass", ".vi.vtt")
                )
                status = "translated" if vi_found else "has_source"

        seasons[season_number].append({
            "episode_id": ep_id,
            "episode_file_id": ep_file_id,
            "season_number": season_number,
            "episode_number": episode_number,
            "episode_key": episode_key,
            "title": ep.get("title", ""),
            "monitored": ep.get("monitored", False),
            "has_file": has_file,
            "local_path": local_path,
            "source_path": source_path,
            "source_lang": source_lang,
            "status": status,
            "audio_languages": audio_languages,
            "subtitles": bazarr_by_ep_id.get(ep_id, []),
        })

    result = {
        "series_id": series_id,
        "bazarr_available": bazarr_available,
        "seasons": [
            {"season_number": sn, "episodes": seasons[sn]}
            for sn in sorted(seasons)
        ],
        "errors": errors,
    }
    return JSONResponse(result)
```

Note: `_normalize_audio_languages` is a local helper in `library.py` (see Audio Normalization section). [Source: ARCHITECTURE.md §4 + D-01/D-02/D-08 locked decisions]

---

## State of the Art

| Old Approach | Current Approach | Relevant Change |
|--------------|------------------|-----------------|
| `episode_file.get()` flat list | `episode.get()` + `episode_file.get()` joined | episode records have authoritative numbering, `hasFile`, `monitored` |
| sync pyarr in async def | `asyncio.to_thread()` wrapping | latent bug fixed in this phase |
| No Bazarr integration | Bazarr `fetch_episode_inventory` merged by sonarrEpisodeId | subtitle badges per episode |
| `_episode_key_from_file` regex parse | `f"S{seasonNumber:02d}E{episodeNumber:02d}"` from ints | no regex fragility; donghua/NxNN handled by Sonarr's own numbering |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` `asyncio_mode = "auto"` |
| Quick run command | `uv run pytest tests/web/test_library_api.py -q` |
| Full suite command | `uv run pytest tests/ -q` |

[VERIFIED: pyproject.toml]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | Bazarr disabled → `bazarr_available:false`, HTTP 200, no errors[] entry | unit | `uv run pytest tests/web/test_library_api.py::test_get_series_episodes_bazarr_disabled -xq` | ❌ Wave 0 |
| API-01 | Bazarr enabled but unreachable → `bazarr_available:false`, HTTP 200, errors[] entry | unit | `uv run pytest tests/web/test_library_api.py::test_get_series_episodes_bazarr_error -xq` | ❌ Wave 0 |
| API-01 | Bazarr join by `episode.id` not `episodeFile.id` | unit | `uv run pytest tests/web/test_library_api.py::test_get_series_episodes_bazarr_join_key -xq` | ❌ Wave 0 |
| API-01 | `audio_languages` normalizes "Korean/English" → ["ko", "en"] | unit | `uv run pytest tests/web/test_library_api.py::test_audio_language_normalization -xq` | ❌ Wave 0 |
| API-01 | Response has `seasons` grouped by `season_number`, `episode_id`, `episode_key` fields | unit | `uv run pytest tests/web/test_library_api.py::test_get_series_episodes_envelope_shape -xq` | ❌ Wave 0 |
| API-02 | `translated_count` + `total_count` present on series list items | unit | `uv run pytest tests/web/test_library_api.py::test_get_library_series_count_fields -xq` | ❌ Wave 0 |
| API-02 | `translated_counts_for_series` returns correct counts given mock ProcessedFile rows | unit | `uv run pytest tests/web/test_library_api.py::test_translated_counts_for_series -xq` | ❌ Wave 0 |
| D-06 fix | engine records `series_id` on success path | unit | `uv run pytest tests/translate/test_engine.py::test_ledger_records_series_id_on_success -xq` | ❌ Wave 0 |

### Existing Tests

The current `tests/web/test_library_api.py` has 4 tests covering HTTP status codes only. All 4 must remain green after the rewrite. Shape assertions need to be updated where `get_series_episodes` changed from a flat list to the season-grouped envelope. [VERIFIED: tests/web/test_library_api.py]

`tests/translate/test_engine.py` exists and tests the engine; the D-06 fix test should go there. [VERIFIED: test file found at tests/translate/test_engine.py]

### Test Fixture Shape for Sonarr Episode Mocking

The enriched endpoint requires two mock pyarr calls. Pattern: mock `client.episode.get` and `client.episode_file.get` independently. Use `unittest.mock.patch` or pytest `monkeypatch`. Tests must patch at `trezarr.arr.sonarr.build_sonarr_client` level and return mock objects.

### Sampling Rate

- Per task commit: `uv run pytest tests/web/test_library_api.py -q`
- Per wave merge: `uv run pytest tests/ -q`
- Phase gate: full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/web/test_library_api.py` — 8 new test functions (Bazarr disabled path, Bazarr error path, join key correctness, audio normalization, envelope shape, count fields, count helper unit test)
- [ ] `tests/translate/test_engine.py` — 1 new test for series_id on success-path ledger.record
- [ ] No new framework or conftest needed; existing fixtures are sufficient

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pyarr (Sonarr client) | Episode API calls | Yes (installed) | 6.6.x | — |
| BazarrClient (httpx) | Subtitle inventory | Yes (installed) | 0.28.x | fail-soft path |
| aiosqlite | Async SQLite for count query | Yes (installed) | 0.22.x | — |
| Live Bazarr at 192.168.5.42 | Integration test of `seriesid[]` param | Yes (per memory) | — | Unbracketed fallback |

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | Yes | `series_id: int` path param — FastAPI validates type automatically |
| V4 Access Control | No | No auth change; existing API key pattern unchanged |
| V2 Authentication | No | Unchanged |
| V6 Cryptography | No | No new cryptography |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path exposure in subtitle badges | Information Disclosure | D-02 mandates stripping subtitle paths; only return code2/code3/hi/forced |
| series_id SQL injection via count query | Tampering | SQLAlchemy parameterized query (`.in_(str_ids)` is always parameterized) |
| BazarrError message leaking API key | Information Disclosure | Already handled in bazarr.py T-10-02 — messages use `_normalize_arr_host` |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sonarr `mediaInfo.audioLanguages` may return a list (not a slash-joined string) as suggested by ARCHITECTURE.md §4 code | Audio Normalization | Normalization helper must handle both; if always a string, list branch is dead code — no functional impact |
| A2 | Sonarr v3 `statistics.episodeFileCount` is present in `series.get()` payload | D-04 / Standard Stack | If absent, total_count defaults to 0; planner must add live verification step |
| A3 | `_ORIG_LANG_NAME_TO_CODE2` in rank.py covers most Sonarr audioLanguages values | Audio Normalization | Unknown languages fall back to lowercased original; audible gap but not a crash |

**If this table is empty after implementation:** All claims were verified against source files — A1/A2/A3 are the only three that warrant a live check.

---

## Open Questions (RESOLVED)

> All three are addressed in-code with safe defaults; each has a live-integration
> verification step documented in 13-VALIDATION.md §Manual-Only Verifications.
> (Q1: `.get("statistics",{}).get("episodeFileCount",0)` safe default; Q2: bracketed
> `seriesid[]` with unbracketed fallback comment; Q3: no backfill — counts reflect
> future translations only.)

1. **Sonarr `statistics.episodeFileCount` live presence**
   - What we know: Present in Sonarr v3 API spec; referenced in CONTEXT.md D-04
   - What's unclear: Whether every series object in the `/api/v3/series` response includes `statistics` (some series may not have been indexed yet)
   - Recommendation: Add `s.get("statistics", {}).get("episodeFileCount", 0)` with 0 default; verify against live Sonarr during integration

2. **Bazarr `seriesid[]` vs `seriesid` param**
   - What we know: `fetch_episode_inventory` uses `[("seriesid[]", N)]`; ARCHITECTURE.md §8 flags it may return empty
   - What's unclear: Whether the live Bazarr at 192.168.5.42 actually returns data with this form
   - Recommendation: Add a live verification step in the integration plan; fall back to `{"seriesid": N}` if empty

3. **Existing ProcessedFile rows with `series_id = NULL`**
   - What we know: All current ledger rows have `series_id = NULL` (engine never populated it)
   - What's unclear: Whether the user wants a backfill migration for existing translations
   - Recommendation: For v1.1, no backfill — `translated_count` counts future translations after the fix. Document this limitation in the plan.

---

## Sources

### Primary (HIGH confidence)
- `trezarr/translate/engine.py` — Step 11 (lines 1097–1103) — success-path ledger.record omits series_id; `arr_series_id` available at line 786 — code verified directly
- `trezarr/bible/models.py:304` — `ProcessedFile.series_id: Mapped[str | None]` — column definition verified
- `trezarr/output/ledger.py:81` — `LedgerEntry.series_id: str | None` — type verified
- `trezarr/arr/bazarr.py:305` — `fetch_episode_inventory` uses `params=[("seriesid[]", N)]` — verified
- `trezarr/arr/bazarr.py:52-86` — `SubtitleEntry` has `forced: bool` and `hi: bool` — verified
- `trezarr/source_selection/rank.py:55-105` — `_ORIG_LANG_NAME_TO_CODE2` 40+ entries — verified
- `trezarr/web/routes/library.py` — current `get_series_episodes` (flat list, sync pyarr) and `get_library` (series/movies + errors) — verified
- `trezarr/output/ledger_sqla.py` — no count method exists; session_factory pattern via `async_sessionmaker` — verified
- `trezarr/web/worker.py:265` — `session_factory = getattr(request.app.state, "session_factory", None)` pattern (actually at library.py:265) — verified
- `tests/web/test_library_api.py` — 4 existing tests, asyncio_mode="auto" — verified
- `pyproject.toml` — `asyncio_mode = "auto"`, `testpaths = ["tests"]`, `uv` tooling — verified

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md §4` — full handler code, JSON contract, asyncio.to_thread pattern — HIGH within project context
- `.planning/phases/13-backend-episodes-enrichment/13-CONTEXT.md` — locked decisions D-01..D-08 — authoritative

---

## Metadata

**Confidence breakdown:**
- D-06 series_id finding: HIGH — code read directly from engine.py
- Standard stack: HIGH — no new packages
- Architecture patterns: HIGH — from ARCHITECTURE.md §4 (pre-done research) + code verification
- Count helper design: HIGH — SQLAlchemy group-by aggregate is straightforward
- Audio normalization: HIGH — existing constant verified; Sonarr return format MEDIUM (A1)
- Pitfalls: HIGH — derived from direct code inspection

**Research date:** 2026-06-03
**Valid until:** 2026-07-03 (stable stack; no fast-moving dependencies)
