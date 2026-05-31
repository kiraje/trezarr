"""Tests for Phase 3 *arr discovery (INTG-01 / D-22).

Imports from trezarr.arr.* are deferred inside each test function body via
pytest.importorskip so collection survives even if the production modules are
absent. Plan 03-03 landed the implementation; all stubs are now GREEN and the
previous Wave-0 RED-scaffolding markers (strict=False) have been removed.

Convention: pyarr 6.x is synchronous (`from pyarr import Sonarr, Radarr` — NOT
`SonarrAPI` / `RadarrAPI`), so these are sync `def` tests using the `httpx_mock`
fixture (from pytest-httpx). pyarr uses httpx internally; httpx_mock intercepts
at the transport layer.

Covers:
  INTG-01  Sonarr series + episode-file discovery via pyarr (D-22)
  INTG-01  Sonarr filters out un-monitored series
  INTG-01  Radarr movie + movieFile discovery via pyarr (D-22)
  INTG-01  Radarr skips movies with no movieFile (movieFileId == 0)
  03-REVIEWS.md MEDIUM #15 — host normalisation: bare IP / full URL with scheme / with port
  03-REVIEWS.md MEDIUM #10 — DiscoveryError raised on HTTP error (one *arr failure
                              is surfaced as a typed exception so the CLI can decide
                              whether to abort or continue with the other service)
"""
from __future__ import annotations

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Sonarr discovery (INTG-01 / D-22)
# ──────────────────────────────────────────────────────────────────────────────


def test_sonarr_discovers_monitored_series(httpx_mock):
    """discover_sonarr_items returns episode-level MediaItems for monitored series (INTG-01)."""
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    discover_sonarr_items = sonarr_mod.discover_sonarr_items

    from trezarr.config import TrezarrSettings

    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        json=[
            {"id": 1, "title": "Show A", "path": "/tv/Show A", "monitored": True, "tvdbId": 100},
        ],
    )
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/episodefile?seriesId=1",
        json=[
            {
                "id": 10,
                "seriesId": 1,
                "seasonNumber": 1,
                "path": "/tv/Show A/Season 1/Show.S01E01.mkv",
                "relativePath": "Season 1/Show.S01E01.mkv",
            },
        ],
    )

    settings = TrezarrSettings(
        sonarr_enabled=True,
        sonarr_host="192.168.1.100",
        sonarr_port=8989,
        sonarr_api_key="test-key",
        path_mappings=[],
    )

    items = discover_sonarr_items(settings)

    assert len(items) == 1, f"Expected 1 MediaItem for the one monitored episode, got {len(items)}"
    # Source path on disk is what gets used for sidecar discovery — must come from episodefile
    assert "Show.S01E01.mkv" in str(items[0].local_path)


