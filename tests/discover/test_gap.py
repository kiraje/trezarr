"""Wave 0 RED stubs for D-110 source-language-change Case 1.5 (gap detection extension).

These stubs cover the new Phase-10 eligibility cases: re-translation when a richer
source language is available (Case 1.5), no-loop guard after a source-language upgrade,
and foreign-vi-unchanged guard (D-26 D-110 non-regression).

All stubs use xfail(strict=False) because:
  - check_by_output_path() does not exist on LedgerSQLA / LedgerProtocol yet (Phase 10-02)
  - The is_eligible Case 1.5 branch does not exist in gap.py yet

Covers:
  D-110  Case 1.5 — vi exists from a ledger entry for a different (worse) source language,
                    new (richer) source available → eligible=True, reason contains "richer source"
  D-110  foreign-vi-unchanged — vi exists but NO ledger entry at all (truly foreign) →
                    eligible=False (D-26 non-regression)
  D-110  no-loop-after-upgrade — the upgraded source (ko) is already in the ledger with
                    status="done" and vi_path exists → eligible=False (Case 2 fires, no re-translate)

Note: test_scan.py covers all the existing Cases 0–4 (including Case 1 foreign-vi).
These stubs extend gap.py with the new source-upgrade logic only.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Case 1.5 — source-language upgrade eligible (D-110)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="D-110 Case 1.5 source-upgrade eligibility not yet implemented (Phase 10)",
)
async def test_source_upgrade_eligible(tmp_path):
    """Case 1.5: vi exists from a ledger entry for a worse source → eligible=True, reason='richer source'.

    Setup:
      - source_sub_path = /tv/Show/S01E01.ko.srt  (Korean — Tier-1, richer)
      - vi_path          = /tv/Show/S01E01.vi.srt  (exists on disk)
      - ledger.check("ko.srt") → None  (ko is NEW, never translated)
      - ledger.check_by_output_path("vi.srt") → LedgerEntry(source="en.srt", status="done")
        (vi was produced from English — a weaker source)

    Expected: is_eligible returns (True, reason) where "richer source" is in reason.
    """
    from trezarr.discover.gap import is_eligible  # noqa: PLC0415
    from trezarr.output.ledger import LedgerEntry  # noqa: PLC0415

    # Create synthetic subtitle files on disk
    ko_sub = tmp_path / "Show.S01E01.ko.srt"
    ko_sub.write_bytes(b"1\n00:00:01,000 --> 00:00:03,000\nAnnyeonghaseyo\n")

    vi_path = tmp_path / "Show.S01E01.vi.srt"
    vi_path.write_bytes(b"1\n00:00:01,000 --> 00:00:03,000\nXin chao\n")

    # The vi was produced from the English source (weaker source)
    en_ledger_entry = LedgerEntry(
        source_path=str(tmp_path / "Show.S01E01.en.srt"),
        output_path=str(vi_path),
        status="done",
        content_hash="abc123",
    )

    # Mock ledger: check(ko.srt) → None; check_by_output_path(vi.srt) → en entry
    mock_ledger = MagicMock()
    mock_ledger.check = AsyncMock(return_value=None)
    mock_ledger.check_by_output_path = AsyncMock(return_value=en_ledger_entry)

    result = await is_eligible(ko_sub, mock_ledger)

    assert isinstance(result, tuple) and len(result) == 2, (
        f"Expected (bool, str) tuple, got {result!r}"
    )
    eligible, reason = result
    assert eligible is True, (
        f"Expected eligible=True for richer source upgrade (D-110 Case 1.5), got {eligible!r}"
    )
    assert "richer source" in reason.lower() or "upgrade" in reason.lower() or "richer" in reason.lower(), (
        f"Expected reason to contain 'richer source', got {reason!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Foreign-vi-unchanged — D-26 non-regression (D-110)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="D-110 foreign-vi-unchanged D-26 guard requires check_by_output_path (Phase 10)",
)
async def test_foreign_vi_unchanged(tmp_path):
    """Foreign vi sidecar with NO ledger entry → eligible=False (D-26 non-regression).

    Setup:
      - source_sub_path = /tv/Show/S01E01.ko.srt
      - vi_path          = /tv/Show/S01E01.vi.srt  (exists on disk — foreign)
      - ledger.check("ko.srt") → None
      - ledger.check_by_output_path("vi.srt") → None  (truly foreign: we never wrote it)

    Expected: is_eligible returns (False, ...) — never clobber a foreign vi sidecar.
    """
    from trezarr.discover.gap import is_eligible  # noqa: PLC0415

    ko_sub = tmp_path / "Show.S01E01.ko.srt"
    ko_sub.write_bytes(b"1\n00:00:01,000 --> 00:00:03,000\nAnnyeonghaseyo\n")

    # Foreign vi sidecar — NOT in the ledger
    vi_path = tmp_path / "Show.S01E01.vi.srt"
    vi_path.write_bytes(b"1\n00:00:01,000 --> 00:00:03,000\nXin chao (foreign)\n")

    mock_ledger = MagicMock()
    mock_ledger.check = AsyncMock(return_value=None)
    mock_ledger.check_by_output_path = AsyncMock(return_value=None)

    result = await is_eligible(ko_sub, mock_ledger)

    assert isinstance(result, tuple) and len(result) == 2, (
        f"Expected (bool, str) tuple, got {result!r}"
    )
    eligible, reason = result
    assert eligible is False, (
        f"D-26 non-regression: expected eligible=False for foreign vi sidecar, got {eligible!r}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# No-loop after upgrade — Case 2 fires (D-110)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.xfail(
    strict=False,
    raises=(ImportError, AssertionError, TypeError),
    reason="D-110 no-loop-after-upgrade requires check_by_output_path (Phase 10)",
)
async def test_no_loop_after_upgrade(tmp_path):
    """After Korean translation is recorded, the same Korean scan → already_done (Case 2, no loop).

    Setup:
      - source_sub_path = /tv/Show/S01E01.ko.srt
      - vi_path          = /tv/Show/S01E01.vi.srt  (exists on disk)
      - ledger.check("ko.srt") → LedgerEntry(source="ko.srt", status="done")
        (Korean translation is complete)

    Expected: is_eligible returns (False, reason containing "already") — Case 2 fires,
    no re-translation loop.
    """
    from trezarr.discover.gap import is_eligible  # noqa: PLC0415
    from trezarr.output.ledger import LedgerEntry  # noqa: PLC0415

    ko_sub = tmp_path / "Show.S01E01.ko.srt"
    ko_sub.write_bytes(b"1\n00:00:01,000 --> 00:00:03,000\nAnnyeonghaseyo\n")

    vi_path = tmp_path / "Show.S01E01.vi.srt"
    vi_path.write_bytes(b"1\n00:00:01,000 --> 00:00:03,000\nXin chao\n")

    # Korean is already done in the ledger — content hash matches current bytes
    content_hash = __import__("hashlib").sha256(ko_sub.read_bytes()).hexdigest()[:16]
    ko_entry = LedgerEntry(
        source_path=str(ko_sub),
        output_path=str(vi_path),
        status="done",
        content_hash=content_hash,
    )

    mock_ledger = MagicMock()
    mock_ledger.check = AsyncMock(return_value=ko_entry)
    # check_by_output_path should not even be called in Case 2 (entry found by source_path)
    mock_ledger.check_by_output_path = AsyncMock(return_value=None)

    result = await is_eligible(ko_sub, mock_ledger)

    assert isinstance(result, tuple) and len(result) == 2, (
        f"Expected (bool, str) tuple, got {result!r}"
    )
    eligible, reason = result
    assert eligible is False, (
        f"D-110 no-loop: expected eligible=False after ko is done, got {eligible!r}"
    )
    assert "already" in reason.lower() or "unchanged" in reason.lower(), (
        f"Expected reason to contain 'already' or 'unchanged', got {reason!r}"
    )
