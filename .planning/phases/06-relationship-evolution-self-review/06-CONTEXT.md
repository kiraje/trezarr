# Phase 6: Relationship Evolution + Self-Review - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning
**Mode:** mvp (vertical slice — keep scope to the success criteria; do not gold-plate)
**Discussion mode:** `--auto` (recommended defaults auto-selected; every decision below is a sensible default the planner/researcher may tune)

<domain>
## Phase Boundary

Phase 6 **deepens the proven consistency core** from Phase 5 with two capabilities, on top of the now-shipped three-pass pronoun engine. It adds no new translation surface and no new format/integration — it makes the existing pipeline *aware of time* (relationships change across episodes) and *self-correcting* (the model checks its own output against the Bible before the gate).

Concretely, Phase 6 delivers:

1. **Relationship evolution across episodes (BIBLE-07).** A relationship shift (strangers→lovers, enemies→rivals) is recorded as an **episode-marked `relationship_event`** row. The active pronoun pair for that ordered character pair then **changes intentionally from that episode forward** — never by silent drift. The Address Map's current row is the active pair; a logged transition is the *only* thing that authorizes its terms to change for an already-established pair. The change is fully auditable via the `bible_event` + `relationship_event` logs (success criterion #3).

2. **LLM self-review pass (ENG-05).** After Pass 3 produces the translated Vietnamese document and **before** the hard `validate_subdoc` gate, a new self-review pass re-reads the output, checks Series Bible adherence (resolved pronoun pairs, Term Dictionary renderings, register/tone), and **corrects violations**. It is best-effort: it can only improve the file, never block it. The existing document gate remains the sole arbiter of what gets written.

Requirements covered: **BIBLE-07** (relationship evolution with episode markers) and **ENG-05** (LLM self-review pass over translated output, checking Bible adherence and correcting violations before finalizing).

**In scope:**
- Light up the **empty `relationship_event` table** (Phase 4 created the schema; Phase 6 INSERTs the first rows) with a store writer + a `RelationshipEventDTO`, and extend `load_series_bible` so reconciliation can see logged transitions.
- **Extend Pass 1** (`trezarr/bible/analyze.py`) so the holistic `BibleAnalysis` also emits `relationship_events` — detected only when a relationship has *changed* vs the carried-forward Bible.
- **Extend reconciliation** (`trezarr/translate/reconcile.py`) so a logged transition for an established pair lets the resolved `(self_term, address_term)` change and bumps `valid_from_episode` to the current episode; absent a transition, the prior pair carries forward unchanged (BIBLE-06).
- A new **self-review pass** (Pass 4) in the Bible-aware branch of `translate_file`, inserted between Pass-3 assembly and `validate_subdoc`, reusing `batch_subdoc`, the numbered-line protocol, and sentinel protection.
- New **Phase-6 `TrezarrSettings`** fields (toggles + review batch/context knobs), grouped under a Phase-6 header mirroring D-50.

**Out of scope (deferred to owning phases / v2):**
- **Retroactive re-translation of earlier episodes** when a later relationship change is logged — v1 translates *forward only*; a transition applies from its episode marker onward, it does not re-render S01E01.
- **Editable / lockable relationship events** (human override of a transition) — **Phase 8** (the override valve). Phase 6 only *respects* existing locks via the merge contract; it never sets locks.
- **Surfacing the relationship timeline or self-review corrections in a UI** — **Phase 7/8** (queue/history/Bible editor).
- **Iterative multi-pass self-review** (review-the-review loops) — single review pass for v1.
- **Confidence-flagging self-review corrections in the UI** (OBS-01) — **v2**.
- **Source-language selection / multi-format / Bazarr inventory** — Phases 9/10.

</domain>

<decisions>
## Implementation Decisions

Continues the project decision ledger (Phase 1 D-01…D-11, Phase 2 D-12…D-20, Phase 3 D-21…D-30, Phase 4 D-31…D-39, Phase 5 D-40…D-50). Phase 6 = **D-51…D-60**. All numbered values are sensible defaults the planner/researcher may tune; all are overridable in planning.

