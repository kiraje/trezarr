r"""Thin custom ASS/SSA reader/writer — byte-identical round-trip (FMT-02, D-08/D-91).

Byte-identity strategy (FMT-02 / D-08):
  The codec preserves the *raw* structural pieces of the source file. For ASS:

      [ScriptInfo_raw] + [V4+Styles_raw] + AssDialogueSlot[0] + … + trailer

  Non-Events sections (Script Info, V4+ Styles, Fonts, Graphics) and Comment: events
  are AssOpaqueSegment instances emitted verbatim. Dialogue: events are AssDialogueSlot
  instances: verbatim prefix (everything up to and including the 9th comma) + translated
  SubLine.text + verbatim line ending.

  Malformed lines → UserWarning + opaque pass-through (D-10).
  pysubs2 is NOT used on the write path (D-91 supersedes D-02).

Design decisions honoured:
  D-91  Hand-rolled raw-preservation parser/serialiser. No pysubs2 on write path.
  D-92  SubLine/SubDoc as format-agnostic pipeline contract; AssDoc is the envelope.
  D-97  Only Dialogue: Text fields become translatable SubLines. Comment: events,
        [Script Info], [V4+ Styles], Format: lines, style names, actor, effect,
        margins — all preserved verbatim in AssOpaqueSegment.
  D-98  Drawing-run cues ({\p1}…{\p0}) detected; SubLine.raw = SubLine.text = original.
  D-99  Karaoke cues (\k/\kf/\ko/\K/\kt) detected; SubLine.raw = SubLine.text = original.
  D-10  Malformed Dialogue: lines → UserWarning + preserved as opaque SubLine.

ReDoS mitigations:
  KARAOKE_RE and DRAWING_RE use fixed-prefix/fixed-width patterns applied per-line
  to short subtitle text — no nested quantifiers, no catastrophic backtracking
  (T-09-03-A, T-09-03-B, ASVS L1 V5).
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path

from .encoding import detect_encoding
from .model import SubDoc, SubLine

# ---------------------------------------------------------------------------
# Karaoke detection (D-99 / RESEARCH §5.2)
# Matches: {\k50}, {\kf50}, {\ko50}, {\K50}, {\kt50} (all karaoke timing tags)
# re.IGNORECASE makes \K match the same as the [foi]? arm for lowercase/uppercase.
# Pattern breakdown: fixed braces, backslash, literal 'k', optional one-char class,
# then digits — no nested quantifiers.
# ---------------------------------------------------------------------------
KARAOKE_RE = re.compile(r'\{\\k[foi]?\d+\}|\{\\K\d+\}|\{\\kt\d+\}', re.IGNORECASE)

# ---------------------------------------------------------------------------
# Drawing-mode detection (D-98 / RESEARCH §5.3)
# Matches: {\p1}, {\p2}, {\p4}, etc. — any {\pN} where N is 1 or more digits >= 1.
# Fixed-prefix with [1-9]\d* (non-nested). Applied per-line to short strings.
# ---------------------------------------------------------------------------
DRAWING_RE = re.compile(r'\{\\p[1-9]\d*\}')

# ---------------------------------------------------------------------------
# Section-header detection: a line starting with '[' (at position 0 in the
# split line) indicates a new ASS section.
# ---------------------------------------------------------------------------
_SECTION_HEADER_RE = re.compile(r'^\[', re.MULTILINE)


# ---------------------------------------------------------------------------
# Envelope dataclasses (RESEARCH §3.2 / PATTERNS.md §"ass.py")
# ---------------------------------------------------------------------------

@dataclass
class AssOpaqueSegment:
    """A verbatim chunk of the ASS file that is never translated."""
    raw: str


@dataclass
class AssDialogueSlot:
    """A Dialogue: event whose Text field is translatable."""
    prefix: str       # "Dialogue: 0,0:01:23.45,0:01:25.67,Default,,0,0,0,,"
                      # (everything INCLUDING the trailing comma before Text)
    line_ending: str  # "\r\n" or "\n"
    sub_index: int    # index into SubDoc.lines


@dataclass
class AssDoc:
    """ASS/SSA document envelope for byte-identical round-trip."""
    segments: list    # list[AssOpaqueSegment | AssDialogueSlot]
    encoding: str
    line_ending: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_ass(path: str | Path) -> SubDoc:
    """Parse an ASS/SSA file into a :class:`SubDoc`, preserving all source bytes.

    Encoding is auto-detected (BOM-first → UTF-8 → charset-normalizer).  The
    file is decomposed into verbatim segments (AssOpaqueSegment for non-translatable
    content and AssDialogueSlot for translatable Dialogue: Text fields) so that
    :func:`write_ass` reconstructs the original bytes exactly (FMT-02 / D-08).

    Karaoke and drawing-run Dialogue cues are detected and marked as opaque
    pass-through by setting SubLine.raw = SubLine.text = original Text field
    (D-98, D-99).  Malformed Dialogue: lines are flagged with a UserWarning and
    kept as opaque SubLines (D-10).

    Args:
        path: Path to the ``.ass`` or ``.ssa`` file (str or :class:`pathlib.Path`).

    Returns:
        A :class:`SubDoc` with envelope=AssDoc for the write-back codec.
    """
    raw_bytes = Path(path).read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")

    # Detect line-ending style from the decoded text.
    le: str = "\r\n" if "\r\n" in text else "\n"

    segments: list[AssOpaqueSegment | AssDialogueSlot] = []
    sub_lines: list[SubLine] = []

    # ---------------------------------------------------------------------------
    # Split text into sections. Strategy: find the positions of all [SectionHeader]
    # lines (lines starting with '[' at column 0) using re.finditer on the full text.
    # Each match is the start of a new section; the previous section spans from its
    # start to this match's start. We accumulate spans, then process each section.
    # ---------------------------------------------------------------------------
    section_starts = [m.start() for m in _SECTION_HEADER_RE.finditer(text)]

    if not section_starts:
        # No section headers at all — treat entire file as opaque.
        segments.append(AssOpaqueSegment(raw=text))
        ass_doc = AssDoc(segments=segments, encoding=encoding, line_ending=le)
        return SubDoc(
            lines=sub_lines,
            encoding=encoding,
            line_ending=le,
            separators=[],
            leading="",
            trailer="",
            envelope=ass_doc,
        )

    # Anything before the first section header is "leading" content (e.g. BOM text
    # in UTF-8-sig mode would have been decoded away; raw comment lines, etc.)
    # Preserve it verbatim as an opaque segment.
    if section_starts[0] > 0:
        segments.append(AssOpaqueSegment(raw=text[: section_starts[0]]))

    # Build (start, end) spans for each section.
    section_spans = []
    for i, start in enumerate(section_starts):
        end = section_starts[i + 1] if i + 1 < len(section_starts) else len(text)
        section_spans.append((start, end))

    # Determine if the [Events] section is present and its index.
    events_idx: int | None = None
    for i, (start, end) in enumerate(section_spans):
        header_line = text[start:end].split(le)[0] if le in text[start:end] else text[start:end].split("\n")[0]
        if header_line.strip() == "[Events]":
            events_idx = i
            break

    # Process each section.
    for i, (start, end) in enumerate(section_spans):
        section_text = text[start:end]
        if i == events_idx:
            _parse_events_section(
                section_text, le, segments, sub_lines
            )
        else:
            segments.append(AssOpaqueSegment(raw=section_text))

    ass_doc = AssDoc(segments=segments, encoding=encoding, line_ending=le)
    return SubDoc(
        lines=sub_lines,
        encoding=encoding,
        line_ending=le,
        separators=[],
        leading="",
        trailer="",
        envelope=ass_doc,
    )


def write_ass(doc: SubDoc, path: str | Path) -> None:
    """Serialise a :class:`SubDoc` back to an ASS/SSA file, byte-identically.

    The output is reconstructed from the AssDoc envelope (captured by
    :func:`read_ass`) by iterating segments: AssOpaqueSegment → verbatim raw
    text; AssDialogueSlot → verbatim prefix + (SubLine.raw if set else SubLine.text)
    + line ending.  Only the Text field changes; all other bytes are preserved.

    pysubs2 is NOT used on the write path (D-91).

    Args:
        doc:  The subtitle document (must have doc.envelope set to an AssDoc).
        path: Destination path for the ``.ass`` or ``.ssa`` file.
    """
    ass_doc: AssDoc = doc.envelope
    parts: list[str] = []

    for seg in ass_doc.segments:
        if isinstance(seg, AssOpaqueSegment):
            parts.append(seg.raw)
        else:
            # AssDialogueSlot — emit prefix + translated (or pass-through) text + line ending
            sl = doc.lines[seg.sub_index]
            text_out = sl.raw if sl.raw is not None else sl.text
            parts.append(seg.prefix + text_out + seg.line_ending)

    result = "".join(parts)
    # CR-01 (D-19 / FMT-05): encode with doc.encoding, NOT ass_doc.encoding.
    # ass_doc.encoding is the source encoding captured at read time; on the vi
    # sidecar path write_vi_sidecar sets doc.encoding='utf-8' to force UTF-8
    # output. (On a plain round-trip read_ass sets doc.encoding == ass_doc.encoding,
    # so byte-identity is unchanged.)
    Path(path).write_bytes(result.encode(doc.encoding))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_events_section(
    section_text: str,
    le: str,
    segments: list,
    sub_lines: list[SubLine],
) -> None:
    """Parse the [Events] section, building segments and SubLines.

    The section_text includes the [Events] header line and all lines within
    the section (up to but not including the next section header, if any).

    Strategy:
    - Split on the file's detected line ending to get individual lines, but
      preserve exact bytes for reconstruction by tracking character positions.
    - The [Events] header line and Format: line go into AssOpaqueSegment.
    - Comment: lines go into AssOpaqueSegment.
    - Dialogue: lines are parsed into AssDialogueSlot + SubLine.
    - Everything else (blank lines, unknown lines) goes into AssOpaqueSegment.

    The Format: line is parsed to build a column-index map so the codec is
    format-agnostic (handles both ASS Layer and SSA Marked first fields).
    Per RESEARCH §Open Question 1 and §1.2, Text is always the LAST field,
    so text_comma_idx = num_fields - 1 (number of commas to split on).
    """
    # Split the section into lines while preserving line endings verbatim.
    # We use splitlines(keepends=True) to get each line with its own line ending.
    raw_lines_with_endings = section_text.splitlines(keepends=True)

    # Default: 9 commas (standard 10-field ASS/SSA layout)
    text_comma_idx = 9

    for raw_line in raw_lines_with_endings:
        # Determine the line ending for this raw line (for AssDialogueSlot).
        if raw_line.endswith("\r\n"):
            line_le = "\r\n"
            line_content = raw_line[:-2]
        elif raw_line.endswith("\n"):
            line_le = "\n"
            line_content = raw_line[:-1]
        elif raw_line.endswith("\r"):
            line_le = "\r"
            line_content = raw_line[:-1]
        else:
            # No trailing line ending (last line of file or section without trailing newline)
            line_le = ""
            line_content = raw_line

        # Parse the Format: line to determine text column index.
        if line_content.startswith("Format:"):
            # e.g. "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
            try:
                fmt_body = line_content[len("Format:"):].strip()
                fmt_fields = [f.strip() for f in fmt_body.split(",")]
                # Text is always the last field; the number of commas to split on
                # is len(fields) - 1.
                if len(fmt_fields) >= 2:
                    text_comma_idx = len(fmt_fields) - 1
            except Exception:
                pass  # Keep default of 9 on any parse error
            segments.append(AssOpaqueSegment(raw=raw_line))

        elif line_content.startswith("Comment:"):
            # Comment: events are preserved verbatim — never translatable (D-97).
            segments.append(AssOpaqueSegment(raw=raw_line))

        elif line_content.startswith("Dialogue:"):
            _parse_dialogue_line(
                raw_line, line_content, line_le, text_comma_idx,
                segments, sub_lines
            )

        else:
            # [Events] header line, blank lines, or any other unrecognized content.
            segments.append(AssOpaqueSegment(raw=raw_line))


def _parse_dialogue_line(
    raw_line: str,
    line_content: str,
    line_le: str,
    text_comma_idx: int,
    segments: list,
    sub_lines: list[SubLine],
) -> None:
    """Parse a single Dialogue: line into an AssDialogueSlot + SubLine.

    Uses split(",", text_comma_idx) to correctly handle commas inside the
    Text field (RESEARCH §1.2 — the 9-comma rule).

    For malformed lines (too few comma-separated fields), emits UserWarning
    and preserves the line verbatim as an opaque SubLine (D-10).

    For karaoke (KARAOKE_RE) and drawing-run (DRAWING_RE) cues, sets both
    SubLine.text AND SubLine.raw to the original Text field so the cue is
    never sent to the LLM and passes gate checks 2 and 3 (D-98, D-99).
    """
    # Split line_content (without line ending) on the first text_comma_idx commas.
    parts = line_content.split(",", text_comma_idx)

    if len(parts) < text_comma_idx + 1:
        # Malformed: not enough commas — preserve verbatim (D-10).
        warnings.warn(
            f"read_ass: malformed Dialogue: line (expected {text_comma_idx + 1} "
            f"comma-separated fields, got {len(parts)}) — preserving verbatim:\n"
            f"{line_content!r}",
            UserWarning,
            stacklevel=3,
        )
        # Add the malformed line as an opaque SubLine so it round-trips verbatim.
        # SubLine.raw carries the full raw line (without line ending); write_ass
        # would emit it via slot.prefix + text_out + slot.line_ending, but since
        # this is a degenerate case we still need an AssDialogueSlot so the
        # sub_index aligns. Use the content minus "Dialogue:" as prefix and the
        # rest as text — but since we can't split, just use empty prefix and
        # store everything in raw.
        sub_idx = len(sub_lines)
        sl = SubLine(
            index="",
            start_tc="",
            end_tc="",
            text=raw_line,
            raw=raw_line,
        )
        sub_lines.append(sl)
        # prefix="" means write_ass emits "" + raw_line + line_le
        # but wait — raw_line already contains the line ending in the raw pass-through.
        # Since sl.raw is set, write_ass emits sl.raw directly. However write_ass
        # appends line_le too. We must not double-count the line ending.
        # Solution: store prefix="" + use raw=line_content (no le), and line_ending=line_le.
        # But sl.raw is set to raw_line (includes le). Let's fix: store content only in raw.
        # Rewrite: sl.raw = line_content (the content without le); line_le is stored
        # in the slot. Then write_ass emits prefix + sl.raw + slot.le = "" + content + le
        # = raw_line. Perfect.
        sl.text = line_content
        sl.raw = line_content
        segments.append(AssDialogueSlot(
            prefix="",
            line_ending=line_le,
            sub_index=sub_idx,
        ))
        return

    # Well-formed: extract structured fields.
    # parts[0]            = "Dialogue: 0" (type prefix + first field value)
    # parts[1]            = start timecode
    # parts[2]            = end timecode
    # parts[3..idx-1]     = Style, Name, MarginL, MarginR, MarginV, Effect (verbatim)
    # parts[text_comma_idx] = Text (the full text, may contain commas)
    start_tc = parts[1].strip()
    end_tc = parts[2].strip()
    text = parts[text_comma_idx]  # verbatim, no strip()

    # Build prefix: everything from parts[0] through parts[text_comma_idx - 1],
    # rejoined with commas, plus the final comma before Text.
    prefix = ",".join(parts[:text_comma_idx]) + ","

    # Detect karaoke and drawing-run cues (D-98, D-99).
    if KARAOKE_RE.search(text) or DRAWING_RE.search(text):
        # Set BOTH text AND raw to the original Text field (RESEARCH A7).
        # Gate check 2 (non-empty) passes because text is non-empty.
        # Gate check 3 (_check_untranslated) skips because raw is not None.
        sl = SubLine(
            index="",
            start_tc=start_tc,
            end_tc=end_tc,
            text=text,
            raw=text,
        )
    else:
        sl = SubLine(
            index="",
            start_tc=start_tc,
            end_tc=end_tc,
            text=text,
        )

    sub_idx = len(sub_lines)
    sub_lines.append(sl)
    segments.append(AssDialogueSlot(
        prefix=prefix,
        line_ending=line_le,
        sub_index=sub_idx,
    ))
