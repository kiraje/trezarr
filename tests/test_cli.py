"""RED test stubs for Phase 3 CLI batch-run semantics (D-21, D-30).

All imports from trezarr.cli are deferred inside each test function body so
pytest collection succeeds before the implementation exists. Tests skip cleanly
via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Status after Plan 03-05 (Wave 4 — GREEN): all 7 stubs are now plain GREEN; the
xfail markers have been removed per 03-REVIEWS.md HIGH #3 (xfail-removal policy).

Status after Plan 04-04 (Phase 4 — Ledger backend swap):
  - All tests updated to patch the new Step 3.5 DB-startup sequence:
    build_engine, run_migrations_to_head, migrate_json_ledger_if_needed, LedgerSQLA.
  - scan_for_eligible_items is now async (Phase 4) — patches changed from
    ``return_value=X`` to ``new=AsyncMock(return_value=X)``.
  - Use ``_db_startup_patches()`` context manager helper to avoid repeating
    the 4 new Step 3.5 patches in every test block.

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

import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _db_patches():
    """Return a list of patch objects for the Step 3.5 DB-startup sequence (Plan 04-04).

    These patches suppress the engine + migration + LedgerSQLA construction so
    CLI unit tests do not need a real database.

    Usage::

        with contextlib.ExitStack() as stack:
            for p in _db_patches():
                stack.enter_context(p)
            stack.enter_context(patch("trezarr.cli.TrezarrSettings", ...))
            ...

    Returns:
        List of patch context managers suitable for use with contextlib.ExitStack.
    """
    return [
        # CR-01: the engine returned by build_engine must have an awaitable
        # `dispose()` because _run_once now wraps the pipeline in
        # `try: ... finally: await engine.dispose()`. A bare MagicMock would
        # return a non-awaitable MagicMock from `engine.dispose()`, which the
        # `await` then chokes on. AsyncMock matches the real AsyncEngine.dispose.
        patch("trezarr.cli.build_engine", return_value=MagicMock(dispose=AsyncMock())),
        patch("trezarr.cli.run_migrations_to_head", new=AsyncMock()),
        patch("trezarr.cli.build_session_factory", return_value=MagicMock()),
        patch("trezarr.cli.migrate_json_ledger_if_needed", new=AsyncMock()),
        patch("trezarr.cli.LedgerSQLA", return_value=MagicMock()),
    ]


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

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([item_ok, item_bad, item_ok_2], MagicMock(scanned=3, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_flaky_translate)))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
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

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_ok_translate)))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
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

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_failing_translate)))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
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

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([item], MagicMock(scanned=5, no_source=2, foreign_vi=1, already_done=1, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_ok_translate)))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
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

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([], MagicMock(scanned=0, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock()))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        mock_llm = stack.enter_context(patch("trezarr.cli.LLMClient"))
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

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", side_effect=DiscoveryError("sonarr down")))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", side_effect=DiscoveryError("radarr down")))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([], MagicMock(scanned=0, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock()))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        stack.enter_context(caplog.at_level(logging.ERROR))
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

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", side_effect=DiscoveryError("Sonarr unreachable")))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[radarr_item]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            # Radarr's one item is already-done so no eligible
            new=AsyncMock(return_value=([], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=1, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock()))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        exit_code = await _run_once(None)

    # Sonarr discovery failure logged; Radarr healthy; no items eligible → 0
    assert exit_code == 0, (
        f"One *arr's DiscoveryError must not abort the slice when the other *arr is healthy; got {exit_code}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Path-traversal guard branches — Rule-1 `if media_roots:` (03-REVIEW WR-07)
#
# Pre-WR-07 every cli test mocked `assert_within_media_roots` so neither side of
# the `if media_roots:` branch was actually exercised. These two tests use a
# REAL assert_within_media_roots and configure path_mappings via TrezarrSettings
# so the guard sees a non-empty media_roots — once with an inside-roots output
# (must succeed) and once with an outside-roots output (must reject + n_fail).
# ──────────────────────────────────────────────────────────────────────────────


async def test_run_once_path_guard_passes_inside_media_roots(tmp_path, capsys, settings_factory):
    """With real path_mappings + output_path INSIDE the configured root, the run completes 0 (WR-07).

    Exercises the `if media_roots:` Rule-1 branch with a real
    ``assert_within_media_roots`` (NOT mocked). The translated output_path is
    inside the configured local root, so the guard passes silently and the
    apply_permissions branch runs.
    """
    from trezarr.paths import PathMapping

    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    media_root = tmp_path / "media"
    media_root.mkdir()
    # Drop a fake media file + source sub inside the real media root so the
    # output_path returned by translate_file resolves inside the root.
    src = media_root / "Show.S01E20.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    inside_output = media_root / "Show.S01E20.vi.srt"

    from tests._helpers.cli_media_item import MediaItem
    item = MediaItem(
        local_path=src.with_suffix(".mkv"),
        source_sub_path=src,
        title="Show",
        source_lang="en",
    )

    # Real path_mappings populate media_roots; *arr stays disabled so
    # assert_media_roots_configured passes silently.
    settings = settings_factory(
        sonarr_enabled=False,
        radarr_enabled=False,
        path_mappings=[PathMapping(remote="/tv", local=str(media_root))],
    )

    async def _ok_translate(path, *_args, **_kwargs):
        from trezarr.translate.engine import TranslationResult
        return TranslationResult(status="done", output_path=inside_output)

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_ok_translate)))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))       # still mocked — we don't care about chmod here
        # NOTE: assert_within_media_roots is NOT mocked — it's the system-under-test (WR-07).
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))       # bypass the FS probe
        # build_media_roots is NOT mocked — it must return [media_root] from path_mappings.
        # assert_media_roots_configured passes silently when *arr is disabled, so we can mock it.
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        exit_code = await _run_once(None)

    summary = capsys.readouterr().out
    assert exit_code == 0, (
        f"Inside-root output must pass the WR-07 path guard and the run must exit 0; "
        f"got {exit_code}. Summary: {summary}"
    )
    assert "translated=1" in summary, f"Expected translated=1, got: {summary}"
    assert "failed=0" in summary, f"Expected failed=0, got: {summary}"


async def test_run_once_path_guard_rejects_outside_media_roots(tmp_path, capsys, caplog, settings_factory):
    """An output_path OUTSIDE the configured media roots is rejected and n_fail bumped (WR-07).

    Exercises the negative side of the `if media_roots:` Rule-1 branch with a
    real ``assert_within_media_roots`` — pre-WR-07 the guard was always mocked,
    so its rejection path (cli.py:253-262) was uncovered.
    """
    import logging

    from trezarr.paths import PathMapping

    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    media_root = tmp_path / "media"
    media_root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    # The translate output lands OUTSIDE the configured media root — the guard
    # MUST reject it. Source sub itself can be inside media_root or anywhere —
    # only the OUTPUT path matters for assert_within_media_roots.
    src = media_root / "Show.S01E21.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    bad_output = elsewhere / "Show.S01E21.vi.srt"  # outside media_root

    from tests._helpers.cli_media_item import MediaItem
    item = MediaItem(
        local_path=src.with_suffix(".mkv"),
        source_sub_path=src,
        title="Show",
        source_lang="en",
    )

    settings = settings_factory(
        sonarr_enabled=False,
        radarr_enabled=False,
        path_mappings=[PathMapping(remote="/tv", local=str(media_root))],
    )

    async def _bad_output_translate(path, *_args, **_kwargs):
        from trezarr.translate.engine import TranslationResult
        return TranslationResult(status="done", output_path=bad_output)

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_bad_output_translate)))
        mock_chmod = stack.enter_context(patch("trezarr.cli.apply_permissions"))  # MUST NOT be called when guard rejects
        # assert_within_media_roots is NOT mocked — the rejection is the SUT.
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        stack.enter_context(caplog.at_level(logging.ERROR))
        exit_code = await _run_once(None)

    summary = capsys.readouterr().out
    assert exit_code == 1, (
        f"Outside-root output must be rejected and n_fail bumped, got exit_code={exit_code}. "
        f"Summary: {summary}"
    )
    assert "failed=1" in summary, f"Expected failed=1 from path-guard rejection, got: {summary}"
    # The chmod-application call site must never run when the guard rejects.
    assert mock_chmod.call_count == 0, (
        "apply_permissions must NOT be called when assert_within_media_roots rejects"
    )
    # An error log must name the rejection.
    assert any(
        "path-traversal guard" in rec.getMessage() for rec in caplog.records
    ), "Expected an error log for the path-traversal guard rejection"


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

    with contextlib.ExitStack() as stack:
        for p in _db_patches():
            stack.enter_context(p)
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_ok_translate)))
        stack.enter_context(patch("trezarr.cli.apply_permissions", side_effect=PermissionApplyError("chmod failed")))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        exit_code = await _run_once(None)

    assert exit_code == 1, (
        f"PermissionApplyError must yield a non-zero exit (item quarantined), got {exit_code}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Task 2: Step 3.5 DB-startup wiring tests (04-04 — cli.py startup)
# ──────────────────────────────────────────────────────────────────────────────


async def test_run_once_builds_engine_and_runs_migrations_before_discovery(tmp_path, capsys, settings_factory):
    """Step 3.5 runs in the correct order: build_engine → run_migrations_to_head →
    build_session_factory → migrate_json_ledger_if_needed → (discovery) (04-04 Task 2 Test 1).
    """
    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    call_order: list[str] = []

    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    def _record_build_engine(*_a, **_kw):
        call_order.append("build_engine")
        # CR-01: engine.dispose() is awaited in _run_once's finally block.
        return MagicMock(dispose=AsyncMock())

    async def _record_run_migrations(*_a, **_kw):
        call_order.append("run_migrations_to_head")

    def _record_build_session_factory(*_a, **_kw):
        call_order.append("build_session_factory")
        return MagicMock()

    async def _record_migrate(*_a, **_kw):
        call_order.append("migrate_json_ledger_if_needed")

    def _record_discover_sonarr(*_a, **_kw):
        call_order.append("discover_sonarr_items")
        return []

    def _record_discover_radarr(*_a, **_kw):
        call_order.append("discover_radarr_items")
        return []

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.build_engine", side_effect=_record_build_engine))
        stack.enter_context(patch("trezarr.cli.run_migrations_to_head", new=AsyncMock(side_effect=_record_run_migrations)))
        stack.enter_context(patch("trezarr.cli.build_session_factory", side_effect=_record_build_session_factory))
        stack.enter_context(patch("trezarr.cli.migrate_json_ledger_if_needed", new=AsyncMock(side_effect=_record_migrate)))
        stack.enter_context(patch("trezarr.cli.LedgerSQLA", return_value=MagicMock()))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", side_effect=_record_discover_sonarr))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", side_effect=_record_discover_radarr))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([], MagicMock(scanned=0, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        await _run_once(None)

    # Verify ordering: build_engine and migrations must precede discovery
    assert "build_engine" in call_order, "build_engine must be called in Step 3.5"
    assert "run_migrations_to_head" in call_order, "run_migrations_to_head must be called in Step 3.5"
    assert "build_session_factory" in call_order, "build_session_factory must be called in Step 3.5"
    assert "migrate_json_ledger_if_needed" in call_order, "migrate_json_ledger_if_needed must be called in Step 3.5"
    engine_idx = call_order.index("build_engine")
    migrate_idx = call_order.index("run_migrations_to_head")
    session_idx = call_order.index("build_session_factory")
    json_migrate_idx = call_order.index("migrate_json_ledger_if_needed")
    discover_s_idx = call_order.index("discover_sonarr_items")
    discover_r_idx = call_order.index("discover_radarr_items")

    assert engine_idx < migrate_idx < session_idx < json_migrate_idx, (
        f"Step 3.5 must run: build_engine < run_migrations < build_session_factory < migrate_json; "
        f"got order: {call_order}"
    )
    assert json_migrate_idx < discover_s_idx, (
        f"migrate_json_ledger_if_needed must run before Sonarr discovery; got: {call_order}"
    )
    assert json_migrate_idx < discover_r_idx, (
        f"migrate_json_ledger_if_needed must run before Radarr discovery; got: {call_order}"
    )


async def test_run_once_constructs_ledger_sqla_not_json_ledger(tmp_path, capsys, settings_factory):
    """_run_once uses LedgerSQLA (not JSON Ledger) for the translate loop (04-04 Task 2 Test 2)."""
    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once
    from trezarr.output.ledger_sqla import LedgerSQLA as _LedgerSQLA

    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    # Capture the ledger passed to scan_for_eligible_items to assert its type
    captured_ledger = []

    async def _capture_scan(items, ledger, *_a, **_kw):
        captured_ledger.append(ledger)
        return ([], MagicMock(scanned=0, no_source=0, foreign_vi=0, already_done=0, error=0))  # WR-08: error=0 required (was missing pre-fix)

    # Use a real LedgerSQLA instance from a temp DB to confirm the type
    from tests.db.conftest import session_factory as _sf_fixture  # use fixture indirectly via MagicMock
    # Mock LedgerSQLA to return a known sentinel so we can test isinstance
    sentinel_ledger = MagicMock(spec=_LedgerSQLA)

    with contextlib.ExitStack() as stack:
        # CR-01: engine mock needs an awaitable dispose for the finally block.
        stack.enter_context(patch("trezarr.cli.build_engine", return_value=MagicMock(dispose=AsyncMock())))
        stack.enter_context(patch("trezarr.cli.run_migrations_to_head", new=AsyncMock()))
        stack.enter_context(patch("trezarr.cli.build_session_factory", return_value=MagicMock()))
        stack.enter_context(patch("trezarr.cli.migrate_json_ledger_if_needed", new=AsyncMock()))
        stack.enter_context(patch("trezarr.cli.LedgerSQLA", return_value=sentinel_ledger))
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.scan_for_eligible_items", new=AsyncMock(side_effect=_capture_scan)))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        await _run_once(None)

    assert len(captured_ledger) == 1, "scan_for_eligible_items must be called with a ledger"
    assert captured_ledger[0] is sentinel_ledger, (
        "The ledger passed to scan_for_eligible_items must be the LedgerSQLA instance (not JSON Ledger)"
    )


async def test_run_once_exits_nonzero_on_migration_failure(tmp_path, caplog, settings_factory):
    """Alembic migration failure causes _run_once to return 1 with an actionable error (04-04 Task 2 Test 3).

    Per RESEARCH §Open Question 3: Alembic schema failure is hard-fatal —
    the DB schema MUST be ready before any translate work can happen.
    """
    import logging

    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        # CR-01: engine mock needs an awaitable dispose for the finally block.
        stack.enter_context(patch("trezarr.cli.build_engine", return_value=MagicMock(dispose=AsyncMock())))
        stack.enter_context(patch(
            "trezarr.cli.run_migrations_to_head",
            new=AsyncMock(side_effect=RuntimeError("Alembic migration failed: DB locked")),
        ))
        stack.enter_context(patch("trezarr.cli.build_session_factory", return_value=MagicMock()))
        stack.enter_context(patch("trezarr.cli.migrate_json_ledger_if_needed", new=AsyncMock()))
        stack.enter_context(patch("trezarr.cli.LedgerSQLA", return_value=MagicMock()))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(caplog.at_level(logging.ERROR))
        exit_code = await _run_once(None)

    assert exit_code == 1, (
        f"Alembic migration failure must cause _run_once to return 1 (non-zero), got {exit_code}"
    )
    assert any(
        "DB startup failed" in rec.getMessage() for rec in caplog.records
    ), "Expected an error log with an actionable message when migration fails"


async def test_run_once_logs_but_continues_on_ledger_migration_failure(tmp_path, caplog, settings_factory):
    """JSON-ledger migration failure logs an error but the run continues (04-04 Task 2 Test 4).

    Per D-37 forgiveness contract: the JSON-ledger one-shot import is best-effort.
    A failure starts SQLite with an empty ledger but does NOT abort the run.
    This is asymmetric vs. the Alembic hard-fatal path (Test 3).
    """
    import logging

    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    settings = settings_factory(sonarr_enabled=False, radarr_enabled=False)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        # CR-01: engine mock needs an awaitable dispose for the finally block.
        stack.enter_context(patch("trezarr.cli.build_engine", return_value=MagicMock(dispose=AsyncMock())))
        stack.enter_context(patch("trezarr.cli.run_migrations_to_head", new=AsyncMock()))
        stack.enter_context(patch("trezarr.cli.build_session_factory", return_value=MagicMock()))
        stack.enter_context(patch(
            "trezarr.cli.migrate_json_ledger_if_needed",
            new=AsyncMock(side_effect=OSError("Disk full during rename")),
        ))
        stack.enter_context(patch("trezarr.cli.LedgerSQLA", return_value=MagicMock()))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([], MagicMock(scanned=0, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        stack.enter_context(caplog.at_level(logging.ERROR))
        exit_code = await _run_once(None)

    # The run MUST NOT abort — it continues to discovery/scan/translate
    # Exit code 0 means "no translate failures" (zero eligible items is fine)
    assert exit_code == 0, (
        f"JSON-ledger migration failure must NOT abort the run (D-37 forgiveness); got exit_code={exit_code}"
    )
    assert any(
        "DB startup failed" in rec.getMessage() for rec in caplog.records
    ), "Expected an error log when JSON-ledger migration fails"


async def test_run_once_end_to_end_smoke_with_temp_sqlite(tmp_path, settings_factory):
    """Integration smoke: _run_once with a real temp SQLite produces a vi.srt sidecar and a
    'done' row in the processed_file table (04-04 Task 2 Test 5).

    Patches the LLM translate_file to avoid a real endpoint but exercises the full
    SQLite startup + LedgerSQLA check/record path with a real AsyncEngine.
    """
    from pathlib import Path as _Path
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker as _async_sessionmaker

    cli_mod = pytest.importorskip("trezarr.cli")
    _run_once = cli_mod._run_once

    # Set up a real media file + source SRT
    media_root = tmp_path / "media"
    media_root.mkdir()
    src = media_root / "Show.S01E01.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    vi_out = media_root / "Show.S01E01.vi.srt"

    # Real temp SQLite DB
    db_path = tmp_path / "trezarr.db"
    from trezarr.paths import PathMapping
    settings = settings_factory(
        sonarr_enabled=False,
        radarr_enabled=False,
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        path_mappings=[PathMapping(remote="/tv", local=str(media_root))],
        translate_ledger_path=str(tmp_path / "processed_files.json"),  # non-existent → migration no-op
        translate_quarantine_dir=str(tmp_path / "quarantine"),
    )

    from tests._helpers.cli_media_item import MediaItem
    item = MediaItem(
        local_path=src.with_suffix(".mkv"),
        source_sub_path=src,
        title="Show",
        source_lang="en",
    )

    async def _fake_translate(path, _settings, _llm, _ledger):
        from trezarr.output.ledger import LedgerEntry
        from trezarr.translate.engine import TranslationResult
        # Write the vi.srt sidecar so write-side logic works
        vi_out.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")
        # Record in the ledger exactly as the real translate_file would do
        await _ledger.record(LedgerEntry(
            source_path=str(path),
            output_path=str(vi_out),
            status="done",
            content_hash=_ledger.content_hash(_Path(path).read_bytes()),
        ))
        return TranslationResult(status="done", output_path=vi_out)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("trezarr.cli.TrezarrSettings", return_value=settings))
        stack.enter_context(patch("trezarr.cli.discover_sonarr_items", return_value=[]))
        stack.enter_context(patch("trezarr.cli.discover_radarr_items", return_value=[]))
        stack.enter_context(patch(
            "trezarr.cli.scan_for_eligible_items",
            new=AsyncMock(return_value=([item], MagicMock(scanned=1, no_source=0, foreign_vi=0, already_done=0, error=0))),
        ))
        stack.enter_context(patch("trezarr.cli.translate_file", new=AsyncMock(side_effect=_fake_translate)))
        stack.enter_context(patch("trezarr.cli.apply_permissions"))
        stack.enter_context(patch("trezarr.cli.probe_media_roots"))
        stack.enter_context(patch("trezarr.cli.assert_media_roots_configured"))
        stack.enter_context(patch("trezarr.cli.LLMClient"))
        exit_code = await _run_once(None)

    assert exit_code == 0, f"End-to-end smoke must exit 0 on success, got {exit_code}"
    assert vi_out.exists(), "translate_file must have written the vi.srt sidecar"

    # Verify the SQLite processed_file table has a 'done' row for the source path
    from trezarr.db.engine import build_engine as _build_engine
    from trezarr.db.migration_runner import run_migrations_to_head as _run_migrations
    verify_engine = _build_engine(settings)
    # CR-01: wrap verify_engine in try/finally so dispose() runs on EVERY exit
    # path — assertion failure inside the async-with block previously skipped
    # dispose and left aiosqlite worker threads bound to the closed event loop.
    try:
        await _run_migrations(verify_engine)
        verify_factory = _async_sessionmaker(verify_engine, expire_on_commit=False)
        async with verify_factory() as session:
            result = await session.execute(
                text("SELECT status, source_path FROM processed_file WHERE source_path = :p"),
                {"p": str(src)},
            )
            row = result.fetchone()
    finally:
        await verify_engine.dispose()

    assert row is not None, f"processed_file must have a row for {src} after a successful run"
    assert row[0] == "done", f"processed_file row for {src} must have status='done', got {row[0]!r}"
