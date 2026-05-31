"""Radarr *arr API discovery client.

Design decisions honoured:
  D-22  Discover via pyarr 6.x (composition API: `from pyarr import Radarr`, NOT RadarrAPI).
        X-Api-Key auth (pyarr injects it). API for knowledge — never scan disk to discover.
  D-23  Path mapping applied to every API-returned path (movieFile.path) before filesystem use.
  D-29  apply_path_mapping is the choke-point; assert_within_media_roots runs at write time.
  D-30  Per-service resilience: pyarr's PyarrError family is caught at the discovery
        boundary and re-raised as DiscoveryError with host/port context so cli.py can
        choose to continue with the other *arr service.

Critical pitfalls honoured:
  - Pitfall 1: `from pyarr import Radarr` (NOT RadarrAPI — pyarr 5.x is gone).
  - Pitfall 2: `movie["path"]` is the movie DIRECTORY (e.g. `/movies/Parasite (2019)`);
              the actual video file is `movie["movieFile"]["path"]`. The subtitle
              must sit next to the video, not in the directory root. We NEVER use
              movie["path"] for a video path.
  - Open Question 1: If `movie.get("movieFile")` is None/absent (some pyarr/Radarr
              versions return the movie list without the inline movieFile embed),
              we fall back to a separate `client.movie_file.get(movie_id=X)` call.
              If THAT is also empty, we log a warning and skip the movie.

Shared MediaItem dataclass is imported from trezarr.arr.sonarr (defined once,
per 03-REVIEWS.md LOW #17 — title field carries both series and movie titles).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pyarr import Radarr
from pyarr.exceptions import PyarrError

from trezarr.arr import DiscoveryError, _normalize_arr_host
from trezarr.arr.sonarr import MediaItem
from trezarr.paths import apply_path_mapping

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)

__all__ = ["build_radarr_client", "discover_radarr_items"]


def build_radarr_client(settings: "TrezarrSettings") -> Radarr:
    """Construct a pyarr Radarr client from TrezarrSettings.

    The API key is resolved via ``SecretStr.get_secret_value()`` here and ONLY here —
    the resolved string is passed straight into the Radarr constructor and never
    retained on this object or any MediaItem (per D-11 SecretStr discipline).

    ``api_ver="v3"`` is set explicitly to skip pyarr's auto-detect `GET /api` probe;
    Radarr's stable API version is v3 in the supported deployment window.

    Args:
        settings: TrezarrSettings carrying radarr_host, radarr_port, radarr_api_key.

    Returns:
        A configured Radarr client (does not perform any HTTP call yet).
    """
    host = _normalize_arr_host(settings.radarr_host)
    return Radarr(
        host=host,
        api_key=settings.radarr_api_key.get_secret_value(),
        port=settings.radarr_port,
        tls=False,
        api_ver="v3",
    )


def discover_radarr_items(settings: "TrezarrSettings") -> list[MediaItem]:
    """Discover all monitored Radarr movies with a video file as MediaItems (D-22, D-23).

    Iterates every monitored movie, extracts the video file path from
    ``movie["movieFile"]["path"]`` (NOT ``movie["path"]`` — Pitfall 2), applies
    path mapping, and returns the union as a flat list.

    Behaviour contract:
      - settings.radarr_enabled is False               → return [] immediately; no client
      - Un-monitored movie                              → skipped
      - Movie with movieFileId == 0 and no movieFile    → skipped (no video file yet)
      - movieFile absent from inline movie response    → fallback via movie_file.get(movie_id=)
      - movie_file fallback also empty                  → log warning, skip
      - HTTP/transport failure (pyarr)                  → re-raise as DiscoveryError

    Args:
        settings: TrezarrSettings. ``radarr_enabled`` gates the call entirely.

    Returns:
        Flat list of MediaItem(local_path, title, source_type="movie", series_id=movie_id).
        Each ``local_path`` is the output of apply_path_mapping over the raw
        ``movieFile["path"]`` (the VIDEO file, not the movie directory).

    Raises:
        DiscoveryError: when the underlying pyarr/httpx call fails for any reason
                        the caller cannot itself recover from. The message includes
                        radarr_host:radarr_port for operator action.
    """
    if not settings.radarr_enabled:
        logger.info("Radarr discovery disabled (radarr_enabled=False); returning empty item list")
        return []

    try:
        client = build_radarr_client(settings)
        movies = client.movie.get()
        # Defensive: a single-record response may come back as dict; normalise to list.
        if isinstance(movies, dict):
            movies = [movies]
        items: list[MediaItem] = []
        for movie in movies:
            if not movie.get("monitored", False):
                continue
            # Skip movies with no associated video file at all.
            # movieFileId of 0 (or absent) is the Radarr "no file yet" sentinel.
            has_file_id = movie.get("movieFileId", 0) != 0
            has_inline_movie_file = movie.get("movieFile") is not None
            if not has_file_id and not has_inline_movie_file:
                # No file → nothing to translate. Common during initial library import.
                continue

            # Prefer the inline movieFile embed (typical response shape).
            movie_file = movie.get("movieFile")
            if movie_file is None:
                # Open Question 1 fallback — fetch the movie_file resource separately.
                # Some Radarr versions / queries return the movie list without the
                # inline embed; pyarr exposes movie_file.get(movie_id=...) for this.
                fallback = client.movie_file.get(movie_id=movie["id"])
                if isinstance(fallback, list):
                    movie_file = fallback[0] if fallback else None
                elif isinstance(fallback, dict):
                    movie_file = fallback
                else:
                    movie_file = None
            if movie_file is None:
                logger.warning(
                    "Radarr movie id=%s title=%r has movieFileId set but no movieFile "
                    "could be resolved (inline missing AND movie_file.get fallback empty); skipping",
                    movie.get("id"),
                    movie.get("title"),
                )
                continue

            raw_path = movie_file.get("path")
            if raw_path is None:
                logger.warning(
                    "Radarr movie id=%s title=%r has a movieFile record with no path; skipping",
                    movie.get("id"),
                    movie.get("title"),
                )
                continue

            # CRITICAL (Pitfall 2): raw_path here is the VIDEO FILE path
            # (movieFile.path), NOT the movie directory (movie["path"]). Subtitles
            # must sit next to the video, not in the directory root.
            local_path = apply_path_mapping(raw_path, settings.path_mappings)
            items.append(
                MediaItem(
                    local_path=local_path,
                    title=movie["title"],
                    source_type="movie",
                    series_id=movie["id"],
                    season_number=None,
                )
            )
        return items
    except PyarrError as exc:
        # pyarr wraps both 4xx/5xx and httpx transport errors in PyarrError —
        # catching the parent gives the broadest typed boundary so cli.py can
        # apply per-service resilience (D-30).
        logger.error(
            "Radarr discovery failed at %s:%d — %s: %s",
            settings.radarr_host,
            settings.radarr_port,
            type(exc).__name__,
            exc,
        )
        raise DiscoveryError(
            f"Radarr discovery failed at {settings.radarr_host}:{settings.radarr_port}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
