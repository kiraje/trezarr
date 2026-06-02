"""Wave 0 RED stubs: byte-identity round-trip tests for the VTT codec (FMT-04).

All tests are xfail stubs — the implementation (trezarr.subtitles.vtt) does not
yet exist. Tests will go GREEN in Wave 2.

Covers:
  FMT-04 — Byte-identical round-trip for all 8 VTT fixture files
  FMT-04 — Cue settings string preserved verbatim on the timing line
  FMT-04 — STYLE / REGION / NOTE blocks preserved verbatim
  D-101  — Hourless timecode (MM:SS.mmm) round-trips correctly
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"

_VTT_FIXTURE_FILES = [
    "minimal.vtt",
    "cue_settings.vtt",
    "voices.vtt",
    "style_region.vtt",
    "inline_timestamp.vtt",
    "hourless_tc.vtt",
    "note_block.vtt",
    "crlf.vtt",
]


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.vtt not yet implemented (Wave 2)",
)
@pytest.mark.parametrize("fixture", _VTT_FIXTURE_FILES)
def test_byte_identical_roundtrip(tmp_path, fixture):
    """Read a VTT fixture, write it back, assert bytes are identical (FMT-04).

    Mirrors the SRT byte-identity contract in test_srt_roundtrip.py exactly.
    """
    import warnings

    vtt_mod = pytest.importorskip("trezarr.subtitles.vtt")
    read_vtt = vtt_mod.read_vtt
    write_vtt = vtt_mod.write_vtt

    src = FIXTURES / fixture
    original_bytes = src.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        doc = read_vtt(str(src))
    out = tmp_path / fixture
    write_vtt(doc, str(out))
    assert out.read_bytes() == original_bytes, (
        f"Round-trip not byte-identical for {fixture}"
    )


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.vtt not yet implemented (Wave 2)",
)
def test_cue_settings_preserved(tmp_path):
    """cue_settings.vtt: cue settings strings on timing lines must survive round-trip (FMT-04)."""
    vtt_mod = pytest.importorskip("trezarr.subtitles.vtt")
    read_vtt = vtt_mod.read_vtt
    write_vtt = vtt_mod.write_vtt

    src = FIXTURES / "cue_settings.vtt"
    original_bytes = src.read_bytes()
    doc = read_vtt(str(src))
    out = tmp_path / "cue_settings.vtt"
    write_vtt(doc, str(out))
    output_bytes = out.read_bytes()
    assert b"position:50%" in output_bytes, "Expected 'position:50%' cue setting preserved"
    assert b"line:90%" in output_bytes, "Expected 'line:90%' cue setting preserved"
    assert b"size:50%" in output_bytes, "Expected 'size:50%' cue setting preserved"
    assert output_bytes == original_bytes, "cue_settings.vtt round-trip not byte-identical"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.vtt not yet implemented (Wave 2)",
)
def test_blocks_verbatim(tmp_path):
    """style_region.vtt and note_block.vtt: STYLE, REGION, NOTE blocks preserved verbatim (FMT-04, D-100)."""
    vtt_mod = pytest.importorskip("trezarr.subtitles.vtt")
    read_vtt = vtt_mod.read_vtt
    write_vtt = vtt_mod.write_vtt

    # Check STYLE and REGION blocks.
    src = FIXTURES / "style_region.vtt"
    original_bytes = src.read_bytes()
    doc = read_vtt(str(src))
    out = tmp_path / "style_region.vtt"
    write_vtt(doc, str(out))
    output_bytes = out.read_bytes()
    assert b"STYLE" in output_bytes, "Expected STYLE block preserved"
    assert b"REGION" in output_bytes, "Expected REGION block preserved"
    assert output_bytes == original_bytes, "style_region.vtt round-trip not byte-identical"

    # Check NOTE block.
    src_note = FIXTURES / "note_block.vtt"
    original_note_bytes = src_note.read_bytes()
    doc_note = read_vtt(str(src_note))
    out_note = tmp_path / "note_block.vtt"
    write_vtt(doc_note, str(out_note))
    output_note_bytes = out_note.read_bytes()
    assert b"NOTE" in output_note_bytes, "Expected NOTE block preserved"
    assert output_note_bytes == original_note_bytes, "note_block.vtt round-trip not byte-identical"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.vtt not yet implemented (Wave 2)",
)
def test_hourless_timecode_roundtrip(tmp_path):
    """hourless_tc.vtt: MM:SS.mmm timecodes must be preserved verbatim on write-back (D-101)."""
    vtt_mod = pytest.importorskip("trezarr.subtitles.vtt")
    read_vtt = vtt_mod.read_vtt
    write_vtt = vtt_mod.write_vtt

    src = FIXTURES / "hourless_tc.vtt"
    original_bytes = src.read_bytes()
    doc = read_vtt(str(src))

    # Verify the SubLine stores the verbatim timecode string (no normalization).
    assert any(":" in sl.start_tc and sl.start_tc.count(":") == 1 for sl in doc.lines), (
        "Expected at least one SubLine with hourless MM:SS.mmm start_tc"
    )

    out = tmp_path / "hourless_tc.vtt"
    write_vtt(doc, str(out))
    assert out.read_bytes() == original_bytes, "hourless_tc.vtt round-trip not byte-identical"
