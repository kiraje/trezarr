# Phase 6: Relationship Evolution + Self-Review - Research

**Researched:** 2026-06-02
**Domain:** SQLAlchemy 2.0 async Bible store extension; LLM self-review prompt engineering; reconciliation precedence; Pydantic v2 additive model extension
**Confidence:** HIGH (all findings grounded in the actual codebase; exact file paths, function signatures, and line ranges cited)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-51** — Detect relationship transitions inside the existing Pass-1 holistic analysis. Extend `BibleAnalysis` with `relationship_events: list[RelationshipEventInference]`. Emit only when a relationship has changed vs the carried-forward Bible.

**D-52** — INSERT `relationship_event` rows via a new store writer (`record_relationship_event` or `upsert_relationship_event`). Add `RelationshipEventDTO` to `trezarr/bible/dto.py`. Load events into `SeriesBibleDTO` via `load_series_bible` (or a sibling loader). Name-matching is case-insensitive (CR-01). No migration needed (table exists from Phase-4 baseline).

**D-53** — The mutable-current Address Map row IS the active pair; `valid_from_episode` is the version marker; a logged transition is the sole authorization to change an established pair. When a `relationship_event` for pair `(A,B)` fires at episode N, reconciliation is permitted to write changed `(self_term, address_term)` and set `valid_from_episode = N`. `bible_event` log records before→after.

**D-54** — Reconciliation precedence: `human lock > logged transition (this episode) > carried-forward prior pair > new low-confidence inference`. The one legitimate way for an established pair's terms to change is a `relationship_event` for that pair this episode.

**D-55** — Pass 4 self-review runs AFTER Pass-3 assembly (Step 8 in `translate_file`) and BEFORE `validate_subdoc` (Step 9). Lives in the Bible-aware branch only.

**D-56** — Batched review, reusing `batch_subdoc`, concurrent via `asyncio.TaskGroup`, gated solely by `LLMClient._semaphore`. No new `asyncio.Semaphore` anywhere (D-06, Pitfall 1). Each review batch carries: source line, Pass-3 Vietnamese line, resolved pronoun pair for its speaker→addressee, relevant Term Dictionary entries, series register.

**D-57** — Numbered-line "corrected output" protocol — reuse `parse_numbered_response` + `extract_sentinels`/`reinsert_sentinels`. Pass 4 must NOT request a Pydantic `response_model` — it uses the forgiving numbered-line text path like Pass 3 (D-47).

**D-58** — Scope review to Bible adherence only: (1) pronoun pair matches Address Map, (2) proper nouns/titles use Term Dictionary rendering, (3) register/tone consistency. Do NOT paraphrase or "improve" adherent lines.

**D-59** — Self-review is BEST-EFFORT. On any review failure (`openai.APIError`, numbered-line/sentinel integrity failure, or Tier-3 endpoint), fall back to pre-review Pass-3 line(s) for that batch. Self-review NEVER triggers quarantine. `validate_subdoc` remains the sole arbiter.

**D-60** — New Phase-6 `TrezarrSettings` fields under a Phase-6 comment header: at minimum `enable_relationship_events: bool = True`, `enable_self_review: bool = True`, plus review batch/context knobs (`self_review_context_lines_k`, `self_review_max_cues_per_batch`) and optionally `relationship_event_min_confidence`.

### Claude's Discretion

Module layout (new `trezarr/translate/review.py` vs fold into `engine.py`; extending `analyze.py` vs small `relationship.py` helper); exact Pydantic shapes of `RelationshipEventInference`, `RelationshipEventDTO`, and `ReviewCorrection`; whether a transition re-derives terms from attribution or trusts LLM-suggested terms (prefer suggested-then-fallback); precise self-review prompt and Bible context per batch; whether `load_series_bible` eager-loads `relationship_events` or a separate loader; reconciliation tie-break when lock and transition both touch a pair (lock wins per D-34); exact new setting names and numeric defaults; store writer name and dedup key `(series_id, character_a_id, character_b_id, episode_marker)`; whether self-review compares against freshly reloaded Bible or in-memory `resolved_map`.

### Deferred Ideas (OUT OF SCOPE)

- Retroactive re-translation of earlier episodes when a later relationship change is logged (forward-only in v1)
- Editable/lockable relationship events (Phase 8)
- Surfacing relationship timeline or self-review corrections in UI (Phase 7/8)
- Iterative multi-pass self-review (single pass for v1)
- Confidence-flagging self-review corrections in UI (OBS-01, v2)
- Source-language selection / multi-format / Bazarr inventory (Phases 9/10)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BIBLE-07 | Trezarr tracks relationship evolution across episodes with episode markers so pronoun choices change correctly over the series | D-51/52/53/54 — additive extension to `BibleAnalysis`, new store writer, reconciliation precedence branch |
| ENG-05 | Trezarr runs an LLM self-review pass over translated output, checking Series Bible adherence and correcting violations before finalizing | D-55/56/57/58/59/60 — Pass 4 in `translate_file` between assembly and `validate_subdoc` |
</phase_requirements>

---

## Summary

Phase 6 is a brownfield deepening phase that INSERTs into the already-existing `relationship_event` table (created empty in Phase 4), adds one new branch to `reconcile_attributions`, inserts a new self-review pass into `translate_file`, and adds a handful of new `TrezarrSettings` fields. All heavy lifting (LLM client, batching, sentinels, numbered-line protocol, store transaction patterns, DTO boundary, `asyncio.TaskGroup` dispatch) already exists and is reused verbatim. The 226-test GREEN suite is the invariant to protect.

**Primary recommendation:** Build Capability A (Relationship Evolution) in Wave 1 and Capability B (Self-Review) in Wave 2. Both capabilities are independently toggleable via D-60 settings; Wave 1 ship gate is `enable_relationship_events=True` passing with the existing pronoun engine. Wave 2 ship gate is `enable_self_review=True` with the gate remaining the sole quarantine arbiter.

The single most important pitfall to prevent: the self-review pass must NEVER add a quarantine path. Every error path in Pass 4 must fall back to the pre-review `translated_doc` and continue to `validate_subdoc`. This is D-59 and it matches the existing Pitfall 5 pattern in `engine.py` — `openai.APIError` propagates (SDK handles it), `BatchValidationError` triggers quarantine ONLY in Pass 3, and self-review has no quarantine trigger.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Relationship transition detection | Bible/LLM pass (analyze.py) | Store (store.py writer) | Transition is a holistic narrative inference — same tier as character/term inference in Pass 1 |
| Transition persistence | Database/Storage (store.py) | — | INSERT only into pre-existing `relationship_event` table |
| Active-pair evolution | Reconciliation (reconcile.py) | Store (upsert_address_pair) | Precedence logic is pure-Python; the write goes through the existing `upsert_address_pair` path |
| Self-review dispatch | Translation engine (engine.py) | LLM Client (llm/client.py) | Pass 4 lives in `translate_file` same as Pass 3; LLM client is the sole LLM-access boundary |
| Self-review correction splicing | Translation engine (engine.py) | Sentinel/parse helpers | Numbered-line protocol + sentinel reinsertion are reused from Pass 3 |
| Phase-6 configuration | Config (config.py) | — | TrezarrSettings per D-11 layered-config convention |

