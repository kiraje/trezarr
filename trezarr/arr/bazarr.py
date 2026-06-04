"""Bazarr inventory client (INTG-02, D-103/D-104/D-105).

Design decisions honoured:
  D-103  httpx-based client (NOT pyarr); BazarrError mirrors DiscoveryError.
         bazarr_api_key resolved via SecretStr.get_secret_value() at boundary only.
  D-104  Bazarr is the inventory authority; filesystem is the byte source and
         graceful fallback. When bazarr_enabled=False or Bazarr unreachable,
         degrade to existing find_source_sub filesystem glob. This client raises
         BazarrError on failure; the caller decides whether to degrade.
  D-105  Bazarr-reported paths optionally reconciled via apply_path_mapping.
         If path_mappings are provided to the client constructor, every
         SubtitleEntry.path is mapped before it is returned to the caller.

Threat mitigations:
  T-10-02  BazarrError messages use _normalize_arr_host(self._host) — the api_key
           is NEVER included in error messages or logs (WR-01).
  T-10-04  bazarr_host flows through _normalize_arr_host (the SSRF choke-point).

Authentication: Bazarr authenticates via X-API-KEY header (case-insensitive HTTP
header; Bazarr reads request.headers["X-API-KEY"] — confirmed against Bazarr source).

Pure-read guarantee: only GET /api/episodes and GET /api/movies are called.
No download, search, or provider endpoints are ever invoked (INTG-02).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

import httpx

from trezarr.arr import _normalize_arr_host
from trezarr.paths import PathMapping, apply_path_mapping

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = ["BazarrError", "BazarrClient", "SubtitleEntry", "BazarrInventoryItem"]


class BazarrError(Exception):
    """Raised when a Bazarr inventory call fails (mirrors DiscoveryError).

    Messages NEVER include the API key — only the display_host from
    _normalize_arr_host() (T-10-02 / WR-01).
    """


@dataclass
class SubtitleEntry:
    """One existing subtitle returned by Bazarr inventory.

    Attributes:
        code2:  2-letter ISO-639-1 code (e.g. "ko", "en") — Bazarr always supplies this.
        code3:  3-letter ISO-639-2 code (e.g. "kor", "eng").
        path:   Local-side subtitle path after apply_path_mapping (D-105). Callers
                must NOT assume this path exists — validate with Path(path).exists()
                and the INTG-03 traversal guard before any filesystem use.
        forced: True if this is a forced subtitle track.
        hi:     True if this is a hearing-impaired subtitle track.
    """

    code2: str
    code3: str
    path: str
    forced: bool = False
    hi: bool = False


@dataclass
class BazarrInventoryItem:
    """Per-episode/movie Bazarr subtitle inventory.

    Attributes:
        arr_id:    sonarrEpisodeId or radarrId — the *arr internal item ID.
        path:      Media file path (Bazarr's container namespace, before mapping).
        subtitles: List of subtitle entries already known to Bazarr for this item.
    """

    arr_id: int
    path: str
    subtitles: list[SubtitleEntry] = field(default_factory=list)


class BazarrClient:
    """httpx-based Bazarr inventory client (D-103).

    Supports two construction modes:
      1. From settings (production): BazarrClient.from_settings(settings)
      2. Direct (test-friendly): BazarrClient(base_url=..., api_key=..., path_mappings=...)

    The direct mode accepts path_mappings as a list of (remote, local) tuples for
    test convenience; in production, PathMapping objects from TrezarrSettings are used.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        path_mappings: Sequence[tuple[str, str] | PathMapping] | None = None,
    ) -> None:
        """Initialise BazarrClient.

        Args:
            base_url:      Full base URL of the Bazarr service, e.g. "http://bazarr.local:6767".
            api_key:       Bazarr API key (plain string — caller resolves SecretStr at boundary).
            path_mappings: Optional list of (remote, local) tuples or PathMapping objects (D-105).
                           If provided, every subtitle path from Bazarr is mapped via
                           apply_path_mapping before being returned. None = passthrough.
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        # Extract just the host for WR-01 error redaction.
        # base_url is already normalized by the caller; we parse it for display.
        try:
            from urllib.parse import urlparse  # noqa: PLC0415
            parsed = urlparse(base_url)
            self._host = parsed.hostname or base_url
        except Exception:  # noqa: BLE001
            self._host = base_url

        # Normalize path_mappings to list[PathMapping] for apply_path_mapping compat.
        self._path_mappings: list[PathMapping] = []
        if path_mappings:
            for pm in path_mappings:
                if isinstance(pm, PathMapping):
                    self._path_mappings.append(pm)
                else:
                    # Tuple (remote, local)
                    remote, local = pm
                    self._path_mappings.append(PathMapping(remote=remote, local=local))

    @classmethod
    def from_settings(cls, settings: object) -> "BazarrClient":
        """Construct from TrezarrSettings (production path, D-103 D-11).

        The API key is resolved via SecretStr.get_secret_value() HERE and ONLY
        HERE — never stored as SecretStr, never included in error messages (D-11).
        The host is routed through _normalize_arr_host (T-10-04 SSRF choke-point).

        Args:
            settings: TrezarrSettings instance.

        Returns:
            A configured BazarrClient.
        """
        host = _normalize_arr_host(settings.bazarr_host)  # type: ignore[attr-defined]
        base_url = f"http://{host}:{settings.bazarr_port}"  # type: ignore[attr-defined]
        api_key = settings.bazarr_api_key.get_secret_value()  # type: ignore[attr-defined]  # D-11
        return cls(
            base_url=base_url,
            api_key=api_key,
            path_mappings=list(settings.path_mappings),  # type: ignore[attr-defined]
        )

    async def fetch_episodes(self, series_id: int) -> list[SubtitleEntry]:
        """GET /api/episodes?seriesid=<sonarr_series_id> — pure read (INTG-02).

        Returns a flat list of SubtitleEntry objects across all episodes of the series.
        Paths are mapped via apply_path_mapping if path_mappings were provided (D-105).

        Args:
            series_id: Sonarr series ID.

        Returns:
            List of SubtitleEntry objects. Empty list if Bazarr has no episodes.

        Raises:
            BazarrError: on HTTP 4xx/5xx or transport error. Message uses display_host
                         only — never the API key (T-10-02 / WR-01).
        """
        url = f"{self._base_url}/api/episodes"
        display_host = _normalize_arr_host(self._host)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    url,
                    params={"seriesid": series_id},
                    headers={"X-API-KEY": self._api_key},
                )
            r.raise_for_status()
            data = r.json().get("data", [])
            entries: list[SubtitleEntry] = []
            for ep in data:
                for sub in ep.get("subtitles", []):
                    entries.append(self._parse_subtitle_entry(sub))
            return entries
        except httpx.HTTPStatusError as exc:
            raise BazarrError(
                f"Bazarr inventory HTTP {exc.response.status_code} at {display_host}"
            ) from exc
        except httpx.RequestError as exc:
            raise BazarrError(
                f"Bazarr inventory fetch failed at {display_host}: "
                f"{type(exc).__name__}"
            ) from exc

    async def fetch_movies(self, radarr_movie_id: int | None = None) -> list[SubtitleEntry]:
        """GET /api/movies — pure read (INTG-02).

        Returns a flat list of SubtitleEntry objects. Paths are mapped via
        apply_path_mapping if path_mappings were provided (D-105).

        Args:
            radarr_movie_id: Optional Radarr movie ID to filter results.

        Returns:
            List of SubtitleEntry objects.

        Raises:
            BazarrError: on HTTP 4xx/5xx or transport error.
        """
        url = f"{self._base_url}/api/movies"
        display_host = _normalize_arr_host(self._host)
        params: dict[str, object] = {}
        if radarr_movie_id is not None:
            params["radarrid"] = radarr_movie_id
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    url,
                    params=params if params else None,
                    headers={"X-API-KEY": self._api_key},
                )
            r.raise_for_status()
            data = r.json().get("data", [])
            entries: list[SubtitleEntry] = []
            for movie in data:
                for sub in movie.get("subtitles", []):
                    entries.append(self._parse_subtitle_entry(sub))
            return entries
        except httpx.HTTPStatusError as exc:
            raise BazarrError(
                f"Bazarr inventory HTTP {exc.response.status_code} at {display_host}"
            ) from exc
        except httpx.RequestError as exc:
            raise BazarrError(
                f"Bazarr inventory fetch failed at {display_host}: "
                f"{type(exc).__name__}"
            ) from exc

    def _parse_subtitle_entry(self, sub: dict) -> SubtitleEntry:
        """Parse one subtitle dict from the Bazarr inventory response.

        Args:
            sub: A dict with keys code2, code3, path, forced, hi.

        Returns:
            SubtitleEntry with the path optionally mapped via apply_path_mapping (D-105).
        """
        raw_path = sub.get("path", "")
        if self._path_mappings and raw_path:
            mapped = apply_path_mapping(raw_path, self._path_mappings)
            mapped_path = str(mapped)
        else:
            mapped_path = raw_path
        return SubtitleEntry(
            code2=sub.get("code2", ""),
            code3=sub.get("code3", ""),
            path=mapped_path,
            forced=bool(sub.get("forced", False)),
            hi=bool(sub.get("hi", False)),
        )

    def _parse_inventory_item(self, item: dict) -> BazarrInventoryItem:
        """Parse one episode/movie dict into a BazarrInventoryItem.

        The arr_id is sonarrEpisodeId or radarrId (whichever is present).

        Args:
            item: A dict from Bazarr's /api/episodes or /api/movies response.

        Returns:
            BazarrInventoryItem with subtitles mapped via apply_path_mapping (D-105).
        """
        arr_id = item.get("sonarrEpisodeId") or item.get("radarrId") or 0
        path = item.get("path", "")
        subtitles = [self._parse_subtitle_entry(sub) for sub in item.get("subtitles", [])]
        return BazarrInventoryItem(arr_id=arr_id, path=path, subtitles=subtitles)

    async def _fetch_inventory_data(self, url: str, id_key: str, id_value: int) -> list:
        """GET an inventory endpoint's ``data`` list, with a param-form fallback (W3).

        Tries the bracketed ``<id_key>[]`` query form first (confirmed working on
        the reference Bazarr instance), then falls back to the plain ``<id_key>``
        form if the bracketed one returns nothing. The fallback only fires on an
        empty result, so an item that genuinely has subtitles never incurs a
        second request; an item that genuinely has none costs one extra request.

        Args:
            url:      Full endpoint URL.
            id_key:   Base query key ("seriesid" or "radarrid").
            id_value: The Sonarr/Radarr id.

        Returns:
            The ``data`` list from whichever param form returned content.

        Raises:
            BazarrError: on HTTP error or transport failure.
        """
        display_host = _normalize_arr_host(self._host)
        headers = {"X-API-KEY": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url, params=[(f"{id_key}[]", id_value)], headers=headers)
                r.raise_for_status()
                data = r.json().get("data", [])
                if not data:
                    # Defensive fallback for Bazarr builds that expect the plain key.
                    r = await client.get(url, params=[(id_key, id_value)], headers=headers)
                    r.raise_for_status()
                    data = r.json().get("data", [])
                return data
        except httpx.HTTPStatusError as exc:
            raise BazarrError(
                f"Bazarr inventory HTTP {exc.response.status_code} at {display_host}"
            ) from exc
        except httpx.RequestError as exc:
            raise BazarrError(
                f"Bazarr inventory fetch failed at {display_host}: "
                f"{type(exc).__name__}"
            ) from exc
        except ValueError as exc:
            # json.JSONDecodeError (a ValueError) on a malformed 200 body — wrap it
            # so a non-JSON response surfaces as BazarrError (fail-soft upstream),
            # never an unhandled crash. Message exposes only the redacted host.
            raise BazarrError(
                f"Bazarr inventory returned a non-JSON body at {display_host}"
            ) from exc

    async def fetch_episode_inventory(self, sonarr_series_id: int) -> list[BazarrInventoryItem]:
        """GET /api/episodes?seriesid=N — returns full BazarrInventoryItem list.

        Use this when you need per-episode structure (arr_id, media path, subtitles).
        Use fetch_episodes() when you only need the flat SubtitleEntry list.

        Tries the ``seriesid[]`` query form, falling back to plain ``seriesid``
        when the bracketed form returns nothing (W3 — param form not guaranteed
        across Bazarr builds).

        Args:
            sonarr_series_id: Sonarr series ID.

        Returns:
            List of BazarrInventoryItem objects.

        Raises:
            BazarrError: on HTTP error or transport failure.
        """
        data = await self._fetch_inventory_data(
            f"{self._base_url}/api/episodes", "seriesid", sonarr_series_id
        )
        return [self._parse_inventory_item(ep) for ep in data]

    async def fetch_movie_inventory(self, radarr_movie_id: int) -> list[BazarrInventoryItem]:
        """GET /api/movies?radarrid=N — returns full BazarrInventoryItem list.

        Tries the ``radarrid[]`` query form, falling back to plain ``radarrid``
        when the bracketed form returns nothing (W3).

        Args:
            radarr_movie_id: Radarr movie ID.

        Returns:
            List of BazarrInventoryItem objects.

        Raises:
            BazarrError: on HTTP error or transport failure.
        """
        data = await self._fetch_inventory_data(
            f"{self._base_url}/api/movies", "radarrid", radarr_movie_id
        )
        return [self._parse_inventory_item(m) for m in data]
