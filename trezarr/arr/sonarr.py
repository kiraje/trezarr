"""Sonarr *arr API discovery client.

Design decisions honoured:
  D-22  Discover via pyarr 6.x (composition API: `from pyarr import Sonarr`, NOT SonarrAPI).
        X-Api-Key auth (pyarr injects it). API for knowledge — never scan disk to discover.
  D-23  Path mapping applied to every API-returned path before filesystem use.
  D-29  apply_path_mapping is the choke-point; assert_within_media_roots runs at write time
        in cli.py / scan layer.
  D-30  Per-service resilience: pyarr's PyarrError family is caught at the discovery
        boundary and re-raised as DiscoveryError with host/port context so cli.py can
        choose to continue with the other *arr service.
  D-35  arr_metadata snapshot fields appended to MediaItem (genres, overview, year,
        network, runtime, arr_kind, tvdb_id, tmdb_id) — captured at discovery so
        Phase 5 never re-fetches arr APIs.

Notable pyarr 6.x specifics:
  - `api_ver="v3"` is passed explicitly to skip pyarr's auto-detect `GET /api` round trip.
    Sonarr's stable API is v3 and the auto-detect call complicates testing (the test
    stubs only mock the typed endpoints, not the version probe).
  - `tls=False` is hardcoded for Phase 3 (HTTP to local *arr); HTTPS support is Phase 7.
  - pyarr wraps httpx errors in its own PyarrError hierarchy (PyarrConnectionError for
    transport, PyarrUnauthorizedError for 401, etc.) — we catch the PyarrError parent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from pyarr import Sonarr
from pyarr.exceptions import PyarrError

from trezarr.arr import DiscoveryError, _normalize_arr_host
from trezarr.paths import apply_path_mapping

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)

# Re-export _normalize_arr_host at module level so tests can patch/inspect it via
# `trezarr.arr.sonarr._normalize_arr_host` (the canonical helper lives in trezarr.arr).
__all__ = [
    "MediaItem",
    "build_sonarr_client",
    "discover_sonarr_items",
    "_normalize_arr_host",
]


@dataclass
class MediaItem:
    """A single media item discovered from an *arr API, after path-mapping.

    Per 03-REVIEWS.md LOW #17: the title field is named ``title`` (NOT
    ``series_title``) because it carries both episode and movie titles —
    ``series_title`` would be misleading for the Radarr movie case.

    Attributes:
        local_path:    The resolved local filesystem path to the video file
                       (after apply_path_mapping). NOT the directory.
        title:         Display title for logging (series title for episodes,
                       movie title for movies).
        source_type:   "episode" or "movie" — the *arr that produced this item.
        series_id:     The *arr internal ID of the parent series (Sonarr) or the
                       movie itself (Radarr). Useful for downstream lookups.
        season_number: Sonarr season number; None for Radarr movies.

        # ── Phase 4: arr_metadata snapshot fields (D-33, D-35) ──
        arr_kind:  Source *arr service: "sonarr" or "radarr" (D-33). None if
                   the item was not produced by a Phase-4 discovery call.
        tvdb_id:   TVDB ID captured at discovery time (D-33, denormalized).
                   Sonarr provides tvdbId; some Radarr movies also carry it.
                   None for Radarr movies that don't expose tvdbId.
        tmdb_id:   TMDB ID captured at discovery time (D-33, denormalized).
                   Radarr provides tmdbId; Sonarr does not. None for Sonarr items.
        genres:    List of genre strings from the *arr payload, or None if absent.
        overview:  Series/movie overview text from the *arr payload, or None.
        year:      Premiere/release year from the *arr payload, or None.
        network:   Broadcast network from the Sonarr payload, or None for movies.
        runtime:   Episode/movie runtime in minutes from the *arr payload, or None.
    """

    local_path: Path
    title: str
    source_type: str
    series_id: int | None = None
    season_number: int | None = None

    # ── Phase 4: arr_metadata snapshot fields (D-33, D-35) ──
    arr_kind: str | None = None        # "sonarr" | "radarr"
    tvdb_id: int | None = None         # D-33: denormalized; captured at series creation
    tmdb_id: int | None = None         # D-33: denormalized; Radarr only
    genres: list[str] | None = None    # D-35: genre list from arr payload
    overview: str | None = None        # D-35: series/movie overview text
    year: int | None = None            # D-35: premiere/release year
    network: str | None = None         # D-35: broadcast network (Sonarr only)
    runtime: int | None = None         # D-35: runtime in minutes
    # ── Phase 10: original_language capture (D-108) ──
    original_language: str | None = None  # e.g. "Korean", "English" — from arr originalLanguage.name


def build_sonarr_client(settings: "TrezarrSettings") -> Sonarr:
    """Construct a pyarr Sonarr client from TrezarrSettings.

    The API key is resolved via ``SecretStr.get_secret_value()`` here and ONLY here —
    the resolved string is passed straight into the Sonarr constructor and never
    retained on this object or any MediaItem (per D-11 SecretStr discipline).

    ``api_ver="v3"`` is set explicitly to skip pyarr's auto-detect `GET /api` probe;
    Sonarr's stable API version is v3 in the supported deployment window.

    Args:
        settings: TrezarrSettings carrying sonarr_host, sonarr_port, sonarr_api_key.

    Returns:
        A configured Sonarr client (does not perform any HTTP call yet).
    """
    host = _normalize_arr_host(settings.sonarr_host)
    return Sonarr(
        host=host,
        api_key=settings.sonarr_api_key.get_secret_value(),
        port=settings.sonarr_port,
        tls=False,
        api_ver="v3",
    )


def discover_sonarr_items(settings: "TrezarrSettings") -> list[MediaItem]:
    """Discover all monitored Sonarr episode files as MediaItems (D-22, D-23).

    Iterates every monitored series, fetches its episode files via the Sonarr API,
    applies path mapping to each returned path, and returns the union as a flat list.

    Behaviour contract:
      - settings.sonarr_enabled is False  → return [] immediately; do not build a client
      - Un-monitored series                → skipped (no episode_file.get() called)
      - ep_file with no path               → log warning, skip
      - HTTP/transport failure (pyarr)     → re-raise as DiscoveryError with host:port context

    Args:
        settings: TrezarrSettings. ``sonarr_enabled`` gates the call entirely.

    Returns:
        Flat list of MediaItem(local_path, title, source_type="episode", series_id, season_number).
        Each ``local_path`` is the output of apply_path_mapping over the raw ``ep_file["path"]``.

    Raises:
        DiscoveryError: when the underlying pyarr/httpx call fails for any reason
                        the caller cannot itself recover from at this layer (4xx, 5xx,
                        connection refused, timeout). The message includes
                        sonarr_host:sonarr_port so the operator can act on it.

    Pitfalls honoured:
      - Pitfall 1: `from pyarr import Sonarr` (NOT SonarrAPI — 5.x is gone).
      - Anti-pattern: never glob disk; "API for knowledge" (D-22).
    """
    if not settings.sonarr_enabled:
        logger.info("Sonarr discovery disabled (sonarr_enabled=False); returning empty item list")
        return []

    try:
        client = build_sonarr_client(settings)
        series_list = client.series.get()
        items: list[MediaItem] = []
        # Phase 7: replace with asyncio.gather + AsyncSonarr for concurrent series iteration.
        # For Phase 3's one-shot CLI, sequential per-series episode_file.get() is acceptable
        # but not optimal at 200+ series scale (03-RESEARCH.md Pitfall 6).
        for series in series_list:
            if not series.get("monitored", False):
                continue
            ep_files = client.episode_file.get(series_id=series["id"])
            # episode_file.get can return a single dict if there's only one matching record;
            # the test stubs (and the typical case) return a list — normalise defensively.
            if isinstance(ep_files, dict):
                ep_files = [ep_files]
            for ep_file in ep_files:
                raw_path = ep_file.get("path")
                if raw_path is None:
                    logger.warning(
                        "Sonarr episode_file id=%s for series=%s has no path; skipping",
                        ep_file.get("id"),
                        series.get("title"),
                    )
                    continue
                local_path = apply_path_mapping(raw_path, settings.path_mappings)
                items.append(
                    MediaItem(
                        local_path=local_path,
                        title=series["title"],
                        source_type="episode",
                        series_id=series["id"],
                        season_number=ep_file.get("seasonNumber"),
                        # ── Phase 4: arr_metadata snapshot fields (D-33, D-35) ──
                        arr_kind="sonarr",
                        tvdb_id=series.get("tvdbId"),    # camelCase JSON key from Sonarr API
                        genres=series.get("genres"),
                        overview=series.get("overview"),
                        year=series.get("year"),
                        network=series.get("network"),
                        runtime=series.get("runtime"),
                        # Phase 10 — D-108: originalLanguage.name for SRC-02 relational-richness ranking
                        original_language=series.get("originalLanguage", {}).get("name"),
                        # tmdb_id intentionally omitted for Sonarr (defaults to None — D-33)
                    )
                )
        return items
    except PyarrError as exc:
        # pyarr wraps both 4xx/5xx (PyarrUnauthorizedError, PyarrServerError, …) and
        # underlying httpx transport errors (PyarrConnectionError) in its own hierarchy.
        # Catching the PyarrError parent gives us the broadest typed boundary.
        #
        # WR-01: route the host through _normalize_arr_host before logging /
        # raising so any `user:password@host` userinfo embedded in the raw
        # sonarr_host setting is stripped — otherwise the credential lands in
        # log files and in the cli summary's partial-discovery-failures suffix.
        display_host = _normalize_arr_host(settings.sonarr_host)
        logger.error(
            "Sonarr discovery failed at %s:%d — %s: %s",
            display_host,
            settings.sonarr_port,
            type(exc).__name__,
            exc,
        )
        raise DiscoveryError(
            f"Sonarr discovery failed at {display_host}:{settings.sonarr_port}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
