"""Thin custom VTT reader/writer — byte-identical round-trip (FMT-04, D-08/D-91).

Byte-identity strategy (FMT-04 / D-08):
  The VTT envelope is a block list.  WEBVTT header + opaque blocks
  (NOTE/STYLE/REGION/malformed) are VttOpaqueBlock entries.  Translatable
  cues are VttCueBlock entries (verbatim timing_line + optional verbatim
  identifier + verbatim trailing_sep).  Only the cue payload text changes on
  translate.

  Original bytes are reconstructed as::

      VttOpaqueBlock[0].raw + VttOpaqueBlock[0].trailing_sep
      + VttCueBlock[1].identifier_line? + le + timing_line + le + payload + trailing_sep
      + ...

  Cue payload is sliced verbatim from the raw block text (no splitlines+join)
  so mixed or trailing line endings inside multi-line payloads are preserved
  exactly (D-09).

  Malformed cue blocks (no ``-->`` line found) → UserWarning + VttOpaqueBlock
  pass-through (D-10).

  pysubs2 is NOT used on the write path (D-91 supersedes D-02).

Design decisions honoured:
  D-91  Hand-rolled raw-preservation codec.  No pysubs2 on the write path.
  D-92  SubLine/SubDoc as format-agnostic pipeline contract; VttDoc is the envelope.
  D-100 WEBVTT header, NOTE/STYLE/REGION blocks, cue identifiers, and cue settings
        strings are preserved verbatim.  Only the cue payload text is translatable.
  D-101 Hourless MM:SS.mmm timecodes are stored verbatim in SubLine.start_tc /
        SubLine.end_tc — no normalisation to HH:MM:SS.mmm form.
  D-10  Malformed cue blocks → UserWarning + verbatim VttOpaqueBlock.

ReDoS mitigations:
  _VTT_TIMING_RE uses the fixed string "-->" with no quantifiers.
  _SEP_RE (borrowed from srt.py) is applied per-file, not per-line, but the
  pattern has no nested quantifiers and has been in production since Phase 1.
  (T-09-04-A, T-09-04-B, ASVS L1 V5)
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path

from .encoding import detect_encoding
from .model import SubDoc, SubLine

# ---------------------------------------------------------------------------
# Blank-line separator: reused from srt.py.  Captures inter-block blank-line
# runs verbatim.  The leading (?:\r?\n) consumes the line ending at the end of
# the preceding content line, and the group (?:[ \t]*\r?\n)+ matches one or
# more subsequent blank lines (each optionally with horizontal whitespace).
# ---------------------------------------------------------------------------
_SEP_RE = re.compile(r"((?:\r?\n)(?:[ \t]*\r?\n)+)")

# Simple fixed-string search for the VTT cue timing separator (RESEARCH §4.2).
# Applied only to single split lines; no nested quantifiers — zero ReDoS exposure.
_VTT_TIMING_RE = re.compile(r"-->")

# TC extraction from a timing line: captures start and end timecodes verbatim.
# Matches both HH:MM:SS.mmm (with hours) and MM:SS.mmm (hourless) forms.
# The end timecode is everything after " --> " up to the first space or end-of-string.
_VTT_TC_SPLIT_RE = re.compile(
    r"^(\S+)"          # start timecode (no spaces)
    r"\s*-->\s*"       # arrow separator (allow surrounding spaces)
    r"(\S+)"           # end timecode (no spaces)
)


# ---------------------------------------------------------------------------
# Envelope dataclasses (RESEARCH §4.1 / PATTERNS.md §"vtt.py")
# ---------------------------------------------------------------------------

@dataclass
class VttOpaqueBlock:
    """A verbatim block of the VTT file that is never translated.

    Covers: WEBVTT header block, NOTE/STYLE/REGION blocks, and malformed
    blocks that contain no recognisable timing line.
    """
    raw: str
    trailing_sep: str   # blank line(s) that follow this block in the source file


@dataclass
class VttCueBlock:
    """A VTT cue block whose payload text is translatable.

    ``identifier_line`` is the optional cue identifier (the line before the
    timing line that does NOT contain ``-->``).  ``timing_line`` is the
    verbatim ``HH:MM:SS.mmm --> HH:MM:SS.mmm [cue-settings]`` line, stored
    exactly as found in the source so cue settings (position:, line:, align:,
    size:, region:) round-trip byte-identically (D-100).
    """
    identifier_line: str | None  # verbatim identifier or None
    timing_line: str             # verbatim "HH:MM:SS.mmm --> HH:MM:SS.mmm [settings]"
    line_ending: str             # "\r\n" or "\n" (document-level detected style)
    sub_index: int               # index into SubDoc.lines
    trailing_sep: str            # blank line(s) after this cue block


@dataclass
class VttDoc:
    """VTT document envelope for byte-identical round-trip."""
    blocks: list    # list[VttOpaqueBlock | VttCueBlock]
    encoding: str
    line_ending: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_vtt(path: str | Path) -> SubDoc:
    """Parse a VTT file into a :class:`SubDoc`, preserving all source bytes.

    Encoding is auto-detected (BOM-first → UTF-8 → charset-normalizer).  The
    file is split into blocks on blank-line boundaries, capturing the exact
    inter-block separators.  The WEBVTT header block and any NOTE/STYLE/REGION
    blocks are stored as :class:`VttOpaqueBlock` entries in the envelope.
    Translatable cue blocks become :class:`VttCueBlock` entries plus
    :class:`SubLine` entries in the returned :class:`SubDoc`.

    Hourless MM:SS.mmm timecodes are stored verbatim in ``SubLine.start_tc``/
    ``SubLine.end_tc`` without normalisation (D-101).

    Malformed blocks (no ``-->`` line found) are flagged with a
    ``UserWarning`` and preserved verbatim as :class:`VttOpaqueBlock` (D-10).

    Args:
        path: Path to the ``.vtt`` file (str or :class:`pathlib.Path`).

    Returns:
        A :class:`SubDoc` with ``envelope=VttDoc`` for the write-back codec.
    """
    raw_bytes = Path(path).read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")

    # Detect line-ending style from the decoded text.
    le: str = "\r\n" if "\r\n" in text else "\n"

    # Split into blocks on blank-line boundaries, capturing each separator
    # verbatim (same strategy as srt.py).
    tokens = _SEP_RE.split(text)

    block_texts: list[str] = tokens[0::2]
    separators: list[str] = tokens[1::2]

    # Pad separators so every block has a corresponding separator entry
    # (the last block will get "" if it has no trailing blank-line separator).
    while len(separators) < len(block_texts):
        separators.append("")

    blocks: list[VttOpaqueBlock | VttCueBlock] = []
    sub_lines: list[SubLine] = []

    for idx, (block_text, trailing_sep) in enumerate(zip(block_texts, separators)):
        if idx == 0:
            # The first block is always the WEBVTT header block (opaque).
            blocks.append(VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep))
        else:
            block = _parse_vtt_block(block_text, trailing_sep, le, sub_lines)
            blocks.append(block)

    vtt_doc = VttDoc(blocks=blocks, encoding=encoding, line_ending=le)
    return SubDoc(
        lines=sub_lines,
        encoding=encoding,
        line_ending=le,
        separators=[],    # VTT uses per-block trailing_sep, not a flat separator list
        leading="",
        trailer="",
        envelope=vtt_doc,
    )


def write_vtt(doc: SubDoc, path: str | Path) -> None:
    """Serialise a :class:`SubDoc` back to a VTT file, byte-identically.

    The output is reconstructed from the VttDoc envelope (captured by
    :func:`read_vtt`) by iterating blocks:

    - :class:`VttOpaqueBlock` → ``raw + trailing_sep``
    - :class:`VttCueBlock` → ``identifier_line + le`` (if identifier present)
      + ``timing_line + le`` + ``SubLine.text`` + ``trailing_sep``

    Only the SubLine.text (cue payload) may have changed.  All structural
    bytes are preserved verbatim.  pysubs2 is NOT used (D-91).

    Args:
        doc:  The subtitle document (must have ``doc.envelope`` set to a
              :class:`VttDoc`).
        path: Destination path for the ``.vtt`` file.
    """
    vtt_doc: VttDoc = doc.envelope
    le = vtt_doc.line_ending
    parts: list[str] = []

    for block in vtt_doc.blocks:
        if isinstance(block, VttOpaqueBlock):
            parts.append(block.raw + block.trailing_sep)
        else:
            # VttCueBlock — reconstruct from structural pieces + translated payload
            sl = doc.lines[block.sub_index]
            payload = sl.raw if sl.raw is not None else sl.text
            chunk_parts: list[str] = []
            if block.identifier_line is not None:
                chunk_parts.append(block.identifier_line + le)
            chunk_parts.append(block.timing_line + le)
            chunk_parts.append(payload)
            chunk_parts.append(block.trailing_sep)
            parts.append("".join(chunk_parts))

    result = "".join(parts)
    Path(path).write_bytes(result.encode(vtt_doc.encoding))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_vtt_block(
    block_text: str,
    trailing_sep: str,
    le: str,
    sub_lines: list[SubLine],
) -> VttOpaqueBlock | VttCueBlock:
    """Parse a single VTT block (not the WEBVTT header) into an opaque or cue block.

    Algorithm (RESEARCH §4.2 / PATTERNS.md §"_parse_vtt_block"):

    1. Empty block → VttOpaqueBlock.
    2. First line starts with NOTE, STYLE, or REGION → VttOpaqueBlock.
    3. First line contains "–>" → cue with no identifier.
    4. Second line contains "–>" → first line is the cue identifier.
    5. Otherwise → malformed; UserWarning + VttOpaqueBlock (D-10).

    The cue payload is extracted verbatim by slicing the block_text at the
    character position immediately after the timing line's line ending, so
    multi-line payloads and trailing newlines within the block are preserved
    exactly (D-09).
    """
    if not block_text:
        return VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep)

    # Use splitlines() ONLY for keyword/timing-line detection (not for payload extraction).
    lines = block_text.splitlines()

    if not lines:
        return VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep)

    # NOTE / STYLE / REGION blocks → opaque (D-100).
    if lines[0].startswith(("NOTE", "STYLE", "REGION")):
        return VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep)

    # Determine timing line position.
    identifier_line: str | None = None
    timing_line: str | None = None

    if _VTT_TIMING_RE.search(lines[0]):
        # No identifier — timing line is the first line.
        timing_line = lines[0]
    elif len(lines) >= 2 and _VTT_TIMING_RE.search(lines[1]):
        # Identifier present on first line, timing line is second.
        identifier_line = lines[0]
        timing_line = lines[1]
    else:
        # Malformed block — preserve verbatim (D-10).
        warnings.warn(
            f"read_vtt: malformed VTT block (no timing line found) — preserving "
            f"verbatim:\n{block_text!r}",
            UserWarning,
            stacklevel=4,
        )
        return VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep)

    # Extract start_tc and end_tc from the timing line verbatim (D-101).
    tc_match = _VTT_TC_SPLIT_RE.match(timing_line.strip())
    if tc_match is None:
        # Timing line exists but is malformed (no valid timecode pair).
        warnings.warn(
            f"read_vtt: malformed VTT timing line (cannot parse timecodes) — "
            f"preserving verbatim:\n{timing_line!r}",
            UserWarning,
            stacklevel=4,
        )
        return VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep)

    start_tc = tc_match.group(1)
    end_tc = tc_match.group(2)

    # Extract the payload verbatim by slicing block_text at the position
    # immediately after the timing line's trailing line ending.  This preserves
    # internal line endings and trailing whitespace in multi-line payloads (D-09).
    payload = _extract_payload(block_text, identifier_line, timing_line)

    sub_idx = len(sub_lines)
    sub_lines.append(SubLine(
        index="",       # VTT cue identifiers live in VttCueBlock, not SubLine (RESEARCH §4.2)
        start_tc=start_tc,
        end_tc=end_tc,
        text=payload,
    ))

    return VttCueBlock(
        identifier_line=identifier_line,
        timing_line=timing_line,
        line_ending=le,
        sub_index=sub_idx,
        trailing_sep=trailing_sep,
    )


def _extract_payload(
    block_text: str,
    identifier_line: str | None,
    timing_line: str,
) -> str:
    """Extract the cue payload verbatim from a VTT cue block text.

    Slices block_text at the character position immediately after the timing
    line and its trailing line ending.  Does NOT use splitlines()+join so
    multi-line payloads and trailing newlines are preserved byte-identically.

    Args:
        block_text:      The full block text (excluding inter-block separators).
        identifier_line: The cue identifier line, or None.
        timing_line:     The verbatim timing line (contains "-->").

    Returns:
        The payload string (may be empty, single-line, or multi-line).
    """
    pos = 0

    # Skip past the identifier line and its line ending, if present.
    if identifier_line is not None:
        id_pos = block_text.find(identifier_line, pos)
        if id_pos >= 0:
            pos = id_pos + len(identifier_line)
            # Skip the line ending after the identifier.
            if block_text[pos:pos + 2] == "\r\n":
                pos += 2
            elif pos < len(block_text) and block_text[pos] in ("\r", "\n"):
                pos += 1

    # Skip past the timing line and its line ending.
    tc_pos = block_text.find(timing_line, pos)
    if tc_pos >= 0:
        pos = tc_pos + len(timing_line)
        # Skip the line ending after the timing line.
        if block_text[pos:pos + 2] == "\r\n":
            pos += 2
        elif pos < len(block_text) and block_text[pos] in ("\r", "\n"):
            pos += 1

    return block_text[pos:]
