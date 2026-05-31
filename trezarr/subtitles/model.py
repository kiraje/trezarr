"""Format-agnostic internal subtitle line model (SubLine and SubDoc).

These dataclasses are the shared schema consumed by the translation pipeline.
They carry no LLM or format-specific concerns — only the minimal structure needed
to represent a subtitle document for round-trip codec use.

Design decisions:
- D-08: All index/timecode fields are stored verbatim as strings — no normalization.
- D-09: SubLine.text includes all inline tags intact; it is the ONLY LLM-mutable field.
- D-10: Malformed cues are handled at the codec level; the model itself is always valid.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SubLine:
    """A single subtitle cue — one timed block of text.

    All fields except ``text`` are immutable by convention: the codec writes them
    back unchanged and the translation pipeline must never touch them.

    Attributes:
        index:    Verbatim index string from the source file (e.g. "5" or "10").
                  Never normalized to an integer.
        start_tc: Verbatim start timecode (e.g. "00:00:01,000" or "00:00:01.000").
                  Comma vs. period separator and digit count are preserved exactly.
        end_tc:   Verbatim end timecode (same preservation guarantee as start_tc).
        text:     Cue text including all inline formatting tags (the LLM-mutable field).
                  Multi-line cue text is stored with the original line ending separator.
        raw:      Opaque pass-through of the block's *original* source text (D-10).
                  When set (non-None) the codec re-emits this verbatim on write,
                  ignoring the parsed fields entirely.  Used for malformed blocks
                  (e.g. non-integer index, trailing timecode garbage) and for the
                  raw timecode line so byte-identity is preserved even when the
                  structured fields cannot fully represent the source.  A normal,
                  well-formed cue leaves ``raw`` as ``None``.
    """

    index: str
    start_tc: str
    end_tc: str
    text: str
    raw: str | None = None


@dataclass
class SubDoc:
    """A subtitle document: an ordered sequence of cues plus file-level metadata.

    Byte-identity (FMT-01 / D-08) is achieved by preserving the *raw* structural
    pieces of the source file rather than reconstructing them from normalised
    fields.  The original file is exactly::

        leading + block[0] + separator[0] + block[1] + ... + block[n-1] + trailer

    where each ``block[i]`` is the verbatim source text of cue ``i`` (no leading
    or trailing whitespace stripped), ``separator[i]`` is the verbatim run of
    bytes that joined cue ``i`` to cue ``i+1`` (typically one blank line), and
    ``leading``/``trailer`` capture any bytes before the first cue / after the
    last cue (a single terminating newline, an extra blank line, etc.).

    Attributes:
        lines:        Ordered list of parsed subtitle cues.  ``lines[i]`` corresponds
                      to ``separators[i]`` (the bytes that follow it, for i < len-1).
        encoding:     Detected encoding of the source file (e.g. "utf-8", "utf-8-sig",
                      "utf-16-le").  Used verbatim when encoding the output bytes,
                      so BOM and endianness round-trip exactly.
        line_ending:  Line ending style detected in the source file ("\n" or "\r\n").
                      Informational only — write-back relies on the raw block text and
                      separators, not on rejoining with this value.
        separators:   Verbatim inter-cue separator strings.  ``separators[i]`` is the
                      run of bytes between ``lines[i]`` and ``lines[i+1]``.  Length is
                      ``max(len(lines) - 1, 0)``.
        leading:      Verbatim bytes (as text) before the first cue block (usually "").
        trailer:      Verbatim bytes (as text) after the last cue block — captures a
                      single terminating newline, a trailing blank line, or "".
    """

    lines: list[SubLine]
    encoding: str
    line_ending: str
    separators: list[str]
    leading: str = ""
    trailer: str = ""
