# Phase 5: Three-Pass Pronoun Engine - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning
**Mode:** mvp (vertical slice — keep scope to the success criteria; do not gold-plate)
**Discussion mode:** `--auto` (recommended defaults auto-selected; every decision below is a sensible default the planner/researcher may tune)

<domain>
## Phase Boundary

Phase 5 makes the translation pipeline **Bible-aware** and ships the **core differentiator**: correct, consistent Vietnamese relational pronouns across an episode. It turns the Phase-2 mechanical translator (numbered-line batches → gate → write) into a multi-pass pipeline that reads from and writes to the Phase-4 Series Bible store.

Concretely, Phase 5 delivers:

1. **Pass 1 — Bible analysis (full-file, holistic).** Read the entire source subtitle file + the per-series `arr_metadata` snapshot + the *existing* Series Bible, and infer: characters (BIBLE-02 fields), term-dictionary entries (BIBLE-04), the series `register` (BIBLE-05), and the **directed Address Map** (BIBLE-03 — per ordered character pair: `self_term` + `address_term`). Merge everything into the Bible via the Phase-4 `merge_inferred` contract (locks + provenance respected). (ENG-04, BIBLE-03, BIBLE-05)
2. **Pass 2 — Speaker/addressee attribution (per-line, batched).** For each dialogue cue, infer the speaker and the addressee from dialogue content, turn-taking, and vocatives, with a confidence value. Subtitles carry no speaker labels — this is pure LLM inference. (PRON-01)
3. **Deterministic reconciliation.** Resolve each observed ordered pair to **one** pronoun pair for the whole episode and write/merge it into the Address Map, so the same pair never flips inside an exchange and reciprocal directions stay coherent. (success criterion #3)
4. **Pass 3 — Pronoun-aware translation (per-line, batched).** Translate each cue applying the resolved `(self_term, address_term)` from the Address Map; when attribution was low-confidence, fall back to a safe neutral/polite default rather than risk a wrong intimate pronoun. (PRON-02, PRON-03)

Requirements covered: **ENG-04** (two-pass: analyze full file → build Bible before translating), **BIBLE-03** (directed Address Map populated), **PRON-01** (speaker/addressee inference), **PRON-02** (apply pronoun pair), **PRON-03** (low-confidence → safe register fallback). Also populates **BIBLE-05** `register` (schema shipped Phase 4; D-35 assigned the LLM population to this phase).

**In scope:**
- A `trezarr/bible/analyze.py` (or similar) Pass-1 analyzer producing a Pydantic `BibleAnalysis` and merging via `store.merge_inferred` / `upsert_character` / `upsert_term` and new Address-Map writes.
- Address-Map write support in `trezarr/bible/store.py` (Phase 4 created the table empty; this phase INSERTs/merges rows).
- A `trezarr/translate/attribute.py` (or similar) Pass-2 attributor producing per-cue `(speaker, addressee, confidence)`.
- Deterministic per-episode pronoun reconciliation feeding the Address Map.
- Pass-3 prompt extension in `trezarr/translate/engine.py` (`build_translate_prompt`) to carry per-line pronoun hints.
- `translate_file` signature/flow extended to thread the `MediaItem`/`EligibleItem` + a Bible store handle, do lazy `get_or_create_series` (D-36), run Pass 1 (barrier) → Pass 2 → reconcile → Pass 3 → existing gate → write.
- New `TrezarrSettings` fields (confidence threshold, safe-default pronoun pair, attribution batch knobs, pass toggles).
- New Pydantic DTOs/response models for `BibleAnalysis` and `LineAttribution`, plus an `AddressMapDTO` at the store boundary.

**Out of scope (deferred to owning phases):**
- **Relationship evolution** across episodes (enemies→lovers, episode-marked transitions, `relationship_event` table) — **Phase 6** (BIBLE-07). Phase 5 writes a static-per-episode Address Map; Phase 6 makes it evolve.
- **LLM self-review / self-critique pass** over the translated output — **Phase 6** (ENG-05).
- **Bible editor UI + production lock-setting** — **Phase 8** (BIBLE-08/09). Phase 5 only *respects* locks via the Phase-4 merge contract.
- **Source-language selection / multi-source prioritization** — **Phase 10** (SRC-01/02). Phase 5 translates whatever single source `EligibleItem.source_lang` already gives it.
- **Surfacing low-confidence lines in a UI** (OBS-01) — **v2**. Phase 5 only logs them; the safe-default fallback is the v1 behavior.
- **Bazarr inventory / continuous daemon** — Phases 7/10.

</domain>

<decisions>
## Implementation Decisions

Continues the project decision ledger (Phase 1 D-01…D-11, Phase 2 D-12…D-20, Phase 3 D-21…D-30, Phase 4 D-31…D-39). Phase 5 = **D-40…D-50**. All numbered values are sensible defaults the planner/researcher may tune; all are overridable in planning.

### Pass architecture (D-40)
- **D-40: Three distinct LLM passes — Analyze → Attribute → Translate.** This honors the phase title ("Three-Pass") and, critically, lets consistency be *enforced deterministically* between attribution and translation rather than hoped for inside one entangled prompt.
  - **Pass 1 (analyze)** is a **barrier**: it must complete and the Bible (incl. Address Map) must be merged before Pass 2/3 run. Pass 1 is file-level/holistic (one or few calls over the whole file, chunked only if it exceeds the token budget).
  - **Pass 2 (attribute)** and **Pass 3 (translate)** are each internally concurrent over batches via `asyncio.gather`, reusing the Phase-2 `batch_subdoc` packing so cue grouping/context windows are identical across passes.
  - Note: the ROADMAP goal phrases attribution+application loosely under "Pass 2"; we split them (attribute as Pass 2, translate as Pass 3) so the reconciliation gate (D-44) and the low-confidence gate (D-45) sit cleanly between inference and output. Folding Pass 2 into Pass 3 is the documented fallback if call cost becomes a problem (cost is explicitly out of v1 scope).

### Pass 1 — Bible analysis (D-41)
- **D-41: Pass 1 grounds on the existing Bible, infers, then merges.** Load `load_series_bible(series_id)` first; include existing characters / terms / register / address-map in the Pass-1 prompt as grounding so inference *extends* prior episodes instead of re-deriving them (BIBLE-06 carry-forward). Pass 1 returns a Pydantic `BibleAnalysis`; apply it through the Phase-4 contract — `merge_inferred` for register, `upsert_character` / `upsert_term` for entities, new Address-Map writes for pairs (D-42). Register is inferred from `arr_metadata` (genre/overview/year/network) + the dialogue itself (D-35). Locks and `bible_event` provenance come for free from the Phase-4 store — Phase 5 never bypasses `merge_inferred`.

### Address Map population (D-42)
- **D-42: Observed/exchanging ordered pairs only — never N² enumeration.** Pass 1 emits Address-Map entries only for ordered `(speaker→addressee)` pairs that actually exchange dialogue in the analyzed file, plus any pairs already carried forward in the Bible. `self_term` / `address_term` are stored in the existing single-string columns (Phase-4 schema, unchanged). When only one direction of a pair is observed, the reciprocal may be inferred from the standard Vietnamese kinship-pair table and written **unlocked + lower-confidence** so a human or a later episode can correct it. Reciprocal coherence (A→B "anh/em" ⇒ B→A "em/anh") is checked during reconciliation (D-44). `valid_from_episode` is set to the current episode key (D-49); Phase 6 will use it for evolution.

### Pass 2 — attribution (D-43)
- **D-43: Batched per-cue attribution returning `(speaker, addressee, confidence)`.** Pass 2 runs over the same batches as translation but with a **wider read-only context window** (turn-taking and vocatives need more neighbors than mechanical translation) — a separate `attribute_context_lines_k`, default larger than `translate_context_lines_k`. Output is a Pydantic `LineAttribution` per cue: `speaker` (character name or `null`/`unknown`), `addressee` (name or `null`), `confidence` (0–1 or an enum `high|medium|low`). Speaker/addressee names are matched back to Bible `original_latin_name`; unmatched names do not crash the file — they resolve to the safe default (D-45).

### Deterministic reconciliation (D-44)
- **D-44: One pronoun pair per ordered pair per episode, resolved deterministically, persisted to the Address Map.** After Pass 2, for each observed ordered pair pick a single `(self_term, address_term)` (first high-confidence attribution wins; tie-break by frequency) and write/merge it into the Address Map. Pass 3 then **looks up** the pair deterministically rather than re-deciding per line — this makes success criterion #3 ("no flips inside an exchange; reciprocal directions consistent") structural, not LLM-dependent. The Address Map row is the single source of truth.

### Low-confidence fallback (D-45)
- **D-45: Below the confidence threshold → safe neutral/polite default pair; never risk an intimate pronoun.** A configurable `pronoun_confidence_threshold` (default ~`0.6` / `medium`) gates pronoun application. Below it (or when speaker/addressee is unknown/unmatched), Pass 3 uses a configurable `pronoun_safe_default` — a neutral-polite pair (e.g. self=`tôi`, address chosen by inferred gender when known: `anh`/`chị`, else neutral `bạn`). This directly satisfies PRON-03 and is the v1 substitute for confidence-flagging UI (OBS-01, v2). Low-confidence lines are logged, not surfaced.

### Pass 3 — pronoun application (D-46)
- **D-46: Per-line pronoun hints in the translation prompt; no mechanical replacement.** Extend `build_translate_prompt` so each numbered line can carry its resolved `self_term`/`address_term` as an instruction (e.g. `[3] (speaker→self: anh; →addressee: em) <source text>`), letting the model produce natural Vietnamese using those terms. Mechanical post-hoc pronoun substitution is **rejected** — Vietnamese pronoun placement is context-sensitive and string replacement corrupts it. The numbered-line 1:1 protocol, sentinel protection (D-12), and the document gate (D-16/D-17) are all preserved unchanged.

### Structured output strategy (D-47)
- **D-47: Pydantic `response_model` for Pass 1 & Pass 2; Pass 3 stays on the numbered-line text protocol.** Reuse the Phase-1 `LLMClient.call(messages, response_model=...)` three-tier path (json_schema → json_object → text). Practical floor for the structured passes is Tier 2 (`json_object`). If an endpoint can only do Tier 3 (plain text) for a structured pass, **degrade gracefully**: treat all attribution as low-confidence → safe default (D-45) rather than failing the file. Pass 3 must never request `response_model` (it uses the existing forgiving numbered-line parser).

### Pipeline wiring (D-48)
- **D-48: `translate_file` is extended to be Bible-aware; whole-Bible failure quarantines, it never writes a wrong-pronoun file.** Thread the `EligibleItem`/`MediaItem` (for `arr_kind`/`series_id`/`arr_metadata`/episode identity) and a Bible store handle (`session_factory`) into `translate_file`. Flow: `get_or_create_series` (lazy, D-36) → `load_series_bible` → **Pass 1 (barrier) + merge** → reload Bible (now with Address Map) → **Pass 2 (gather)** → **reconcile (D-44)** → **Pass 3 (gather)** → existing `validate_subdoc` gate → atomic write → `ledger.record(done)`. Failures in Pass 1/2 follow the existing per-file quarantine pattern (D-18/D-30) — a file we can't analyze/attribute is quarantined, never written with guessed pronouns (consistency is non-negotiable). **The sole concurrency gate remains `LLMClient._semaphore`** — no new `asyncio.Semaphore` in the engine (Pitfall 1). The CLI loop in `cli.py` passes the `eligible_item` and `session_factory` it already holds.

### Episode key + movies (D-49)
- **D-49: `episode_key = f"S{season:02d}E{episode:02d}"` for episodes; movies use a stable single-episode key (e.g. `"movie"` or the tmdb/title slug).** This keys carry-forward and `bible_event` provenance. Movies still get a Bible + Address Map (one "episode"); they simply never accumulate cross-episode history. Exact movie-key shape is Claude's discretion as long as it is stable and idempotent.

### New settings (D-50)
- **D-50: New `TrezarrSettings` fields, layered per the existing convention.** At minimum: `pronoun_confidence_threshold`, `pronoun_safe_default` (self + address, possibly gendered), `attribute_context_lines_k`, optional `enable_pass1_analysis` / `enable_attribution` toggles (for staged rollout + tests), and any Pass-1 chunking knobs. Group under a Phase-5 comment header in `config.py`, mirroring the Phase-3/4 grouping.

### Claude's Discretion
Planner/researcher retain latitude on: exact module layout (`trezarr/bible/analyze.py`, `trezarr/translate/attribute.py`, `trezarr/translate/reconcile.py` vs folding into `engine.py`); the precise Pydantic shapes of `BibleAnalysis` / `LineAttribution` / `AddressMapDTO`; whether confidence is a float or an enum; the exact pronoun-hint prompt syntax; the standard Vietnamese kinship-pair reciprocal table contents; whether Pass 1 chunks long files and how it merges chunk results; the reconciliation tie-break rule; the movie episode-key string; whether the Address-Map store API is `upsert_address` mirroring `upsert_character` or a dedicated merge; how attribution failure vs translation failure are distinguished in the quarantine reason; default numeric values for all new settings; and whether to add an Address-Map read accessor (`get_address_pair(series_id, speaker_id, addressee_id)`) to the store.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/REQUIREMENTS.md` §Translation Engine — **ENG-04** (two-pass analyze→translate); §Series Bible — **BIBLE-03** (directed Address Map), **BIBLE-05** (register grounding), **BIBLE-06** (carry-forward, the constraint Pass 1 must honor); §Pronoun Attribution — **PRON-01, PRON-02, PRON-03** (the heart of this phase)
- `.planning/ROADMAP.md` §"Phase 5: Three-Pass Pronoun Engine" — goal + 4 success criteria (esp. #3 consistency, #4 low-confidence fallback)

### Prior-phase foundations this phase consumes & extends
- `.planning/phases/04-series-bible-store-schema/04-CONTEXT.md` — **D-35** (`arr_metadata` snapshot Pass-1 reads for register; Phase 5 sets `register` via `merge_inferred`), **D-36** (lazy `get_or_create_series` on first translate — the wiring point), **D-39** (Pydantic DTOs at the store boundary; Phase 5 must NOT import SQLAlchemy), **D-34** (lock precedence `merge_inferred` enforces — Pass-1 inferences yield to locks), **D-32** (`bible_event` provenance written automatically on every merge), **D-31** (Address-Map / register tables already exist empty — Phase 5 only INSERTs/merges)
- `.planning/phases/02-mechanical-translation-core-validation-gate/02-CONTEXT.md` — **D-12** (sentinel inline-tag protection — preserved through Pass 3), **D-13** (numbered-line 1:1 protocol — Pass 3 keeps it), **D-14/D-15** (`batch_subdoc` packing + context window — reused by Pass 2 & Pass 3), **D-16/D-17** (document gate — unchanged), **D-18/D-30** (per-batch/per-file quarantine pattern — extended to Pass 1/2 failures)
- `.planning/phases/01-codec-llm-client-foundation/01-CONTEXT.md` — **D-03/D-04** (`LLMClient` three-tier structured output — Pass 1 & 2 use `response_model`; Pass 3 uses text), **D-06** (sole `asyncio.Semaphore` lives in `LLMClient` — no new semaphore in the engine), **D-11** (layered `pydantic-settings` — new Phase-5 fields go here)

### Existing code to reuse / extend (do not reinvent)
- `trezarr/translate/engine.py` — `translate_file` (extend signature + flow), `build_translate_prompt` (extend for pronoun hints — D-46), `_translate_batch` / numbered-line parser (Pass 3 reuses verbatim), quarantine + ledger pattern (extend to Pass 1/2)
- `trezarr/translate/batching.py` — `batch_subdoc` / `Batch` (Pass 2 & Pass 3 reuse; Pass 2 may pass a larger context K)
- `trezarr/llm/client.py` — `LLMClient.call(messages, response_model=...)` (the structured-output path for Pass 1 & 2; returns a typed Pydantic object on Tier 1)
- `trezarr/bible/store.py` — `get_or_create_series`, `load_series_bible`, `upsert_character`, `upsert_term`, `merge_inferred` (Pass-1 merge); **add Address-Map write/read** here
- `trezarr/bible/dto.py` — `SeriesBibleDTO`, `CharacterDTO`, `TermDTO` (read side); **add `AddressMapDTO`**
- `trezarr/bible/models.py` — `AddressMap` ORM model (columns `speaker_character_id`, `addressee_character_id`, `self_term`, `address_term`, `valid_from_episode`, `locked_fields`) — INSERT/merge into it
- `trezarr/discover/scan.py` — `EligibleItem` (`media_item`, `source_sub_path`, `source_lang`) — the input carrier threaded into `translate_file`
- `trezarr/arr/sonarr.py` — `MediaItem` (`series_id`, `season_number`, `arr_kind`, `tvdb_id`, `tmdb_id`, `genres`, `overview`, `year`, `network`, `runtime`, `title`, `source_type`) — source of identity + register grounding
- `trezarr/cli.py` — the translate loop (~L291) that calls `translate_file`; it already holds `session_factory` (L176) and `eligible_item` to pass through
- `trezarr/config.py` — `TrezarrSettings` (add Phase-5 fields — D-50)

### Research (risk & stack grounding)
- `.planning/research/PITFALLS.md` — re-check anything tagged LLM / concurrency / structured-output / prompt-injection / Vietnamese-text; specifically Pitfall 1 (single semaphore) and Pitfall 5 (don't quarantine on transient API errors) which Pass 1/2 must also obey
- `.planning/research/ARCHITECTURE.md` — Series Bible as the consistency substrate; the two-pass→three-pass pipeline shape; "API for knowledge, filesystem for action"
- `.planning/research/STACK.md` — OpenAI SDK structured-output (`chat.completions.parse`) patterns and the json_schema→json_object→text degradation already implemented
- `.planning/research/FEATURES.md` — the relational-pronoun / Address-Map problem framing (why this is the moat)

### Project-wide grounding
- `CLAUDE.md` §"Stack Patterns by Variant" / "OpenAI-Compatible Client" — structured-output fallback, semaphore-bounded concurrency, "translate only dialogue text" rule
- `.planning/PROJECT.md` §Core Value / Key Decisions — "consistency is non-negotiable" (drives D-44/D-45/D-48: quarantine over guess), "LLM infers speaker/addressee from context"

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`translate_file` (`engine.py`)** — the single entry point; Phase 5 wraps Pass 1 around it and inserts Pass 2 + reconcile before the existing Pass-3 translation/gate/write. Its quarantine + ledger idempotency machinery is reused for Pass-1/2 failures.
- **`batch_subdoc` / `Batch` (`batching.py`)** — already packs cues at scene/token boundaries with read-only context neighbors; Pass 2 (attribution) and Pass 3 (translation) both run over these batches. Pass 2 wants a larger context K (turn-taking needs more neighbors).
- **`LLMClient.call(..., response_model=...)` (`llm/client.py`)** — returns a *typed* Pydantic object on Tier 1 and a JSON/text string on Tiers 2/3; exactly the structured-output surface Pass 1 (`BibleAnalysis`) and Pass 2 (`LineAttribution`) need. The semaphore inside it is the only concurrency gate — do not add another.
- **Phase-4 store API (`bible/store.py`, `bible/dto.py`)** — `load_series_bible` (read), `merge_inferred` / `upsert_*` (write with lock precedence + provenance). Phase 5 adds an Address-Map writer here and never touches SQLAlchemy outside `store.py` (D-39).
- **`AddressMap` model (`bible/models.py`)** — table + columns already exist empty from the Phase-4 baseline migration; **no new migration needed** to populate it.

### Established Patterns
- **Numbered-line 1:1 protocol + sentinel protection + document gate** (D-12/D-13/D-16/D-17) — Pass 3 keeps all of it; pronoun hints ride alongside the numbered lines without breaking the 1:1 mapping.
- **`merge_inferred` precedence `human lock > prior value > new inference`** (D-34) — every Pass-1 write goes through it; Phase 5 produces inferences, never sets locks.
- **Per-file quarantine + ledger idempotency** (D-18/D-19/D-20/D-30) — extended: a file that fails analysis/attribution is quarantined with a clear reason, never written with guessed pronouns.
- **Pydantic everywhere at boundaries; no SQLAlchemy leakage** (D-39) — new DTOs/response models follow this; the engine/attributor import only `trezarr.bible.dto`.
- **Single `asyncio.Semaphore` in `LLMClient`** (D-06, Pitfall 1) — all three passes call through it; the engine adds no semaphore.

### Integration Points
- **`cli.py` translate loop (~L291)** — change the `translate_file(source_sub_path, settings, llm_client, ledger)` call to also pass `eligible_item` (or its `media_item`) and `session_factory` (both already in scope at L176/L291).
- **`translate_file` entry** — `get_or_create_series` (lazy, D-36) using `MediaItem.arr_kind` / `series_id` / snapshot fields, then `load_series_bible`, then Pass 1 (barrier) before any line is attributed or translated (ENG-04 ordering).
- **Bible store ↔ Address Map** — Pass 1 writes pairs; reconciliation (D-44) finalizes one pair per ordered pair; Pass 3 reads them back. Add a read accessor if the planner deems it cleaner than carrying the reconciled map in memory.

</code_context>

<specifics>
## Specific Ideas

- **The phase title says "Three-Pass" but the ROADMAP goal text describes two.** Resolution: Analyze (Pass 1) → Attribute (Pass 2) → Translate (Pass 3). The split exists specifically so the **deterministic reconciliation gate** (D-44) and the **low-confidence safe-default gate** (D-45) sit between inference and output — that is how success criteria #3 and #4 become structural guarantees instead of prompt-quality gambles.
- **Consistency is non-negotiable → prefer quarantine over a guessed pronoun.** When in doubt at the *file* level (Pass 1/2 can't produce a usable Bible/attribution), quarantine. When in doubt at the *line* level, apply the safe neutral pair (D-45). Never write an intimate pronoun on a guess.
- **The Address Map is the single source of truth** the LLM is *told*, not *asked* — Pass 3 receives the resolved pair as an instruction and the model renders natural Vietnamese around it. This is the inversion that buys consistency.
- **Reciprocal kinship coherence** (A→B "anh/em" ⇒ B→A "em/anh") is a known, small Vietnamese table — encode it for reconciliation rather than asking the LLM to keep both directions straight.

</specifics>

<deferred>
## Deferred Ideas

- **Relationship evolution across episodes** (enemies→lovers, episode-marked transitions, `relationship_event` table) → **Phase 6** (BIBLE-07). Phase 5's Address Map is static-per-episode with `valid_from_episode` set; Phase 6 makes the active pair change intentionally over the series.
- **LLM self-review / self-critique pass** over translated output before the gate → **Phase 6** (ENG-05). It will re-read the output and check Bible adherence; Phase 5 ships the Bible it checks against.
- **Confidence-flagging low-certainty lines in the UI** (OBS-01) → **v2**. Phase 5 logs them and falls back to the safe pair.
- **Source-language selection / multi-source prioritization** (prefer zh/ko/ja over en for relational fidelity) → **Phase 10** (SRC-01/02). Phase 5 uses the single source `EligibleItem.source_lang` already chosen upstream.
- **Bible editor UI + production lock-setting** (BIBLE-08/09) → **Phase 8**. Phase 5 respects locks; it never sets them.
- **`arr_metadata` refresh policy** (re-pull on series update) → tuning concern, Phase 10 per-series overrides.
- **Folding Pass 2 into Pass 3** to cut LLM calls → revisit only if cost becomes a concern (out of v1 scope); the D-40 split is the default.

None of these block Phase 5. Discussion stayed within phase scope.

</deferred>

---

*Phase: 05-three-pass-pronoun-engine*
*Context gathered: 2026-06-01*
