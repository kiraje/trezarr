# Phase 2: Mechanical Translation Core + Validation Gate - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 wires the Phase 1 leaves into the first end-to-end translation path **for a single already-parsed file path** (the file is handed in; *arr discovery that finds it is Phase 3):

1. **Batch** a parsed `SubDoc` into LLM-sized chunks within the configured token budget, never splitting a cue, preferring scene/pause boundaries (ENG-02).
2. **Translate** each batch in a single LLM pass with a read-only surrounding-line context window for conversational coherence (ENG-03), preserving the 1:1 cue mapping.
3. **Gate** the assembled result with a hard pre-write validation check; on failure, quarantine + log and write nothing (ENG-06).
4. **Write** a passing result as a correctly-named, atomic, UTF-8 `.vi.srt` sidecar (FMT-05), idempotently re-runnable without duplicating or corrupting output (ENG-07).

Requirements covered: **ENG-02** (batching), **ENG-03** (surrounding-line context), **ENG-06** (hard validation gate), **ENG-07** (idempotent re-run), **FMT-05** (sidecar naming / atomic / UTF-8).

**In scope:** batching/chunking, single-pass translation orchestration over `LLMClient.call()`, inline-tag protection, the pre-write validation gate, quarantine + logging, atomic sidecar write, and an idempotency ledger.