### Capability A — Relationship Evolution (BIBLE-07)

#### Transition detection source (D-51)
- **D-51: Detect relationship transitions inside the existing Pass-1 holistic analysis — do NOT add a separate LLM pass.** The Pass-1 analyzer already reads the **full source file + the existing carried-forward Bible + arr metadata** in one holistic call; relationship change detection is the same shape of reasoning. Extend the `BibleAnalysis` Pydantic model with `relationship_events: list[RelationshipEventInference]` (fields: `character_a_name`, `character_b_name`, `episode_marker`, `description`, optionally a suggested new `self_term`/`address_term`). The LLM is instructed to emit an entry **only when a relationship has changed relative to the Bible context it was given** — not for every co-occurring pair. This reuses one call (no extra round-trip / cost) and keeps the analyze→merge flow intact. Rejected: a dedicated transition-detection pass (extra LLM call, out of v1 cost scope) and a pure deterministic address-pair diff (can't read narrative intent — "they fell in love" isn't a term change yet).

#### Storage + DTO (D-52)
- **D-52: INSERT `relationship_event` rows via a store writer, exposed as a `RelationshipEventDTO` at the boundary (D-39).** Add `record_relationship_event(...)` (or `upsert_relationship_event`) to `trezarr/bible/store.py` — name back-matched to Bible characters by the **case-insensitive `.strip().lower()` contract** (CR-01; see Memory). Add `RelationshipEventDTO` to `trezarr/bible/dto.py` and load events into `SeriesBibleDTO` via `load_series_bible` (or a sibling loader) so reconciliation can see them without importing SQLAlchemy. No migration — the table already exists from the Phase-4 baseline (D-31). Each write still rides the `bible_event` provenance pattern where it changes Bible state (D-32).

#### Active-pair evolution semantics (D-53)
- **D-53: The mutable-current Address Map row IS the active pair; `valid_from_episode` is the version marker; a logged transition is the sole authorization to change an established pair.** This honors Phase 4 D-32 (mutable current + append-only audit) and Phase 5 D-42/D-49 (`valid_from_episode` reserved for exactly this). When a `relationship_event` for ordered pair `(A,B)` fires at episode N, reconciliation is **permitted** to write changed `(self_term, address_term)` for that pair and set `valid_from_episode = N`. The `bible_event` log records before→after; the `relationship_event` row is the narrative marker. Together they make success criterion #3 ("consistent pair across a logged change, change auditable") structural, not prompt-dependent. v1 translates forward, so "active as of episode N" for the current translate is simply the current row (already updated through N).

