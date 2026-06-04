# Phase 9: Multi-Format — ASS/SSA + VTT - Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 11 new/modified files
**Analogs found:** 11 / 11

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trezarr/subtitles/ass.py` | codec (reader+writer) | file-I/O, transform | `trezarr/subtitles/srt.py` | exact |
| `trezarr/subtitles/vtt.py` | codec (reader+writer) | file-I/O, transform | `trezarr/subtitles/srt.py` | exact |
| `trezarr/subtitles/dispatch.py` | router / utility | request-response | `trezarr/subtitles/srt.py` (read_srt/write_srt entry points) | role-match |
| `trezarr/subtitles/model.py` | model | — | self (add `envelope` field) | exact |
| `trezarr/translate/sentinel.py` | utility | transform | self (extend `TAG_RE`) | exact |
| `trezarr/translate/_timecode.py` | utility | transform | self (extend `tc_to_ms`) | exact |
| `trezarr/translate/validate.py` | gate / service | request-response | self (extend `_check_untranslated`) | exact |
| `trezarr/translate/engine.py` | orchestrator | request-response | self (swap `read_srt` import) | exact |
| `trezarr/output/write.py` | service | file-I/O | self (generalize `derive_vi_sidecar_path`) | exact |
| `trezarr/discover/gap.py` | service | request-response | self (update log message) | exact |
| `tests/codec/test_ass_roundtrip.py` etc. | test | — | `tests/codec/test_srt_roundtrip.py` | exact |

---

## Pattern Assignments

---

### `trezarr/subtitles/ass.py` (codec, file-I/O + transform)

**Analog:** `trezarr/subtitles/srt.py` (entire file — the direct template)

**Module docstring pattern** (`srt.py` lines 1–30):
```python
"""Thin custom ASS/SSA reader/writer — byte-identical round-trip (FMT-02, D-08/D-91).

Byte-identity strategy (FMT-02 / D-08):
  The codec preserves the *raw* structural pieces of the source file. For ASS:

      [ScriptInfo_raw] + [V4+Styles_raw] + AssDialogueSlot[0] + … + trailer

  Non-Events sections (Script Info, V4+ Styles, Fonts, Graphics) and Comment: events
  are AssOpaqueSegment instances emitted verbatim. Dialogue: events are AssDialogueSlot
  instances: verbatim prefix (everything up to and including the 9th comma) + translated
  SubLine.text + verbatim line ending.

  Malformed lines → UserWarning + opaque pass-through (D-10).
  pysubs2 is NOT used on the write path (D-91 supersedes D-02).
"""
```

**Imports pattern** (`srt.py` lines 31–38):
```python
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from .encoding import detect_encoding
from .model import SubDoc, SubLine
```

**Envelope dataclasses** (new — no analog in srt.py; sourced from RESEARCH.md §3.2):
```python
@dataclass
class AssOpaqueSegment:
    """A verbatim chunk of the ASS file that is never translated."""
    raw: str

@dataclass
class AssDialogueSlot:
    """A Dialogue: event whose Text field is translatable."""
    prefix: str        # "Dialogue: 0,0:01:23.45,0:01:25.67,Default,,0,0,0,,"
                       # (everything INCLUDING the trailing comma before Text)
    line_ending: str   # "\r\n" or "\n"
    sub_index: int     # index into SubDoc.lines

@dataclass
class AssDoc:
    """ASS/SSA document envelope for byte-identical round-trip."""
    segments: list      # list[AssOpaqueSegment | AssDialogueSlot]
    encoding: str
    line_ending: str
```

**Line-ending detection pattern** (`srt.py` line 94):
```python
le: str = "\r\n" if "\r\n" in text else "\n"
```

**read_srt entry point pattern** (`srt.py` lines 63–152) — adapt to `read_ass(path)`:
```python
def read_ass(path: str | Path) -> SubDoc:
    raw_bytes = Path(path).read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors="replace")
    le: str = "\r\n" if "\r\n" in text else "\n"
    # ... build segments list + SubLine list simultaneously
    ass_doc = AssDoc(segments=segments, encoding=encoding, line_ending=le)
    sub_doc = SubDoc(
        lines=sub_lines,
        encoding=encoding,
        line_ending=le,
        separators=[],          # ASS has no inter-cue blank-line separators
        leading="",
        trailer="",
        envelope=ass_doc,       # D-92: format envelope stored on SubDoc
    )
    return sub_doc
