"""Library browser + manual translate endpoints (quick task 260603-l8g).

Endpoints:
  GET  /api/library                          — list Sonarr series + Radarr movies
  GET  /api/library/series/{id}/episodes     — per-series episode file list
  POST /api/translate                        — enqueue a single item for translation

Design decisions:
  - All imports are deferred inside route bodies (PLC0415 project pattern).
  - GET /api/library always returns HTTP 200 — per-source errors land in the
    ``errors`` list so the caller never gets a 500 on *arr timeout.
  - POST /api/translate never calls translate_file synchronously; it only calls
    enqueue_job(trigger='manual') so the worker loop handles the work.
  - Path-traversal guard mirrors cli.py: skip when media_roots is empty/None
    (passthrough mode), apply assert_within_media_roots otherwise (T-l8g-01).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _episode_key_from_file(ep_file: dict, raw_path: str) -> str:
    """Build an ``SxxExx`` display key for a Sonarr episode file.

    Sonarr gives the authoritative ``seasonNumber`` on the file record; the
    episode number is parsed from the file/scene name, tolerant of both
    ``SxxExx`` and ``NxNN`` (e.g. ``6x01``) naming used by donghua/anime
    releases. Falls back to the shared ``derive_episode_key`` parser only when
    nothing matches (never reuse that parser's S00E00 default blindly).
    """
    name = ep_file.get("relativePath") or ep_file.get("sceneName") or raw_path
    season = ep_file.get("seasonNumber")
    ep_num: int | None = None

    m = re.search(r"[sS](\d{1,3})[ ._-]*[eE](\d{1,4})", name)
    if m:
        if season is None:
            season = int(m.group(1))
        ep_num = int(m.group(2))
    else:
        # NxNN form (e.g. "6x01"); lookarounds avoid matching resolutions like 1920x1080
        m = re.search(r"(?<!\d)(\d{1,3})\s*[xX]\s*(\d{1,4})(?!\d)", name)
        if m:
            if season is None:
                season = int(m.group(1))
            ep_num = int(m.group(2))
        else:
            m = re.search(r"(?<![A-Za-z\d])[eE](\d{1,4})(?!\d)", name)
            if m:
                ep_num = int(m.group(1))

    if season is not None and ep_num is not None:
        return f"S{int(season):02d}E{int(ep_num):02d}"

    from trezarr.translate.engine import derive_episode_key  # noqa: PLC0415
    return derive_episode_key(None, raw_path)


def _normalize_audio_languages(raw: list | str | None) -> list[str]:
    """Normalize Sonarr mediaInfo.audioLanguages to ISO-639-1 code2 list (D-07).

    Handles both string (slash-joined, e.g. "Korean/English") and list input.
    Dedupes preserving order. Maps full names via _ORIG_LANG_NAME_TO_CODE2;
    unknown names fall back to lowercased original.

    Args:
        raw: Raw audioLanguages value from Sonarr mediaInfo — str, list, or None.

    Returns:
        List of ISO-639-1 code2 strings (or lowercased fallback for unknowns).
    """
    if not raw:
        return []

    # Deferred import — D-07 reuses rank.py constants (noqa: PLC0415 pattern)
    from trezarr.source_selection.rank import _ORIG_LANG_NAME_TO_CODE2  # noqa: PLC0415

    names: list[str] = []
    if isinstance(raw, str):
        names = [part.strip() for part in raw.split("/") if part.strip()]
    else:
        # List input — each item may itself be slash-joined
        for item in raw:
            if isinstance(item, str):
                names.extend(part.strip() for part in item.split("/") if part.strip())

    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        code = _ORIG_LANG_NAME_TO_CODE2.get(name.lower(), name.lower())
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


# ── GET /api/library ───────────────────────────────────────────────────────────

@router.get("/library")
async def get_library(request: Request) -> JSONResponse:
    """List Sonarr series and Radarr movies.

    Per-source errors are collected into the ``errors`` list; the endpoint
    always returns HTTP 200 so the UI can display partial results.

    Series items include translated_count (D-05 bulk query) and total_count
    (D-04 from statistics.episodeFileCount). Movie items include translated_count
    (filesystem vi-sidecar check) and total_count (1 if hasFile else 0).
    """
    import asyncio  # noqa: PLC0415
    from trezarr.arr import DiscoveryError, _normalize_arr_host  # noqa: PLC0415
    from trezarr.arr.radarr import build_radarr_client  # noqa: PLC0415
    from trezarr.arr.sonarr import build_sonarr_client  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from trezarr.discover.scan import find_source_sub  # noqa: PLC0415
    from trezarr.paths import apply_path_mapping  # noqa: PLC0415
    from pyarr.exceptions import PyarrError  # noqa: PLC0415

    settings: TrezarrSettings = getattr(request.app.state, "settings", None) or TrezarrSettings()

    series_list: list[dict] = []
    movies_list: list[dict] = []
    errors: list[dict] = []

    # ── Sonarr: list all series ───────────────────────────────────────────────
    raw_series: list[dict] = []
    raw_series_stats: dict[int, int] = {}  # series_id -> episodeFileCount (D-04)

    if settings.sonarr_enabled:
        try:
            client = build_sonarr_client(settings)
            raw_series = await asyncio.to_thread(client.series.get)
            if isinstance(raw_series, dict):
                raw_series = [raw_series]
            for s in raw_series:
                images = s.get("images") or []
                poster_url = images[0].get("remoteUrl") if images else None
                s_id = s.get("id")
                # Accumulate episodeFileCount for post-loop total_count (D-04)
                if s_id is not None:
                    raw_series_stats[s_id] = s.get("statistics", {}).get("episodeFileCount", 0)
                series_list.append({
                    "kind": "series",
                    "id": s_id,
                    "title": s.get("title", ""),
                    "year": s.get("year"),
                    "monitored": s.get("monitored", False),
                    "poster_url": poster_url,
                })
        except (PyarrError, DiscoveryError, Exception) as exc:  # noqa: BLE001
            display = _normalize_arr_host(settings.sonarr_host)
            logger.warning("get_library: Sonarr error at %s — %s", display, type(exc).__name__)
            series_list = []
            raw_series = []
            errors.append({"source": "sonarr", "error": f"{type(exc).__name__} at {display}"})

    # D-05: bulk translated count — one aggregate DB query, not N queries
    if series_list:
        session_factory = getattr(request.app.state, "session_factory", None)
        if session_factory:
            from trezarr.output.ledger_sqla import translated_counts_for_series  # noqa: PLC0415
            _s_ids = [item.get("id") for item in series_list if item.get("id") is not None]
            t_counts = await translated_counts_for_series(session_factory, _s_ids)
        else:
            t_counts: dict[str, int] = {}
    else:
        t_counts = {}

    # Post-loop: apply translated_count and total_count to each series item
    for item in series_list:
        s_id = item.get("id")
        item["translated_count"] = t_counts.get(str(s_id), 0) if s_id is not None else 0
        item["total_count"] = raw_series_stats.get(s_id, 0) if s_id is not None else 0

    # ── Radarr: list all movies + source-sub status ───────────────────────────
    if settings.radarr_enabled:
        try:
            client = build_radarr_client(settings)
            raw_movies = await asyncio.to_thread(client.movie.get)
            if isinstance(raw_movies, dict):
                raw_movies = [raw_movies]
            for m in raw_movies:
                # movieFile.path is the video file (Pitfall 2 in radarr.py)
                movie_file = m.get("movieFile") or {}
                raw_path: str = movie_file.get("path", "") or ""
                if raw_path:
                    local_path = apply_path_mapping(raw_path, settings.path_mappings)
                    source_sub_result = find_source_sub(local_path, settings.source_lang_priority)
                    source_sub_found = source_sub_result is not None
                    # D-05 movie translated_count: filesystem vi-sidecar check
                    vi_found = any(
                        (local_path.parent / (local_path.stem + ext)).exists()
                        for ext in (".vi.srt", ".vi.ass", ".vi.vtt")
                    )
                else:
                    source_sub_found = False
                    vi_found = False
                images = m.get("images") or []
                poster_url = images[0].get("remoteUrl") if images else None
                movies_list.append({
                    "kind": "movie",
                    "id": m.get("id"),
                    "title": m.get("title", ""),
                    "year": m.get("year"),
                    "monitored": m.get("monitored", False),
                    "poster_url": poster_url,
                    "source_sub_found": source_sub_found,
                    "translated_count": 1 if vi_found else 0,
                    "total_count": 1 if m.get("hasFile", False) else 0,
                })
        except (PyarrError, DiscoveryError, Exception) as exc:  # noqa: BLE001
            display = _normalize_arr_host(settings.radarr_host)
            logger.warning("get_library: Radarr error at %s — %s", display, type(exc).__name__)
            movies_list = []
            errors.append({"source": "radarr", "error": f"{type(exc).__name__} at {display}"})

    return JSONResponse({
        "series": series_list,
        "movies": movies_list,
        "errors": errors,
        # Positive enabled flags (W1): each flag is the service's configured-on
        # state (settings.*_enabled). The UI combines it with the `errors[]` array
        # for the LIVE badge (enabled AND not erroring). This replaces the old
        # absence-of-error inference, under which a DISABLED service (empty list,
        # no error) showed a false-positive green LIVE badge.
        "services": {
            "sonarr": settings.sonarr_enabled,
            "radarr": settings.radarr_enabled,
            "bazarr": settings.bazarr_enabled,
        },
    })


# ── GET /api/library/series/{id}/episodes ─────────────────────────────────────

@router.get("/library/series/{series_id}/episodes")
async def get_series_episodes(series_id: int, request: Request) -> JSONResponse:
    """Return season-grouped episode records for one Sonarr series (D-01/D-08).

    Always returns HTTP 200 when Sonarr succeeds — Bazarr failures degrade
    gracefully (bazarr_available=False, subtitles=[]) per D-08 fail-soft contract.

    Sonarr disabled → 400. PyarrError → 502 (episodes view requires Sonarr).

    Response envelope:
      { series_id, bazarr_available, seasons: [{ season_number, episodes: [...] }], errors: [] }

    Each episode carries: episode_id, episode_file_id, season_number, episode_number,
    episode_key (SxxExx from ints — D-03), title, monitored, has_file, local_path,
    source_path, source_lang, status, audio_languages (ISO-639-1 — D-07),
    subtitles (list of {code2, code3, hi, forced} — D-02, no path field).
    """
    import asyncio  # noqa: PLC0415
    from collections import defaultdict  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415

    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    settings: TrezarrSettings = getattr(request.app.state, "settings", None) or TrezarrSettings()

    if not settings.sonarr_enabled:
        return JSONResponse({"error": "sonarr_disabled"}, status_code=400)

    errors: list[dict] = []

    # ── Sonarr fetch (asyncio.to_thread wraps all blocking pyarr calls — D-03) ─
    try:
        from trezarr.arr.sonarr import build_sonarr_client  # noqa: PLC0415
        from trezarr.discover.scan import find_source_sub  # noqa: PLC0415
        from trezarr.paths import apply_path_mapping  # noqa: PLC0415
        from pyarr.exceptions import PyarrError  # noqa: PLC0415

        client = build_sonarr_client(settings)

        # asyncio.to_thread for both pyarr calls; gather for concurrency (D-01)
        # Also fetch series record for series_title (UI#1 — heading needs the real name)
        episodes_coro = asyncio.to_thread(client.episode.get, series_id=series_id)
        ep_files_coro = asyncio.to_thread(client.episode_file.get, series_id=series_id)
        series_coro = asyncio.to_thread(client.series.get, series_id)
        episodes_raw, ep_files_raw, series_raw = await asyncio.gather(
            episodes_coro, ep_files_coro, series_coro
        )

        # series.get(id_=...) may return a list or a dict; normalise to dict
        if isinstance(series_raw, list):
            series_raw = series_raw[0] if series_raw else {}
        series_title: str | None = series_raw.get("title") if isinstance(series_raw, dict) else None

        # Pitfall 2: pyarr returns a single dict for a single result
        if isinstance(episodes_raw, dict):
            episodes_raw = [episodes_raw]
        if isinstance(ep_files_raw, dict):
            ep_files_raw = [ep_files_raw]

        # Build episode-file lookup by episodeFile.id (NOT episode.id — D-02)
        ep_file_by_id: dict[int, dict] = {ef["id"]: ef for ef in ep_files_raw if ef.get("id")}

    except PyarrError as exc:
        from trezarr.arr import _normalize_arr_host as _nh  # noqa: PLC0415
        display = _nh(settings.sonarr_host)
        logger.error("get_series_episodes: Sonarr error at %s for series_id=%d — %s", display, series_id, type(exc).__name__)
        return JSONResponse({"error": f"{type(exc).__name__} at {display}"}, status_code=502)
    except Exception as exc:  # noqa: BLE001
        logger.error("get_series_episodes: unexpected error for series_id=%d — %s", series_id, type(exc).__name__)
        return JSONResponse({"error": type(exc).__name__}, status_code=502)


    # ── Bazarr fail-soft block (D-08) ─────────────────────────────────────────
    # Disabled → bazarr_available=False, errors=[] (disabled is not an error).
    # Enabled + BazarrError → bazarr_available=False, errors[] entry. Always HTTP 200.
    bazarr_by_ep_id: dict[int, list[dict]] = {}
    bazarr_available = False

    if settings.bazarr_enabled:
        try:
            from trezarr.arr.bazarr import BazarrClient, BazarrError  # noqa: PLC0415

            bazarr_client = BazarrClient.from_settings(settings)
            # fetch_episode_inventory tries the "seriesid[]" query form then falls
            # back to plain "seriesid" if the bracketed form returns nothing (W3),
            # so a Bazarr build that expects either key works without a code change.
            bazarr_items = await bazarr_client.fetch_episode_inventory(series_id)
            # Build lookup: episode.id (arr_id / sonarrEpisodeId) → badge list (D-02)
            bazarr_by_ep_id = {
                item.arr_id: [
                    {
                        "code2": s.code2,
                        "code3": s.code3,
                        "hi": s.hi,
                        "forced": s.forced,
                        # D-02: subtitle path intentionally stripped — codes+flags only (T-13-01)
                    }
                    for s in item.subtitles
                ]
                for item in bazarr_items
            }
            bazarr_available = True
        except BazarrError as exc:
            logger.warning("get_series_episodes: Bazarr error for series_id=%d — %s", series_id, exc)
            errors.append({"source": "bazarr", "error": str(exc)})
            # bazarr_available stays False

    # ── Season grouping loop ──────────────────────────────────────────────────
    seasons: dict[int, list[dict]] = defaultdict(list)

    for ep in episodes_raw:
        ep_id: int | None = ep.get("id")
        ep_file_id: int | None = ep.get("episodeFileId")
        has_file: bool = bool(ep.get("hasFile", False))

        # Look up episode file by episodeFile.id (the join is file.id → file, not ep.id)
        ep_file: dict | None = ep_file_by_id.get(ep_file_id) if ep_file_id else None

        raw_path: str = ep_file.get("path", "") if ep_file else ""
        local_path_obj: _Path | None = None
        if raw_path:
            local_path_obj = apply_path_mapping(raw_path, settings.path_mappings)

        # Audio language normalization via _ORIG_LANG_NAME_TO_CODE2 (D-07)
        media_info: dict = (ep_file or {}).get("mediaInfo") or {}
        audio_raw = media_info.get("audioLanguages") or []
        audio_languages = _normalize_audio_languages(audio_raw)

        # D-03: episode_key from authoritative Sonarr episode-record ints (not filename parse)
        season_number: int = ep.get("seasonNumber", 0)
        episode_number: int = ep.get("episodeNumber", 0)
        episode_key = f"S{season_number:02d}E{episode_number:02d}"

        # Filesystem-based status (vi sidecar check)
        source_path: str | None = None
        source_lang: str | None = None
        status = "nothing"
        local_path_str: str | None = None

        if local_path_obj is not None:
            local_path_str = str(local_path_obj)
            if local_path_obj.exists():
                src = find_source_sub(local_path_obj, settings.source_lang_priority)
                if src is not None:
                    source_path = str(src[0])
                    source_lang = src[1]
                    vi_found = any(
                        (local_path_obj.parent / (local_path_obj.stem + ext)).exists()
                        for ext in (".vi.srt", ".vi.ass", ".vi.vtt")
                    )
                    status = "translated" if vi_found else "has_source"

        # Bazarr subtitles: join on episode.id == BazarrInventoryItem.arr_id (D-02)
        subtitles = bazarr_by_ep_id.get(ep_id, []) if ep_id is not None else []

        seasons[season_number].append({
            "episode_id": ep_id,
            "episode_file_id": ep_file_id,
            "season_number": season_number,
            "episode_number": episode_number,
            "episode_key": episode_key,
            "title": ep.get("title", ""),
            "monitored": ep.get("monitored", False),
            "has_file": has_file,
            "local_path": local_path_str,
            "source_path": source_path,
            "source_lang": source_lang,
            "status": status,
            "audio_languages": audio_languages,
            "subtitles": subtitles,
        })

    return JSONResponse({
        "series_id": series_id,
        "series_title": series_title,  # UI#1: real series name for SeriesDetail heading
        "bazarr_available": bazarr_available,
        "seasons": [{"season_number": sn, "episodes": seasons[sn]} for sn in sorted(seasons)],
        "errors": errors,
    })


# ── POST /api/translate ────────────────────────────────────────────────────────

@router.post("/translate")
async def post_translate(request: Request) -> JSONResponse:
    """Enqueue a single subtitle file for manual translation.

    Body (JSON): { kind, source_path, arr_series_id? }

    Returns 400 when source_path is absent or does not exist on disk.
    When media_roots is configured, validates path stays within allowed roots
    (T-l8g-01 path-traversal guard — mirrors cli.py ``if media_roots:`` guard).
    Returns { enqueued, source_path } on success.

    Bible-aware path (fix #3): constructs a media_item carrying arr_kind/series_id/
    source_type so _execute_job takes the Bible-aware branch instead of the mechanical
    fallback.  Sonarr enrichment (title/tvdb_id/arr_metadata) is fetched fail-soft —
    if *arr is unavailable, a minimal media_item is still passed so Bible-aware runs
    with safe-default register.
    """
    import asyncio  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    body: dict = await request.json()

    source_path: str | None = body.get("source_path")
    if not source_path:
        return JSONResponse({"error": "source_path_required"}, status_code=400)

    kind: str = body.get("kind") or "series"
    arr_series_id: int | None = body.get("arr_series_id")

    p = Path(source_path)
    if not p.exists():
        return JSONResponse(
            {"error": "source_sub_not_found", "path": source_path},
            status_code=400,
        )

    # Path-traversal guard (T-l8g-01): only active when media_roots is configured.
    # Mirrors cli.py's `if media_roots:` guard — skip in passthrough mode.
    media_roots = getattr(request.app.state, "media_roots", None)
    if media_roots:
        try:
            from trezarr.paths import assert_within_media_roots  # noqa: PLC0415
            assert_within_media_roots(p.resolve(), media_roots)
        except ValueError as exc:
            logger.warning("post_translate: path outside media roots — %s", exc)
            return JSONResponse(
                {"error": "path_outside_media_roots", "path": source_path},
                status_code=400,
            )

    session_factory = getattr(request.app.state, "session_factory", None)

    # ── Build media_item for Bible-aware path (fix #3) ───────────────────────
    # Derive source_type from the subtitle file extension (matches poll-path convention
    # in discover_sonarr_items: "episode" for series, "movie" for movies).
    # source_type is used by translate_file's register/genre signal; safe fallback
    # when the extension is ambiguous is the `kind` from the request body.
    _suffix = p.suffix.lower()
    if kind == "movie":
        arr_kind = "radarr"
        source_type = "movie"
    else:
        arr_kind = "sonarr"
        source_type = "episode"

    # Minimal media_item — always safe even if Sonarr fetch fails below.
    media_item_ns = SimpleNamespace(
        arr_kind=arr_kind,
        series_id=arr_series_id,
        source_type=source_type,
        # enrichment fields populated by Sonarr fetch below (default None is safe —
        # getattr(media_item, field, None) is the snapshot contract in worker.py)
        title=None,
        tvdb_id=None,
        tmdb_id=None,
        season_number=None,
        arr_metadata=None,
    )

    # ── Sonarr enrichment (fail-soft) ────────────────────────────────────────
    # Fetch series record for title/tvdb_id/arr_metadata (the register/genre signal).
    # Uses asyncio.to_thread (Phase-13 convention) so the blocking pyarr call does not
    # hold the event loop.  Any failure (PyarrError, settings not configured, etc.)
    # is caught and logged; the minimal media_item above is used instead.
    if kind != "movie" and arr_series_id is not None:
        from trezarr.config import TrezarrSettings  # noqa: PLC0415
        settings: TrezarrSettings = getattr(request.app.state, "settings", None) or TrezarrSettings()
        if settings.sonarr_enabled:
            try:
                from trezarr.arr.sonarr import build_sonarr_client, _normalize_arr_host  # noqa: PLC0415
                client = build_sonarr_client(settings)
                series_raw = await asyncio.to_thread(client.series.get, arr_series_id)
                # pyarr may return a list or dict for a single-id fetch
                if isinstance(series_raw, list):
                    series_raw = series_raw[0] if series_raw else {}
                if isinstance(series_raw, dict) and series_raw:
                    media_item_ns.title = series_raw.get("title")
                    media_item_ns.tvdb_id = series_raw.get("tvdbId")
                    # arr_metadata mirrors the snapshot fields captured by discover_sonarr_items
                    media_item_ns.arr_metadata = {
                        "genres": series_raw.get("genres"),
                        "overview": series_raw.get("overview"),
                        "year": series_raw.get("year"),
                        "network": series_raw.get("network"),
                        "runtime": series_raw.get("runtime"),
                    }
            except Exception:  # noqa: BLE001
                # Fail-soft: log without host/credentials, proceed with minimal media_item
                display = _normalize_arr_host(settings.sonarr_host) if settings.sonarr_enabled else "sonarr"
                logger.warning(
                    "post_translate: Sonarr enrichment failed for series_id=%s at %s "
                    "(proceeding with minimal media_item — Bible-aware still runs with safe-default register)",
                    arr_series_id,
                    display,
                )

    from trezarr.web.worker import enqueue_job  # noqa: PLC0415

    enqueued: bool = await enqueue_job(
        session_factory=session_factory,
        source_path=source_path,
        series_id=arr_series_id,
        trigger="manual",
        media_item=media_item_ns,
    )

    return JSONResponse({"enqueued": enqueued, "source_path": source_path})
