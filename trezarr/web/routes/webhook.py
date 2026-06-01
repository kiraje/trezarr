"""FastAPI /webhook endpoint — enqueue-only handler for Sonarr/Radarr/Bazarr (AUTO-02, D-66).

Design decisions honoured:
  D-66  Enqueue-only: handler creates a background asyncio.Task that runs
        poll_and_enqueue(). The handler itself NEVER awaits translate_file or any
        long-running work (Pitfall D). Returns 200 immediately.
  D-77  enable_webhooks toggle: if settings.enable_webhooks is False, return 503
        immediately. The router is always registered; the toggle is enforced inside
        the handler (not at registration time) to keep routing predictable.
  D-78  Trusted-LAN, no auth. POST /webhook is open to the configured *arr services
        on the local network — no API key check (D-78). The payload's file paths
        are NEVER trusted; discovery goes through Sonarr/Radarr APIs (D-66 / SSRF
        mitigation T-07-03-02).

STRIDE Threat mitigations:
  T-07-03-01 (DoS flood): One asyncio.Task per request; enqueue_job dedup inside
             poll_and_enqueue ensures a flood creates at most one queued job per
             unique source_path.
  T-07-03-03 (translate_file in handler): Enforced by using asyncio.create_task
             — handler returns before the task runs (event loop yields only after
             return). No await on poll_and_enqueue in request scope.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Strong references to in-flight background asyncio.Tasks (CR-02).
# asyncio holds only a weak reference to tasks — without a strong reference here,
# the GC can collect the poll_and_enqueue task mid-execution under memory pressure
# (asyncio docs warning). Each task is added at creation and removed via
# add_done_callback when it completes.
_background_tasks: set[asyncio.Task] = set()


@router.post("/webhook")
async def receive_webhook(request: Request) -> JSONResponse:
    """Accept an inbound webhook from Sonarr, Radarr, or Bazarr and trigger a scan.

    The handler:
      1. Parses the JSON body (ignores unrecognised fields).
      2. Extracts eventType and a series_id hint (Sonarr: body.series.id;
         Radarr: body.movie.id; Bazarr or others: None).
      3. Fires poll_and_enqueue as a background asyncio.Task — NOT awaited here.
      4. Returns {"status": "accepted", "eventType": eventType} with HTTP 200.

    CRITICAL: This handler MUST NOT await poll_and_enqueue or translate_file
    (Pitfall D / T-07-03-03). A flood of webhook POSTs each creates one Task;
    enqueue_job inside poll_and_enqueue deduplicates via the DB guard (D-66).

    Payload extraction (T-07-03-02 — never trust payload file paths):
      - series_id is extracted ONLY as a filtering hint for poll_and_enqueue.
        It narrows the discovery scan to one series — it does not bypass pyarr.
      - episodeFile.path / movieFile.path from the payload is COMPLETELY IGNORED.
        Actual eligible paths come from Sonarr/Radarr API calls inside
        poll_and_enqueue (authoritative source).

    Args:
        request: FastAPI Request. App state must expose: session_factory, settings,
                 ledger, media_roots, llm_client (all set by the lifespan in app.py).

    Returns:
        JSONResponse with {"status": "accepted", "eventType": <str>} and HTTP 200,
        or {"status": "disabled"} with HTTP 503 if enable_webhooks is False (D-77).
    """
    from trezarr.web.scheduler import poll_and_enqueue  # noqa: PLC0415

    # D-77 toggle: check settings on the app state
    settings = getattr(request.app.state, "settings", None)
    if settings is not None and not settings.enable_webhooks:
        logger.info("receive_webhook: webhooks disabled (enable_webhooks=False) — returning 503")
        return JSONResponse(
            {"status": "disabled", "reason": "webhooks are disabled in settings"},
            status_code=503,
        )

    # Parse body — gracefully handle malformed JSON
    try:
        body = await request.json()
    except Exception:
        body = {}

    event_type: str = body.get("eventType", "unknown") if isinstance(body, dict) else "unknown"

    # Extract series_id hint — Sonarr uses body.series.id; Radarr uses body.movie.id
    # We ONLY use this as a filter hint inside poll_and_enqueue, never as a file path.
    series_id: int | None = None
    if isinstance(body, dict):
        series_block = body.get("series", {})
        movie_block = body.get("movie", {})
        if isinstance(series_block, dict) and series_block.get("id") is not None:
            try:
                series_id = int(series_block["id"])
            except (TypeError, ValueError):
                series_id = None
        elif isinstance(movie_block, dict) and movie_block.get("id") is not None:
            try:
                series_id = int(movie_block["id"])
            except (TypeError, ValueError):
                series_id = None

    logger.info(
        "receive_webhook: eventType=%s series_id_hint=%s — triggering background scan",
        event_type,
        series_id,
    )

    # Retrieve app state values set by the lifespan
    session_factory = getattr(request.app.state, "session_factory", None)
    ledger = getattr(request.app.state, "ledger", None)
    media_roots = getattr(request.app.state, "media_roots", None)
    llm_client = getattr(request.app.state, "llm_client", None)

    # Fire poll_and_enqueue as a background asyncio.Task — NOT awaited here.
    # The handler returns 200 immediately; the task runs after we yield (D-66 / Pitfall D).
    # T-07-03-01: each webhook creates at most one Task; dedup inside enqueue_job
    # ensures a flood of requests creates at most one queued job per source_path.
    # CR-02: hold a strong reference to the task via _background_tasks so the GC
    # cannot collect it mid-execution. The done_callback removes it when complete.
    t = asyncio.create_task(
        poll_and_enqueue(
            session_factory,
            settings,
            ledger=ledger,
            media_roots=media_roots,
            llm_client=llm_client,
            series_id_hint=series_id,
        )
    )
    _background_tasks.add(t)
    t.add_done_callback(_background_tasks.discard)

    return JSONResponse({"status": "accepted", "eventType": event_type})