**Out of scope (later phases):**
- **No Series Bible, no pronoun engine, no relational consistency** — Phase 2 is a *mechanical* single pass. Vietnamese pronoun/relationship correctness (the product's core value) arrives in Phases 4–5. Phase 2 must not pretend to solve consistency.
- *arr discovery / path-mapping / the file-watcher that feeds this pipeline — Phase 3.
- Two-pass analyze→translate and the LLM self-review pass — Phases 4 and 6.
- ASS/SSA + VTT — Phase 9 (Phase 2 is SRT-only).
- PUID/PGID ownership and Docker packaging — Phase 7 (Phase 2 writes with the running process's identity).

</domain>

<decisions>
## Implementation Decisions

The user delegated all gray areas ("you think then decide"). The decisions below are research-grounded defaults (corroborated by `.planning/research/PITFALLS.md`), continuing the Phase 1 decision ledger (D-01…D-11). **All are overridable in planning.** Numbered values (retry counts, neighbor-line counts, thresholds) are sensible defaults the planner/researcher may tune.

### Inline tag handling (carries D-09 forward)
- **D-12: Placeholder-protect inline tags.** Before sending a cue's `text` to the LLM, extract inline formatting (`<i> <b> <u> <font…>`, occasional `{\anX}`) and replace each with a unique non-translatable sentinel token; instruct the model to keep sentinels in place; reinsert the original tags by sentinel after translation. Tags are **never translated** and styling is preserved (the project's ASS/SSA-styling constraint applies to SRT inline tags too). If a cue's sentinels don't round-trip (count/identity mismatch), that cue **fails the gate** (see D-18). Timing/indices remain locally-owned and untouched (D-08).

### Translation orchestration
- **D-13: Guarantee 1:1 cue mapping by construction.** Send numbered lines and require numbered output (structured/delimited per the Phase 1 `auto → json_schema → json_object → text` degradation, D-04); reassemble translated `text` back onto the original `SubLine` list by index. Cue-count match is enforced at assembly; the gate (D-16) is the backstop, not the only line of defense.
- **D-14: Batch by token budget at safe boundaries (ENG-02).** Pack cues into batches sized to a fraction of `llm_context_window` (reserve headroom for prompt + neighbor context + output). **Never split a single cue.** Prefer boundaries at a time gap ≥ a scene/pause threshold; if a run of dialogue has no gap, fall back to a max-cue-count window. Token estimation should be **conservative and tokenizer-agnostic** (many user endpoints aren't OpenAI-tokenizer-exact) — a char/token heuristic with a safety margin is acceptable; researcher chooses the exact mechanism.
- **D-15: Surrounding-line context window (ENG-03).** Each batch is translated with K read-only source lines before and after (default K≈2–5) that the model sees for coherence but does **not** re-emit. Respects batch boundaries (context can cross a boundary even though cues don't).

### Validation gate — the hard pre-write check (ENG-06)
- **D-16: Gate every write on ALL of:** (1) cue count equals source; (2) no empty/whitespace-only translated lines; (3) no "untranslated" lines (D-17); (4) timecodes/indices byte-identical to source (they were never sent to the LLM, so any drift is a bug); (5) monotonic, non-overlapping timestamps preserved from source; (6) tag-sentinel integrity (D-12); (7) result re-parses as valid SRT and encodes as valid UTF-8. **Any failure → quarantine, never write** (Pitfall: blind trust means a silent partial write is a betrayal of the core contract).
- **D-17: "Untranslated line" detection = cheap, layered, low-false-reject.** Per line: flag if the translated text is byte-identical to the source line, **except** an allowlist of legitimately-unchanged lines (all-punctuation/digits/whitespace, lone proper nouns/numbers, "♪"/"..."). Per file: a Vietnamese-signal sanity check — the ratio of lines containing Vietnamese diacritics/characters must exceed a conservative threshold. **No heavy per-line language-detection dependency** (short subtitle lines are too ambiguous). Thresholds configurable.
- **D-18: Failure handling = bounded per-batch retry, then whole-file reject.** On a gate-relevant batch failure (count/sentinel/empty/untranslated), re-prompt that batch up to N times (default 2). If any batch still fails after retries, or the assembled document fails the document-level gate, **reject the whole file** — never write a partial/half-translated sidecar (consistency bar). Quarantine = write a failure artifact under the `/config` state dir (e.g. `/config/quarantine/<basename>.json`: reason, failing cue indices, timestamp, optional rejected candidate for debugging) and log loudly. Nothing is written next to the media on failure.

### Output & idempotency
- **D-19: Atomic UTF-8 sidecar (FMT-05).** Write to a temp file in the destination directory, then `os.replace()` (atomic same-filesystem rename) to `<video-basename>.vi.srt` (ISO-639 `vi`, matching the media basename). Always valid UTF-8. A crash mid-write never leaves a corrupt or half-visible sidecar.
- **D-20: Idempotency via a `/config` processed-files ledger (ENG-07).** Maintain a lightweight ledger under the config dir, **schema-compatible with the Phase-4 `processed_file` table** (`source_path`, `output_path`, `status`, `content_hash`) so Phase 4 can migrate it into SQLAlchemy/SQLite without a redesign. Behavior on re-run:
  - Compute a content hash of the **source** `SubDoc`. If a valid `.vi.srt` exists, the ledger says **we** created it, and the source hash is unchanged → **skip** (idempotent no-op).
  - Source changed (upgrade/re-grab) → **regenerate** and atomically overwrite our own output.
  - A `.vi.srt` exists that the ledger does **not** attribute to Trezarr → **skip + log, do NOT clobber** it (it may be a real downloaded/human Vietnamese sub — Bazarr-collision safety, Pitfall 10). A config override may allow take-over later.
  - A previously **quarantined** file is retried on re-run (not skipped).
  - Provenance recorded here is what lets the Phase 3/7 watcher avoid re-translating Trezarr's own output (re-processing loop, Pitfall 10b).

### Claude's Discretion
Per the delegation, planner/researcher retain full latitude on: exact module/package layout (e.g. `trezarr/translate/…`, `trezarr/validate/…`, `trezarr/output/…`), the token-estimation mechanism and its safety margin, the exact batch-packing algorithm and scene-gap threshold, neighbor-line count K, retry count N, the untranslated-ratio threshold, the sentinel token format, the ledger storage format (JSON vs a tiny SQLite seam), and prompt wording — provided the decisions above and the four phase success criteria hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/REQUIREMENTS.md` — ENG-02, ENG-03, ENG-06, ENG-07 (§Translation Engine) and FMT-05 (§Subtitle Formats); the five requirements this phase delivers
- `.planning/ROADMAP.md` §"Phase 2: Mechanical Translation Core + Validation Gate" — goal + 4 success criteria

### Research (risk & stack grounding) — high priority for this phase
- `.planning/research/PITFALLS.md` — **directly Phase-2-load-bearing.** The 1:1 cue invariant as a hard gate (retries → quarantine, never write); "validate before overwrite, always" check list (cue count, no empty/untranslated, valid encoding, parseable, monotonic timestamps); Pitfall 10 (Bazarr `.vi.srt` collision + watcher self-loop) → provenance/atomic-write requirements
- `.planning/research/ARCHITECTURE.md` — "API for knowledge, filesystem for action"; codec is LLM-agnostic; where the translate→gate→write seam sits
- `.planning/research/STACK.md` — OpenAI SDK v2 structured-output/JSON-mode patterns, `pydantic-settings` config surface (token-budget + thresholds live here)
- `.planning/research/SUMMARY.md` — phase sequencing rationale (why mechanical pass precedes the Series Bible)

### Phase 1 foundation this phase consumes
- `.planning/phases/01-codec-llm-client-foundation/01-CONTEXT.md` — D-01…D-11 (esp. D-04 structured-output degradation, D-08 byte-identical timing, D-09 tags-in-text, D-11 layered config)
- `trezarr/subtitles/model.py` — `SubDoc` (`lines`, `encoding`, `line_ending`, `separators`, `leading`, `trailer`) and `SubLine` (`index`, `start_tc`, `end_tc`, `text` ← the only LLM-mutable field, `raw`)
- `trezarr/subtitles/srt.py` — `read_srt()` / `write_srt()` (byte-identical round-trip; reuse for read-in and final serialize)
- `trezarr/llm/client.py` — `LLMClient.call(...)` (single async entry; semaphore + degradation already inside)
- `trezarr/config.py` — `TrezarrSettings` (`llm_context_window=32768`, `llm_max_concurrency=4`, `llm_model`, `llm_structured_output_mode`); add Phase-2 settings here (token budget, neighbor K, retry N, thresholds, quarantine/ledger paths)

### Project context
- `.planning/PROJECT.md` §Constraints, §Core Value — blind-trust quality bar (why the gate is non-negotiable); the Series Bible is *not* this phase

No external ADRs/specs exist (greenfield) — requirements are fully captured in REQUIREMENTS.md + the decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `read_srt()` / `write_srt()` (`trezarr/subtitles/srt.py`) — parse the source file in and serialize the translated `SubDoc` out; byte-identical guarantee means only `text` changes between read and write.
- `SubDoc` / `SubLine` (`trezarr/subtitles/model.py`) — `SubLine.text` is the sole mutable field; mutate it per cue and re-serialize. Timing/indices/separators carry through untouched.
- `LLMClient.call()` (`trezarr/llm/client.py`) — the async translation entry; already enforces the concurrency cap (D-06) and the structured-output→JSON→text degradation (D-04). Phase 2 calls it once per batch; do **not** add a second retry layer (D-07 double-retry warning).
- `TrezarrSettings` (`trezarr/config.py`) — extend with Phase-2 knobs rather than introducing a new config system (D-11 layered `pydantic-settings`).

### Established Patterns
- Timing-separable-from-text is the spine: the LLM only ever sees/returns cue `text`; the gate asserting timing byte-identity (D-16.4) is a near-free correctness check because timing never left local ownership.
- Structured-output degradation already exists — reuse it for the numbered-line batch protocol (D-13) instead of inventing a new transport.
- Async + `asyncio.Semaphore` concurrency is the established execution model; batch translation fans out under the same cap.

### Integration Points
- **Input:** Phase 2 receives a file path (or `SubDoc`). Phase 3 will be the producer that discovers and hands it over; design the entry as a clean callable (e.g. `translate_file(path, settings) -> result`) so Phase 3 can drive it.
- **Output seam:** the `/config` quarantine dir (D-18) and processed-files ledger (D-20) are new persistence surfaces that Phases 3/4/7 build on (ledger → Phase-4 `processed_file` table; provenance → Phase-3/7 watcher loop prevention).

</code_context>

<specifics>
## Specific Ideas

- The validation gate is the embodiment of the project's "blind trust" promise — per PITFALLS.md, *any* undetected error (truncation, partial translation, passed-through source lines, encoding garbage) becomes the trusted final file. Bias the gate toward **false rejects over missed misses**: a quarantined file is recoverable; a silently-wrong written file is not.
- Phase 2 deliberately produces *mechanically* translated Vietnamese with **no relational/pronoun consistency** — that is expected and not a defect. The gate validates structural integrity, not translation *quality of pronouns*; quality is Phases 4–6. Don't let the gate over-reach into semantic correctness it can't yet judge.

</specifics>

<deferred>
## Deferred Ideas

- **Series Bible / pronoun + relationship consistency** — the core value, but Phases 4–5. Phase 2's single mechanical pass is the substrate it will later wrap.
- **Two-pass (analyze → translate) and LLM self-review** — Phases 4 and 6.
- **File-watcher / re-processing-loop prevention** — Phase 3/7. Phase 2 only *establishes the provenance ledger* (D-20) that makes loop-prevention possible; it does not build the watcher.
- **Configurable "take over a foreign `.vi.srt`" override** — noted in D-20; concrete UI/config exposure can wait until the Web UI (Phase 7) unless trivially added.

</deferred>

---

*Phase: 2-Mechanical Translation Core + Validation Gate*
*Context gathered: 2026-05-31*
