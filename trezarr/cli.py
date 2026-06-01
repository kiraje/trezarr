"""One-shot CLI entry point: `trezarr run --once`.

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


# ── Main entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """Console-scripts entry point: `trezarr run --once`.

    Per 03-REVIEWS.md HIGH #6: the only sys.exit / SystemExit translation point
    is here. _run_once() returns an int; main() wraps it in raise SystemExit(...).
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

    args = parser.parse_args()

    if args.command == "run" and args.once:
        # HIGH #6: wrap the async int return in SystemExit at the ONLY translation
        # point. _run_once never calls sys.exit() itself.
        raise SystemExit(asyncio.run(_run_once(args.config)))


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
    try:
        engine = build_engine(settings)
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
    n_done = 0
    n_translate_skipped = 0
    n_quar = 0
    n_fail = 0

    for eligible_item in eligible:
        source_sub_path = eligible_item.source_sub_path
        try:
            result = await translate_file(source_sub_path, settings, llm_client, ledger)

            if result.status == "done":
                if result.output_path is None:
                    # Defensive: status="done" must always carry an output_path.
                    logger.error(
                        "translate_file returned status='done' but output_path is None for %s",
                        source_sub_path,
                    )
                    n_fail += 1
                    continue

                # Path-traversal guard before write-permission application (D-29).
                # Only fire when media_roots is non-empty — the all-*arr-disabled
                # passthrough mode (assert_media_roots_configured passed silently)
                # is intentionally unconstrained. When *arr discovery is enabled,
                # assert_media_roots_configured has already enforced a non-empty
                # media_roots above, so this branch is reached only in passthrough.
                if media_roots:
                    try:
                        assert_within_media_roots(result.output_path, media_roots)
                    except ValueError as exc:
                        logger.error(
                            "path-traversal guard rejected output_path=%s: %s",
                            result.output_path, exc,
                        )
                        n_fail += 1
                        continue

                try:
                    apply_permissions(
                        result.output_path,
                        settings.puid,
                        settings.pgid,
                        settings.umask,
                    )
                    n_done += 1
                except PermissionApplyError as perm_exc:
                    # chmod failure → INTG-04 readability at risk. Quarantine
                    # the item so cli's exit code surfaces the broken contract
                    # (MEDIUM #13).
                    logger.warning(
                        "item quarantined due to chmod failure on %s: %s",
                        result.output_path, perm_exc,
                    )
                    n_quar += 1

            elif result.status == "skipped":
                n_translate_skipped += 1

            elif result.status == "quarantined":
                n_quar += 1
                logger.warning(
                    "item quarantined by translate_file: %s (reason=%s)",
                    source_sub_path, result.reason,
                )

            else:
                # Defensive: an unrecognised status is a contract violation.
                logger.error(
                    "translate_file returned unknown status %r for %s",
                    result.status, source_sub_path,
                )
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
    scan_error = getattr(scan_stats, "error", 0)
    n_scan_skipped = (
        scan_stats.no_source
        + scan_stats.foreign_vi
        + scan_stats.already_done
        + scan_error
    )
    summary = (
        f"Run complete: discovered={n_discovered}, eligible={n_eligible}, "
        f"translated={n_done}, translate_skipped={n_translate_skipped}, "
        f"scan_skipped={n_scan_skipped} "
        f"(no_source={scan_stats.no_source}, "
        f"foreign_vi={scan_stats.foreign_vi}, "
        f"already_done={scan_stats.already_done}, "
        f"error={scan_error}), "
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
