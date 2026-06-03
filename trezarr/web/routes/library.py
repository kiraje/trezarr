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


# ── GET /api/library ───────────────────────────────────────────────────────────

@router.get("/library")
async def get_library(request: Request) -> JSONResponse:
    """List Sonarr series and Radarr movies.

    Per-source errors are collected into the ``errors`` list; the endpoint
    always returns HTTP 200 so the UI can display partial results.
    """
    from trezarr.arr import DiscoveryError  # noqa: PLC0415
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
    if settings.sonarr_enabled:
        try:
            client = build_sonarr_client(settings)
            raw_series = client.series.get()
            if isinstance(raw_series, dict):
                raw_series = [raw_series]
            for s in raw_series:
                images = s.get("images") or []
                poster_url = images[0].get("remoteUrl") if images else None
                series_list.append({
                    "kind": "series",
                    "id": s.get("id"),
                    "title": s.get("title", ""),
                    "year": s.get("year"),
                    "monitored": s.get("monitored", False),
                    "poster_url": poster_url,
                })
        except (PyarrError, DiscoveryError, Exception) as exc:  # noqa: BLE001
            logger.warning("get_library: Sonarr error — %s", exc)
            series_list = []
            errors.append({"source": "sonarr", "error": str(exc)})

    # ── Radarr: list all movies + source-sub status ───────────────────────────
    if settings.radarr_enabled:
        try:
            client = build_radarr_client(settings)
            raw_movies = client.movie.get()
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
                else:
                    source_sub_found = False
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
                })
        except (PyarrError, DiscoveryError, Exception) as exc:  # noqa: BLE001
            logger.warning("get_library: Radarr error — %s", exc)
            movies_list = []
            errors.append({"source": "radarr", "error": str(exc)})

    return JSONResponse({"series": series_list, "movies": movies_list, "errors": errors})


# ── GET /api/library/series/{id}/episodes ─────────────────────────────────────

@router.get("/library/series/{series_id}/episodes")
async def get_series_episodes(series_id: int, request: Request) -> JSONResponse:
    """Return per-episode file rows for one Sonarr series.

    Status enum: ``translated`` | ``has_source`` | ``nothing``.
    """
    from trezarr.config import TrezarrSettings  # noqa: PLC0415

    settings: TrezarrSettings = getattr(request.app.state, "settings", None) or TrezarrSettings()

    if not settings.sonarr_enabled:
        return JSONResponse({"error": "sonarr_disabled"}, status_code=400)

    try:
        from trezarr.arr.sonarr import build_sonarr_client  # noqa: PLC0415
        from trezarr.discover.scan import find_source_sub  # noqa: PLC0415
        from trezarr.paths import apply_path_mapping  # noqa: PLC0415
        from pyarr.exceptions import PyarrError  # noqa: PLC0415

        client = build_sonarr_client(settings)
        ep_files = client.episode_file.get(series_id=series_id)
        # Normalise single-dict response (matches sonarr.py lines 173-179 pattern)
        if isinstance(ep_files, dict):
            ep_files = [ep_files]

        rows: list[dict] = []
        for ep_file in ep_files:
            raw_path: str = ep_file.get("path", "") or ""
            if not raw_path:
                continue

            local_path: Path = apply_path_mapping(raw_path, settings.path_mappings)
            source_sub_result = find_source_sub(local_path, settings.source_lang_priority)

            # Use Sonarr's authoritative seasonNumber + tolerant episode parse
            # (handles SxxExx and NxNN donghua naming); falls back gracefully.
            episode_key: str = _episode_key_from_file(ep_file, raw_path)

            # Determine status
            if source_sub_result is None:
                status = "nothing"
                source_path = None
                source_lang = None
            else:
                source_path = str(source_sub_result[0])
                source_lang = source_sub_result[1]
                # Check for existing vi sidecar
                vi_found = any(
                    (local_path.parent / (local_path.stem + ext)).exists()
                    for ext in (".vi.srt", ".vi.ass", ".vi.vtt")
                )
                status = "translated" if vi_found else "has_source"

            title: str = ep_file.get("sceneName") or ep_file.get("relativePath", "")

            rows.append({
                "episode_key": episode_key,
                "title": title,
                "local_path": str(local_path),
                "status": status,
                "source_path": source_path,
                "source_lang": source_lang,
            })

        return JSONResponse(rows)

    except (PyarrError, Exception) as exc:  # noqa: BLE001
        logger.error("get_series_episodes: error for series_id=%d — %s", series_id, exc)
        return JSONResponse({"error": str(exc)}, status_code=502)


# ── POST /api/translate ────────────────────────────────────────────────────────

@router.post("/translate")
async def post_translate(request: Request) -> JSONResponse:
    """Enqueue a single subtitle file for manual translation.

    Body (JSON): { kind, source_path, arr_series_id? }

    Returns 400 when source_path is absent or does not exist on disk.
    When media_roots is configured, validates path stays within allowed roots
    (T-l8g-01 path-traversal guard — mirrors cli.py ``if media_roots:`` guard).
    Returns { enqueued, source_path } on success.
    """
    body: dict = await request.json()

    source_path: str | None = body.get("source_path")
    if not source_path:
        return JSONResponse({"error": "source_path_required"}, status_code=400)

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

    from trezarr.web.worker import enqueue_job  # noqa: PLC0415

    enqueued: bool = await enqueue_job(
        session_factory=session_factory,
        source_path=source_path,
        series_id=arr_series_id,
        trigger="manual",
        media_item=None,
    )

    return JSONResponse({"enqueued": enqueued, "source_path": source_path})
