---
phase: 09-multi-format-ass-ssa-vtt
plan: 06
subsystem: testing
tags: [ass, ssa, vtt, libass, jassub, uat, visual-verification, pysubs2]

requires:
  - phase: 09-05
    provides: format dispatcher + pipeline wiring (engine.py / write.py) for ASS/SSA/VTT
provides:
  - Human visual UAT sign-off for Phase 9 success criterion 3 (signs render in original screen position)
  - Confirmation that positioned ASS signs ({\an8}{\pos}) and VTT cue settings (position:/line:/size:) survive translation and render correctly in a real renderer
affects: [phase-10, milestone-completion]

tech-stack:
  added: []
  patterns:
    - "Visual UAT via libass-wasm (JASSUB) browser harness — renders translated .vi.ass with the same libass engine players use, no native player install required"
    - "VTT positioning UAT via native browser <track> harness served over localhost HTTP (avoids file:// track restrictions)"

key-files:
  created: []
  modified: []

key-decisions:
  - "ASS render verified with JASSUB (libass compiled to WASM) instead of mpv — mpv was not installed and host ffmpeg lacked libass; JASSUB is the same renderer Jellyfin's web client uses, so the render is faithful with zero install"
  - "Byte-identity of positioning tags / cue settings was machine-confirmed via diff BEFORE the visual check, so the human step only had to confirm the renderer interprets the preserved bytes"

patterns-established:
  - "Pre-UAT automated gate (full pytest) must be green before the human visual check"

requirements-completed: [FMT-02, FMT-03, FMT-04]

duration: ~20min
completed: 2026-06-03
---

# Phase 9: Multi-Format ASS/SSA + VTT — Plan 06 (Visual UAT) Summary

**Human visual UAT PASSED: positioned ASS signs ({\an8}{\pos(960,50)}) and VTT cue settings (position:/line:/size:) render at their original on-screen position after translation, with only the dialogue text rendered in Vietnamese — closing the final Phase 9 gate (truth #12).**

## Performance

- **Duration:** ~20 min (walkthrough)
- **Completed:** 2026-06-03
- **Tasks:** 2 (1 automated gate + 1 human-verify checkpoint)
- **Files modified:** 0 (verification-only plan, no code produced)

## Accomplishments
- **Pre-UAT automated gate (Task 1): GREEN** — `uv run pytest tests/` → **346 passed**, 1 skipped, 3 xfailed, 43 xpassed, 1 (intentional) warning. (Up from the 343 baseline at re-verify; the +3 are the CR-02 regression test added in `3c7f5ae`.)
- **ASS positioned-sign UAT: PASS** — `pos_an8.vi.ass` rendered via JASSUB (libass-wasm). The `{\an8}{\pos(960,50)}` sign appears top-center, identical to source; dialogue translated to Vietnamese (`Ký văn bản tại đây`); override tags untranslated. Pre-confirmed by `diff`: the ONLY byte difference from source is the dialogue text.
- **VTT cue-settings UAT: PASS** — `cue_settings.vi.vtt` rendered via native browser `<track>`. All three cues (`position:50% align:center`, `line:90% align:start`, `size:50%`) render in their source positions with Vietnamese text. Pre-confirmed by `diff`: all three cue-settings strings byte-identical; only cue text differs.

## Files Created/Modified
- None — this is a verification-only plan. Output is this sign-off record + the 09-VERIFICATION.md status flip to 12/12.

## Decisions Made
- **ASS rendered with JASSUB (libass-wasm), not mpv** — mpv was not installed and the host's homebrew ffmpeg was built without libass (no `subtitles`/`ass` filter). JASSUB is libass compiled to WebAssembly — the same engine Jellyfin's web client and many players use — so the render faithfully exercises the preserved positioning tags with no install. Harness files were downloaded same-origin to sidestep cross-origin worker/wasm restrictions.
- **Machine-checked byte-identity first, human-checked rendering second** — `diff` proved the structural envelope (timecodes, `[Script Info]`/`[V4+ Styles]`, override tags, VTT cue settings, WEBVTT header) is byte-identical pre-render, so the human only had to confirm the renderer's interpretation — the part tests genuinely cannot cover.

## Deviations from Plan
None - the plan specified mpv/Jellyfin; JASSUB (libass-wasm) is a faithful, equivalent renderer substituted for tool-availability reasons (documented above). The verification target (signs render in original position) was met.

## Issues Encountered
- A minor, non-blocking observation: `cue_settings.vi.vtt` lost the trailing newline on the final cue. This is inside the translated text region, not the structural envelope, and has no rendering impact. Not a codec-fidelity violation.
- Translation-quality nuance (non-blocking, fixture-only): the placeholder `Sign text here` was rendered as `Ký văn bản tại đây` ("sign the document here") — an ambiguous-placeholder artifact, irrelevant to the positioning gate under test.

## User Setup Required
None.

## Next Phase Readiness
- **Phase 9 is COMPLETE.** All 6 plans have summaries; truth #12 verified → 12/12. Milestone v1.0 is now 10/10 phases.
- Two non-blocking advisories carried forward (do NOT block the milestone):
  - ⚠️ Add a dedicated FMT-03 regression test for the Pass-4 self-review splice over interleaved raw (karaoke/drawing) cues — self-review is enabled by default, so this guarantee is currently pinned by code review + the CR-02 test rather than a splice-with-raw-cues test.
  - ℹ️ Refresh the stale `.srt`-only docstrings in `trezarr/discover/scan.py`.
- Ready for `/gsd-verify-work` → `/gsd-complete-milestone`.

---
*Phase: 09-multi-format-ass-ssa-vtt*
*Completed: 2026-06-03*
