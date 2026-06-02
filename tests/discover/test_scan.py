"""RED test stubs for Phase 3 source-sub scan + gap detection (AUTO-01, AUTO-03, AUTO-04).

All imports from trezarr.discover.* are deferred inside each test function body
so pytest collection succeeds before the implementation exists. Tests skip
cleanly via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Status after Plan 03-05 (Wave 4 — GREEN):
  - All 10 stubs are now plain GREEN. The cli-layer MediaItem dataclass
    used by these stubs moved from ``trezarr.cli`` to
    ``tests/_helpers/cli_media_item.py`` per 03-REVIEW WR-06 (it was dead
    code in the production import graph).

BREAKING INTERNAL API CHANGE (Phase 4): is_eligible() and scan_for_eligible_items()
are now async. All test calls use ``await``. _make_minimal_ledger() is also async
because ledger.record() is now async (Ledger.check/record became async as part of
the LedgerSQLA backend swap — Option C lock-in per 04-PATTERNS.md §Pattern 5).

Covers:
  AUTO-01  find_source_sub(): highest-priority language wins, None when absent,
           deterministic on collision (03-REVIEWS.md MEDIUM #12)
  AUTO-01  is_eligible(): new item → eligible, no-source pre-filtered, foreign vi → skip
  AUTO-03  is_eligible(): unchanged source hash → skip; changed hash → re-translate
  AUTO-04  is_eligible(): never re-process Trezarr's own vi.srt (ledger provenance)
  03-REVIEWS.md HIGH #4 — is_eligible takes (source_sub_path, ledger) — NO media_path
  03-REVIEWS.md HIGH #5 — scan_for_eligible_items returns (list[EligibleItem], ScanStats)
"""
from __future__ import annotations

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


async def _make_minimal_ledger(tmp_path, entries=None):
    """Build a Ledger from tmp_path/processed_files.json with optional pre-populated entries.

    Mirrors the _make_minimal_doc helper pattern from tests/output/test_write.py.
    Caller passes a list of LedgerEntry-shape dicts (or None for an empty ledger).

    BREAKING INTERNAL API CHANGE (Phase 4): async because ledger.record() is now async.
    """
    from trezarr.output.ledger import Ledger, LedgerEntry

    ledger_path = tmp_path / "processed_files.json"
    ledger = Ledger(ledger_path)
    for entry_data in (entries or []):
        await ledger.record(LedgerEntry(**entry_data))
    return ledger


# ──────────────────────────────────────────────────────────────────────────────
# find_source_sub — source subtitle selection by language priority (AUTO-01 / D-25)
# ──────────────────────────────────────────────────────────────────────────────


def test_find_source_sub_priority(tmp_path):
    """find_source_sub returns the highest-priority language match (D-25)."""
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    find_source_sub = scan_mod.find_source_sub

    media = tmp_path / "Show.S01E01.mkv"
    media.write_bytes(b"\x00\x00\x00fake-mkv")
    # Three candidates, two languages
    (tmp_path / "Show.S01E01.zh.srt").write_text("zh", encoding="utf-8")
    en_path = tmp_path / "Show.S01E01.en.srt"
    en_path.write_text("en", encoding="utf-8")

    result = find_source_sub(media, ["en", "zh", "ko"])

    assert result is not None, "Expected a match for the en/zh candidates"
    sub_path, lang = result
    assert lang == "en", f"Expected 'en' (highest priority), got {lang!r}"
    assert sub_path == en_path, f"Expected en_path, got {sub_path}"


def test_find_source_sub_none_when_absent(tmp_path):
    """find_source_sub returns None when no priority-language sidecar exists (D-25)."""
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    find_source_sub = scan_mod.find_source_sub

    media = tmp_path / "Show.S01E02.mkv"
    media.write_bytes(b"\x00\x00\x00fake-mkv")
    # Only an unsupported language exists
    (tmp_path / "Show.S01E02.fr.srt").write_text("fr", encoding="utf-8")

    result = find_source_sub(media, ["en", "zh"])

    assert result is None, f"Expected None when no priority-lang match exists, got {result!r}"


