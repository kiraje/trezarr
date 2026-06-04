# Phase 9: Multi-Format — ASS/SSA + VTT - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** `--auto` (all gray areas auto-resolved to the recommended default; planner/researcher may override any with rationale)

<domain>
## Phase Boundary

Phase 9 extends Trezarr's subtitle codec from **SRT-only** to **ASS/SSA + VTT**, so the
existing three-pass translation pipeline can process those formats without changing the
moat. Trezarr translates **only dialogue text** while leaving everything else —
override tags (`{\an8}`, `\pos`, fonts), drawing commands, `\N`/`\h` breaks, karaoke
(`\k`) timing, `[Script Info]`/`[V4+ Styles]` headers, and VTT cue settings/positioning —
**byte-identical** on round-trip.

Requirements covered: **FMT-02** (ASS/SSA dialogue-only translation, byte-identical
structure), **FMT-03** (karaoke `\k` round-trips without corruption), **FMT-04** (VTT
parse/write round-tripping cue settings/positioning).

**In scope:** hand-rolled ASS/SSA reader+writer and VTT reader+writer (byte-identical
raw-preservation, mirroring the existing SRT codec); a format-dispatch layer keyed on file
suffix; per-format extraction of the translatable text into the existing `SubLine`/`SubDoc`
pipeline contract and re-injection on write; extending the inline-tag sentinel + the
validation gate's untranslated-allowlist + the shared timecode parser to cover ASS/VTT;
output sidecars that mirror the source format/extension (`.vi.ass`, `.vi.ssa`, `.vi.vtt`);
generalizing self-output exclusion (AUTO-04) and idempotency to `.vi.<ext>`.

**Out of scope:** any change to the Series Bible, the pronoun/attribution engine, the
batching strategy, or the 3-pass/self-review flow (those operate on the format-agnostic
`SubLine.text` and must remain untouched — see D-94); source-language selection / Bazarr
inventory (Phase 10); re-timing or re-styling subtitles; format **conversion** (ASS→SRT
etc. — output always mirrors input format); karaoke syllable-timing **remapping** (we
preserve verbatim, never remap — FMT-03).

</domain>

<decisions>
## Implementation Decisions

> Carried forward from Phase 1 (codec fidelity) and Phase 2 (sentinel): **D-08**
> byte-identical round-trip is THE contract; **D-09** inline tags ride along inside cue
> text (model separates *timing* from text, not *tags* from text); **D-10** malformed
> cues are preserved-and-flagged, never dropped; **D-12** the sentinel placeholder-protects
> inline tags before the LLM call. Critically, Phase 1 **rejected pysubs2** for SRT after
> empirical testing (it renumbers indices, comma-normalizes timecodes, pads milliseconds,
> forces LF) and shipped a hand-rolled raw-preservation codec (`trezarr/subtitles/srt.py`).
> Phase 9 inherits that verdict.

### Parser strategy (the central decision)
- **D-91:** Build **hand-rolled, raw-preservation parsers/serializers** for ASS/SSA and
  VTT, mirroring `srt.py`'s strategy (preserve the verbatim structural pieces —
  headers/sections/separators/trailer — and reconstruct output from raw bytes rather than
  re-rendering from normalized fields). **Do NOT use pysubs2** for parse/serialize: it
  normalizes styles, reorders/rewrites fields, drops comments, and would fail success
  criterion 1 ("byte-identical"). Supersedes Phase-1 **D-02** (which provisionally named
  pysubs2) — D-08 byte-identity wins, exactly as it already did for SRT. The researcher may
  use pysubs2 (or its grammar) as a *read-only reference* for field layout, but it must not
  be on the write path.

### Pipeline contract (keep the moat untouched)
- **D-92:** Keep `SubLine`/`SubDoc` (`trezarr/subtitles/model.py`) as the **format-agnostic
  pipeline contract**. Each translatable ASS `Dialogue:` line / VTT cue maps to exactly one
  `SubLine` (its verbatim source timecodes in `start_tc`/`end_tc`; the translatable text in
  `.text`). The full document structure (sections, styles, headers, cue settings, line
  order) lives in a **per-format "envelope"** owned by the format codec — analogous to
  `SubDoc.leading`/`separators`/`trailer` but richer. The codec, not the pipeline, knows
  about ASS sections and VTT blocks.
- **D-93:** `batch_subdoc`, `validate_subdoc`, the sentinel, reconcile, and the 3-pass/
  self-review engine stay **format-agnostic** — they continue to operate on
  `SubLine.text` + timecodes and must not learn format specifics. This preserves the 1:1
  cue↔SubLine mapping the validation gate depends on.

