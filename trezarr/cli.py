"""One-shot CLI entry point: `trezarr run --once`; long-running daemon: `trezarr serve`.

Design decisions honoured:
  D-21  One-shot CLI. No daemon, scheduler, webhook, or watcher — Phase 7.
  D-22  Discovery via pyarr; per-service resilience at this orchestration boundary.
  D-23  Path mapping applied inside discover_*_items; cli passes settings through.
  D-24  Startup probe (probe_media_roots) runs BEFORE any *arr API call.
  D-29  assert_media_roots_configured runs FIRST (refuses empty path_mappings
        when any *arr enabled); assert_within_media_roots guards every write
        path before apply_permissions; apply_permissions enforces PUID/PGID/UMASK.
  D-30  Per-item quarantine on failure; run continues; end-of-run summary; non-zero
        exit on any failure.
  D-62  process_one_item: shared async callable extracted from the per-item loop body
        of _run_pipeline_steps. Both the CLI loop and the worker's _execute_job call
        this function — no logic duplication. trezarr run --once behavior UNCHANGED.

Codex review fixes (03-REVIEWS.md):
  HIGH #2   assert_media_roots_configured before probe (refuse empty path_mappings
            when arr enabled).
  HIGH #6   _run_once() returns int; main() wraps in raise SystemExit(...).
  HIGH #7   LLMClient instantiated only when eligible list is non-empty.
  MEDIUM #10  except DiscoveryError per-service for per-service resilience.
  MEDIUM #13  except PermissionApplyError → quarantine the item.
  MEDIUM #14  widened summary fields (discovered=, eligible=, translated=,
              translate_skipped=, scan_skipped=, quarantined=, failed=).

Notes:
  - WR-06: the cli-layer MediaItem dataclass that previously lived here moved
    to ``tests/_helpers/cli_media_item.py``. Production never constructed it
    — _run_once consumes ``trezarr.arr.sonarr.MediaItem`` instances produced
    by discover_*_items, and the translate loop reads
    ``EligibleItem.source_sub_path`` directly off the EligibleItem dataclass,
    never off the inner media_item attribute. The dataclass lived under
    ``trezarr.cli`` purely for test-stub convenience and was a maintainability
    hazard (next reviewer assumes it's part of the production contract).
  - SEQUENTIAL translate loop: LLMClient.semaphore handles concurrency
    WITHIN translate_file. Adding a second asyncio.Semaphore around the
    item loop would double-cap and fight the LLM semaphore.
  - Phase 7: replace with AsyncSonarr/AsyncRadarr + asyncio.gather for parallel
    item discovery across large libraries (currently sequential per *arr).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from trezarr.arr import DiscoveryError
from trezarr.arr.radarr import discover_radarr_items
from trezarr.arr.sonarr import discover_sonarr_items
from trezarr.config import TrezarrSettings
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import migrate_json_ledger_if_needed, run_migrations_to_head
from trezarr.db.session import build_session_factory
from trezarr.discover.scan import scan_for_eligible_items
from trezarr.llm.client import LLMClient
from trezarr.output.ledger_sqla import LedgerSQLA
from trezarr.output.write import PermissionApplyError, apply_permissions
from trezarr.paths import (
    assert_media_roots_configured,
    assert_within_media_roots,
    build_media_roots,
    probe_media_roots,
)
from trezarr.translate.engine import translate_file

logger = logging.getLogger(__name__)


# ── Shared per-item result type (D-62) ─────────────────────────────────────────


@dataclass
class ItemResult:
    """Outcome of processing one eligible subtitle item (D-62).

    Returned by process_one_item and consumed by both the CLI loop
    (_run_pipeline_steps) and the worker (_execute_job in trezarr/web/worker.py).
    """

    status: Literal["done", "skipped", "quarantined", "error"]
    output_path: str | None = None
    error: Exception | None = None
    reason: str | None = None


# ── Shared per-item callable (D-62) ────────────────────────────────────────────


async def process_one_item(
    eligible_item,
    settings: TrezarrSettings,
    llm_client: LLMClient | None,
    ledger: LedgerSQLA,
    media_roots: list,
    session_factory=None,
) -> ItemResult:
    """Translate one eligible subtitle item and apply PUID/PGID permissions.

    This is the shared callable that both the CLI loop (via _run_pipeline_steps)
    and the queue worker (via trezarr.web.worker._execute_job) invoke. Extracting
    it eliminates logic duplication (D-62) and ensures the daemon worker reuses
    the exact same production path as `trezarr run --once`.

    Steps performed (mirrors the original _run_pipeline_steps per-item body):
      0. resolve_effective_settings — per-series source priority + model override (D-112).
      1. translate_file — runs the full 3-pass + self-review pipeline.
      2. Path-traversal guard (assert_within_media_roots) if media_roots is non-empty.
      3. apply_permissions — enforces PUID/PGID/umask on the output file.
      4. PermissionApplyError → quarantine (INTG-04, MEDIUM #13).

    The caller (CLI loop or worker) is responsible for catching any unhandled
    Exception at the batch boundary (D-30 batch resilience).

    Args:
        eligible_item: EligibleItem produced by scan_for_eligible_items.
        settings:      Loaded TrezarrSettings.
        llm_client:    LLMClient instance (or None for passthrough mode).
        ledger:        LedgerSQLA bound to the live session factory.
        media_roots:   Path-traversal guard root list (D-29). Empty list = passthrough.
        session_factory: Async session factory for Bible-aware translation (D-48).

    Returns:
        ItemResult with status ∈ {done, skipped, quarantined, error}.
    """
    # Step 0 — D-112: resolve per-series effective settings before translate_file.
    # Load series_dto from DB if session_factory is available and media_item has
    # the required arr identity; degrade gracefully to global settings if not.
    from trezarr.source_selection.resolve import resolve_effective_settings  # noqa: PLC0415

    series_dto = None
    # eligible_item may be an EligibleItem (has .media_item) or a test MediaItem stub.
    # Use getattr to handle both gracefully (D-104: degrade to global settings if not found).
    media_item = getattr(eligible_item, "media_item", eligible_item)
    arr_kind = getattr(media_item, "arr_kind", None)
    arr_series_id = getattr(media_item, "series_id", None)

    if session_factory is not None and arr_kind and arr_series_id is not None:
        try:
            from trezarr.bible.store import get_series_by_arr_id  # noqa: PLC0415
            series_dto = await get_series_by_arr_id(
                session_factory, arr_kind=arr_kind, arr_series_id=arr_series_id
            )
        except Exception:
            # D-104 graceful degradation: DB error → use global settings
            logger.debug(
                "Failed to load series_dto for arr_kind=%s arr_series_id=%s — using global settings",
                arr_kind, arr_series_id,
            )

    _source_priority, _register, effective_model = resolve_effective_settings(series_dto, settings)

    # Bazarr inventory wiring (D-104, D-112): if enabled, fetch inventory for better source selection.
    # Note: eligible_item.source_sub_path is already selected by scan; this provides the inventory
    # for any re-translation path that calls select_source_for_item within translate_file.
    if settings.bazarr_enabled and settings.bazarr_use_inventory and arr_kind == "sonarr" and arr_series_id:
        try:
            from trezarr.arr.bazarr import BazarrClient, BazarrError  # noqa: PLC0415
            bazarr_client = BazarrClient.from_settings(settings)
            _bazarr_inventory = await bazarr_client.fetch_episodes(arr_series_id)
        except Exception as exc:
            # D-104: BazarrError or any error → degrade to None (Bazarr unreachable must never block)
            logger.warning(
                "Bazarr inventory unavailable for series_id=%s: %s — degrading to filesystem scan",
                arr_series_id, exc,
            )
            _bazarr_inventory = None
    else:
        _bazarr_inventory = None

    # WR-03 / D-109: use select_source_for_item to apply the per-series source
    # priority + Bazarr inventory to select the best available source path.
    # This wires the D-109 fallback chain that was previously computed but discarded.
    # D-104 graceful degradation: if selection or path resolution fails, fall back
    # to the path that scan_for_eligible_items already chose.
    source_sub_path = eligible_item.source_sub_path  # default: scan's choice
    try:
        from trezarr.discover.scan import select_source_for_item  # noqa: PLC0415
        from trezarr.discover.scan import find_source_sub  # noqa: PLC0415

        # Per-series source override: pass it only when it actually differs from
        # global settings (None = let ranking decide; no artificial override).
        per_series_override = (
            _source_priority
            if _source_priority != settings.source_lang_priority
            else None
        )
        best_lang = select_source_for_item(
            media_item,
            settings,
            bazarr_inventory=_bazarr_inventory,
            per_series_source_override=per_series_override,
        )
        if best_lang is not None:
            # Resolve the language code to a real path on the filesystem.
            # find_source_sub([best_lang]) returns the first (and only) matching
            # file for that language — or None if the file is gone (TOCTOU).
            media_path = getattr(media_item, "local_path", None)
            if media_path is not None:
                fs_result = find_source_sub(media_path, [best_lang])
                if fs_result is not None:
                    source_sub_path = fs_result[0]
    except Exception:
        # D-104: any error in source selection → degrade to scan's existing choice.
        logger.debug(
            "Source selection failed for %s — using scan's source: %s",
            getattr(media_item, "local_path", "?"), eligible_item.source_sub_path,
        )
        source_sub_path = eligible_item.source_sub_path

    result = await translate_file(
        source_sub_path,
        settings,
        llm_client,
        ledger,
        eligible_item=eligible_item,
        session_factory=session_factory,
        model=effective_model,  # D-113: per-series model override threads here
    )

    if result.status == "done":
        if result.output_path is None:
            # Defensive: status="done" must always carry an output_path.
            logger.error(
                "translate_file returned status='done' but output_path is None for %s",
                source_sub_path,
            )
            return ItemResult(status="error")

        # Path-traversal guard before write-permission application (D-29).
        # Only fire when media_roots is non-empty.
        if media_roots:
            try:
                assert_within_media_roots(result.output_path, media_roots)
            except ValueError as exc:
                logger.error(
                    "path-traversal guard rejected output_path=%s: %s",
                    result.output_path, exc,
                )
                return ItemResult(status="error", output_path=result.output_path, error=exc)

        try:
            apply_permissions(
                result.output_path,
                settings.puid,
                settings.pgid,
                settings.umask,
            )
            return ItemResult(status="done", output_path=result.output_path)
        except PermissionApplyError as perm_exc:
            # chmod failure → INTG-04 readability at risk. Quarantine the item
            # so exit code surfaces the broken contract (MEDIUM #13).
            logger.warning(
                "item quarantined due to chmod failure on %s: %s",
                result.output_path, perm_exc,
            )
            return ItemResult(
                status="quarantined",
                output_path=result.output_path,
                error=perm_exc,
                reason=str(perm_exc),
            )

    elif result.status == "skipped":
        return ItemResult(status="skipped")

    elif result.status == "quarantined":
        logger.warning(
            "item quarantined by translate_file: %s (reason=%s)",
            source_sub_path, result.reason,
        )
        return ItemResult(
            status="quarantined",
            reason=getattr(result, "reason", None),
        )

    else:
        # Defensive: unrecognised status is a contract violation.
        logger.error(
            "translate_file returned unknown status %r for %s",
            result.status, source_sub_path,
        )
        return ItemResult(status="error")


# ── Main entry point ───────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser (exposed for testing).

    Separating parser construction from main() lets tests call _build_parser()
    to probe the subcommand tree without executing any dispatch logic.
    """
    parser = argparse.ArgumentParser(
        prog="trezarr",
        description="Automated Vietnamese subtitle translator for the *arr media stack.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="Run one pass of the discover → translate → write pipeline and exit (D-21).",
    )
    run_parser.add_argument(
        "--once",
        action="store_true",
        required=True,
        help="Required flag for the one-shot run (D-21). No daemon mode in Phase 3.",
    )
    run_parser.add_argument(
        "--config",
        default=None,
        help="Optional path to a YAML config file (overrides /config/config.yaml default).",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the long-running daemon service (D-61, SVC-01).",
    )
    serve_parser.add_argument(
        "--config",
        default=None,
        help="Optional path to a YAML config file (overrides /config/config.yaml default).",
    )

    return parser


def main() -> None:
    """Console-scripts entry point: `trezarr run --once` or `trezarr serve`.

    Per 03-REVIEWS.md HIGH #6: the only sys.exit / SystemExit translation point
    is here. _run_once() returns an int; main() wraps it in raise SystemExit(...).
    D-62: `trezarr serve` dispatches to trezarr.web.app.run_serve — the daemon
    entry point. `trezarr run --once` behavior is unchanged.
    """
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "run" and args.once:
        # HIGH #6: wrap the async int return in SystemExit at the ONLY translation
        # point. _run_once never calls sys.exit() itself.
        raise SystemExit(asyncio.run(_run_once(args.config)))

    elif args.command == "serve":
        from trezarr.web.app import run_serve  # noqa: PLC0415 — lazy import avoids circular dep
        run_serve(args.config)


async def _run_once(config_path: str | None) -> int:
    """Execute one pass of the Phase-3 vertical slice and return an int exit code.

    Per 03-REVIEWS.md HIGH #6: returns an int rather than calling sys.exit().
    main() wraps the int in raise SystemExit(...). This keeps _run_once
    directly testable as a normal coroutine (no pytest.raises(SystemExit)).

    Step sequence (per 03-04 SUMMARY Next Plan Readiness section + 04-04 wiring):

      1. Load settings (+ basicConfig logging)
      2. assert_media_roots_configured(settings)               ← HIGH #2, runs FIRST
      3. build_media_roots(settings) → probe_media_roots(roots) ← D-24
      3.5 DB startup: build_engine → run_migrations_to_head → migrate_json_ledger_if_needed
          → LedgerSQLA construction                           ← 04-04 / D-37 / D-38
      4. Per-service discover (Sonarr, Radarr) with except DiscoveryError ← MEDIUM #10
      5. LedgerSQLA + scan_for_eligible_items                  ← D-25/D-26/D-27/D-28
      6. LLMClient(settings) ONLY if eligible is non-empty      ← HIGH #7
      7. Sequential translate loop with per-item quarantine    ← D-30
      8. Widened summary + return int exit code                ← MEDIUM #14

    Args:
        config_path: Optional YAML config-file path (None = use /config/config.yaml
                     default; or whatever TREZARR_CONFIG_PATH points at).

    Returns:
        int exit code: 0 on full success, 1 on any per-item failure / quarantine /
        all-discovery-failed condition.
    """
    # Step 1 — Load settings + logging
    settings = TrezarrSettings(_yaml_file=config_path) if config_path else TrezarrSettings()
    logging.basicConfig(level=logging.INFO)

    # Step 2 — Startup configuration check (HIGH #2). Refuses empty path_mappings
    # when any *arr is enabled. Calls sys.exit(1) on misconfiguration — this is
    # intentionally not recoverable (an empty media_roots set would silently
    # disable the D-29 traversal guard).
    assert_media_roots_configured(settings)

    # Step 3 — Startup probe (D-24, fail-fast before any API call). Mandatory
    # R_OK|X_OK checks call sys.exit on failure; non-W_OK is a soft warning.
    media_roots = build_media_roots(settings)
    probe_media_roots(media_roots)

    # Step 3.5a — DB engine + Alembic migrations (hard-fatal on failure).
    # Schema must be ready before any translate work; mirrors probe_media_roots
    # fail-fast severity — per RESEARCH §Open Question 3.
    #
    # CR-01: the AsyncEngine holds aiosqlite worker threads that schedule
    # coroutines onto this event loop. If the engine is not disposed before
    # asyncio.run() tears down the loop, the worker thread later tries to
    # schedule onto a closed loop and raises `RuntimeError: Event loop is
    # closed`. The engine is created BEFORE the outer try so its existence
    # is unambiguous on every dispose path; on build_engine failure we never
    # reach the try/finally.
    try:
        engine = build_engine(settings)
    except Exception as exc:
        logger.error(
            "DB startup failed — cannot continue. "
            "Check your bible_db_url setting and disk permissions. Error: %s",
            exc,
            exc_info=True,
        )
        return 1

    # CR-01: every code path below MUST go through the finally block so the
    # AsyncEngine is disposed before asyncio.run() tears down the event loop.
    try:
        try:
            await run_migrations_to_head(engine)
            session_factory = build_session_factory(engine)
            ledger: LedgerSQLA = LedgerSQLA(session_factory)
        except Exception as exc:
            logger.error(
                "DB startup failed — cannot continue. "
                "Check your bible_db_url setting and disk permissions. Error: %s",
                exc,
                exc_info=True,
            )
            return 1

        # Step 3.5b — JSON ledger one-shot migration (best-effort per D-37 forgiveness).
        # A failure here starts SQLite with an empty ledger but does NOT abort the run.
        # Asymmetric vs. Step 3.5a: the translate loop can still run without the old JSON data.
        try:
            await migrate_json_ledger_if_needed(session_factory, settings)
        except Exception as exc:
            logger.error(
                "DB startup failed — JSON ledger migration failed (%s). "
                "Continuing with an empty SQLite ledger (D-37 forgiveness). "
                "Prior processed_files.json entries will NOT be migrated on this run.",
                exc,
                exc_info=True,
            )

        return await _run_pipeline_steps(settings, ledger, media_roots, session_factory)
    finally:
        # CR-01: ALWAYS dispose the AsyncEngine before this coroutine returns —
        # otherwise aiosqlite worker threads outlive the event loop and the
        # next finalization attempt raises `RuntimeError: Event loop is closed`.
        await engine.dispose()


async def _run_pipeline_steps(
    settings: TrezarrSettings,
    ledger: LedgerSQLA,
    media_roots: list,
    session_factory=None,
) -> int:
    """Steps 4-8 of _run_once factored out so cli's try/finally around engine
    dispose stays compact and readable.

    Args:
        settings:        Loaded TrezarrSettings.
        ledger:          LedgerSQLA bound to the live session_factory.
        media_roots:     Path-traversal guard root list (D-29).
        session_factory: Async session factory for Phase-5 Bible-aware translation
                         (D-48). None for backward compat (mechanical translation only).

    Returns:
        int exit code (0 on full success; 1 on any per-item failure /
        quarantine / all-discovery-failed condition).
    """
    # Step 4 — Discovery with per-service resilience (MEDIUM #10).
    # One *arr down does NOT abort the run if the other is healthy.
    all_items: list = []
    discovery_failures: list[str] = []

    try:
        sonarr_items = discover_sonarr_items(settings)
        all_items.extend(sonarr_items)
        if sonarr_items:
            logger.info("Sonarr discovered %d items", len(sonarr_items))
    except DiscoveryError as exc:
        logger.error("Sonarr discovery failed: %s", exc)
        discovery_failures.append(f"sonarr: {exc}")

    try:
        radarr_items = discover_radarr_items(settings)
        all_items.extend(radarr_items)
        if radarr_items:
            logger.info("Radarr discovered %d items", len(radarr_items))
    except DiscoveryError as exc:
        logger.error("Radarr discovery failed: %s", exc)
        discovery_failures.append(f"radarr: {exc}")

    enabled_arr = (1 if settings.sonarr_enabled else 0) + (1 if settings.radarr_enabled else 0)
    all_arr_failed = enabled_arr > 0 and len(discovery_failures) == enabled_arr
    if all_arr_failed:
        # WR-04: all enabled *arr services failed — log this at the same
        # severity used by D-30 batch resilience (logger.error, not warning)
        # and emit a distinct one-line operator notice BEFORE the summary so
        # the "discovery_failures=N" suffix isn't easy to overlook. The run
        # still completes the summary line (for symmetry with the partial-
        # failure case) and exits non-zero.
        logger.error(
            "All enabled *arr services failed discovery (%d of %d): %s",
            len(discovery_failures), enabled_arr, "; ".join(discovery_failures),
        )
        print(
            "ALL DISCOVERY FAILED — see logs above; the run will exit non-zero "
            "after the summary line.",
            flush=True,
        )

    n_discovered = len(all_items)
    logger.info("Discovered %d total media items", n_discovered)

    # Step 5 — Scan for eligible items using LedgerSQLA (D-25/D-26/D-27/D-28).
    # scan_for_eligible_items is async (Phase 4 — is_eligible and ledger.check are async).
    eligible, scan_stats = await scan_for_eligible_items(
        all_items, ledger, settings.source_lang_priority,
    )
    n_eligible = len(eligible)
    logger.info("%d items eligible for translation", n_eligible)

    # Step 6 — LLMClient construction (HIGH #7 — ONLY when there is work to do).
    # Avoids the LLM endpoint-config tax on empty / discovery-only runs.
    llm_client: LLMClient | None = None
    if n_eligible > 0:
        llm_client = LLMClient(settings)

    # Step 7 — Sequential translate loop with per-item quarantine (D-30).
    # Uses process_one_item (D-62 shared callable) so the CLI and the daemon
    # worker execute identical per-item logic.
    n_done = 0
    n_translate_skipped = 0
    n_quar = 0
    n_fail = 0

    for eligible_item in eligible:
        source_sub_path = eligible_item.source_sub_path
        try:
            item_result = await process_one_item(
                eligible_item,
                settings,
                llm_client,
                ledger,
                media_roots,
                session_factory=session_factory,
            )
            if item_result.status == "done":
                n_done += 1
            elif item_result.status == "skipped":
                n_translate_skipped += 1
            elif item_result.status == "quarantined":
                n_quar += 1
            else:  # "error"
                n_fail += 1

        except Exception:
            # D-30 batch resilience — one bad item never aborts the slice.
            # WR-05: logger.exception captures the traceback automatically.
            # Pre-WR-05 the operator only saw "unhandled error translating
            # <path>: <exc>" with no stack — root-causing an unexpected
            # failure mode required guessing or adding ad-hoc prints.
            logger.exception("unhandled error translating %s", source_sub_path)
            n_fail += 1

    # Step 8 — Widened summary (MEDIUM #14) + exit code (D-30).
    # WR-03: `scan_stats.error` is a transient I/O error count and must be
    # surfaced separately from no_source (a missing-source skip). It is
    # included in scan_skipped for the headline total but broken out in the
    # parenthesised breakdown alongside the existing pre-translate counters.
    # WR-08: read scan_stats.error directly (no getattr defensive fallback).
    # ScanStats is a typed dataclass with `error: int = 0` — the attribute is
    # always present on real returns. The previous defensive `getattr(...,
    # "error", 0)` only papered over test sloppiness (test MagicMocks built
    # without the field); silencing a future real contract break (e.g. a
    # rename of ScanStats.error) into a silent zero would lose operator
    # visibility. Tests now provide the full ScanStats shape.
    n_scan_skipped = (
        scan_stats.no_source
        + scan_stats.foreign_vi
        + scan_stats.already_done
        + scan_stats.error
    )
    summary = (
        f"Run complete: discovered={n_discovered}, eligible={n_eligible}, "
        f"translated={n_done}, translate_skipped={n_translate_skipped}, "
        f"scan_skipped={n_scan_skipped} "
        f"(no_source={scan_stats.no_source}, "
        f"foreign_vi={scan_stats.foreign_vi}, "
        f"already_done={scan_stats.already_done}, "
        f"error={scan_stats.error}), "
        f"quarantined={n_quar}, failed={n_fail}"
    )
    if discovery_failures:
        # WR-04: distinguish "1 of 2 *arrs failed" (partial) from "2 of 2
        # *arrs failed" (fatal) inline in the summary so log scrapers don't
        # need to count the discovery_failures list themselves.
        failure_label = "all-discovery-failures" if all_arr_failed else "partial-discovery-failures"
        summary += f"; {failure_label}=[{'; '.join(discovery_failures)}]"
    print(summary)

    # All-enabled-arr-failed condition contributes to exit 1 even when no items
    # were processed (per HIGH #2 + MEDIUM #10 conjunction). `all_arr_failed`
    # was computed above (WR-04) so the log + summary stay in sync with the
    # exit-code decision.
    if n_fail > 0 or n_quar > 0 or all_arr_failed:
        return 1
    return 0