```

**9-comma split rule** (RESEARCH §1.2 — the core ASS parsing rule):
```python
# After stripping "Dialogue: " prefix:
parts = line.split(",", 9)
# parts[0] = layer; parts[1] = start_tc; parts[2] = end_tc
# parts[3] = style; parts[4] = name; parts[5..7] = margins; parts[8] = effect
# parts[9] = Text (may contain commas — captured whole)
start_tc = parts[1].strip()
end_tc   = parts[2].strip()
text     = parts[9]    # verbatim, no strip()
prefix   = ",".join(parts[:9]) + ","   # everything up to and including 9th comma
```

**Karaoke + drawing detection** (RESEARCH §5.2 and §5.3):
```python
KARAOKE_RE = re.compile(r'\{\\k[foi]?\d+\}|\{\\K\d+\}|\{\\kt\d+\}', re.IGNORECASE)
DRAWING_RE  = re.compile(r'\{\\p[1-9]\d*\}')

def _is_karaoke(text: str) -> bool:
    return bool(KARAOKE_RE.search(text))

def _is_drawing_run(text: str) -> bool:
    return bool(DRAWING_RE.search(text))
```

**Opaque pass-through for karaoke/drawing** (`srt.py` `_parse_block` malformed branch, lines 171–177):
```python
# Analog: srt.py line 176 — set raw=block for malformed
# For karaoke/drawing: set BOTH text AND raw to the original Text field (RESEARCH A7)
return SubLine(index="", start_tc=start_tc, end_tc=end_tc, text=text, raw=text)
```

**Malformed block warning pattern** (`srt.py` lines 171–177):
```python
warnings.warn(
    f"read_ass: malformed Dialogue: line — preserving verbatim:\n{line!r}",
    UserWarning,
    stacklevel=3,
)
```

**write_srt pattern** (`srt.py` lines 218–248) — adapt to `write_ass(doc, path)`:
```python
def write_ass(doc: SubDoc, path: str | Path) -> None:
    ass_doc: AssDoc = doc.envelope
    parts: list[str] = []
    slot_iter = iter(sl for sl in doc.lines)   # or use sub_index directly
    for seg in ass_doc.segments:
        if isinstance(seg, AssOpaqueSegment):
            parts.append(seg.raw)
        else:  # AssDialogueSlot
            sl = doc.lines[seg.sub_index]
            text_out = sl.raw if sl.raw is not None else sl.text
            parts.append(seg.prefix + text_out + seg.line_ending)
    result = "".join(parts)
    Path(path).write_bytes(result.encode(ass_doc.encoding))
```

**_render_block pattern** (`srt.py` lines 251–262) — raw takes precedence:
```python
# srt.py _render_block:
if sl.raw is not None:
    return sl.raw           # opaque pass-through verbatim
le = line_ending
return f"{sl.index}{le}{sl.start_tc} --> {sl.end_tc}{le}{sl.text}"
# For ASS write_ass: the write loop handles this inline via seg.prefix
```

---

### `trezarr/subtitles/vtt.py` (codec, file-I/O + transform)

**Analog:** `trezarr/subtitles/srt.py` (same pattern — blank-line block splitting)

**Envelope dataclasses** (from RESEARCH §4.1):
```python
@dataclass
class VttOpaqueBlock:
    raw: str
    trailing_sep: str    # blank line(s) after this block

@dataclass
class VttCueBlock:
    identifier_line: str | None   # cue identifier or None
    timing_line: str              # verbatim "HH:MM:SS.mmm --> HH:MM:SS.mmm [settings]"
    line_ending: str              # "\r\n" or "\n"
    sub_index: int                # index into SubDoc.lines
    trailing_sep: str             # blank line(s) after

@dataclass
class VttDoc:
    blocks: list          # list[VttOpaqueBlock | VttCueBlock]
    encoding: str
    line_ending: str
```

**Blank-line split pattern** — same `_SEP_RE` logic as `srt.py` lines 59–136:
```python
# srt.py uses:
_SEP_RE = re.compile(r"((?:\r?\n)(?:[ \t]*\r?\n)+)")
tokens = _SEP_RE.split(text)
block_texts: list[str] = tokens[0::2]
separators: list[str]  = tokens[1::2]
# VTT: same split, but the first "block" is always the WEBVTT header → VttOpaqueBlock
```

**Timing-line detection** (VTT `-->` rule, RESEARCH §4.2):
```python
_VTT_TIMING_RE = re.compile(r'-->')