def test_sonarr_filters_unmonitored(httpx_mock):
    """discover_sonarr_items skips series with monitored=False (INTG-01).

    Only the monitored series id=1 should be discovered; id=2 must be filtered
    out before episode_file.get() is even called for it.
    """
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    discover_sonarr_items = sonarr_mod.discover_sonarr_items

    from trezarr.config import TrezarrSettings

    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        json=[
            {"id": 1, "title": "Monitored Show", "path": "/tv/Monitored", "monitored": True, "tvdbId": 100},
            {"id": 2, "title": "Unmonitored Show", "path": "/tv/Unmonitored", "monitored": False, "tvdbId": 200},
        ],
    )
    # Only the monitored series should fetch episodefile
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/episodefile?seriesId=1",
        json=[
            {
                "id": 11,
                "seriesId": 1,
                "seasonNumber": 1,
                "path": "/tv/Monitored/Season 1/Monitored.S01E01.mkv",
                "relativePath": "Season 1/Monitored.S01E01.mkv",
            },
        ],
    )

    settings = TrezarrSettings(
        sonarr_enabled=True,
        sonarr_host="192.168.1.100",
        sonarr_port=8989,
        sonarr_api_key="test-key",
        path_mappings=[],
    )

    items = discover_sonarr_items(settings)

    # All items must come from the monitored series
    for item in items:
        assert "Monitored" in str(item.local_path) and "Unmonitored" not in str(item.local_path), (
            f"Discovered an item from an un-monitored series: {item.local_path}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Radarr discovery (INTG-01 / D-22, Pitfall 2)
# ──────────────────────────────────────────────────────────────────────────────


def test_radarr_discovers_movies(httpx_mock):
    """discover_radarr_items returns MediaItems with movieFile.path (Pitfall 2)."""
    radarr_mod = pytest.importorskip("trezarr.arr.radarr")
    discover_radarr_items = radarr_mod.discover_radarr_items

    from trezarr.config import TrezarrSettings

    httpx_mock.add_response(
        url="http://192.168.1.100:7878/api/v3/movie",
        json=[
            {
                "id": 1,
                "title": "Parasite",
                "path": "/movies/Parasite (2019)",
                "monitored": True,
                "movieFileId": 42,
                "movieFile": {
                    "id": 42,
                    "movieId": 1,
                    "path": "/movies/Parasite (2019)/Parasite.mkv",
                    "relativePath": "Parasite.mkv",
                },
            },
        ],
    )

    settings = TrezarrSettings(
        radarr_enabled=True,
        radarr_host="192.168.1.100",
        radarr_port=7878,
        radarr_api_key="test-key",
        path_mappings=[],
    )

    items = discover_radarr_items(settings)

    assert len(items) == 1, f"Expected 1 MediaItem for the monitored movie, got {len(items)}"
    # Must be the movieFile.path, NOT the movie.path directory (Pitfall 2)
    assert str(items[0].local_path).endswith("Parasite.mkv"), (
        f"Expected movieFile.path (Parasite.mkv), got {items[0].local_path}"
    )


def test_radarr_skips_missing_file(httpx_mock):
    """A movie with movieFileId=0 / movieFile=None is skipped, not yielded as eligible (Pitfall 2)."""
    radarr_mod = pytest.importorskip("trezarr.arr.radarr")
    discover_radarr_items = radarr_mod.discover_radarr_items

    from trezarr.config import TrezarrSettings

    httpx_mock.add_response(
        url="http://192.168.1.100:7878/api/v3/movie",
        json=[
            {
                "id": 1,
                "title": "Has File",
                "path": "/movies/HasFile (2020)",
                "monitored": True,
                "movieFileId": 50,
                "movieFile": {
                    "id": 50,
                    "movieId": 1,
                    "path": "/movies/HasFile (2020)/HasFile.mkv",
                    "relativePath": "HasFile.mkv",
                },
            },
            {
                "id": 2,
                "title": "No File Yet",
                "path": "/movies/NoFile (2021)",
                "monitored": True,
                "movieFileId": 0,
                # movieFile absent or None
            },
        ],
    )

    settings = TrezarrSettings(
        radarr_enabled=True,
        radarr_host="192.168.1.100",
        radarr_port=7878,
        radarr_api_key="test-key",
        path_mappings=[],
    )

    items = discover_radarr_items(settings)

    # Only the movie with a movieFile is discovered
    assert len(items) == 1, f"Expected only 1 movie discovered (the one with a movieFile), got {len(items)}"
    assert "HasFile" in str(items[0].local_path)


# ──────────────────────────────────────────────────────────────────────────────
# Host normalisation — 03-REVIEWS.md MEDIUM #15 / 03-03 MEDIUM concern
#
# Users may enter `sonarr_host` as bare IP ("192.168.1.10"), full URL with
# scheme ("http://sonarr.example"), or full URL with port
# ("http://192.168.1.10:8989"). pyarr's `Sonarr(host=..., port=..., tls=...)`
# constructor wants a bare host. _normalize_arr_host() is the helper that strips
# scheme / port / paths to produce the bare host string.
# ──────────────────────────────────────────────────────────────────────────────


def test_normalize_arr_host_bare_ip():
    """A bare IP / hostname passes through unchanged."""
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    _normalize_arr_host = sonarr_mod._normalize_arr_host

    assert _normalize_arr_host("192.168.1.10") == "192.168.1.10"


def test_normalize_arr_host_full_url_with_scheme():
    """A full URL with scheme has the scheme stripped."""
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    _normalize_arr_host = sonarr_mod._normalize_arr_host

    assert _normalize_arr_host("https://sonarr.example/api") == "sonarr.example"


def test_normalize_arr_host_full_url_with_port():
    """A full URL with scheme and port strips both — port is passed via the `port=` kwarg, not via host."""
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    _normalize_arr_host = sonarr_mod._normalize_arr_host

    assert _normalize_arr_host("http://192.168.1.10:8989") == "192.168.1.10"


# ──────────────────────────────────────────────────────────────────────────────
# DiscoveryError — typed exception so CLI can choose to continue past one *arr's
# failure rather than crash the run (03-REVIEWS.md MEDIUM #10)
# ──────────────────────────────────────────────────────────────────────────────


def test_discovery_error_raised_on_http_error(httpx_mock):
    """HTTP 401 from Sonarr raises trezarr.arr.DiscoveryError (typed exception, INTG-01).

    Per 03-REVIEWS.md MEDIUM #10: discovery failures need a typed exception so the
    CLI can decide whether one *arr service failing aborts the whole run or just
    zeros that source while the other service continues.
    """
    arr_pkg = pytest.importorskip("trezarr.arr")
    DiscoveryError = arr_pkg.DiscoveryError
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    discover_sonarr_items = sonarr_mod.discover_sonarr_items

    from trezarr.config import TrezarrSettings

    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        status_code=401,
        json={"error": "Unauthorized"},
    )

    settings = TrezarrSettings(
        sonarr_enabled=True,
        sonarr_host="192.168.1.100",
        sonarr_port=8989,
        sonarr_api_key="wrong-key",
        path_mappings=[],
    )

    with pytest.raises(DiscoveryError):
        discover_sonarr_items(settings)
