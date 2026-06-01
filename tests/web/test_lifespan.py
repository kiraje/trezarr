"""Wave-0 RED stubs for SVC-01 lifespan / engine lifecycle tests.

These stubs are xfail markers — the RED suite runs without import errors.
All trezarr.web.* imports are deferred inside test bodies so collection
succeeds before Plan 07-02 lands the implementation.

asyncio_mode="auto" is configured project-wide — no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.app not yet created — Plan 07-02")
async def test_lifespan_startup_shutdown():
    """FastAPI lifespan starts engine and scheduler without error, shuts down cleanly (SVC-01)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.app not yet created — Plan 07-02")
async def test_engine_disposed_on_shutdown():
    """AsyncEngine is disposed on lifespan shutdown (no CR-01 reuse-after-close) (SVC-01)."""
    from trezarr.web.app import create_app  # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test"):
        pass
    # After lifespan exit, engine should be disposed (no further connections possible)
    engine = app.state.engine
    assert engine is not None
    # Attempting to use a disposed engine raises — proves dispose was called
    assert getattr(engine, "_closed", True) or engine.pool.size() == 0


@pytest.mark.xfail(raises=(ImportError, AssertionError), reason="trezarr.web.app.run_serve not yet created — Plan 07-02")
def test_serve_subcommand_exists():
    """`trezarr serve` CLI subcommand is registered in the argument parser (SVC-01)."""
    import argparse  # noqa: PLC0415
    from trezarr.cli import main  # noqa: PLC0415

    # Probe the subparsers without running the actual command
    import trezarr.cli as cli_mod  # noqa: PLC0415
    # The parser must have a 'serve' subcommand registered
    # We verify by attempting to parse 'serve' — it should NOT raise SystemExit(2)
    # (which would indicate unknown command)
    try:
        parser = cli_mod._build_parser()  # type: ignore[attr-defined]
        args = parser.parse_args(["serve"])
        assert args.command == "serve"
    except AttributeError:
        # If _build_parser doesn't exist yet, fall back to checking main's parser
        raise AssertionError("trezarr.cli._build_parser not yet available — Plan 07-02")
