---
phase: 9
slug: multi-format-ass-ssa-vtt
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-02
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `09-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/subtitles/ tests/translate/test_timecode.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~20–40 seconds |

> Note: research named the new codec test dir `tests/codec/`; the existing tree uses
> `tests/subtitles/`. The planner picks the final location (Wave 0) — keep it consistent
> with the existing `tests/subtitles/test_srt*.py` placement.

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/subtitles/ tests/translate/test_timecode.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~40 seconds

---

## Per-Task Verification Map

> Requirement-keyed at plan-time; the planner maps each row to a concrete `{N}-WW-TT` task ID
> and Wave 0 RED stub. `❌ W0` = test file must be created in Wave 0 before implementation.

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| FMT-02 | ASS byte-identical round-trip (plain cue) | unit | `pytest tests/subtitles/test_ass_roundtrip.py -x` | ❌ W0 | ⬜ pending |
| FMT-02 | ASS `\N`/`\h` preserved verbatim | unit | `pytest tests/subtitles/test_ass_roundtrip.py::test_line_break_preserved -x` | ❌ W0 | ⬜ pending |
| FMT-02 | ASS `[Script Info]`/`[V4+ Styles]` headers verbatim | unit | `pytest tests/subtitles/test_ass_roundtrip.py::test_section_headers_preserved -x` | ❌ W0 | ⬜ pending |
| FMT-02 | ASS `Comment:` events verbatim (never translated) | unit | `pytest tests/subtitles/test_ass_roundtrip.py::test_comments_verbatim -x` | ❌ W0 | ⬜ pending |
| FMT-02 | SSA `.ssa` variant byte-identical round-trip | unit | `pytest tests/subtitles/test_ass_roundtrip.py::test_ssa_roundtrip -x` | ❌ W0 | ⬜ pending |
| FMT-02 | ASS drawing run NOT sent to LLM, verbatim output (D-98) | unit | `pytest tests/subtitles/test_drawing.py -x` | ❌ W0 | ⬜ pending |
| FMT-02 | Sentinel `\N`/`\h` placeholder-protected | unit | `pytest tests/translate/test_sentinel_ass_vtt.py -x` | ❌ W0 | ⬜ pending |
| FMT-02 | Gate check 5 (monotonic) works for ASS centisecond timecodes (D-101) | unit | `pytest tests/translate/test_timecode.py -x` | ❌ W0 | ⬜ pending |
| FMT-02 | Gate check 4 works with empty-string index (A2) | unit | `pytest tests/translate/test_validate_allowlist.py -x` | ❌ W0 | ⬜ pending |
| FMT-03 | Karaoke cue verbatim pass-through (not sent to LLM) | unit | `pytest tests/subtitles/test_karaoke.py -x` | ❌ W0 | ⬜ pending |
| FMT-03 | Karaoke cue allowlisted at gate (no false-quarantine, D-102) | unit | `pytest tests/translate/test_validate_allowlist.py::test_karaoke_allowlisted -x` | ❌ W0 | ⬜ pending |
| FMT-04 | VTT byte-identical round-trip (plain cue) | unit | `pytest tests/subtitles/test_vtt_roundtrip.py -x` | ❌ W0 | ⬜ pending |
| FMT-04 | VTT cue settings string preserved verbatim | unit | `pytest tests/subtitles/test_vtt_roundtrip.py::test_cue_settings_preserved -x` | ❌ W0 | ⬜ pending |
| FMT-04 | VTT STYLE/REGION/NOTE blocks verbatim | unit | `pytest tests/subtitles/test_vtt_roundtrip.py::test_blocks_verbatim -x` | ❌ W0 | ⬜ pending |
| FMT-04 | VTT `<v>`/inline `<timestamp>` protected | unit | `pytest tests/translate/test_sentinel_ass_vtt.py::test_vtt_tags -x` | ❌ W0 | ⬜ pending |
| FMT-04 | VTT hourless timecode `tc_to_ms` (D-101) | unit | `pytest tests/translate/test_timecode.py::test_vtt_hourless -x` | ❌ W0 | ⬜ pending |
| AUTO-04 | `derive_*_sidecar_path(.ass)` returns `.vi.ass` (D-95) | unit | `pytest tests/output/ -k sidecar -x` | ❌ W0 | ⬜ pending |
| AUTO-04 | foreign `.vi.ass` skipped / not re-triggered (D-96) | unit | `pytest tests/discover/ -k foreign_ass -x` | ❌ W0 | ⬜ pending |
| FMT-04 | Visual: positioned ASS/VTT cue renders in original screen position | manual | Load `.vi.ass`/`.vi.vtt` in mpv/Jellyfin; sign position matches source | human UAT |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/subtitles/test_ass_roundtrip.py` — FMT-02 byte-identity (incl. SSA, comments, headers, `\N`/`\h`)
- [ ] `tests/subtitles/test_vtt_roundtrip.py` — FMT-04 byte-identity (cue settings, STYLE/REGION/NOTE)
- [ ] `tests/subtitles/test_dispatch.py` — D-94 suffix routing (`read_subtitle`/`write_subtitle`)
- [ ] `tests/subtitles/test_karaoke.py` — FMT-03 verbatim pass-through
- [ ] `tests/subtitles/test_drawing.py` — D-98 drawing-run pass-through
- [ ] `tests/translate/test_timecode.py` — add ASS centisecond + VTT hourless cases (D-101)
- [ ] `tests/translate/test_sentinel_ass_vtt.py` — D-98/D-100 sentinel extension
- [ ] `tests/translate/test_validate_allowlist.py` — D-102 gate allowlist extension
- [ ] `tests/output/` — `derive_*_sidecar_path` extension-mirroring tests (D-95)
- [ ] `tests/discover/` — foreign `.vi.<ext>` exclusion tests (D-96, AUTO-04)
- [ ] Real-world `.ass` / `.ssa` / `.vtt` fixtures (anime ASS with `\pos`/`\an8`/`\p` drawing/`\k`; SSA variant; VTT with cue settings + `<v>` + STYLE/REGION + inline `<timestamp>`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Positioned sign renders in original screen position | FMT-04 / SC3 | Visual fidelity in a real player cannot be asserted by a byte round-trip alone | Translate a source `.ass` (with `\pos`/`\an8` sign) and a `.vtt` (with `position:`/`line:`); load the `.vi.*` sidecar in mpv and Jellyfin; confirm the sign appears at the same on-screen position as the source |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
