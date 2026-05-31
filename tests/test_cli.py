"""RED test stubs for Phase 3 CLI batch-run semantics (D-21, D-30).

All imports from trezarr.cli are deferred inside each test function body so
pytest collection succeeds before the implementation exists. Tests skip cleanly
via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Status after Plan 03-05 (Wave 4 — GREEN): all 7 stubs are now plain GREEN; the
xfail markers have been removed per 03-REVIEWS.md HIGH #3 (xfail-removal policy).

Convention: _run_once() is async (the underlying translate_file() pipeline is
async), but it returns an `int` exit code rather than calling sys.exit() — per
03-REVIEWS.md HIGH #6. Tests assert the returned int directly, NOT pytest.raises(SystemExit).

Covers:
  D-30  Batch run continues past per-item failure (one bad item doesn't kill the slice)
  D-30  _run_once returns 0 when every item succeeded (03-REVIEWS.md HIGH #6)
  D-30  _run_once returns 1 when any item failed
  D-30  Summary includes widened skip counters (03-REVIEWS.md MEDIUM #14):
        discovered, eligible, translated, translate_skipped, scan_skipped,
        quarantined, failed
  03-REVIEWS.md HIGH #7  LLMClient is constructed only when there are eligible items
  03-REVIEWS.md MEDIUM #10 One *arr failure doesn't kill the other *arr's discovery
  03-REVIEWS.md MEDIUM #13 chmod failure raises PermissionApplyError → quarantines item
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers — build the test-double pipeline that _run_once() drives
# ──────────────────────────────────────────────────────────────────────────────


def _make_media_item(tmp_path, name: str = "Show.S01E01.en.srt"):
    """Build a MediaItem-shaped object with a real on-disk source sub.

    Per WR-06: the cli-layer MediaItem dataclass has moved out of
    ``trezarr.cli`` (where it was dead code in the production import graph)
    into ``tests/_helpers/cli_media_item.py``. The production translate loop
    consumes ``arr.sonarr.MediaItem`` via the discover_*_items adapters and
    reads ``EligibleItem.source_sub_path`` — it never constructs this class.
    """
    from tests._helpers.cli_media_item import MediaItem

    src = tmp_path / name
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    return MediaItem(
        local_path=src.with_suffix(".mkv"),   # the implied media file
        source_sub_path=src,
        title="Show",
        source_lang="en",
    )


# ──────────────────────────────────────────────────────────────────────────────
# D-30 batch semantics: one bad item never aborts the run
# ──────────────────────────────────────────────────────────────────────────────


async def test_batch_run_continues_past_failure(tmp_path, settings_factory):
    """A per-item failure in translate_file is logged + counted, the next item is still processed (D-30)."""
    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    item_ok = _make_media_item(tmp_path, "Show.S01E01.en.srt")
    item_bad = _make_media_item(tmp_path, "Show.S01E02.en.srt")
    item_ok_2 = _make_media_item(tmp_path, "Show.S01E03.en.srt")

    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    async def _flaky_translate(path, *_args, **_kwargs):
        from trezarr.translate.engine import TranslationResult
        if "S01E02" in str(path):
            raise RuntimeError("simulated translate failure for this one item")
        return TranslationResult(status="done", output_path=Path(str(path).replace(".en.srt", ".vi.srt")))

    with (
        patch("trezarr.cli.TrezarrSettings", return_value=settings),
        patch("trezarr.cli.discover_sonarr_items", return_value=[]),
        patch("trezarr.cli.discover_radarr_items", return_value=[]),
        patch(
            "trezarr.cli.scan_for_eligible_items",
            return_value=([item_ok, item_bad, item_ok_2], MagicMock(scanned=3, no_source=0, foreign_vi=0, already_done=0)),
        ),
        patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_flaky_translate)),
        patch("trezarr.cli.apply_permissions"),
        patch("trezarr.cli.probe_media_roots"),
        patch("trezarr.cli.assert_media_roots_configured"),
        patch("trezarr.cli.LLMClient"),
    ):
        exit_code = await _run_once(None)

    # Exit code is non-zero because one item failed
    assert exit_code != 0, f"Expected non-zero exit (one item failed), got {exit_code}"


async def test_run_once_returns_int_zero_on_all_success(tmp_path, settings_factory):
    """_run_once returns 0 (int) when every item translated successfully (D-30, HIGH #6).

    Note: _run_once returns int — NOT pytest.raises(SystemExit). main() converts
    the int to SystemExit; _run_once itself stays testable as a normal coroutine.
    """
    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    item = _make_media_item(tmp_path, "Show.S01E10.en.srt")

    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    async def _ok_translate(path, *_args, **_kwargs):
        from trezarr.translate.engine import TranslationResult
        return TranslationResult(status="done", output_path=Path(str(path).replace(".en.srt", ".vi.srt")))

    with (
        patch("trezarr.cli.TrezarrSettings", return_value=settings),
        patch("trezarr.cli.discover_sonarr_items", return_value=[]),
        patch("trezarr.cli.discover_radarr_items", return_value=[]),
        patch(
            "trezarr.cli.scan_for_eligible_items",
            return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0)),
        ),
        patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_ok_translate)),
        patch("trezarr.cli.apply_permissions"),
        patch("trezarr.cli.probe_media_roots"),
        patch("trezarr.cli.assert_media_roots_configured"),
        patch("trezarr.cli.LLMClient"),
    ):
        exit_code = await _run_once(None)

    assert exit_code == 0, f"Expected exit_code == 0 on all-success, got {exit_code!r}"


async def test_run_once_returns_int_nonzero_on_any_failure(tmp_path, settings_factory):
    """_run_once returns 1 (int) when any item failed or was quarantined (D-30, HIGH #6)."""
    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    item = _make_media_item(tmp_path, "Show.S01E11.en.srt")

    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    async def _failing_translate(path, *_args, **_kwargs):
        raise RuntimeError("simulated translate failure")

    with (
        patch("trezarr.cli.TrezarrSettings", return_value=settings),
        patch("trezarr.cli.discover_sonarr_items", return_value=[]),
        patch("trezarr.cli.discover_radarr_items", return_value=[]),
        patch(
            "trezarr.cli.scan_for_eligible_items",
            return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0)),
        ),
        patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_failing_translate)),
        patch("trezarr.cli.apply_permissions"),
        patch("trezarr.cli.probe_media_roots"),
        patch("trezarr.cli.assert_media_roots_configured"),
        patch("trezarr.cli.LLMClient"),
    ):
        exit_code = await _run_once(None)

    assert exit_code == 1, f"Expected exit_code == 1 on any failure, got {exit_code!r}"


