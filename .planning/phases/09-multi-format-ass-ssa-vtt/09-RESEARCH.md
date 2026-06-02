# Phase 9: Multi-Format — ASS/SSA + VTT — Research

**Researched:** 2026-06-02
**Domain:** ASS/SSA + WebVTT subtitle codecs; format dispatch; sentinel/timecode/gate extension
**Confidence:** HIGH (format grammars verified against Aegisub docs and W3C spec; all code findings grounded in direct codebase reads)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-91:** Hand-rolled, raw-preservation parsers/serializers for ASS/SSA and VTT. Do NOT use pysubs2 on the write path. (Supersedes D-02.)
- **D-92:** Keep `SubLine`/`SubDoc` as the format-agnostic pipeline contract. Each translatable ASS `Dialogue:` / VTT cue maps to one `SubLine`. Full document structure lives in a per-format envelope owned by the codec.
- **D-93:** `batch_subdoc`, `validate_subdoc`, sentinel, reconcile, 3-pass engine — format-agnostic; must not learn format specifics.
- **D-94:** Suffix-keyed dispatcher `read_subtitle(path)` / `write_subtitle(doc, path)`. Replace hardcoded `read_srt` and `write_srt` calls in `engine.py` and `output/write.py`.
- **D-95:** Output format mirrors input. `.ass` → `.vi.ass`, `.vtt` → `.vi.vtt`, `.srt` → `.vi.srt`. Generalize `derive_vi_sidecar_path` to mirror source extension, keep ISO-639 lang-suffix stripping.
- **D-96:** Generalize self-output exclusion (AUTO-04) and gap-detection: foreign `.vi.<ext>` skip logic in `engine.py` and `discover/gap.py` must become `.vi.<ext>`-aware.
- **D-97:** Translatable unit = entire `Text` field of a `Dialogue:` event. Never translate `Comment:` events, `[Script Info]`, styles, Format lines, actor/name, effect, layer, or margins.
- **D-98:** Extend sentinel `TAG_RE` to also protect `\N`/`\n`/`\h` inside Text, and drawing-mode runs (text between `{\p1}`…`{\p0}` is vector geometry — protect the whole run).
- **D-99:** Karaoke = verbatim pass-through. Any Dialogue Text containing `\k`, `\kf`, `\ko`, `\K`, or `\kt` → pass cue text UNTRANSLATED, byte-identical; allowlist at gate.
- **D-100:** VTT codec preserves WEBVTT header, NOTE/STYLE/REGION blocks, cue identifiers, and cue settings strings verbatim. Extend sentinel for VTT inline tags. Translate only the cue payload text.
- **D-101:** Extend `tc_to_ms` in `trezarr/translate/_timecode.py` for ASS `H:MM:SS.cc` (centiseconds) and VTT `MM:SS.mmm` / `HH:MM:SS.mmm`. Verbatim strings stay in `start_tc`/`end_tc`.
- **D-102:** Extend `validate_subdoc` untranslated-line allowlist for karaoke, drawing-only, empty-after-tag-strip, and pure-tag/sign cues.
- **Carried forward:** D-08 (byte-identical), D-09 (tags in text, pipeline never touches them), D-10 (malformed → preserve-and-flag), D-12 (sentinel placeholder-protection).

### Claude's Discretion

- Exact module/package layout (`trezarr/subtitles/ass.py`, `trezarr/subtitles/vtt.py`, `trezarr/subtitles/dispatch.py`)
- Precise envelope data structure per format
- Exact regexes for drawing-run/karaoke detection and VTT cue-settings capture
- Test-fixture selection (must include real-world anime ASS with `\pos`/`\an8`/`\p`/`\k` and VTT with cue settings + `<v>` + STYLE/REGION + inline `<timestamp>`)
- Whether style-based sign/OP/ED skipping is added now or deferred

### Deferred Ideas (OUT OF SCOPE)

- Style-based sign/OP/ED skipping (per-style policy + per-series config knob)
- Karaoke syllable-timing remapping
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FMT-02 | Parse and write ASS/SSA, translating only dialogue text and leaving override tags, drawing commands, `\N` breaks, and `[Script Info]`/`[V4+ Styles]` headers byte-identical | Grounded: ASS grammar documented below; hand-rolled raw-preservation envelope strategy specified; srt.py is the direct template |
| FMT-03 | Preserve karaoke (`\k`) lines without corruption — verbatim if remapping is unsafe | Grounded: karaoke detection regex specified; D-99 allowlist mechanism is an extension of existing ALLOWLIST_RE in validate.py |
| FMT-04 | Parse and write VTT, round-tripping cue settings/positioning | Grounded: VTT grammar from W3C spec; envelope strategy specified; tc_to_ms extension defined |
</phase_requirements>

---

## Summary

Phase 9 extends the subtitle pipeline from SRT-only to ASS/SSA + VTT by adding two new hand-rolled raw-preservation codecs, a format dispatcher, and targeted extensions to three shared modules (`sentinel.py`, `_timecode.py`, `validate.py`). The pipeline above the codec layer — batching, sentinel, validation gate, three-pass engine — remains untouched (D-93).

The critical structural insight is that `srt.py`'s `leading + block[i] + separator[i] + trailer` raw-preservation strategy generalizes directly to ASS and VTT, but with richer envelope shapes: ASS needs to preserve non-Event sections (Script Info, Styles, Fonts, Graphics) and the event-section structure verbatim around only the `Dialogue:` lines that are translated; VTT needs to preserve the WEBVTT header block, NOTE/STYLE/REGION blocks, and the per-cue identifier + settings string around only the cue payload that is translated.

Three integration seams are high-risk regression points: (1) `_timecode.py` `tc_to_ms` — currently returns 0 for any ASS/VTT timecode, which causes the gate's monotonic check to raise `GateError` on every ASS/VTT file; (2) `derive_vi_sidecar_path` and the foreign-vi-skip logic in `engine.py` and `gap.py` — currently hardcoded to `.vi.srt`, so AUTO-04 self-output exclusion will silently fail for the new formats; (3) `validate.py` ALLOWLIST_RE — currently admits only punctuation/digits/symbols, so tag-heavy or karaoke cues will false-quarantine.

**Primary recommendation:** Implement ASS and VTT codecs as separate modules (`ass.py`, `vtt.py`) with a thin `dispatch.py`. Extend sentinel, timecode, and validation gate as targeted, minimal changes. The ASS codec carries a per-format `AssDoc` envelope; the VTT codec carries a `VttDoc` envelope. Both codecs expose the same `read_*(path) -> SubDoc` / `write_*(doc, path)` interface as `srt.py`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ASS/SSA parse (byte-identity) | Subtitle Codec (`ass.py`) | — | Owns the format-specific envelope; pipeline never sees sections/styles |
| VTT parse (byte-identity) | Subtitle Codec (`vtt.py`) | — | Owns the format-specific envelope; pipeline never sees header/blocks/settings |
| Format dispatch (`read_subtitle`/`write_subtitle`) | `dispatch.py` | — | Single seam replacing two hardcoded call sites in `engine.py` and `output/write.py` |
| Sidecar naming (generalized) | `output/write.py` `derive_vi_sidecar_path` | `discover/gap.py` | Generalizes `.vi.srt` to mirror source extension; gap.py consumes it |
| Self-output exclusion (generalized) | `engine.py` + `discover/gap.py` | — | Both have independent foreign-vi-skip checks that must become `.vi.<ext>`-aware |
| Sentinel protection (ASS `\N`/`\h`, drawing runs, VTT tags) | `translate/sentinel.py` `TAG_RE` | — | The sentinel owns all placeholder-protection; codecs must not do their own |
| Timecode parsing (ASS centiseconds, VTT hourless) | `translate/_timecode.py` `tc_to_ms` | — | Single source of truth consumed by both `batching.py` and `validate.py` |
| Gate allowlist extension (karaoke/drawing/tag-only) | `translate/validate.py` | — | Gate is format-agnostic on `.text`; extend ALLOWLIST_RE or add per-cue allowlist flags |
| Drawing-mode detection | `ass.py` codec (parse time) | `sentinel.py` (protection) | Codec detects drawing runs during parse and marks them; sentinel protects the text in the pipeline |
| Karaoke detection | `ass.py` codec (parse time) | `validate.py` (allowlist) | Codec detects at parse time, sets SubLine metadata or uses `raw`; gate allowlists the cue |

---

## 1. ASS/SSA Format Grammar (FMT-02)

### 1.1 Section Structure

An ASS file is a UTF-8 text file (often without BOM; sometimes with UTF-8 BOM; line endings are typically CRLF in Windows-produced files and LF in Unix/fansub-tool output — both exist in the wild) with this section structure [CITED: aegisub.org/docs/latest/ass_tags, multimedia.cx/SubStation_Alpha]:

