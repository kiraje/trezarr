"""RED test stubs for Phase 3 source-sub scan + gap detection (AUTO-01, AUTO-03, AUTO-04).

All imports from trezarr.discover.* are deferred inside each test function body
so pytest collection succeeds before the implementation exists. Tests skip
cleanly via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Status after Plan 03-05 (Wave 4 — GREEN):
  - All 10 stubs are now plain GREEN. trezarr.cli.MediaItem now exists,
    so test_scan_returns_eligible_item_and_scan_stats had its xfail marker
    removed (per 03-REVIEWS.md HIGH #3 xfail-removal policy).

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


def _make_minimal_ledger(tmp_path, entries=None):
    """Build a Ledger from tmp_path/processed_files.json with optional pre-populated entries.

    Mirrors the _make_minimal_doc helper pattern from tests/output/test_write.py.
    Caller passes a list of LedgerEntry-shape dicts (or None for an empty ledger).
    """
    from trezarr.output.ledger import Ledger, LedgerEntry

    ledger_path = tmp_path / "processed_files.json"
    ledger = Ledger(ledger_path)
    for entry_data in (entries or []):
        ledger.record(LedgerEntry(**entry_data))
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
# ──────────────────────────────────────────────────────────────────────────────


def test_gap_detection_no_source(tmp_path):
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

    ledger = _make_minimal_ledger(tmp_path)

    nonexistent = tmp_path / "DoesNotExist.S01E01.en.srt"
    # The contract: a missing source file is not eligible
    eligible, _reason = is_eligible(nonexistent, ledger)
    assert eligible is False, "Missing source sub must not be eligible"


def test_gap_detection_eligible_new(tmp_path):
    """A new source sub with no vi sidecar and no ledger entry is eligible (D-26)."""
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    ledger = _make_minimal_ledger(tmp_path)

    src = tmp_path / "Show.S01E04.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    # No vi sidecar exists; no ledger entry — definitely eligible

    eligible, _reason = is_eligible(src, ledger)
    assert eligible is True, "New source sub with no vi sidecar and no ledger entry must be eligible"


def test_gap_detection_foreign_vi_skip(tmp_path):
    """A foreign vi sidecar (present, not in ledger) is skipped — never clobbered (D-26, AUTO-04)."""
    scan_mod = pytest.importorskip("trezarr.discover.scan")
    is_eligible = getattr(scan_mod, "is_eligible", None) or pytest.importorskip(
        "trezarr.discover.gap"
    ).is_eligible

    ledger = _make_minimal_ledger(tmp_path)

    src = tmp_path / "Show.S01E05.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    # A foreign .vi.srt exists (e.g. Bazarr-downloaded) but is not in the ledger
    foreign_vi = tmp_path / "Show.S01E05.vi.srt"
    foreign_vi.write_text("foreign", encoding="utf-8")

    eligible, reason = is_eligible(src, ledger)
    assert eligible is False, "Foreign vi sidecar must not be clobbered (D-26)"
    assert "foreign" in reason.lower() or "vi" in reason.lower(), (
        f"Expected a foreign/vi reason, got: {reason!r}"
    )


def test_idempotency_skip_unchanged(tmp_path):
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

    ledger = _make_minimal_ledger(
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

    eligible, _reason = is_eligible(src, ledger)
    assert eligible is False, "Unchanged source + status=done must skip (AUTO-03)"


def test_idempotency_retranslate_on_change(tmp_path):
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

    ledger = _make_minimal_ledger(
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

    eligible, reason = is_eligible(src, ledger)
    assert eligible is True, f"Changed source must trigger re-translate (got reason: {reason!r})"


def test_foreign_vi(tmp_path):
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

    ledger = _make_minimal_ledger(
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

    eligible, _reason = is_eligible(src, ledger)
    assert eligible is False, "Our own vi.srt (matching ledger entry) must NOT be re-processed (AUTO-04)"


# ──────────────────────────────────────────────────────────────────────────────
# scan_for_eligible_items — returns (list[EligibleItem], ScanStats)
# (03-REVIEWS.md HIGH #5 + MEDIUM #14)
# ──────────────────────────────────────────────────────────────────────────────


def test_scan_returns_eligible_item_and_scan_stats(tmp_path):
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
    from trezarr.cli import MediaItem  # MediaItem dataclass lives in cli.py per PATTERNS

    media = tmp_path / "Show.S01E09.mkv"
    media.write_bytes(b"\x00\x00\x00fake-mkv")

    item = MediaItem(
        local_path=media,
        source_sub_path=None,   # filled in by scan_for_eligible_items based on lang_priority
        title="Show",
        source_lang=None,
    )

    ledger = _make_minimal_ledger(tmp_path)

    result = scan_for_eligible_items([item], ledger=ledger, lang_priority=["en"])

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
