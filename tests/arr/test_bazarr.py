"""Wave 0 RED stubs for Bazarr inventory client (INTG-02).

All imports from trezarr.arr.bazarr are deferred inside each test so pytest
collection succeeds before the module exists. The xfail(strict=False) pattern
matches the established Trezarr convention (see tests/arr/test_arr_discovery.py
and STATE.md decisions: xfail(strict=False, raises=(ImportError, AssertionError, TypeError))).

Covers:
  INTG-02  BazarrClient.fetch_episodes() parses SubtitleEntry list
  INTG-02  BazarrClient.fetch_movies() parses SubtitleEntry list
  INTG-02  BazarrError raised on 4xx responses
  INTG-02  BazarrError raised on connection failure
  INTG-02  Path mapping applied to subtitle path

Recorded fixture shape from RESEARCH.md §"Confirmed Endpoints and Response Shapes":
  GET /api/episodes?seriesid=<id>  →  {"data": [<episode_obj>, ...]}
  where episode_obj["subtitles"] = [{"name": "Korean", "code2": "ko", "code3": "kor",
                                      "path": "/tv/Show/S01E01.ko.srt", "forced": false,
                                      "hi": false}]
"""
from __future__ import annotations

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixture data — synthetic only (T-10-01: no real credentials or paths)
# ──────────────────────────────────────────────────────────────────────────────

EPISODE_FIXTURE = {
    "seriesId": 1,
    "episode": 1,
    "season": 1,
    "title": "Pilot",
    "subtitles": [
        {
            "name": "Korean",
            "code2": "ko",
            "code3": "kor",
            "path": "/tv/Show/S01E01.ko.srt",
            "forced": False,
            "hi": False,
        }
    ],
}

