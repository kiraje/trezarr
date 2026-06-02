---
phase: 09-multi-format-ass-ssa-vtt
plan: "01"
subsystem: test-infrastructure
tags: [wave-0, red-scaffold, ass, vtt, fixtures, xfail]
dependency_graph:
  requires: []
  provides:
    - tests/codec/test_ass_roundtrip.py (FMT-02 byte-identity stubs)
    - tests/codec/test_vtt_roundtrip.py (FMT-04 byte-identity stubs)
    - tests/codec/test_dispatch.py (D-94 routing stubs)
    - tests/codec/test_karaoke.py (D-99/FMT-03 karaoke stubs)
    - tests/codec/test_drawing.py (D-98 drawing-run stubs)
    - tests/translate/test_timecode.py (D-101 tc_to_ms ASS+VTT stubs)
    - tests/translate/test_sentinel_ass_vtt.py (D-98/D-100 sentinel stubs)
    - tests/translate/test_validate_allowlist.py (D-102 gate allowlist stubs)
    - tests/output/test_sidecar_format.py (D-95 sidecar naming stubs)
    - tests/discover/test_gap_format.py (D-96 gap format stubs)
    - tests/fixtures/*.ass (8 ASS/SSA fixtures)
    - tests/fixtures/*.vtt (8 VTT fixtures)
  affects: []
tech_stack:
  added: []
  patterns:
    - pytest.importorskip pattern for deferred module imports (Wave 0 stubs)
    - xfail(strict=False) for extension tests where module may already handle behavior
key_files:
  created:
    - tests/codec/test_ass_roundtrip.py
    - tests/codec/test_vtt_roundtrip.py
    - tests/codec/test_dispatch.py
    - tests/codec/test_karaoke.py
    - tests/codec/test_drawing.py
    - tests/translate/test_timecode.py
    - tests/translate/test_sentinel_ass_vtt.py
    - tests/translate/test_validate_allowlist.py
    - tests/output/test_sidecar_format.py
    - tests/discover/test_gap_format.py
    - tests/fixtures/minimal.ass
    - tests/fixtures/karaoke.ass
    - tests/fixtures/drawing.ass
    - tests/fixtures/pos_an8.ass
    - tests/fixtures/mixed.ass
    - tests/fixtures/crlf.ass
    - tests/fixtures/ssa_v4.ssa
    - tests/fixtures/utf8bom.ass
    - tests/fixtures/minimal.vtt
    - tests/fixtures/cue_settings.vtt
    - tests/fixtures/voices.vtt
    - tests/fixtures/style_region.vtt
    - tests/fixtures/inline_timestamp.vtt
    - tests/fixtures/hourless_tc.vtt
    - tests/fixtures/note_block.vtt
    - tests/fixtures/crlf.vtt
  modified: []
decisions:
  - "Wave 0 xfail strategy: tests targeting not-yet-existing modules (ass.py, vtt.py, dispatch.py) use pytest.importorskip — they SKIP cleanly when the module is absent, and go GREEN when the module exists"
  - "validate_allowlist tests use xfail(strict=False) without raises= restriction because the test failure mode is pytest.fail() (a _pytest.outcomes.Failed exception), not ImportError/AssertionError — the raises= tuple would need to be broad enough to catch all failure modes"
  - "4 tests are XPASS (already handled by existing code): test_vtt_with_explicit_zero_hours (current _TC_PARSE_RE with [,.] covers HH:MM:SS.mmm), test_vtt_voice_tag and test_vtt_inline_timestamp (existing TAG_RE <[^>]+> already covers these), test_check2_skips_raw_lines (check 2 naturally passes for raw-set SubLine with non-empty text)"
  - "SRT regression guard (test_sidecar_naming_srt_unchanged) passes GREEN — derive_vi_sidecar_path already handles SRT correctly"
metrics:
  duration: "8 minutes"
  completed: "2026-06-02"
  tasks: 2
  files: 26
---

# Phase 09 Plan 01: Wave 0 RED Scaffold — ASS/SSA/VTT Fixtures and Test Stubs

**One-liner:** 16 real-world ASS/SSA/VTT fixture files and 10 Wave-0 xfail test stubs covering FMT-02/03/04, D-94 through D-102, with SRT regression guards passing GREEN.

## What Was Built

### Task 1: 16 Fixture Files in tests/fixtures/

**ASS fixtures (8 files):**
- `minimal.ass` — baseline [Script Info]/[V4+ Styles]/[Events] with one plain Dialogue
- `karaoke.ass` — Dialogue Text with `{\k50}syl{\k60}la{\k70}ble` karaoke tags (FMT-03)
- `drawing.ass` — Dialogue Text with `{\p1}m 0 0 l 100 0 100 100 0 100{\p0}` vector commands (D-98)
- `pos_an8.ass` — Dialogue Text with `{\an8}{\pos(960,50)}` positioning tags
- `mixed.ass` — Integration fixture: Comment: event, multiple Styles, `\N` hard-break, karaoke, drawing, normal Dialogue
- `crlf.ass` — CRLF line endings throughout (Pitfall 8 regression guard)
- `ssa_v4.ssa` — [V4 Styles] (no plus), `Marked=0` field format (SSA variant)
- `utf8bom.ass` — UTF-8 with BOM prefix `\xef\xbb\xbf`

**VTT fixtures (8 files):**
- `minimal.vtt` — WEBVTT header + one simple cue
- `cue_settings.vtt` — Cues with `position:50% align:center`, `line:90% align:start`, `size:50%`
- `voices.vtt` — Cues with `<v Alice>` / `<v Bob>` voice annotation tags (D-100)
- `style_region.vtt` — STYLE block (CSS) + REGION block before first cue (FMT-04)
- `inline_timestamp.vtt` — Cue payload with `<00:00:02.500>` inline timestamp (D-100)
- `hourless_tc.vtt` — Cues with `01:23.456 --> 01:25.000` hourless MM:SS.mmm timecodes (D-101)
- `note_block.vtt` — NOTE block interspersed between cues (FMT-04)
- `crlf.vtt` — CRLF line endings throughout

### Task 2: 10 Wave 0 RED Test Files

**tests/codec/ (5 new files):**
- `test_ass_roundtrip.py` — 6 xfail stubs: byte-identical roundtrip (parametrized over 8 ASS fixtures), `\N` break preserved, section headers verbatim, Comment: events verbatim, SSA roundtrip, malformed Dialogue preserved+flagged
- `test_vtt_roundtrip.py` — 4 xfail stubs: byte-identical roundtrip (parametrized over 8 VTT fixtures), cue settings preserved, STYLE/REGION/NOTE blocks verbatim, hourless timecode roundtrip
- `test_dispatch.py` — 6 xfail stubs: .srt/.ass/.ssa/.vtt routing, unknown suffix ValueError, write routing
- `test_karaoke.py` — 2 xfail stubs: karaoke SubLine.raw set + karaoke not in LLM batch
- `test_drawing.py` — 2 xfail stubs: drawing SubLine.raw set + drawing not in LLM batch

**tests/translate/ (3 new files):**
- `test_timecode.py` — 4 GREEN SRT assertions + 3 xfail ASS/VTT extension cases (1 xpassed for HH:MM:SS.mmm which existing regex already handles)
- `test_sentinel_ass_vtt.py` — 5 xfail stubs: `\N`/`\n`/`\h` ASS breaks + VTT voice/inline-timestamp (2 xpassed — existing TAG_RE already covers `<[^>]+>`)
- `test_validate_allowlist.py` — 4 xfail stubs: karaoke/drawing/pure-tag allowlist + check2 skip (1 xpassed — check 2 naturally passes for non-empty raw text)

**tests/output/ (1 new file):**
- `test_sidecar_format.py` — 3 xfail stubs for .vi.ass/.vi.ssa/.vi.vtt + 1 GREEN SRT regression guard

**tests/discover/ (1 new file):**
- `test_gap_format.py` — 2 xfail stubs: foreign .vi.ass and .vi.vtt exclusion (AUTO-04)

## Test Status Summary

```
tests/codec/ tests/translate/test_timecode.py tests/translate/test_sentinel_ass_vtt.py
tests/translate/test_validate_allowlist.py tests/output/test_sidecar_format.py
tests/discover/test_gap_format.py:

18 passed, 34 skipped, 14 xfailed, 4 xpassed in 0.15s
```

- **18 passed**: SRT roundtrip (existing), SRT timecode assertions (GREEN), SRT sidecar regression guard (GREEN)
- **34 skipped**: New codec tests skip via `pytest.importorskip` (trezarr.subtitles.ass/vtt/dispatch absent)
- **14 xfailed**: ASS centisecond timecode tests, validate allowlist tests (expected failures — implementation pending)
- **4 xpassed**: Tests we marked xfail that already work with existing code (existing TAG_RE handles VTT tags; existing _TC_PARSE_RE handles HH:MM:SS.mmm with period; check 2 naturally passes for non-empty raw SubLine)
- **0 collection ERRORs**: All test files collect cleanly

**Existing suite:** 297 passed, 1 skipped — no regressions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] xfail raises= tuple too narrow for test_validate_allowlist.py**
- **Found during:** Task 2 verification
- **Issue:** Tests using `pytest.fail(...)` inside a `try/except GateError` block raise `_pytest.outcomes.Failed`, not `AssertionError`. The `raises=(ImportError, AssertionError, TypeError)` tuple on xfail didn't cover this, causing the tests to show as FAILED instead of xfail.
- **Fix:** Removed the `raises=` restriction from the 4 test_validate_allowlist.py xfail marks — `strict=False` without `raises=` correctly handles all failure modes.
- **Files modified:** tests/translate/test_validate_allowlist.py
- **Commit:** 3669a3d

## Known Stubs

All stub tests are intentionally non-implemented — they are Wave 0 placeholders:
- `tests/codec/test_ass_roundtrip.py` — waits for Wave 2 `trezarr/subtitles/ass.py`
- `tests/codec/test_vtt_roundtrip.py` — waits for Wave 2 `trezarr/subtitles/vtt.py`
- `tests/codec/test_dispatch.py` — waits for Wave 3 `trezarr/subtitles/dispatch.py`
- `tests/codec/test_karaoke.py` — waits for Wave 2 ass.py
- `tests/codec/test_drawing.py` — waits for Wave 2 ass.py
- `tests/translate/test_sentinel_ass_vtt.py::test_extract_ass_hard_break/lowercase_n/h` — waits for Wave 1 sentinel extension
- `tests/translate/test_validate_allowlist.py::test_karaoke/drawing/pure_tag_cue_allowlisted` — waits for Wave 1 validate extension
- `tests/output/test_sidecar_format.py::test_sidecar_naming_ass/ssa/vtt` — waits for Wave 3 derive_vi_sidecar_path generalization
- `tests/discover/test_gap_format.py::test_foreign_vi_ass/vtt_excluded` — waits for Wave 3 is_eligible generalization

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced. Fixtures are hand-authored synthetic files with no external downloads.

## Self-Check: PASSED

Files exist:
- tests/codec/test_ass_roundtrip.py: FOUND
- tests/codec/test_vtt_roundtrip.py: FOUND
- tests/codec/test_dispatch.py: FOUND
- tests/codec/test_karaoke.py: FOUND
- tests/codec/test_drawing.py: FOUND
- tests/translate/test_timecode.py: FOUND
- tests/translate/test_sentinel_ass_vtt.py: FOUND
- tests/translate/test_validate_allowlist.py: FOUND
- tests/output/test_sidecar_format.py: FOUND
- tests/discover/test_gap_format.py: FOUND
- All 16 fixture files: FOUND (verified by Python assertion script)

Commits exist:
- da846b4: chore(09-01): create 16 ASS/SSA/VTT fixture files — FOUND
- 3669a3d: test(09-01): add Wave 0 RED test stubs — FOUND
