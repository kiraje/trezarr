# Phase 9: Multi-Format — ASS/SSA + VTT - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 9-Multi-Format — ASS/SSA + VTT
**Mode:** `--auto` (fully autonomous — all gray areas auto-resolved to the recommended default; no interactive prompts)
**Areas discussed:** Parser strategy, Pipeline contract, Format dispatch & sidecar naming, ASS translatable-unit & tag protection, Karaoke policy, VTT structure & gate robustness

---

## Parser strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-rolled raw-preservation per format (mirror `srt.py`) | Preserve verbatim structural bytes; reconstruct output from raw, not normalized fields. Guarantees byte-identity. | ✓ |
| pysubs2 parse/serialize (CLAUDE.md-prescribed) | One unified lib for ASS/VTT; less code — but normalizes styles/fields/comments → breaks byte-identity (already proven for SRT in Phase 1). | |
| Hybrid (pysubs2 to locate events, hand-rolled write-back) | Use pysubs2 only to find dialogue; raw-preserve on write. Adds a dependency on the read path for little gain. | |

**Choice:** Hand-rolled raw-preservation (D-91).
**Notes:** Byte-identity is success criterion 1 and a carried-forward hard contract (D-08). Phase 1 already rejected pysubs2 for SRT for exactly these normalization reasons (`srt.py` header documents it). Supersedes Phase-1 D-02.

---

## Pipeline contract

| Option | Description | Selected |
|--------|-------------|----------|
| Keep `SubLine`/`SubDoc` as the format-agnostic contract; per-format codec envelope | One Dialogue/cue ↔ one SubLine; structure lives in a per-format envelope. Batching/validate/sentinel/3-pass untouched. | ✓ |
| Generalize `SubLine` with format fields (style/name/margins) | Pollutes the model; forces pipeline changes; risks the moat. | |
| Separate per-format models with a common protocol | More machinery; pipeline must learn formats. | |

**Choice:** Keep the contract; per-format envelope (D-92/D-93).
**Notes:** Preserves the 1:1 cue↔SubLine mapping the validation gate relies on and keeps the differentiator (Bible/pronoun/3-pass) code unchanged.

---

## Format dispatch & sidecar naming

| Option | Description | Selected |
|--------|-------------|----------|
| Suffix-keyed `read_subtitle`/`write_subtitle`; output mirrors source ext; self-output → `.vi.<ext>` | Route `.srt/.ass/.ssa/.vtt`; `.ass`→`.vi.ass` etc.; generalize foreign-skip + idempotency. | ✓ |
| Keep `.vi.srt` only, convert ASS/VTT→SRT | Discards styling — defeats the entire phase. | |

**Choice:** Dispatcher + mirror extension (D-94/D-95/D-96).
**Notes:** AUTO-04 self-output exclusion and gap-detection must generalize to `.vi.<ext>` (regression risk; test per format).

---

## ASS translatable-unit & tag protection

| Option | Description | Selected |
|--------|-------------|----------|
| Whole `Dialogue:` Text field = one cue; extend sentinel (`{...}` done + `\N`/`\h` + drawing `\p` runs); never touch Comment/headers/styles | Translate only natural language; protect all structure/geometry. | ✓ |
| Split on `\N` into separate SubLines | Risks LLM merge/reorder; breaks 1:1 cue mapping the gate needs. | |

**Choice:** Whole Text field + extended sentinel (D-97/D-98).
**Notes:** Drawing-mode runs (`{\p1}`…`{\p0}`) are vector coordinates, never sent to the LLM.

---

## Karaoke (`\k`) policy

| Option | Description | Selected |
|--------|-------------|----------|
| Verbatim pass-through, gate-allowlisted | If `\k/\kf/\ko/\K` present, keep the cue untranslated/byte-identical; allowlist so the gate doesn't quarantine. | ✓ |
| Attempt syllable-timing remapping | High corruption risk across a reflowed translation. | |

**Choice:** Verbatim pass-through (D-99).
**Notes:** Directly follows FMT-03's own wording ("verbatim where remapping is unsafe").

---

## VTT structure & gate robustness

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-rolled VTT raw-preservation + extend timecode parser + extend untranslated-allowlist | Preserve WEBVTT/NOTE/STYLE/REGION + per-cue settings verbatim; sentinel for `<v>/<c>/<ruby>/<timestamp>`; teach `tc_to_ms` ASS centiseconds + VTT hourless; admit tag-heavy/sign cues. | ✓ |
| pysubs2 VTT | Normalizes; drops regions/styles. | |

**Choice:** Hand-rolled VTT + gate robustness (D-100/D-101/D-102).
**Notes:** `tc_to_ms` currently returns 0 for any ASS/VTT timecode → zero-duration GateError; without this, no ASS/VTT file would ever pass the gate.

## Claude's Discretion

Module/package layout for the new codecs (`ass.py`/`vtt.py`/`dispatch.py` likely), the precise envelope structure per format, exact regexes for drawing-run/karaoke/cue-settings detection, test-fixture selection (real-world ASS + VTT required), and whether style-based sign/OP/ED skipping ships now or is deferred. All four single-question turns were auto-answered with the recommended option per `--auto`.

## Deferred Ideas

- Style-based sign/OP/ED skipping (translate-all-Dialogue vs skip-sign-styles) — refinement, aligns with Phase-10 per-series overrides.
- Karaoke syllable-timing remapping — explicitly out of scope for v1 (FMT-03 chooses verbatim).
