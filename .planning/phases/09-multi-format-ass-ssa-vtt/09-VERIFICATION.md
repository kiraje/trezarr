---
phase: 09-multi-format-ass-ssa-vtt
verified: 2026-06-02T00:00:00Z
status: gaps_found
score: 8/12 must-haves verified
overrides_applied: 0
gaps:
  - truth: "write_ass/write_vtt always write UTF-8 output regardless of source encoding (D-19 / FMT-05 output-UTF-8 contract)"
    status: failed
    reason: "CR-01: write_ass uses ass_doc.encoding and write_vtt uses vtt_doc.encoding (captured from source at read time). doc.encoding='utf-8' set by write_vi_sidecar is silently ignored. A Latin-1 or UTF-16LE source .ass/.vtt produces a non-UTF-8 vi sidecar."
    artifacts:
      - path: "trezarr/subtitles/ass.py"
        issue: "Line 215: result.encode(ass_doc.encoding) reads envelope encoding, not doc.encoding"
      - path: "trezarr/subtitles/vtt.py"
        issue: "Line 218: result.encode(vtt_doc.encoding) reads envelope encoding, not doc.encoding"
    missing:
      - "ass.py write_ass: use doc.encoding instead of ass_doc.encoding when encoding the result"
      - "vtt.py write_vtt: use doc.encoding instead of vtt_doc.encoding when encoding the result"

  - truth: "Karaoke (\\k) lines round-trip without corruption when Pass-4 self-review is enabled and the source file has karaoke/drawing cues (FMT-03)"
    status: failed
    reason: "CR-02: Pass-4 splice in engine.py (lines 1001-1016) uses offset+=len(rb.cues) where rb.cues excludes raw-flagged (karaoke/drawing) cues. corrected_lines[offset+i] then overwrites karaoke/drawing pass-through slots with translated text and misaligns all subsequent cues. Self-review is disabled by default but is a documented pipeline feature; when enabled with an ASS file containing karaoke or drawing cues, the karaoke verbatim guarantee (FMT-03) is violated."
    artifacts:
      - path: "trezarr/translate/engine.py"
        issue: "Lines 1001-1016: splice loop increments offset by len(rb.cues) which excludes raw-cue slots, misaligning all writes after any raw cue"
    missing:
      - "engine.py: replace the splice loop with a doc-level pointer that skips raw-cue slots, mirroring the queue-based assembly approach at lines 879-899 (see REVIEW.md CR-02 fix)"

  - truth: "Trezarr handles ASS/SSA and VTT in production — a real operator with .en.ass or .en.vtt source subtitles sees them discovered and queued for translation (phase goal reachability)"
    status: failed
    reason: "WR-01: scan.py find_source_sub globs only {stem}.*.srt (line 167). The dispatch table in dispatch.py is correct, but no .ass, .ssa, or .vtt source file is ever discovered. An operator who has ASS/VTT source subtitles sees zero eligible items despite Phase 9 being nominally in place. The codecs exist but are unreachable in production."
    artifacts:
      - path: "trezarr/discover/scan.py"
        issue: "Line 167: glob f'{escaped_stem}.*.srt' — hard-coded .srt suffix excludes .ass/.ssa/.vtt sources"
      - path: "trezarr/discover/scan.py"
        issue: "Line 45: _LANG_SIDECAR_RE = re.compile(r'^(.+?)\\.([a-z]{2,3})\\.srt$') — regex also hard-coded to .srt"
    missing:
      - "scan.py: extend find_source_sub to glob all supported suffixes (.srt, .ass, .ssa, .vtt) and broaden _LANG_SIDECAR_RE to match all extensions"