# ──────────────────────────────────────────────────────────────────────────────
# Widened summary fields (03-REVIEWS.md MEDIUM #14)
# ──────────────────────────────────────────────────────────────────────────────


async def test_batch_summary_printed_with_widened_fields(tmp_path, capsys, settings_factory):
    """End-of-run summary line includes pre-translate skip counters (MEDIUM #14).

    The old D-30 summary only reported {translated, skipped, quarantined, failed}.
    Per MEDIUM #14, the user needs visibility into pre-translate skips too
    (no_source, foreign_vi, already_done) — so the summary widens to include
    discovered/eligible/translated/translate_skipped/scan_skipped/quarantined/failed.
    """
    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    item = _make_media_item(tmp_path, "Show.S01E12.en.srt")
    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    async def _ok_translate(path, *_args, **_kwargs):
        from trezarr.translate.engine import TranslationResult
        return TranslationResult(status="done", output_path=Path(str(path).replace(".en.srt", ".vi.srt")))

    with (
        patch("trezarr.cli.TrezarrSettings", return_value=settings),
        patch("trezarr.cli.discover_sonarr_items", return_value=[]),
        patch("trezarr.cli.discover_radarr_items", return_value=[]),
        patch(
            "trezarr.cli.scan_for_eligible_items",
            return_value=([item], MagicMock(scanned=5, no_source=2, foreign_vi=1, already_done=1)),
        ),
        patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_ok_translate)),
        patch("trezarr.cli.apply_permissions"),
        patch("trezarr.cli.probe_media_roots"),
        patch("trezarr.cli.assert_media_roots_configured"),
        patch("trezarr.cli.LLMClient"),
    ):
        await _run_once(None)

    captured = capsys.readouterr().out
    for token in (
        "discovered=",
        "eligible=",
        "translated=",
        "translate_skipped=",
        "scan_skipped=",
        "quarantined=",
        "failed=",
    ):
        assert token in captured, (
            f"Expected token {token!r} in CLI summary output, got:\n{captured}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# LLMClient lazy-construct — don't pay LLM config tax on empty runs
# (03-REVIEWS.md HIGH #7)
# ──────────────────────────────────────────────────────────────────────────────


async def test_llm_client_not_constructed_when_no_eligible(tmp_path, settings_factory):
    """LLMClient is NOT instantiated when there are no eligible items (HIGH #7).

    Avoids exercising LLM endpoint config on a discovery-only no-op run.
    """
    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    with (
        patch("trezarr.cli.TrezarrSettings", return_value=settings),
        patch("trezarr.cli.discover_sonarr_items", return_value=[]),
        patch("trezarr.cli.discover_radarr_items", return_value=[]),
        patch(
            "trezarr.cli.scan_for_eligible_items",
            return_value=([], MagicMock(scanned=0, no_source=0, foreign_vi=0, already_done=0)),
        ),
        patch("trezarr.cli.translate_file", new=AsyncMock()),
        patch("trezarr.cli.apply_permissions"),
        patch("trezarr.cli.probe_media_roots"),
        patch("trezarr.cli.assert_media_roots_configured"),
        patch("trezarr.cli.LLMClient") as mock_llm,
    ):
        await _run_once(None)

    assert mock_llm.call_count == 0, (
        f"LLMClient must not be constructed on an empty-eligible run; was called {mock_llm.call_count} times"
    )


# ──────────────────────────────────────────────────────────────────────────────
# One *arr failure does not abort discovery from the other *arr
# (03-REVIEWS.md MEDIUM #10)
# ──────────────────────────────────────────────────────────────────────────────


async def test_all_arr_failure_distinct_notice_and_label(tmp_path, capsys, caplog, settings_factory):
    """When both *arrs are enabled and BOTH fail discovery, the run exits 1 with a distinct notice (WR-04).

    Pre-WR-04: the "All enabled *arr services failed" log fired but the run
    silently continued through the same "Run complete: ... partial-discovery-
    failures=[...]" summary used by the 1-of-2-failed case, so operators
    couldn't distinguish the fatal state from a partial one. WR-04 emits a
    one-line "ALL DISCOVERY FAILED" notice on stdout AND switches the summary
    suffix from "partial-discovery-failures" to "all-discovery-failures".
    """
    import logging

    arr_pkg = pytest.importorskip("trezarr.arr")
    DiscoveryError = arr_pkg.DiscoveryError

    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    settings = settings_factory(sonarr_enabled=True, radarr_enabled=True)

    with (
        patch("trezarr.cli.TrezarrSettings", return_value=settings),
        patch("trezarr.cli.discover_sonarr_items", side_effect=DiscoveryError("sonarr down")),
        patch("trezarr.cli.discover_radarr_items", side_effect=DiscoveryError("radarr down")),
        patch(
            "trezarr.cli.scan_for_eligible_items",
            return_value=([], MagicMock(scanned=0, no_source=0, foreign_vi=0, already_done=0, error=0)),
        ),
        patch("trezarr.cli.translate_file", new=AsyncMock()),
        patch("trezarr.cli.apply_permissions"),
        patch("trezarr.cli.probe_media_roots"),
        patch("trezarr.cli.assert_media_roots_configured"),
        patch("trezarr.cli.LLMClient"),
        caplog.at_level(logging.ERROR),
    ):
        exit_code = await _run_once(None)

    captured = capsys.readouterr().out
    assert exit_code == 1, f"All-arr-failed must exit non-zero, got {exit_code}"
    assert "ALL DISCOVERY FAILED" in captured, (
        f"Distinct WR-04 notice missing from stdout; got:\n{captured}"
    )
    assert "all-discovery-failures=[" in captured, (
        f"Summary must distinguish all-vs-partial failure mode; got:\n{captured}"
    )
    # Cross-check: a logger.error for the all-arr-failed condition must have fired.
    assert any(
        "All enabled *arr services failed" in rec.getMessage()
        for rec in caplog.records
    ), "Expected an error log naming the all-arr-failed condition"


async def test_one_arr_failure_does_not_kill_other_arr(tmp_path, settings_factory):
    """Sonarr raising DiscoveryError still allows Radarr discovery + run to complete (MEDIUM #10).

    Sonarr fails → log + zero its contribution.
    Radarr returns 1 movie that's already translated (0 eligible).
    Result: 0 items processed, 0 failures → _run_once returns 0.
    """
    arr_pkg = pytest.importorskip("trezarr.arr")
    DiscoveryError = arr_pkg.DiscoveryError

    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    settings = settings_factory(sonarr_enabled=True, radarr_enabled=True)

    radarr_item = _make_media_item(tmp_path, "Movie.en.srt")

    with (
        patch("trezarr.cli.TrezarrSettings", return_value=settings),
        patch("trezarr.cli.discover_sonarr_items", side_effect=DiscoveryError("Sonarr unreachable")),
        patch("trezarr.cli.discover_radarr_items", return_value=[radarr_item]),
        patch(
            "trezarr.cli.scan_for_eligible_items",
            # Radarr's one item is already-done so no eligible
            return_value=([], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=1)),
        ),
        patch("trezarr.cli.translate_file", new=AsyncMock()),
        patch("trezarr.cli.apply_permissions"),
        patch("trezarr.cli.probe_media_roots"),
        patch("trezarr.cli.assert_media_roots_configured"),
        patch("trezarr.cli.LLMClient"),
    ):
        exit_code = await _run_once(None)

    # Sonarr discovery failure logged; Radarr healthy; no items eligible → 0
    assert exit_code == 0, (
        f"One *arr's DiscoveryError must not abort the slice when the other *arr is healthy; got {exit_code}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# chmod failure → quarantine the item (03-REVIEWS.md MEDIUM #13)
# ──────────────────────────────────────────────────────────────────────────────


async def test_chmod_error_quarantines_item(tmp_path, settings_factory):
    """apply_permissions raising PermissionApplyError quarantines the item; _run_once returns 1 (MEDIUM #13).

    INTG-04 requires media-server-readable sidecars; a chmod failure violates that
    invariant. CLI must surface this as a quarantine (per-item failure) so the
    run exit code reflects the broken contract.
    """
    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once
    from trezarr.output.write import PermissionApplyError  # noqa: F401  (module check)

    item = _make_media_item(tmp_path, "Show.S01E13.en.srt")
    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    async def _ok_translate(path, *_args, **_kwargs):
        from trezarr.translate.engine import TranslationResult
        return TranslationResult(status="done", output_path=Path(str(path).replace(".en.srt", ".vi.srt")))

    with (
        patch("trezarr.cli.TrezarrSettings", return_value=settings),
        patch("trezarr.cli.discover_sonarr_items", return_value=[]),
        patch("trezarr.cli.discover_radarr_items", return_value=[]),
        patch(
            "trezarr.cli.scan_for_eligible_items",
            return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0)),
        ),
        patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_ok_translate)),
        patch("trezarr.cli.apply_permissions", side_effect=PermissionApplyError("chmod failed")),
        patch("trezarr.cli.probe_media_roots"),
        patch("trezarr.cli.assert_media_roots_configured"),
        patch("trezarr.cli.LLMClient"),
    ):
        exit_code = await _run_once(None)

    assert exit_code == 1, (
        f"PermissionApplyError must yield a non-zero exit (item quarantined), got {exit_code}"
    )
