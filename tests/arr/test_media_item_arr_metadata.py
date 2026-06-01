"""Phase 4 arr_metadata snapshot tests for MediaItem extension (D-33, D-35).

These tests verify that MediaItem carries the Phase-4 arr_metadata fields
(arr_kind, tvdb_id, tmdb_id, genres, overview, year, network, runtime) and that
discover_sonarr_items / discover_radarr_items populate them from the pyarr payload.

Convention: pyarr 6.x is synchronous; these are sync `def` tests using the
httpx_mock fixture (from pytest-httpx). pyarr uses httpx internally; httpx_mock
intercepts at the transport layer.

Mirrors test pattern from tests/arr/test_arr_discovery.py.
"""
from __future__ import annotations


def test_sonarr_media_item_carries_arr_metadata_fields(httpx_mock):
    """discover_sonarr_items returns MediaItem with arr_kind='sonarr' and arr_metadata fields populated.

    Stubs the pyarr Sonarr.series.get() response to include tvdbId, genres, overview,
    year, network, runtime. Verifies the returned MediaItem carries all Phase-4 fields
    with correct values.

    Validates: D-35 arr_metadata snapshot fields; D-33 tvdb_id captured at discovery.
    """
    import pytest
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    discover_sonarr_items = sonarr_mod.discover_sonarr_items

    from trezarr.config import TrezarrSettings

    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        json=[
            {
                "id": 1,
                "title": "Show A",
                "path": "/tv/Show A",
                "monitored": True,
                "tvdbId": 12345,
                "genres": ["drama", "thriller"],
                "overview": "A gripping drama series.",
                "year": 2020,
                "network": "BBC",
                "runtime": 60,
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

    assert len(items) == 1
    item = items[0]
    assert item.arr_kind == "sonarr", f"Expected arr_kind='sonarr', got {item.arr_kind!r}"
    assert item.tvdb_id == 12345, f"Expected tvdb_id=12345, got {item.tvdb_id!r}"
    assert item.tmdb_id is None, f"Expected tmdb_id=None for Sonarr, got {item.tmdb_id!r}"
    assert item.genres == ["drama", "thriller"], f"Expected genres=['drama', 'thriller'], got {item.genres!r}"
    assert item.overview == "A gripping drama series.", f"Unexpected overview: {item.overview!r}"
    assert item.year == 2020, f"Expected year=2020, got {item.year!r}"
    assert item.network == "BBC", f"Expected network='BBC', got {item.network!r}"
    assert item.runtime == 60, f"Expected runtime=60, got {item.runtime!r}"


def test_radarr_media_item_carries_arr_metadata_fields(httpx_mock):
    """discover_radarr_items returns MediaItem with arr_kind='radarr' and arr_metadata fields populated.

    Stubs the pyarr Radarr.movie.get() response to include tmdbId, genres, overview,
    year, runtime (movies have no network). Verifies the returned MediaItem carries
    all Phase-4 fields with correct values and no network.

    Validates: D-35 arr_metadata snapshot fields; D-33 tmdb_id captured at discovery.
    """
    import pytest
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
                "tmdbId": 67890,
                "genres": ["thriller", "comedy"],
                "overview": "A parasite story.",
                "year": 2019,
                "runtime": 132,
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

    assert len(items) == 1
    item = items[0]
    assert item.arr_kind == "radarr", f"Expected arr_kind='radarr', got {item.arr_kind!r}"
    assert item.tmdb_id == 67890, f"Expected tmdb_id=67890, got {item.tmdb_id!r}"
    assert item.tvdb_id is None, f"Expected tvdb_id=None for Radarr movie without tvdbId, got {item.tvdb_id!r}"
    assert item.genres == ["thriller", "comedy"], f"Unexpected genres: {item.genres!r}"
    assert item.overview == "A parasite story.", f"Unexpected overview: {item.overview!r}"
    assert item.year == 2019, f"Expected year=2019, got {item.year!r}"
    assert item.network is None, f"Expected network=None for Radarr movies, got {item.network!r}"
    assert item.runtime == 132, f"Expected runtime=132, got {item.runtime!r}"


def test_media_item_extension_is_backwards_compatible():
    """MediaItem constructed with only Phase-3 positional/keyword args works — all Phase-4 fields default None.

    Validates: D-22 backwards compatibility (MediaItem extension must never break
    existing Phase-3 constructors).
    """
    import pytest
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    MediaItem = sonarr_mod.MediaItem
    from pathlib import Path

    # Construct with only the original Phase-3 fields
    item = MediaItem(
        local_path=Path("/tv/Show/S01E01.mkv"),
        title="Show",
        source_type="episode",
        series_id=1,
        season_number=1,
    )

    # All Phase-4 fields must default to None
    assert item.arr_kind is None, f"Expected arr_kind=None, got {item.arr_kind!r}"
    assert item.tvdb_id is None, f"Expected tvdb_id=None, got {item.tvdb_id!r}"
    assert item.tmdb_id is None, f"Expected tmdb_id=None, got {item.tmdb_id!r}"
    assert item.genres is None, f"Expected genres=None, got {item.genres!r}"
    assert item.overview is None, f"Expected overview=None, got {item.overview!r}"
    assert item.year is None, f"Expected year=None, got {item.year!r}"
    assert item.network is None, f"Expected network=None, got {item.network!r}"
    assert item.runtime is None, f"Expected runtime=None, got {item.runtime!r}"

    # Phase-3 fields still set correctly
    assert str(item.local_path) == "/tv/Show/S01E01.mkv"
    assert item.title == "Show"
    assert item.source_type == "episode"
    assert item.series_id == 1
    assert item.season_number == 1


def test_arr_metadata_fields_default_none_when_payload_missing(httpx_mock):
    """MediaItem still constructs with fields as None when arr payload omits metadata fields.

    Stubs a pyarr payload that omits genres/overview/year/network/runtime
    (a sparse *arr install). Verifies no KeyError and fields default to None.

    Validates: D-35 defensive .get() access for all metadata fields.
    """
    import pytest
    sonarr_mod = pytest.importorskip("trezarr.arr.sonarr")
    discover_sonarr_items = sonarr_mod.discover_sonarr_items

    from trezarr.config import TrezarrSettings

    # Minimal Sonarr series response — omitting all arr_metadata fields
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/series",
        json=[
            {
                "id": 1,
                "title": "Minimal Show",
                "path": "/tv/Minimal",
                "monitored": True,
                # No tvdbId, genres, overview, year, network, runtime
            },
        ],
    )
    httpx_mock.add_response(
        url="http://192.168.1.100:8989/api/v3/episodefile?seriesId=1",
        json=[
            {
                "id": 20,
                "seriesId": 1,
                "seasonNumber": 1,
                "path": "/tv/Minimal/Season 1/Minimal.S01E01.mkv",
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

    # Must not raise KeyError even though arr_metadata fields are absent
    items = discover_sonarr_items(settings)

    assert len(items) == 1
    item = items[0]
    assert item.arr_kind == "sonarr", f"arr_kind should still be 'sonarr', got {item.arr_kind!r}"
    assert item.tvdb_id is None, f"Missing tvdbId in payload → tvdb_id=None, got {item.tvdb_id!r}"
    assert item.genres is None, f"Missing genres in payload → genres=None, got {item.genres!r}"
    assert item.overview is None, f"Missing overview in payload → overview=None, got {item.overview!r}"
    assert item.year is None, f"Missing year in payload → year=None, got {item.year!r}"
    assert item.network is None, f"Missing network in payload → network=None, got {item.network!r}"
    assert item.runtime is None, f"Missing runtime in payload → runtime=None, got {item.runtime!r}"