human_verification:
  - test: "Visual UAT: Positioned sign renders at correct screen position in mpv/Jellyfin after translation"
    expected: "A .vi.ass sidecar produced from pos_an8.ass (contains {\\an8}{\\pos(960,50)} cues) renders the positioned sign at the SAME screen position as the source .ass when loaded in mpv or Jellyfin alongside any video of the right resolution"
    why_human: "Unit tests verify byte-identity of the timing_line and tag bytes. Only a real media player test confirms that a player's renderer correctly interprets the preserved positioning tags in the translated output."
  - test: "Visual UAT: VTT cue-settings positioning preserved in browser or VTT player"
    expected: "A .vi.vtt sidecar produced from cue_settings.vtt renders cues with position:/line: settings at the correct screen position. Text-editor inspection of the .vi.vtt output confirms the timing line still contains the verbatim cue-settings string (e.g. '00:00:01.000 --> 00:00:03.000 position:50% align:center')."
    why_human: "VTT cue settings are preserved verbatim in VttCueBlock.timing_line and tests confirm byte-identity. Player rendering of the CSS-based VTT positioning requires a real browser or player environment."
---

# Phase 9: Multi-Format ASS/SSA + VTT Verification Report

**Phase Goal:** Trezarr handles ASS/SSA and VTT in addition to SRT, translating only dialogue text while leaving override tags, fonts, positioning, karaoke timing, headers, and cue settings byte-identical.
**Verified:** 2026-06-02T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ASS/SSA codec (read_ass/write_ass) exists with hand-rolled byte-identity strategy | VERIFIED | trezarr/subtitles/ass.py: AssDoc/AssOpaqueSegment/AssDialogueSlot present; read_ass + write_ass implemented |
| 2 | VTT codec (read_vtt/write_vtt) exists with hand-rolled byte-identity strategy | VERIFIED | trezarr/subtitles/vtt.py: VttDoc/VttOpaqueBlock/VttCueBlock present; read_vtt + write_vtt implemented |
| 3 | Override tags, drawing commands, Comment: events, [Script Info]/[V4+ Styles] headers preserved byte-identical via AssOpaqueSegment | VERIFIED | ass.py _parse_events_section: Comment:, Format: and all non-Dialogue lines → AssOpaqueSegment; non-Events sections → AssOpaqueSegment |
| 4 | Karaoke (\\k/\\kf/\\ko/\\K/\\kt) lines set SubLine.raw = text — never sent to LLM batch | VERIFIED | ass.py line 379: KARAOKE_RE.search triggers raw=text assignment; validate.py check 2 and check 3 skip raw-is-not-None lines |
| 5 | Drawing-run cues ({\p1}…) set SubLine.raw = text — never sent to LLM batch | VERIFIED | ass.py line 379: DRAWING_RE.search triggers raw=text; same gate guards |
| 6 | VTT cue settings (position:, line:, align:) preserved verbatim in VttCueBlock.timing_line | VERIFIED | vtt.py VttCueBlock.timing_line stores full verbatim timing line; write_vtt emits timing_line + le unchanged |
| 7 | NOTE/STYLE/REGION blocks preserved verbatim as VttOpaqueBlock | VERIFIED | vtt.py _parse_vtt_block: NOTE/STYLE/REGION → VttOpaqueBlock verbatim |
| 8 | Format dispatcher routes .ass/.ssa→read_ass/write_ass, .vtt→read_vtt/write_vtt, .srt unchanged | VERIFIED | dispatch.py: _READERS/_WRITERS dicts correctly keyed; read_subtitle/write_subtitle wired; engine.py imports read_subtitle; write.py uses write_subtitle |
| 9 | write_ass/write_vtt always output UTF-8 regardless of source encoding (D-19 / FMT-05) | FAILED | CR-01: ass.py L215 encodes with ass_doc.encoding; vtt.py L218 encodes with vtt_doc.encoding. doc.encoding='utf-8' override from write_vi_sidecar is silently dropped. Round-trip tests pass only because all fixtures are UTF-8. |
| 10 | Karaoke lines round-trip without corruption when Pass-4 self-review is enabled | FAILED | CR-02: engine.py L1001-1016 splice loop uses offset+=len(rb.cues). rb.cues excludes raw (karaoke/drawing) cues. corrected_lines[offset+i] overwrites karaoke/drawing slots and misaligns translations for all subsequent cues when raw cues are present in the file. |
| 11 | ASS/VTT source subtitles are discoverable in production — operator sees eligible items | FAILED | WR-01: scan.py L167 globs only *.srt. _LANG_SIDECAR_RE (L45) only matches .srt. No .ass, .ssa, or .vtt source is ever found by find_source_sub. All Phase 9 codecs are unreachable in a real deployment. |
| 12 | Signs render in their original screen position in a media player (FMT-04 SC-3 / FMT-02 SC-3) | UNCERTAIN (human needed) | Byte-identity of positioning tags is verified by codec structure. Player rendering requires human visual UAT (09-06-PLAN.md task 2). |

