---
phase: 09-multi-format-ass-ssa-vtt
plan: "03"
subsystem: subtitle-codec
tags: [ass, ssa, subtitle, codec, karaoke, drawing, validate, gate, sentinel]

# Dependency graph
requires:
  - phase: 09-02
    provides: SubDoc.envelope field, sentinel TAG_RE extension, timecode extension

provides:
  - trezarr/subtitles/ass.py: hand-rolled ASS/SSA codec (read_ass, write_ass, AssDoc, AssOpaqueSegment, AssDialogueSlot)
  - trezarr/translate/validate.py: extended gate with raw-is-not-None guard + SENTINEL_ONLY_RE
  - batch_subdoc skips raw-set (karaoke/drawing) cues — never sent to LLM

affects:
  - 09-04 (VTT codec — same envelope pattern)
  - 09-05 (format dispatch — imports read_ass/write_ass)
  - translate/engine.py (any plan testing end-to-end ASS translation)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AssOpaqueSegment/AssDialogueSlot/AssDoc envelope: section-split + slot-list for byte-identical ASS round-trip"
    - "SubLine.raw = SubLine.text for karaoke/drawing opaque pass-through (D-98/D-99)"
    - "SENTINEL_ONLY_RE allows pure-token cues (no natural language) at gate check 3"
    - "raw-is-not-None guard at batch_subdoc and gate checks 2+3: codec marks verbatim cues, pipeline respects it"

key-files:
  created:
    - trezarr/subtitles/ass.py
  modified:
    - trezarr/translate/validate.py
    - trezarr/translate/batching.py
    - tests/codec/test_ass_roundtrip.py
    - tests/codec/test_karaoke.py
    - tests/codec/test_drawing.py
    - tests/translate/test_validate_allowlist.py

key-decisions:
  - "Section-split via re.finditer on [..] headers, not line-by-line walking — cleaner span arithmetic"
  - "Dynamic Format: line column-index map handles both ASS (Layer) and SSA (Marked) first fields transparently"
  - "Malformed Dialogue: stored via AssDialogueSlot with prefix='' so write_ass emits '' + content + le = original line"
  - "batch_subdoc skip for raw-set cues added as Rule 2 (missing critical: karaoke verbatim contract requires it)"

patterns-established:
  - "Batch.cues (not Batch.lines) is the attribute for cues in a batch — tests must use batch.cues"
  - "splitlines(keepends=True) to preserve per-line endings in mixed-CRLF/LF ASS files"

requirements-completed:
  - FMT-02
  - FMT-03

# Metrics
duration: 25min
completed: 2026-06-02
---

# Phase 9 Plan 03: ASS/SSA Codec + Gate Extension Summary

**Hand-rolled byte-identical ASS/SSA codec (read_ass/write_ass) with karaoke/drawing verbatim pass-through and gate extension that skips raw-set cues and pure-sentinel-token lines**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-02T00:00:00Z
- **Completed:** 2026-06-02T00:25:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- `trezarr/subtitles/ass.py` created: AssOpaqueSegment/AssDialogueSlot/AssDoc envelope, section-split strategy, dynamic Format: line column-index map, byte-identical round-trip for all 8 ASS/SSA fixtures (minimal, karaoke, drawing, pos_an8, mixed, crlf, ssa_v4, utf8bom)
- Karaoke cues (`\k/\kf/\ko/\K/\kt`) and drawing-run cues (`{\p1}…{\p0}`) detected at parse time and marked as opaque pass-through via SubLine.raw = SubLine.text = original Text
- `validate.py` extended: `SENTINEL_ONLY_RE` allowlists pure-`<<TN>>` cues; raw-is-not-None guard at checks 2 and 3 prevents false-quarantine of karaoke/drawing cues
- All 31 target tests green (17 ASS codec + 4 validate allowlist + 10 validate core); full suite clean (323 passed, no regressions)

## Task Commits

1. **Task 1: ASS/SSA codec + batching fix** - `8046bfb` (feat)
2. **Task 2: validate.py gate extension** - `57d0158` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified

- `trezarr/subtitles/ass.py` - Hand-rolled ASS/SSA codec: read_ass/write_ass, AssDoc/AssOpaqueSegment/AssDialogueSlot, KARAOKE_RE, DRAWING_RE
- `trezarr/translate/validate.py` - Added SENTINEL_ONLY_RE, raw-is-not-None guards in check 2 and _check_untranslated
- `trezarr/translate/batching.py` - Added raw-set cue skip (Rule 2 auto-fix: karaoke/drawing never sent to LLM)
- `tests/codec/test_ass_roundtrip.py` - Promoted 6 xfail stubs to real assertions
- `tests/codec/test_karaoke.py` - Promoted 2 xfail stubs; fixed batch.lines → batch.cues (Rule 1 bug fix)
- `tests/codec/test_drawing.py` - Promoted 2 xfail stubs; fixed batch.lines → batch.cues (Rule 1 bug fix)
- `tests/translate/test_validate_allowlist.py` - Promoted 4 xfail stubs to real assertions

