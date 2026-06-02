---
phase: 09-multi-format-ass-ssa-vtt
verified: 2026-06-02T00:00:00Z
status: human_needed
score: 11/12 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 8/12
  fix_commit: 4052d90
  gaps_closed:
    - "CR-01: write_ass/write_vtt now encode with doc.encoding (UTF-8 on the vi-sidecar path), honoring the D-19/FMT-05 UTF-8 output contract"
    - "CR-02: Pass-4 self-review splice rewritten to walk the full doc and advance the correction pointer only on non-raw cues — karaoke/drawing pass-through slots no longer overwritten/misaligned (FMT-03)"
    - "WR-01: scan.py source discovery broadened to .srt/.ass/.ssa/.vtt via _SOURCE_SUFFIXES + _glob_source_sidecars, used by both find_source_sub and select_source_for_item — ASS/SSA/VTT sources now discoverable in production"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Visual UAT: Positioned sign renders at correct screen position in mpv/Jellyfin after translation"
    expected: "A .vi.ass sidecar produced from pos_an8.ass (contains {\\an8}{\\pos(960,50)} cues) renders the positioned sign at the SAME screen position as the source .ass when loaded in mpv or Jellyfin alongside any video of the right resolution"
    why_human: "Unit tests verify byte-identity of the timing_line and tag bytes. Only a real media player test confirms that a player's renderer correctly interprets the preserved positioning tags in the translated output. Artifacts were staged at /tmp/trezarr_uat/ (09-06-PLAN.md task 2) but player rendering needs a human."
  - test: "Visual UAT: VTT cue-settings positioning preserved in browser or VTT player"
    expected: "A .vi.vtt sidecar produced from cue_settings.vtt renders cues with position:/line: settings at the correct screen position. Text-editor inspection of the .vi.vtt output confirms the timing line still contains the verbatim cue-settings string (e.g. '00:00:01.000 --> 00:00:03.000 position:50% align:center')."
    why_human: "VTT cue settings are preserved verbatim in VttCueBlock.timing_line and tests confirm byte-identity. Player rendering of the CSS-based VTT positioning requires a real browser or player environment."
---

# Phase 9: Multi-Format ASS/SSA + VTT Verification Report

**Phase Goal:** Trezarr handles ASS/SSA and VTT in addition to SRT, translating only dialogue text while leaving override tags, fonts, positioning, karaoke timing, headers, and cue settings byte-identical.
**Verified:** 2026-06-02T00:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (commit 4052d90 "fix(09): resolve verification blockers CR-01, CR-02, WR-01")

---

## Re-Verification Summary

