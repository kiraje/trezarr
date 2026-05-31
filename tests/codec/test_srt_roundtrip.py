"""Golden-file byte-identity round-trip tests for the SRT codec (FMT-01).

All tests are marked xfail(strict=False) until the Plan 02 codec implementation
ships. Once implementation lands, these should automatically move from XFAIL to
PASSED — at that point remove the xfail marker.
"""
import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"

_FIXTURE_FILES = [
    "minimal.srt",
    "crlf_indices.srt",
    "period_timecodes.srt",
    "utf8bom.srt",
    "inline_bold.srt",
    "malformed_index.srt",
]


@pytest.mark.parametrize("fixture", _FIXTURE_FILES)
@pytest.mark.xfail(strict=False, reason="SRT codec not yet implemented (Plan 02)")
def test_byte_identical_roundtrip(tmp_path, fixture):
    """Read a golden SRT fixture, write it back, assert bytes are identical.

    This is the primary FMT-01 contract: the codec must preserve the original
    encoding, BOM, line endings, indices, timecodes, inline tags, and text
    byte-for-byte. The only field the translation pipeline is allowed to change
    is SubLine.text — everything else is immutable.
    """
    from trezarr.subtitles.srt import read_srt, write_srt  # deferred import

    src = FIXTURES / fixture
    original_bytes = src.read_bytes()
    doc = read_srt(str(src))
    out = tmp_path / fixture
    write_srt(doc, str(out))
    assert out.read_bytes() == original_bytes, (
        f"Round-trip not byte-identical for {fixture}"
    )
