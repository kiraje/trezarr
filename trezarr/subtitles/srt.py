"""Thin custom SRT reader/writer — byte-identical round-trip (FMT-01, D-08).

This module is the SOLE SRT implementation in Trezarr.  pysubs2 is intentionally
NOT used here: empirical testing showed that pysubs2 1.8.1 unconditionally
renumbers indices from 1, normalises period-separator timecodes to comma, pads
2-digit milliseconds to 3 digits, and always outputs LF endings — all of which
break byte identity.  See RESEARCH.md Pitfalls 1–3.

Byte-identity strategy (FMT-01 / D-08):
  The codec preserves the *raw* structural pieces of the source file rather than
  reconstructing them from normalised fields.  The original bytes are exactly::

      leading + block[0] + separator[0] + ... + block[n-1] + trailer

  Each ``block[i]`` is stored verbatim (no ``strip()``); each ``separator[i]`` is
  the exact run of bytes joining one block to the next; ``leading``/``trailer``
  capture any bytes before the first / after the last block (a single terminating
  newline, an extra blank line, etc.).  Cue text is NOT re-joined from
  ``splitlines()`` — the block's raw text is kept so mixed LF-in-CRLF text and
  trailing whitespace survive verbatim (D-09).

  Malformed blocks (non-integer index, missing/invalid timecode line, trailing
  garbage on the timecode line) are flagged with a ``UserWarning`` and kept as
  opaque pass-through blocks (``SubLine.raw`` set) so write-back re-emits them
  unchanged — reconciling D-10 ("preserve-and-flag") with FMT-01 ("byte-identical").

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
# separator; any number of millisecond digits preserved verbatim).  Anchored
# with ``$`` (via fullmatch) so trailing garbage on the timecode line is treated
# as malformed and the whole block is preserved verbatim instead of silently
# dropping the extra data (WR-03).  Applied only to a single already-split line —
# safe against ReDoS.
_TC_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,.]\d+)"  # start timecode
    r"\s*-->\s*"                     # separator (allow surrounding spaces)
    r"(\d{2}:\d{2}:\d{2}[,.]\d+)"  # end timecode
)

# An index line must be an integer (one or more decimal digits, no sign).
_INDEX_RE = re.compile(r"^\d+$")

# A blank-line separator: one line ending immediately followed by one or more
# *blank* lines (runs of optional horizontal whitespace + line ending).  The
# whole matched run is captured (note the outer capturing group — required so
# re.split() keeps the separator verbatim) as the inter-cue separator so any
# extra blank lines between cues are preserved (CR-01 #2).
_SEP_RE = re.compile(r"((?:\r?\n)(?:[ \t]*\r?\n)+)")


def read_srt(path: str | Path) -> SubDoc:
    """Parse an SRT file into a :class:`SubDoc`, preserving all source bytes.

    Encoding is auto-detected (BOM-first → UTF-8 → charset-normalizer).  The
    file is split into cue blocks on blank-line boundaries, capturing the exact
    inter-cue separators plus any leading / trailing bytes so that
    :func:`write_srt` reconstructs the original bytes exactly (FMT-01 / D-08).

    Malformed cue blocks (non-integer index, missing/invalid timecode line, or
    trailing garbage on the timecode line) are flagged with a ``UserWarning`` and
    kept as opaque pass-through blocks (``SubLine.raw`` set) so write-back is still
    byte-identical (D-10).

    Args:
        path: Path to the ``.srt`` file (str or :class:`pathlib.Path`).

    Returns:
        A :class:`SubDoc` containing the parsed cues and file-level metadata.
    """
    raw_bytes = Path(path).read_bytes()
    encoding = detect_encoding(raw_bytes)
    # WR-06: detect_encoding's CJK guard may return "utf-8" for bytes that are
    # NOT valid UTF-8 (a mis-detected CP1258 file), which would crash a strict
    # decode.  Decode with errors="replace" so a recoverable mis-detection
    # degrades to replacement characters instead of a hard UnicodeDecodeError.
    # (Byte-identity is already forfeit for such files; the goal here is "do not
    # crash the read of exactly the files this guard claims to handle.")
    text = raw_bytes.decode(encoding, errors="replace")

    # Detect line-ending style from the decoded text (informational only —
    # write-back relies on the raw captured bytes, not on rejoining).
    le: str = "\r\n" if "\r\n" in text else "\n"

    # Capture any leading blank-line bytes before the first non-blank content so
    # a file that legitimately begins with blank lines round-trips (WR-02).
    leading = ""
    lead_match = re.match(r"^(?:[ \t]*\r?\n)+", text)
    if lead_match:
        # Only treat it as leading whitespace if there *is* a cue after it.
        rest = text[lead_match.end():]
        if rest.strip():
            leading = lead_match.group(0)
            text = rest

    # Split into cue blocks on blank-line boundaries, capturing each separator
    # verbatim.  Using a capturing group in re.split interleaves the separators
    # with the block text: [block0, sep0, block1, sep1, ..., blockN].
    tokens = _SEP_RE.split(text)

    block_texts: list[str] = tokens[0::2]
    separators: list[str] = tokens[1::2]

    # The final block may carry a trailing separator (a terminating newline or a
    # trailing blank line).  Strip it off the last block into ``trailer`` so the
    # block text itself contains no trailing structural whitespace.
    trailer = ""
    if block_texts:
        last = block_texts[-1]
        trail_match = re.search(r"(?:[ \t]*\r?\n)+$", last)
        if trail_match:
            trailer = trail_match.group(0)
            block_texts[-1] = last[: trail_match.start()]

    # Drop any wholly-empty trailing block produced by a separator that landed at
    # end-of-text, keeping the corresponding separator out of the cue list.
    while block_texts and block_texts[-1] == "":
        block_texts.pop()
        if separators:
            # The dropped empty block was preceded by a separator that is really
            # part of the trailer — fold it in (rare; defensive).
            trailer = separators.pop() + trailer

    # Re-align separators: there must be exactly len(block_texts) - 1 of them.
    separators = separators[: max(len(block_texts) - 1, 0)]

    lines: list[SubLine] = []
    for block in block_texts:
        if block == "":
            continue
        sub = _parse_block(block)
        lines.append(sub)

    return SubDoc(
        lines=lines,
        encoding=encoding,
        line_ending=le,
        separators=separators,
        leading=leading,
        trailer=trailer,
    )


def _parse_block(block: str) -> SubLine:
    """Parse a single verbatim cue block into a :class:`SubLine`.

    The raw block text is always retained on the returned ``SubLine``:
      * For a well-formed cue, ``raw`` is left ``None`` and the structured fields
        (index, start_tc, end_tc, text) drive write-back.
      * For a malformed block (bad index, bad/garbled timecode line, too few
        lines), ``raw`` is set to the verbatim block and a ``UserWarning`` is
        emitted; write-back re-emits ``raw`` unchanged (D-10 + FMT-01).
    """
    # Split on the block's own line endings WITHOUT discarding content; we only
    # need the index + timecode lines to validate.  splitlines() is used purely
    # for validation here — the verbatim block text is what gets written back.
    block_lines = block.splitlines()

    if len(block_lines) < 2:
        warnings.warn(
            f"read_srt: malformed SRT block (too few lines) — preserving verbatim:\n{block!r}",
            UserWarning,
            stacklevel=3,
        )
        return SubLine(index="", start_tc="", end_tc="", text=block, raw=block)

    index = block_lines[0]
    tc_line = block_lines[1]
    tc_match = _TC_RE.fullmatch(tc_line.strip())

    if tc_match is None or not _INDEX_RE.match(index.strip()):
        warnings.warn(
            f"read_srt: malformed SRT block (invalid index {index!r} or timecode "
            f"{tc_line!r}) — preserving verbatim:\n{block!r}",
            UserWarning,
            stacklevel=3,
        )
        return SubLine(index="", start_tc="", end_tc="", text=block, raw=block)

    # Well-formed cue: recover the verbatim text body by stripping exactly the
    # index line + its line ending + the timecode line + its line ending off the
    # front of the raw block.  This preserves the text bytes verbatim (mixed
    # LF/CRLF, leading whitespace, inline tags) — no splitlines()+join (CR-01 #3).
    le = "\r\n" if "\r\n" in block else "\n"
    prefix = index + le + tc_line + le
    if block.startswith(prefix):
        text_body = block[len(prefix):]
        return SubLine(
            index=index.strip(),
            start_tc=tc_match.group(1),
            end_tc=tc_match.group(2),
            text=text_body,
        )

    # Line endings inside the block are mixed in a way that the simple prefix
    # reconstruction cannot represent losslessly — keep the whole block verbatim
    # so byte-identity is never sacrificed.
    return SubLine(
        index=index.strip(),
        start_tc=tc_match.group(1),
        end_tc=tc_match.group(2),
        text=block,
        raw=block,
    )


def write_srt(doc: SubDoc, path: str | Path) -> None:
    """Serialise a :class:`SubDoc` back to an SRT file, byte-identically.

    The output is reconstructed from the raw structural pieces captured by
    :func:`read_srt` (``leading`` + blocks interleaved with ``separators`` +
    ``trailer``), then encoded with ``doc.encoding`` (preserving BOM and UTF-16
    endianness).  Blocks with ``raw`` set are re-emitted verbatim (D-10);
    well-formed blocks are reconstructed from their fields using the block's
    detected line ending.

    Args:
        doc:  The subtitle document to serialise.
        path: Destination path for the ``.srt`` file (str or :class:`pathlib.Path`).
    """
    block_texts = [_render_block(sl, doc.line_ending) for sl in doc.lines]

    out_parts: list[str] = [doc.leading]
    for i, block in enumerate(block_texts):
        out_parts.append(block)
        if i < len(block_texts) - 1:
            # Use the captured separator; fall back to a blank-line separator
            # built from the document's line ending if separators are missing
            # (e.g. a SubDoc constructed by hand rather than via read_srt).
            if i < len(doc.separators):
                out_parts.append(doc.separators[i])
            else:
                out_parts.append(doc.line_ending + doc.line_ending)
    out_parts.append(doc.trailer)

    result = "".join(out_parts)
    Path(path).write_bytes(result.encode(doc.encoding))


def _render_block(sl: SubLine, line_ending: str) -> str:
    """Render a single :class:`SubLine` back to its verbatim block text.

    ``raw`` (opaque pass-through) takes precedence — it is re-emitted verbatim.
    Otherwise the index + timecode header lines are joined with the document's
    line ending (``line_ending``), and the verbatim ``text`` body is appended
    unchanged (its own internal line endings are preserved exactly, D-09).
    """
    if sl.raw is not None:
        return sl.raw
    le = line_ending
    return f"{sl.index}{le}{sl.start_tc} --> {sl.end_tc}{le}{sl.text}"
