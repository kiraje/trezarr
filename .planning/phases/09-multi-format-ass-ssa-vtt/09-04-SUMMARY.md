---
phase: 09-multi-format-ass-ssa-vtt
plan: "04"
subsystem: subtitles/vtt-codec
tags: [codec, vtt, byte-identity, round-trip, fmt-04]
dependency_graph:
  requires:
    - 09-02   # Wave 1 foundation: SubDoc.envelope field, tc_to_ms extension
  provides:
    - trezarr/subtitles/vtt.py (read_vtt, write_vtt, VttDoc, VttOpaqueBlock, VttCueBlock)
  affects:
    - 09-05   # dispatcher wires read_vtt/write_vtt into read_subtitle/write_subtitle
tech_stack:
  added: []
  patterns:
    - Blank-line block splitting via _SEP_RE (reused from srt.py)
    - VttDoc/VttOpaqueBlock/VttCueBlock envelope for byte-identical VTT round-trip
    - Verbatim payload slicing (position-based, not splitlines+join) for exact byte preservation
key_files:
  created:
    - trezarr/subtitles/vtt.py
  modified:
    - tests/codec/test_vtt_roundtrip.py  # promoted xfail stubs to real assertions
decisions:
  - Verbatim payload extraction via position-slicing (not splitlines+join) to preserve trailing newlines inside blocks and mixed line-ending payloads
  - trailing_sep field on VttOpaqueBlock and VttCueBlock captures the blank-line separator that follows each block; last block gets trailing_sep=""
  - _VTT_TC_SPLIT_RE extracts start/end timecodes verbatim; cue settings remain in timing_line untouched
metrics:
  duration: "~12 minutes"
  completed: "2026-06-02"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 1
---

# Phase 09 Plan 04: VTT Codec (read_vtt/write_vtt) Summary

Hand-rolled VTT codec with byte-identical round-trip for all 8 VTT fixtures; no pysubs2 on write path.

## What Was Built

`trezarr/subtitles/vtt.py` — the complete VTT codec (D-91, D-100, FMT-04).

### Key exports
- `read_vtt(path) -> SubDoc` — parses a VTT file into the pipeline-agnostic SubDoc contract with `envelope=VttDoc`
- `write_vtt(doc, path)` — reconstructs the original VTT bytes from the VttDoc envelope; only the cue payload text changes
- `VttDoc`, `VttOpaqueBlock`, `VttCueBlock` — envelope dataclasses

### Architecture

The codec follows the same "verbatim block segment list" strategy as `srt.py` and `ass.py`. VTT files are split on blank-line boundaries using `_SEP_RE` (imported strategy from srt.py). Each block is classified:

- **Block 0** (always WEBVTT header): `VttOpaqueBlock`
- **NOTE / STYLE / REGION blocks**: `VttOpaqueBlock` (never sent to LLM)
- **Cue blocks with `-->` line**: `VttCueBlock` + one `SubLine` per cue
- **Malformed blocks** (no `-->` found): `VttOpaqueBlock` + UserWarning (D-10)

The `trailing_sep` field on both block types captures the inter-block blank-line separator verbatim, enabling exact reconstruction.

### Payload extraction

Cue payload is extracted by slicing `block_text` at the character position immediately after the timing line's line ending — not via `splitlines()+join`. This preserves trailing newlines inside the final block and any mixed line-ending sequences in multi-line payloads (D-09).

### VTT cue settings

The full timing line `"HH:MM:SS.mmm --> HH:MM:SS.mmm position:50% align:center"` is stored verbatim in `VttCueBlock.timing_line`. Settings are never parsed or modified.

### Hourless timecodes

`"01:23.456"` stored verbatim in `SubLine.start_tc`/`SubLine.end_tc`. No normalisation to `HH:MM:SS.mmm` form (D-101). `tc_to_ms` extended in plan 09-02 handles the hourless pattern downstream.

## Task Results

| Task | Description | Status | Commit |
|------|-------------|--------|--------|
| 1    | vtt.py — hand-rolled VTT codec | DONE | 9949169 |

## Verification

```
pytest tests/codec/test_vtt_roundtrip.py -x -q
# 11 passed (8 parametrized byte-identity + 3 structural)

pytest tests/ -x -q
# 334 passed, 7 skipped, 21 xfailed, 11 xpassed — 0 regressions
```

All 8 VTT fixtures produce byte-identical round-trip output:
- `minimal.vtt` — basic WEBVTT header + one cue
- `cue_settings.vtt` — `position:50% align:center`, `line:90% align:start`, `size:50%` preserved
- `voices.vtt` — `<v Speaker>` inline tags in payload (stored in SubLine.text; sentinel handles downstream)
- `style_region.vtt` — STYLE block (with CSS) + REGION block preserved as VttOpaqueBlock
- `inline_timestamp.vtt` — `<00:00:02.500>` inline timestamp in payload preserved verbatim
- `hourless_tc.vtt` — `"01:23.456"` stored verbatim in SubLine.start_tc (count(":")==1 verified)
- `note_block.vtt` — NOTE block interspersed with cues preserved as VttOpaqueBlock
- `crlf.vtt` — CRLF line endings (`\r\n`) detected and preserved byte-identically

## Deviations from Plan

None — plan executed exactly as written.

The xfail stub promotion (per project convention) was included in the task commit.

## Known Stubs

None. `read_vtt` and `write_vtt` are fully wired. The dispatcher integration (`_READERS[".vtt"] = read_vtt`) is deferred to plan 09-05 as designed.

## Threat Flags

None. The codec introduces no new network endpoints, auth paths, or schema changes. The threat model in the plan (T-09-04-A through T-09-04-E) was reviewed:
- `_VTT_TIMING_RE` uses fixed string `-->` — zero ReDoS exposure (T-09-04-A accepted)
- `_SEP_RE` is the same production-tested pattern from srt.py (T-09-04-B accepted)
- STYLE block CSS emitted verbatim, never executed (T-09-04-C accepted)
- Cue identifiers stored verbatim, never executed or used as path (T-09-04-D accepted)
- Path-traversal guard is upstream in write_vi_sidecar (T-09-04-E accepted)

## Self-Check: PASSED

- [x] `trezarr/subtitles/vtt.py` exists and exports `read_vtt`, `write_vtt`, `VttDoc`, `VttOpaqueBlock`, `VttCueBlock`
- [x] Commit 9949169 exists
- [x] 11 VTT tests pass as real assertions (not xfail)
- [x] Full suite: 334 passed, 0 regressions
- [x] No pysubs2 on write path
