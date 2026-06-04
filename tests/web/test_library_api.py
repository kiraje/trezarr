"""Tests for GET /api/library, GET /api/library/series/{id}/episodes,
and POST /api/translate endpoints (quick task 260603-l8g).

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
All trezarr.web.* imports are deferred inside test bodies (PLC0415 pattern).
"""
from __future__ import annotations


async def test_get_library_returns_200():
    """GET /api/library always returns 200 even when *arr disabled."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/library")
    assert resp.status_code == 200
    data = resp.json()
    assert "series" in data
    assert "movies" in data
    assert "errors" in data
    assert isinstance(data["series"], list)
    assert isinstance(data["movies"], list)


async def test_get_series_episodes_disabled_returns_400():
    """GET /api/library/series/{id}/episodes returns 400 when sonarr disabled."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    # Default settings have sonarr_enabled=False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/library/series/1/episodes")
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data


async def test_post_translate_missing_source_path_returns_400():
    """POST /api/translate without source_path returns 400."""
    import json  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/translate",
            content=json.dumps({"kind": "series"}),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data


async def test_post_translate_nonexistent_path_returns_400():
    """POST /api/translate with a source_path that doesn't exist on disk returns 400."""
    import json  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/translate",
            content=json.dumps({"kind": "series", "source_path": "/nonexistent/path.srt"}),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data


# ── Fix #3 regression tests: post_translate builds media_item for Bible-aware path ──


async def test_post_translate_series_builds_media_item(tmp_path):
    """POST /api/translate (series) enqueues with arr_kind+series_id in media_item (fix #3).

    Regression: manual translate used to call enqueue_job(media_item=None), causing
    _execute_job to take the mechanical (non-Bible-aware) path.  After fix #3 it must
    pass a media_item SimpleNamespace with at least arr_kind and series_id populated
    so the worker can build a Bible-aware eligible_stub.
    """
    import json  # noqa: PLC0415
    from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    # Create a real subtitle file so the existence check passes
    srt_file = tmp_path / "show.S01E01.en.srt"
    srt_file.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n")

    app = create_app()
    app.state.settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        sonarr_enabled=False,  # disable enrichment fetch; test minimal media_item path
    )

    captured_calls: list[dict] = []

    async def mock_enqueue_job(session_factory, source_path, series_id=None, trigger="poll", media_item=None):
        captured_calls.append({
            "source_path": source_path,
            "series_id": series_id,
            "trigger": trigger,
            "media_item": media_item,
        })
        return True

    # patch at the module that defines it (the deferred import resolves to this)
    with patch("trezarr.web.worker.enqueue_job", side_effect=mock_enqueue_job):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/translate",
                content=json.dumps({
                    "kind": "series",
                    "source_path": str(srt_file),
                    "arr_series_id": 42,
                }),
                headers={"Content-Type": "application/json"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["enqueued"] is True

    # Verify that enqueue_job was called with a media_item that carries arr_kind + series_id
    assert len(captured_calls) == 1, f"Expected exactly 1 enqueue_job call, got {captured_calls}"
    mi = captured_calls[0]["media_item"]
    assert mi is not None, "media_item must not be None for Bible-aware path"
    assert getattr(mi, "arr_kind", None) == "sonarr", f"Expected arr_kind='sonarr', got {getattr(mi, 'arr_kind', None)!r}"
    assert getattr(mi, "series_id", None) == 42, f"Expected series_id=42, got {getattr(mi, 'series_id', None)!r}"
    assert getattr(mi, "source_type", None) == "episode", f"Expected source_type='episode', got {getattr(mi, 'source_type', None)!r}"


async def test_post_translate_series_failsoft_when_sonarr_unavailable(tmp_path):
    """POST /api/translate still enqueues with minimal media_item when Sonarr fetch fails (fix #3).

    Regression: if Sonarr enrichment raises, the route must NOT 500 — it should log a
    warning and enqueue with the minimal media_item (arr_kind/series_id/source_type) so
    the Bible-aware path still runs with safe-default register.
    """
    import json  # noqa: PLC0415
    from unittest.mock import AsyncMock, MagicMock, patch  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    srt_file = tmp_path / "show.S01E02.en.srt"
    srt_file.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n")

    app = create_app()
    app.state.settings = TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        sonarr_enabled=True,
        sonarr_host="http://sonarr:8989",
        sonarr_api_key="fake-key",
    )

    captured_calls: list[dict] = []

    async def mock_enqueue_job(session_factory, source_path, series_id=None, trigger="poll", media_item=None):
        captured_calls.append({"media_item": media_item})
        return True

    # Make the Sonarr client raise on .series.get() — simulates *arr unavailable
    mock_sonarr = MagicMock()
    mock_sonarr.series.get.side_effect = Exception("connection refused")

    with patch("trezarr.web.worker.enqueue_job", side_effect=mock_enqueue_job), \
         patch("trezarr.arr.sonarr.build_sonarr_client", return_value=mock_sonarr):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/translate",
                content=json.dumps({
                    "kind": "series",
                    "source_path": str(srt_file),
                    "arr_series_id": 7,
                }),
                headers={"Content-Type": "application/json"},
            )

    # Must not 500 — fail-soft means still enqueues
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["enqueued"] is True

    # media_item still populated with minimal fields (arr_kind + series_id + source_type)
    assert len(captured_calls) == 1
    mi = captured_calls[0]["media_item"]
    assert mi is not None, "media_item must not be None even when Sonarr fetch fails"
    assert getattr(mi, "arr_kind", None) == "sonarr"
    assert getattr(mi, "series_id", None) == 7
    assert getattr(mi, "source_type", None) == "episode"


