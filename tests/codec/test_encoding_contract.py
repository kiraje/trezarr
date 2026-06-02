"""CR-01 regression: write_ass / write_vtt must honour the D-19 UTF-8 output
contract (FMT-05), encoding with ``doc.encoding`` rather than the source
encoding captured in the envelope (``ass_doc.encoding`` / ``vtt_doc.encoding``).

Before the fix both writers encoded with the envelope's source encoding. On the
vi-sidecar path ``write_vi_sidecar`` sets ``doc.encoding='utf-8'`` to force UTF-8
output, but that override was silently dropped — a non-UTF-8 source produced a
non-UTF-8 (or unwritable) sidecar. These tests pin the override: a Vietnamese
character that is NOT representable in latin-1 must still round-trip as UTF-8
when ``doc.encoding='utf-8'`` even though the envelope's encoding is 'latin-1'.

(Pre-fix behaviour: ``"ệ".encode("latin-1")`` raises UnicodeEncodeError → fail.)
"""
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"

# 'ệ' (U+1EC7) and 'ế' (U+1EBF) are outside the latin-1 codepage.
_VIETNAMESE = "Tiếng Việt: chào ệ"


def test_write_ass_forces_doc_encoding_over_envelope(tmp_path):
    ass_mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass, write_ass = ass_mod.read_ass, ass_mod.write_ass

    doc = read_ass(str(FIXTURES / "pos_an8.ass"))
    # Simulate the production vi-sidecar path: a latin-1 source whose envelope
    # captured 'latin-1', but write_vi_sidecar forces doc.encoding='utf-8'.
    doc.envelope.encoding = "latin-1"
    doc.encoding = "utf-8"
    doc.lines[0].text = _VIETNAMESE  # non-latin-1 dialogue text

    out = tmp_path / "pos_an8.vi.ass"
    write_ass(doc, str(out))  # must NOT raise; must write UTF-8

    raw = out.read_bytes()
    assert raw.decode("utf-8"), "output must be valid UTF-8 (D-19 / FMT-05)"
    assert _VIETNAMESE in raw.decode("utf-8")


def test_write_vtt_forces_doc_encoding_over_envelope(tmp_path):
    vtt_mod = pytest.importorskip("trezarr.subtitles.vtt")
    read_vtt, write_vtt = vtt_mod.read_vtt, vtt_mod.write_vtt

    doc = read_vtt(str(FIXTURES / "cue_settings.vtt"))
    doc.envelope.encoding = "latin-1"
    doc.encoding = "utf-8"
    doc.lines[0].text = _VIETNAMESE

    out = tmp_path / "cue_settings.vi.vtt"
    write_vtt(doc, str(out))

    raw = out.read_bytes()
    assert raw.decode("utf-8"), "output must be valid UTF-8 (D-19 / FMT-05)"
    assert _VIETNAMESE in raw.decode("utf-8")