def _parse_vtt_block(block_text: str, trailing_sep: str) -> VttOpaqueBlock | VttCueBlock:
    lines = block_text.splitlines()
    if not lines:
        return VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep)
    # NOTE/STYLE/REGION blocks → opaque
    if lines[0].startswith(("NOTE", "STYLE", "REGION")):
        return VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep)
    # Timing line detection: first line with "-->" is the timing line
    if _VTT_TIMING_RE.search(lines[0]):
        timing_line = lines[0]
        identifier_line = None
        payload = "\n".join(lines[1:]) if len(lines) > 1 else ""
    elif len(lines) >= 2 and _VTT_TIMING_RE.search(lines[1]):
        identifier_line = lines[0]
        timing_line = lines[1]
        payload = "\n".join(lines[2:]) if len(lines) > 2 else ""
    else:
        # Malformed — preserve verbatim (D-10)
        warnings.warn(...)
        return VttOpaqueBlock(raw=block_text, trailing_sep=trailing_sep)
    # Parse start_tc / end_tc from timing_line
    ...
```

**read_vtt entry point** — mirrors `read_srt` structure; returns `SubDoc` with `envelope=VttDoc(...)`.

**write_vtt** — emits each block:
- `VttOpaqueBlock`: `raw + trailing_sep`
- `VttCueBlock`: `(identifier_line + le if identifier_line else "") + timing_line + le + translated_payload + trailing_sep`

---

### `trezarr/subtitles/dispatch.py` (router, request-response)

**Analog:** `engine.py` lines 46 + 674 (the hardcoded `read_srt` import/call being replaced)

**Full module** (from RESEARCH §8.2 — verbatim implementation to copy):
```python
from pathlib import Path
from .model import SubDoc
from .srt import read_srt, write_srt
from .ass import read_ass, write_ass
from .vtt import read_vtt, write_vtt

_READERS = {".srt": read_srt, ".ass": read_ass, ".ssa": read_ass, ".vtt": read_vtt}
_WRITERS = {".srt": write_srt, ".ass": write_ass, ".ssa": write_ass, ".vtt": write_vtt}

def read_subtitle(path: str | Path) -> SubDoc:
    path = Path(path)
    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"Unsupported subtitle format: {path.suffix}")
    return reader(path)

def write_subtitle(doc: SubDoc, path: str | Path) -> None:
    path = Path(path)
    writer = _WRITERS.get(path.suffix.lower())
    if writer is None:
        raise ValueError(f"Unsupported subtitle format: {path.suffix}")
    writer(doc, path)
```

---

### `trezarr/subtitles/model.py` (model — ADD one field)

**Analog:** `model.py` lines 48–86 (the existing `SubDoc` dataclass)

**Existing SubDoc tail** (`model.py` lines 80–86):
```python
    lines: list[SubLine]
    encoding: str
    line_ending: str
    separators: list[str]
    leading: str = ""
    trailer: str = ""
```

**Addition — append `envelope` field** (D-92 / RESEARCH §8 Open Question 2):
```python
    envelope: object = None   # format-specific envelope (AssDoc, VttDoc); None for SRT.
                               # Codec sets at read time; codec reads at write time.
                               # Pipeline NEVER reads this field.
```

The field is typed `object` (or `Any`) so no circular import is needed between `model.py` and the codec modules. The docstring note to add: "The pipeline (batching, sentinel, gate, engine) never reads `envelope`; only the codec that wrote it reads it back at `write_subtitle` time."

---

### `trezarr/translate/sentinel.py` (utility — EXTEND `TAG_RE`)

**Analog:** `sentinel.py` lines 14–17 (the current `TAG_RE`)

**Current TAG_RE** (`sentinel.py` line 17):
```python
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\})')
```

**Extended TAG_RE** (D-98 Extension A + optional Extension C, RESEARCH §5.2):
```python
# Extended to cover:
#   \\[Nnh]  — ASS raw hard breaks \N, \n, \h (not inside braces — raw backslash sequences)
#   &...;    — VTT HTML entity references (optional robustness; low priority)
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\}|\\[Nnh])')
```

Only this one line changes. `extract_sentinels` and `reinsert_sentinels` are unchanged — they use `TAG_RE.sub(replacer, text)` which picks up the new arm automatically.

**No change to function signatures.** The `replacer` closure at lines 44–49 and the reinsertion loop at lines 69–77 are untouched.

---

### `trezarr/translate/_timecode.py` (utility — EXTEND `tc_to_ms`)

**Analog:** `_timecode.py` lines 17–38 (the current single-regex `tc_to_ms`)

**Current `_TC_PARSE_RE`** (`_timecode.py` line 18):
```python
_TC_PARSE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)")
```

**Extended module** (RESEARCH §6.2 — drop-in replacement for the whole file body after imports):
```python
# Existing SRT pattern (2-digit hours, comma or period, variable ms digits)
_TC_PARSE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)")