**Score:** 8/12 truths verified (3 FAILED blockers, 1 UNCERTAIN pending human UAT)

---

### Gaps Summary

Three blockers prevent the phase goal from being achieved:

**Gap 1 — CR-01 (UTF-8 output contract):** `write_ass` and `write_vtt` use the envelope's encoding captured from the source file rather than `doc.encoding`. `write_vi_sidecar` sets `doc_out.encoding='utf-8'` to force D-19 compliance, but both codecs read `ass_doc.encoding`/`vtt_doc.encoding` instead. A non-UTF-8 source (Latin-1 .ass, UTF-16LE .vtt) produces a non-UTF-8 sidecar. Tests pass only because all fixtures are UTF-8. Fix: change both write functions to use `doc.encoding` directly.

**Gap 2 — CR-02 (Pass-4 karaoke corruption):** The Pass-4 self-review splice at engine.py lines 1001-1016 increments `offset` by `len(rb.cues)`. But `batch_subdoc` skips raw-flagged (karaoke/drawing) cues, so `rb.cues` is shorter than the corresponding span of `corrected_lines`. The splice then overwrites karaoke/drawing pass-through slots with translated text and shifts all subsequent corrections by one position. This directly violates FMT-03. Fix: use a doc-level pointer that skips raw-cue slots when iterating corrected_lines (see REVIEW.md CR-02 for the exact fix).