#### Drift guard / reconciliation precedence (D-54)
- **D-54: Reconciliation precedence becomes `human lock > logged transition (this episode) > carried-forward prior pair > new low-confidence inference`.** This is the central Phase-6 change to `reconcile.py`. Phase 5 already preserves an existing pair's terms for "confirmed" pairs (it reuses the existing Address Map entry rather than overwriting) — that default stays. Phase 6 adds the **one** legitimate way for an *established* pair's terms to change: a `relationship_event` for that pair this episode. The new terms come from the transition's suggested terms if the LLM provided them, else from this episode's high-confidence reconciled attribution for the pair (D-44 machinery). No event ⇒ the carried-forward pair wins ⇒ no silent drift (this is what "intentionally, not by silent drift" means in success criterion #1).

### Capability B — LLM Self-Review Pass (ENG-05)

#### Insertion point (D-55)
- **D-55: A new "Pass 4 — self-review" runs in `translate_file` AFTER Pass-3 assembly and BEFORE `validate_subdoc`.** Roadmap success criterion #2 is explicit: "corrects violations **before** the validation gate." It lives in the Bible-aware branch only (gated on `eligible_item` + `session_factory`, like the Phase-5 passes); the Phase-3 mechanical path (no Bible) is unchanged. Concretely it slots between current engine Step 8 (assemble `translated_doc`) and Step 9 (`validate_subdoc`).

#### Review granularity (D-56)
- **D-56: Batched review, reusing `batch_subdoc`, concurrent via `asyncio.TaskGroup`, gated solely by `LLMClient._semaphore`.** No new `asyncio.Semaphore` anywhere (D-06, Pitfall 1). Each review batch prompt carries: the source line, the Pass-3 Vietnamese line, and **compact Bible context** for that line — the resolved pronoun pair for its speaker→addressee, the relevant Term Dictionary entries, and the series register. Whole-file single-call review is rejected (token blow-up on long files; batching matches the established Pass-2/Pass-3 shape and reuses the same cue grouping).

#### Correction protocol (D-57)
- **D-57: Numbered-line "corrected output" protocol — reuse `parse_numbered_response` + `extract_sentinels`/`reinsert_sentinels`.** The reviewer returns the (possibly corrected) Vietnamese for each numbered line; lines it leaves unchanged pass through verbatim. This preserves the 1:1 cue mapping (D-13) and inline-tag integrity (D-12), and slots into the existing assembly machinery. Pass 4 must **not** request a Pydantic `response_model` — it uses the forgiving numbered-line text path like Pass 3 (D-47). Structured-diff correction is rejected (re-introduces a parsing surface and risks index drift).

#### What the reviewer checks (D-58)
- **D-58: Scope the review to Bible adherence only — not free re-translation or "style improvement."** The reviewer checks (1) the pronoun pair matches the resolved Address Map for the line's speaker→addressee, (2) proper nouns/titles use the Term Dictionary rendering, (3) register/tone consistency. It is instructed **not** to paraphrase or "improve" lines that already adhere — this prevents the reviewer from drifting an otherwise-correct translation. Character/name matching to the Bible uses the case-insensitive `.strip().lower()` contract (CR-01).

#### Failure & safety semantics (D-59)
- **D-59: Self-review is BEST-EFFORT — it can only improve, never quarantine.** On any review failure (`openai.APIError`, numbered-line/sentinel integrity failure, or a Tier-3-only endpoint that can't do the review reliably), fall back to the **pre-review Pass-3 line(s)** for that batch and proceed. The self-review pass NEVER, by itself, marks a file quarantined; the hard `validate_subdoc` gate remains the sole arbiter and runs once on the final assembled doc. Rationale: consistency is non-negotiable, and a flaky reviewer must not be able to turn a good translation into a quarantine (Pitfall 5 — never quarantine on transient endpoint errors).

#### Settings + staged rollout (D-60)
- **D-60: New Phase-6 `TrezarrSettings` fields under a Phase-6 comment header, mirroring the D-50 grouping.** At minimum: `enable_relationship_events: bool = True` and `enable_self_review: bool = True` (staged-rollout + test toggles), plus self-review batch/context knobs (`self_review_context_lines_k`, `self_review_max_cues_per_batch`) and optionally a `relationship_event_min_confidence` gate for emitting transitions. All overridable; defaults are Claude's discretion.

### Claude's Discretion
Planner/researcher retain latitude on: module layout (a new `trezarr/translate/review.py` vs folding Pass 4 into `engine.py`; extending `analyze.py` vs a small `relationship.py` helper); the exact Pydantic shapes of `RelationshipEventInference`, `RelationshipEventDTO`, and any `ReviewCorrection` model; whether a transition re-derives terms from attribution or trusts the LLM-suggested terms (D-54 allows either, prefer suggested-then-fallback); the precise self-review prompt and how much Bible context each batch carries; whether `load_series_bible` eager-loads `relationship_events` or a separate loader is added; the reconciliation tie-break when a lock and a transition both touch a pair (lock wins — D-34); the exact new setting names and numeric defaults; the store writer's name (`record_relationship_event` vs `upsert_relationship_event`) and its dedup key `(series_id, character_a, character_b, episode_marker)`; and whether self-review compares against a freshly reloaded Bible or the in-memory `resolved_map` already in scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/REQUIREMENTS.md` §Series Bible — **BIBLE-07** (relationship evolution with episode markers); §Translation Engine — **ENG-05** (LLM self-review over translated output, check Bible adherence, correct before finalizing); §Series Bible **BIBLE-06** (carry-forward — the invariant Phase 6 must not break) and **BIBLE-03** (the directed Address Map being evolved)
- `.planning/ROADMAP.md` §"Phase 6: Relationship Evolution + Self-Review" — goal + 3 success criteria (esp. #1 "intentional, not silent drift", #2 "self-review before the gate", #3 "consistent across a logged change, auditable")

### Prior-phase foundations this phase consumes & extends
- `.planning/phases/05-three-pass-pronoun-engine/05-CONTEXT.md` — **D-42**/**D-49** (`valid_from_episode` set on Address Map rows specifically so Phase 6 evolves the active pair), **D-44** (deterministic reconciliation — the seam Phase 6 extends), **D-45** (safe-default gate — preserved), **D-46** (per-line pronoun hints — Pass 4 reviews these), **D-48** (the Bible-aware `translate_file` branch Pass 4 plugs into), **D-50** (settings grouping pattern Phase 6 mirrors)
- `.planning/phases/04-series-bible-store-schema/04-CONTEXT.md` — **D-31** (the `relationship_event` table already exists empty — Phase 6 only INSERTs; no migration), **D-32** (mutable-current + append-only `bible_event` log — the audit substrate that makes a relationship change auditable), **D-34** (lock precedence `merge_inferred` enforces — locks beat a transition), **D-39** (Pydantic DTOs at the store boundary — `RelationshipEventDTO`; no SQLAlchemy leakage)
- `.planning/phases/02-mechanical-translation-core-validation-gate/02-CONTEXT.md` — **D-12** (sentinel inline-tag protection — Pass 4 reuses), **D-13** (numbered-line 1:1 protocol — Pass 4 reuses), **D-14/D-15** (`batch_subdoc` packing + context window — Pass 4 reuses), **D-16/D-17** (document gate — runs once, after self-review), **D-18/D-30** (quarantine pattern — self-review must NOT add a new quarantine trigger, D-59)

### Existing code to reuse / extend (do not reinvent)
- `trezarr/translate/engine.py` — `translate_file` Bible-aware branch (insert Pass 4 between assembly and `validate_subdoc`), `build_translate_prompt` / `parse_numbered_response` (Pass 4 reuses the numbered-line protocol), `_translate_batch` / `asyncio.TaskGroup` dispatch pattern (mirror for review batches), `_write_quarantine` (NOT triggered by review failure — D-59)
- `trezarr/translate/reconcile.py` — `reconcile_attributions` (extend with transition precedence — D-54), `KINSHIP_RECIPROCAL`, `get_safe_default` (unchanged); the `name_to_id` case-insensitive index pattern (CR-01)
- `trezarr/bible/analyze.py` — `BibleAnalysis` / `AddressMapInference` / `_build_analysis_prompt` / `analyze_file` / `merge_bible_analysis` (extend to emit + merge `relationship_events` — D-51)
- `trezarr/bible/store.py` — `load_series_bible` (extend to load relationship events), `upsert_address_pair` / `_upsert_address_pair_in_session` (the `valid_from_episode` write path — D-53), `merge_inferred` (lock precedence); **add** a relationship-event writer here
- `trezarr/bible/models.py` — `RelationshipEvent` ORM model (columns `series_id`, `character_a_id`, `character_b_id`, `episode_marker`, `description`, `created_at`) — INSERT only; `AddressMap` (`valid_from_episode`, `locked_fields`); `BibleEvent` (audit)
- `trezarr/bible/dto.py` — `SeriesBibleDTO`, `AddressMapDTO` (read side); **add** `RelationshipEventDTO`
- `trezarr/translate/batching.py` — `batch_subdoc` / `Batch` (Pass 4 reuses; may pass its own `context_lines_k` / `max_cues_per_batch`)
- `trezarr/translate/sentinel.py` — `extract_sentinels` / `reinsert_sentinels` (Pass 4 reuses to protect inline tags — D-57)
- `trezarr/translate/validate.py` — `validate_subdoc` / `GateError` (the hard gate self-review runs *before*; sole arbiter — D-55/D-59)
- `trezarr/llm/client.py` — `LLMClient.call(...)` (Pass 4 calls through it; the single `_semaphore` is the only concurrency gate — D-06)
- `trezarr/config.py` — `TrezarrSettings` (add Phase-6 fields under a Phase-6 header — D-60); see the existing Phase-5 group (`enable_pass1_analysis`, `enable_attribution`, `attribute_context_lines_k`, `pronoun_confidence_threshold`, `pronoun_safe_default`)

### Research (risk & stack grounding)
- `.planning/research/PITFALLS.md` — re-check anything tagged LLM / concurrency / structured-output / prompt-injection / Vietnamese-text; **specifically Pitfall 1** (single semaphore — Pass 4 adds none) and **Pitfall 5** (never quarantine on transient endpoint errors — the basis for D-59 best-effort review)
- `.planning/research/ARCHITECTURE.md` — Series Bible as the consistency substrate; the multi-pass pipeline shape (self-review is the natural next pass); "API for knowledge, filesystem for action"
- `.planning/research/FEATURES.md` — the relational-pronoun / Address-Map framing and why relationship evolution is part of the moat
- `.planning/research/STACK.md` — OpenAI SDK structured-output + the json_schema→json_object→text degradation (relevant to Pass-1 `relationship_events` and the Tier-3 self-review fallback)

### Project-wide grounding
- `.planning/PROJECT.md` §Core Value / Key Decisions — "consistency is non-negotiable" (drives D-54 drift-guard + D-59 best-effort review); "Track relationship evolution across episodes" + "Two-pass + LLM self-review pipeline" Key Decisions (both `— Pending` / `◑ Partial`, this phase closes them)
- `CLAUDE.md` §"Stack Patterns by Variant" / "OpenAI-Compatible Client" — structured-output fallback, semaphore-bounded concurrency, "translate only dialogue text" rule (the reviewer corrects dialogue text only, never timing/format)
- Memory: `bible-name-matching-case-insensitive.md` (CR-01) — normalize names with `.strip().lower()` in the new transition matcher AND the self-review name lookups, or pronoun/term checks silently drop

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`reconcile_attributions` (`reconcile.py`)** — already resolves one pronoun pair per ordered pair per episode and preserves an existing Address Map entry's terms for confirmed pairs. Phase 6 adds exactly one new branch: a logged `relationship_event` for the pair permits the terms to change + bumps `valid_from_episode`. The case-insensitive `name_to_id` index is the CR-01 pattern to copy.
- **`analyze_file` / `BibleAnalysis` (`analyze.py`)** — the holistic full-file Pass-1 call. Extending its response model with `relationship_events` is strictly additive (the model uses `extra="ignore"` and safe defaults), and `merge_bible_analysis` is the place to fan the events into the store writer.
- **`translate_file` Bible-aware branch (`engine.py`)** — Pass 4 plugs in between Step 8 (assemble `translated_doc`) and Step 9 (`validate_subdoc`); the `TaskGroup` + per-batch pattern from Pass 3 is the template, and the numbered-line + sentinel helpers are reused verbatim.
- **`RelationshipEvent` model (`models.py`)** — table + columns exist empty from the Phase-4 baseline migration; **no new migration** needed to populate it (mirrors how Phase 5 lit up `AddressMap`).
- **`validate_subdoc` (`validate.py`)** — the hard 7-check gate that runs once, after self-review; self-review's only job is to feed it a better document, never to replace or bypass it.

### Established Patterns
- **Mutable current row + append-only `bible_event` audit** (D-32) — relationship evolution updates the current Address Map row and the audit log captures before/after; "auditable change" (success #3) is free.
- **Numbered-line 1:1 protocol + sentinel protection + document gate** (D-12/D-13/D-16/D-17) — Pass 4 keeps all of it; corrections ride the same numbered lines.
- **Single `asyncio.Semaphore` in `LLMClient`** (D-06, Pitfall 1) — Pass 1 transition detection and Pass 4 review both call through it; no new semaphore.
- **Quarantine = file-level logic failure only; transient/endpoint errors propagate and retry** (D-18/D-30, Pitfall 5) — self-review is best-effort and adds **no** quarantine trigger (D-59).
- **Pydantic DTOs at boundaries, no SQLAlchemy leakage** (D-39) — `RelationshipEventDTO` follows the `AddressMapDTO` precedent; reconcile/analyze never import SQLAlchemy.

### Integration Points
- **Pass 1 (`analyze.py`) → store** — `merge_bible_analysis` calls the new relationship-event writer for each detected transition (name-matched case-insensitively to characters).
- **`load_series_bible` → `reconcile.py`** — relationship events for the series load into the Bible DTO so reconciliation can apply transition precedence (D-54) without a hot-path DB read.
- **`translate_file` → Pass 4** — after Pass-3 assembly, batch the `(source, translated, bible-context)` triples, review concurrently, splice corrections back via the numbered-line/sentinel path, then run `validate_subdoc` once.
- **`config.py`** — Phase-6 settings group (`enable_relationship_events`, `enable_self_review`, review batch/context knobs) so both capabilities are independently toggleable for staged rollout and tests.

</code_context>

<specifics>
## Specific Ideas

- **"Intentional, not silent drift" is a precedence rule, not a prompt instruction.** The drift guard (D-54) makes the *only* path for an established pair's pronouns to change a logged `relationship_event` this episode. That is what turns success criterion #1 into a structural guarantee instead of hoping the LLM is consistent across episodes.
- **Phase 4 pre-built the runway.** `relationship_event` (empty table), `valid_from_episode` (set but unused), and the `bible_event` audit log were all created with Phase 6 explicitly in mind (D-31/D-32, and Phase 5 D-42/D-49). Phase 6 is mostly INSERTs and one new reconciliation branch — not new schema.
- **Self-review can only help.** D-59 is the safety spine: a flaky or low-tier endpoint must never convert a passing translation into a quarantine. Review improves; the gate decides; on review failure we keep the pre-review output.
- **Reuse the moat machinery — don't reinvent it.** Pass 4 is built almost entirely from existing parts (`batch_subdoc`, `parse_numbered_response`, sentinel helpers, `TaskGroup`, the single semaphore). The new surface is a prompt, a small correction-splice, and the toggle.
- **Forward-only evolution.** A relationship change at episode N applies from N forward; v1 does not re-translate earlier episodes. This keeps the scope an INSERT + a precedence rule, not a re-render engine.

</specifics>

<deferred>
## Deferred Ideas

- **Retroactive re-translation of earlier episodes** when a later relationship change is logged → out of scope for v1 (forward-only). Possible future enhancement once a Bible-edit-triggered reprocess exists.
- **Editable / lockable relationship events** (human can correct or force a transition) → **Phase 8** (the override valve). Phase 6 respects existing locks; it never sets them.
- **Surfacing the relationship timeline and self-review corrections in the UI** → **Phase 7/8** (queue/history/Bible editor).
- **Iterative / multi-round self-review** (review the review, or escalate to a stronger model on disagreement) → out of scope; single best-effort pass for v1.
- **Confidence-flagging low-certainty self-review corrections in the UI** (OBS-01) → **v2**.
- **Source-language selection, ASS/SSA + VTT formats** → Phases 9/10.

None of these block Phase 6. Discussion stayed within phase scope.

</deferred>

---

*Phase: 06-relationship-evolution-self-review*
*Context gathered: 2026-06-02*
