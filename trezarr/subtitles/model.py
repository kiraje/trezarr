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
from typing import Literal


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
    """

    index: str
    start_tc: str
    end_tc: str
    text: str


@dataclass
class SubDoc:
    """A subtitle document: an ordered sequence of cues plus file-level metadata.

    The metadata (encoding, line_ending, trailing_newline) is required to reconstruct
    the original file bytes exactly during write-back (D-08).

    Attributes:
        lines:           Ordered list of parsed subtitle cues.
        encoding:        Detected encoding of the source file (e.g. "utf-8", "utf-8-sig").
                         Used verbatim when encoding the output bytes.
        line_ending:     Line ending style detected in the source file.  Only two values
                         are valid: ``"\n"`` (LF) or ``"\r\n"`` (CRLF).
        trailing_newline: True if the source file ended with a blank line (i.e. two
                          consecutive line endings after the last cue).  Preserved on
                          write-back to maintain byte identity.
    """

    lines: list[SubLine]
    encoding: str
    line_ending: Literal["\n", "\r\n"]
    trailing_newline: bool