```
[Script Info]
; comments starting with semicolon
ScriptType: v4.00+
Title: ...
PlayResX: 1920
PlayResY: 1080
... other metadata key: value lines ...

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,...

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:01:23.45,0:01:25.67,Default,,0,0,0,,Xin chào
Comment: 0,0:01:23.45,0:01:25.67,Default,,0,0,0,,This is not displayed

[Fonts]
; optional — uuencoded embedded font data

[Graphics]
; optional — uuencoded embedded image data
```

For **SSA v4** (`.ssa` files), the section is `[V4 Styles]` (no plus) and the Events `Format:` line is:
```
Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
```
The first field is `Marked` (not `Layer`) and the 6th field is `Name` (not `Actor`). `Marked` is typically `Marked=0`. The raw-preservation strategy handles both identically — the key point is that **Text is always the LAST field** in both formats. [CITED: multimedia.cx/index.php/SubStation_Alpha]

### 1.2 Dialogue Line Parsing — The Comma Rule

The `Format:` line establishes the field count (10 fields in standard ASS, 10 in SSA). A `Dialogue:` line always has exactly `N-1 = 9` comma-separated prefix fields before the Text field, **regardless of how many commas Text itself contains**. The correct parse is:

```python
parts = line.split(",", 9)   # split on FIRST 9 commas only
# parts[0] = "Dialogue: 0"  (includes the "Dialogue: " prefix and Layer value)
# parts[1] = "0:01:23.45"   (Start)
# parts[2] = "0:01:25.67"   (End)
# parts[3] = "Default"       (Style)
# parts[4] = ""              (Name/Actor)
# parts[5] = "0"             (MarginL)
# parts[6] = "0"             (MarginR)
# parts[7] = "0"             (MarginV)
# parts[8] = ""              (Effect)
# parts[9] = "Xin chào, tôi là..."   (Text — may contain commas)
```

The strip of the line prefix `"Dialogue: "` leaves the Layer value at position 0. A cleaner approach: after stripping the line type prefix (`"Dialogue: "` or `"Comment: "`), split the remainder on `,` with `maxsplit=9`. [VERIFIED from format spec — the split-on-9-commas rule is exactly how every correct ASS parser works] [ASSUMED from training knowledge cross-verified with search results; the rule is stated consistently in multiple sources]

### 1.3 ASS Timecodes — `H:MM:SS.cc`

ASS timecodes use `H:MM:SS.cc` format where:
- `H` = hours (1 digit, typically `0`–`9`; can be more but extremely rare)
- `MM` = minutes (always 2 digits)
- `SS` = seconds (always 2 digits)
- `cc` = centiseconds (always **exactly 2 digits**, NOT milliseconds)

Examples: `0:01:23.45`, `1:00:00.00`, `0:00:00.00`

**Conversion to milliseconds for the gate:**
```
ms = H * 3_600_000 + MM * 60_000 + SS * 1_000 + cc * 10
```
The cc → ms conversion multiplies by 10 (because 1 centisecond = 10 ms). [CITED: multimedia.cx/SubStation_Alpha — timecode format `H:MM:SS.CC`; Aegisub confirms centiseconds]

**Round-trip rule:** The verbatim string `"0:01:23.45"` stays in `SubLine.start_tc`/`SubLine.end_tc` — it is never normalized on write-back. Only the parsed integer is used by the gate.

### 1.4 Inline Tags Inside the ASS Text Field

The Text field can contain: [CITED: aegisub.org/docs/latest/ass_tags/]

