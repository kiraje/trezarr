---
phase: 09-multi-format-ass-ssa-vtt
reviewed: 2026-06-02T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - trezarr/subtitles/ass.py
  - trezarr/subtitles/vtt.py
  - trezarr/subtitles/dispatch.py
  - trezarr/subtitles/model.py
  - trezarr/translate/_timecode.py
  - trezarr/translate/sentinel.py
  - trezarr/translate/validate.py
  - trezarr/translate/batching.py
  - trezarr/translate/engine.py
  - trezarr/output/write.py
  - trezarr/discover/gap.py
findings:
  critical: 2
  warning: 2
  info: 2
  total: 6
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-06-02
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 9 delivers hand-rolled ASS/SSA and VTT codecs with a byte-identity strategy
that is sound in design and largely correct in execution. The section-splitting logic
in ass.py, the block-based VTT parser, the dynamic Format: column map, the 9-comma
rule, the karaoke/drawing detection, and the dispatch table are all correctly
implemented. tc_to_ms handles ASS centiseconds and VTT hourless timecodes correctly;
the SRT pattern does NOT wrongly shadow 2-digit ASS timecodes because the ljust(3)[:3]
centisecond conversion is mathematically equivalent to the ASS cc*10 formula. The
ReDoS mitigations for all new patterns were verified with adversarial inputs. The
AUTO-04 self-output exclusion is correctly enforced by two independent guards
(foreign-vi skip in translate_file + find_source_sub never discovers .ass/.vtt files).

Two critical defects were found: the D-19 UTF-8 output requirement is violated for
non-UTF-8 ASS/VTT sources, and the Pass 4 review splice has an index-alignment bug
that corrupts translated text positions and overwrites karaoke/drawing pass-throughs
whenever raw-flagged cues are present. Both require fixes before the phase ships.

Two warnings were found: ASS/VTT source files are never discovered by the scanner
(find_source_sub only globs .srt), and the Pass 4 dominant_pair offset uses
inconsistent batch-size counters.

---

## Critical Issues

### CR-01: write_ass / write_vtt ignore doc.encoding — D-19 UTF-8 output violated

**File:** `trezarr/subtitles/ass.py:215`, `trezarr/subtitles/vtt.py:218`

**Issue:** `write_vi_sidecar` (output/write.py:144) creates a new `SubDoc` with
`encoding='utf-8'` to force the D-19 "always output UTF-8" contract. However,
`write_ass` uses `ass_doc.encoding` (from `doc.envelope`, which was captured from
the SOURCE file during `read_ass`) and `write_vtt` uses `vtt_doc.encoding`
(same pattern). The `doc.encoding` field set by `write_vi_sidecar` is **never read
by either codec**. For a Latin-1 or UTF-16LE source `.ass` or `.vtt` file, the
translated vi sidecar is written in the original encoding, not UTF-8, silently
producing an unreadable or BOM-prefixed Vietnamese subtitle.

SRT is correctly implemented: `write_srt` uses `doc.encoding` (srt.py:248).
Only ASS and VTT are affected.

**Fix:** Pass `doc.encoding` through to the codec rather than reading it from the
envelope. The simplest fix is to synchronize the envelope encoding from doc at
write time:

```python
# ass.py write_ass — before line 215
ass_doc: AssDoc = doc.envelope
ass_doc = AssDoc(
    segments=ass_doc.segments,
    encoding=doc.encoding,     # honour write-time encoding override (D-19)
    line_ending=ass_doc.line_ending,
)
...
Path(path).write_bytes(result.encode(ass_doc.encoding))
```

```python
# vtt.py write_vtt — before line 218
vtt_doc: VttDoc = doc.envelope
vtt_doc = VttDoc(
    blocks=vtt_doc.blocks,
    encoding=doc.encoding,     # honour write-time encoding override (D-19)
    line_ending=vtt_doc.line_ending,
)
...
Path(path).write_bytes(result.encode(vtt_doc.encoding))
```

Alternatively, both codecs can simply read `doc.encoding` directly without
rebuilding the envelope.

---

### CR-02: Pass 4 review splice has index misalignment when raw (karaoke/drawing) cues are present

**File:** `trezarr/translate/engine.py:988-1003`

**Issue:** `batch_subdoc(translated_doc)` skips cues where `SubLine.raw is not None`
(karaoke/drawing pass-through). The resulting `review_batches[i].cues` list is
therefore **shorter** than `translated_doc.lines` whenever raw cues are present.
The splice loop then indexes into `corrected_lines` (which has the FULL length
including raw-cue entries) using `corrected_lines[offset + i]` where `offset`
increments by `len(rb.cues)` — but `len(rb.cues)` does not account for the
raw-cue slots.