## Decisions Made

- Section-split via `re.finditer` on `^\[` multiline pattern gives clean span boundaries for byte-identical section preservation
- Dynamic Format: column-index map approach (RESEARCH §Open Question 1 recommendation) handles both ASS and SSA variants: `text_comma_idx = len(fields) - 1` since Text is always last
- Malformed Dialogue: tracked via AssDialogueSlot with `prefix=""` so write_ass emits `"" + line_content + line_le` = original line verbatim
- Karaoke/drawing detection at `_parse_dialogue_line` sets `SubLine.raw = SubLine.text = original_text` — satisfies check 2 (non-empty text) and allows check 3 raw guard to skip it

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] batch_subdoc does not skip raw-set cues**
- **Found during:** Task 1 (ASS codec)
- **Issue:** `batch_subdoc` in `trezarr/translate/batching.py` included ALL cues in batches, including karaoke/drawing cues marked with `SubLine.raw`. The test `test_karaoke_not_in_llm_batch` and `test_drawing_run_not_in_llm_batch` verify the D-99/D-98 contract that opaque cues never reach the LLM. Without the filter, these cues would be sent to the LLM.
- **Fix:** Added `if cue.raw is not None: continue` at the top of the `batch_subdoc` for-loop. Raw-set cues are skipped entirely — they never enter any Batch.
- **Files modified:** `trezarr/translate/batching.py`
- **Verification:** `test_karaoke_not_in_llm_batch` and `test_drawing_run_not_in_llm_batch` now pass
- **Committed in:** `8046bfb`

**2. [Rule 1 - Bug] test_karaoke and test_drawing use wrong Batch attribute**
- **Found during:** Task 1 (ASS codec test execution)
- **Issue:** Both `test_karaoke_not_in_llm_batch` and `test_drawing_run_not_in_llm_batch` iterated `batch.lines` — but `Batch` has `batch.cues`. This caused `AttributeError` which was outside the xfail `raises` tuple, making these real test failures.
- **Fix:** Changed `batch.lines` to `batch.cues` in both test files.
- **Files modified:** `tests/codec/test_karaoke.py`, `tests/codec/test_drawing.py`
- **Verification:** Tests pass after fix
- **Committed in:** `8046bfb`

---

**Total deviations:** 2 auto-fixed (1 Rule 2 missing critical, 1 Rule 1 bug)
**Impact on plan:** Both fixes essential for the karaoke/drawing verbatim pass-through feature to work end-to-end. No scope creep.

## Known Stubs

None — all SubLine.text fields for translatable cues come from the parsed Dialogue Text field. No hardcoded empty values or placeholder text. Karaoke/drawing stubs use the actual original text as both `.text` and `.raw`.

## Threat Flags

No new threat surface beyond what the plan's `<threat_model>` covers. KARAOKE_RE, DRAWING_RE, and SENTINEL_ONLY_RE all follow fixed-prefix/anchored patterns with no nested quantifiers (T-09-03-A/B/C mitigated as specified). No new network endpoints, auth paths, or file-access patterns introduced.

## Issues Encountered

None — the section-split algorithm worked correctly on first implementation across all 8 ASS/SSA fixture files including BOM (utf8bom.ass), CRLF (crlf.ass), SSA variant (ssa_v4.ssa), and mixed content (mixed.ass).

## Next Phase Readiness

- `read_ass`/`write_ass` fully implemented and tested; `AssDoc` envelope populated at read time
- Ready for 09-04 (VTT codec — same envelope pattern applies)
- Ready for 09-05 (format dispatch — `read_ass`/`write_ass` now importable)
- Gate is ASS-aware: karaoke/drawing pass-through won't false-quarantine; pure-tag cues with sentinel tokens won't false-quarantine

---
*Phase: 09-multi-format-ass-ssa-vtt*
*Completed: 2026-06-02*

## Self-Check: PASSED

Files confirmed present:
- `trezarr/subtitles/ass.py` — FOUND
- `trezarr/translate/validate.py` — FOUND (modified)

Commits confirmed:
- `8046bfb` — FOUND (Task 1: ASS codec)
- `57d0158` — FOUND (Task 2: validate extension)
