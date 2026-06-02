"""Wave 0 RED stubs: AUTO-04 regression guards for ASS/VTT foreign-sidecar exclusion (D-96).

All tests are xfail stubs — the is_eligible ASS/VTT sidecar-exclusion generalization
lands in Wave 3 (D-96: .vi.<ext>-aware foreign-sidecar skip). Tests will go GREEN
in Wave 3.

Covers:
  D-96 — is_eligible returns False when a .vi.ass exists without a ledger entry
         (foreign ASS sidecar present — AUTO-04 never-clobber for ASS)
  D-96 — is_eligible returns False when a .vi.vtt exists without a ledger entry
         (foreign VTT sidecar present — AUTO-04 never-clobber for VTT)
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers (mirrors _make_minimal_ledger from test_scan.py)
# ---------------------------------------------------------------------------


async def _make_empty_ledger(tmp_path):
    """Build an empty Ledger at tmp_path/processed_files.json."""
    from trezarr.output.ledger import Ledger
    return Ledger(tmp_path / "processed_files.json")


# ---------------------------------------------------------------------------
# AUTO-04 ASS foreign-sidecar exclusion
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="is_eligible .vi.ass foreign-sidecar exclusion (D-96) not yet generalized (Wave 3)",
)
@pytest.mark.asyncio
async def test_foreign_vi_ass_excluded(tmp_path):
    """is_eligible returns (False, ...) when a .vi.ass foreign sidecar exists (D-96 / AUTO-04).

    The foreign .vi.ass was NOT written by Trezarr (no ledger entry) so it must NOT
    be clobbered — is_eligible must return False.
    """
    gap_mod = pytest.importorskip("trezarr.discover.gap")
    is_eligible = gap_mod.is_eligible

    # Source subtitle (.ass) exists.
    source_ass = tmp_path / "Show.S01E01.en.ass"
    source_ass.write_bytes(b"[Script Info]\nScriptType: v4.00+\n")

    # A foreign .vi.ass already exists (NOT written by Trezarr — no ledger entry).
    foreign_vi_ass = tmp_path / "Show.S01E01.vi.ass"
    foreign_vi_ass.write_bytes(b"[Script Info]\nScriptType: v4.00+\n")

    ledger = await _make_empty_ledger(tmp_path)

    result = await is_eligible(source_ass, ledger)

    # is_eligible returns (bool, str) or a similar structure — check False/falsy.
    if isinstance(result, tuple):
        eligible, reason = result[0], result[1] if len(result) > 1 else ""
    else:
        eligible = bool(result)
        reason = ""

    assert not eligible, (
        f"Expected is_eligible to return False for source with foreign .vi.ass present, "
        f"got eligible={eligible!r}, reason={reason!r}"
    )


# ---------------------------------------------------------------------------
# AUTO-04 VTT foreign-sidecar exclusion
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="is_eligible .vi.vtt foreign-sidecar exclusion (D-96) not yet generalized (Wave 3)",
)
@pytest.mark.asyncio
async def test_foreign_vi_vtt_excluded(tmp_path):
    """is_eligible returns (False, ...) when a .vi.vtt foreign sidecar exists (D-96 / AUTO-04).

    The foreign .vi.vtt was NOT written by Trezarr (no ledger entry) so it must NOT
    be clobbered — is_eligible must return False.
    """
    gap_mod = pytest.importorskip("trezarr.discover.gap")
    is_eligible = gap_mod.is_eligible

    # Source subtitle (.vtt) exists.
    source_vtt = tmp_path / "Episode.S02E03.en.vtt"
    source_vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHello\n", encoding="utf-8")

    # A foreign .vi.vtt already exists (NOT written by Trezarr — no ledger entry).
    foreign_vi_vtt = tmp_path / "Episode.S02E03.vi.vtt"
    foreign_vi_vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nXin chao\n", encoding="utf-8")

    ledger = await _make_empty_ledger(tmp_path)

    result = await is_eligible(source_vtt, ledger)

    if isinstance(result, tuple):
        eligible, reason = result[0], result[1] if len(result) > 1 else ""
    else:
        eligible = bool(result)
        reason = ""

    assert not eligible, (
        f"Expected is_eligible to return False for source with foreign .vi.vtt present, "
        f"got eligible={eligible!r}, reason={reason!r}"
    )