**Gap 3 — WR-01 (ASS/VTT source discovery):** `find_source_sub` in scan.py globs only `{stem}.*.srt` and `_LANG_SIDECAR_RE` matches only `.srt` filenames. The entire Phase 9 codec stack — dispatch, read_ass, read_vtt — is dead code in production because no ASS or VTT source subtitle is ever discovered. An operator with `.en.ass` source files sees zero eligible items. Fix: extend `find_source_sub` to glob all supported extensions and broaden `_LANG_SIDECAR_RE`.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/subtitles/ass.py` | Hand-rolled ASS/SSA codec | VERIFIED | Exports read_ass, write_ass, AssDoc, AssOpaqueSegment, AssDialogueSlot |
| `trezarr/subtitles/vtt.py` | Hand-rolled VTT codec | VERIFIED | Exports read_vtt, write_vtt, VttDoc, VttOpaqueBlock, VttCueBlock |
| `trezarr/subtitles/dispatch.py` | Format dispatcher | VERIFIED | read_subtitle/write_subtitle routing all four extensions; wired in engine.py and write.py |
| `trezarr/subtitles/model.py` | SubDoc.envelope field | VERIFIED | envelope: object = None present at end of SubDoc dataclass (L87) |
| `trezarr/translate/_timecode.py` | Extended tc_to_ms for ASS+VTT | VERIFIED | _ASS_TC_RE, _VTT_HOURS_TC_RE, _VTT_HOURLESS_TC_RE present; cascaded match in correct order |
| `trezarr/translate/sentinel.py` | TAG_RE with \\N/\\n/\\h arm | VERIFIED | TAG_RE = re.compile(r'(<[^>]+>|{\\[^}]+}|\\[Nnh])') at L19 |
| `trezarr/translate/validate.py` | SENTINEL_ONLY_RE + raw-is-not-None guards | VERIFIED | SENTINEL_ONLY_RE at L45; raw guard in check 2 (L218) and check 3 (L96) |
| `trezarr/output/write.py` | derive_vi_sidecar_path uses f'.vi{suffix}' | VERIFIED | L91-95: suffix = media_path.suffix.lower(); returns stem + f'.vi{suffix}'; envelope=doc.envelope carried at L149 |
| `trezarr/discover/gap.py` | AUTO-04 generalized to .vi.<ext> | VERIFIED | is_eligible uses derive_vi_sidecar_path which mirrors source extension; "foreign vi sidecar" log string |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| engine.py | dispatch.py | read_subtitle call (L693) | WIRED | engine.py L46 imports read_subtitle from dispatch; L693 calls read_subtitle(path) |
| write.py | dispatch.py | write_subtitle call (L151) | WIRED | write.py L44 imports write_subtitle as _dispatch_write_subtitle; L151 calls it |
| engine.py translated_doc | write_vi_sidecar | envelope=source_doc.envelope (L921) | WIRED | engine.py L921 sets envelope=source_doc.envelope in translated_doc SubDoc constructor |
| write_vi_sidecar doc_out | write_subtitle | envelope=doc.envelope (L149) | WIRED | write.py L149 carries envelope=doc.envelope into doc_out |
| write_ass / write_vtt | doc.encoding | UTF-8 override from doc_out | NOT WIRED (CR-01) | Both codecs read ass_doc.encoding/vtt_doc.encoding from the envelope, not doc.encoding |
| gap.py | write.py | derive_vi_sidecar_path | WIRED | gap.py L36 imports derive_vi_sidecar_path; L112 calls it |
| engine.py Pass-4 splice | translated_doc (raw slots) | corrected_lines[offset+i] | NOT WIRED (CR-02) | Splice index arithmetic doesn't account for raw-cue slots in corrected_lines |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| write_ass output encoding | ass_doc.encoding | AssDoc captured from source at read time | No — D-19 override (doc.encoding='utf-8') is ignored | HOLLOW — correct value exists in doc.encoding but wrong field is read |
| write_vtt output encoding | vtt_doc.encoding | VttDoc captured from source at read time | No — same issue | HOLLOW |
| Pass-4 corrected_lines[offset+i] | rb.cues (non-raw only) | translated_doc.lines (ALL cues including raw) | No — index mismatch when raw cues present | HOLLOW |
| find_source_sub candidates | glob f'{stem}.*.srt' | filesystem | No .ass/.vtt files returned | DISCONNECTED |

---

### Behavioral Spot-Checks

Step 7b: SKIPPED for production pipeline invocation (requires running server + LLM endpoint). Codec-level spot-checks performed via code inspection.

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| write_ass uses source encoding for non-UTF-8 input | ass.py L215: result.encode(ass_doc.encoding) — ass_doc.encoding comes from detect_encoding(source_bytes) | Confirmed: ass_doc.encoding is NOT overridden to 'utf-8' | FAIL (CR-01) |
| write_vtt same issue | vtt.py L218: result.encode(vtt_doc.encoding) | Confirmed: vtt_doc.encoding is NOT overridden to 'utf-8' | FAIL (CR-01) |
| engine.py Pass-4 splice accounts for raw cues | L1003-1016: offset += len(rb.cues); corrected_lines[offset+i] | rb.cues excludes raw cues; corrected_lines includes them — misalignment confirmed | FAIL (CR-02) |
| find_source_sub discovers .ass/.vtt sources | scan.py L167: glob f'{escaped_stem}.*.srt' | Glob hard-coded to .srt — confirmed | FAIL (WR-01) |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| FMT-02 | 09-01, 09-03, 09-05 | ASS/SSA: translate dialogue text only; override tags, drawing commands, headers byte-identical | PARTIAL | Codec structure is correct and byte-identity is achieved for UTF-8 sources. Blocked by CR-01 (non-UTF-8 output for non-UTF-8 sources) and WR-01 (ASS sources never discovered in production). |
| FMT-03 | 09-01, 09-03, 09-05 | Karaoke (\\k) lines preserved verbatim without corruption | PARTIAL | read_ass correctly sets raw=text for karaoke cues; validate.py gate guards correct. Blocked by CR-02: Pass-4 self-review splice corrupts karaoke slots when self-review is enabled. |
| FMT-04 | 09-01, 09-04, 09-05 | VTT parses/writes round-tripping cue settings/positioning | PARTIAL | Codec structure correct; timing_line preserved verbatim; VttOpaqueBlock for NOTE/STYLE/REGION. Blocked by CR-01 (non-UTF-8 output) and WR-01 (VTT sources never discovered). SC-3 (player rendering) pending human UAT. |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| trezarr/subtitles/ass.py | 215 | `result.encode(ass_doc.encoding)` — reads envelope field instead of doc.encoding | BLOCKER | Non-UTF-8 ASS sources produce non-UTF-8 vi sidecars; violates D-19 / FMT-05 |
| trezarr/subtitles/vtt.py | 218 | `result.encode(vtt_doc.encoding)` — same pattern | BLOCKER | Non-UTF-8 VTT sources produce non-UTF-8 vi sidecars; violates D-19 / FMT-05 |
| trezarr/translate/engine.py | 1003-1016 | `corrected_lines[offset + i]` with `offset += len(rb.cues)` — rb.cues excludes raw cues but corrected_lines includes them | BLOCKER | Karaoke/drawing pass-through cues overwritten by translated text when self-review is on; FMT-03 violated |
| trezarr/discover/scan.py | 167 | `glob(f"{escaped_stem}.*.srt")` — hard-coded .srt suffix | BLOCKER | ASS/VTT sources never discovered; entire Phase 9 codec stack unreachable in production |
| trezarr/discover/scan.py | 45 | `_LANG_SIDECAR_RE = re.compile(r'^(.+?)\.([a-z]{2,3})\.srt$')` — .srt only | BLOCKER | Companion to L167 — pattern must also be extended |

No unreferenced TBD/FIXME/XXX debt markers found in phase-modified files.

---

### Human Verification Required

#### 1. Positioned sign rendering in ASS

**Test:** Produce a `.vi.ass` sidecar from the `pos_an8.ass` fixture (contains `{\an8}{\pos(960,50)}` cues) by running the translation pipeline. Load the sidecar alongside any video of the right resolution in mpv:
`mpv <video-file> --sub-file=<path-to.vi.ass>`

**Expected:** The positioned sign cue (`{\an8}{\pos(...)}`) appears at the **same screen position** as in the source `.ass` file — top-center for `{\an8}`, or at exact x,y coordinates for `{\pos}`.

**Why human:** Unit tests verify byte-identity of override tag bytes in the output. Only a real player test confirms that the player's renderer correctly interprets the preserved positioning override tags after translation.

#### 2. VTT cue-settings positioning in browser/player

**Test:** Produce a `.vi.vtt` sidecar from the `cue_settings.vtt` fixture. First, text-editor inspection: confirm the timing line still contains the verbatim cue-settings string (e.g., `00:00:01.000 --> 00:00:03.000 position:50% align:center`). Then load in a browser's `<track>` element or a VTT-capable player and confirm cues render at the specified screen position.

**Expected:** (1) Timing line in `.vi.vtt` is byte-identical to source for settings portion. (2) Cue renders at the CSS-specified position in a real player.

**Why human:** VTT cue settings are preserved in `VttCueBlock.timing_line` and structural byte-identity is confirmed by tests. Player rendering of `position:`/`line:` settings via CSS depends on the player's VTT renderer — requires a real browser or player environment.

---

## Verdict

**Status: gaps_found**

Phase 9 delivers a structurally sound codec stack. The byte-identity strategy (envelope + opaque segments), karaoke/drawing detection, VTT block categorization, dispatch table, sidecar-path generalization, and gate extensions are all correctly implemented. The test suite covering these structural behaviors is green.

However three blockers prevent the phase goal from being achieved:

1. **CR-01** (BLOCKER): `write_ass`/`write_vtt` ignore the D-19 UTF-8 override — non-UTF-8 sources produce non-UTF-8 sidecars.
2. **CR-02** (BLOCKER): Pass-4 splice in `engine.py` misaligns when raw (karaoke/drawing) cues are present — FMT-03 violated when self-review is enabled.
3. **WR-01** (BLOCKER): `scan.py find_source_sub` globs only `.srt` — ASS/VTT sources are never discovered in production; the entire Phase 9 codec stack is unreachable.

Additionally, visual UAT (SC-3: signs render at correct screen position) has not been performed and is required as a human-needed item regardless of the above blockers.

---

_Verified: 2026-06-02T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Depth: standard_