**Concrete failure scenario** (source has 4 cues, index 1 is karaoke/drawing):

```
translated_doc.lines = [tcue0, tcue1(raw='k'), tcue2, tcue3]
review_batches = [Batch(cues=[tcue0, tcue2, tcue3])]   # tcue1 skipped
corrected_texts = ['vi0', 'vi2', 'vi3']

# Splice:
# i=0: corrected_lines[0+0] = new cue(tcue0, 'vi0')   ← correct
# i=1: corrected_lines[0+1] = new cue(tcue2, 'vi2')   ← WRONG: writes index 1 (tcue1/karaoke)
#      raw pass-through is OVERWRITTEN with a normal translated SubLine
# i=2: corrected_lines[0+2] = new cue(tcue3, 'vi3')   ← WRONG: writes index 2 (tcue2)
```

**Effects:** (a) karaoke/drawing cues have `raw` cleared and arbitrary translated
text injected — producing garbage output for karaoke runs; (b) translated cue texts
are written one position too low, so the wrong lines get the Pass 4 corrections;
(c) gate check 4 (timecode byte-identity) may fail if cue.start_tc fields are
misaligned after the overwrite.

**Fix:** Walk `corrected_lines` with a separate doc-level pointer that advances
past raw-cue slots, mirroring the queue-based approach used in the main assembly
(engine.py:879-899):

```python
# Replace the splice block (lines 988-1003) with:
corrected_lines = list(translated_doc.lines)
# Walk corrected_lines with a doc-level pointer; review_batch cues are in
# the same relative order as non-raw translated_doc.lines entries.
doc_pos = 0   # position in corrected_lines (includes raw slots)
for rb, corrected_texts in zip(review_batches, review_results):
    if corrected_texts is None:
        # Skip forward by the number of cues in this batch (non-raw only),
        # but we need to advance doc_pos past all slots including raw ones.
        # Collect the cues from rb to know how many non-raw lines to skip.
        for cue in rb.cues:
            # advance doc_pos past any raw slots, then past this cue slot
            while doc_pos < len(corrected_lines) and corrected_lines[doc_pos].raw is not None:
                doc_pos += 1
            doc_pos += 1
        continue
    for cue, new_text in zip(rb.cues, corrected_texts):
        # Skip past any raw-cue slots that precede this translatable slot
        while doc_pos < len(corrected_lines) and corrected_lines[doc_pos].raw is not None:
            doc_pos += 1
        corrected_lines[doc_pos] = SubLine(
            index=cue.index,
            start_tc=cue.start_tc,
            end_tc=cue.end_tc,
            text=new_text,
            raw=None,
        )
        doc_pos += 1
```

---

## Warnings

### WR-01: find_source_sub only discovers .srt sources — ASS/VTT sources never reach the pipeline

**File:** `trezarr/discover/scan.py:167`

**Issue:** `find_source_sub` globs `{escaped_stem}.*.srt` (hard-coded `.srt` suffix).
Phase 9 adds codecs for `.ass`, `.ssa`, and `.vtt` but the scanner's discovery
function will never find a `.en.ass` or `.en.vtt` source file. An operator who
has ASS/VTT source subtitles will see zero eligible items despite Phase 9 being
in place. The dispatch table in dispatch.py is correct; the gap is purely in
discovery.

**Fix:** Extend `find_source_sub` to glob all supported suffixes:

```python
SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt")

for ext in SUBTITLE_EXTENSIONS:
    candidates = sorted(media_dir.glob(f"{escaped_stem}.*{ext}"))
    # ... match _LANG_SIDECAR_RE adjusted to match the specific ext, or
    # use a broader pattern that captures the lang token for each ext
```

The `_LANG_SIDECAR_RE` pattern should be parameterised or broadened to
`r'^(.+?)\.([a-z]{2,3})\.(srt|ass|ssa|vtt)$'`.

---

### WR-02: Pass 4 dominant_pair stamps wrong attributions when review batch size differs from attribution batch size

**File:** `trezarr/translate/engine.py:940-952`

**Issue:** The dominant_pair stamping loop (Pass 4 pre-dispatch) uses `_rb_offset`
incremented by `_batch_size = len(rb.cues)` (review batch sizes, governed by
`self_review_max_cues_per_batch`). It slices `flat_attributions` built from Pass 2
attribution batches (governed by `attribute_max_cues_per_batch`, a different setting).
When these two settings differ, `_rb_offset` diverges from the actual position within
`flat_attributions`, stamping dominant_pair from the wrong cue range. The cue totals
match (same non-raw cues), but the boundary positions shift.

