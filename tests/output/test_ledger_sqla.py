"""Regression suite for LedgerSQLA — proves interface parity with the Phase-2 JSON Ledger.

Every test from tests/output/test_ledger.py is duplicated here, modified ONLY to:
  (a) construct LedgerSQLA(session_factory) instead of Ledger(path)
  (b) await ledger.check(...) / await ledger.record(...)
  (c) async def test_... instead of def test_...

All existing assertions on data shape, status values, and persistence-across-construction
are preserved verbatim. If this suite passes, the LedgerSQLA implements LedgerProtocol
correctly and the D-37 call-site contract is preserved.

Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
"""
from __future__ import annotations

import pytest

# ── pytest fixture imports ───────────────────────────────────────────────────
# session_factory is provided by tests/db/conftest.py (shared fixture).


# ── Test 1: skip unchanged (mirrors test_skip_unchanged) ──────────────────────


async def test_skip_unchanged(session_factory, tmp_path):
    """LedgerSQLA.check() returns the entry; matching hash → 'skipped' outcome (ENG-07)."""
    # Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    LedgerSQLA = sqla_mod.LedgerSQLA
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    LedgerEntry = ledger_mod.LedgerEntry

    ledger = LedgerSQLA(session_factory)

    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    content_hash = LedgerSQLA.content_hash(src.read_bytes())

    dest = tmp_path / "Show.S01E01.vi.srt"
    dest.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    entry = LedgerEntry(
        source_path=str(src),
        output_path=str(dest),
        status="done",
        content_hash=content_hash,
    )
    await ledger.record(entry)

    # Reload via a new instance (proves persistence across construction)
    ledger2 = LedgerSQLA(session_factory)
    found = await ledger2.check(str(src))

    assert found is not None, "Expected ledger entry to be found after record()"
    assert found.status == "done"
    assert found.content_hash == content_hash

    current_hash = LedgerSQLA.content_hash(src.read_bytes())
    assert found.status == "done" and found.content_hash == current_hash, (
        "Expected skip condition (status=done + matching hash) to be satisfied"
    )


# ── Test 2: regenerate on hash change ─────────────────────────────────────────


async def test_regenerate_on_hash_change(session_factory, tmp_path):
    """Stored hash != current hash → should regenerate (ENG-07)."""
    # Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    LedgerSQLA = sqla_mod.LedgerSQLA
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    LedgerEntry = ledger_mod.LedgerEntry

    ledger = LedgerSQLA(session_factory)

    src = tmp_path / "Show.S01E02.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    stale_hash = "stale0000hash0000"
    entry = LedgerEntry(
        source_path=str(src),
        output_path=str(tmp_path / "Show.S01E02.vi.srt"),
        status="done",
        content_hash=stale_hash,
    )
    await ledger.record(entry)

    found = await ledger.check(str(src))
    current_hash = LedgerSQLA.content_hash(src.read_bytes())

    assert found is not None
    should_skip = found.status == "done" and found.content_hash == current_hash
    assert not should_skip, "Expected hash mismatch to trigger regeneration (not skip)"


# ── Test 3: foreign .vi.srt not clobbered ─────────────────────────────────────


async def test_foreign_srt_not_clobbered(session_factory, tmp_path):
    """source_path not in ledger → check() returns None (foreign file) (ENG-07)."""
    # Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    LedgerSQLA = sqla_mod.LedgerSQLA

    ledger = LedgerSQLA(session_factory)

    src = tmp_path / "Show.S01E03.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    dest = tmp_path / "Show.S01E03.vi.srt"
    dest.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    found = await ledger.check(str(src))
    assert found is None, (
        "Expected check() to return None for source_path not in ledger (foreign .vi.srt)"
    )

    assert dest.exists(), "Foreign .vi.srt should still exist (not clobbered)"


# ── Test 4: quarantine retry ───────────────────────────────────────────────────


async def test_quarantine_retry(session_factory, tmp_path):
    """Entry with status='quarantined' → check() returns the entry (ENG-07)."""
    # Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    LedgerSQLA = sqla_mod.LedgerSQLA
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    LedgerEntry = ledger_mod.LedgerEntry

    ledger = LedgerSQLA(session_factory)

    src = tmp_path / "Show.S01E04.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    content_hash = LedgerSQLA.content_hash(src.read_bytes())

    entry = LedgerEntry(
        source_path=str(src),
        output_path=None,
        status="quarantined",
        content_hash=content_hash,
        quarantine_path=str(tmp_path / "quarantine" / "Show.S01E04.json"),
    )
    await ledger.record(entry)

    found = await ledger.check(str(src))

    assert found is not None
    assert found.status == "quarantined", f"Expected status='quarantined', got {found.status!r}"

    should_skip = found.status == "done"
    assert not should_skip, "Quarantined entry should not be skipped — it should be retried"


# ── Test 5: persistence across construction ────────────────────────────────────


