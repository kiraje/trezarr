"""Atomic UTF-8 sidecar write with correct naming convention (D-19).

Design decisions honoured:
  D-19  Write to a NamedTemporaryFile in dest.parent (SAME filesystem as dest),
        then atomically rename via os.replace().  Crash before os.replace()
        leaves a .tmp file in dest.parent but never a partially-visible dest.
        Output is always UTF-8 regardless of the source SubDoc encoding.

Sidecar naming:
  Input:  Show.S01E01.en.srt  →  Output:  Show.S01E01.vi.srt
  Input:  Show.S01E01.srt     →  Output:  Show.S01E01.vi.srt
  Rule: strip any 2-letter ISO-639 language-code suffix from the stem
  (e.g. ".en", ".ja", ".fr"), then append ".vi.srt".
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from trezarr.subtitles.model import SubDoc
from trezarr.subtitles.srt import write_srt

# Matches a 2-letter (case-insensitive) language code at the end of the stem,
# e.g. ".en", ".ja", ".fr", ".vi".  Used to strip the source language code
# before appending ".vi.srt" to form the sidecar name.
_LANG_CODE_RE = re.compile(r'\.[a-z]{2}$', re.IGNORECASE)


def write_vi_sidecar(doc: SubDoc, media_path: str | Path) -> Path:
    """Write a translated SubDoc as a Vietnamese sidecar SRT file atomically.

    The output file is always encoded as UTF-8 (D-19), regardless of the source
    SubDoc's encoding.  The write is atomic: a NamedTemporaryFile is written in
    the same directory as the destination (ensuring same filesystem for os.replace),
    then renamed to the final path in a single POSIX-atomic operation.  If any
    exception occurs before the rename, the temporary file is cleaned up and the
    destination is never created or overwritten.

    Args:
        doc:        The translated SubDoc to serialise.
        media_path: Path to the source SRT file (str or Path).  Used to derive
                    the output sidecar path (see module docstring for naming rules).

    Returns:
        Path to the written sidecar file (Show.S01E01.vi.srt).
    """
    media_path = Path(media_path).resolve()
    stem = media_path.stem  # e.g. "Show.S01E01.en" from "Show.S01E01.en.srt"

    # Strip 2-letter language code suffix from the stem if present
    if _LANG_CODE_RE.search(stem):
        stem = stem.rsplit('.', 1)[0]  # "Show.S01E01.en" → "Show.S01E01"

    dest = media_path.parent / (stem + '.vi.srt')

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix='.tmp',
            dir=dest.parent,    # MUST be same filesystem as dest (D-19, Pitfall 3)
            delete=False,
        ) as f:
            tmp_path = Path(f.name)

        # Force UTF-8 output regardless of source encoding (D-19)
        doc_out = SubDoc(
            lines=doc.lines,
            encoding='utf-8',
            line_ending=doc.line_ending,
            separators=doc.separators,
            leading=doc.leading,
            trailer=doc.trailer,
        )
        write_srt(doc_out, tmp_path)      # reuse Phase-1 serialiser
        os.replace(tmp_path, dest)        # POSIX-atomic rename
        tmp_path = None                   # prevent cleanup in finally
        return dest
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()             # cleanup on any failure before os.replace
