---
phase: 09-multi-format-ass-ssa-vtt
plan: "05"
subsystem: subtitles-dispatch / output / engine / gap
tags: [dispatch, sidecar, format-agnostic, ASS, VTT, D-94, D-95, D-96, D-92]
requirements: [FMT-02, FMT-03, FMT-04]

dependency_graph:
  requires:
    - 09-03  # ass.py + vtt.py codecs
    - 09-04  # validate/sentinel/timecode extensions
  provides:
    - trezarr/subtitles/dispatch.py  # read_subtitle / write_subtitle routing
    - derive_vi_sidecar_path generalized to mirror source extension
    - engine.py format-agnostic read (any supported format)
    - gap.py AUTO-04 foreign-sidecar exclusion generalized to .vi.<ext>
  affects:
    - trezarr/translate/engine.py
    - trezarr/output/write.py
    - trezarr/discover/gap.py

tech_stack:
  added:
    - trezarr/subtitles/dispatch.py: suffix-keyed routing table for read_subtitle/write_subtitle
  patterns:
    - Allowlist-based dispatch dict: only .srt/.ass/.ssa/.vtt are in _READERS/_WRITERS
    - Two-stage temp-file strategy: NamedTemporaryFile(.tmp) for fs locality, with_suffix(dest.suffix) for format routing
    - Reassembly walker: interleave skipped raw cues back at original source positions

key_files:
  created:
    - trezarr/subtitles/dispatch.py
  modified:
    - trezarr/output/write.py
    - trezarr/translate/engine.py
    - trezarr/discover/gap.py
    - tests/translate/test_engine.py

decisions:
  - "Two-stage temp-file: NamedTemporaryFile(.tmp) for same-fs slot, then write to tmp.with_suffix(dest.suffix) so dispatcher routes by correct format; rename routed_tmp to dest atomically"
  - "Reassembly integrity fix: engine Step 8 now uses a queue-based walker that interleaves raw/karaoke cues at their original source positions, ensuring translated_doc.lines count == source_doc.lines count for any format with skipped cues"
  - "gap.py D-110 Phase 10 working-tree changes (check_by_output_path) were NOT included; restored to HEAD + D-96 log-message-only change"

metrics:
  duration: ~35 minutes
  completed: "2026-06-02"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 5
---

# Phase 09 Plan 05: Format Dispatcher + Integration Seams Summary

**One-liner:** Format-agnostic pipeline via read_subtitle/write_subtitle dispatcher + generalized derive_vi_sidecar_path + reassembly integrity fix for raw/karaoke cue positioning.

## Tasks Completed

| Task | Description | Commit | Status |
|------|-------------|--------|--------|
| 1 | dispatch.py + derive_vi_sidecar_path generalization (D-94, D-95) | d86ad75 | done |
| 2 | engine.py + gap.py seam wiring + reassembly fix (D-94, D-96) | 6459135 | done |

## What Was Built

### Task 1: dispatch.py + write.py (D-94, D-95, D-92)

**trezarr/subtitles/dispatch.py** — new module.

`read_subtitle(path)` and `write_subtitle(doc, path)` use suffix-keyed dicts:
```python
_READERS = {".srt": read_srt, ".ass": read_ass, ".ssa": read_ass, ".vtt": read_vtt}
_WRITERS = {".srt": write_srt, ".ass": write_ass, ".ssa": write_ass, ".vtt": write_vtt}
```
Unknown extension raises `ValueError` before any file I/O (T-09-05-A allowlist).

**trezarr/output/write.py** — 5 changes:
1. Import replaced: `write_srt` → `_dispatch_write_subtitle` from dispatch
2. `derive_vi_sidecar_path`: hardcoded `.vi.srt` → `f'.vi{suffix}'` (D-95)
3. `write_vi_sidecar` docstring updated for multi-format
4. `write_vi_sidecar` uses two-stage temp strategy: NamedTemporaryFile(.tmp) for same-filesystem slot, then writes to `tmp.with_suffix(dest.suffix)` so the dispatcher routes to the right codec, then `os.replace` to dest
5. `doc_out` carries `envelope=doc.envelope` so write codec can reconstruct ASS/VTT structure (D-92)

### Task 2: engine.py + gap.py (D-94, D-96) + reassembly integrity fix

**trezarr/translate/engine.py** — 4 changes:
1. Import: `read_srt` → `read_subtitle` from dispatch (D-94)
2. Call site: `source_doc = read_srt(path)` → `read_subtitle(path)`
3. Log message: "foreign vi.srt" → "foreign vi sidecar" (D-96)
4. Reassembly (Step 8) — CRITICAL FIX: the original code assembled `translated_lines` only from `zip(batches, batch_results)`, missing raw/karaoke cues that `batch_subdoc` skips. Fixed to use a queue walker that interleaves skipped raw cues at their original source positions, guaranteeing `len(translated_doc.lines) == len(source_doc.lines)` always.
5. `translated_doc` carries `envelope=source_doc.envelope` (D-92)
6. Pass-4 corrected_doc also carries `envelope=translated_doc.envelope`

**trezarr/discover/gap.py** — log message only: "foreign vi.srt" → "foreign vi sidecar" (D-96). Logic is already format-agnostic via `derive_vi_sidecar_path` (single seam).

