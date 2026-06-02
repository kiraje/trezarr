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


def test_normalize_arr_host_bare_with_port():
    """A bare host:port form (no scheme) strips the trailing port (WR-02).

    docker-compose service-name conventions like `sonarr:8989` previously
    survived intact and produced a malformed pyarr URL of the form
    `http://sonarr:8989:8989/api/v3/...` when pyarr re-attached its `port=` kwarg.
    """
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    _normalize_arr_host = sonarr_mod._normalize_arr_host

    assert _normalize_arr_host("sonarr.lan:8989") == "sonarr.lan"
    assert _normalize_arr_host("sonarr:8989") == "sonarr"


def test_normalize_arr_host_strips_userinfo(caplog):
    """A URL with embedded user:password@host MUST have the credential stripped (WR-01).

    Hosts pasted with userinfo (the user-experience footgun: copying a fully-
    qualified URL from a password manager into the host field) previously had
    the raw value echoed into error logs and into the cli summary's
    partial-discovery-failures suffix on the first 401 / connect-refused. The
    normalizer is the redaction choke-point; callers must route the host
    through it before any logging.
    """
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    _normalize_arr_host = sonarr_mod._normalize_arr_host

    out = _normalize_arr_host("http://admin:hunter2@sonarr.local:8989/api")
    assert out == "sonarr.local", f"Expected 'sonarr.local' (userinfo + port stripped), got {out!r}"
    assert "hunter2" not in out, "Credential must not survive normalization"
    assert "admin" not in out, "Username must not survive normalization"


def test_sonarr_discovery_error_log_redacts_userinfo_credentials(httpx_mock, caplog):
    """When Sonarr fails, the host in the error log and DiscoveryError message must NOT carry userinfo (WR-01)."""
    import logging

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
        # Userinfo embedded in the host setting — common when users paste a URL
        # from a password manager. _normalize_arr_host strips it for both pyarr
        # AND the log/error path.
        sonarr_host="http://admin:hunter2@192.168.1.100/api",
        sonarr_port=8989,
        sonarr_api_key="wrong-key",
        path_mappings=[],
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(DiscoveryError) as excinfo:
            discover_sonarr_items(settings)

    # The error message MUST NOT include the credentials.
    msg = str(excinfo.value)
    assert "hunter2" not in msg, f"DiscoveryError leaked password: {msg!r}"
    assert "admin" not in msg, f"DiscoveryError leaked username: {msg!r}"
    # And the error log records likewise must not contain the credentials.
    for rec in caplog.records:
        assert "hunter2" not in rec.getMessage(), f"Error log leaked password: {rec.getMessage()!r}"
        assert "admin" not in rec.getMessage(), f"Error log leaked username: {rec.getMessage()!r}"


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


# ──────────────────────────────────────────────────────────────────────────────
# D-108 Wave-0 stubs: original_language capture
#
# These are the AUTHORITATIVE D-108 coverage stubs (see 10-VALIDATION.md and
# 10-01-PLAN.md: no separate test_sonarr.py / test_radarr.py files are created).
#
# Sonarr and Radarr APIs include originalLanguage:{id, name} in series/movie
# objects. MediaItem must expose original_language for Phase-10 ranking to work.
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=False,
    raises=(AssertionError, AttributeError),
    reason="MediaItem.original_language field not yet added (D-108, Phase 10)",
)
def test_sonarr_captures_original_language(httpx_mock):
    """discover_sonarr_items captures originalLanguage.name → MediaItem.original_language (D-108).

    Sonarr v3 series objects include originalLanguage:{id:1, name:"Korean"} for
    East-Asian content. The D-108 original_language field on MediaItem enables
    Phase-10 ranking to prefer the native source language.
    """
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    discover_sonarr_items = sonarr_mod.discover_sonarr_items

    from trezarr.config import TrezarrSettings

    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        json=[
            {
                "id": 1,
                "title": "Crash Landing on You",
                "path": "/tv/CLOY",
                "monitored": True,
                "tvdbId": 200,
                "originalLanguage": {"id": 1, "name": "Korean"},
            },
        ],
    )
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/episodefile?seriesId=1",
        json=[
            {
                "id": 10,
                "seriesId": 1,
                "seasonNumber": 1,
                "path": "/tv/CLOY/Season 1/CLOY.S01E01.mkv",
                "relativePath": "Season 1/CLOY.S01E01.mkv",
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

    assert len(items) == 1, f"Expected 1 MediaItem, got {len(items)}"
    assert items[0].original_language == "Korean", (
        f"D-108: expected MediaItem.original_language == 'Korean', got {items[0].original_language!r}"
    )


@pytest.mark.xfail(
    strict=False,
    raises=(AssertionError, AttributeError),
    reason="MediaItem.original_language field not yet added (D-108, Phase 10)",
)
def test_radarr_captures_original_language(httpx_mock):
    """discover_radarr_items captures originalLanguage.name → MediaItem.original_language (D-108).

    Radarr v3 movie objects include originalLanguage:{id:1, name:"Korean"} for
    non-English films (e.g. Parasite). The D-108 field enables ranking to prefer
    the native source language.
    """
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
                "originalLanguage": {"id": 1, "name": "Korean"},
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

    assert len(items) == 1, f"Expected 1 MediaItem, got {len(items)}"
    assert items[0].original_language == "Korean", (
        f"D-108: expected MediaItem.original_language == 'Korean', got {items[0].original_language!r}"
    )
