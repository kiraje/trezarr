"""Wave 0 RED stubs: format dispatcher routing tests (D-94).

All tests are xfail stubs — the implementation (trezarr.subtitles.dispatch) does not
yet exist. Tests will go GREEN in Wave 3.

Covers:
  D-94 — read_subtitle routes .srt to read_srt
  D-94 — read_subtitle routes .ass to read_ass
  D-94 — read_subtitle routes .ssa to read_ass
  D-94 — read_subtitle routes .vtt to read_vtt
  D-94 — read_subtitle raises ValueError for unknown suffix
  D-94 — write_subtitle routes by suffix correctly
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.dispatch not yet implemented (Wave 3)",
)
def test_dispatch_srt(tmp_path):
    """read_subtitle(.srt) returns a SubDoc (same as read_srt) — D-94."""
    dispatch_mod = pytest.importorskip("trezarr.subtitles.dispatch")
    read_subtitle = dispatch_mod.read_subtitle

    src = FIXTURES / "minimal.srt"
    doc = read_subtitle(str(src))
    assert doc is not None
    assert len(doc.lines) >= 1


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.dispatch not yet implemented (Wave 3)",
)
def test_dispatch_ass(tmp_path):
    """read_subtitle(.ass) returns a SubDoc — D-94."""
    dispatch_mod = pytest.importorskip("trezarr.subtitles.dispatch")
    read_subtitle = dispatch_mod.read_subtitle

    src = FIXTURES / "minimal.ass"
    doc = read_subtitle(str(src))
    assert doc is not None
    assert len(doc.lines) >= 1


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.dispatch not yet implemented (Wave 3)",
)
def test_dispatch_ssa(tmp_path):
    """read_subtitle(.ssa) routes to the same reader as .ass — D-94."""
    dispatch_mod = pytest.importorskip("trezarr.subtitles.dispatch")
    read_subtitle = dispatch_mod.read_subtitle

    src = FIXTURES / "ssa_v4.ssa"
    doc = read_subtitle(str(src))
    assert doc is not None
    assert len(doc.lines) >= 1


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.dispatch not yet implemented (Wave 3)",
)
def test_dispatch_vtt(tmp_path):
    """read_subtitle(.vtt) returns a SubDoc — D-94."""
    dispatch_mod = pytest.importorskip("trezarr.subtitles.dispatch")
    read_subtitle = dispatch_mod.read_subtitle

    src = FIXTURES / "minimal.vtt"
    doc = read_subtitle(str(src))
    assert doc is not None
    assert len(doc.lines) >= 1


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError, ValueError),
    strict=False,
    reason="trezarr.subtitles.dispatch not yet implemented (Wave 3)",
)
def test_dispatch_unknown_suffix(tmp_path):
    """read_subtitle raises ValueError for an unsupported suffix — D-94."""
    dispatch_mod = pytest.importorskip("trezarr.subtitles.dispatch")
    read_subtitle = dispatch_mod.read_subtitle

    unknown = tmp_path / "file.xyz"
    unknown.write_bytes(b"data")

    with pytest.raises(ValueError, match="Unsupported"):
        read_subtitle(str(unknown))


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="trezarr.subtitles.dispatch not yet implemented (Wave 3)",
)
def test_dispatch_write_routes_by_suffix(tmp_path):
    """write_subtitle routes to the correct writer by path suffix — D-94."""
    dispatch_mod = pytest.importorskip("trezarr.subtitles.dispatch")
    read_subtitle = dispatch_mod.read_subtitle
    write_subtitle = dispatch_mod.write_subtitle

    src = FIXTURES / "minimal.srt"
    doc = read_subtitle(str(src))
    out = tmp_path / "out.srt"
    write_subtitle(doc, str(out))
    assert out.exists(), "Expected write_subtitle to create the output file"