# ASS: H:MM:SS.cc (1+ hour digit, exactly 2 centisecond digits, period only)
_ASS_TC_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{2})$")

# VTT with hours: HH:MM:SS.mmm (2+ hour digits, exactly 3 ms digits, period only)
_VTT_HOURS_TC_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{3})$")

# VTT hourless: MM:SS.mmm (no hours, exactly 3 ms digits, period only)
_VTT_HOURLESS_TC_RE = re.compile(r"(\d+):(\d{2})\.(\d{3})$")


def tc_to_ms(tc: str) -> int:
    """Convert timecode to milliseconds. Supports SRT, ASS, and VTT formats.

    Formats:
      SRT:          HH:MM:SS,mmm or HH:MM:SS.mmm  (existing — unchanged)
      ASS:          H:MM:SS.cc  (centiseconds * 10 = ms)
      VTT with hrs: HH:MM:SS.mmm
      VTT hourless: MM:SS.mmm

    Returns 0 for malformed input (existing contract — unchanged).
    """
    tc = tc.strip()

    # Try SRT first (must be first — its variable-digit ms pattern would shadow VTT 3-digit)
    m = _TC_PARSE_RE.match(tc)
    if m:
        h, mi, s, ms_str = m.group(1), m.group(2), m.group(3), m.group(4)
        ms = int(ms_str.ljust(3, '0')[:3])
        return int(h) * 3600000 + int(mi) * 60000 + int(s) * 1000 + ms

    # Try ASS: H:MM:SS.cc (exactly 2 centisecond digits)
    m = _ASS_TC_RE.match(tc)
    if m:
        h, mi, s, cc = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600000 + mi * 60000 + s * 1000 + cc * 10

    # Try VTT with hours: HH:MM:SS.mmm (exactly 3 ms digits)
    m = _VTT_HOURS_TC_RE.match(tc)
    if m:
        h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600000 + mi * 60000 + s * 1000 + ms

    # Try VTT hourless: MM:SS.mmm (exactly 3 ms digits)
    m = _VTT_HOURLESS_TC_RE.match(tc)
    if m:
        mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return mi * 60000 + s * 1000 + ms

    return 0  # malformed — existing contract unchanged
```

The module docstring's "Contract for malformed input" paragraph stays verbatim; extend it to mention ASS + VTT formats are now also handled.

---

### `trezarr/translate/validate.py` (gate — EXTEND `_check_untranslated`)

**Analog:** `validate.py` lines 37–106 (the current `ALLOWLIST_RE` + `_check_untranslated`)

**Current ALLOWLIST_RE** (`validate.py` line 37):
```python
ALLOWLIST_RE = re.compile(r'^[\W\d\s♪♫…\.]+$')
```

**New constant to add** (RESEARCH §7.2):
```python
# Lines that are exclusively sentinel tokens after tag extraction (no natural language)
SENTINEL_ONLY_RE = re.compile(r'^(<<T\d+>>\s*)*$')
```

**Current `_check_untranslated` loop** (`validate.py` lines 84–93):
```python
for i, (trn_line, src_line) in enumerate(zip(translated.lines, source.lines)):
    text = trn_line.text.strip()
    if not text:
        continue  # caught by check 2 before this; defensive skip
    if ALLOWLIST_RE.match(text):
        continue  # legitimately unchanged — excluded from ratio
    translatable_indices.append(i)
    if VN_DIACRITIC_RE.search(text):
        vi_count += 1
```

**Extended loop** (D-102 — add two early-continue guards before `translatable_indices.append`):
```python
for i, (trn_line, src_line) in enumerate(zip(translated.lines, source.lines)):
    # D-99/D-98: opaque pass-through cues (karaoke, drawing) — intentionally untranslated
    if trn_line.raw is not None:
        continue
    text = trn_line.text.strip()
    if not text:
        continue  # caught by check 2; defensive skip
    if ALLOWLIST_RE.match(text):
        continue  # legitimately unchanged — excluded from ratio
    if SENTINEL_ONLY_RE.match(text):   # pure-tag cue — no natural language content
        continue
    translatable_indices.append(i)
    if VN_DIACRITIC_RE.search(text):
        vi_count += 1