**Override blocks (already matched by existing `TAG_RE`):**
- `{\an8}`, `{\pos(960,50)}`, `{\i1}`, `{\b1}`, `{\c&H00FF00&}`, `{\alpha&HFF&}` — any `{\...}` block
- `{\t(...)}` — animation transform; may contain commas inside the block
- `{\fn Times New Roman}` — font name may contain spaces (safe: the whole block `{...}` is matched by TAG_RE's `\{\\[^}]+\}` pattern)
- `{\clip(m 0 0 l 1920 0 1920 1080 0 1080)}` — clip coordinates

**Hard breaks (must be added to sentinel):**
- `\N` — forced line break (uppercase N; no surrounding braces) — this is a raw backslash + capital N in the text
- `\n` — soft line break (lowercase n; used in wrap mode 2)
- `\h` — non-breaking space

**Drawing mode (must be protected as a run):**
- `{\p1}` starts drawing mode (scale=1); `{\p2}`, `{\p4}` are higher-resolution scales
- The text content BETWEEN `{\pN}` (N > 0) and `{\p0}` is vector drawing commands: `m`, `l`, `b`, `s`, `n` with coordinate pairs — NOT natural language
- Example: `{\p1}m 0 0 l 100 0 100 100 0 100{\p0}` — the `m 0 0 l 100 0 100 100 0 100` portion is geometry
- A drawing run with no `{\p0}` closer extends to end of Text field (implicit close)

**Karaoke tags (must trigger verbatim pass-through per D-99):**
- `{\k50}` — fill before highlight in secondary color, instantly switch at syllable start; duration in centiseconds
- `{\kf50}` or `{\K50}` — sweep fill left-to-right during duration
- `{\ko50}` — border-only before highlight
- `{\kt50}` — sets absolute start time for next syllable

### 1.5 Distinguishing ASS from SSA for Byte-Identity

The codec can detect format variant from:
1. `[V4+ Styles]` section header → ASS (write back as-is)
2. `[V4 Styles]` section header → SSA (write back as-is)
3. `ScriptType: v4.00+` in `[Script Info]` → ASS
4. `ScriptType: v4.00` → SSA

For byte-identity purposes, no discrimination is needed — the raw-preservation strategy preserves whatever header text is there verbatim. The only format-specific parse difference is the field names (Marked vs. Layer), but since we split on first 9 commas regardless and preserve everything except `parts[9]` (Text), the distinction collapses to: **always split on 9 commas, always treat index 9 as Text.** [ASSUMED: based on consistent field count across both variants; verified against spec sources]

---

## 2. VTT Format Grammar (FMT-04)

### 2.1 File Structure [CITED: w3.org/TR/webvtt1/]

```
WEBVTT [optional: space + arbitrary text on same line]

[optional blank lines or REGION/STYLE/NOTE blocks]

[cue-id line — any text not containing "-->"]
HH:MM:SS.mmm --> HH:MM:SS.mmm [cue-settings]
cue payload line 1
cue payload line 2

[blank line separator]

next cue...
```

**WEBVTT header:** The first line MUST begin with exactly `WEBVTT`. It may be followed by a space/tab and arbitrary text (e.g., `WEBVTT Kind: captions` or `WEBVTT - Generated`). After the header line come one or more line terminators, then optional header-block content (REGION/STYLE/NOTE blocks) separated by blank lines from the first cue.

**Block types before first cue:**
- `REGION\n...settings...` — defines positioning regions
- `STYLE\n...CSS...` — CSS rules for styling; CSS may NOT contain `-->` and must not have blank lines within
- `NOTE [text]` — comment block

**VTT timecodes (two shapes):**
- `HH:MM:SS.mmm` — with explicit hours
- `MM:SS.mmm` — hours omitted when zero (e.g., `01:23.456`)
- Separator is `.` (period, not comma)

**Cue settings on the timing line** (space-separated after the end timecode):
- `vertical:rl` or `vertical:lr`
- `line:N[%][,start|center|end]`
- `position:N%[,line-left|center|line-right]`
- `size:N%`
- `align:start|center|end|left|right`
- `region:id`

**Cue identifier:** Optional; any text on the line before the timecode line that does not contain `-->`. May be absent.

**Cue payload:** Lines of text until the first blank line. Cannot contain `-->`.

**Encoding:** UTF-8 by spec. Optional leading BOM (`U+FEFF`). Line endings: CRLF, LF, or CR all valid.

### 2.2 VTT Timecode Parsing for `tc_to_ms`

Two valid patterns:
```
MM:SS.mmm       where MM may be 1+ digits, SS = 2 digits, mmm = 3 digits
HH:MM:SS.mmm    where HH = 2+ digits
```

Detection rule: if the string has two colons, it's the HH:MM:SS.mmm form; if one colon, it's MM:SS.mmm.

```python
# Pattern for HH:MM:SS.mmm or MM:SS.mmm (VTT)
_VTT_TC_RE = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})")
```

Conversion:
```
ms = hours * 3_600_000 + minutes * 60_000 + seconds * 1_000 + milliseconds
```
Where hours = 0 if omitted. [CITED: w3.org/TR/webvtt1/]

### 2.3 VTT Inline Tags (Must Be Sentinel-Protected)

Tags appearing in cue payload text: [CITED: w3.org/TR/webvtt1/]
- `<v Speaker Name>` — voice annotation (speaker label; NOT a closing tag; content until `</v>`)
- `<c.classname>...</c>` — class span
- `<b>`, `<i>`, `<u>` — text styling
- `<ruby>base<rt>annotation</rt></ruby>` — ruby annotation; `<rt>` content is translatable annotation text
- `<lang en>...</lang>` — language span
- `<00:01:23.456>` — inline timestamp (timestamp cue tag; never translatable, always verbatim)
- Character references: `&amp;`, `&nbsp;`, `&#160;`, etc.

The existing `TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\})')` already matches `<v Speaker>`, `<c.class>`, `<b>`, `<i>`, `<u>`, `<ruby>`, `<rt>`, `<lang>`, and `<00:01:23.456>` via the `<[^>]+>` arm. **The only gap** is entity references (`&nbsp;`, `&amp;`, etc.) — these are not matched by the current TAG_RE. Since entity refs appear in the middle of natural language text and are not themselves translatable (they render as whitespace or punctuation), they should either be (a) protected as sentinels or (b) passed through to the LLM as-is (the LLM will typically preserve `&nbsp;` literally since it's a web entity). The safest approach for byte-identity: extend the sentinel to match `&[a-zA-Z]+;` and `&#\d+;` patterns. [ASSUMED: entity refs are common enough in VTT to warrant protection]

---

## 3. ASS Codec Envelope Design (D-91 / D-92)

### 3.1 The Core Challenge

ASS files have multiple sections. Only the `[Events]` section contains `Dialogue:` lines. The byte-identity requirement means the codec must preserve `[Script Info]`, `[V4+ Styles]`, `[Fonts]`, `[Graphics]`, `Comment:` events, and all formatting within the Events section — while allowing the Text field of `Dialogue:` events to be replaced.

### 3.2 Recommended Envelope: Token/Segment List

The recommended strategy is a **verbatim segment list**, analogous to how `srt.py` uses `leading + block[i] + separator[i] + trailer`, but at two levels:

**Level 1 — Section segments:** Decompose the raw file into a list of segments where each segment is either:
- A verbatim "opaque" chunk (the entire `[Script Info]` text, the entire `[V4+ Styles]` text including its Format line and Style lines, a `Comment:` event line, a `[Fonts]` block, etc.)
- A "dialogue slot" that records the verbatim prefix (everything from `"Dialogue: "` through the 9th comma, including all fields up to but NOT including Text) and holds a reference to the `SubLine` whose `.text` replaces the original Text field on write-back

On write-back, the codec reconstructs the file by iterating segments: opaque chunks are emitted verbatim; dialogue slots emit their verbatim prefix + translated `SubLine.text`.

**Concrete data shape (Python):**

```python
from dataclasses import dataclass, field

@dataclass
class AssOpaqueSegment:
    """A verbatim chunk of the ASS file that is never translated."""
    raw: str

@dataclass
class AssDialogueSlot:
    """A Dialogue: event whose Text field is translatable."""
    prefix: str          # "Dialogue: 0,0:01:23.45,0:01:25.67,Default,,0,0,0,,"
                         # (everything including the trailing comma before Text)
    line_ending: str     # "\r\n" or "\n"
    sub_index: int       # index into SubDoc.lines — links slot to SubLine

@dataclass
class AssDoc:
    """ASS/SSA document envelope for byte-identical round-trip."""
    segments: list[AssOpaqueSegment | AssDialogueSlot]
    encoding: str
    line_ending: str
    # SubDoc is the pipeline contract; AssDoc.segments + SubDoc.lines are parallel.
    # The reader populates both simultaneously.
```

**Why not store raw byte offsets?** Byte offsets require the write-back to slice raw bytes, which fails when `SubLine.text` has a different byte length than the original Text field. The segment list naturally handles length changes because it reconstructs from string parts. The ONLY part that changes on write-back is the Text field content; all prefix bytes are preserved verbatim. [ASSUMED: this design is the most robust for variable-length text replacement; confirmed by the analogous srt.py strategy]

### 3.3 Read Algorithm

```
1. read_bytes() → detect encoding → decode
2. Split on section headers ([...] lines at start of a line)
3. For each non-[Events] section: append as AssOpaqueSegment(raw=entire_section_text)
4. For the [Events] section:
   a. The "Format: Layer, ..." line → append as AssOpaqueSegment
   b. For each subsequent line:
      - If starts with "Comment:": append as AssOpaqueSegment
      - If starts with "Dialogue:": split on first 9 commas → extract prefix (parts[0..8])
        and text (parts[9]). Detect karaoke/drawing. Append AssDialogueSlot(prefix=..., sub_index=len(sub_lines))
        and SubLine(index="", start_tc=parts[1].strip(), end_tc=parts[2].strip(), text=parts[9]).
        Handle karaoke (SubLine.raw=parts[9]) and drawing-only (SubLine.raw=parts[9]) cases.
      - Anything else (blank line, stray line): append as AssOpaqueSegment
5. Return AssDoc(segments=...) and SubDoc(lines=sub_lines, ...)
```

**Important:** `SubLine.index` has no natural meaning in ASS (events are not numbered). Use `""` for index (the pipeline's index-mutation check in validate.py check 4 compares source vs. translated index — both will be `""` so the check passes). [ASSUMED: using empty string for ASS index is safe given validate.py check 4 compares source.index == translated.index]

### 3.4 Write Algorithm

```
1. Assert len([s for s in doc.segments if isinstance(s, AssDialogueSlot)]) == len(sub_doc.lines)
2. For each segment in doc.segments:
   - AssOpaqueSegment → emit segment.raw verbatim
   - AssDialogueSlot → emit slot.prefix + sub_doc.lines[slot.sub_index].text + slot.line_ending
3. Encode result with doc.encoding, write_bytes()
```

---

## 4. VTT Codec Envelope Design (D-100)

### 4.1 Recommended Envelope: Block List

VTT files decompose naturally into blank-line-delimited blocks, similar to SRT. The VTT envelope is a list of blocks where each block is either:
- A verbatim "opaque" block (WEBVTT header block, NOTE/STYLE/REGION blocks, or blocks that fail to parse as cues)
- A "cue block" with a verbatim prefix (identifier line if present + timing line including settings) and a reference to a SubLine for payload

```python
@dataclass
class VttOpaqueBlock:
    raw: str
    trailing_sep: str   # blank line(s) after this block

@dataclass
class VttCueBlock:
    identifier_line: str | None  # verbatim identifier line (or None)
    timing_line: str             # verbatim "HH:MM:SS.mmm --> HH:MM:SS.mmm [settings]"
    line_ending: str             # "\r\n" or "\n"
    sub_index: int               # index into SubDoc.lines
    trailing_sep: str            # blank line(s) after this cue block

@dataclass
class VttDoc:
    blocks: list[VttOpaqueBlock | VttCueBlock]
    encoding: str
    line_ending: str
```

**Write-back:** Each VttOpaqueBlock emits `raw + trailing_sep`. Each VttCueBlock emits:
- `identifier_line + line_ending` (if identifier_line is not None)
- `timing_line + line_ending`
- `sub_doc.lines[sub_index].text` (the translated payload; may be multi-line with internal `\n` or `\r\n`)
- `trailing_sep`

### 4.2 VTT Read Algorithm

```
1. read_bytes() → detect encoding → decode
2. Extract WEBVTT header block (everything up to the first blank line) → VttOpaqueBlock
3. Split remainder on blank-line boundaries (capturing separators, like srt.py)
4. For each block:
   a. If starts with "NOTE", "STYLE", "REGION": VttOpaqueBlock
   b. Otherwise: try to parse as a cue:
      - If the FIRST line contains "-->": timing_line = first_line, identifier_line = None,
        payload = remainder
      - If the SECOND line contains "-->": identifier_line = first_line, timing_line = second_line,
        payload = remainder after second line
      - Otherwise: VttOpaqueBlock (malformed — preserve verbatim per D-10)
   c. For a valid cue: parse start_tc and end_tc from timing_line. payload is the cue payload text.
      Append VttCueBlock and SubLine(index="", start_tc=..., end_tc=..., text=payload)
5. Return VttDoc and SubDoc
```

**Note on multi-line payloads:** VTT cue payloads can span multiple lines. `SubLine.text` stores the full multi-line payload verbatim (with internal line endings preserved) — the same pattern as SRT where multi-line cue text is stored with its original line endings.

---

## 5. Sentinel Extension (D-98 / D-100)

### 5.1 Current `TAG_RE`

```python
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\})')
```

This already matches `{\an8}`, `{\pos(960,50)}`, `<i>`, `<v Speaker>`, `<00:01:23.456>`, etc.

### 5.2 Required Extensions

**Extension A — ASS `\N`, `\n`, `\h` hard breaks:**

These appear as raw backslash sequences in the Text field (not inside `{}`). They are NOT natural language and MUST survive the LLM unchanged (the LLM must not drop or translate them).

Add a third arm to TAG_RE:
```python
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\}|\\[Nnh])')
```
This matches `\N`, `\n`, `\h` as literal backslash + character. [ASSUMED: adding `\\[Nnh]` is the correct minimal extension; no overlap with existing arms]

**Extension B — ASS drawing-mode runs:**

A drawing-mode run is the entire span from `{\pN}` (N >= 1) through `{\p0}` (or end of Text if no closer). The drawing commands inside are coordinate geometry and must NEVER be sent to the LLM.

Detection in the codec (at parse time, before sentinels): use a regex to detect any `{\p[1-9]}` in the Text field. If found, mark the entire Text as a drawing run — the whole `SubLine.text` is non-translatable.

```python
DRAWING_RE = re.compile(r'\{\\p[1-9]\d*\}')

def is_drawing_run(text: str) -> bool:
    return bool(DRAWING_RE.search(text))
```

Policy: if `is_drawing_run(text)` is True, set `SubLine.raw = text` (opaque pass-through, same as malformed SRT blocks). This means the drawing cue is never sent to the LLM and is re-emitted verbatim. **Do NOT try to protect only the geometry portion** — the Text field may interleave drawing commands with position tags in complex ways that are not safe to partially protect. [ASSUMED: whole-cue pass-through for drawing runs is the correct conservative approach; consistent with D-98 "protect the whole run"]

**Extension C — VTT entity references:**

Optional but recommended for robustness:
```python
TAG_RE = re.compile(r'(<[^>]+>|\{\\[^}]+\}|\\[Nnh]|&(?:[a-zA-Z]+|\#\d+|\#x[0-9a-fA-F]+);)')
```
This adds HTML entity references. The LLM is not adversely affected if entities pass through unprotected (it will typically preserve `&nbsp;` literally), so this is low-priority — skip if it complicates the regex. [ASSUMED: entity refs are not a critical sentinel gap; the LLM behavior is predictable]

### 5.3 Drawing-Mode vs. Karaoke: Two Different Mechanisms

| Situation | Detection | Action | Gate behavior |
|-----------|-----------|--------|---------------|
| Drawing run `{\p1}...{\p0}` | `DRAWING_RE` in codec | `SubLine.raw = text` (whole cue verbatim) | raw-set cues have `.text = original_text` → ALLOWLIST_RE or raw flag |
| Karaoke `\k`, `\kf`, `\K`, `\ko`, `\kt` | `KARAOKE_RE` in codec | `SubLine.raw = text` (whole cue verbatim) | same |

Both use `SubLine.raw` as the verbatim pass-through mechanism (same as malformed SRT cues). On write-back, the codec emits `SubLine.raw` when set. **The gate sees the raw text as `.text`** — currently `SubLine.raw` is emitted by the codec but the pipeline's SubLine builder needs to also set `.text` to the raw value so validate.py's check 2 (no empty text) and check 3 (untranslated ratio) work correctly. [ASSUMED: setting both `.raw` and `.text` to the original Text field for karaoke/drawing cues is the cleanest approach]

---

## 6. Timecode Parser Extension (D-101)

### 6.1 Current `_TC_PARSE_RE`

```python
_TC_PARSE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)")
```

**Problem:** Requires exactly 2-digit hours. ASS timecodes have 1-digit hours (`0:01:23.45`). VTT timecodes may omit hours entirely (`01:23.456`). Both return 0 (malformed→0 contract) → gate raises GateError on every ASS/VTT file.

### 6.2 Extended `tc_to_ms`

```python
import re

# ASS: H:MM:SS.cc (1 or more hour digits, 2-digit centiseconds, period separator)
_ASS_TC_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{2})$")

# VTT hourless: MM:SS.mmm (no hours; period separator; exactly 3 ms digits)
_VTT_HOURLESS_TC_RE = re.compile(r"(\d+):(\d{2})\.(\d{3})$")

# VTT with hours: HH:MM:SS.mmm (2+ hour digits; period separator; exactly 3 ms digits)
_VTT_HOURS_TC_RE = re.compile(r"(\d+):(\d{2}):(\d{2})\.(\d{3})$")

def tc_to_ms(tc: str) -> int:
    tc = tc.strip()

    # Try SRT-style first (HH:MM:SS,mmm or HH:MM:SS.mmm with 2+ hour digits — existing behavior)
    m = _TC_PARSE_RE.match(tc)
    if m:
        h, mi, s, ms_str = m.group(1), m.group(2), m.group(3), m.group(4)
        ms = int(ms_str.ljust(3, '0')[:3])
        return int(h) * 3600000 + int(mi) * 60000 + int(s) * 1000 + ms

    # Try ASS: H:MM:SS.cc (centiseconds * 10 = ms)
    m = _ASS_TC_RE.match(tc)
    if m:
        h, mi, s, cc = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600000 + mi * 60000 + s * 1000 + cc * 10

    # Try VTT with hours: HH:MM:SS.mmm
    m = _VTT_HOURS_TC_RE.match(tc)
    if m:
        h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600000 + mi * 60000 + s * 1000 + ms

    # Try VTT hourless: MM:SS.mmm
    m = _VTT_HOURLESS_TC_RE.match(tc)
    if m:
        mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return mi * 60000 + s * 1000 + ms

    return 0  # malformed — existing contract unchanged
```

**Key disambiguation:** The ASS pattern uses a 2-digit centisecond group `\.(\d{2})$` while VTT uses 3-digit milliseconds `\.(\d{3})$`. These are unambiguous. The SRT existing pattern uses `[,.](\d+)` with variable digit count, so it must be tried FIRST (to not shadow the 3-digit VTT case). Actually, since SRT uses comma OR period and ASS uses only period, we can refine further, but the try-order above is safe. [VERIFIED: ASS spec uses exactly 2 centisecond digits; VTT spec uses exactly 3 millisecond digits — these do not conflict]

**Verbatim strings** stay unchanged in `SubLine.start_tc` / `SubLine.end_tc`. The parsed ms value is used only by `tc_to_ms` (batching and gate). Write-back emits the verbatim string.

---

## 7. Validation Gate Extension (D-102)

### 7.1 Current `ALLOWLIST_RE`

```python
ALLOWLIST_RE = re.compile(r'^[\W\d\s♪♫…\.]+$')
```

Lines matching this are excluded from the Vietnamese diacritic ratio check. Currently covers: all-punctuation, all-digits, musical notes, ellipsis.

### 7.2 Extensions Needed

**Problem:** ASS/VTT files contain cues that have no natural-language content:
- A karaoke cue: `{\k50}She {\k60}said {\k70}yes` — has what looks like English words but must pass verbatim
- A drawing cue: `{\p1}m 0 0 l 100 0 100 100 0 100{\p0}` — all drawing commands
- A pure-tag cue: `{\an8}{\pos(960,50)}` — no text at all (after sentinel replacement: `<<T0>><<T1>>`)
- A sign-only cue: `{\pos(100,200)}BAKERY` — the word "BAKERY" is a sign/location label; after translation it may remain in Latin characters

**Recommended approach:** Rather than extending `ALLOWLIST_RE` to cover all these cases (the regex would become unmaintainable), use a **SubLine-level flag** approach:

When the ASS codec detects a karaoke or drawing cue (sets `SubLine.raw`), it also sets `SubLine.text` to the original Text. The gate's check 3 (`_check_untranslated`) should skip any SubLine where `.raw is not None` (opaque pass-through = intentionally untranslated). This is cleaner than adding more arms to ALLOWLIST_RE.

Additionally, extend ALLOWLIST_RE to cover the empty-after-tag-strip case (a cue whose text is entirely override tags with no natural language):
```python
# After sentinel extraction, cleaned_text may be empty or only sentinel tokens
# Extend ALLOWLIST_RE or add a separate check:
SENTINEL_ONLY_RE = re.compile(r'^(<<T\d+>>\s*)*$')
```
A line that is only sentinel tokens has no natural language → allowlisted. [ASSUMED: this is the minimal correct extension; the sentinel-only pattern does not overlap with legitimate translation output]

**Modified `_check_untranslated`:**
```python
for i, (trn_line, src_line) in enumerate(zip(translated.lines, source.lines)):
    # Skip opaque pass-through cues (karaoke, drawing — D-99/D-98)
    if trn_line.raw is not None:
        continue
    text = trn_line.text.strip()
    if not text:
        continue
    if ALLOWLIST_RE.match(text):
        continue
    if SENTINEL_ONLY_RE.match(text):  # pure-tag cue — no natural language
        continue
    translatable_indices.append(i)
    ...
```

### 7.3 Check 2 (No Empty Lines) for Karaoke/Drawing Cues

Check 2 asserts `sl.text.strip()` is not empty. For karaoke/drawing cues where `SubLine.raw` is set to a non-empty value and `.text` is set to the same non-empty value, check 2 passes naturally. The risk is if `.text` is accidentally set to `""` for these cues — the codec must ensure `.text` is always the original Text field even for pass-through cues.

### 7.4 Check 4 (Timecode/Index Identity) for ASS/VTT

ASS does not have numeric indices. Using `index=""` in SubLine for all ASS cues means source.index == translated.index == `""` for all cues → check 4 passes. Same for VTT. [ASSUMED: consistent empty-string indexing satisfies the byte-equality check]

---

## 8. Format Dispatch and Module Layout (D-94 / D-95 / D-96)

### 8.1 Recommended Module Layout

```
trezarr/
  subtitles/
    __init__.py
    model.py          (unchanged — SubLine, SubDoc)
    encoding.py       (unchanged — detect_encoding)
    srt.py            (unchanged — read_srt, write_srt)
    ass.py            (NEW — read_ass, write_ass; AssDoc envelope)
    vtt.py            (NEW — read_vtt, write_vtt; VttDoc envelope)
    dispatch.py       (NEW — read_subtitle, write_subtitle keyed on suffix)
```

### 8.2 `dispatch.py`

```python
from pathlib import Path
from .model import SubDoc
from .srt import read_srt, write_srt
from .ass import read_ass, write_ass
from .vtt import read_vtt, write_vtt

_READERS = {
    ".srt": read_srt,
    ".ass": read_ass,
    ".ssa": read_ass,
    ".vtt": read_vtt,
}

_WRITERS = {
    ".srt": write_srt,
    ".ass": write_ass,
    ".ssa": write_ass,
    ".vtt": write_vtt,
}

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

### 8.3 Generalizing `derive_vi_sidecar_path` (D-95)

Current code in `output/write.py` (line ~88):
```python
return media_path.parent / (stem + '.vi.srt')   # HARDCODED .vi.srt
```

Generalized version:
```python
def derive_vi_sidecar_path(media_path: str | Path) -> Path:
    media_path = Path(media_path).resolve()
    suffix = media_path.suffix.lower()            # ".srt", ".ass", ".ssa", ".vtt"
    stem = media_path.stem
    if _LANG_CODE_RE.search(stem):
        stem = stem.rsplit('.', 1)[0]
    return media_path.parent / (stem + f'.vi{suffix}')
```

This produces `.vi.ass`, `.vi.ssa`, `.vi.vtt` to mirror the source extension. The ISO-639 lang-suffix stripping (`_LANG_CODE_RE`) continues to strip `.en`, `.ja`, etc. from the stem. [VERIFIED: the stripping regex strips the LANG code from the stem; the suffix comes from the source path unchanged]

**Critical note:** This function is called in TWO places — `engine.py` (line ~643) and `discover/gap.py` (line ~102) — both via the same imported function. Changing the function in `output/write.py` automatically fixes both call sites. The import in `gap.py` is `from trezarr.output.write import derive_vi_sidecar_path`. No separate fix is needed in `gap.py` if the function signature is unchanged. [VERIFIED: gap.py line 35 imports `derive_vi_sidecar_path` from `output.write` and uses it at line 102]

### 8.4 Generalizing Self-Output Exclusion (D-96)

**`engine.py` lines ~648-651 (foreign-vi skip):**
```python
# CURRENT (hardcoded .vi.srt in log message only — the actual check uses derive_vi_sidecar_path):
if entry is None and dest.exists():
    logger.info("foreign vi.srt at %s, not ours — skipping %s", dest, path)
    return TranslationResult(status="skipped")
```
The log message says "vi.srt" but the `dest` is already derived via `derive_vi_sidecar_path(path)` — once that function is generalized (D-95), `dest` will be correct for all formats. **The only change needed in `engine.py` is updating the log message string** from `"foreign vi.srt"` to `"foreign vi sidecar"` (cosmetic only). The logic itself is already format-agnostic via the shared `derive_vi_sidecar_path`.

**`discover/gap.py` line ~112 (log message):**
```python
logger.info("foreign vi.srt at %s — skipping %s (D-26, never clobber)", vi_path, source_sub_path)
```
Similarly: the `vi_path` is already derived via `derive_vi_sidecar_path`. Only the log message needs updating. The scan logic in `scan.py` that classifies the `False` reason via substring match (`"foreign"` in reason string) does not need to change.

**Bottom line:** AUTO-04 self-output exclusion is effectively already format-agnostic at the logic level — it relies on `derive_vi_sidecar_path` which is the single source of truth. The D-96 work is: (1) generalize `derive_vi_sidecar_path` (D-95 work), (2) update log message strings, (3) ensure tests cover the ASS/VTT variant.

### 8.5 `engine.py` Read Dispatch (D-94)

**Change at line ~674:**
```python
# BEFORE:
source_doc = read_srt(path)
# AFTER:
from trezarr.subtitles.dispatch import read_subtitle
source_doc = read_subtitle(path)
```

The import of `read_srt` from `srt.py` (line ~47 of engine.py) becomes `read_subtitle` from `dispatch`. The `write_vi_sidecar` in `output/write.py` also needs to use `write_subtitle` dispatch instead of `write_srt`. However, `write_vi_sidecar` currently forces `encoding='utf-8'` for the output (D-19). This needs to carry through: the dispatcher in `write_subtitle` should also force UTF-8 output (or the `write_vi_sidecar` wrapper does it, then calls `write_subtitle`). [ASSUMED: write_vi_sidecar continues to force UTF-8 and calls the dispatch writer]

---

## 9. Test Fixtures and Test Strategy

### 9.1 Byte-Identity Round-Trip Pattern (from existing `test_srt_roundtrip.py`)

The existing SRT round-trip test pattern is:
```python
original_bytes = src.read_bytes()
doc = read_srt(str(src))
write_srt(doc, str(out))
assert out.read_bytes() == original_bytes
```

The ASS and VTT tests mirror this exactly, parameterized over format-specific fixtures.

### 9.2 Required Fixtures — ASS

| Fixture | What It Covers | Why |
|---------|---------------|-----|
| `minimal.ass` | `[Script Info]`, `[V4+ Styles]`, `[Events]` with one plain Dialogue line | Baseline round-trip |
| `karaoke.ass` | `[Events]` with `{\k50}syllable{\k60}timing` in one Dialogue Text | FMT-03 karaoke verbatim |
| `drawing.ass` | `[Events]` with `{\p1}m 0 0 l 100 100{\p0}` in one Dialogue Text | FMT-02 drawing protection |
| `pos_an8.ass` | `[Events]` with `{\an8}{\pos(960,50)}` positioning tags | Tag preservation |
| `mixed.ass` | All of the above plus `Comment:` lines, multiple styles, `\N` breaks | Integration fixture |
| `crlf.ass` | CRLF line endings throughout | Line-ending preservation |
| `ssa_v4.ssa` | `[V4 Styles]` section (not V4+), `Marked=0` in Dialogue format | SSA variant |
| `utf8bom.ass` | UTF-8 with BOM | BOM round-trip |

**Real-world fixture recommendation:** Source a genuine anime `.ass` file from a public fansub release (e.g., released under GPL or CC) with `\pos`, `\an8`, `\p` drawing signs, and `\k` karaoke timing for the OP. If licensing is uncertain, construct a synthetic file that includes all these structural elements. The fixture must exercise the full section structure as it appears in real files.

### 9.3 Required Fixtures — VTT

| Fixture | What It Covers | Why |
|---------|---------------|-----|
| `minimal.vtt` | `WEBVTT` header + one simple cue | Baseline |
| `cue_settings.vtt` | Cues with `position:`, `line:`, `align:`, `size:` settings | FMT-04 position preservation |
| `voices.vtt` | `<v Speaker>` inline tags | Voice tag protection |
| `style_region.vtt` | `STYLE` + `REGION` blocks before first cue | Block preservation |
| `inline_timestamp.vtt` | Cue with `<00:01:23.456>` inline timestamp | Inline timestamp protection |
| `hourless_tc.vtt` | Cues with `MM:SS.mmm` timecodes (no hours) | tc_to_ms hourless path |
| `note_block.vtt` | `NOTE` block interspersed with cues | Note block preservation |
| `crlf.vtt` | CRLF line endings | Line-ending preservation |

### 9.4 Test for `tc_to_ms` Extension

Direct unit tests for the new timecode forms:
```python
assert tc_to_ms("0:01:23.45") == 83450    # ASS centiseconds → ms
assert tc_to_ms("1:00:00.00") == 3600000  # ASS 1-hour
assert tc_to_ms("01:23.456")  == 83456    # VTT hourless
assert tc_to_ms("00:01:23.456") == 83456  # VTT with explicit 0 hours
assert tc_to_ms("00:00:01,000") == 1000   # SRT unchanged
assert tc_to_ms("garbage")     == 0       # malformed contract unchanged
```

### 9.5 Regression Tests — AUTO-04

For each supported extension (`.srt`, `.ass`, `.ssa`, `.vtt`):
- Test that `derive_vi_sidecar_path(source.ext)` returns `source.vi.ext` (not `.vi.srt`)
- Test that `is_eligible` returns `(False, "foreign vi sidecar at ...")` when a `.vi.ass` file exists without a ledger entry (for an `.ass` source)

---

## 10. Common Pitfalls

### Pitfall 1: Comma in ASS Text Field

**What goes wrong:** `text.split(",")` on a Dialogue line splits at commas inside dialogue. The cue "Yes, I know" becomes two fields.
**Why it happens:** ASS Text may contain commas; the field count is fixed at 10.
**How to avoid:** Always `line.split(",", 9)` — exactly 9 splits, making the 10th element (index 9) the complete Text regardless of its internal commas.
**Warning sign:** `SubLine.text` ends with a numeric value or empty string (truncated at first dialogue comma).

### Pitfall 2: ASS Timecode Returns 0 in `tc_to_ms`

**What goes wrong:** Gate raises `GateError` on every ASS/VTT file because `tc_to_ms("0:01:23.45")` returns 0 → start_ms=0, end_ms=0 → zero-duration guard fires.
**Why it happens:** Current `_TC_PARSE_RE` requires exactly 2-digit hours; ASS uses 1-digit hours.
**How to avoid:** The tc_to_ms extension (Section 6) handles this. Run the regression test suite after extending.
**Warning sign:** Every ASS/VTT file is quarantined with a GateError mentioning "non-positive duration: start=0ms >= end=0ms".

### Pitfall 3: `\N` Translated or Dropped by LLM

**What goes wrong:** The LLM sees `Xin chào\nTôi là` and interprets `\n` as a punctuation artifact, rewriting as `Xin chào Tôi là` (merged) or translating the surrounding words differently without the break.
**Why it happens:** `\N` and `\n` are NOT within `{...}` blocks; they are raw text that the LLM sees.
**How to avoid:** The sentinel extension (Section 5.2, Extension A) replaces `\N`, `\n`, `\h` with `<<TN>>` tokens before the LLM call.
**Warning sign:** A round-tripped ASS file where multi-line cues are merged on screen, or `\N` appears literally in the translated Vietnamese text.

### Pitfall 4: Drawing Coordinates Corrupted

**What goes wrong:** A drawing-mode cue `{\p1}m 0 0 l 100 0 100 100 0 100{\p0}` is sent to the LLM. The LLM "translates" the coordinates (e.g., changes numbers or removes tokens), making the drawing corrupt on screen.
**Why it happens:** Without drawing-run detection, the Text field looks like noise text to the sentinel — the `{\p1}` and `{\p0}` tags are protected as sentinels, but the coordinate string `m 0 0 l 100 0 100 100 0 100` is sent raw to the LLM.
**How to avoid:** Detect drawing runs at parse time (DRAWING_RE) and set `SubLine.raw` for the whole cue. Never send drawing-run cues to the LLM.
**Warning sign:** ASS sign overlays appear corrupted in the player — wrong shape, wrong position, or missing entirely.

### Pitfall 5: Karaoke Timing Reflow

**What goes wrong:** A karaoke line `{\k50}She {\k60}said {\k70}yes` is translated to `Cô {\k50}ấy {\k60}đã {\k70}nói rằng có`. The syllable timing `\k50` no longer corresponds to the translated syllables.
**Why it happens:** Vietnamese translation reflows the text; karaoke timing is syllable-aligned to the source.
**How to avoid:** D-99 mandates verbatim pass-through (set `SubLine.raw` for karaoke cues). ALLOWLIST them in the gate. Never attempt to remap timing.
**Warning sign:** The karaoke sync is off in the player, or the gate rejects the file for "untranslated lines."

### Pitfall 6: VTT Hourless Timecode Breaks `tc_to_ms`

**What goes wrong:** VTT file has `01:23.456 --> 01:25.000`. `tc_to_ms("01:23.456")` returns 0. Gate fails.
**Why it happens:** Current regex requires two colons (HH:MM:SS); VTT with `MM:SS.mmm` has only one colon.
**How to avoid:** Extended `tc_to_ms` handles this (Section 6.2).
**Warning sign:** VTT files with short (<1 hour) cues quarantine with zero-duration gate errors.

### Pitfall 7: AUTO-04 Regression for New Extensions

**What goes wrong:** After writing `Show.S01E01.vi.ass`, the watcher picks up the sidecar as a new source subtitle and re-queues it for translation. Translation loop.
**Why it happens:** The self-output exclusion in `engine.py` / `gap.py` derives the vi-path via `derive_vi_sidecar_path`, which (after generalization) returns `.vi.ass` — the ledger entry records this path. The exclude check (`entry is None and dest.exists()`) correctly identifies it as "ours" on the next scan. BUT: if there is a bug in `derive_vi_sidecar_path` (returns wrong extension), the ledger lookup misses and the file appears "foreign" → retry loop.
**How to avoid:** Test `derive_vi_sidecar_path` for each extension. Test the AUTO-04 exclusion path for ASS/VTT explicitly.
**Warning sign:** Same ASS/VTT file keeps appearing as "new item" in the queue after being written.

### Pitfall 8: CRLF vs. LF in ASS Files

**What goes wrong:** An ASS file with CRLF line endings is read, and the codec splits on `\n` only, leaving trailing `\r` on each line's content. The `\r` appears inside tag detection or is written back with doubled CRLFs.
**Why it happens:** Python's `str.splitlines()` handles CRLF but joining on `\n` strips the CR.
**How to avoid:** Detect line endings at read time (same as `srt.py` line 94: `le = "\r\n" if "\r\n" in text else "\n"`). Use `re.split()` on `\r?\n` for section/line splitting. The raw block text (AssOpaqueSegment.raw, VttOpaqueBlock.raw, slot prefix strings) is captured from the original decoded text verbatim — so CRLFs are preserved as long as you don't re-split and re-join.

### Pitfall 9: VTT STYLE Block Blank-Line Rule

**What goes wrong:** A STYLE block in VTT is parsed as two cues because it contains a blank line (e.g., between CSS rules).
**Why it happens:** Blank lines are the VTT block separator. STYLE blocks explicitly CANNOT contain blank lines (W3C spec). In practice, some VTT files include blank lines inside STYLE blocks — treating this as a block boundary is correct per spec, but it may split a malformed STYLE block.
**How to avoid:** When a block starts with `STYLE`, read ALL lines until the next blank line as a single opaque block (no blank lines inside STYLE is the spec rule — any blank line terminates it). Emit as opaque verbatim including any trailing whitespace. [CITED: W3C WebVTT spec]

### Pitfall 10: VTT Cue Identifier Looks Like a Cue Setting

**What goes wrong:** A cue identifier line containing `-->` is mistaken for the timing line or causes an off-by-one in the timing line detection.
**Why it happens:** Cue identifiers may NOT contain `-->` per spec. A line containing `-->` is definitionally a timing line.
**How to avoid:** The timing-line detector is: "any line containing `-->`" (with optional surrounding whitespace). The identifier line is: "the line immediately before a timing line that does NOT contain `-->`". This unambiguously identifies both.

---

## 11. Dispatch & Integration Seams Summary

The following table lists each seam, the current hardcoded behavior, and the required change:

| File | Line(s) | Current | Change Required | Risk |
|------|---------|---------|-----------------|------|
| `engine.py` | ~47 | `from trezarr.subtitles.srt import read_srt` | Add `from trezarr.subtitles.dispatch import read_subtitle` | LOW |
| `engine.py` | ~674 | `source_doc = read_srt(path)` | `source_doc = read_subtitle(path)` | LOW |
| `engine.py` | ~649-651 | `"foreign vi.srt"` log message | Update log message string only | LOW |
| `output/write.py` | ~43 | `from trezarr.subtitles.srt import write_srt` | Add import of `write_subtitle` from dispatch | LOW |
| `output/write.py` | ~88 | `stem + '.vi.srt'` | `stem + f'.vi{suffix}'` | HIGH (regression risk for SRT) |
| `output/write.py` | ~129 | `write_srt(doc_out, tmp_path)` | `write_subtitle(doc_out, tmp_path)` | LOW |
| `discover/gap.py` | ~112 | `"foreign vi.srt"` log message | Update log message string only | LOW |
| `translate/_timecode.py` | ~18 | `_TC_PARSE_RE` only matches `\d{2}:\d{2}:\d{2}[,.]` | Add ASS + VTT patterns (Section 6) | HIGH (monotonic gate fails on all ASS/VTT) |
| `translate/sentinel.py` | ~17 | `TAG_RE` misses `\N`, `\n`, `\h` | Add `\\[Nnh]` arm to TAG_RE | MEDIUM |
| `translate/validate.py` | ~86-104 | `_check_untranslated` skips only ALLOWLIST_RE | Skip `raw is not None` cues (Section 7.2) | MEDIUM |

---

## 12. Package Legitimacy Audit

This phase adds **no new external packages**. All work is in the standard library plus already-installed project dependencies. pysubs2 is already installed (from Phase 1 research, though not used on the write path); it remains a read-only reference tool only.

No `## Package Legitimacy Audit` table is needed — zero new packages are introduced.

---

## 13. Architecture Patterns

### System Architecture Diagram

```
subtitle file (bytes: .srt / .ass / .ssa / .vtt)
       |
       v
[dispatch.py read_subtitle(path)]
       |
       +-- .srt --> srt.py read_srt()  --+
       |                                  |
       +-- .ass/.ssa --> ass.py read_ass() --+
       |                                  |
       +-- .vtt --> vtt.py read_vtt()  --+
                                          |
                                          v
                             SubDoc (format-agnostic)
                                    + AssDoc / VttDoc (envelope, not in pipeline)
                                          |
                             [sentinel.py] extract_sentinels()
                             [batching.py] batch_subdoc()
                             [engine.py]   3-pass LLM pipeline
                             [validate.py] 7-check gate
                                          |
                                          v
                             translated SubDoc
                                          |
                                          v
[dispatch.py write_subtitle(doc, path)]
       |
       +-- .srt --> srt.py write_srt()
       |
       +-- .ass/.ssa --> ass.py write_ass()
       |                    (re-injects translated text into AssDoc envelope)
       |
       +-- .vtt --> vtt.py write_vtt()
                       (re-injects translated text into VttDoc envelope)
                                          |
                                          v
                      sidecar file (.vi.srt / .vi.ass / .vi.ssa / .vi.vtt)
```

### Project Structure (additions only)

```
trezarr/
  subtitles/
    ass.py          # NEW: ASS/SSA raw-preservation codec
    vtt.py          # NEW: VTT raw-preservation codec
    dispatch.py     # NEW: read_subtitle / write_subtitle dispatcher

tests/
  codec/
    test_ass_roundtrip.py   # NEW: byte-identity tests for ASS/SSA fixtures
    test_vtt_roundtrip.py   # NEW: byte-identity tests for VTT fixtures
    test_dispatch.py        # NEW: dispatcher routing tests
    test_karaoke.py         # NEW: karaoke verbatim pass-through tests
    test_drawing.py         # NEW: drawing-run verbatim tests
  translate/
    test_timecode.py        # NEW: tc_to_ms extension tests
    test_sentinel_ass_vtt.py # NEW: \N/\h/drawing-run sentinel tests
    test_validate_allowlist.py # NEW: gate allowlist extension tests
  fixtures/
    minimal.ass             # NEW
    karaoke.ass             # NEW
    drawing.ass             # NEW
    pos_an8.ass             # NEW
    mixed.ass               # NEW
    crlf.ass                # NEW
    ssa_v4.ssa              # NEW
    utf8bom.ass             # NEW
    minimal.vtt             # NEW
    cue_settings.vtt        # NEW
    voices.vtt              # NEW
    style_region.vtt        # NEW
    inline_timestamp.vtt    # NEW
    hourless_tc.vtt         # NEW
    note_block.vtt          # NEW
    crlf.vtt                # NEW
```

### Anti-Patterns to Avoid

- **Using pysubs2 on the write path:** pysubs2 normalizes section order, drops Comment events, renormalizes Style fields — breaks byte-identity (D-91, inherited from D-08/Phase 1 empirical finding).
- **Stripping `{...}` tags from Text before sending to LLM:** The sentinel mechanism handles tag protection; the codec must pass the raw Text field to the pipeline as-is.
- **Re-joining Text lines with `\n`:** ASS Text fields can contain `\N` (which is NOT a line ending in the file — it's a hard-break control character). Joining multi-line text with `\n` would corrupt these.
- **Splitting ASS Dialogue on ALL commas:** The Text field contains dialogue commas. Always use `split(",", 9)`.
- **Treating VTT `<v>` as an HTML tag and stripping it:** `<v Speaker>` is a voice annotation that must be preserved verbatim. The sentinel protects it as an opaque token.
- **Using `re.MULTILINE` carelessly on ASS content:** ASS section headers are detected with `^` match at line start — use `re.MULTILINE` or split on line boundaries first.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Encoding detection | Custom BOM/chardet logic | `encoding.detect_encoding()` (already implemented) | Handles UTF-8, UTF-8-BOM, UTF-16-LE/BE, CJK guard |
| Subtitle byte-identity | pysubs2 write path | Hand-rolled codec (srt.py pattern) | pysubs2 normalizes — empirically validated in Phase 1 |
| Concurrent LLM calls | `asyncio.gather` without cap | `LLMClient._semaphore` (already implemented) | Single concurrency gate; codecs never call LLM directly |
| Tag protection | Custom per-format tag stripping | `sentinel.py extract_sentinels()` (extended) | One mechanism for all formats; reinsertion integrity check |
| Atomic file write | `open(path, 'w')` | `write_vi_sidecar()` temp+rename pattern | Crash safety; FMT-05 contract |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pytest.ini` / `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `pytest tests/codec/ tests/translate/test_timecode.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FMT-02 | ASS byte-identical round-trip (plain cue) | unit | `pytest tests/codec/test_ass_roundtrip.py -x` | ❌ Wave 0 |
| FMT-02 | ASS `\N`/`\h` preserved verbatim | unit | `pytest tests/codec/test_ass_roundtrip.py::test_line_break_preserved -x` | ❌ Wave 0 |
| FMT-02 | ASS `[Script Info]` / `[V4+ Styles]` headers verbatim | unit | `pytest tests/codec/test_ass_roundtrip.py::test_section_headers_preserved -x` | ❌ Wave 0 |
| FMT-02 | ASS `Comment:` events verbatim (not translated) | unit | `pytest tests/codec/test_ass_roundtrip.py::test_comments_verbatim -x` | ❌ Wave 0 |
| FMT-02 | SSA `.ssa` variant byte-identical round-trip | unit | `pytest tests/codec/test_ass_roundtrip.py::test_ssa_roundtrip -x` | ❌ Wave 0 |
| FMT-02 | ASS drawing run NOT sent to LLM, verbatim output | unit | `pytest tests/codec/test_drawing.py -x` | ❌ Wave 0 |
| FMT-02 | Sentinel `\N`/`\h` placeholder-protected | unit | `pytest tests/translate/test_sentinel_ass_vtt.py -x` | ❌ Wave 0 |
| FMT-02 | Gate check 5 works for ASS timecodes | unit | `pytest tests/translate/test_timecode.py -x` | ❌ Wave 0 |
| FMT-02 | Gate check 4 works with empty-string index | unit | `pytest tests/translate/test_validate_allowlist.py -x` | ❌ Wave 0 |
| FMT-03 | Karaoke cue verbatim pass-through (not sent to LLM) | unit | `pytest tests/codec/test_karaoke.py -x` | ❌ Wave 0 |
| FMT-03 | Karaoke cue allowlisted at gate (no false-quarantine) | unit | `pytest tests/translate/test_validate_allowlist.py::test_karaoke_allowlisted -x` | ❌ Wave 0 |
| FMT-04 | VTT byte-identical round-trip (plain cue) | unit | `pytest tests/codec/test_vtt_roundtrip.py -x` | ❌ Wave 0 |
| FMT-04 | VTT cue settings string preserved verbatim | unit | `pytest tests/codec/test_vtt_roundtrip.py::test_cue_settings_preserved -x` | ❌ Wave 0 |
| FMT-04 | VTT STYLE/REGION/NOTE blocks verbatim | unit | `pytest tests/codec/test_vtt_roundtrip.py::test_blocks_verbatim -x` | ❌ Wave 0 |
| FMT-04 | VTT `<v>` / inline timestamp protected | unit | `pytest tests/translate/test_sentinel_ass_vtt.py::test_vtt_tags -x` | ❌ Wave 0 |
| FMT-04 | VTT hourless timecode `tc_to_ms` | unit | `pytest tests/translate/test_timecode.py::test_vtt_hourless -x` | ❌ Wave 0 |
| AUTO-04 | `derive_vi_sidecar_path(.ass)` returns `.vi.ass` | unit | `pytest tests/output/ -k "sidecar" -x` | ❌ Wave 0 |
| AUTO-04 | `is_eligible` skips foreign `.vi.ass` (not in ledger) | unit | `pytest tests/discover/ -k "foreign_ass" -x` | ❌ Wave 0 |
| FMT-04 | Visual: positioned ASS/VTT cue renders in correct screen position | manual | Load `.vi.ass` in mpv/Jellyfin, verify sign position matches source | human UAT |

### Sampling Rate

- **Per task commit:** `pytest tests/codec/ tests/translate/test_timecode.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps (all test files must be created before implementation)

- [ ] `tests/codec/test_ass_roundtrip.py` — covers FMT-02 byte-identity
- [ ] `tests/codec/test_vtt_roundtrip.py` — covers FMT-04 byte-identity
- [ ] `tests/codec/test_dispatch.py` — covers D-94 routing
- [ ] `tests/codec/test_karaoke.py` — covers FMT-03
- [ ] `tests/codec/test_drawing.py` — covers D-98 drawing-run
- [ ] `tests/translate/test_timecode.py` (add ASS/VTT cases to existing if file exists, else create)
- [ ] `tests/translate/test_sentinel_ass_vtt.py` — covers D-98/D-100 sentinel extension
- [ ] `tests/translate/test_validate_allowlist.py` — covers D-102 gate allowlist extension
- [ ] `tests/output/` — add derive_vi_sidecar_path generalization tests
- [ ] `tests/discover/` — add foreign `.vi.<ext>` exclusion tests
- [ ] All `.ass`/`.ssa`/`.vtt` fixture files (16 files listed in Section 9.2–9.3)
- [ ] Human UAT: visual player check for positioned cues

---

## Security Domain

`security_enforcement` is enabled (ASVS level 1 from config).

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Malformed ASS/VTT → D-10 preserve-and-flag; no code execution from subtitle content |
| V6 Cryptography | no | No crypto in codec layer |
| V2 Authentication | no | No auth in codec layer |
| V3 Session Management | no | No sessions in codec layer |
| V4 Access Control | no | Path traversal guard is at `output/write.py` caller level (already implemented) |

**Known threat patterns for this stack:**

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Subtitle-borne code execution (SSI/injection in ASS effect field) | Tampering | Effect field is never executed by Trezarr; preserved verbatim in envelope — not a concern for codec |
| Path traversal via derived sidecar path | Tampering | `paths.assert_within_media_roots()` already called by `cli.py` before write; unchanged |
| Malformed subtitle causing ReDoS | Denial of Service | Tag regex `[^>]+` and `[^}]+` have no nested quantifiers; applied per-line after split — safe. New `_ASS_TC_RE` uses anchored patterns applied per-field string only. |
| LLM-injected content in subtitle output | Tampering | The gate (validate.py) and sentinel reinsertion check are the integrity barrier; structural bytes (timecodes, headers) are never touched by the LLM |

---

## Environment Availability

This phase is code/config-only. No new external services, databases, or CLI tools are required beyond those already in use. pysubs2 is already installed (used as read-only reference only).

Step 2.6: SKIPPED (no new external dependencies; all required tools already present in the project environment).

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pysubs2 on write path (Phase 1 plan) | Hand-rolled raw-preservation codec | Phase 1 empirical testing | pysubs2 normalizes — byte-identity requires hand-rolling |
| SRT-only pipeline | ASS + VTT dispatch | Phase 9 | Format-agnostic pipeline contract (D-92/D-93) enables extension without moat changes |
| Hardcoded `.vi.srt` sidecar naming | Mirror source extension | Phase 9 | Players select subtitle format by extension; converting ASS→SRT discards styling |

**Deprecated/outdated:**
- D-02 (pysubs2 for ASS/SRT codec): Superseded by D-91. pysubs2 remains a read-only reference tool for grammar/field layout only.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ASS Dialogue line always has exactly 10 fields (split on 9 commas) regardless of SSA vs. ASS variant | 1.2 | If some variant has a different field count, Text extraction lands on the wrong field — wrong content translated |
| A2 | Using `SubLine.index = ""` for all ASS/VTT cues safely passes validate.py check 4 | 7.4 | If check 4 is stricter (requires non-empty or numeric), it will raise GateError for all ASS/VTT files |
| A3 | Drawing-run whole-cue pass-through (entire cue verbatim when `{\pN}` detected) is the correct conservative policy | 5.2 | If a cue interleaves natural-language dialogue with drawing commands, the dialogue goes untranslated — but this is explicitly the safe default per D-98 |
| A4 | VTT entity references (`&nbsp;` etc.) passed through to LLM are preserved literally and do not need sentinel protection | 5.2 | If an LLM model translates `&nbsp;` to a regular space, the output is subtly different from source — gate check 4 does NOT catch this (it only checks timecodes) |
| A5 | `derive_vi_sidecar_path` is the only place where the sidecar extension is determined; fixing it propagates to all consumers | 8.3 | If another code path derives the sidecar path independently, AUTO-04 regression is possible |
| A6 | SSA (`Marked` field) and ASS (`Layer` field) both use 10 fields and split identically on 9 commas | 1.5 | If SSA has a different field count, the split is wrong |
| A7 | Karaoke and drawing cues should use `SubLine.raw = original_text` AND `SubLine.text = original_text` (both set) | 5.3 | If only `raw` is set and `text` is empty/None, check 2 (no empty lines) fires |

---

## Open Questions

1. **ASS subtitle content from Phase 1/2: can pysubs2 be used as a grammar reference for the Format: line?**
   - What we know: pysubs2 1.8.1 is installed and can parse ASS correctly
   - What's unclear: whether the Format: line is always `Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text` or can be user-reordered
   - Recommendation: Treat the Format: line as authoritative (read it dynamically, build a column index map) rather than hardcoding the field order. This handles any non-standard ordering. [ASSUMED: standard field order is universal in practice, but dynamic parsing is safer]

2. **Does `engine.py` need to carry the `AssDoc`/`VttDoc` envelope through the pipeline?**
   - What we know: D-92 says the envelope lives in the codec; the pipeline sees only `SubDoc`. But `write_vi_sidecar` calls `write_srt` (or the dispatcher) and only has `SubDoc`. The write function needs BOTH the SubDoc (translated text) AND the AssDoc/VttDoc (envelope structure).
   - What's unclear: How does `write_ass()` get the envelope at write time?
   - Recommendation: The envelope must be stored on the SubDoc or passed separately. The cleanest approach is to store the envelope on SubDoc as an optional field (e.g., `SubDoc.envelope: Any = None`), set at read time by the codec, consumed at write time by the codec. This avoids changing the function signatures that pass SubDoc through the pipeline. The pipeline never reads `SubDoc.envelope` — only the codec does. [ASSUMED: this approach requires a single-field addition to SubDoc dataclass — minimal change]

3. **Is the VTT inline timestamp `<00:01:23.456>` always in `HH:MM:SS.mmm` format?**
   - What we know: The W3C spec defines inline timestamps in cue payloads; they must be within the cue's time range.
   - What's unclear: Whether hourless `<01:23.456>` inline timestamps appear in practice.
   - Recommendation: The existing `TAG_RE` arm `<[^>]+>` matches both forms without parsing the timestamp format. Since inline timestamps are never translatable, they are protected as sentinel tokens regardless of their exact format. No separate handling needed.

---

## Sources

### Primary (HIGH confidence)
- W3C WebVTT 1.0 Specification (w3.org/TR/webvtt1/) — VTT file structure, cue format, timecodes, inline tags, block types, encoding requirements
- Aegisub ASS Override Tags Reference (aegisub.org/docs/latest/ass_tags/) — complete tag list, drawing mode `{\p}`, karaoke `\k`/`\kf`/`\K`/`\ko`, `\N`/`\n`/`\h` breaks
- multimedia.cx/index.php/SubStation_Alpha — SSA vs. ASS differences, Events Format line fields, timecode format
- Direct codebase reads: `srt.py`, `model.py`, `encoding.py`, `sentinel.py`, `_timecode.py`, `validate.py`, `batching.py`, `engine.py` (lines 640-720), `output/write.py`, `discover/gap.py` — all integration seams verified against actual source

### Secondary (MEDIUM confidence)
- Phase 1 RESEARCH.md — pysubs2 byte-identity pitfalls (renumber/normalize/pad/LF); verified empirically in Phase 1
- WebSearch cross-verification: ASS Dialogue field count = 10 (split on 9 commas) confirmed in multiple independent sources (quicklrc.com/subtitle-formats/ass, multimedia.cx)

### Tertiary (LOW confidence — assumed)
- Field count consistency across SSA/ASS variants (A1, A6): stated in spec sources but no empirical test of exotic variants
- LLM entity-reference behavior (A4): based on general LLM behavior knowledge, not tested

---

## Metadata

**Confidence breakdown:**
- ASS grammar (section structure, comma rule, timecodes, tags): HIGH — Aegisub + multimedia.cx authoritative sources
- VTT grammar (blocks, timecodes, inline tags, settings): HIGH — W3C spec authoritative
- Envelope design (AssDoc, VttDoc): HIGH — derived from srt.py pattern directly
- tc_to_ms extension (exact regex): HIGH — formats are unambiguous, conversion math is exact
- Sentinel extension (TAG_RE): HIGH — existing regex pattern extended minimally
- Integration seams (exact line numbers): HIGH — verified by reading actual engine.py/write.py/gap.py source
- Test fixture list: MEDIUM — informed by real-world ASS/VTT structure but no actual anime ASS file read

**Research date:** 2026-06-02
**Valid until:** 2026-07-02 (stable formats; ASS spec has not changed in 15+ years; W3C VTT spec is a Recommendation)