def test_find_source_sub_stem_with_glob_metachars(tmp_path):
    """Media stems containing `[`, `]`, `*`, `?` must still match their source sidecars (CR-02).

    Real *arr libraries commonly have filenames like `Show [2024].S01E01.mkv`
    or `Movie (2019) [1080p].mkv`. Path.glob interprets `[...]` as a character
    class — without glob.escape the stem, find_source_sub silently returns
    None and the file is reported as no_source / never translated.
    """
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    find_source_sub = scan_mod.find_source_sub

    media = tmp_path / "Show [2024].S01E01.mkv"
    media.write_bytes(b"\x00")
    sub = tmp_path / "Show [2024].S01E01.en.srt"
    sub.write_text("en", encoding="utf-8")

    result = find_source_sub(media, ["en"])
    assert result is not None, (
        "find_source_sub must match stems containing glob meta-chars like [2024]"
    )
    sub_path, lang = result
    assert sub_path == sub, f"Expected {sub}, got {sub_path}"
    assert lang == "en", f"Expected 'en', got {lang!r}"


def test_find_source_sub_deterministic_on_collision(tmp_path):
    """When two candidates exist for the same language, lexicographically-first wins (deterministic).

    Real-world libraries sometimes have multiple en sidecars (e.g. `.en.srt` and
    `.en.forced.srt`) or duplicates in subdirectories. find_source_sub must return
    a deterministic choice so re-runs of the CLI behave identically.
    """
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    find_source_sub = scan_mod.find_source_sub

    media = tmp_path / "Show.S01E03.mkv"
    media.write_bytes(b"\x00\x00\x00fake-mkv")
    # Two .en.srt candidates — only `Show.S01E03.en.srt` matches the strict
    # `{stem}.{lang}.srt` pattern; the implementation should prefer the exact
    # match. If forced.srt is treated as a same-language candidate by a future
    # impl, the lexicographically-first one (`Show.S01E03.en.forced.srt`) would
    # win. Either deterministic choice is acceptable — just NOT iteration order.
    exact = tmp_path / "Show.S01E03.en.srt"
    exact.write_text("en-exact", encoding="utf-8")
    # Also create a same-name candidate in a subdir to perturb iteration order
    subdir = tmp_path / "subs"
    subdir.mkdir()
    (subdir / "Show.S01E03.en.srt").write_text("en-shadow", encoding="utf-8")

    result_1 = find_source_sub(media, ["en"])
    result_2 = find_source_sub(media, ["en"])

    assert result_1 is not None and result_2 is not None
    # Two consecutive calls must agree
    assert result_1 == result_2, (
        f"find_source_sub is non-deterministic: {result_1!r} vs {result_2!r}"
    )
    # And the exact stem.lang.srt next to the media must be the choice
    sub_path, _lang = result_1
    assert sub_path == exact, (
        f"Expected the exact-name candidate {exact}, got {sub_path}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# is_eligible — gap detection (AUTO-01, AUTO-03, AUTO-04 / D-26)
#
# Per 03-REVIEWS.md HIGH #4: is_eligible takes (source_sub_path, ledger) — NO
# media_path parameter (the vi sidecar path is derived from the source sub).
#
# BREAKING INTERNAL API CHANGE (Phase 4): is_eligible is now async.
# All tests must use ``await is_eligible(...)`` and be ``async def``.
# ──────────────────────────────────────────────────────────────────────────────


async def test_gap_detection_no_source(tmp_path):
    """is_eligible called on a non-existent / missing source sub returns (False, reason).

    This stub exists so the contract is explicit even though the call site in
    scan_for_eligible_items() filters out no-source items before is_eligible() is
    reached. Defensive belt-and-suspenders.
    """
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    # is_eligible may live in scan.py or gap.py — try both
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    ledger = await _make_minimal_ledger(tmp_path)

    nonexistent = tmp_path / "DoesNotExist.S01E01.en.srt"
    # The contract: a missing source file is not eligible
    eligible, _reason = await is_eligible(nonexistent, ledger)
    assert eligible is False, "Missing source sub must not be eligible"


async def test_gap_detection_eligible_new(tmp_path):
    """A new source sub with no vi sidecar and no ledger entry is eligible (D-26)."""
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    ledger = await _make_minimal_ledger(tmp_path)

    src = tmp_path / "Show.S01E04.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    # No vi sidecar exists; no ledger entry — definitely eligible

    eligible, _reason = await is_eligible(src, ledger)
    assert eligible is True, "New source sub with no vi sidecar and no ledger entry must be eligible"


async def test_gap_detection_foreign_vi_skip(tmp_path):
    """A foreign vi sidecar (present, not in ledger) is skipped — never clobbered (D-26, AUTO-04)."""
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    ledger = await _make_minimal_ledger(tmp_path)

    src = tmp_path / "Show.S01E05.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    # A foreign .vi.srt exists (e.g. Bazarr-downloaded) but is not in the ledger
    foreign_vi = tmp_path / "Show.S01E05.vi.srt"
    foreign_vi.write_text("foreign", encoding="utf-8")

    eligible, reason = await is_eligible(src, ledger)
    assert eligible is False, "Foreign vi sidecar must not be clobbered (D-26)"
    assert "foreign" in reason.lower() or "vi" in reason.lower(), (
        f"Expected a foreign/vi reason, got: {reason!r}"
    )


async def test_idempotency_skip_unchanged(tmp_path):
    """Ledger says done + source hash unchanged → skip (AUTO-03 / D-27)."""
    from trezarr.output.ledger import Ledger

    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    src = tmp_path / "Show.S01E06.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    vi_path = tmp_path / "Show.S01E06.vi.srt"
    vi_path.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")
    source_hash = Ledger.content_hash(src.read_bytes())

    ledger = await _make_minimal_ledger(
        tmp_path,
        entries=[
            dict(
                source_path=str(src),
                output_path=str(vi_path),
                status="done",
                content_hash=source_hash,
            )
        ],
    )

    eligible, _reason = await is_eligible(src, ledger)
    assert eligible is False, "Unchanged source + status=done must skip (AUTO-03)"


async def test_idempotency_retranslate_on_change(tmp_path):
    """Ledger says done but stored hash != current hash → re-translate (AUTO-03 / D-27)."""
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    src = tmp_path / "Show.S01E07.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello (updated)\n", encoding="utf-8")
    vi_path = tmp_path / "Show.S01E07.vi.srt"
    vi_path.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào (stale)\n", encoding="utf-8")

    # Ledger holds a STALE hash (different from current src bytes)
    stale_hash = "stale0000hash0000"

    ledger = await _make_minimal_ledger(
        tmp_path,
        entries=[
            dict(
                source_path=str(src),
                output_path=str(vi_path),
                status="done",
                content_hash=stale_hash,
            )
        ],
    )

    eligible, reason = await is_eligible(src, ledger)
    assert eligible is True, f"Changed source must trigger re-translate (got reason: {reason!r})"