```

**Check 2 must also skip `raw is not None`** (RESEARCH §7.3) — add guard at the top of the check 2 loop:
```python
# Check 2: no empty/whitespace-only translated lines
for i, sl in enumerate(translated.lines):
    if sl.raw is not None:
        continue   # D-99/D-98: opaque pass-through — non-empty by codec contract
    if not sl.text.strip():
        raise GateError(GateFailure(2, f"Empty translated cue at index {i}", ...))
```

No other checks change. Check 4 (index/timecode identity) passes because ASS/VTT cues use `index=""` throughout, so source.index == translated.index == `""` for all ASS/VTT lines. Check 5 (monotonic) uses `tc_to_ms` which is now extended.

---

### `trezarr/translate/engine.py` (orchestrator — SWAP `read_srt` import)

**Analog:** `engine.py` lines 44–46 (current imports) and line 674 (current `read_srt` call)

**Current imports** (`engine.py` lines 44–46):
```python
from trezarr.output.write import derive_vi_sidecar_path, write_vi_sidecar
...
from trezarr.subtitles.srt import read_srt
```

**Change 1 — replace `read_srt` import** (engine.py line 46):
```python
# REMOVE:
from trezarr.subtitles.srt import read_srt
# ADD:
from trezarr.subtitles.dispatch import read_subtitle
```

**Change 2 — replace call site** (engine.py line 674):
```python
# BEFORE:
source_doc = read_srt(path)
# AFTER:
source_doc = read_subtitle(path)
```

**Change 3 — update log message** (engine.py line 650):
```python
# BEFORE:
logger.info("foreign vi.srt at %s, not ours — skipping %s", dest, path)
# AFTER:
logger.info("foreign vi sidecar at %s, not ours — skipping %s", dest, path)
```

The docstring at line 586 (`"Translate a source SRT file"`) and step descriptions mentioning `.vi.srt` should be updated to reflect format-agnostic language, but these are cosmetic.

**No other changes to engine.py.** The `write_vi_sidecar` call at line ~900+ is in `output/write.py` (handled below). The `SubDoc` reconstruction at lines 869–872 passes `envelope=None` (the translated SubDoc never needs the envelope — the write codec fetches it from the *source* SubDoc's `envelope` field; see RESEARCH Open Question 2).

**Important:** `write_vi_sidecar` in `output/write.py` constructs a NEW `SubDoc` (doc_out at line 121–128) with `encoding='utf-8'`. That new SubDoc must also carry `envelope=source_doc.envelope` so the write codec can reconstruct the ASS/VTT structure. See the `output/write.py` section below.

---

### `trezarr/output/write.py` (service — GENERALIZE sidecar naming + write dispatch)

**Analog:** `write.py` lines 43–44 (import), lines 63–88 (`derive_vi_sidecar_path`), lines 91–135 (`write_vi_sidecar`)

**Current import** (`write.py` line 43):
```python
from trezarr.subtitles.srt import write_srt
```

**Change 1 — replace import**:
```python
# REMOVE:
from trezarr.subtitles.srt import write_srt
# ADD:
from trezarr.subtitles.dispatch import write_subtitle
```

**Current `derive_vi_sidecar_path`** (`write.py` lines 68–88):
```python
def derive_vi_sidecar_path(media_path: str | Path) -> Path:
    media_path = Path(media_path).resolve()
    stem = media_path.stem
    if _LANG_CODE_RE.search(stem):
        stem = stem.rsplit('.', 1)[0]
    return media_path.parent / (stem + '.vi.srt')   # <-- HARDCODED
```

**Change 2 — generalize** (D-95, RESEARCH §8.3):
```python
def derive_vi_sidecar_path(media_path: str | Path) -> Path:
    """Derive the Vietnamese sidecar path from a source subtitle path.

    Rules:
      - Preserve the source extension (.srt, .ass, .ssa, .vtt).
      - If the stem ends with a 2-letter language code (e.g. ".en"), strip it.
      - Append ".vi<ext>" to form the sidecar name in the same directory.

    Example: Show.S01E01.en.ass → Show.S01E01.vi.ass
    """
    media_path = Path(media_path).resolve()
    suffix = media_path.suffix.lower()              # ".srt", ".ass", ".ssa", ".vtt"
    stem = media_path.stem
    if _LANG_CODE_RE.search(stem):
        stem = stem.rsplit('.', 1)[0]
    return media_path.parent / (stem + f'.vi{suffix}')