# ── Phase 13 RED stubs (Wave 0) ───────────────────────────────────────────────
#
# All 8 tests below are xfail stubs that document the Phase-13 API contract
# before implementation.  They run as XFAIL; they must NOT hard-fail pytest.
# Implementations land in Phase 13 plans 02–03.


import pytest  # noqa: E402 — module-level import required for @pytest.mark.xfail


@pytest.mark.xfail(
    strict=False,
    reason="D-08 fail-soft: GET /api/library/series/{id}/episodes returns 200 + "
    "bazarr_available=False + errors=[] when bazarr disabled — implemented in Phase 13 plan 02",
)
async def test_get_series_episodes_bazarr_disabled():
    """HTTP 200 + bazarr_available=False + errors=[] when bazarr is disabled (D-08).

    Sonarr is mocked as enabled+working so the endpoint reaches the Bazarr branch.
    When bazarr_enabled=False, the response must omit any error entry — disabled is
    not an error, just a flag.
    """
    from unittest.mock import patch, MagicMock  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    # Inject settings: Sonarr enabled, Bazarr disabled
    app.state.settings = TrezarrSettings(
        sonarr_enabled=True,
        bazarr_enabled=False,
    )

    mock_client = MagicMock()
    mock_client.episode.get.return_value = [
        {"id": 10, "seasonNumber": 1, "episodeNumber": 1, "hasFile": False},
    ]
    mock_client.episode_file.get.return_value = []

    with patch("trezarr.arr.sonarr.build_sonarr_client", return_value=mock_client):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/library/series/1/episodes")

    assert resp.status_code == 200
    data = resp.json()
    assert data["bazarr_available"] is False
    assert data["errors"] == []