### Format dispatch & sidecar naming
- **D-94:** Add a suffix-keyed dispatcher — `read_subtitle(path)` / `write_subtitle(doc,
  path)` — that routes `.srt`→existing SRT codec, `.ass`/`.ssa`→ASS codec, `.vtt`→VTT codec.
  Replace the hardcoded `read_srt` call in `engine.py` and the hardcoded `write_srt` call
  in `output/write.py` with the dispatcher.
- **D-95:** **Output format mirrors input format.** An `.ass` source produces a `.vi.ass`
  sidecar, `.vtt`→`.vi.vtt`, `.srt`→`.vi.srt`. Generalize `derive_sidecar_path`
  (`output/write.py`, currently hardcodes `.vi.srt`) to mirror the source extension while
  keeping the existing ISO-639 lang-suffix stripping.
- **D-96:** Generalize **self-output exclusion (AUTO-04)** and gap-detection: the
  "foreign `.vi.srt` → skip / never clobber" logic in `engine.py` and `discover/gap.py`
  must become `.vi.<ext>`-aware so Trezarr still excludes its own ASS/VTT output and stays
  idempotent. This is a regression risk — must be explicitly tested for every format.

### ASS/SSA translatable unit & tag protection (FMT-02)
- **D-97:** The **translatable unit is the entire `Text` field of a `Dialogue:` event** —
  one Dialogue Text = one `SubLine`. Translate the `Text` field only. **Never** translate
  or mutate `Comment:` events, `[Script Info]`, `[V4+ Styles]`/`[V4 Styles]`, the `Format:`
  lines, style names, actor/Name, effect, layer, or margins — all preserved verbatim by the
  envelope.
- **D-98:** Extend the sentinel (`trezarr/translate/sentinel.py`, whose `TAG_RE` already
  matches `{\...}` override blocks and `<...>` tags) to also placeholder-protect, inside the
  Text field: **`\N`/`\n`/`\h`** hard breaks/spaces, and **drawing-mode runs** (text between
  `{\p1}`…`{\p0}` is vector geometry, not language — protect the whole run so coordinates are
  never sent to the LLM). The LLM receives only natural-language text + opaque `<<TN>>`
  tokens and must return the tokens unchanged in place; reinsertion failure follows the
  existing D-59 integrity path.

### Karaoke policy (FMT-03)
- **D-99:** **Karaoke = verbatim pass-through.** If a Dialogue Text field contains `\k`,
  `\kf`, `\ko`, or `\K` syllable-timing tags, pass that cue's text **untranslated,
  byte-identical** (remapping syllable timing across a reflowed translation is unsafe — the
  requirement itself says "verbatim where remapping is unsafe"). Flag/count these as
  `skipped-karaoke` and **allowlist them at the gate** so the untranslated-line check does
  not quarantine the whole file (same mechanism as the existing per-line allowlist).

### VTT structure & gate robustness (FMT-04)
- **D-100:** Hand-rolled VTT codec preserves the **`WEBVTT` header line(s), `NOTE`/`STYLE`/
  `REGION` blocks, optional cue identifiers, and each cue's settings string** (`position:`,
  `line:`, `align:`, `size:`, `vertical:`, `region:` on the timecode line) **verbatim**.
  Extend the sentinel to VTT inline tags (`<v Speaker>`, `<c.class>`, `<ruby>/<rt>`, inline
  `<00:00:00.000>` timestamps, `&nbsp;`/entities). Translate only the cue payload text.
- **D-101:** Teach the shared timecode parser (`trezarr/translate/_timecode.py`,
  `tc_to_ms`) the new timecode shapes so the gate's monotonic check works (today it matches
  only `HH:MM:SS,mmm`/`.mmm` with a 2-digit hour and **returns 0 → fails closed** on
  anything else): **ASS** `H:MM:SS.cc` (1-digit hour, 2-digit **centiseconds**) and **VTT**
  `MM:SS.mmm` (hour omitted) / `HH:MM:SS.mmm`. Keep the verbatim string in
  `start_tc`/`end_tc` for byte-identity; parse to ms only for the gate. **The gate still
  runs for ASS/VTT** — cue-count, no-empty, untranslated-allowlist, timecode/index
  non-mutation, monotonic, UTF-8 — because blind-trust automation is the product promise.