```

**Change 3 — update the docstring module header** (lines 29–32) to describe the generalized rule:
```
  Input:  Show.S01E01.en.ass  →  Output:  Show.S01E01.vi.ass
  Input:  Show.S01E01.vtt     →  Output:  Show.S01E01.vi.vtt
  Rule: strip any 2-letter ISO-639 language-code suffix from the stem
  (e.g. ".en", ".ja", ".fr"), then append ".vi<ext>" mirroring the source extension.
```

**Current `write_vi_sidecar` call** (`write.py` line 129):
```python
write_srt(doc_out, tmp_path)      # reuse Phase-1 serialiser
```

**Change 4 — use dispatch** (`write.py` line 129):
```python
write_subtitle(doc_out, tmp_path)   # format-dispatched serialiser
```

**Change 5 — carry the envelope through `doc_out`** (`write.py` lines 121–128):
The current `doc_out` construction omits `envelope` (it didn't exist before). Add it:
```python
doc_out = SubDoc(
    lines=doc.lines,
    encoding='utf-8',
    line_ending=doc.line_ending,
    separators=doc.separators,
    leading=doc.leading,
    trailer=doc.trailer,
    envelope=doc.envelope,    # <-- ADD: carry AssDoc/VttDoc for write codec
)
```

This is the critical bridge: the engine-assembled `translated_doc` carries the source's `envelope` because the engine copies it from `source_doc` when building `translated_doc` (see engine.py lines 869–872 — the planner must add `envelope=source_doc.envelope` there too).

---

### `trezarr/discover/gap.py` (service — LOG MESSAGE ONLY)

**Analog:** `gap.py` line 109 (the `logger.info` in Case 1)

**Current log message** (`gap.py` line 109):
```python
logger.info(
    "foreign vi.srt at %s — skipping %s (D-26, never clobber)",
    vi_path, source_sub_path,
)
```

**Change — update string only** (D-96 cosmetic fix):
```python
logger.info(
    "foreign vi sidecar at %s — skipping %s (D-26, never clobber)",
    vi_path, source_sub_path,
)
```

**No logic change.** `vi_path` is already derived via `derive_vi_sidecar_path(source_sub_path)` at line 102 — once `derive_vi_sidecar_path` is generalized in `output/write.py`, this import picks up the fix automatically (gap.py line 35: `from trezarr.output.write import derive_vi_sidecar_path`).

The return string at line 112 uses `"foreign vi sidecar at"` wording — update to match, since `scan.py` classifies via substring `"foreign"` (which is preserved in both forms). No scan.py change needed.

---

## Test File Patterns

### `tests/codec/test_ass_roundtrip.py`, `test_vtt_roundtrip.py`, `test_dispatch.py`, `test_karaoke.py`, `test_drawing.py`

**Analog:** `tests/codec/test_srt_roundtrip.py` (entire file — direct template)

**Fixture parameterization pattern** (`test_srt_roundtrip.py` lines 15–30):
```python
FIXTURES = Path(__file__).parent.parent / "fixtures"

_FIXTURE_FILES = [
    "minimal.ass",
    "karaoke.ass",
    "drawing.ass",
    "pos_an8.ass",
    "mixed.ass",
    "crlf.ass",
    "ssa_v4.ssa",
    "utf8bom.ass",
]

@pytest.mark.parametrize("fixture", _FIXTURE_FILES)
def test_byte_identical_roundtrip(tmp_path, fixture):
    from trezarr.subtitles.ass import read_ass, write_ass
    src = FIXTURES / fixture
    original_bytes = src.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        doc = read_ass(str(src))
    out = tmp_path / fixture
    write_ass(doc, str(out))
    assert out.read_bytes() == original_bytes
```

**Malformed block test pattern** (`test_srt_roundtrip.py` lines 60–86):
```python
def test_malformed_block_preserved_and_flagged(tmp_path):
    from trezarr.subtitles.ass import read_ass, write_ass
    src = FIXTURES / "malformed_dialogue.ass"
    original_bytes = src.read_bytes()
    with pytest.warns(UserWarning, match="malformed"):
        doc = read_ass(str(src))
    assert any(sl.raw is not None for sl in doc.lines)
    out = tmp_path / "malformed_dialogue.ass"
    write_ass(doc, str(out))
    assert out.read_bytes() == original_bytes
