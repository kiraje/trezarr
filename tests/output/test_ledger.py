"""RED test stubs for ENG-07: idempotency ledger in trezarr.output.ledger.

All imports from trezarr.output.ledger are deferred inside each test function body
so pytest collection succeeds even when the implementation module does not yet exist.
Tests skip cleanly via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Mix of synchronous and async tests. Uses tmp_path pytest fixture for file I/O.
Async test functions use async def without @pytest.mark.asyncio (asyncio_mode="auto").

Covers:
  ENG-07 — Skip when status="done" + content_hash matches
  ENG-07 — Regenerate when source hash changed (hash mismatch)
  ENG-07 — Foreign .vi.srt (not in ledger) is skipped + logged, not clobbered
  ENG-07 — Quarantined entry retried on re-run
  ENG-07 — Ledger persists atomically after record(); on-disk JSON is valid
  ENG-07 — Corrupt ledger JSON falls back to empty dict without exception
"""
import pytest


def test_skip_unchanged(tmp_path):
    """Ledger.check() returns the entry; matching hash → 'skipped' outcome (ENG-07)."""
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    Ledger = ledger_mod.Ledger
    LedgerEntry = ledger_mod.LedgerEntry

    ledger_path = tmp_path / "processed_files.json"
    ledger = Ledger(ledger_path)

    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    content_hash = Ledger.content_hash(src.read_bytes())

    dest = tmp_path / "Show.S01E01.vi.srt"
    dest.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    entry = LedgerEntry(
        source_path=str(src),
        output_path=str(dest),
        status="done",
        content_hash=content_hash,
    )
    ledger.record(entry)

    # Reload from disk and check
    ledger2 = Ledger(ledger_path)
    found = ledger2.check(str(src))

    assert found is not None, "Expected ledger entry to be found after record()"
    assert found.status == "done"
    assert found.content_hash == content_hash

    # Skip logic: same hash + status="done" → should skip
    current_hash = Ledger.content_hash(src.read_bytes())
    assert found.status == "done" and found.content_hash == current_hash, (
        "Expected skip condition (status=done + matching hash) to be satisfied"
    )


def test_regenerate_on_hash_change(tmp_path):
    """Ledger status="done" but stored hash != current hash → should regenerate (ENG-07)."""
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    Ledger = ledger_mod.Ledger
    LedgerEntry = ledger_mod.LedgerEntry

    ledger_path = tmp_path / "processed_files.json"
    ledger = Ledger(ledger_path)

    src = tmp_path / "Show.S01E02.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    # Store a different (stale) hash in the ledger
    stale_hash = "stale0000hash0000"
    entry = LedgerEntry(
        source_path=str(src),
        output_path=str(tmp_path / "Show.S01E02.vi.srt"),
        status="done",
        content_hash=stale_hash,
    )
    ledger.record(entry)

    found = ledger.check(str(src))
    current_hash = Ledger.content_hash(src.read_bytes())

    assert found is not None
    # Hash mismatch → should NOT skip
    should_skip = found.status == "done" and found.content_hash == current_hash
    assert not should_skip, (
        "Expected hash mismatch to trigger regeneration (not skip)"
    )


def test_foreign_srt_not_clobbered(tmp_path):
    """Dest .vi.srt exists but source_path not in ledger → skip + don't translate (ENG-07, D-20)."""
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    Ledger = ledger_mod.Ledger

    ledger_path = tmp_path / "processed_files.json"
    ledger = Ledger(ledger_path)  # empty ledger

    src = tmp_path / "Show.S01E03.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    # A foreign .vi.srt exists (e.g. Bazarr-downloaded)
    dest = tmp_path / "Show.S01E03.vi.srt"
    dest.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    # Key contract: source_path not in ledger → it's a foreign file
    found = ledger.check(str(src))
    assert found is None, (
        "Expected check() to return None for source_path not in ledger (foreign .vi.srt)"
    )

    # The foreign file must not be overwritten
    original_content = dest.read_text(encoding="utf-8")
    # (No translate call happens — the call site checks ledger.check() == None AND dest.exists())
    assert dest.exists(), "Foreign .vi.srt should still exist (not clobbered)"
    assert dest.read_text(encoding="utf-8") == original_content, "Foreign .vi.srt should be unchanged"


def test_quarantine_retry(tmp_path):
    """Ledger entry with status='quarantined' → should proceed to translation (ENG-07, D-20)."""
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    Ledger = ledger_mod.Ledger
    LedgerEntry = ledger_mod.LedgerEntry

    ledger_path = tmp_path / "processed_files.json"
    ledger = Ledger(ledger_path)

    src = tmp_path / "Show.S01E04.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")
    content_hash = Ledger.content_hash(src.read_bytes())

    entry = LedgerEntry(
        source_path=str(src),
        output_path=None,
        status="quarantined",
        content_hash=content_hash,
        quarantine_path=str(tmp_path / "quarantine" / "Show.S01E04.json"),
    )
    ledger.record(entry)

    found = ledger.check(str(src))

    assert found is not None
    assert found.status == "quarantined", f"Expected status='quarantined', got {found.status!r}"

    # Quarantined entry → should NOT skip; should retry (proceed to translation)
    should_skip = found.status == "done"
    assert not should_skip, "Quarantined entry should not be skipped — it should be retried"


def test_ledger_persists_atomically(tmp_path):
    """After Ledger.record(), the JSON file on disk contains the entry and is valid JSON (ENG-07)."""
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    Ledger = ledger_mod.Ledger
    LedgerEntry = ledger_mod.LedgerEntry

    import json

    ledger_path = tmp_path / "processed_files.json"
    ledger = Ledger(ledger_path)

    src_path = "/media/Show.S01E05.en.srt"
    entry = LedgerEntry(
        source_path=src_path,
        output_path="/media/Show.S01E05.vi.srt",
        status="done",
        content_hash="abcd1234abcd1234",
    )
    ledger.record(entry)

    assert ledger_path.exists(), "Ledger file should exist after record()"

    raw = ledger_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        pytest.fail(f"Ledger file is not valid JSON after record(): {e}")

    assert src_path in data, f"Expected source_path {src_path!r} in on-disk ledger"
    assert data[src_path]["status"] == "done"
    assert data[src_path]["content_hash"] == "abcd1234abcd1234"


def test_ledger_corrupt_fallback(tmp_path):
    """Malformed JSON in ledger path → Ledger._data is empty dict, no exception raised (ENG-07)."""
    ledger_mod = pytest.importorskip("trezarr.output.ledger")
    Ledger = ledger_mod.Ledger

    ledger_path = tmp_path / "processed_files.json"
    ledger_path.write_text("THIS IS NOT VALID JSON {{{", encoding="utf-8")

    # Constructing Ledger on corrupt file must not raise
    try:
        ledger = Ledger(ledger_path)
    except Exception as e:
        pytest.fail(f"Ledger() raised an exception on corrupt JSON: {e}")

    # _data must be empty (not None, not raising AttributeError)
    assert hasattr(ledger, "_data"), "Ledger must have a _data attribute"
    assert ledger._data == {}, (
        f"Expected _data == {{}} after corrupt JSON fallback, got {ledger._data!r}"
    )