async def test_is_eligible_retries_quarantined(tmp_path):
    """A ledger entry with status='quarantined' makes the source eligible for retry (WR-08, D-30 Case 3).

    D-30 promises that a previously-quarantined item retries on every subsequent
    run. Pre-WR-08 this branch was completely untested — a refactor that
    accidentally turned Case 3 into a skip would have slipped through.
    """
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    src = tmp_path / "Show.S01E14.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    ledger = await _make_minimal_ledger(
        tmp_path,
        entries=[
            dict(
                source_path=str(src),
                output_path=None,
                status="quarantined",
                content_hash="x" * 16,
                quarantine_path=str(tmp_path / "quarantine" / "Show.S01E14.json"),
            )
        ],
    )

    eligible, reason = await is_eligible(src, ledger)
    assert eligible is True, (
        f"Quarantined item must be eligible for retry (D-30, WR-08); got reason={reason!r}"
    )
    assert "quarantin" in reason.lower(), (
        f"Expected the reason string to mention quarantine, got {reason!r}"
    )


async def test_is_eligible_resumes_in_progress(tmp_path):
    """A ledger entry with status='in_progress' makes the source eligible for resume (WR-08, Case 4).

    A run that crashed mid-translate leaves the ledger record at
    status='in_progress' (created at start, never updated to done/quarantined).
    The next run must pick it up. Pre-WR-08 this defensive recovery path was
    completely untested.
    """
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    src = tmp_path / "Show.S01E15.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    ledger = await _make_minimal_ledger(
        tmp_path,
        entries=[
            dict(
                source_path=str(src),
                output_path=None,
                status="in_progress",
                content_hash="y" * 16,
            )
        ],
    )

    eligible, reason = await is_eligible(src, ledger)
    assert eligible is True, (
        f"in_progress item must be eligible for resume (WR-08); got reason={reason!r}"
    )
    assert "in_progress" in reason.lower() or "resuming" in reason.lower(), (
        f"Expected reason to mention in_progress / resuming, got {reason!r}"
    )


