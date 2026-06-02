"""Wave 0 RED stubs: byte-identity round-trip tests for the ASS/SSA codec (FMT-02).

All tests are xfail stubs — the implementation (trezarr.subtitles.ass) does not
yet exist. Tests will go GREEN in Wave 2.

Covers:
  FMT-02 — Byte-identical round-trip for all 8 ASS/SSA fixture files
  FMT-02 — \\N hard-break preserved verbatim in Text field
  FMT-02 — [Script Info] / [V4+ Styles] section headers byte-identical
  FMT-02 — Comment: events preserved verbatim (not translated)
  FMT-02 — SSA ([V4 Styles]) variant byte-identical round-trip
  D-10   — Malformed Dialogue preserved-and-flagged (UserWarning + raw set)
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"

_ASS_FIXTURE_FILES = [
    "minimal.ass",
    "karaoke.ass",
    "drawing.ass",
    "pos_an8.ass",
    "mixed.ass",
    "crlf.ass",
    "ssa_v4.ssa",
    "utf8bom.ass",
]


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.ass not yet implemented (Wave 2)",
)
@pytest.mark.parametrize("fixture", _ASS_FIXTURE_FILES)
def test_byte_identical_roundtrip(tmp_path, fixture):
    """Read an ASS/SSA fixture, write it back, assert bytes are identical (FMT-02).

    Mirrors the SRT byte-identity contract in test_srt_roundtrip.py exactly.
    """
    import warnings

    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = ass_mod.read_ass
    write_ass = ass_mod.write_ass

    src = FIXTURES / fixture
    original_bytes = src.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        doc = read_ass(str(src))
    out = tmp_path / fixture
    write_ass(doc, str(out))
    assert out.read_bytes() == original_bytes, (
        f"Round-trip not byte-identical for {fixture}"
    )


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.ass not yet implemented (Wave 2)",
)
def test_line_break_preserved(tmp_path):
    r"""mixed.ass: the \\N hard-break in Dialogue Text must survive round-trip (FMT-02).

    \\N is a raw backslash + capital N in the ASS Text field — it is not a file line
    ending, it is an in-text hard-break control sequence. The codec must NOT
    interpret it as a newline during parse or join.
    """
    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = ass_mod.read_ass

    src = FIXTURES / "mixed.ass"
    doc = read_ass(str(src))
    # The mixed.ass fixture has a Dialogue with \N in the Text field.
    texts = [sl.text for sl in doc.lines if sl.raw is None]
    assert any(r"\N" in t for t in texts), (
        r"Expected at least one SubLine.text to contain \N (hard-break) from mixed.ass"
    )


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.ass not yet implemented (Wave 2)",
)
def test_section_headers_preserved(tmp_path):
    """Write-back bytes must contain the original [Script Info] header verbatim (FMT-02)."""
    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = ass_mod.read_ass
    write_ass = ass_mod.write_ass

    src = FIXTURES / "minimal.ass"
    doc = read_ass(str(src))
    out = tmp_path / "minimal.ass"
    write_ass(doc, str(out))
    output_bytes = out.read_bytes()
    assert b"[Script Info]" in output_bytes, "Expected [Script Info] in write-back bytes"
    assert b"[V4+ Styles]" in output_bytes, "Expected [V4+ Styles] in write-back bytes"
    assert b"[Events]" in output_bytes, "Expected [Events] in write-back bytes"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.ass not yet implemented (Wave 2)",
)
def test_comments_verbatim(tmp_path):
    """Comment: event lines must be preserved verbatim in write-back bytes (FMT-02, D-97)."""
    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = ass_mod.read_ass
    write_ass = ass_mod.write_ass

    src = FIXTURES / "mixed.ass"
    doc = read_ass(str(src))
    out = tmp_path / "mixed.ass"
    write_ass(doc, str(out))
    output_bytes = out.read_bytes()
    assert b"Comment:" in output_bytes, (
        "Expected Comment: event to be preserved verbatim in write-back bytes"
    )


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.ass not yet implemented (Wave 2)",
)
def test_ssa_roundtrip(tmp_path):
    """ssa_v4.ssa ([V4 Styles] variant) must round-trip byte-identically (FMT-02)."""
    import warnings

    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = ass_mod.read_ass
    write_ass = ass_mod.write_ass

    src = FIXTURES / "ssa_v4.ssa"
    original_bytes = src.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        doc = read_ass(str(src))
    out = tmp_path / "ssa_v4.ssa"
    write_ass(doc, str(out))
    assert out.read_bytes() == original_bytes, "SSA round-trip not byte-identical"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError, UserWarning),
    strict=False,
    reason="trezarr.subtitles.ass not yet implemented (Wave 2)",
)
def test_malformed_dialogue_preserved_and_flagged(tmp_path):
    """Malformed Dialogue must emit UserWarning AND keep raw is not None (D-10).

    Uses minimal.ass as a base; the codec's D-10 path fires when a Dialogue
    line cannot be split on 9 commas into a complete field set.
    """
    import warnings

    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = ass_mod.read_ass

    # Write a version of minimal.ass with a broken Dialogue line (too few commas).
    src = tmp_path / "malformed.ass"
    src.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name\nStyle: Default\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,badline\n",
        encoding="utf-8",
    )

    with pytest.warns(UserWarning):
        doc = read_ass(str(src))

    # Malformed cue is kept as an opaque pass-through.
    raw_lines = [sl for sl in doc.lines if sl.raw is not None]
    assert len(raw_lines) >= 1, "Expected at least one SubLine with raw set for malformed Dialogue"