**tests/translate/test_engine.py** — 2 changes:
1. Mock patch updated: `read_srt` → `read_subtitle`
2. Added `test_reassembly_preserves_raw_cues_at_original_positions`: end-to-end ASS translate_file with karaoke cue in the middle; asserts output is .vi.ass, karaoke cue is byte-identical at position 1, surrounding translated cues are in correct positions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] write_subtitle dispatching by .tmp extension**
- **Found during:** Task 1 test run
- **Issue:** `write_vi_sidecar` created a NamedTemporaryFile with `.tmp` suffix, then called `write_subtitle(doc_out, tmp_path)` — the dispatcher routed by `.tmp` which isn't in the allowlist, raising `ValueError: Unsupported subtitle format: .tmp`
- **Fix:** Two-stage temp strategy: keep `.tmp` slot for same-filesystem guarantee, create `routed_tmp = tmp_path.with_suffix(dest.suffix)` for writing so dispatcher routes correctly; `os.replace(routed_tmp, dest)`
- **Files modified:** `trezarr/output/write.py`
- **Commit:** d86ad75

**2. [Rule 1 - Bug] test_engine.py patched read_srt which no longer exists**
- **Found during:** Task 2 test run
- **Issue:** `test_translate_file_read_failure_quarantines` used `patch("trezarr.translate.engine.read_srt", ...)` — after import replacement, `read_srt` no longer exists in engine's namespace
- **Fix:** Updated patch target to `trezarr.translate.engine.read_subtitle`
- **Files modified:** `tests/translate/test_engine.py`
- **Commit:** 6459135

**3. [Rule 1 - Bug] Reassembly dropped raw/karaoke cues from translated_doc**
- **Found during:** Task 2 planning/analysis (pre-emptive fix before test failure)
- **Issue:** `batch_subdoc` skips cues with `raw is not None` — those cues don't appear in any `batch.cues` list. The original reassembly only rebuilt lines from `zip(batches, batch_results)`, producing a `translated_doc` with fewer lines than `source_doc`. For an ASS file with karaoke cues, the gate would fail on line count mismatch, and the AssDoc slot `sub_index` values would be misaligned.
- **Fix:** Queue-based reassembly walker in engine.py Step 8: flatten all translated texts from batches into a queue, then walk `source_doc.lines` — raw cues are preserved verbatim at their original index; non-raw cues pop the next translated text from the queue.
- **Files modified:** `trezarr/translate/engine.py`
- **Commit:** 6459135

**4. [Rule 3 - Blocking] gap.py had uncommitted Phase 10 D-110 changes in working tree**
- **Found during:** Task 2 full-suite run
- **Issue:** gap.py working tree had Case 1.5 / `check_by_output_path` logic (Phase 10 D-110 not yet committed). Our Edit applied on top of this, inheriting the broken code. When tests ran, `AttributeError: 'Ledger' object has no attribute 'check_by_output_path'` caused test failures.
- **Fix:** Restored gap.py to HEAD + only the D-96 log message change. Phase 10 D-110 changes are NOT part of this plan.
- **Files modified:** `trezarr/discover/gap.py`
- **Commit:** 6459135

## Verification

### Targeted Tests
```
pytest tests/codec/test_dispatch.py tests/output/test_sidecar_format.py tests/discover/test_gap_format.py -x -q
→ 1 passed, 11 xpassed (all xfail stubs promoted to GREEN)
```

### Full Suite
```
pytest tests/ -q (excluding pre-existing failure in source_selection/test_resolve.py)
→ 335 passed, 1 skipped, 6 xfailed, 36 xpassed
```

### Structural Checks
```
grep -c "read_subtitle" engine.py     → 2 ✓
grep -c "write_subtitle" write.py     → 2 ✓ (import alias + calls)
grep -c "vi\.srt" engine.py           → 0 ✓
grep -c "vi\.srt" gap.py              → 0 ✓
```

### End-to-End Reassembly Integrity
`test_reassembly_preserves_raw_cues_at_original_positions` PASSED:
- ASS source with 3 cues (normal, karaoke, normal)
- translate_file with mocked LLM returning 2 translations
- Output is `.vi.ass` (D-95 extension mirror)
- Karaoke cue at position 1 is byte-identical to source (raw preserved)
- Surrounding cues are correctly translated
- Cue count: 3 in == 3 out (no misalignment)

## Known Stubs

None. All plan objectives fully wired.

## Threat Flags

No new threat surface beyond what is documented in the plan's threat model (T-09-05-A through T-09-05-D). The allowlist dispatch, path containment, and AUTO-04 exclusion mitigations are all implemented.

## Self-Check: PASSED

Files exist:
- trezarr/subtitles/dispatch.py ✓
- trezarr/output/write.py ✓ (modified)
- trezarr/translate/engine.py ✓ (modified)
- trezarr/discover/gap.py ✓ (modified)

Commits exist:
- d86ad75 (Task 1: feat(09-05): dispatch.py + derive_vi_sidecar_path generalization)
- 6459135 (Task 2: feat(09-05): engine.py + gap.py seam wiring + reassembly integrity fix)
