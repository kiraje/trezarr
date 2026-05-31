"""Thin custom SRT reader/writer — byte-identical round-trip (FMT-01, D-08).

This module is the SOLE SRT implementation in Trezarr.  pysubs2 is intentionally
NOT used here: empirical testing showed that pysubs2 1.8.1 unconditionally
renumbers indices from 1, normalises period-separator timecodes to comma, pads
2-digit milliseconds to 3 digits, and always outputs LF endings — all of which
break byte identity.  See RESEARCH.md Pitfalls 1–3.

The custom parser:
  1. Detects encoding via :func:`~trezarr.subtitles.encoding.detect_encoding`.
  2. Splits on blank lines (handles both LF and CRLF).
  3. Stores index, start_tc, end_tc as verbatim source strings (never parsed).
  4. Stores cue text including all inline tags intact (D-09).
  5. Skips malformed blocks with a ``UserWarning`` (D-10 preserve-and-flag).

ReDoS mitigation: the timecode regex is applied only to single lines that have
already been split from their block; ``[,\\.]`` and ``\\d+`` have no nested
quantifiers and cannot backtrack catastrophically (T-01-02-02).
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

from .encoding import detect_encoding
from .model import SubDoc, SubLine

# Timecode pattern: ``HH:MM:SS,mmm`` or ``HH:MM:SS.mmm`` (period or comma
# separator; any number of millisecond digits preserved verbatim).
# Applied only to a single already-split line — safe against ReDoS.
_TC_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,.]\d+)"  # start timecode
    r"\s*-->\s*"                     # separator (allow surrounding spaces)
    r"(\d{2}:\d{2}:\d{2}[,.]\d+)"  # end timecode
)

# An index line must be an integer (one or more decimal digits, no sign).
_INDEX_RE = re.compile(r"^\d+$")


def read_srt(path: str | Path) -> SubDoc:
    """Parse an SRT file into a :class:`SubDoc`, preserving all source properties.

    Encoding is auto-detected (BOM-first → UTF-8 → charset-normalizer).  The
    line-ending style (LF or CRLF) and trailing-blank-line flag are captured so
    that :func:`write_srt` can reconstruct the original bytes exactly.

    Malformed cue blocks (non-integer index or missing/invalid timecode line) are
    skipped with a ``UserWarning`` rather than raising an exception (D-10).

    Args:
        path: Path to the ``.srt`` file (str or :class:`pathlib.Path`).

    Returns:
        A :class:`SubDoc` containing the parsed cues and file-level metadata.
    """
    raw_bytes = Path(path).read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding)

    # Detect line-ending style from the decoded text.
    le: str = "\r\n" if "\r\n" in text else "\n"

    # Detect trailing blank line: true when the file ends with two consecutive
    # line endings (i.e. a blank line after the last cue).  Strip only
    # horizontal whitespace before checking so that a stray trailing space does
    # not mask a real blank-line terminator.
    trailing = text.rstrip(" \t").endswith(le + le)

    # Split into cue blocks on any blank-line boundary (handles mixed LF/CRLF).
    blocks = re.split(r"\r?\n\r?\n", text.strip())

    lines: list[SubLine] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        block_lines = block.splitlines()

        # A valid cue block must have at least an index line and a timecode line.
        if len(block_lines) < 2:
            warnings.warn(
                f"read_srt: malformed SRT block (too few lines) — skipping:\n{block!r}",
                UserWarning,
                stacklevel=2,
            )
            continue

        index = block_lines[0].strip()
        tc_match = _TC_RE.match(block_lines[1])

        # Both the index and the timecode must be valid; otherwise skip (D-10).
        if not tc_match or not _INDEX_RE.match(index):
            warnings.warn(
                f"read_srt: malformed SRT block (invalid index {index!r} or timecode) "
                f"— skipping:\n{block!r}",
                UserWarning,
                stacklevel=2,
            )
            continue

        # Rejoin multi-line cue text using the *detected* line ending so that
        # write_srt can write it back without altering the original separators.
        text_body = le.join(block_lines[2:])

        lines.append(
            SubLine(
                index=index,
                start_tc=tc_match.group(1),
                end_tc=tc_match.group(2),
                text=text_body,
            )
        )

    return SubDoc(lines=lines, encoding=encoding, line_ending=le, trailing_newline=trailing)


def write_srt(doc: SubDoc, path: str | Path) -> None:
    """Serialise a :class:`SubDoc` back to an SRT file.

    The output is encoded with ``doc.encoding`` (preserving BOM for
    ``"utf-8-sig"``), uses ``doc.line_ending`` throughout, and appends a
    trailing blank line when ``doc.trailing_newline`` is ``True`` — all
    mirroring the properties detected by :func:`read_srt`.

    Args:
        doc:  The subtitle document to serialise.
        path: Destination path for the ``.srt`` file (str or :class:`pathlib.Path`).
    """
    le = doc.line_ending
    parts = [
        f"{sl.index}{le}{sl.start_tc} --> {sl.end_tc}{le}{sl.text}"
        for sl in doc.lines
    ]
    result = (le + le).join(parts)
    if doc.trailing_newline:
        result += le + le
    Path(path).write_bytes(result.encode(doc.encoding))