async def test_foreign_vi(tmp_path):
    """AUTO-04: never re-process our own output. A ledger entry must keep the vi sidecar 'ours'.

    This is the AUTO-04 invariant: even if the source sub and a vi sidecar exist,
    presence of a matching ledger entry with the current source hash means it's
    OUR output (status=done, hash matches) — and we skip rather than re-translate.
    """
    from trezarr.output.ledger import Ledger

    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    src = tmp_path / "Show.S01E08.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    vi_path = tmp_path / "Show.S01E08.vi.srt"
    vi_path.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")
    source_hash = Ledger.content_hash(src.read_bytes())

    ledger = await _make_minimal_ledger(
        tmp_path,
        entries=[
            dict(
                source_path=str(src),
                output_path=str(vi_path),
                status="done",
                content_hash=source_hash,
            )
        ],
    )

    eligible, _reason = await is_eligible(src, ledger)
    assert eligible is False, "Our own vi.srt (matching ledger entry) must NOT be re-processed (AUTO-04)"


# ──────────────────────────────────────────────────────────────────────────────
# scan_for_eligible_items — returns (list[EligibleItem], ScanStats)
# (03-REVIEWS.md HIGH #5 + MEDIUM #14)
#
# BREAKING INTERNAL API CHANGE (Phase 4): scan_for_eligible_items is now async.
# All tests must use ``await scan_for_eligible_items(...)`` and be ``async def``.
# ──────────────────────────────────────────────────────────────────────────────