MOVIE_FIXTURE = {
    "radarrId": 1,
    "title": "Parasite",
    "subtitles": [
        {
            "name": "Korean",
            "code2": "ko",
            "code3": "kor",
            "path": "/movies/Parasite (2019)/Parasite.ko.srt",
            "forced": False,
            "hi": False,
        }
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# Stubs (xfail — trezarr.arr.bazarr does not exist yet)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="BazarrClient not yet implemented (INTG-02, Phase 10)",
)
async def test_fetch_episodes_parses_subtitle_entries(httpx_mock):
    """BazarrClient.fetch_episodes() returns SubtitleEntry objects for the source language (INTG-02)."""
    from trezarr.arr.bazarr import BazarrClient, SubtitleEntry  # type: ignore[import-not-found]

    httpx_mock.add_response(
        url="http://bazarr.local:6767/api/episodes?seriesid=1",
        json={"data": [EPISODE_FIXTURE]},
    )

    client = BazarrClient(base_url="http://bazarr.local:6767", api_key="test-key")
    results = await client.fetch_episodes(series_id=1)

    assert results, "Expected at least one SubtitleEntry"
    entry = results[0]
    assert isinstance(entry, SubtitleEntry), f"Expected SubtitleEntry, got {type(entry)}"
    assert entry.code2 == "ko", f"Expected code2='ko', got {entry.code2!r}"
    assert "/tv/Show/S01E01.ko.srt" in str(entry.path), f"Expected path to contain S01E01.ko.srt, got {entry.path!r}"


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="BazarrClient.fetch_movies() not yet implemented (INTG-02, Phase 10)",
)
async def test_fetch_movies_parses_subtitle_entries(httpx_mock):
    """BazarrClient.fetch_movies() returns SubtitleEntry objects for the source language (INTG-02)."""
    from trezarr.arr.bazarr import BazarrClient, SubtitleEntry  # type: ignore[import-not-found]

    httpx_mock.add_response(
        url="http://bazarr.local:6767/api/movies",
        json={"data": [MOVIE_FIXTURE]},
    )

    client = BazarrClient(base_url="http://bazarr.local:6767", api_key="test-key")
    results = await client.fetch_movies()

    assert results, "Expected at least one SubtitleEntry"
    entry = results[0]
    assert isinstance(entry, SubtitleEntry), f"Expected SubtitleEntry, got {type(entry)}"
    assert entry.code2 == "ko", f"Expected code2='ko', got {entry.code2!r}"


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="BazarrError not yet implemented (INTG-02, Phase 10)",
)
async def test_bazarr_error_on_4xx(httpx_mock):
    """BazarrClient raises BazarrError on a 4xx response from the Bazarr API (INTG-02)."""
    from trezarr.arr.bazarr import BazarrClient, BazarrError  # type: ignore[import-not-found]

    httpx_mock.add_response(
        url="http://bazarr.local:6767/api/episodes?seriesid=99",
        status_code=401,
        json={"error": "Unauthorized"},
    )

    client = BazarrClient(base_url="http://bazarr.local:6767", api_key="wrong-key")
    with pytest.raises(BazarrError):
        await client.fetch_episodes(series_id=99)


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="BazarrError on connection failure not yet implemented (INTG-02, Phase 10)",
)
async def test_bazarr_error_on_connection_failure(httpx_mock):
    """BazarrClient raises BazarrError when the Bazarr host is unreachable (INTG-02)."""
    import httpx  # noqa: PLC0415
    from trezarr.arr.bazarr import BazarrClient, BazarrError  # type: ignore[import-not-found]

    httpx_mock.add_exception(
        httpx.ConnectError("Connection refused"),
        url="http://bazarr.unreachable:6767/api/episodes?seriesid=1",
    )

    client = BazarrClient(base_url="http://bazarr.unreachable:6767", api_key="test-key")
    with pytest.raises(BazarrError):
        await client.fetch_episodes(series_id=1)


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="Path mapping for Bazarr subtitle paths not yet implemented (INTG-02, Phase 10)",
)
async def test_path_mapping_applied_to_subtitle_path(httpx_mock):
    """BazarrClient applies path_mappings to subtitle paths returned by the API (INTG-02).

    When the Bazarr host sees `/tv/...` but Trezarr sees `/media/tv/...`, the
    BazarrClient must translate the path before returning the SubtitleEntry.
    """
    from trezarr.arr.bazarr import BazarrClient, BazarrInventoryItem  # type: ignore[import-not-found]

    fixture_with_bazarr_path = {
        **EPISODE_FIXTURE,
        "subtitles": [
            {
                "name": "Korean",
                "code2": "ko",
                "code3": "kor",
                "path": "/bazarr/tv/Show/S01E01.ko.srt",
                "forced": False,
                "hi": False,
            }
        ],
    }
    httpx_mock.add_response(
        url="http://bazarr.local:6767/api/episodes?seriesid=1",
        json={"data": [fixture_with_bazarr_path]},
    )

    client = BazarrClient(
        base_url="http://bazarr.local:6767",
        api_key="test-key",
        path_mappings=[("/bazarr/tv", "/trezarr/tv")],
    )
    results = await client.fetch_episodes(series_id=1)

    assert results, "Expected at least one result after path mapping"
    entry = results[0]
    assert "/trezarr/tv" in str(entry.path), (
        f"Expected path_mapping to rewrite /bazarr/tv → /trezarr/tv, got {entry.path!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# W3: inventory param-form fallback (seriesid[] → plain seriesid). Real tests
# (not xfail) — BazarrClient ships since Phase 10.
# ──────────────────────────────────────────────────────────────────────────────

INVENTORY_FIXTURE = {
    "sonarrEpisodeId": 100,
    "path": "/tv/Show/S01E01.mkv",
    "subtitles": [
        {"name": "Korean", "code2": "ko", "code3": "kor",
         "path": "/tv/Show/S01E01.ko.srt", "forced": False, "hi": False},
    ],
}


async def test_fetch_episode_inventory_falls_back_to_plain_seriesid(httpx_mock):
    """W3: when the bracketed seriesid[] form returns empty, retry with plain seriesid."""
    from trezarr.arr.bazarr import BazarrClient  # noqa: PLC0415

    httpx_mock.add_response(json={"data": []})                    # seriesid[] → empty
    httpx_mock.add_response(json={"data": [INVENTORY_FIXTURE]})    # seriesid   → data

    client = BazarrClient(base_url="http://bazarr.local:6767", api_key="test-key")
    items = await client.fetch_episode_inventory(1)

    assert len(items) == 1, "fallback must surface the plain-seriesid data"
    reqs = httpx_mock.get_requests()
    assert len(reqs) == 2, "must try bracketed then fall back to plain"
    assert "seriesid%5B%5D=1" in str(reqs[0].url), "first request uses the seriesid[] form"
    u1 = str(reqs[1].url)
    assert "seriesid=1" in u1 and "seriesid%5B%5D" not in u1, "fallback uses plain seriesid"


async def test_fetch_episode_inventory_no_fallback_when_bracketed_returns_data(httpx_mock):
    """W3: no extra request when the bracketed form already returns data."""
    from trezarr.arr.bazarr import BazarrClient  # noqa: PLC0415

    httpx_mock.add_response(json={"data": [INVENTORY_FIXTURE]})

    client = BazarrClient(base_url="http://bazarr.local:6767", api_key="test-key")
    items = await client.fetch_episode_inventory(1)

    assert len(items) == 1
    assert len(httpx_mock.get_requests()) == 1, "no fallback call when the bracketed form has data"


async def test_fetch_movie_inventory_falls_back_to_plain_radarrid(httpx_mock):
    """W3: the movie inventory path has the same radarrid[] → radarrid fallback."""
    from trezarr.arr.bazarr import BazarrClient  # noqa: PLC0415

    movie_item = {**INVENTORY_FIXTURE, "radarrId": 7, "sonarrEpisodeId": None}
    httpx_mock.add_response(json={"data": []})              # radarrid[] → empty
    httpx_mock.add_response(json={"data": [movie_item]})    # radarrid   → data

    client = BazarrClient(base_url="http://bazarr.local:6767", api_key="test-key")
    items = await client.fetch_movie_inventory(7)

    assert len(items) == 1, "fallback must surface the plain-radarrid data"
    reqs = httpx_mock.get_requests()
    assert len(reqs) == 2, "must try bracketed then fall back to plain"
    assert "radarrid%5B%5D=7" in str(reqs[0].url), "first request uses the radarrid[] form"
    u1 = str(reqs[1].url)
    assert "radarrid=7" in u1 and "radarrid%5B%5D" not in u1, "fallback uses plain radarrid"