This does not corrupt output (Pass 4 is best-effort; wrong dominant_pair only means
weaker Bible-adherence hints), but it means the Pass 4 self-review ignores or
misapplies pronoun context in every batch after the first divergence.

**Fix:** Build a unified attribution-index map from `flat_attributions` keyed on
`cue.index` (or document position), then look up attributions for each review batch
cue by index rather than by sequential offset:

```python
# Build a flat dict from cue index -> attribution (single pass)
_attr_by_cue_index: dict[str, object] = {}
_attr_cue_idx = 0
for src_line in source_doc.lines:
    if src_line.raw is None and _attr_cue_idx < len(flat_attributions):
        _attr_by_cue_index[src_line.index] = flat_attributions[_attr_cue_idx]
        _attr_cue_idx += 1

# Then in the dominant_pair loop, look up each rb.cue by cue.index:
for rb in review_batches:
    _pair_counts: dict[tuple[int, int], int] = {}
    for _cue in rb.cues:
        _attr = _attr_by_cue_index.get(_cue.index)
        if _attr:
            ...  # existing pair-count logic
```

---

## Info

### IN-01: SENTINEL_ONLY_RE in validate.py is unreachable dead code

**File:** `trezarr/translate/validate.py:45, 103-104`

**Issue:** `SENTINEL_ONLY_RE = re.compile(r'^(<<T\d+>>\s*)*$')` is compiled at
module level and checked in `_check_untranslated` (line 103). The accompanying
comment states it matches "A pure-tag cue (e.g. `{\an8}{\pos(960,50)}`) becomes
`<<T0>><<T1>>`". However, `_check_untranslated` runs on the **translated SubDoc**,
whose `SubLine.text` fields have already had sentinels **reinserted** (back to
original tag form, e.g. `{\an8}{\pos(960,50)}`). The `<<T0>><<T1>>` form is never
present in `translated.lines[i].text` at this point; sentinel tokens remaining after
reinsertion are caught by gate check 6 (`SENTINEL_RE`) and cause
`BatchValidationError` before the doc-level gate runs. `SENTINEL_ONLY_RE.match`
always returns `None` in practice, and the `continue` on line 104 is never reached.

The comment is also misleading: `{\an8}` is NOT matched by `ALLOWLIST_RE`
(the characters `a`, `n` are `\w`, not `\W`), so pure-tag ASS events without
karaoke/drawing detection will count toward the VI diacritic ratio denominator —
the opposite of what the comment implies.

**Fix:** Remove the dead `SENTINEL_ONLY_RE` check and its module-level constant.
If the intent was to exclude pure-tag-only events from the ratio, use `ALLOWLIST_RE`
extended to cover `{\\...}` ASS override blocks, or set `raw=text` for
tag-only-text cues in the codec.

---

### IN-02: ASS pure-tag-only Dialogue events can falsely suppress the VI diacritic ratio

**File:** `trezarr/translate/validate.py:_check_untranslated`

**Issue:** An ASS `Dialogue:` event whose `Text` field contains only override tags
with no natural-language content (e.g. `{\an8}{\pos(960,50)}` — used for global
positioning) is not a karaoke or drawing-mode cue, so `KARAOKE_RE`/`DRAWING_RE` do
not fire and `SubLine.raw` is left `None`. The event enters the LLM batch, the LLM
is expected to pass the sentinels through unchanged, and reinsertion restores the
tag text. `_check_untranslated` then sees the restored tag text, finds no Vietnamese
diacritics, and counts it as an untranslated line toward the denominator. For
heavily-styled ASS files (many layout-only events), this can push the VI ratio
below the threshold and trigger a spurious quarantine.

**Fix:** In `_parse_dialogue_line` (ass.py), after the existing KARAOKE_RE /
DRAWING_RE check, add a check for text that consists entirely of ASS override tags
(all content is within `{...}` blocks, no plain text outside):

```python
# After KARAOKE_RE / DRAWING_RE check, before creating the normal SubLine:
_TAG_ONLY_RE = re.compile(r'^(\{[^}]*\})+$')
if _TAG_ONLY_RE.fullmatch(text):
    sl = SubLine(index="", start_tc=start_tc, end_tc=end_tc, text=text, raw=text)
```

This is lower priority than CR-01/CR-02; many ASS files have few or no
tag-only-text events. Quarantine only occurs when the ratio of such events
exceeds `(1 - translate_vi_diacritic_ratio)`.

---

_Reviewed: 2026-06-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
