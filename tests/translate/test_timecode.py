"""Timecode parser tests for trezarr.translate._timecode.tc_to_ms (D-101).

SRT assertions (HH:MM:SS,mmm and HH:MM:SS.mmm) are concrete and must pass GREEN
immediately — tc_to_ms already handles these forms.

ASS centisecond (H:MM:SS.cc) and VTT hourless (MM:SS.mmm) assertions are marked
xfail(strict=False) because the tc_to_ms extension for those forms lands in Wave 1.

All assertions follow the exact values from RESEARCH §9.4.
"""
import pytest


# ---------------------------------------------------------------------------
# Concrete SRT assertions — must pass GREEN immediately (tc_to_ms already handles)
# ---------------------------------------------------------------------------


def test_srt_standard_timecode():
    """tc_to_ms('00:00:01,000') == 1000 — baseline SRT comma-separated ms (existing contract)."""
    tc_mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = tc_mod.tc_to_ms

    assert tc_to_ms("00:00:01,000") == 1000


def test_srt_period_separator():
    """tc_to_ms('00:01:23.456') == 83456 — SRT with period separator (existing contract)."""
    tc_mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = tc_mod.tc_to_ms

    assert tc_to_ms("00:01:23.456") == 83456


def test_srt_large_hour():
    """tc_to_ms('01:00:00,000') == 3600000 — 1-hour SRT timecode (existing contract)."""
    tc_mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = tc_mod.tc_to_ms

    assert tc_to_ms("01:00:00,000") == 3600000


def test_malformed_returns_zero():
    """tc_to_ms('garbage') == 0 — malformed contract unchanged (existing contract)."""
    tc_mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = tc_mod.tc_to_ms

    assert tc_to_ms("garbage") == 0


# ---------------------------------------------------------------------------
# ASS centisecond timecodes — xfail until Wave 1 (tc_to_ms extension)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason="tc_to_ms ASS centisecond extension (H:MM:SS.cc) not yet implemented (Wave 1)",
)
def test_ass_centisecond_basic():
    """tc_to_ms('0:01:23.45') == 83450 — ASS H:MM:SS.cc, cc*10=ms (RESEARCH §9.4)."""
    tc_mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = tc_mod.tc_to_ms

    assert tc_to_ms("0:01:23.45") == 83450


@pytest.mark.xfail(
    strict=False,
    reason="tc_to_ms ASS centisecond extension (H:MM:SS.cc) not yet implemented (Wave 1)",
)
def test_ass_centisecond_one_hour():
    """tc_to_ms('1:00:00.00') == 3600000 — ASS 1-hour timecode (RESEARCH §9.4)."""
    tc_mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = tc_mod.tc_to_ms

    assert tc_to_ms("1:00:00.00") == 3600000


# ---------------------------------------------------------------------------
# VTT hourless timecodes — xfail until Wave 1 (tc_to_ms extension)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason="tc_to_ms VTT hourless extension (MM:SS.mmm) not yet implemented (Wave 1)",
)
def test_vtt_hourless():
    """tc_to_ms('01:23.456') == 83456 — VTT MM:SS.mmm hourless form (RESEARCH §9.4)."""
    tc_mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = tc_mod.tc_to_ms

    assert tc_to_ms("01:23.456") == 83456


@pytest.mark.xfail(
    strict=False,
    reason="tc_to_ms VTT with-hours extension (HH:MM:SS.mmm period) not yet implemented (Wave 1)",
)
def test_vtt_with_explicit_zero_hours():
    """tc_to_ms('00:01:23.456') == 83456 — VTT HH:MM:SS.mmm with explicit 0 hours (RESEARCH §9.4)."""
    tc_mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = tc_mod.tc_to_ms

    # NOTE: the existing _TC_PARSE_RE uses [,.] so it matches '00:01:23.456' as well as '00:01:23,456'.
    # If the existing regex already handles this, this test will pass even before the extension —
    # that is acceptable (strict=False).
    assert tc_to_ms("00:01:23.456") == 83456