async def test_scan_returns_eligible_item_and_scan_stats(tmp_path):
    """scan_for_eligible_items returns a 2-tuple (list[EligibleItem], ScanStats).

    Per 03-REVIEWS.md HIGH #5: promote the bare tuple to a typed EligibleItem
    dataclass for stable contract.
    Per 03-REVIEWS.md MEDIUM #14: emit a ScanStats summary so the CLI's
    end-of-run line can include the pre-translate skip counters
    (no_source / foreign_vi / already_done), not just the post-translate counts.
    """
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    scan_for_eligible_items = scan_mod.scan_for_eligible_items

    EligibleItem = scan_mod.EligibleItem
    ScanStats = scan_mod.ScanStats

    # Build a single MediaItem for a fake media file with no source sub —
    # producing a no_source skip and no eligible items.
    # WR-06: the cli-layer MediaItem dataclass moved to tests/_helpers (was
    # dead code in the production import graph — production constructs
    # trezarr.arr.sonarr.MediaItem via discover_*_items).
    from tests._helpers.cli_media_item import MediaItem

    media = tmp_path / "Show.S01E09.mkv"
    media.write_bytes(b"\x00\x00\x00fake-mkv")

    item = MediaItem(
        local_path=media,
        source_sub_path=None,   # filled in by scan_for_eligible_items based on lang_priority
        title="Show",
        source_lang=None,
    )

    ledger = await _make_minimal_ledger(tmp_path)

    result = await scan_for_eligible_items([item], ledger=ledger, lang_priority=["en"])

    assert isinstance(result, tuple) and len(result) == 2, (
        f"Expected (list[EligibleItem], ScanStats) tuple, got {type(result).__name__}"
    )
    eligible_items, stats = result

    # The single MediaItem has no .en.srt, so eligible should be empty
    assert isinstance(eligible_items, list)
    for it in eligible_items:
        assert isinstance(it, EligibleItem), (
            f"Expected EligibleItem instance, got {type(it).__name__}"
        )
        # EligibleItem fields per 03-REVIEWS.md HIGH #5
        for field in ("media_item", "source_sub_path", "reason", "source_lang"):
            assert hasattr(it, field), f"EligibleItem missing field: {field}"

    assert isinstance(stats, ScanStats), (
        f"Expected ScanStats instance, got {type(stats).__name__}"
    )
    # ScanStats fields per 03-REVIEWS.md MEDIUM #14
    for field in ("scanned", "no_source", "foreign_vi", "already_done"):
        assert hasattr(stats, field), f"ScanStats missing field: {field}"

    # The single item with no source sub increments no_source
    assert stats.no_source == 1, (
        f"Expected stats.no_source == 1 (the only MediaItem has no en sidecar), got {stats.no_source}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# WR-03: every gap.is_eligible False reason must land in a typed ScanStats
# bucket — pre-WR-03 the "no source subtitle at ..." (TOCTOU) and "source
# subtitle unreadable: ..." reasons fell through to an unclassified INFO log
# and were silently un-counted by the summary.
# ──────────────────────────────────────────────────────────────────────────────


async def test_scan_counts_unreadable_source_into_error_bucket(tmp_path, monkeypatch):
    """A source-unreadable reason from is_eligible increments ScanStats.error, NOT no_source (WR-03)."""
    import trezarr.discover.scan as scan_mod

    media = tmp_path / "Show.S01E01.mkv"
    media.write_bytes(b"\x00")
    # Create the source sub so find_source_sub succeeds — only is_eligible reports unreadable.
    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text("...", encoding="utf-8")

    from tests._helpers.cli_media_item import MediaItem

    item = MediaItem(local_path=media, source_sub_path=None, title="Show", source_lang=None)

    # Patch the lazily-imported gap.is_eligible inside scan's namespace via the
    # actual gap module — scan does `from trezarr.discover.gap import is_eligible`
    # at call time, so we patch the source.
    # BREAKING INTERNAL API CHANGE (Phase 4): is_eligible is now async — the
    # monkeypatch replacement must also be async.
    import trezarr.discover.gap as gap_mod

    async def _fake_is_eligible(source_sub_path, ledger):
        return (False, f"source subtitle unreadable: simulated EIO at {source_sub_path}")

    monkeypatch.setattr(gap_mod, "is_eligible", _fake_is_eligible)

    ledger = await _make_minimal_ledger(tmp_path)
    _, stats = await scan_mod.scan_for_eligible_items([item], ledger=ledger, lang_priority=["en"])

    assert stats.error == 1, f"Expected stats.error == 1 for unreadable source, got {stats.error}"
    assert stats.no_source == 0, "Unreadable source must NOT be counted as no_source (WR-03)"


async def test_scan_counts_toctou_no_source_into_no_source_bucket(tmp_path, monkeypatch):
    """A 'no source subtitle at ...' is_eligible reason increments ScanStats.no_source (WR-03)."""
    import trezarr.discover.scan as scan_mod

    media = tmp_path / "Show.S01E02.mkv"
    media.write_bytes(b"\x00")
    src = tmp_path / "Show.S01E02.en.srt"
    src.write_text("...", encoding="utf-8")

    from tests._helpers.cli_media_item import MediaItem

    item = MediaItem(local_path=media, source_sub_path=None, title="Show", source_lang=None)

    import trezarr.discover.gap as gap_mod

    # BREAKING INTERNAL API CHANGE (Phase 4): is_eligible is now async.
    async def _fake_is_eligible(source_sub_path, ledger):
        # Simulate TOCTOU: the source file vanished between find_source_sub and is_eligible.
        return (False, f"no source subtitle at {source_sub_path}")

    monkeypatch.setattr(gap_mod, "is_eligible", _fake_is_eligible)

    ledger = await _make_minimal_ledger(tmp_path)
    _, stats = await scan_mod.scan_for_eligible_items([item], ledger=ledger, lang_priority=["en"])

    assert stats.no_source == 1, (
        f"Expected stats.no_source == 1 (TOCTOU between find_source_sub and is_eligible), got {stats.no_source}"
    )
    assert stats.error == 0, "TOCTOU no-source must NOT be counted as error (WR-03)"


# ──────────────────────────────────────────────────────────────────────────────
# WR-01 — ASS/SSA/VTT source discovery (Phase 9 multi-format reachability)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ext", ["ass", "ssa", "vtt"])
def test_find_source_sub_discovers_non_srt_sources(tmp_path, ext):
    """WR-01: find_source_sub discovers .ass/.ssa/.vtt sources, not just .srt.

    Before the fix the glob and _LANG_SIDECAR_RE were hard-coded to .srt, so an
    operator whose only source subtitle was ASS/SSA/VTT saw ZERO eligible items —
    the entire Phase 9 codec stack was unreachable in production.
    """
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    find_source_sub = scan_mod.find_source_sub

    media = tmp_path / "Show.S01E09.mkv"
    media.write_bytes(b"\x00\x00\x00fake-mkv")
    src = tmp_path / f"Show.S01E09.en.{ext}"
    src.write_text("placeholder", encoding="utf-8")

    result = find_source_sub(media, ["en"])

    assert result is not None, f".{ext} source must be discoverable (WR-01)"
    sub_path, lang = result
    assert sub_path == src
    assert sub_path.suffix == f".{ext}"
    assert lang == "en"


def test_find_source_sub_priority_across_extensions(tmp_path):
    """WR-01: language priority still governs selection across mixed extensions.

    An .en.ass and a .zh.vtt both present → the higher-priority language wins
    regardless of file extension.
    """
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    find_source_sub = scan_mod.find_source_sub

    media = tmp_path / "Show.S01E10.mkv"
    media.write_bytes(b"\x00\x00\x00fake-mkv")
    (tmp_path / "Show.S01E10.zh.vtt").write_text("WEBVTT\n", encoding="utf-8")
    en_ass = tmp_path / "Show.S01E10.en.ass"
    en_ass.write_text("[Events]\n", encoding="utf-8")

    result = find_source_sub(media, ["en", "zh"])

    assert result is not None
    sub_path, lang = result
    assert lang == "en", "highest-priority language must win across extensions"
    assert sub_path == en_ass


def test_lang_sidecar_re_matches_all_supported_suffixes():
    """WR-01: the sidecar regex accepts every supported source suffix."""
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    rx = scan_mod._LANG_SIDECAR_RE
    for ext in ("srt", "ass", "ssa", "vtt"):
        m = rx.match(f"Show.S01E01.en.{ext}")
        assert m is not None, f".{ext} sidecar must match _LANG_SIDECAR_RE (WR-01)"
        assert m.group(2) == "en"
    # A non-subtitle companion must NOT match.
    assert rx.match("Show.S01E01.en.mkv") is None