- **D-102:** Extend the untranslated-line **allowlist** (`validate_subdoc`) so
  intentionally-untranslated cues — karaoke (D-99), drawing-only, empty-after-tag-strip, and
  pure-tag/sign cues with no natural-language content — do not trip the VI-diacritic-ratio
  false-quarantine. Tag-heavy ASS/VTT files would otherwise be wrongly rejected.

### Claude's Discretion
Delegated to planner/researcher (auto mode picked recommended defaults above; these
remain open within the decisions): exact module/package layout for the new codecs
(`trezarr/subtitles/ass.py`, `trezarr/subtitles/vtt.py`, and a `dispatch.py` are the
obvious shape); the precise envelope data structure per format; the exact regexes for
ASS drawing-run / karaoke detection and VTT cue-settings capture; test-fixture selection
(must include real-world anime ASS with `\pos`/`\an8`/`\p` drawing/`\k` karaoke and a VTT
with cue settings + `<v>` voices + regions); whether sign/OP/ED **style-based skipping**
is added now or deferred (see Deferred Ideas).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/ROADMAP.md` §"Phase 9: Multi-Format — ASS/SSA + VTT" — goal + 3 success
  criteria (ASS dialogue-only + headers/tags/drawing/`\N` byte-identical; karaoke `\k`
  round-trips uncorrupted; VTT round-trips cue settings/positioning, signs render in
  original screen position)
- `.planning/REQUIREMENTS.md` §Subtitle Formats — **FMT-02, FMT-03, FMT-04** (and FMT-01/
  FMT-05 already-shipped for the SRT precedent)
- `.planning/PROJECT.md` §Constraints ("preserve original styling for ASS/SSA"),
  §Requirements ›Formats & delivery

### Codec fidelity precedent (the pattern to mirror — and the pysubs2 verdict)
- `.planning/phases/01-codec-llm-client-foundation/01-CONTEXT.md` — **D-08/D-09/D-10**
  codec-fidelity decisions carried forward; **D-02** (pysubs2) is superseded by D-91
- `.planning/phases/01-codec-llm-client-foundation/01-RESEARCH.md` — pysubs2
  byte-identity pitfalls (renumber/normalize/pad/LF) that justify hand-rolling
- `.planning/research/PITFALLS.md` — byte-identity, encoding/UTF-8 vs CP1258 failure modes
- `.planning/research/STACK.md` — pysubs2 is the *prescribed* lib (CLAUDE.md), deliberately
  **diverged from** on the write path per D-91; read to understand what is being traded away
- `CLAUDE.md` §Technology Stack (pysubs2 1.8.x rationale) and §"Translate only the dialogue
  event text… validate that inline override tags `{\...}` are preserved" — the prescription
  Phase 9 honors in spirit (dialogue-only) while replacing pysubs2 on the write path

### Code to extend (the integration seams — read before planning)
- `trezarr/subtitles/srt.py` — the raw-preservation reference implementation to mirror
- `trezarr/subtitles/model.py` — the `SubLine`/`SubDoc` pipeline contract (kept; D-92)
- `trezarr/subtitles/encoding.py` — encoding/BOM detection reused for ASS/VTT
- `trezarr/translate/sentinel.py` — `TAG_RE`; extend for `\N`/`\h`, drawing runs, VTT tags (D-98/D-100)
- `trezarr/translate/_timecode.py` — `tc_to_ms`; extend for ASS centiseconds + VTT hourless (D-101)
- `trezarr/translate/validate.py` — 7-check gate + untranslated-allowlist (D-102)
- `trezarr/translate/batching.py` — `batch_subdoc` (format-agnostic; must stay so — D-93)
- `trezarr/translate/engine.py` — hardcoded `read_srt` @~674 + `.vi.srt`/foreign-skip @~650 → dispatch (D-94/D-96)
- `trezarr/output/write.py` — `write_srt` @~129 + `derive_sidecar_path` `.vi.srt` @~88 → dispatch + mirror ext (D-94/D-95)
- `trezarr/discover/gap.py` — foreign-`.vi.srt` skip + `derive_sidecar_path` consumer → `.vi.<ext>` (D-96)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`srt.py` raw-preservation strategy** (`leading + block[i] + separator[i] + … + trailer`,
  reconstruct from raw bytes, malformed→opaque pass-through): directly transferable to ASS
  sections and VTT blocks. This is the template for D-91.
- **`SubLine`/`SubDoc` model**: already exactly what the pipeline needs; no change required
  (D-92). `SubLine.raw` (opaque pass-through) is the precedent for verbatim karaoke/drawing.
- **`sentinel.py`**: `TAG_RE = (<[^>]+>|\{\\[^}]+\})` already protects ASS `{\...}` override
  blocks AND HTML-style tags — extending it (not rewriting) covers most ASS/VTT inline tags.
- **`validate_subdoc` + per-line allowlist**: the gate is format-agnostic on `.text`;
  extend the allowlist rather than special-case formats (D-102).
- **`encoding.detect_encoding`** + verbatim-encoding write-back: ASS is typically UTF-8(±BOM);
  VTT is UTF-8 by spec — the existing BOM/endianness round-trip already handles both.

### Established Patterns
- **Timing is locally-owned; text is the only LLM-mutable field** (D-09) — the spine the
  whole pipeline relies on. ASS/VTT must keep timecodes/structure out of the LLM's reach.
- **Byte-identity via raw capture, not field re-rendering** (D-08) — the reason pysubs2 is
  off the write path.
- **Preserve-and-flag for the malformed** (D-10) — apply to unparseable ASS/VTT lines.

### Integration Points (seams the planner MUST touch — each is a regression risk)
1. `engine.py` ~L674 `source_doc = read_srt(path)` → format dispatch (`read_subtitle`).
2. `output/write.py` ~L88 `derive_sidecar_path` (hardcodes `.vi.srt`) → mirror source ext;
   ~L129 `write_srt` → `write_subtitle` dispatch.
3. `engine.py` ~L650 + `discover/gap.py` ~L109 foreign-`.vi.srt` skip → `.vi.<ext>` so
   AUTO-04 self-output exclusion does not regress for ASS/VTT.
4. `_timecode.py` `tc_to_ms` regex (`\d{2}:\d{2}:\d{2}[,.]\d+` only) — **fails closed
   (returns 0 → zero-duration GateError) on every ASS/VTT timecode today.** Must parse ASS
   `H:MM:SS.cc` and VTT `MM:SS.mmm`/`HH:MM:SS.mmm` or no ASS/VTT file will ever pass the gate.
5. `validate.py` untranslated-allowlist → admit karaoke/drawing/sign/pure-tag cues.
6. `sentinel.py` `TAG_RE` → add `\N`/`\h`, ASS drawing runs, VTT `<v>/<c>/<ruby>/<timestamp>`.

</code_context>

<specifics>
## Specific Ideas

- **Byte-identity for the non-dialogue parts is the entire value here.** Anime/fansub ASS
  carries typesetting (signs, `\pos` positioning, OP/ED karaoke) that, if disturbed, makes
  the output worse than the original. "Preserve perfectly, translate only the words" is the
  bar — when in doubt, preserve.
- **Output mirrors input** (D-95): `.ass`→`.vi.ass`, `.vtt`→`.vi.vtt`. Media players
  (Plex/Jellyfin/Emby/mpv) select and style by extension + embedded styles; converting to
  SRT would discard the styling this phase exists to protect.
- **VTT success criterion 3 ("signs render in their original screen position in a media
  player") is visually verifiable** — flag a human/visual UAT item: render a positioned
  ASS `\pos`/`\an8` cue and a VTT `position:`/`line:` cue in a real player and confirm the
  sign lands where the source put it. Unit round-trip tests alone can't prove this.
- Provide **real-world fixtures**, not synthetic: a genuine anime `.ass` with `[Script
  Info]`, `[V4+ Styles]`, `\pos`/`\an8`, a `\p` drawing, and `\k` karaoke; a `.vtt` with
  cue settings, `<v>` voices, a `STYLE`/`REGION` block, and an inline `<timestamp>`.

</specifics>

<deferred>
## Deferred Ideas

- **Style-based sign/OP/ED skipping** — optionally *skip translating* `Dialogue:` events
  whose Style suggests signs/songs/OP/ED (e.g. style name `Signs`, `OP`, `ED`) rather than
  translating every Dialogue Text field. The recommended Phase-9 default (D-97) translates
  all Dialogue Text except karaoke/drawing; a per-style skip *policy* (and a config/per-series
  knob for it) is a refinement, not required by FMT-02/03/04. Revisit if real output shows
  signs being unhelpfully translated; aligns naturally with Phase-10 per-series overrides.
- **Karaoke syllable-timing remapping** — actually re-timing `\k` syllables to a translated
  reflow (instead of verbatim pass-through). Explicitly out of scope for v1 (FMT-03 chooses
  verbatim); a future enhancement only if there's demand.

</deferred>

---

*Phase: 9-Multi-Format — ASS/SSA + VTT*
*Context gathered: 2026-06-02*
