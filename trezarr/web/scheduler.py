"""APScheduler poll callback for continuous monitoring (AUTO-02, D-65, D-66).

Design decisions honoured:
  D-65  Hybrid trigger — APScheduler interval poll is the source of truth;
        inbound webhook is the low-latency complement. Both call poll_and_enqueue.
  D-66  Enqueue-only: poll_and_enqueue runs discover → scan → enqueue. Translation
        happens ONLY in the worker. Dedup via enqueue_job guard (D-66 / worker.py).
  D-77  setup_scheduler gates on settings.enable_webhooks (scheduler toggle) at call
        time. The scheduler itself is always started inside the lifespan (Pitfall B).

Anti-patterns avoided:
  - Pitfall B: scheduler.start() is NOT called here — it is called inside the
    FastAPI lifespan after the uvicorn event loop is running. setup_scheduler only
    registers the job; the caller (lifespan) calls scheduler.start().
  - Pitfall D: poll_and_enqueue never calls translate_file — it only enqueues.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)


async def poll_and_enqueue(
    session_factory,
    settings: "TrezarrSettings | None",
    ledger=None,
    media_roots: list | None = None,
    llm_client=None,
    series_id_hint: int | None = None,
) -> None:
    """Discover eligible items and enqueue them for translation (D-65/D-66).

    Body mirrors cli.py lines 229–273 (discover + scan + enqueue sequence):
      1. If settings.sonarr_enabled: discover_sonarr_items; catch DiscoveryError (log, continue)
      2. If settings.radarr_enabled: discover_radarr_items; catch DiscoveryError (log, continue)
      3. Combine items; call scan_for_eligible_items(items, ledger, lang_priority)
      4. For each eligible_item: await enqueue_job(session_factory, source_path, series_id, trigger="poll")
      5. If series_id_hint is provided, filter to items matching that series_id before enqueueing

    Graceful no-op when session_factory or settings is None (test/startup stub path).

    Args:
        session_factory:  Async session factory. None is a no-op (test stub).
        settings:         TrezarrSettings. None is a no-op (test stub).
        ledger:           LedgerSQLA instance for gap detection. None skips scan.
        media_roots:      Path list for assert_within_media_roots guard.
        llm_client:       LLMClient (passed through; not used in enqueue path).
        series_id_hint:   Optional series_id from a webhook payload. When provided,
                          filters eligible items to those matching that series_id,
                          narrowing the enqueue scope (fast-path for webhook trigger).
                          The series_id is only a hint — discovery goes through
                          Sonarr/Radarr (authoritative source), never the payload path.
    """
    if session_factory is None or settings is None:
        # Permissive no-op for tests and pre-configuration startup
        logger.debug("poll_and_enqueue: session_factory or settings is None — skipping")
        return

    if not getattr(settings, "auto_translate_enabled", False):
        logger.debug(
            "poll_and_enqueue: auto_translate_enabled=False — skipping auto-translate sweep"
        )
        return

    from trezarr.arr import DiscoveryError  # noqa: PLC0415
    from trezarr.arr.radarr import discover_radarr_items  # noqa: PLC0415
    from trezarr.arr.sonarr import discover_sonarr_items  # noqa: PLC0415
    from trezarr.discover.scan import scan_for_eligible_items  # noqa: PLC0415
    from trezarr.web.worker import enqueue_job  # noqa: PLC0415

    items: list = []

    # Step 1 — Sonarr discovery (per-service resilience: D-30)
    if settings.sonarr_enabled:
        try:
            sonarr_items = discover_sonarr_items(settings)
            items.extend(sonarr_items)
            logger.debug(
                "poll_and_enqueue: Sonarr discovered %d items", len(sonarr_items)
            )
        except DiscoveryError as exc:
            # Per D-30: one *arr down does not abort the whole poll — log and continue
            logger.error(
                "poll_and_enqueue: Sonarr discovery failed — %s; continuing with Radarr",
                exc,
            )

    # Step 2 — Radarr discovery (per-service resilience: D-30)
    if settings.radarr_enabled:
        try:
            radarr_items = discover_radarr_items(settings)
            items.extend(radarr_items)
            logger.debug(
                "poll_and_enqueue: Radarr discovered %d items", len(radarr_items)
            )
        except DiscoveryError as exc:
            logger.error(
                "poll_and_enqueue: Radarr discovery failed — %s; continuing without Radarr",
                exc,
            )

    if not items:
        logger.debug("poll_and_enqueue: no items discovered; nothing to enqueue")
        return

    # Step 3 — scan for eligible items (requires ledger; skip scan if ledger is None)
    if ledger is None:
        logger.debug(
            "poll_and_enqueue: ledger is None — skipping scan; no items enqueued"
        )
        return

    eligible, stats = await scan_for_eligible_items(
        items,
        ledger,
        settings.source_lang_priority,
    )

    logger.info(
        "poll_and_enqueue: scanned=%d eligible=%d no_source=%d foreign_vi=%d already_done=%d",
        stats.scanned,
        len(eligible),
        stats.no_source,
        stats.foreign_vi,
        stats.already_done,
    )

    # Step 4 — enqueue eligible items (with optional series_id_hint filter)
    enqueued = 0
    for eligible_item in eligible:
        item_series_id = getattr(eligible_item.media_item, "series_id", None)

        # Step 5 — apply series_id_hint filter (webhook fast-path)
        if series_id_hint is not None and item_series_id != series_id_hint:
            # Not the series the webhook was about — skip for this poll pass
            continue

        queued = await enqueue_job(
            session_factory,
            str(eligible_item.source_sub_path),
            item_series_id,
            trigger="poll",
            media_item=eligible_item.media_item,
        )
        if queued:
            enqueued += 1

    logger.info(
        "poll_and_enqueue: enqueued=%d (series_id_hint=%s)", enqueued, series_id_hint
    )


def setup_scheduler(
    scheduler,
    session_factory,
    settings: "TrezarrSettings",
    ledger,
    media_roots: list,
    llm_client,
) -> None:
    """Register the main_poll interval job on the scheduler (D-65).

    IMPORTANT: This function only REGISTERS the job. The caller (FastAPI lifespan)
    is responsible for calling scheduler.start() AFTER the uvicorn event loop is
    running — Pitfall B: scheduler.start() must never be called at module scope or
    before the event loop exists.

    Args:
        scheduler:        AsyncIOScheduler instance (already created, not yet started).
        session_factory:  Async session factory — passed through to poll_and_enqueue.
        settings:         TrezarrSettings — determines the poll interval (D-76).
        ledger:           LedgerSQLA for gap detection.
        media_roots:      Path list for assert_within_media_roots guard.
        llm_client:       LLMClient instance.
    """
    scheduler.add_job(
        poll_and_enqueue,
        "interval",
        seconds=settings.poll_interval_seconds,
        id="main_poll",
        replace_existing=True,
        kwargs=dict(
            session_factory=session_factory,
            settings=settings,
            ledger=ledger,
            media_roots=media_roots,
            llm_client=llm_client,
        ),
    )
    logger.info(
        "setup_scheduler: registered main_poll job (interval=%ds)",
        settings.poll_interval_seconds,
    )
