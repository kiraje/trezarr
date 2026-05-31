"""Golden-file byte-identity round-trip tests for the SRT codec (FMT-01).

The SRT codec must preserve the original bytes exactly on read → write. This
includes encoding/BOM, line endings, indices, timecodes, inline tags, text,
inter-cue blank-line spacing, trailing newlines, and malformed cue blocks
(preserved verbatim per D-10). These tests assert that contract for real — no
xfail masking (CR-03).
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"

_FIXTURE_FILES = [
    "minimal.srt",
    "crlf_indices.srt",
    "period_timecodes.srt",
    "utf8bom.srt",
    "inline_bold.srt",
    # Malformed block is kept as opaque pass-through (D-10) so it still
    # round-trips byte-identically.
    "malformed_index.srt",
    # Edge cases that the previous (normalising) codec silently corrupted —
    # now exercised so the byte-identity contract is genuinely enforced (CR-01).
    "single_trailing_newline.srt",  # file ends in a single \n (most common shape)
    "extra_blank_lines.srt",        # >1 blank line between cues must be preserved
    "mixed_lf_in_crlf.srt",         # LF inside a CRLF file (D-09 verbatim text)
    "tc_trailing_data.srt",         # trailing coordinate data on the timecode line
]


@pytest.mark.parametrize("fixture", _FIXTURE_FILES)
def test_byte_identical_roundtrip(tmp_path, fixture):
    """Read a golden SRT fixture, write it back, assert bytes are identical.

    This is the primary FMT-01 contract: the codec must preserve the original
    encoding, BOM, line endings, indices, timecodes, inline tags, and text
    byte-for-byte. The only field the translation pipeline is allowed to change
    is SubLine.text — everything else is immutable.
    """
    import warnings

    from trezarr.subtitles.srt import read_srt, write_srt  # deferred import

    src = FIXTURES / fixture
    original_bytes = src.read_bytes()
    # Malformed/garbled blocks legitimately emit a UserWarning on read (D-10);
    # that is preserve-and-flag behaviour, not a failure.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        doc = read_srt(str(src))
    out = tmp_path / fixture
    write_srt(doc, str(out))
    assert out.read_bytes() == original_bytes, (
        f"Round-trip not byte-identical for {fixture}"
    )


def test_malformed_block_preserved_and_flagged(tmp_path):
    """A malformed cue is flagged with a UserWarning AND preserved verbatim (D-10).

    The previous codec *skipped* malformed blocks, which both lost data and broke
    byte identity (CR-01 #4). The codec now keeps the malformed block as an opaque
    pass-through (SubLine.raw set) so write-back is byte-identical, while still
    emitting the UserWarning so the malformation is surfaced.
    """
    from trezarr.subtitles.srt import read_srt, write_srt  # deferred import

    src = FIXTURES / "malformed_index.srt"
    original_bytes = src.read_bytes()

    with pytest.warns(UserWarning, match="malformed SRT block"):
        doc = read_srt(str(src))

    # Both cues are retained (the malformed one is NOT dropped).
    assert len(doc.lines) == 2
    # The malformed cue is kept as an opaque pass-through block.
    malformed = [sl for sl in doc.lines if sl.raw is not None]
    assert len(malformed) == 1
    assert "abc" in malformed[0].raw

    # And it round-trips byte-identically.
    out = tmp_path / "malformed_index.srt"
    write_srt(doc, str(out))
    assert out.read_bytes() == original_bytes
