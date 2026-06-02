"""FastAPI application factory + lifespan (D-61, SVC-01).

Design decisions honoured:
  D-61  One uvicorn process. FastAPI lifespan owns the daemon (APScheduler poll
        + webhook receiver + queue worker) AND serves the built Vite SPA static
        assets. Single image, single port (default 6868).
  D-62  `trezarr serve` dispatches here via run_serve(). `trezarr run --once`
        behavior is preserved in cli.py and is completely unaffected.
  D-67  reconcile_in_progress (ARM 1) + reconcile_in_progress_from_ledger (ARM 2)
        are both called on startup — crash-safe resume.
  D-68  worker_loop runs as an asyncio.Task; per-series serialization is managed
        by _series_locks inside worker.py (NOT a second Semaphore — Pitfall C).
  CR-01 ONE AsyncEngine for the process lifetime, created BEFORE the outer try
        in lifespan so its existence is unambiguous on every dispose path. Disposed
        in the finally block of lifespan shutdown.

Anti-patterns avoided (RESEARCH.md):
  - Engine NOT created at module scope (Pitfall A)
  - Scheduler NOT started outside lifespan (Pitfall B)
  - StaticFiles mount LAST (Pitfall E)
  - No translation inside request handlers (Pitfall D)
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)


# ── Application factory ─────────────────────────────────────────────────────────


def _resolve_db_url(settings: TrezarrSettings) -> str:
    """Return a usable DB URL, falling back to a temp file if the config path's
    parent directory does not exist.

    This makes create_app() / the lifespan work in test environments where
    /config/ has not been created, without requiring callers to pass custom
    settings. In production the /config/ volume is always mounted.
    """
    db_url = settings.bible_db_url
    # Only apply fallback for file-based SQLite URLs (not :memory:)
    if "sqlite+aiosqlite:///" in db_url and ":memory:" not in db_url:
        # Extract the file path: sqlite+aiosqlite:////abs/path → /abs/path
        path_part = db_url.split("sqlite+aiosqlite:///", 1)[-1]
        parent = Path(path_part).parent
        if not parent.exists():
            # Parent directory doesn't exist — use a temp file instead.
            # This happens in test environments where /config/ is not mounted.
            tmp_dir = tempfile.mkdtemp(prefix="trezarr_test_")
            tmp_path = os.path.join(tmp_dir, "trezarr.db")
            logger.warning(
                "DB parent directory %s does not exist; using temp DB at %s "
                "(this is normal in test environments without /config/ mounted)",
                parent, tmp_path,
            )
            return f"sqlite+aiosqlite:///{tmp_path}"
    return db_url


@asynccontextmanager
async def _lifespan(app, settings: TrezarrSettings | None = None, engine_cell: list | None = None) -> AsyncIterator[None]:
    """FastAPI lifespan manager — owns engine, scheduler, and worker task (D-61).

    Startup sequence mirrors cli.py::_run_once but at process scope (CR-01):
      1. assert_media_roots_configured (HIGH #2)
      2. build_media_roots + probe_media_roots (D-24)
      3. build_engine BEFORE outer try (CR-01 invariant)
      4. run_migrations_to_head (0001 + 0002)
      5. build_session_factory
      6. reconcile_in_progress + reconcile_in_progress_from_ledger (D-67 both arms)
      7. Build LLMClient + LedgerSQLA
      8. AsyncIOScheduler.start() (INSIDE lifespan — Pitfall B)
      9. asyncio.create_task(worker_loop(...))
      yield (app is serving)
    Finally:
      cancel worker tasks → scheduler.shutdown() → await engine.dispose() (CR-01)
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: PLC0415

    from trezarr.db.engine import build_engine  # noqa: PLC0415
    from trezarr.db.migration_runner import run_migrations_to_head  # noqa: PLC0415
    from trezarr.db.session import build_session_factory  # noqa: PLC0415
    from trezarr.llm.client import LLMClient  # noqa: PLC0415
    from trezarr.output.ledger_sqla import LedgerSQLA  # noqa: PLC0415
    from trezarr.paths import (  # noqa: PLC0415
        assert_media_roots_configured,
        build_media_roots,
        probe_media_roots,
    )
    from trezarr.web.worker import (  # noqa: PLC0415
        _background_tasks as _worker_background_tasks,
        reconcile_in_progress,
        reconcile_in_progress_from_ledger,
        worker_loop,
    )

    _settings = settings or TrezarrSettings()

    # Step 1 — assert media roots configured (HIGH #2 from 03-REVIEWS.md)
    assert_media_roots_configured(_settings)

    # Step 2 — build and probe media roots (D-24)
    media_roots = build_media_roots(_settings)
    probe_media_roots(media_roots)

    # Step 3 — resolve DB URL (with fallback for test environments)
    db_url = _resolve_db_url(_settings)
    if db_url != _settings.bible_db_url:
        # Rebuild settings with the resolved URL to keep everything consistent
        _settings = TrezarrSettings(
            _yaml_file=None,
            bible_db_url=db_url,
            llm_api_key=_settings.llm_api_key,
        )

    # CR-01: engine created BEFORE the outer try so its existence is
    # unambiguous on every dispose path (see cli.py::_run_once for the
    # identical comment explaining this invariant).
    engine = build_engine(_settings)
    # Store engine reference in the cell so the outer app.state.engine proxy
    # can expose it after startup (Starlette lifespan passes the inner Router
    # app, not the outer FastAPI instance, so app.state here is the inner state).
    if engine_cell is not None:
        engine_cell.append(engine)
    app.state.engine = engine

    worker_task: asyncio.Task | None = None
    scheduler: AsyncIOScheduler | None = None

    try:
        # Step 4 — run Alembic migrations (0001 + 0002 baseline + job queue)
        await run_migrations_to_head(engine)

        # Step 5 — build session factory (expire_on_commit=False per Pitfall 2)
        session_factory = build_session_factory(engine)
        app.state.session_factory = session_factory
        app.state.settings = _settings

        # Step 6 — crash-resume reconciliation (D-67, both arms)
        await reconcile_in_progress(session_factory)
        await reconcile_in_progress_from_ledger(session_factory)

        # Step 7 — build LLMClient and LedgerSQLA
        llm_client = LLMClient(_settings)
        ledger = LedgerSQLA(session_factory)

        # Expose ledger, media_roots, and llm_client on app.state for route handlers
        # (webhook handler reads these via request.app.state)
        app.state.ledger = ledger
        app.state.media_roots = media_roots
        app.state.llm_client = llm_client

        # Step 8 — APScheduler (MUST start INSIDE lifespan — Pitfall B)
        scheduler = AsyncIOScheduler()
        # Wire the poll job (Plan 07-03 monitoring, D-65/D-66)
        from trezarr.web.scheduler import setup_scheduler  # noqa: PLC0415
        setup_scheduler(scheduler, session_factory, _settings, ledger, media_roots, llm_client)
        scheduler.start()
        logger.info("lifespan: APScheduler started with main_poll job")

        # Step 9 — start the worker loop as an asyncio.Task
        worker_task = asyncio.create_task(
            worker_loop(session_factory, _settings, llm_client, ledger, media_roots)
        )
        logger.info("lifespan: worker_loop task started")

        yield  # ← app is now serving requests

    finally:
        # SHUTDOWN — reverse order (CR-01 at process scope)
        logger.info("lifespan: shutting down")

        if worker_task is not None:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

        # WR-01: cancel in-flight _execute_job tasks before engine.dispose() to
        # avoid DB operations against a closed engine. Cancelling worker_task above
        # stops NEW dispatches; these cancel the already-dispatched tasks.
        if _worker_background_tasks:
            logger.info(
                "lifespan: cancelling %d in-flight job tasks before engine dispose",
                len(_worker_background_tasks),
            )
            for t in list(_worker_background_tasks):
                t.cancel()
            await asyncio.gather(*list(_worker_background_tasks), return_exceptions=True)

        if scheduler is not None:
            scheduler.shutdown(wait=False)

        # CR-01: ALWAYS dispose the AsyncEngine before the lifespan exits.
        # Without this, aiosqlite worker threads outlive the event loop and
        # the next finalization attempt raises `RuntimeError: Event loop is closed`.
        await engine.dispose()
        logger.info("lifespan: engine disposed (CR-01)")


def create_app(settings: TrezarrSettings | None = None) -> FastAPI:
    """Create and return the FastAPI application with lifespan management.

    Args:
        settings: Optional TrezarrSettings override. If None, TrezarrSettings()
                  is used inside the lifespan (with test-friendly DB path fallback).

    Returns:
        Configured FastAPI instance with lifespan, health endpoint, and (when
        the static dist/ exists) the SPA static file mount.
    """
    # We use a list as a mutable cell so the inner lifespan can write the engine
    # reference back to the outer scope. This is needed because Starlette/FastAPI
    # passes an INNER app (the Router) to the lifespan, not the outer FastAPI
    # instance. Storing on the outer app's state directly is not possible from
    # inside the lifespan via the `app` param.
    _engine_cell: list = []

    @asynccontextmanager
    async def _bound_lifespan(inner_app) -> AsyncIterator[None]:
        """Lifespan closure that captures the settings argument and engine cell."""
        async with _lifespan(inner_app, settings=settings, engine_cell=_engine_cell):
            yield

    outer_app = FastAPI(
        title="Trezarr",
        description="Automated Vietnamese subtitle translator for the *arr media stack.",
        version="0.1.0",
        lifespan=_bound_lifespan,
    )

    # Expose the engine cell through app.state so the test can access it after
    # the lifespan. The engine reference is written by _lifespan into _engine_cell.
    # We store the cell reference (not the engine) so it can be read after startup.
    outer_app.state._engine_cell = _engine_cell

    # Convenience property: app.state.engine reads from the cell.
    # We patch the State object to provide the 'engine' attribute dynamically.
    class _StateWithEngine:
        """Proxy that exposes engine from the mutable cell."""
        def __getattr__(self, name: str):
            if name == "engine":
                if _engine_cell:
                    return _engine_cell[0]
                raise AttributeError("'State' object has no attribute 'engine' (lifespan not started?)")
            return object.__getattribute__(self, name)

        def __setattr__(self, name: str, value) -> None:
            object.__setattr__(self, name, value)

    # Replace app.state with our proxy that exposes engine
    outer_app.state = _StateWithEngine()
    outer_app.state._engine_cell = _engine_cell

    app = outer_app

    # ── Routes registered BEFORE StaticFiles mount (Pitfall E) ──────────────────

    @app.get("/api/health")
    async def health() -> JSONResponse:
        """Docker HEALTHCHECK endpoint — always returns 200 OK (no auth needed)."""
        return JSONResponse({"status": "ok"})

    # GET/PUT /api/settings + GET /api/settings/env-locked (SVC-02, D-70)
    # Registered BEFORE StaticFiles (Pitfall E)
    from trezarr.web.routes.settings import router as settings_router  # noqa: PLC0415
    app.include_router(settings_router, prefix="/api")

    # POST /api/test/{sonarr|radarr|bazarr|llm} — connection-test endpoints (D-71)
    # Registered BEFORE StaticFiles (Pitfall E)
    from trezarr.web.routes.test_connection import router as test_connection_router  # noqa: PLC0415
    app.include_router(test_connection_router, prefix="/api")

    # GET /api/queue, GET /api/jobs, GET /api/jobs/{id}/logs (SVC-03, D-75)
    # Registered BEFORE StaticFiles (Pitfall E)
    from trezarr.web.routes.queue import router as queue_router  # noqa: PLC0415
    app.include_router(queue_router, prefix="/api")

    # POST /api/jobs/{id}/retry (SVC-04, D-74)
    # Registered BEFORE StaticFiles (Pitfall E)
    from trezarr.web.routes.jobs import router as jobs_router  # noqa: PLC0415
    app.include_router(jobs_router, prefix="/api")

    # Bible editor endpoints (BIBLE-08) — registered before StaticFiles (Pitfall E)
    from trezarr.web.routes.bible import router as bible_router  # noqa: PLC0415
    app.include_router(bible_router, prefix="/api")

    # POST /webhook — Sonarr/Radarr/Bazarr inbound webhooks (AUTO-02, D-66)
    # Registered BEFORE StaticFiles (Pitfall E: StaticFiles matches all remaining paths)
    from trezarr.web.routes.webhook import router as webhook_router  # noqa: PLC0415
    app.include_router(webhook_router)  # no prefix — /webhook is top-level (not /api/webhook)

    # ── SPA static file mount — LAST (Pitfall E: StaticFiles must be after routes) ─
    _static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(_static_dir):
        from fastapi.staticfiles import StaticFiles  # noqa: PLC0415

        app.mount("/", StaticFiles(directory=_static_dir, html=True), name="spa")
        logger.info("Serving SPA from %s", _static_dir)
    else:
        logger.info(
            "SPA static directory %s not found — frontend not built yet "
            "(normal in development without `npm run build`)",
            _static_dir,
        )

    return app


# ── Module-level app instance (for uvicorn string reference) ───────────────────
# This is the app uvicorn imports when launched via `trezarr serve`.
# For tests, prefer create_app() to get a fresh instance with isolated lifespan.
app = create_app()


# ── Serve entry point (D-62 / D-61) ────────────────────────────────────────────


def run_serve(config_path: str | None = None) -> None:
    """Start the uvicorn server — called by `trezarr serve` CLI subcommand (D-62).

    Loads TrezarrSettings (with optional config_path override) then launches
    uvicorn. Do NOT use reload=True (single-process daemon, per D-61).

    Args:
        config_path: Optional path to a YAML config file. Overrides CONFIG_PATH
                     for this instantiation (passed as _yaml_file to TrezarrSettings).
    """
    import uvicorn  # noqa: PLC0415

    settings = TrezarrSettings(_yaml_file=config_path) if config_path else TrezarrSettings()
    uvicorn.run(
        "trezarr.web.app:app",
        host=settings.web_host,
        port=settings.web_port,
        log_level="info",
    )