```

### `tests/translate/test_timecode.py` (ADD cases to existing file if it exists, else create)

**Analog:** `tests/translate/test_validate.py` lines 21–48 (helper + importorskip pattern)

**Pattern for new test cases** (RESEARCH §9.4):
```python
def test_tc_to_ms_ass_centiseconds():
    """ASS H:MM:SS.cc timecodes are converted correctly (centiseconds * 10 = ms)."""
    mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = mod.tc_to_ms
    assert tc_to_ms("0:01:23.45") == 83450    # 83*1000 + 45*10
    assert tc_to_ms("1:00:00.00") == 3600000
    assert tc_to_ms("0:00:00.00") == 0        # NOTE: zero-duration guard is at call site

def test_tc_to_ms_vtt_hourless():
    mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = mod.tc_to_ms
    assert tc_to_ms("01:23.456") == 83456
    assert tc_to_ms("00:01:23.456") == 83456  # VTT with explicit 0 hours

def test_tc_to_ms_srt_unchanged():
    mod = pytest.importorskip("trezarr.translate._timecode")
    tc_to_ms = mod.tc_to_ms
    assert tc_to_ms("00:00:01,000") == 1000   # SRT with comma — existing behavior
    assert tc_to_ms("garbage") == 0           # malformed contract unchanged
```

### `tests/translate/test_sentinel_ass_vtt.py`

**Analog:** `tests/translate/test_sentinel.py` lines 19–60 (deferred-import + TAG_RE test pattern)

```python
def test_extract_ass_hard_break():
    """\\N in ASS Text is treated as a sentinel token, not sent to LLM (D-98)."""
    sentinel_mod = pytest.importorskip("trezarr.translate.sentinel")
    extract_sentinels = sentinel_mod.extract_sentinels
    text = "Hello\\NWorld"
    cleaned, sentinel_map = extract_sentinels(text)
    assert "\\N" not in cleaned
    assert any("\\N" == v for v in sentinel_map.values())
```

### `tests/translate/test_validate_allowlist.py`

**Analog:** `tests/translate/test_validate.py` (the `_make_line` / `_make_doc` / `_settings` helpers + `pytest.importorskip` pattern)

```python
def test_karaoke_cue_allowlisted():
    """A SubLine with raw set (karaoke/drawing pass-through) is skipped by check 3 (D-102)."""
    validate_mod = pytest.importorskip("trezarr.translate.validate")
    from trezarr.subtitles.model import SubLine, SubDoc
    karaoke_text = r"{\k50}She {\k60}said {\k70}yes"
    sl = SubLine(index="", start_tc="0:00:01.00", end_tc="0:00:03.00",
                 text=karaoke_text, raw=karaoke_text)
    src = SubDoc(lines=[sl], encoding="utf-8", line_ending="\n", separators=[])
    trn = SubDoc(lines=[sl], encoding="utf-8", line_ending="\n", separators=[])
    # Should NOT raise — karaoke cue is allowlisted
    validate_mod.validate_subdoc(trn, src, _settings())
```

### `tests/output/` — sidecar extension tests

**Analog:** `tests/output/test_write.py` lines 37–71 (the `test_sidecar_naming` pattern):
```python
def test_sidecar_naming_ass(tmp_path):
    """derive_vi_sidecar_path(.ass) returns .vi.ass, not .vi.srt (D-95)."""
    write_mod = pytest.importorskip("trezarr.output.write")
    derive = write_mod.derive_vi_sidecar_path
    src = tmp_path / "Show.S01E01.en.ass"
    assert derive(src) == tmp_path / "Show.S01E01.vi.ass"

def test_sidecar_naming_vtt(tmp_path):
    write_mod = pytest.importorskip("trezarr.output.write")
    derive = write_mod.derive_vi_sidecar_path
    src = tmp_path / "Episode.S02E03.vtt"
    assert derive(src) == tmp_path / "Episode.S02E03.vi.vtt"