---

## Standard Stack

No new dependencies for Phase 6. All required libraries are already installed and in use.

### Core (pre-existing, reused)

| Library | Version | Purpose | Reuse in Phase 6 |
|---------|---------|---------|-----------------|
| SQLAlchemy 2.0 async + aiosqlite | 2.0.50 / 0.22.1 | Bible DB reads/writes | `record_relationship_event` writer; `load_series_bible` extension |
| openai SDK | 2.38.x | LLM calls | Pass 4 calls through `LLMClient.call(messages)` (no `response_model`) |
| Pydantic 2.x | 2.13.x | DTOs and inference models | `RelationshipEventInference`, `RelationshipEventDTO` |
| pydantic-settings | 2.14.x | Settings | Phase-6 `TrezarrSettings` fields |
| asyncio.TaskGroup | stdlib | Concurrent batch dispatch | Pass 4 review batches dispatched the same way as Pass 3 |
| tenacity | 9.1.x | Pipeline-level retry | NOT used in Pass 4 (best-effort, no retry) |

### No New Installs Required

Phase 6 installs zero new packages. The `relationship_event` table already exists (Phase-4 baseline migration). All helper modules (`batching.py`, `sentinel.py`, `validate.py`, `engine.py`) are reused verbatim.

---

## Package Legitimacy Audit

No packages are installed in Phase 6. This section is not applicable.

---

## Architecture Patterns

### System Architecture Diagram

```
translate_file (engine.py)
│
├── Steps 1–4: read, hash, ledger check, batch [unchanged]
│
├── Step 4.5: Phase-5 three-pass block [unchanged]
│   ├── Pass 1 BARRIER: analyze_file → merge_bible_analysis
│   │     [Phase 6 ADDITIVE: BibleAnalysis now includes relationship_events]
│   │     [Phase 6 ADDITIVE: merge_bible_analysis calls record_relationship_event for each]
│   ├── Reload Bible [Phase 6 ADDITIVE: SeriesBibleDTO now includes relationship_events list]
│   ├── Pass 2: attribute_batch gather [unchanged]
│   └── reconcile_attributions → resolved_map
│         [Phase 6 ADDITIVE: new transition-precedence branch]
│         [if relationship_event exists for pair this episode → new terms + bump valid_from_episode]
│
├── Step 7: Pass 3 translate gather [unchanged]
│
├── Step 8: Assemble translated_doc [unchanged]
│
├── [Phase 6 NEW] Step 8.5: Pass 4 Self-Review (when enable_self_review=True)
│   ├── Build review batches (batch_subdoc with self_review_context/max knobs)
│   ├── Build per-batch Bible context (resolved_map + term dict + register)
│   ├── asyncio.TaskGroup dispatch _review_batch for each batch
│   │     _review_batch:
│   │       1. extract_sentinels per cue
│   │       2. build_review_prompt (source, vietnamese, pronoun pair, terms, register)
│   │       3. llm_client.call(messages) — NO response_model
│   │       4. parse_numbered_response → corrected texts
│   │       5. reinsert_sentinels
│   │       6. On ANY failure → return pre-review texts (never raise, never quarantine)
│   └── Splice corrections into translated_doc (new SubLine objects)
│
├── Step 9: validate_subdoc (sole quarantine arbiter) [unchanged]
├── Step 10: write_vi_sidecar [unchanged]
└── Steps 11–12: ledger + result [unchanged]
```

### Recommended Project Structure (new files only)

```
trezarr/
├── bible/
│   ├── analyze.py    # EXTEND: add RelationshipEventInference, add relationship_events to BibleAnalysis,
│   │                 # extend merge_bible_analysis to call record_relationship_event
│   ├── dto.py        # EXTEND: add RelationshipEventDTO; extend SeriesBibleDTO with relationship_events list
│   ├── models.py     # READ ONLY: RelationshipEvent ORM model already exists (INSERT only, schema locked)
│   └── store.py      # EXTEND: add record_relationship_event (or upsert_relationship_event);
│                     #          extend load_series_bible to selectinload(Series.relationship_events)
├── translate/
│   ├── engine.py     # EXTEND: insert Pass 4 block between Step 8 and Step 9
│   ├── reconcile.py  # EXTEND: add transition-precedence branch (D-54)
│   └── review.py     # NEW (optional): _review_batch helper if extracted from engine.py
└── config.py         # EXTEND: Phase-6 settings group (D-60)

tests/
├── bible/
│   └── test_relationship_events.py  # NEW: store writer, DTO, load_series_bible extension
├── translate/
│   ├── test_reconcile.py            # EXTEND: add transition-precedence test cases
│   └── test_self_review.py          # NEW: Pass 4 best-effort semantics, correction splice, fallback
```

---

## Concrete Implementation Knowledge

### Q1: Self-Review Prompt Design (D-58)

The reviewer must correct Bible violations without re-translating adherent lines. The key prompt discipline is:

1. **Provide specific constraints, not general style guidance.** If the model is given "improve if needed," it will "improve." It must be told: "Return each line VERBATIM if it already adheres; only rewrite when a specific Bible violation is detected."

2. **List the Bible constraints explicitly per batch.** Each batch should include:
   - Resolved pronoun pair for the dominant speaker→addressee in that batch (from `resolved_map`)
   - Relevant Term Dictionary entries (source_term → vietnamese_rendering) that appear in the source lines
   - Series register (e.g. "romantic, casual")

3. **Recommended prompt structure** (grounded in Pass-3 prompt pattern in `engine.py` `build_translate_prompt`):

```
[INSTRUCTIONS]
You are a Vietnamese subtitle reviewer. Check each numbered line for Series Bible violations ONLY.

Series Bible for this batch:
  - Register/tone: {register}
  - Pronoun pair (speaker→addressee): speaker says "{self_term}", addresses as "{address_term}"
  - Term dictionary: {source_term} → {vietnamese_rendering} [repeat per relevant term]

RULES:
1. Output ONLY numbered lines [1], [2], ... [N] in order.
2. Keep <<T0>>, <<T1>>, ... tokens EXACTLY as-is.
3. Return each line VERBATIM unless it has a SPECIFIC Bible violation:
   - Wrong pronoun: the line uses a different first-person or second-person term than the Bible pair above.
   - Wrong term: a proper noun/title/place from the Bible is not rendered as specified above.
   - Wrong register: the line is significantly more formal or informal than the series register.
4. Do NOT rephrase, "improve," or paraphrase lines that already comply.

[LINES TO REVIEW]
[1] (source: {source_text}) {vietnamese_text}
[2] ...
```

**Key design choices:**
- Source text alongside Vietnamese text so the reviewer can check adherence, not just fluency.
- Pronoun pair is stated as a pair (both self_term AND address_term), not just one direction.
- "Return verbatim" instruction is the primary directive; correction is the exception path.
- Character/name matching for "which pronoun pair applies" uses `.strip().lower()` (CR-01).

**What to include in per-batch Bible context:** Use the `resolved_map` already in scope in `translate_file` — it maps `(speaker_id, addressee_id) → (self_term, address_term)`. The dominant pair for a batch can be determined from `flat_attributions` for that batch (the most frequent attributed speaker/addressee). For Term Dictionary: filter `bible.terms` to those whose `source_term` appears (case-insensitive) in any source text in the batch.