The initial verification (8/12, gaps_found) raised 3 code BLOCKERS (CR-01, CR-02, WR-01) and 1 UNCERTAIN (truth #12, visual UAT). Commit **4052d90** fixed all three code blockers. This re-verification confirms — against the current code on `main`, not the SUMMARY narrative — that **all 3 code blockers are genuinely RESOLVED**. The only remaining item is the human visual UAT (truth #12), which by its nature cannot be verified programmatically.

**New score: 11/12 truths verified. All CODE blockers are cleared. Status is `human_needed` because the sole remaining item is human visual UAT — no code gaps remain.**

Test suite: `uv run pytest -q` → **343 passed**, 1 skipped, 3 xfailed, 43 xpassed, 1 warning (the warning is an intentional malformed-SRT preservation path in an unrelated integration test). Matches the expected 343-pass baseline.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ASS/SSA codec (read_ass/write_ass) exists with hand-rolled byte-identity strategy | ✓ VERIFIED | trezarr/subtitles/ass.py: AssDoc/AssOpaqueSegment/AssDialogueSlot present; read_ass + write_ass implemented |
| 2 | VTT codec (read_vtt/write_vtt) exists with hand-rolled byte-identity strategy | ✓ VERIFIED | trezarr/subtitles/vtt.py: VttDoc/VttOpaqueBlock/VttCueBlock present; read_vtt + write_vtt implemented |
| 3 | Override tags, drawing commands, Comment: events, headers preserved byte-identical via AssOpaqueSegment | ✓ VERIFIED | ass.py _parse_events_section: Comment:/Format:/non-Dialogue → AssOpaqueSegment; non-Events sections → AssOpaqueSegment |
| 4 | Karaoke (\\k/\\kf/\\ko/\\K/\\kt) lines set SubLine.raw = text — never sent to LLM batch | ✓ VERIFIED | ass.py KARAOKE_RE triggers raw=text; batch_subdoc skips raw cues (batching.py L146-147); validate.py raw guards |
| 5 | Drawing-run cues ({\\p1}…) set SubLine.raw = text — never sent to LLM batch | ✓ VERIFIED | ass.py DRAWING_RE triggers raw=text; same batch/gate guards |
| 6 | VTT cue settings (position:, line:, align:) preserved verbatim in VttCueBlock.timing_line | ✓ VERIFIED | vtt.py VttCueBlock.timing_line stores full verbatim timing line; write_vtt emits timing_line + le unchanged |
| 7 | NOTE/STYLE/REGION blocks preserved verbatim as VttOpaqueBlock | ✓ VERIFIED | vtt.py _parse_vtt_block: NOTE/STYLE/REGION → VttOpaqueBlock verbatim |
| 8 | Format dispatcher routes .ass/.ssa→read_ass/write_ass, .vtt→read_vtt/write_vtt, .srt unchanged | ✓ VERIFIED | dispatch.py _READERS/_WRITERS map all four extensions (.ssa shares the ASS codec); wired in engine.py + write.py |
| 9 | write_ass/write_vtt always write UTF-8 output regardless of source encoding (D-19 / FMT-05) | ✓ VERIFIED (was FAILED) | **CR-01 RESOLVED.** ass.py L220 `result.encode(doc.encoding)`; vtt.py L223 `result.encode(doc.encoding)`. read_* set SubDoc.encoding == envelope.encoding (ass.py L135/138, L176/179; vtt.py L168/171) so round-trip byte-identity is unchanged. write_vi_sidecar builds doc_out with encoding='utf-8' (write.py L144). New test tests/codec/test_encoding_contract.py pins the non-latin-1 case (would raise UnicodeEncodeError pre-fix). |
| 10 | Karaoke lines round-trip without corruption when Pass-4 self-review is enabled (FMT-03) | ✓ VERIFIED (was FAILED) | **CR-02 RESOLVED.** engine.py L1012-1043: the splice now flattens corrections to one entry per non-raw cue, then walks ALL of translated_doc.lines and advances `_corr_iter` ONLY on non-raw cues (raw cues are appended verbatim before any `next()`). This exactly mirrors batch_subdoc's raw-skip contract (batching.py L146-147). The old `corrected_lines[offset+i]` misalignment is gone. Envelope is carried forward (engine.py L1052). Verified by inspection — see WARNING re: missing dedicated regression test. |
| 11 | ASS/VTT source subtitles are discoverable in production — operator sees eligible items | ✓ VERIFIED (was FAILED) | **WR-01 RESOLVED.** scan.py L43 `_SOURCE_SUFFIXES=("srt","ass","ssa","vtt")`; L51-54 `_LANG_SIDECAR_RE` joins all suffixes; L57-68 `_glob_source_sidecars()` globs all four; used by BOTH find_source_sub (L190) AND select_source_for_item (L469). New tests test_find_source_sub_discovers_non_srt_sources (parametrized ass/ssa/vtt), test_find_source_sub_priority_across_extensions, test_lang_sidecar_re_matches_all_supported_suffixes. |
| 12 | Signs render in their original screen position in a media player (FMT-04 SC-3 / FMT-02 SC-3) | ? UNCERTAIN (human needed) | Byte-identity of positioning tags is verified by codec structure and round-trip tests. Player rendering requires human visual UAT (09-06-PLAN.md task 2; UAT artifacts staged at /tmp/trezarr_uat/). NOT marked verified — only a real player confirms the renderer interprets the preserved tags. |

**Score:** 11/12 truths verified (all 3 code blockers RESOLVED; 1 UNCERTAIN pending human visual UAT)

---

## Blocker Resolution Detail

### CR-01 (UTF-8 output contract, D-19/FMT-05) — RESOLVED

- `trezarr/subtitles/ass.py` L220: `Path(path).write_bytes(result.encode(doc.encoding))` — reads `doc.encoding`, NOT `ass_doc.encoding`.
- `trezarr/subtitles/vtt.py` L223: `Path(path).write_bytes(result.encode(doc.encoding))` — reads `doc.encoding`, NOT `vtt_doc.encoding`.
- Round-trip integrity preserved: `read_ass` (L135/138, L176/179) and `read_vtt` (L168/171) construct the SubDoc with `encoding=encoding` and the envelope (`AssDoc`/`VttDoc`) with the same `encoding`, so on a plain round-trip `SubDoc.encoding == envelope.encoding` and byte-identity is unchanged.
- Production UTF-8 forcing: `write_vi_sidecar` (write.py L142-150) builds `doc_out` with `encoding='utf-8'` and carries the envelope through, so the writer encodes the vi sidecar as UTF-8 even when the source was latin-1/UTF-16.
- Regression test: `tests/codec/test_encoding_contract.py` sets `doc.envelope.encoding='latin-1'`, `doc.encoding='utf-8'`, and a Vietnamese string containing chars outside latin-1 (`'ệ'`, `'ế'`). Pre-fix this raised `UnicodeEncodeError`; post-fix it round-trips as valid UTF-8. The test is precise and pins the exact failure mode.

**Verdict: genuinely resolved, not superficial. Regression test present.**

### CR-02 (Pass-4 karaoke/drawing corruption, FMT-03) — RESOLVED

- `trezarr/translate/engine.py` L1012-1043 rewrote the splice. New logic:
  1. Build `_corrections` — one entry per non-raw cue, in document order (`None` for failed batches; defensively aligned to `len(rb.cues)` for any length mismatch from `_review_batch`).
  2. Iterate `translated_doc.lines` (ALL cues). For `line.raw is not None` (karaoke/drawing), append verbatim and `continue` **before** consuming the iterator.
  3. Only call `next(_corr_iter)` for non-raw cues.
- This is exactly aligned with `batch_subdoc` (batching.py L146-147), which `continue`s on `cue.raw is not None`, so `review_batches[*].cues` cover precisely the non-raw cues in document order. The per-non-raw-cue iterator therefore stays in lockstep regardless of how many raw cues are interleaved. The old offset-arithmetic misalignment is structurally impossible now.
- Envelope carried forward in the rebuilt SubDoc (engine.py L1052).

**Verdict: logic is correct by inspection — the fix is genuine.**

**WARNING (non-blocking):** Severity context — `enable_self_review` defaults to **True** (config.py L151), so Pass-4 runs on the default production path, not only when explicitly enabled (the initial verification mis-stated it as "disabled by default"). This makes CR-02's correctness load-bearing for default ASS karaoke/drawing handling. Yet there is **no dedicated automated regression test** that exercises the Pass-4 splice with interleaved raw cues — the commit added regression tests only for WR-01 and CR-01 (confirmed by the commit body and by inspecting tests/translate/test_self_review.py, which covers prompt construction and the D-59 fallback but not the splice-with-raw-cues path). The fix is correct, but the FMT-03 guarantee is currently pinned by code review, not by a test. Recommend adding a regression test that runs the engine Pass-4 splice over a doc with interleaved karaoke/drawing raw cues and asserts the raw slots are byte-identical and the non-raw corrections land on the right cues.

### WR-01 (ASS/SSA/VTT source discovery) — RESOLVED

- `trezarr/discover/scan.py` L43: `_SOURCE_SUFFIXES = ("srt","ass","ssa","vtt")`.
- L51-54: `_LANG_SIDECAR_RE` now matches `^(.+?)\.([a-z]{2,3})\.(?:srt|ass|ssa|vtt)$` (case-insensitive).
- L57-68: `_glob_source_sidecars(media_dir, escaped_stem)` globs all four suffixes and returns a single sorted list (preserving the deterministic lexicographically-first-wins selection).
- Used by BOTH consumers: `find_source_sub` (L190) and `select_source_for_item` (L469) — so neither the legacy filesystem-glob discovery path nor the Phase-10 Bazarr-complement selector is `.srt`-only anymore.
- Regression tests in `tests/discover/test_scan.py`: `test_find_source_sub_discovers_non_srt_sources` (parametrized over ass/ssa/vtt), `test_find_source_sub_priority_across_extensions` (.en.ass beats .zh.vtt), `test_lang_sidecar_re_matches_all_supported_suffixes` (and asserts `.mkv` does NOT match).

**Verdict: genuinely resolved with thorough regression coverage.**

**INFO (cosmetic, non-blocking):** Stale docstrings in scan.py still describe the old `.srt`-only limitation (module docstring L9-12 "only matches {media_stem}.{lang}.srt"; find_source_sub docstring L150 "Glob {media_stem}.*.srt"; L159-162 Phase-3 limitation note). These no longer reflect behavior and could mislead a future reader. No functional impact.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/subtitles/ass.py` | Hand-rolled ASS/SSA codec, UTF-8 output via doc.encoding | ✓ VERIFIED | write_ass L220 uses doc.encoding; read_ass sets SubDoc.encoding == envelope.encoding |
| `trezarr/subtitles/vtt.py` | Hand-rolled VTT codec, UTF-8 output via doc.encoding | ✓ VERIFIED | write_vtt L223 uses doc.encoding; read_vtt sets SubDoc.encoding == envelope.encoding |
| `trezarr/subtitles/dispatch.py` | Format dispatcher (.srt/.ass/.ssa/.vtt) | ✓ VERIFIED | _READERS/_WRITERS map all four; .ssa shares ASS codec; wired in engine.py + write.py |
| `trezarr/translate/engine.py` | Pass-4 splice that skips raw-cue slots | ✓ VERIFIED | L1012-1043 walk-doc + advance-on-non-raw-only logic; envelope carried forward L1052 |
| `trezarr/translate/batching.py` | batch_subdoc skips raw cues | ✓ VERIFIED | L146-147 `if cue.raw is not None: continue` — contract CR-02 relies on |
| `trezarr/discover/scan.py` | Multi-format source discovery | ✓ VERIFIED | _SOURCE_SUFFIXES, broadened regex, _glob_source_sidecars used by both discovery functions |
| `trezarr/output/write.py` | write_vi_sidecar forces UTF-8, carries envelope | ✓ VERIFIED | doc_out encoding='utf-8' (L144), envelope=doc.envelope (L149) |
| `tests/codec/test_encoding_contract.py` | CR-01 regression | ✓ VERIFIED | latin-1 envelope + utf-8 doc + non-latin-1 Vietnamese text round-trips |
| `tests/discover/test_scan.py` | WR-01 regression | ✓ VERIFIED | parametrized ass/ssa/vtt discovery + cross-extension priority + regex coverage |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| engine.py | dispatch.py | read_subtitle call | ✓ WIRED | engine imports read_subtitle; calls read_subtitle(path) |
| write.py | dispatch.py | write_subtitle call | ✓ WIRED | write.py imports + calls _dispatch_write_subtitle |
| write_vi_sidecar doc_out | write_ass/write_vtt | encoding='utf-8' on doc_out → doc.encoding | ✓ WIRED (was NOT WIRED, CR-01) | doc_out.encoding='utf-8' (write.py L144) is now the value both writers encode with |
| engine.py Pass-4 splice | translated_doc raw slots | _corr_iter advanced only on non-raw cues | ✓ WIRED (was NOT WIRED, CR-02) | raw cues appended verbatim before any next(); aligned with batch_subdoc raw-skip |
| find_source_sub / select_source_for_item | filesystem | _glob_source_sidecars over all suffixes | ✓ WIRED (was DISCONNECTED, WR-01) | both discovery paths now glob .srt/.ass/.ssa/.vtt |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| write_ass output encoding | doc.encoding | doc_out built with 'utf-8' on sidecar path; envelope.encoding on round-trip | Yes — correct field read | ✓ FLOWING |
| write_vtt output encoding | doc.encoding | same | Yes | ✓ FLOWING |
| Pass-4 corrected_lines | _corr_iter over non-raw cues | review_results from batch_subdoc (non-raw only) | Yes — iterator advances only on non-raw cues, matching the source span exactly | ✓ FLOWING |
| find_source_sub candidates | _glob_source_sidecars over _SOURCE_SUFFIXES | filesystem | Yes — .ass/.ssa/.vtt files returned | ✓ FLOWING |

---

### Behavioral Spot-Checks

Full suite executed: `uv run pytest -q` → 343 passed, 1 skipped, 3 xfailed, 43 xpassed, 1 warning (intentional malformed-SRT preservation in an unrelated integration test).

| Behavior | Check | Result | Status |
|----------|-------|--------|--------|
| write_ass/write_vtt honour UTF-8 override over envelope | tests/codec/test_encoding_contract.py (both functions) | latin-1 envelope + utf-8 doc + non-latin-1 text round-trips as UTF-8 | ✓ PASS |
| ASS/SSA/VTT sources discovered | tests/discover/test_scan.py::test_find_source_sub_discovers_non_srt_sources[ass|ssa|vtt] | each extension discoverable; priority preserved across extensions | ✓ PASS |
| batch_subdoc skips raw cues (CR-02 contract) | batching.py L146-147 inspection | `if cue.raw is not None: continue` confirmed | ✓ PASS |
| Pass-4 splice aligns to non-raw cues | engine.py L1012-1043 inspection | iterator advanced only on non-raw cues; raw appended verbatim | ✓ PASS (inspection — no dedicated test, see CR-02 WARNING) |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| FMT-02 | 09-01, 09-03, 09-05 | ASS/SSA: translate dialogue text only; tags/drawing/headers byte-identical | ✓ SATISFIED | Codec byte-identity verified; CR-01 (UTF-8 output) and WR-01 (discovery) resolved — ASS sources reach the pipeline and produce UTF-8 sidecars |
| FMT-03 | 09-01, 09-03, 09-05 | Karaoke (\\k) lines preserved verbatim without corruption | ✓ SATISFIED | read_ass raw=text; batch skips raw; CR-02 Pass-4 splice no longer overwrites raw slots. WARNING: pinned by code review, not a dedicated test |
| FMT-04 | 09-01, 09-04, 09-05 | VTT round-trips cue settings/positioning | ✓ SATISFIED (SC-3 pending human) | timing_line verbatim; VttOpaqueBlock for NOTE/STYLE/REGION; CR-01 + WR-01 resolved. SC-3 player-render pending human UAT (truth #12) |
| FMT-05 | 09-05 | Output always UTF-8 regardless of source encoding | ✓ SATISFIED | CR-01 resolved — write_vi_sidecar forces 'utf-8' and writers honour it; regression test pins it |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| trezarr/discover/scan.py | 9-12, 150, 159-162 | Stale docstrings still describe `.srt`-only discovery | ℹ️ Info | Cosmetic — behavior is correct (multi-format); docstrings could mislead a future reader |
| trezarr/translate/engine.py | 1012-1043 | CR-02 splice correct but unguarded by a dedicated FMT-03 regression test | ⚠️ Warning | FMT-03 default-path guarantee (self-review enabled by default) is pinned by code review only |

No `TBD`/`FIXME`/`XXX` debt markers in phase-modified files. The previously-flagged BLOCKER anti-patterns (ass.py L215, vtt.py L218, engine.py L1003-1016, scan.py L167/L45) are all RESOLVED.

---

### Human Verification Required

#### 1. Positioned sign rendering in ASS

**Test:** Produce a `.vi.ass` sidecar from the `pos_an8.ass` fixture (contains `{\an8}{\pos(960,50)}` cues) by running the translation pipeline (UAT artifacts staged at /tmp/trezarr_uat/). Load alongside any video of the right resolution in mpv:
`mpv <video-file> --sub-file=<path-to.vi.ass>`

**Expected:** The positioned sign cue appears at the **same screen position** as in the source `.ass` — top-center for `{\an8}`, or exact x,y for `{\pos}`.

**Why human:** Unit tests verify byte-identity of override-tag bytes in the output. Only a real player confirms the renderer interprets the preserved positioning tags after translation.

#### 2. VTT cue-settings positioning in browser/player

**Test:** Produce a `.vi.vtt` sidecar from `cue_settings.vtt`. Text-editor check: confirm the timing line still contains the verbatim cue-settings string (e.g. `00:00:01.000 --> 00:00:03.000 position:50% align:center`). Then load in a browser `<track>` element or VTT-capable player and confirm cues render at the specified position.

**Expected:** (1) Timing line byte-identical for the settings portion. (2) Cue renders at the CSS-specified position in a real player.

**Why human:** Cue settings are preserved in `VttCueBlock.timing_line` and structural byte-identity is confirmed by tests. Player rendering of `position:`/`line:` via CSS depends on the player's VTT renderer.

---

## Verdict

**Status: human_needed**

All three code blockers from the initial verification are **RESOLVED** in commit 4052d90, confirmed against the current code on `main` (not the SUMMARY narrative):

1. **CR-01** (UTF-8 output contract) — RESOLVED. `write_ass`/`write_vtt` encode with `doc.encoding`; round-trip byte-identity preserved; `write_vi_sidecar` forces UTF-8; regression test pins the non-latin-1 case.
2. **CR-02** (Pass-4 karaoke corruption) — RESOLVED. The splice now walks the full document and advances the correction pointer only on non-raw cues, exactly aligned with `batch_subdoc`'s raw-skip contract. Correct by inspection.
3. **WR-01** (ASS/SSA/VTT source discovery) — RESOLVED. Discovery broadened to all four suffixes via `_glob_source_sidecars`, used by both discovery functions; thorough regression tests.

Full suite green: **343 passed**. Score raised from 8/12 to **11/12**.

The only remaining item is the human visual UAT for truth #12 (signs render at correct screen position in mpv/Jellyfin and VTT cue-settings positioning in a browser). This is `human_needed`, not a code gap — there are **no remaining code gaps**. Per the project memory note, an `--auto` chain should hold here for the operator to perform the visual walkthrough rather than auto-closing with pending UAT.

Two non-blocking advisories for follow-up (do not block the phase):
- ⚠️ Add a dedicated FMT-03 regression test for the Pass-4 splice over interleaved raw (karaoke/drawing) cues — self-review is enabled by default, so this guarantee is currently pinned by code review only.
- ℹ️ Refresh the stale `.srt`-only docstrings in `scan.py`.

---

_Verified: 2026-06-02T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Depth: standard (re-verification)_