```

---

## Shared Patterns

### Byte-Identity via Raw Segment Capture
**Source:** `trezarr/subtitles/srt.py` lines 1–30 (module docstring strategy) + lines 108–136 (split/token logic)
**Apply to:** `ass.py` (segment list), `vtt.py` (block list)

The pattern: preserve verbatim structural pieces in a list of opaque/translatable segments. On write-back, iterate the list — opaque segments are emitted verbatim; translatable slots emit their verbatim prefix + translated text + captured line ending. The translated text is the ONLY byte that changes.

### Opaque Pass-Through (`SubLine.raw`)
**Source:** `trezarr/subtitles/srt.py` lines 155–214 (`_parse_block` + `_render_block`)
**Apply to:** `ass.py` karaoke/drawing detection; `vtt.py` malformed blocks

```python
# When raw is not None → emit verbatim (srt.py _render_block line 259-260):
if sl.raw is not None:
    return sl.raw
```

For karaoke/drawing: set BOTH `text` AND `raw` to the original Text field (RESEARCH §7.3 / A7). This satisfies check 2 (non-empty text) while marking the cue as intentionally untranslated for check 3.

### Encoding Detection + Verbatim Write-Back
**Source:** `trezarr/subtitles/srt.py` lines 82–90 + line 248
**Apply to:** `ass.py`, `vtt.py`

```python
raw_bytes = Path(path).read_bytes()
encoding = detect_encoding(raw_bytes)
text = raw_bytes.decode(encoding, errors="replace")
# ... on write-back:
Path(path).write_bytes(result.encode(doc.encoding))
```

### Deferred Import + `pytest.importorskip` (test pattern)
**Source:** `tests/translate/test_validate.py` lines 51–56 and `tests/codec/test_srt_roundtrip.py` lines 44–54
**Apply to:** All new test files

```python
def test_something():
    mod = pytest.importorskip("trezarr.subtitles.ass")
    read_ass = mod.read_ass
    ...
```

### `_make_doc` / `_make_line` helpers
**Source:** `tests/translate/test_validate.py` lines 21–48
**Apply to:** `tests/translate/test_validate_allowlist.py`, `tests/translate/test_sentinel_ass_vtt.py`

Copy the `_make_line`, `_make_doc`, and `_settings` helpers verbatim from `test_validate.py` into each new test file that needs `SubLine`/`SubDoc` construction.

---

## No Analog Found

All files have close analogs. No files require falling back to RESEARCH.md patterns alone.

| File | Note |
|------|------|
| `trezarr/subtitles/ass.py` `AssDoc`/`AssDialogueSlot`/`AssOpaqueSegment` dataclasses | No prior envelope dataclasses exist; use RESEARCH §3.2 design verbatim |
| `trezarr/subtitles/vtt.py` `VttDoc`/`VttCueBlock`/`VttOpaqueBlock` dataclasses | Same — use RESEARCH §4.1 design verbatim |
| Test fixtures (16 `.ass`/`.ssa`/`.vtt` files) | Synthetic files; RESEARCH §9.2–9.3 specifies required content per fixture |

---

## Integration Seam Priority (Regression Risk Order)

| Risk | Seam | Files | Key Line |
|------|------|-------|----------|
| HIGH | `tc_to_ms` regex — returns 0 for ALL ASS/VTT timecodes today → GateError on every file | `_timecode.py` | line 18 |
| HIGH | `derive_vi_sidecar_path` hardcodes `.vi.srt` → wrong sidecar for ASS/VTT, AUTO-04 loop | `output/write.py` | line 88 |
| MEDIUM | `_check_untranslated` will false-quarantine karaoke/drawing/tag-only cues | `validate.py` | lines 84–93 |
| MEDIUM | `TAG_RE` misses `\N`/`\h` → LLM drops hard breaks in ASS files | `sentinel.py` | line 17 |
| LOW | `read_srt` call in engine.py | `engine.py` | line 674 |
| LOW | `write_srt` call in write.py | `output/write.py` | line 129 |
| LOW | Log message strings saying "vi.srt" | `engine.py` L650, `gap.py` L109 |

---

## Metadata

**Analog search scope:** `trezarr/subtitles/`, `trezarr/translate/`, `trezarr/output/`, `trezarr/discover/`, `tests/codec/`, `tests/translate/`, `tests/output/`, `tests/discover/`
**Files read:** `srt.py`, `model.py`, `sentinel.py`, `_timecode.py`, `validate.py`, `engine.py` (seam lines), `output/write.py`, `discover/gap.py`, `tests/codec/test_srt_roundtrip.py`, `tests/translate/test_validate.py`, `tests/translate/test_sentinel.py`, `tests/output/test_write.py`, `tests/discover/test_scan.py`
**Pattern extraction date:** 2026-06-02