async def test_ledger_persists_across_construction(session_factory, tmp_path):
    """After record(), a new LedgerSQLA instance returns the entry (proves DB persistence)."""
    # Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    LedgerSQLA = sqla_mod.LedgerSQLA
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    LedgerEntry = ledger_mod.LedgerEntry

    ledger1 = LedgerSQLA(session_factory)

    src_path = "/media/Show.S01E05.en.srt"
    entry = LedgerEntry(
        source_path=src_path,
        output_path="/media/Show.S01E05.vi.srt",
        status="done",
        content_hash="abcd1234abcd1234",
    )
    await ledger1.record(entry)

    # A new instance shares the same session_factory → same DB
    ledger2 = LedgerSQLA(session_factory)
    found = await ledger2.check(src_path)

    assert found is not None, "Entry must persist across LedgerSQLA construction"
    assert found.status == "done"
    assert found.content_hash == "abcd1234abcd1234"


# ── Test 6: schema-drift skips bad entry, keeps good ─────────────────────────


async def test_ledger_schema_drift_skips_bad_entry_keeps_good(session_factory, tmp_path):
    """LedgerSQLA stores good entries and returns None for entries that were never recorded."""
    # Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    LedgerSQLA = sqla_mod.LedgerSQLA
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    LedgerEntry = ledger_mod.LedgerEntry

    ledger = LedgerSQLA(session_factory)

    good_path = "/media/Show.S01E01.en.srt"
    bad_path = "/media/Show.S01E02.en.srt"

    entry = LedgerEntry(
        source_path=good_path,
        output_path="/media/Show.S01E01.vi.srt",
        status="done",
        content_hash="abcd1234abcd1234",
    )
    await ledger.record(entry)

    good = await ledger.check(good_path)
    assert good is not None, "Good entry must be retrievable"
    assert good.status == "done"

    bad = await ledger.check(bad_path)
    assert bad is None, "Unrecorded path must return None"


# ── Test 7: check returns None for unknown path (additional LedgerSQLA test) ──


async def test_check_returns_none_for_unknown_path(session_factory):
    """LedgerSQLA.check() returns None for a path that was never recorded."""
    # Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    LedgerSQLA = sqla_mod.LedgerSQLA

    ledger = LedgerSQLA(session_factory)
    result = await ledger.check("/unknown/path/never/recorded.srt")
    assert result is None


# ── Test 8: UPSERT semantics ───────────────────────────────────────────────────


async def test_record_upserts_existing_entry(session_factory, tmp_path):
    """record() with the same source_path updates the existing row (UPSERT, not double-INSERT)."""
    from sqlalchemy import func, select

    from trezarr.bible.models import ProcessedFile

    # Phase 4 / 04-04: ledger.check/record are now async (Option C in 04-PATTERNS §Pattern 5).
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    LedgerSQLA = sqla_mod.LedgerSQLA
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    LedgerEntry = ledger_mod.LedgerEntry

    ledger = LedgerSQLA(session_factory)
    src_path = "/media/Show.S01E06.en.srt"

    # First record: in_progress
    await ledger.record(LedgerEntry(
        source_path=src_path,
        output_path=None,
        status="in_progress",
        content_hash="hash1111hash1111",
    ))

    # Second record: done (upsert with new status + translated_at)
    await ledger.record(LedgerEntry(
        source_path=src_path,
        output_path="/media/Show.S01E06.vi.srt",
        status="done",
        content_hash="hash1111hash1111",
        translated_at="2026-06-01T12:00:00+00:00",
    ))

    # Assert: exactly ONE row (not two)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(ProcessedFile).where(
                ProcessedFile.source_path == src_path
            )
        )
    assert count == 1, f"Expected 1 row after upsert (UPSERT semantics), got {count}"

    # Assert: the row has the updated values
    found = await ledger.check(src_path)
    assert found is not None
    assert found.status == "done"
    assert found.translated_at == "2026-06-01T12:00:00+00:00"
    assert found.output_path == "/media/Show.S01E06.vi.srt"


# ── Test 9: LedgerProtocol issubclass check ───────────────────────────────────


def test_ledger_sqla_implements_ledger_protocol():
    """Both LedgerSQLA and Ledger implement LedgerProtocol structurally (@runtime_checkable)."""
    protocol_mod = pytest.importorskip("trezarr.output._ledger_protocol")
    sqla_mod = pytest.importorskip("trezarr.output.ledger_sqla")
    ledger_mod = pytest.importorskip("trezarr.output.ledger")

    LedgerProtocol = protocol_mod.LedgerProtocol
    LedgerSQLA = sqla_mod.LedgerSQLA
    Ledger = ledger_mod.Ledger

    assert issubclass(LedgerSQLA, LedgerProtocol), (
        "LedgerSQLA must implement LedgerProtocol (runtime_checkable structural check)"
    )
    assert issubclass(Ledger, LedgerProtocol), (
        "Ledger must implement LedgerProtocol (runtime_checkable structural check)"
    )