**Tier-3 fallback:** If `llm_client._mode == "text"` (Tier-3 endpoint, the same check already in `analyze_file`), skip Pass 4 entirely and return pre-review `translated_doc`. [ASSUMED — check `analyze.py` lines 252–259 for the exact `_mode` attribute check pattern; the Tier-3 check is Claude's discretion per D-59.]

### Q2: Relationship Event New Pronoun Pair Selection (D-54)

**Preferred precedence for new terms when a transition fires:**

1. **LLM-suggested terms from `RelationshipEventInference`** — if the Pass-1 LLM provided `suggested_self_term`/`suggested_address_term` on the `RelationshipEventInference`, use them. These are derived from the LLM's holistic read of the narrative change and are most likely to be correct.

2. **Fallback: this episode's high-confidence reconciled attribution** for the pair — if the LLM did not suggest terms, check `resolved_map.get((char_a_id, char_b_id))` for the pair as reconciled in the current episode (which will be the high-confidence pair if attribution succeeded).

3. **Fallback: `get_safe_default`** — if neither is available.

**Dedup key for `relationship_event` rows:** `(series_id, character_a_id, character_b_id, episode_marker)` — the combination must be unique per episode. Use `INSERT OR IGNORE` semantics (i.e., the writer should check for existence before inserting, per the existing `_upsert_*_in_session` pattern).

**Forward-only**: Once the Address Map row is updated (by calling `upsert_address_pair` with the new terms and `valid_from_episode=episode_key`), all future episodes see the new pair as the established pair. Reconciliation for future episodes will land in the "confirmed — use existing Address Map entry" branch (the same branch Phase 5 already uses), with the new terms. No retroactive re-translation.

### Q3: Minimal, Surgical reconcile.py Change (D-54)

**Integration point:** In `reconcile_attributions` (`reconcile.py` lines 204–261), the current logic for `survivors` (high-confidence observed pairs) is:

```python
if survivors:
    existing = existing_map.get(pair)
    if existing and existing.self_term and existing.address_term:
        self_term = existing.self_term  # carry-forward wins
        address_term = existing.address_term
    else:
        # safe default
```

**Phase 6 adds one new branch BEFORE the `if survivors:` check:** "Is there a logged transition for this pair at this episode?" If yes, the transition's suggested terms (or fallback derivation) are used and the address pair is updated. The transition check must happen before the confidence-gate check, but AFTER the lock check (D-34: lock wins over a transition).

**Concrete precedence flow (the minimal change):**

```python
for pair in all_pairs:
    spk_id, addr_id = pair
    attributions = pair_attributions.get(pair, [])
    existing = existing_map.get(pair)

    # LOCK CHECK (unchanged from Phase 5) — lock always wins
    if existing:
        locked = set(existing.locked_fields or [])
        if "self_term" in locked or "address_term" in locked:
            if existing.self_term and existing.address_term:
                resolved_map[pair] = (existing.self_term, existing.address_term)
                continue  # lock wins — skip transition + confidence gate

    # [Phase 6 NEW BRANCH] TRANSITION CHECK — logged event authorizes change
    # relationship_events is a list[RelationshipEventDTO] on SeriesBibleDTO
    # event matches if (char_a_id, char_b_id) == (spk_id, addr_id) OR (addr_id, spk_id)
    # (events are undirected; the transition affects the pair in both directions)
    if settings.enable_relationship_events:
        transition = _find_transition_for_pair(bible.relationship_events, spk_id, addr_id, episode_key)
        if transition is not None:
            new_self, new_addr = _derive_transition_terms(transition, pair, resolved_map, id_to_gender, settings)
            resolved_map[pair] = (new_self, new_addr)
            await upsert_address_pair(
                session_factory, series_id=series_id,
                speaker_character_id=spk_id, addressee_character_id=addr_id,
                self_term=new_self, address_term=new_addr,
                valid_from_episode=episode_key, episode_key=episode_key, source="inference",
            )
            continue  # transition handled — skip confidence gate

    # Existing confidence-gate logic (unchanged from Phase 5)
    survivors = [a for a in attributions if _confidence_value(a.confidence) >= threshold_val]
    if survivors:
        ...  # existing Phase-5 "confirmed — use existing terms" branch
    else:
        ...  # existing Phase-5 "below threshold → safe default" branch
```

**Preserving Phase-5 success #4 invariant:** The transition branch (`continue`) only fires when there IS a logged event. When there is no event and no survivors, the code falls through to the existing `get_safe_default` path — unchanged. The below-threshold → safe default invariant is fully preserved.

**Reciprocal coherence:** When a transition fires for `(A→B)`, the caller should also check `(B→A)` — if a `KINSHIP_RECIPROCAL` entry exists for the new terms, call `upsert_address_pair` for the reverse direction too. This mirrors the existing Step (e) reciprocal logic at the bottom of `reconcile_attributions`.

### Q4: Pass 4 Correction Splice into translated_doc (D-57, D-59)

The review returns corrected texts via `parse_numbered_response`. The correction splice replaces lines in `translated_doc` (or builds a new `SubDoc`) preserving the 1:1 cue mapping and `SubLine` identity fields.

**Precise splice approach:**

1. `translated_doc.lines` is a `list[SubLine]` built in Step 8. After Pass 3, this is the list of all translated `SubLine` objects.

2. For each review batch, the batch's `cues` are a slice of `translated_doc.lines` (the TRANSLATED lines, not the source). The review batch uses the TRANSLATED text as the content to review/correct.

3. After reviewing batch `i`, the corrected texts (from `parse_numbered_response`) replace the text of the corresponding `translated_doc.lines` entries for that batch. The replacement must create NEW `SubLine` objects (never mutate in-place — mirrors Pitfall 8 / D-48 pattern in `engine.py` line 706: "Never mutate source SubLines").

4. Best-effort fallback per batch (D-59): if `_review_batch` returns `None` (review failed) or raises, the pre-review texts for that batch are kept as-is. This is implemented by having `_review_batch` return `list[str] | None`: `None` means "use pre-review."

**Splice implementation pattern:**

```python
# After Pass 3 assembly (Step 8), translated_doc is assembled.
# Pass 4 (Step 8.5):
if settings.enable_self_review and eligible_item is not None and session_factory is not None:
    review_batches = batch_subdoc(
        translated_doc,  # review the TRANSLATED document
        settings,
        context_lines_k=settings.self_review_context_lines_k,
        max_cues_per_batch=settings.self_review_max_cues_per_batch,
    )
    # Build parallel source batches for the review prompt (source text alongside translated)
    source_lines_by_index = {line.index: line for line in source_doc.lines}

    async with asyncio.TaskGroup() as tg:
        review_tasks = [
            tg.create_task(_review_batch(
                review_batch=rb,
                source_lines_by_index=source_lines_by_index,
                resolved_map=resolved_map,
                bible=bible,
                llm_client=llm_client,
                settings=settings,
            ))
            for rb in review_batches
        ]
    review_results = [t.result() for t in review_tasks]

    # Splice corrections — build replacement SubLines
    corrected_lines = list(translated_doc.lines)  # shallow copy of list
    offset = 0
    for rb, corrected_texts in zip(review_batches, review_results):
        if corrected_texts is None:
            # fallback: keep pre-review lines (D-59)
            offset += len(rb.cues)
            continue
        for i, (cue, new_text) in enumerate(zip(rb.cues, corrected_texts)):
            # Find position in corrected_lines by SubLine identity (index field)
            corrected_lines[offset + i] = SubLine(
                index=cue.index,
                start_tc=cue.start_tc,
                end_tc=cue.end_tc,
                text=new_text,
                raw=None,
            )
        offset += len(rb.cues)

    translated_doc = SubDoc(
        lines=corrected_lines,
        encoding=translated_doc.encoding,
        line_ending=translated_doc.line_ending,
        separators=translated_doc.separators,
        leading=translated_doc.leading,
        trailer=translated_doc.trailer,
    )
```

**TaskGroup and exception handling (D-59 best-effort):** `_review_batch` must NEVER raise — it catches all exceptions internally and returns `None` on failure. This means the `TaskGroup` will not propagate exceptions from review tasks. This is intentional and matches D-59's "best-effort, never quarantine" contract. This differs from the Pass-3 `TaskGroup` which re-raises `BatchValidationError` as an `ExceptionGroup`.

**Sentinel integrity in review:** `_review_batch` follows the same sentinel flow as `_translate_batch_inner` in `engine.py` lines 306–338:
1. `extract_sentinels(cue.text)` on each TRANSLATED cue (the `<<T...>>` tokens are already in the translated text from Pass 3)
2. Build prompt with cleaned texts
3. `llm_client.call(messages)` — no `response_model`
4. `parse_numbered_response`
5. `reinsert_sentinels` — if `integrity_ok=False`, return `None` for this batch (fallback, not exception)

### Q5: OpenAI SDK Structured Output for relationship_events in BibleAnalysis (D-51)

The existing `BibleAnalysis` model (`analyze.py` lines 80–100) uses:

```python
class BibleAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    register_value: str | None = Field(default=None, alias="register")
    characters: list[CharacterInference] = []
    terms: list[TermInference] = []
    address_map: list[AddressMapInference] = []
```

**Phase 6 extension is strictly additive:**

```python
class RelationshipEventInference(BaseModel):
    """A relationship transition detected by Pass-1 analysis."""
    character_a_name: str
    character_b_name: str
    episode_marker: str   # e.g. "S01E04" — the current episode
    description: str      # narrative description of the transition
    suggested_self_term: str | None = None   # new self_term for A→B (if LLM can suggest)
    suggested_address_term: str | None = None  # new address_term for A→B (if LLM can suggest)

class BibleAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    register_value: str | None = Field(default=None, alias="register")
    characters: list[CharacterInference] = []
    terms: list[TermInference] = []
    address_map: list[AddressMapInference] = []
    relationship_events: list[RelationshipEventInference] = []  # [ADDITIVE — safe default []]
```

**Safety guarantees:**
- `extra="ignore"` means endpoints that return the OLD schema (without `relationship_events`) will not fail Pydantic validation.
- `relationship_events: list[...] = []` means if the LLM omits the field (Tier-2 JSON or Tier-3 degradation), the result is an empty list — safe, never raises.
- The Tier-2 validation path (`BibleAnalysis.model_validate_json(result)` in `analyze_file` lines 291–296) will work with or without `relationship_events` in the JSON.

**Pass-1 prompt extension (D-51):** Add to the `[INSTRUCTIONS]` section in `_build_analysis_prompt` (`analyze.py` lines 191–204):

```
  - relationship_events: list of relationship transitions detected in this episode
    (ONLY emit when a relationship has CHANGED relative to the existing Bible context above).
    Each entry: character_a_name, character_b_name, episode_marker (use "{episode_key}"),
    description (narrative description of the shift, e.g. "They become lovers in this episode"),
    suggested_self_term (optional: new Vietnamese self-reference term for A→B),
    suggested_address_term (optional: new Vietnamese address term for A→B).
    IMPORTANT: Do NOT emit entries for stable, unchanged relationships.
```

**`episode_key` injection:** `_build_analysis_prompt` currently does NOT receive `episode_key`. It needs to be added as a parameter so the LLM can be told which episode to use as `episode_marker`. [VERIFIED: `analyze.py` line 107 — `_build_analysis_prompt` signature is `(cue_texts, bible, arr_metadata)`. Phase 6 must add `episode_key: str` parameter and thread it from `analyze_file`.]

**`merge_bible_analysis` extension (D-52):** After Step 4 (address pairs), add Step 5: for each `analysis.relationship_events`, resolve `character_a_name` and `character_b_name` to IDs via the same `name_to_id` map (case-insensitive, CR-01), then call `record_relationship_event(session_factory, series_id, char_a_id, char_b_id, episode_key, description)`. Skip entries where either name cannot be resolved (warn, never crash). [VERIFIED: `analyze.py` lines 355–487 show the merge pattern.]

### Q6: Testing Patterns for Phase 6

**Project test patterns (verified in codebase):**

1. **Async tests:** `asyncio_mode = "auto"` in `pyproject.toml` — all `async def test_*` functions run without `@pytest.mark.asyncio`. [VERIFIED: conftest.py files use `@pytest_asyncio.fixture`, test files use bare `async def`.]

2. **DB fixtures:** `temp-file SQLite + real Alembic baseline migration per test` (NOT `:memory:`). Fixture chain: `db_engine (pytest_asyncio.fixture, tmp_path)` → `session_factory (pytest_asyncio.fixture, db_engine)`. Imported via `tests/bible/conftest.py` and `tests/translate/conftest.py` which re-export from `tests/db/conftest.py`. [VERIFIED: `tests/db/conftest.py`.]

3. **LLM mocking:** Use `AsyncMock` for `LLMClient.call`. For self-review tests, the mock must return a numbered-line string. Pattern from `tests/translate/test_analyze.py` lines 17, 22. For relationship event tests, the mock must return a `BibleAnalysis` with `relationship_events` populated (Tier-1 path) or a JSON string (Tier-2 path).

4. **Helper factories:** `_make_subdoc(texts)`, `_make_settings(**kwargs)`, `_create_series(session_factory)`, `_create_characters(session_factory, series_id)` — defined at module level in each test file. [VERIFIED: `test_analyze.py`, `test_reconcile.py`.]

5. **RED-stub-first Wave 0 pattern (Phase-5 precedent):** Wave 0 creates all test stubs as `pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))` so the suite stays green before implementation. [VERIFIED: `05-01-PLAN.md` in Phase-5 plans.]

6. **`xfail` pattern for stubs in existing modules:** Use `raises=(ImportError, AssertionError, TypeError)` — NOT just `ImportError` — because the existing modules import without error; the assertion fails on missing functionality. [VERIFIED: STATE.md accumulated context.]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM concurrency limiting | New `asyncio.Semaphore` in review.py | `LLMClient._semaphore` | D-06 / Pitfall 1 — single semaphore invariant. Adding a second creates double-gating and makes the concurrency ceiling unpredictable |
| Inline-tag protection in Pass 4 | Custom token replacement | `extract_sentinels` / `reinsert_sentinels` (`sentinel.py`) | These already handle `<i>`, `<b>`, `{\anX}` etc. and the round-trip integrity check |
| Numbered-line parsing in Pass 4 | Custom regex parser | `parse_numbered_response` (`engine.py` line 200) | Handles `[N]`, `[N].`, `[N])` variants; includes all validation |
| Batch packing for Pass 4 | Custom batcher | `batch_subdoc` with `context_lines_k` and `max_cues_per_batch` overrides | Already accepts per-call overrides; no modification needed |
| Transaction management in new store writer | New session lifecycle | `async with session_factory() as session: async with session.begin():` pattern | Exact pattern used by all existing `upsert_*` functions in `store.py` |
| Lock precedence in transition | Custom lock check | Read `existing_row.locked_fields` off the SQLA row inside the transaction | WR-01 / HIGH finding from Phase 4 — never trust the DTO for lock state |
| Name-to-ID resolution | New case-sensitive lookup | `.strip().lower()` normalized dict built from `bible.characters` | CR-01 — the established cross-module contract |

**Key insight:** Pass 4 is approximately 70% reused code. The new surface is: (1) a review prompt builder, (2) a `_review_batch` function that mirrors `_translate_batch_inner` but returns `None` on any failure instead of raising, and (3) the correction splice into `translated_doc`. Everything else is existing machinery.

---

## Common Pitfalls

### Pitfall 1: Adding a second asyncio.Semaphore in the review module

**What goes wrong:** A developer sees that Pass 4 fires concurrent LLM calls and adds `asyncio.Semaphore(4)` in `review.py`. This creates double-gating: the review calls are also gated by `LLMClient._semaphore`, so effective concurrency is `min(review_semaphore, llm_semaphore)` which is unpredictable. Worse, if the review semaphore is inside a `TaskGroup`, it can cause deadlock if the TaskGroup holds all slots while waiting for `LLMClient._semaphore` to release.

**Why it happens:** D-06 is easy to forget when writing a new module; the existing passes in `engine.py` don't appear to have a semaphore because `LLMClient._semaphore` is inside the client.

**How to avoid:** Add module-level comment: `# No asyncio.Semaphore in this module. LLMClient._semaphore is the sole gate (D-06, Pitfall 1).` — the exact pattern used in `analyze.py`, `reconcile.py`, `engine.py`.

**Warning signs:** Any `asyncio.Semaphore(...)` instantiation outside `trezarr/llm/client.py`.

### Pitfall 2: Self-Review Quarantining on Failure (violates D-59)

**What goes wrong:** A developer catches `BatchValidationError` inside the Pass-4 TaskGroup the same way the Pass-3 TaskGroup does, and routes it to `_write_quarantine`. This converts a "reviewer had a bad day" event into a permanent quarantine for a file that would have passed the gate.

**Why it happens:** The Pass-3 `except* BatchValidationError` block in `engine.py` lines 687–702 is the obvious template. Phase 6's Pass 4 uses the same TaskGroup pattern but must NOT have this exception handler.

**How to avoid:** `_review_batch` must catch ALL exceptions internally and return `None` (pre-review fallback). The Pass-4 `TaskGroup` block should have NO `except*` block. Any uncaught exception from a Task would propagate as an `ExceptionGroup` — to be safe, wrap the TaskGroup in a bare `except Exception` and fall back to the pre-review `translated_doc`.

**Warning signs:** Any `_write_quarantine` or `ledger.record(status="quarantined")` call that can be reached from Pass-4 code paths.

### Pitfall 3: Relationship Event Applied to Both Directions Without Reciprocal Derivation

**What goes wrong:** The `relationship_event` table stores `(character_a_id, character_b_id)` without directionality (the schema has `character_a_id` and `character_b_id`, not `speaker_id` / `addressee_id`). A developer applies the transition only to the `(A→B)` direction in `reconcile_attributions`, leaving `(B→A)` unchanged. The pair is now inconsistent: A calls B with the new romantic terms but B still calls A with old terms.

**Why it happens:** `reconcile_attributions` works with directed pairs (speaker_id, addressee_id). The `relationship_event` stores an undirected pair. The bridge between them requires explicitly finding both `(char_a_id, char_b_id)` AND `(char_b_id, char_a_id)` and deriving appropriate terms for each direction.

**How to avoid:** `_find_transition_for_pair` should look up events where EITHER `(character_a_id == spk_id AND character_b_id == addr_id)` OR `(character_a_id == addr_id AND character_b_id == spk_id)`. When a transition is found, apply the `KINSHIP_RECIPROCAL` table (already in `reconcile.py` lines 34–53) to derive the reverse direction's terms.

**Warning signs:** After a logged transition, A→B uses new terms but B→A still uses old terms in the same episode's output.

### Pitfall 4: Case-Sensitive Name Matching in merge_bible_analysis for Relationship Events (violates CR-01)

**What goes wrong:** `merge_bible_analysis` resolves `character_a_name` and `character_b_name` from `RelationshipEventInference` using a case-sensitive dict lookup, silently dropping transitions where the LLM capitalized the name differently than the Bible.

**Why it happens:** CR-01 was a Phase-5 bug (fixed in 05-REVIEW-FIX.md — the original `analyze.py` also had this bug for address pairs before the fix). The fix at `analyze.py` line 371 (`name_to_id[char.original_latin_name.strip().lower()] = char_dto.id`) and lines 427–428 builds the normalized index — the same pattern must be applied for transition name resolution.

**How to avoid:** Use the same `name_to_id` dict (already built in `merge_bible_analysis`) which uses `.strip().lower()` keys. Resolve `(pair.character_a_name or "").strip().lower()` and `(pair.character_b_name or "").strip().lower()`. This is the exact same pattern as the address-pair resolution at lines 427–428.

**Warning signs:** Relationship events with character names in different capitalizations silently producing no DB rows.

### Pitfall 5: SQLAlchemy Import Leakage from New Store Writer (violates D-39)

**What goes wrong:** `record_relationship_event` is placed in a new file (e.g., `trezarr/bible/relationship.py`) that is imported by `analyze.py`, but `relationship.py` imports `RelationshipEvent` from `models.py` directly at the top of the file. `analyze.py` now transitively imports SQLAlchemy, breaking the D-39 DTO boundary.

**Why it happens:** SQLAlchemy models live in `models.py` which is imported by `store.py`. The rule is that only `store.py` may import from `models.py`. Any new store function must live IN `store.py`.

**How to avoid:** `record_relationship_event` (or `upsert_relationship_event`) MUST live in `trezarr/bible/store.py`, not in a new file. The existing `test_dto_boundary.py` test (`tests/bible/test_dto_boundary.py`) will catch this via import-graph inspection.

**Warning signs:** `from trezarr.bible.models import RelationshipEvent` appearing outside `store.py`. The `test_dto_boundary.py` test failing.

### Pitfall 6: Forward-Only Evolution Violated by relationship_event in SeriesBibleDTO Load

**What goes wrong:** `load_series_bible` loads ALL `relationship_event` rows for the series, including future episodes (if somehow events from later episodes are already in the DB). `reconcile_attributions` then sees a transition from `S03E10` when translating `S01E03` and applies it retroactively.

**Why it happens:** SQLAlchemy `selectinload` eagerly loads all rows without an episode filter.

**How to avoid:** The `_find_transition_for_pair` helper in `reconcile_attributions` must filter events to ONLY those where `event.episode_marker == episode_key` (current episode's transition authorizes a change). Past events may have already caused Address Map updates (which persist) — those are read via the existing Address Map, not by replaying history. Future events are irrelevant.

In practice, since Phase 6 only INSERTS events when it detects a transition in the current episode, this pitfall primarily applies to order-of-processing edge cases. Still, the filter in `_find_transition_for_pair` must be explicit: `episode_marker == current_episode_key`.

### Pitfall 7: review batch_subdoc indexes out of sync with translated_doc.lines

**What goes wrong:** The review is built by calling `batch_subdoc(translated_doc, settings, ...)`. The resulting batches have `batch.cues` as slices of `translated_doc.lines`. If the splice logic uses `offset + i` assuming batches are contiguous and non-overlapping, it will be correct. But if context cues (from `batch.context_before`/`batch.context_after`) are confused with translation cues, indices will drift.

**How to avoid:** The splice only replaces `batch.cues`, not context cues. The `offset` counter advances by `len(batch.cues)` per batch. Context cues do not appear in `translated_doc.lines` at the offset position — they are read-only. [VERIFIED: `batching.py` lines 85–95 — `batch.cues` is a slice of `all_lines[first_idx:next_idx]`; context lines are from outside this slice.]

---

## Code Examples

All examples grounded in the actual codebase with verified file paths and line numbers.

### Pattern 1: Store Writer for relationship_event (mirrors _upsert_address_pair_in_session)

The new `record_relationship_event` follows the exact `_upsert_address_pair_in_session` structure (`store.py` lines 581–697). Key differences: `RelationshipEvent` has no `locked_fields`; it is INSERT-only (no merge); dedup key is `(series_id, character_a_id, character_b_id, episode_marker)`.

```python
# trezarr/bible/store.py (new public function, following upsert_address_pair pattern)
async def record_relationship_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    character_a_id: int,
    character_b_id: int,
    episode_marker: str,
    description: str | None = None,
) -> RelationshipEventDTO:
    """INSERT a relationship_event row (no-op if already exists for this dedup key)."""
    async with session_factory() as session:
        async with session.begin():
            # Dedup check: (series_id, character_a_id, character_b_id, episode_marker)
            stmt = select(RelationshipEvent).where(
                RelationshipEvent.series_id == series_id,
                RelationshipEvent.character_a_id == character_a_id,
                RelationshipEvent.character_b_id == character_b_id,
                RelationshipEvent.episode_marker == episode_marker,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                return RelationshipEventDTO.model_validate(existing, from_attributes=True)
            row = RelationshipEvent(
                series_id=series_id,
                character_a_id=character_a_id,
                character_b_id=character_b_id,
                episode_marker=episode_marker,
                description=description,
            )
            session.add(row)
            await session.flush()
        return RelationshipEventDTO.model_validate(row, from_attributes=True)
# Source: verified against store.py _upsert_address_pair_in_session lines 581-697 [VERIFIED: codebase]
```

### Pattern 2: RelationshipEventDTO (mirrors AddressMapDTO)

```python
# trezarr/bible/dto.py (additive — append after AddressMapDTO)
class RelationshipEventDTO(BaseModel):
    """Relationship transition entry DTO (BIBLE-07)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    series_id: int
    character_a_id: int
    character_b_id: int
    episode_marker: str
    description: str | None = None
    created_at: datetime | None = None
    # Optional: carry suggested terms from the inference (not in DB, populated from analyze output)
    suggested_self_term: str | None = None
    suggested_address_term: str | None = None
# Source: verified against dto.py AddressMapDTO lines 120-147 [VERIFIED: codebase]
```

**Note on `suggested_self_term`/`suggested_address_term`:** The `relationship_event` table (ORM model, `models.py` lines 187–213) has NO columns for suggested terms — the schema is locked. The DTO can carry these fields as non-persisted attributes (populated from the `RelationshipEventInference` before writing to DB, passed through reconciliation in-memory). The DB row stores only `description`. [VERIFIED: `models.py` lines 187–213.]

### Pattern 3: load_series_bible Extension for relationship_events

The current `load_series_bible` (`store.py` lines 173–230) uses `selectinload` for `characters`, `terms`, `address_maps`. Phase 6 extends it with `selectinload(Series.relationship_events)`. This requires adding a SQLAlchemy `relationship` to `Series` (`models.py`) and `relationship_events: list[RelationshipEventDTO]` to `SeriesBibleDTO` (`dto.py`).

```python
# store.py load_series_bible — extend the select statement:
stmt = (
    select(Series)
    .where(Series.id == series_id)
    .options(
        selectinload(Series.characters),
        selectinload(Series.terms),
        selectinload(Series.address_maps),
        selectinload(Series.relationship_events),  # [Phase 6 NEW]
    )
)
# Then in the SeriesBibleDTO construction:
relationship_events=[
    RelationshipEventDTO.model_validate(e, from_attributes=True)
    for e in row.relationship_events
],
# Source: store.py lines 193-230 [VERIFIED: codebase]
```

**models.py addition:** Add `relationship_events` relationship to `Series`:
```python
relationship_events: Mapped[list["RelationshipEvent"]] = relationship(
    back_populates="series", cascade="all, delete-orphan"
)
```
And add back-reference to `RelationshipEvent`:
```python
series: Mapped["Series"] = relationship(back_populates="relationship_events")
```

### Pattern 4: _review_batch (mirrors _translate_batch_inner, returns None on failure)

```python
# trezarr/translate/review.py (or inside engine.py)
# No asyncio.Semaphore here. LLMClient._semaphore is the sole gate (D-06, Pitfall 1).

async def _review_batch(
    review_batch: Batch,           # batch of TRANSLATED cues
    source_lines_by_index: dict,   # {index → SubLine} from source_doc
    resolved_map: dict,            # (spk_id, addr_id) → (self_term, addr_term)
    bible: SeriesBibleDTO,
    llm_client: LLMClient,
    settings: TrezarrSettings,
) -> list[str] | None:
    """Review a batch of translated cues against the Bible. Returns corrected texts or None.

    Returns None on ANY failure — never raises (D-59 best-effort contract).
    """
    try:
        # Step 1: extract sentinels from TRANSLATED texts
        cleaned_texts, sentinel_maps = [], []
        source_texts = []
        for cue in review_batch.cues:
            cleaned, smap = extract_sentinels(cue.text)
            cleaned_texts.append(cleaned)
            sentinel_maps.append(smap)
            src = source_lines_by_index.get(cue.index)
            source_texts.append(src.text if src else "")

        # Step 2: build review prompt with Bible context
        prompt = build_review_prompt(
            source_texts=source_texts,
            translated_texts=cleaned_texts,
            resolved_map=resolved_map,
            bible=bible,
            settings=settings,
        )

        # Step 3: call LLM — no response_model (D-57)
        raw_response = await llm_client.call([{"role": "user", "content": prompt}])

        # Step 4: parse numbered-line response
        corrected_texts = parse_numbered_response(str(raw_response), len(review_batch.cues))

        # Step 5: reinsert sentinels
        restored = []
        for text, smap in zip(corrected_texts, sentinel_maps):
            if smap:
                restored_text, ok = reinsert_sentinels(text, smap)
                if not ok:
                    return None  # integrity failure → fallback (D-59)
                restored.append(restored_text)
            else:
                restored.append(text)
        return restored

    except Exception:
        logger.warning("Pass 4 review batch failed — using pre-review output (D-59)", exc_info=True)
        return None  # never raises, never quarantines
# Source: mirrors engine.py _translate_batch_inner lines 278-339 [VERIFIED: codebase]
```

### Pattern 5: Phase-6 TrezarrSettings Fields (mirrors Phase-5 group at config.py lines 128–143)

```python
# trezarr/config.py — add after Phase-5 group comment

# ── Phase 6: Relationship Evolution + Self-Review (D-51…D-60) ──────────────
# Capability A — Relationship Evolution
enable_relationship_events: bool = True   # D-60: toggle for staged rollout/tests
relationship_event_min_confidence: float = 0.0  # min confidence to emit a transition (0=all)

# Capability B — Self-Review Pass
enable_self_review: bool = True           # D-60: toggle for staged rollout/tests
self_review_context_lines_k: int = 3     # context K for review batches (same as translate default)
self_review_max_cues_per_batch: int = 20  # smaller batches for review (fewer tokens per call)
# Source: mirrors config.py Phase-5 group lines 128-143 [VERIFIED: codebase]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact on Phase 6 |
|--------------|------------------|--------------|-------------------|
| Static per-episode address map (Phase 5) | Evolution-aware map with `valid_from_episode` marker (Phase 6) | Phase 6 | Phase 6 is the event that activates `valid_from_episode`; Phase 5 set it, Phase 6 uses it for the drift-guard semantics |
| Three-pass pipeline (Phase 5) | Four-pass pipeline with self-review (Phase 6) | Phase 6 | Pass 4 is strictly additive; the three-pass path is unchanged when `enable_self_review=False` |
| `BibleAnalysis` has no relationship tracking | `BibleAnalysis` includes `relationship_events` (Phase 6) | Phase 6 | Additive extension; `extra="ignore"` + safe default `[]` guarantees backward compat |
| Empty `relationship_event` table (Phase 4) | Table populated by Phase 6 | Phase 6 | No migration needed; `record_relationship_event` is the first writer |

**Deprecated/outdated (not applicable):**
- No deprecated patterns in this phase — it is purely additive over well-established Phase-5 patterns.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `llm_client._mode == "text"` is the attribute checked for Tier-3 detection (pattern from `analyze.py` lines 252–253) | Q1 / Self-review prompt design | If the attribute name changed, the Tier-3 guard for Pass 4 would fail silently. Verify against `trezarr/llm/client.py` during implementation. |
| A2 | `RelationshipEventDTO.suggested_self_term`/`suggested_address_term` can be non-persisted DTO fields (carried from inference, not stored in DB) | Q2 / DTO design | If the planner requires them in the DB, the schema is locked from Phase 4 and a migration would be needed. But D-31 explicitly says Phase 6 is INSERT-only into the existing schema. |
| A3 | `Series` ORM model (`models.py`) does NOT yet have a `relationship_events` SQLAlchemy `relationship` — it needs to be added in Phase 6 | Standard Stack / load_series_bible extension | If a `relationship_events` relationship already exists on `Series`, the Phase 6 addition would duplicate it. Verify `models.py` lines 87–95 (current relationships: `characters`, `terms`, `address_maps`). [VERIFIED: `models.py` lines 87–95 — only `characters`, `terms`, `address_maps`. Relationship needed.] |
| A4 | `translate_file` review batch uses `translated_doc.lines` as the cues passed to `batch_subdoc` (reviewing the translated output, not the source) | Q4 / correction splice | If source lines were used for batching, the cue objects passed to `_review_batch` would have source text, and the sentinel reinsertion would be incorrect (sentinels in the source, not the translated output). |
| A5 | `parse_numbered_response` (engine.py line 200) can be called from `review.py` without circular import | Q4 / code examples | `review.py` would import from `engine.py`. This is a circular risk if `engine.py` imports from `review.py`. Solution: extract `parse_numbered_response`, `build_translate_prompt`, `extract_sentinels`/`reinsert_sentinels` from `engine.py` into a utility module, OR keep `_review_batch` inside `engine.py`. The latter is simpler and avoids import cycles. |

**If the table is empty:** A1 and A5 require verification during implementation. All other claims are verified from the codebase.

---

## Open Questions

1. **Module placement for `_review_batch`**
   - What we know: `engine.py` already imports from `sentinel.py`, `batching.py`, `validate.py`, `analyze.py`, `reconcile.py`; `parse_numbered_response` lives in `engine.py`.
   - What's unclear: Can `review.py` import `parse_numbered_response` from `engine.py` without creating a circular import? (If `engine.py` also imports from `review.py`.)
   - Recommendation: Keep `_review_batch` and `build_review_prompt` INSIDE `engine.py` to avoid the circular import problem entirely. This matches the precedent where `_translate_batch_inner` is also in `engine.py`.

2. **`RelationshipEvent` → `Series` back-reference direction for `selectinload`**
   - What we know: `models.py` line 187 defines `RelationshipEvent` without a `series` back-reference or `series_id` relationship. `Series` has no `relationship_events` ORM relationship.
   - What's unclear: Is there a `character_a`/`character_b` relationship needed for `Character` → `RelationshipEvent`? Or is it enough to query by `series_id` only?
   - Recommendation: Add `Series.relationship_events` relationship only (query by `series_id`). Character relationships for relationship events are not needed for Phase 6 (we use `character_a_id`/`character_b_id` directly).

3. **How to pass `episode_key` into `_build_analysis_prompt`**
   - What we know: `_build_analysis_prompt` signature is `(cue_texts, bible, arr_metadata)` — no `episode_key`. `analyze_file` has `episode_key` in scope.
   - What's unclear: Best approach — add `episode_key: str` parameter to `_build_analysis_prompt`, or embed it in the instructions string at `analyze_file` level before calling.
   - Recommendation: Add `episode_key: str` to `_build_analysis_prompt` signature. Simpler to test than string interpolation outside the function.

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — Phase 6 is code-only changes to existing modules using already-installed libraries).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (async mode: auto) |
| Config file | `pyproject.toml` (`asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/bible/test_relationship_events.py tests/translate/test_self_review.py tests/translate/test_reconcile.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BIBLE-07-A | `RelationshipEventInference` in `BibleAnalysis`; Pass-1 LLM returns transition; row written to `relationship_event` via `merge_bible_analysis` | unit | `pytest tests/bible/test_relationship_events.py::test_relationship_event_written_to_db -x` | ❌ Wave 0 |
| BIBLE-07-B | `load_series_bible` returns `relationship_events` in `SeriesBibleDTO` | unit | `pytest tests/bible/test_relationship_events.py::test_load_series_bible_includes_events -x` | ❌ Wave 0 |
| BIBLE-07-C | `reconcile_attributions` — transition authorizes terms change + `valid_from_episode` bump; no-event pair carries forward unchanged | unit | `pytest tests/translate/test_reconcile.py::test_transition_authorizes_terms_change -x` | ❌ Wave 0 (extend existing file) |
| BIBLE-07-D | `reconcile_attributions` — lock beats transition (D-34/D-54) | unit | `pytest tests/translate/test_reconcile.py::test_lock_beats_transition -x` | ❌ Wave 0 |
| BIBLE-07-E | `reconcile_attributions` — no transition → below-threshold → safe default (Phase-5 success #4 invariant preserved) | unit | `pytest tests/translate/test_reconcile.py::test_no_transition_no_survivors_safe_default -x` | ❌ Wave 0 |
| ENG-05-A | Pass 4 runs after assembly and before `validate_subdoc`; corrects a pronoun violation; `validate_subdoc` sees corrected output | integration | `pytest tests/translate/test_self_review.py::test_pass4_corrects_violation_before_gate -x` | ❌ Wave 0 |
| ENG-05-B | Pass 4 review failure (mock LLM raises) → pre-review output used; `validate_subdoc` still runs; no quarantine | unit | `pytest tests/translate/test_self_review.py::test_pass4_failure_fallback_no_quarantine -x` | ❌ Wave 0 |
| ENG-05-C | `enable_self_review=False` → Pass 4 skipped entirely; `translated_doc` unchanged | unit | `pytest tests/translate/test_self_review.py::test_pass4_disabled_skips_review -x` | ❌ Wave 0 |
| ENG-05-D | Sentinel integrity failure in review → pre-review batch kept; rest of file unaffected | unit | `pytest tests/translate/test_self_review.py::test_sentinel_failure_fallback_per_batch -x` | ❌ Wave 0 |
| BIBLE-07-F | Case-insensitive name matching in `merge_bible_analysis` for relationship events (CR-01) | unit | `pytest tests/bible/test_relationship_events.py::test_name_matching_case_insensitive -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/bible/test_relationship_events.py tests/translate/test_self_review.py tests/translate/test_reconcile.py -x -q`
- **Per wave merge:** `uv run pytest -x -q` (full suite — 226 existing tests must stay green)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/bible/test_relationship_events.py` — covers BIBLE-07-A, B, F (store writer, DTO, load, case-insensitive names)
- [ ] `tests/translate/test_self_review.py` — covers ENG-05-A, B, C, D (Pass 4 full lifecycle, failure fallback, toggle, sentinel)
- [ ] Extend `tests/translate/test_reconcile.py` — add test stubs for BIBLE-07-C, D, E (transition precedence, lock-beats-transition, preserved Phase-5 invariant)

*(All existing 226 tests remain green throughout — these are purely additive test files.)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Relationship event names resolved via existing `name_to_id` case-insensitive map — same prompt injection defense as analyze.py T-05-04-01 |
| V6 Cryptography | no | — |
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |

### Known Threat Patterns for Phase 6 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via self-review reviewer "correcting" content to malicious text | Tampering | Review prompt instructs "return verbatim unless specific Bible violation"; sentinel protection preserves inline tags; `validate_subdoc` gate catches structural corruption |
| Subtitle content leakage via `description` field in `relationship_event` | Information Disclosure | `description` comes from the LLM output, not raw subtitle text; existing `merge_bible_analysis` WR-06 failure-per-row pattern limits blast radius |
| Transition applied to wrong pair via name confusion | Tampering | CR-01 case-insensitive matching + warning-and-skip on unresolved names |

---

## Sources

### Primary (HIGH confidence)

- `trezarr/bible/analyze.py` (entire file, verified) — `BibleAnalysis`, `AddressMapInference`, `_build_analysis_prompt`, `analyze_file`, `merge_bible_analysis` — exact function signatures, line numbers, and extension points
- `trezarr/translate/reconcile.py` (entire file, verified) — `reconcile_attributions`, `KINSHIP_RECIPROCAL`, `get_safe_default`, `_threshold_value`, `_confidence_value` — exact precedence flow and Phase-6 insertion point
- `trezarr/translate/engine.py` (entire file, verified) — `translate_file` pipeline step numbering, `_translate_batch_inner`, `parse_numbered_response`, `build_translate_prompt`, `TaskGroup` dispatch pattern, `except* BatchValidationError` handler
- `trezarr/bible/store.py` (entire file, verified) — `_upsert_address_pair_in_session`, `load_series_bible`, `upsert_address_pair`, `merge_inferred` — transaction patterns, `selectinload` usage, DTO boundary
- `trezarr/bible/models.py` (entire file, verified) — `RelationshipEvent` ORM model columns, `Series` relationships (confirmed: no `relationship_events` relationship exists yet)
- `trezarr/bible/dto.py` (entire file, verified) — `AddressMapDTO`, `SeriesBibleDTO` patterns, `ConfigDict` usage
- `trezarr/translate/batching.py` (entire file, verified) — `batch_subdoc` `context_lines_k`/`max_cues_per_batch` overrides, `Batch.cues` as slice of source lines
- `trezarr/translate/sentinel.py` (first 50 lines, verified) — `extract_sentinels` / `reinsert_sentinels` API and integrity check semantics
- `trezarr/config.py` (entire file, verified) — Phase-5 settings group pattern, `TrezarrSettings` structure
- `tests/db/conftest.py` (entire file, verified) — `db_engine`, `session_factory` fixture pattern
- `.planning/phases/06-relationship-evolution-self-review/06-CONTEXT.md` (entire file, verified) — D-51 through D-60 locked decisions
- `.planning/phases/05-three-pass-pronoun-engine/05-REVIEW-FIX.md` (first 60 lines, verified) — CR-01 case-insensitive fix, 226 test GREEN baseline

### Secondary (MEDIUM confidence)

- `.planning/research/PITFALLS.md` — Pitfall 1 (single semaphore), Pitfall 5 (no quarantine on transient errors), Pitfall 4 (Bible drift — relationship events are the structural solution)
- `.planning/research/STACK.md` — OpenAI SDK structured-output tier degradation (`json_schema → json_object → text`)
- `.planning/phases/04-series-bible-store-schema/04-CONTEXT.md` — D-31 (schema locked), D-32 (bible_event audit), D-34 (lock precedence), D-39 (DTO boundary)
- `.planning/phases/05-three-pass-pronoun-engine/05-CONTEXT.md` — D-42 (`valid_from_episode` reserved for Phase 6), D-44 (deterministic reconciliation), D-45 (safe default), D-47 (Pass 3 text path), D-50 (settings group pattern)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all libraries verified in active codebase
- Architecture: HIGH — grounded in exact codebase file paths, function signatures, line numbers
- Pitfalls: HIGH for structural pitfalls (Pitfall 1, 5 from prior research); MEDIUM for review-prompt-specific pitfalls (reasoned from design, not observed failures)
- Test patterns: HIGH — verified from `tests/db/conftest.py`, `tests/translate/test_analyze.py`, `tests/translate/test_reconcile.py`

**Research date:** 2026-06-02
**Valid until:** 2026-07-02 (stable stack; Phase 6 is brownfield with locked schema — 30 days)