@pytest.mark.xfail(
    strict=False,
    reason="D-08 fail-soft: GET /api/library/series/{id}/episodes returns 200 + "
    "bazarr_available=False + errors entry when bazarr enabled but unreachable — Phase 13 plan 02",
)
async def test_get_series_episodes_bazarr_error():
    """HTTP 200 + bazarr_available=False + errors[0].source=='bazarr' when bazarr unreachable (D-08).

    Bazarr is enabled but BazarrError is raised from BazarrClient.  The endpoint
    must stay HTTP 200 and populate the errors list with one entry carrying
    source='bazarr'.
    """
    from unittest.mock import patch, MagicMock  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415
    from trezarr.arr.bazarr import BazarrError  # noqa: PLC0415

    app = create_app()
    app.state.settings = TrezarrSettings(
        sonarr_enabled=True,
        bazarr_enabled=True,
    )

    mock_client = MagicMock()
    mock_client.episode.get.return_value = [
        {"id": 10, "seasonNumber": 1, "episodeNumber": 1, "hasFile": False},
    ]
    mock_client.episode_file.get.return_value = []

    with patch("trezarr.arr.sonarr.build_sonarr_client", return_value=mock_client), \
         patch("trezarr.arr.bazarr.BazarrClient.from_settings", side_effect=BazarrError("timeout")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/library/series/1/episodes")

    assert resp.status_code == 200
    data = resp.json()
    assert data["bazarr_available"] is False
    assert len(data["errors"]) >= 1
    assert data["errors"][0]["source"] == "bazarr"


@pytest.mark.xfail(
    strict=False,
    reason="D-02 join key: Bazarr inventory joins on episode.id (sonarrEpisodeId), "
    "not episodeFile.id — implemented in Phase 13 plan 02",
)
async def test_get_series_episodes_bazarr_join_key():
    """Bazarr subtitle appears on the episode whose id matches arr_id, not episodeFile.id (D-02).

    Two mock episodes: ep_id=10 (target) and ep_id=11.
    One episode file with id=99.
    Bazarr inventory has arr_id=10 (episode.id, NOT episodeFile.id=99).
    The subtitle must appear on the episode with episode_id==10, not ep_id==11.
    """
    from unittest.mock import patch, MagicMock, AsyncMock  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    app.state.settings = TrezarrSettings(
        sonarr_enabled=True,
        bazarr_enabled=True,
    )

    mock_sonarr = MagicMock()
    mock_sonarr.episode.get.return_value = [
        {"id": 10, "seasonNumber": 1, "episodeNumber": 1, "hasFile": True},
        {"id": 11, "seasonNumber": 1, "episodeNumber": 2, "hasFile": True},
    ]
    mock_sonarr.episode_file.get.return_value = [
        {"id": 99, "path": "/media/show/s01e01.mkv", "seasonNumber": 1},
    ]

    # Bazarr inventory keyed on arr_id=10 (episode.id), not 99 (episodeFile.id)
    # SubtitleEntry is the correct class name (BazarrSubtitle was an alias in the stub — Rule 1 fix)
    # fetch_episode_inventory is async, so mock with AsyncMock (Rule 1 fix)
    from trezarr.arr.bazarr import BazarrInventoryItem, SubtitleEntry  # noqa: PLC0415
    bazarr_inventory = [
        BazarrInventoryItem(
            arr_id=10,
            path="/media/show/s01e01.mkv",
            subtitles=[SubtitleEntry(code2="en", code3="eng", path="", forced=False, hi=False)],
        ),
    ]

    mock_bazarr = MagicMock()
    mock_bazarr.fetch_episode_inventory = AsyncMock(return_value=bazarr_inventory)

    with patch("trezarr.arr.sonarr.build_sonarr_client", return_value=mock_sonarr), \
         patch("trezarr.arr.bazarr.BazarrClient.from_settings", return_value=mock_bazarr):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/library/series/1/episodes")

    assert resp.status_code == 200
    data = resp.json()
    # Flatten all episodes across seasons
    all_episodes = [ep for season in data["seasons"] for ep in season["episodes"]]
    ep_10 = next(ep for ep in all_episodes if ep["episode_id"] == 10)
    ep_11 = next(ep for ep in all_episodes if ep["episode_id"] == 11)
    assert len(ep_10["subtitles"]) > 0, "Subtitle must appear on episode id=10 (arr_id match)"
    assert len(ep_11["subtitles"]) == 0, "Episode id=11 must have no subtitles (no arr_id match)"


@pytest.mark.xfail(
    strict=False,
    reason="D-07 audio normalization: _normalize_audio_languages maps full names to ISO-639-1 "
    "codes — implemented in Phase 13 plan 02",
)
async def test_audio_language_normalization():
    """_normalize_audio_languages('Korean/English') == ['ko', 'en']; unknown → lowercased (D-07)."""
    from trezarr.web.routes.library import _normalize_audio_languages  # noqa: PLC0415

    result = _normalize_audio_languages("Korean/English")
    assert result == ["ko", "en"], f"Expected ['ko', 'en'], got {result!r}"

    result_unknown = _normalize_audio_languages("Klingon")
    assert result_unknown == ["klingon"], f"Expected ['klingon'] (lowercased fallback), got {result_unknown!r}"


@pytest.mark.xfail(
    strict=False,
    reason="D-01/D-03 envelope shape: GET /api/library/series/{id}/episodes returns season-grouped "
    "envelope with episode_key field — implemented in Phase 13 plan 02",
)
async def test_get_series_episodes_envelope_shape():
    """Response has series_id, bazarr_available, seasons list; each season and episode has required fields (D-01/D-03).

    Asserts the Phase-13 JSON contract:
      { series_id, bazarr_available, seasons: [{ season_number, episodes: [{ episode_id, episode_key,
        audio_languages, subtitles }] }], errors: [] }
    """
    from unittest.mock import patch, MagicMock  # noqa: PLC0415
    from trezarr.web.app import create_app  # noqa: PLC0415
    from trezarr.config import TrezarrSettings  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    app.state.settings = TrezarrSettings(
        sonarr_enabled=True,
        bazarr_enabled=False,
    )

    mock_client = MagicMock()
    mock_client.episode.get.return_value = [
        {"id": 1, "seasonNumber": 1, "episodeNumber": 1, "hasFile": False},
        {"id": 2, "seasonNumber": 1, "episodeNumber": 2, "hasFile": False},
    ]
    mock_client.episode_file.get.return_value = []

    with patch("trezarr.arr.sonarr.build_sonarr_client", return_value=mock_client):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/library/series/1/episodes")

    assert resp.status_code == 200
    data = resp.json()
    # Top-level envelope fields
    assert "series_id" in data
    assert "bazarr_available" in data
    assert "seasons" in data
    assert "errors" in data
    assert isinstance(data["seasons"], list)
    assert len(data["seasons"]) >= 1
    season = data["seasons"][0]
    assert "season_number" in season
    assert season["season_number"] == 1
    assert "episodes" in season
    assert isinstance(season["episodes"], list)
    assert len(season["episodes"]) >= 1
    episode = season["episodes"][0]
    assert "episode_id" in episode
    assert "episode_key" in episode
    assert "audio_languages" in episode
    assert "subtitles" in episode


@pytest.mark.xfail(
    strict=False,
    reason="D-04/D-05/API-02: GET /api/library series items have translated_count and total_count "
    "integer fields — implemented in Phase 13 plan 02",
)
async def test_get_library_series_count_fields():
    """Each series item in GET /api/library has translated_count (int) and total_count (int) (D-04/API-02).

    When Sonarr is disabled, series list is empty — the test is xfail until implementation
    adds count fields to series items returned by the live Sonarr call.
    """
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/library")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["series"], list)
    # After implementation, each series item must carry count fields
    for series_item in data["series"]:
        assert "translated_count" in series_item, f"Missing translated_count in {series_item}"
        assert "total_count" in series_item, f"Missing total_count in {series_item}"
        assert isinstance(series_item["translated_count"], int)
        assert isinstance(series_item["total_count"], int)


@pytest.mark.xfail(
    strict=False,
    reason="D-05 bulk count: translated_counts_for_series(session_factory, ids) returns "
    "{str(series_id): n} — implemented in Phase 13 plan 02",
)
async def test_translated_counts_for_series():
    """translated_counts_for_series returns {str(series_id): count} from ProcessedFile rows (D-05).

    Uses in-memory SQLite + SQLAlchemy async to insert 2 done rows for series_id='42'
    and 1 done row for series_id='99', then asserts the helper returns correct counts.
    series_id=7 is absent from DB → not in the returned dict (caller uses .get(k, 0)).
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa: PLC0415
    from trezarr.output.ledger_sqla import translated_counts_for_series  # noqa: PLC0415
    from trezarr.bible.models import ProcessedFile, Base  # noqa: PLC0415

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionFactory() as session:
        session.add_all([
            ProcessedFile(series_id="42", source_path="/a/1.srt", output_path="/a/1.vi.srt", status="done", content_hash="a1b2c3d4e5f60001"),
            ProcessedFile(series_id="42", source_path="/a/2.srt", output_path="/a/2.vi.srt", status="done", content_hash="a1b2c3d4e5f60002"),
            ProcessedFile(series_id="99", source_path="/b/1.srt", output_path="/b/1.vi.srt", status="done", content_hash="a1b2c3d4e5f60003"),
        ])
        await session.commit()

    result = await translated_counts_for_series(SessionFactory, [42, 99, 7])
    assert result.get("42") == 2, f"Expected 2 for series_id='42', got {result}"
    assert result.get("99") == 1, f"Expected 1 for series_id='99', got {result}"
    assert "7" not in result, "series_id='7' with no rows must be absent from result"

    await engine.dispose()


@pytest.mark.xfail(
    strict=False,
    reason="D-04/API-02: GET /api/library movie items have translated_count and total_count "
    "integer fields — implemented in Phase 13 plan 02",
)
async def test_get_library_movies_count_fields():
    """Each movie item in GET /api/library has translated_count (int) and total_count (int) (D-04/API-02).

    When Radarr is disabled, movies list is empty — the test is xfail until implementation
    adds count fields to movie items returned by the live Radarr call.
    """
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/library")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["movies"], list)
    for movie_item in data["movies"]:
        assert "translated_count" in movie_item, f"Missing translated_count in {movie_item}"
        assert "total_count" in movie_item, f"Missing total_count in {movie_item}"
        assert isinstance(movie_item["translated_count"], int)
        assert isinstance(movie_item["total_count"], int)


async def test_get_library_includes_services_flags():
    """W1: GET /api/library exposes positive per-service enabled flags for the LIVE badge.

    The LIVE badge previously inferred "live" from absence-of-error, so a DISABLED
    *arr service showed a false-positive green badge. The response now carries a
    positive `services` map; a disabled service is False (→ not LIVE).
    """
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/library")

    assert resp.status_code == 200
    data = resp.json()
    assert "services" in data, "response must expose positive enabled flags (W1)"
    services = data["services"]
    assert set(services.keys()) == {"sonarr", "radarr", "bazarr"}
    # Default settings disable all *arr services → all flags False (the exact
    # disabled-service case that used to false-positive as LIVE).
    assert services == {"sonarr": False, "radarr": False, "bazarr": False}
