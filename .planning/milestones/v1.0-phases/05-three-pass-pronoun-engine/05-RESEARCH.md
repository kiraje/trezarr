# Phase 5: Three-Pass Pronoun Engine - Research

**Researched:** 2026-06-01
**Domain:** LLM pipeline extension, Vietnamese pronoun attribution, Series Bible store extension
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-40:** Three distinct LLM passes — Analyze → Attribute → Translate. Pass 1 is a barrier; Pass 2 and Pass 3 are each internally concurrent via `asyncio.gather`.
- **D-41:** Pass 1 grounds on the existing Bible (load first, include in prompt), infers, then merges via the Phase-4 contract.
- **D-42:** Address Map — observed/exchanging pairs only; `self_term`/`address_term` in existing single-string columns; reciprocal inferred from kinship table unlocked + lower-confidence; `valid_from_episode` set to current episode key.
- **D-43:** Pass 2 — batched per-cue attribution with wider context window (`attribute_context_lines_k`), `LineAttribution` per cue: speaker, addressee, confidence. Unmatched names resolve to safe default (not crash).
- **D-44:** Deterministic reconciliation — one `(self_term, address_term)` per ordered pair per episode; first high-confidence wins, tie-break by frequency; reciprocal coherence check against kinship table; persist to Address Map.
- **D-45:** Below confidence threshold → safe neutral/polite default pair; never risk intimate pronoun. Configurable `pronoun_confidence_threshold` (default ~0.6 / `medium`). Low-confidence lines are logged, not surfaced.
- **D-46:** Per-line pronoun hints in translation prompt; no mechanical string replacement.
- **D-47:** Pydantic `response_model` for Pass 1 & 2; Pass 3 stays on numbered-line text protocol. If endpoint is Tier-3-only (plain text), degrade gracefully: all attribution → low-confidence → safe default.
- **D-48:** `translate_file` extended to be Bible-aware; whole-Bible failure quarantines. Sole concurrency gate remains `LLMClient._semaphore` — no new semaphore. CLI loop passes `eligible_item` and `session_factory`.
- **D-49:** `episode_key = f"S{season:02d}E{episode:02d}"` for episodes; stable single key for movies (Claude's discretion on exact movie key form).
- **D-50:** New `TrezarrSettings` fields: `pronoun_confidence_threshold`, `pronoun_safe_default`, `attribute_context_lines_k`, optional `enable_pass1_analysis` / `enable_attribution` toggles, Pass-1 chunking knobs. Grouped under a Phase-5 comment header mirroring Phase-3/4 grouping.

### Claude's Discretion
Module layout (`trezarr/bible/analyze.py`, `trezarr/translate/attribute.py`, `trezarr/translate/reconcile.py` vs folding); exact Pydantic shapes of `BibleAnalysis`/`LineAttribution`/`AddressMapDTO`; confidence float vs enum; exact pronoun-hint prompt syntax; Vietnamese kinship-pair table contents; Pass-1 chunking merge strategy; reconciliation tie-break rule; movie episode-key string; Address-Map store API shape; whether to add a `get_address_pair` read accessor; default numeric values for all new settings; how attribution vs translation failure are distinguished in quarantine reason.

### Deferred Ideas (OUT OF SCOPE)
- Relationship evolution across episodes → Phase 6
- LLM self-review pass → Phase 6
- Bible editor UI + lock-setting → Phase 8
- Source-language selection → Phase 10
- Confidence-flagging UI → v2
- Folding Pass 2 into Pass 3 (cost concern) → revisit only if cost matters
- Bazarr inventory / continuous daemon → Phases 7/10
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENG-04 | Two-pass pipeline — Pass 1 analyzes full file + metadata to build/update Bible BEFORE Pass 2 translates any line | Pass 1 barrier pattern; `translate_file` flow ordering; `load_series_bible` + `get_or_create_series` calls before any batch dispatch |
| BIBLE-03 | Directed Address Map — per ordered character pair: self-term + address-term | `AddressMap` ORM table already exists empty; new `upsert_address_pair` API in `store.py`; reconciliation algorithm |
| PRON-01 | Infer speaker and addressee for each line from dialogue, turn-taking, vocatives | Pass 2 `attribute.py`; batched over same batches as translation; `LineAttribution` Pydantic shape |
| PRON-02 | Apply correct pronoun pair from Address Map based on inferred speaker→addressee | Pass 3 prompt extension in `build_translate_prompt`; per-line hints; deterministic lookup |
| PRON-03 | Low-confidence attribution → fall back to safe register, never risk wrong intimate pronoun | Confidence threshold gate; `pronoun_safe_default` settings; safe-default selection logic |
</phase_requirements>

---

## Summary

Phase 5 transforms the Phase-2 mechanical translator into a three-pass Bible-aware pipeline. The core insight — and the project's primary value proposition — is that Vietnamese relational pronoun consistency cannot be achieved inside a single translation pass because the correct pronoun pair depends on *who is speaking to whom*, information that English source subtitles have already flattened. The three-pass split enforces a strict ordering: analyze the whole file first (building ground truth into the Bible), then infer speaker/addressee per line, then translate with that ground truth as explicit instruction rather than a probabilistic guess.

The existing codebase (Phases 1–4) provides almost all the infrastructure: `LLMClient.call(response_model=...)` for structured outputs, `batch_subdoc` for context-window-respecting cue batching, the `merge_inferred`/`upsert_*` contract for lock-respecting Bible writes, and the quarantine+ledger idempotency machinery for per-file failure handling. Phase 5 adds three new modules (`analyze.py`, `attribute.py`, `reconcile.py`), two new store functions (`upsert_address_pair`, `load_address_map`), three new Pydantic shapes (`BibleAnalysis`, `LineAttribution`, `AddressMapDTO`), and extends `translate_file`'s signature and flow. No new Alembic migration is needed — the `address_map` table was created empty in Phase 4.

The structural guarantee for "no pronoun flips" (success criterion #3) is architectural: Pass 3 does a deterministic lookup from the Address Map and injects the result as an instruction. The LLM is told which pronoun pair to use; it is not asked to decide. This is the design inversion that makes consistency a property of the code, not a prayer about model behavior.

**Primary recommendation:** Implement Phase 5 as three focused modules wired through a minimally-modified `translate_file`. The barrier between Pass 1 and Passes 2/3 is the central correctness guarantee — never skip it, never merge it with Pass 2.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Pass 1: Bible analysis (full-file holistic) | API/Backend (`trezarr/bible/analyze.py`) | Bible store (`bible/store.py`) | LLM call is I/O; merge goes through store contract |
| Pass 2: Per-cue speaker/addressee attribution | API/Backend (`trezarr/translate/attribute.py`) | Batching (`translate/batching.py`) | Reuses `batch_subdoc` with wider K; structured LLM call |
| Deterministic reconciliation | API/Backend (`trezarr/translate/reconcile.py`) | Bible store (Address Map write) | Pure algorithm on in-memory attribution results + kinship table |
| Pass 3: Pronoun-aware translation | API/Backend (`trezarr/translate/engine.py`) | `build_translate_prompt` extension | Extends existing engine; Address Map provides hints |
| Address Map persistence | Database (`trezarr/bible/store.py`) | ORM (`bible/models.py`) | Mirrors upsert_character/upsert_term pattern; no SQLA outside store |
| Episode key derivation | API/Backend (`trezarr/translate/engine.py`) | `trezarr/arr/sonarr.py` (MediaItem) | Computed from `MediaItem.season_number` + episode number |
| Safe-default pronoun selection | API/Backend (`trezarr/translate/reconcile.py`) | Config (`config.py` D-50) | Pure function over kinship table + inferred gender; configurable default |
| Pipeline orchestration / barrier | API/Backend (`trezarr/translate/engine.py`) | `trezarr/cli.py` (pass-through of context) | `translate_file` is the sole orchestrator; cli wires session_factory + eligible_item |

---

## Standard Stack

No new packages required. [VERIFIED: codebase grep] All capabilities are implemented using libraries already present in the project.

### Core (already installed, reused directly)
| Library | Current Version | Phase-5 Use |
|---------|-----------------|-------------|
| `openai` (AsyncOpenAI) | 2.38.x | `LLMClient.call(response_model=BibleAnalysis)` for Pass 1; `response_model=LineAttribution` for Pass 2 |
| `pydantic` | 2.13.x | `BibleAnalysis`, `LineAttribution`, `AddressMapDTO` response/DTO models |
| `sqlalchemy` (async) + `aiosqlite` | 2.0.x + 0.22.x | Address Map `INSERT`/`SELECT` via existing store pattern |
| `pydantic-settings` | 2.14.x | Phase-5 `TrezarrSettings` fields (D-50) |

### No New Dependencies
Phase 5 introduces no new packages. The package legitimacy audit section is omitted because no new packages are installed.

---

## Architecture Patterns

### System Architecture Diagram

```
cli.py translate loop
        │
        │ eligible_item, session_factory, settings, llm_client, ledger
        ▼
translate_file() [engine.py — extended]
        │
        ├─ [1] get_or_create_series(session_factory, ...) ──► SeriesDTO
        │
        ├─ [2] load_series_bible(session_factory, series_id) ──► SeriesBibleDTO
        │       └─ existing characters, terms, register, address_map entries
        │
        ├─ [BARRIER: Pass 1] analyze_file(source_doc, bible, arr_metadata, llm_client, settings)
        │       │
        │       │   LLMClient.call(response_model=BibleAnalysis)
        │       │   ← Three-tier path (json_schema → json_object → text-fallback)
        │       │
        │       ├─► merge_inferred(series_dto, {"register": ...}) → SeriesDTO
        │       ├─► upsert_character(session_factory, ...) × N chars
        │       ├─► upsert_term(session_factory, ...) × N terms
        │       └─► upsert_address_pair(session_factory, ...) × N observed pairs
        │               └─ + infer reciprocals from kinship table (unlocked, lower-confidence)
        │
        │       [Quarantine here if Pass 1 fails after retries — never proceed to Pass 2/3]
        │
        ├─ [3] load_series_bible() again ──► fresh SeriesBibleDTO (with Address Map)
        │
        ├─ [Pass 2] attribute_batches(batches, bible, llm_client, settings)
        │       │
        │       │   asyncio.gather over batches
        │       │   LLMClient.call(response_model=List[LineAttribution]) per batch
        │       │
        │       └─► List[LineAttribution] (speaker, addressee, confidence per cue)
        │
        ├─ [4] reconcile_attributions(attributions, bible, settings)
        │       │
        │       │   For each observed (speaker_id, addressee_id) pair:
        │       │     - first high-confidence wins → (self_term, address_term)
        │       │     - tie-break by frequency
        │       │     - reciprocal coherence check vs kinship table
        │       │     - upsert_address_pair(session_factory, ...) → Address Map
        │       │
        │       └─► ResolvedPairMap: {(speaker_id, addressee_id) → (self_term, address_term)}
        │
        ├─ [Pass 3] translate_batches(batches, attributions, resolved_map, settings, llm_client)
        │       │
        │       │   asyncio.gather over batches
        │       │   build_translate_prompt(texts, ctx_before, ctx_after,
        │       │       pronoun_hints={line_idx: (self_term, addr_term)})
        │       │   LLMClient.call(plain text — numbered-line protocol)
        │       │
        │       └─► translated SubDoc
        │
        ├─ validate_subdoc() gate [unchanged — D-16/D-17]
        │
        ├─ write_vi_sidecar() [unchanged — D-19]
        │
        └─ ledger.record(status="done") [unchanged — D-20]
```

### Recommended Project Structure

```
trezarr/
├── bible/
│   ├── analyze.py       # NEW: Pass-1 BibleAnalysis prompt + merge orchestration
│   ├── store.py         # EXTEND: add upsert_address_pair, load_address_map
│   ├── dto.py           # EXTEND: add AddressMapDTO
│   ├── models.py        # NO CHANGE (AddressMap table already exists)
│   ├── merge.py         # NO CHANGE
│   └── ...
├── translate/
│   ├── attribute.py     # NEW: Pass-2 attribution prompt + LineAttribution parsing
│   ├── reconcile.py     # NEW: deterministic reconciliation + kinship table
│   ├── engine.py        # EXTEND: translate_file signature + 3-pass flow
│   ├── batching.py      # NO CHANGE (reused as-is by Pass 2 and Pass 3)
│   └── ...
└── config.py            # EXTEND: Phase-5 settings fields (D-50)

tests/
├── bible/
│   └── test_address_map.py     # NEW: upsert_address_pair, load_address_map
├── translate/
│   ├── test_analyze.py         # NEW: BibleAnalysis prompt + merge mocks
│   ├── test_attribute.py       # NEW: LineAttribution parsing + confidence gate
│   ├── test_reconcile.py       # NEW: deterministic reconciliation + kinship table
│   └── test_pronoun_engine.py  # NEW: end-to-end 3-pass integration (mocked LLM)
```

---

## Key Pattern 1: Pass-1 Bible Analysis

**What:** A holistic full-file LLM call that reads all cues + existing Bible + arr_metadata and returns a `BibleAnalysis` Pydantic model.

**Pydantic shape (Claude's discretion, recommended):**
```python
# Source: trezarr/bible/analyze.py  [ASSUMED — new module]
from pydantic import BaseModel

class AddressMapInference(BaseModel):
    speaker_name: str          # original_latin_name of speaker
    addressee_name: str        # original_latin_name of addressee
    self_term: str             # Vietnamese first-person term used by speaker
    address_term: str          # Vietnamese term used to address addressee
    confidence: float          # 0.0–1.0

class CharacterInference(BaseModel):
    original_latin_name: str
    gender: str | None = None
    rough_age: str | None = None
    role: str | None = None

class TermInference(BaseModel):
    source_term: str
    vietnamese_rendering: str
    category: str | None = None  # "proper_noun"|"title"|"place"|"jargon"

class BibleAnalysis(BaseModel):
    register: str | None = None           # series tone inferred from metadata + dialogue
    characters: list[CharacterInference] = []
    terms: list[TermInference] = []
    address_map: list[AddressMapInference] = []
```

**Prompt structure:** [ASSUMED — recommended pattern]
```
You are analyzing a subtitle file to build a Series Bible for Vietnamese translation.

EXISTING BIBLE CONTEXT (do not contradict locked entries):
Register: {bible.register_value or "unknown"}
Characters: {format_characters(bible.characters)}
Address Map (locked): {format_locked_address_map(bible.address_map)}

SERIES METADATA:
Title: {arr_metadata.get("title")}
Genre: {arr_metadata.get("genres")}
Overview: {arr_metadata.get("overview")}
Year: {arr_metadata.get("year")}

DIALOGUE SAMPLE (first {N} cues):
{numbered_cues}

Analyze and return:
1. Register/tone (formal/casual/historical/contemporary)
2. Characters with gender, approximate age, role
3. Recurring proper nouns/terms with Vietnamese rendering
4. Directed address pairs: for each (speaker, addressee) pair that exchanges
   dialogue, what Vietnamese first-person and address terms do they use?
   (Consider: romantic convention anh/em, hierarchical ông/cô, etc.)
```

**Token budget for Pass 1:** [ASSUMED — recommended approach]

The full dialogue of a standard episode (300–800 cues × ~80 chars avg) is roughly 24,000–64,000 characters ≈ 7,000–18,000 tokens of input. With a typical 32K context window (`llm_context_window`), and accounting for 30% overhead and the system prompt + existing Bible (which grows with episodes), the full file usually fits in one call. For long files, chunk by scene boundary (use the same `translate_scene_gap_ms` gap detector from `batch_subdoc`), run per-chunk analysis calls concurrently (they each read from the same Bible but only write after all calls complete), then merge chunk results by union (characters/terms = union; register = most-common across chunks; address_map = union of observed pairs, aggregating confidence).

**Three-tier degradation for Pass 1 (D-47):**
- Tier 1/2 (json_schema / json_object): `BibleAnalysis` is returned as a typed Pydantic object → merge normally.
- Tier 3 (plain text only): The structured passes cannot produce a usable `BibleAnalysis`. Per D-47, degrade gracefully: skip the Bible merge (log a warning), skip Pass 2 (no attribution data), skip pronoun hints in Pass 3. The file translates as Phase-2 did — mechanically — but is not quarantined. This is the least-bad option for endpoints that truly cannot do JSON. Toggle `enable_pass1_analysis=False` produces the same effect explicitly.

---

## Key Pattern 2: Address Map Store Extension

**What:** Add `upsert_address_pair` and `load_address_map` to `trezarr/bible/store.py`, following the exact pattern established by `upsert_character`/`upsert_term`.

**Critical constraints from existing code:**
- [VERIFIED: codebase] `AddressMap` ORM model exists at `trezarr/bible/models.py:153` with columns: `id`, `series_id`, `speaker_character_id`, `addressee_character_id`, `self_term`, `address_term`, `valid_from_episode`, `locked_fields`.
- [VERIFIED: codebase] The store has no `MERGEABLE_FIELDS` entry for `"address_map"` — this must be added.
- [VERIFIED: codebase] `VALID_SOURCES` includes `"inference"` — use this for all Phase-5 writes.
- [VERIFIED: codebase] No transaction may be opened inside another — the session/begin pattern is mandatory.

**AddressMapDTO (add to `dto.py`):**
```python
# Source: trezarr/bible/dto.py  [ASSUMED — new DTO]
class AddressMapDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    speaker_character_id: int
    addressee_character_id: int
    self_term: str | None = None
    address_term: str | None = None
    valid_from_episode: str | None = None
    locked_fields: list[str] = []
```

**`upsert_address_pair` signature (recommended):**
```python
# Source: trezarr/bible/store.py  [ASSUMED — new function]
async def upsert_address_pair(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    speaker_character_id: int,
    addressee_character_id: int,
    self_term: str | None = None,
    address_term: str | None = None,
    valid_from_episode: str | None = None,
    episode_key: str | None = None,
    source: str = "inference",
) -> tuple[AddressMapDTO, list[BibleEventDTO]]:
    ...
```

**Identity key:** `(series_id, speaker_character_id, addressee_character_id)` — one row per directed ordered pair. The `MERGEABLE_FIELDS["address_map"]` whitelist is `frozenset({"self_term", "address_term", "valid_from_episode"})`.

**Lock precedence:** Identical to `upsert_character` — `locked_fields` is checked inside `_merge_inferred_in_session`. A row with `"self_term"` in `locked_fields` is never overwritten by inference. Phase 5 never sets locks (Phase 8 does via the UI).

**`load_address_map` (read accessor, recommended):**
```python
# Source: trezarr/bible/store.py  [ASSUMED — new function]
async def load_address_map(
    session_factory: async_sessionmaker[AsyncSession],
    series_id: int,
) -> list[AddressMapDTO]:
    """Load all Address Map entries for a series."""
    ...
```

Alternatively, extend `SeriesBibleDTO` with `address_map: list[AddressMapDTO] = []` and load it via `selectinload` in `load_series_bible`. This is the recommended approach — it means Pass 3 always has the map without an extra query, and the existing "reload Bible after Pass 1 merge" step (D-48) already provides it fresh.

**Extend `load_series_bible` to include address_map:**
```python
# In store.py load_series_bible — extend selectinload
stmt = (
    select(Series)
    .where(Series.id == series_id)
    .options(
        selectinload(Series.characters),
        selectinload(Series.terms),
        selectinload(Series.address_maps),   # add this relationship
    )
)
```
This requires adding `address_maps` relationship to `Series` model (back-populates `AddressMap.series`).

---

## Key Pattern 3: Pass-2 Attribution

**What:** Batched per-cue speaker/addressee inference, reusing `batch_subdoc` with a wider `attribute_context_lines_k`.

**`LineAttribution` shape (Claude's discretion, recommended):**
```python
# Source: trezarr/translate/attribute.py  [ASSUMED — new module]
from enum import Enum
from pydantic import BaseModel

class AttributionConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class LineAttribution(BaseModel):
    line_index: int                          # 1-based, matching numbered-line protocol
    speaker: str | None = None              # original_latin_name or None
    addressee: str | None = None            # original_latin_name or None
    confidence: AttributionConfidence = AttributionConfidence.LOW

class BatchAttribution(BaseModel):
    attributions: list[LineAttribution]
```

**Why enum not float:** Enum maps directly onto D-43's "confidence 0–1 or enum `high|medium|low`" choice and aligns with D-45's threshold ("`default ~0.6 / medium`"). An enum is easier to reason about in reconciliation and in tests. Claude's discretion — float is equally valid.

**Attribution prompt structure:** [ASSUMED]
```
You are identifying the SPEAKER and ADDRESSEE for each subtitle line.
Context: This is a {register} {genre} series. Known characters: {character_list}.

[CONTEXT — read only]
[context] {context_before_texts}

[LINES TO ATTRIBUTE]
[1] {text}
[2] {text}
...

[CONTEXT — read only]
[context] {context_after_texts}

For each numbered line, output: [N] speaker=<name or "unknown"> addressee=<name or "unknown"> confidence=<high|medium|low>
If dialogue direction is unclear, use confidence=low and unknown.
```

**Wider context K:** `attribute_context_lines_k` defaults larger than `translate_context_lines_k` (recommend 8 vs 3) because turn-taking vocatives require more dialogue history. This is a new `TrezarrSettings` field (D-50).

**Name matching:** After Pass 2 returns `speaker`/`addressee` names, match them against `bible.characters` by `original_latin_name` (case-insensitive, strip whitespace). Unmatched → resolve to `(None, None)` → safe default in reconciliation (D-45). Never crash on unmatched names (D-43).

**Tier-3 degradation:** If `LLMClient._mode == "text"` and Pass 2 cannot produce structured output, return all attributions as `confidence=LOW`, `speaker=None`, `addressee=None`. Pass 3 then uses `pronoun_safe_default` for every line (D-47). This is the graceful degradation path.

---

## Key Pattern 4: Deterministic Reconciliation

**What:** Post-Pass-2 pure algorithm producing one `(self_term, address_term)` per ordered pair for the entire episode. [ASSUMED — standard algorithm, grounded in D-44]

```python
# Source: trezarr/translate/reconcile.py  [ASSUMED — new module]
from collections import Counter

def reconcile_attributions(
    attributions: list[LineAttribution],
    bible: SeriesBibleDTO,
    settings: TrezarrSettings,
) -> dict[tuple[int, int], tuple[str, str]]:
    """
    Returns: {(speaker_char_id, addressee_char_id): (self_term, address_term)}
    """
    ...
```

**Algorithm:**
1. For each attribution where `speaker` and `addressee` both matched to known characters:
   a. Look up `(speaker_char_id, addressee_char_id)` in the existing Address Map (from reloaded Bible).
   b. If locked Address Map entry exists → use it (respects Phase-8 human locks).
   c. If not locked, collect all `confidence == HIGH` attributions for this pair from Pass 2; pick the first one seen (D-44: "first high-confidence wins").
   d. If no HIGH-confidence attributions, tie-break by frequency among MEDIUM-confidence attributions.
   e. If still no usable attribution, keep any existing unlocked Address Map entry from a prior episode.
   f. If nothing, use `pronoun_safe_default`.
2. For each resolved pair, call `upsert_address_pair(session_factory, ...)` to persist (overwrites unlocked rows; respects locked rows via merge contract).
3. Reciprocal coherence check: for pair `(A→B, self_term=X, address_term=Y)`, look up the kinship table to verify `(B→A)` should be `(self_term=Y, address_term=X)`. If B→A is not yet in the Address Map, infer it and write it as `source="inference"`, `confidence=LOW` (D-42).
4. Return the resolved `{(speaker_id, addressee_id): (self_term, address_term)}` in-memory map for Pass 3.

**The resolved in-memory map is the pass-3 lookup table — it does not require a DB read in the hot path.**

---

## Key Pattern 5: Vietnamese Kinship-Pair Table

The reciprocal kinship table encodes the standard pairings. [ASSUMED based on linguistics sources cited in PITFALLS.md — Wikipedia Vietnamese pronouns + Migaku guide]

```python
# Source: trezarr/translate/reconcile.py  [ASSUMED]
# Standard Vietnamese kinship pronoun reciprocal pairs.
# (self_term, address_term) → expected reciprocal (self_term, address_term) for B→A
KINSHIP_RECIPROCAL: dict[tuple[str, str], tuple[str, str]] = {
    # Romantic / close-age heterosexual convention (very common in drama)
    ("anh", "em"):   ("em", "anh"),
    ("em", "anh"):   ("anh", "em"),
    ("chị", "em"):   ("em", "chị"),
    ("em", "chị"):   ("chị", "em"),
    # Elder/younger same-sex
    ("anh", "anh"):  ("anh", "anh"),   # close-age male peers
    ("chị", "chị"):  ("chị", "chị"),   # close-age female peers
    # Formal/authority — one-directional asymmetric
    ("ông", "cháu"): ("cháu", "ông"),
    ("bà", "cháu"):  ("cháu", "bà"),
    ("ông", "con"):  ("con", "ông"),
    ("bà", "con"):   ("con", "bà"),
    ("bố", "con"):   ("con", "bố"),
    ("mẹ", "con"):   ("con", "mẹ"),
    ("cha", "con"):  ("con", "cha"),
    # Formal neutral — not intimate
    ("tôi", "bạn"):  ("bạn", "tôi"),
    ("tôi", "anh"):  ("anh", "tôi"),
    ("tôi", "chị"):  ("chị", "tôi"),
    ("tôi", "ông"):  ("ông", "tôi"),
    ("tôi", "bà"):   ("bà", "tôi"),
}

# Safe neutral/polite default — used when confidence is below threshold
# or when speaker/addressee is unknown
SAFE_DEFAULT_SELF = "tôi"
SAFE_DEFAULT_ADDRESS_MALE = "anh"
SAFE_DEFAULT_ADDRESS_FEMALE = "chị"
SAFE_DEFAULT_ADDRESS_NEUTRAL = "bạn"  # when gender unknown
```

**Note on the table:** This is a curated subset of the most common pairings in contemporary drama. [ASSUMED — based on cited linguistics sources] The full Vietnamese pronoun system has many more terms (`cô`, `chú`, `bác`, `cậu`, `dì`, etc.) but the above covers ~90% of dramatic dialogue. The table should be hardcoded in `reconcile.py` with a comment noting it can be extended. The `pronoun_safe_default` settings field (D-50) allows operators to override the default pair.

**Safe-default selection logic (D-45):**
```python
def get_safe_default(
    addressee_gender: str | None,
    settings: TrezarrSettings,
) -> tuple[str, str]:
    """Return (self_term, address_term) for low-confidence attributions."""
    if settings.pronoun_safe_default:
        return settings.pronoun_safe_default  # user override
    address = {
        "male": SAFE_DEFAULT_ADDRESS_MALE,
        "female": SAFE_DEFAULT_ADDRESS_FEMALE,
    }.get(addressee_gender or "", SAFE_DEFAULT_ADDRESS_NEUTRAL)
    return (SAFE_DEFAULT_SELF, address)
```

---

## Key Pattern 6: Pass-3 Pronoun Hints in `build_translate_prompt`

**What:** Extend `build_translate_prompt` to accept an optional `pronoun_hints` dict and inject per-line instructions. [VERIFIED: codebase — current signature does not include pronoun hints]

**Current signature:**
```python
def build_translate_prompt(
    batch_texts: list[str],
    context_before: list[str],
    context_after: list[str],
    source_lang: str = "English",
) -> str:
```

**Extended signature (D-46):**
```python
def build_translate_prompt(
    batch_texts: list[str],
    context_before: list[str],
    context_after: list[str],
    source_lang: str = "English",
    pronoun_hints: dict[int, tuple[str, str]] | None = None,
    # pronoun_hints: {1-based line index → (self_term, address_term)}
) -> str:
```

**Hint injection format (D-46, recommended):**
```
[LINES TO TRANSLATE]
[1] (speaker says: anh; addresses as: em) I missed you so much.
[2] I'll be home soon.
[3] (speaker says: em; addresses as: anh) Are you sure?
```

Lines without attribution hints receive no prefix — they translate using whatever pronoun the model infers naturally (which is acceptable for non-dialogue or single-speaker lines).

**Preserved invariants:**
- Numbered-line 1:1 protocol: line numbers correspond exactly to `batch_texts` indices (1-based). [VERIFIED: codebase — `_NUMBERED_LINE_RE` forgiving parser and count validation unchanged]
- Sentinel protection: `extract_sentinels` / `reinsert_sentinels` runs BEFORE building the prompt, so `<<T0>>` tokens are already extracted from `batch_texts`. Pronoun hints are added to the cleaned text, not the raw text. [VERIFIED: codebase — `_translate_batch_inner` extracts sentinels first at step 1]
- Document gate: `validate_subdoc` gate is unchanged. [VERIFIED: codebase]
- No `response_model` in Pass 3. [VERIFIED: codebase — `llm_client.call(messages)` has no response_model arg in _translate_batch]

---

## Key Pattern 7: `translate_file` Signature and Flow Extension

**Current signature:** [VERIFIED: codebase]
```python
async def translate_file(
    path: str | Path,
    settings: "TrezarrSettings",
    llm_client: LLMClient,
    ledger: LedgerProtocol,
) -> TranslationResult:
```

**Extended signature (D-48):**
```python
async def translate_file(
    path: str | Path,
    settings: "TrezarrSettings",
    llm_client: LLMClient,
    ledger: LedgerProtocol,
    eligible_item: "EligibleItem | None" = None,
    session_factory: "async_sessionmaker[AsyncSession] | None" = None,
) -> TranslationResult:
```

Default `None` for both new args maintains backward compatibility with existing callers (the Phase-4 integration tests and CLI path). When both are `None`, Phase-5 Bible logic is bypassed — mechanical translation only (equivalent to `enable_pass1_analysis=False`).

**CLI wiring (D-48):** [VERIFIED: codebase — cli.py L176 holds `session_factory`, L291 holds `eligible_item`]
```python
# cli.py translate loop — change:
result = await translate_file(source_sub_path, settings, llm_client, ledger)

# To:
result = await translate_file(
    source_sub_path, settings, llm_client, ledger,
    eligible_item=eligible_item,
    session_factory=session_factory,
)
```

**Extended flow (D-48, ordered):**
```
[Unchanged: Steps 1–4 from Phase 2 — resolve path, hash, derive dest, ledger check, record in_progress]

[NEW: Step 4.5 — Bible setup (only when eligible_item and session_factory provided)]
  series_dto = await get_or_create_series(session_factory, ...) from eligible_item.media_item
  episode_key = derive_episode_key(eligible_item.media_item)  # D-49
  bible = await load_series_bible(session_factory, series_dto.id)

[NEW: Pass 1 BARRIER — analyze and merge]
  try:
      analysis = await analyze_file(source_doc, bible, arr_metadata, llm_client, settings, episode_key)
      await merge_bible_analysis(session_factory, series_dto, analysis, episode_key)
  except (BibleAnalysisError, BatchValidationError) as exc:
      → quarantine (reason="pass1 analysis failure: {exc}") + ledger.record(quarantined)
      → return TranslationResult(status="quarantined")
  # Note: transient openai.APIError NOT caught here — same as Pitfall 5 / D-18

[NEW: Step 5.5 — reload Bible with fresh Address Map]
  bible = await load_series_bible(session_factory, series_dto.id)

[NEW: Pass 2 — attribution (asyncio.gather over batches)]
  try:
      attributions: list[list[LineAttribution]] = await asyncio.gather(
          *[attribute_batch(b, bible, llm_client, settings) for b in batches]
      )
  except AttributionError as exc:
      → quarantine (reason="pass2 attribution failure: {exc}")
      → return TranslationResult(status="quarantined")

[NEW: Step 6.5 — reconcile + persist Address Map]
  flat_attributions = [a for batch in attributions for a in batch]
  resolved_map = await reconcile_attributions(
      flat_attributions, bible, session_factory, series_dto.id, episode_key, settings
  )

[Existing Step 7 — Pass 3 (asyncio.gather, modified)]
  batches augmented with pronoun_hints from resolved_map before dispatch
  _translate_batch extended to accept+use pronoun_hints

[Unchanged: Steps 8–12 — assemble, gate, write, ledger.record(done)]
```

**Quarantine reason taxonomy (Claude's discretion, recommended):**
- `"pass1 analysis failure: {exc}"` — Pass 1 failed after exhausting retries
- `"pass2 attribution failure: {exc}"` — Pass 2 failed (unlikely with graceful degradation, but possible if settings.enable_attribution=True and strict mode)
- Existing: `"read/batch failure: ..."`, `"retry exhaustion: ..."`, gate failures

**Episode key derivation (D-49):**
```python
# Source: trezarr/translate/engine.py  [ASSUMED]
def derive_episode_key(media_item: "MediaItem") -> str:
    """Derive a stable episode key for Address Map valid_from_episode."""
    if media_item.source_type == "episode":
        season = media_item.season_number or 0
        # episode_number is not currently on MediaItem — it may need to be
        # added OR derived from the source_sub_path filename
        # e.g. parse "S01E03" from the filename stem
        ...
        return f"S{season:02d}E{episode:02d}"
    else:
        # Movie — stable single key (D-49: Claude's discretion)
        slug = (media_item.title or "movie").lower().replace(" ", "-")[:20]
        return f"movie-{slug}"
```

**Note:** `MediaItem` (sonarr.py) does not currently have an `episode_number` field. [VERIFIED: codebase — sonarr.py MediaItem has `season_number` but not `episode_number`] The planner must decide: (a) add `episode_number` to `MediaItem` (sonarr.py) OR (b) parse it from the source subtitle filename stem (which already encodes `S01E01` in standard *arr naming). Option (b) is lower-risk as it avoids touching the Phase-3 discovery layer.

---

## Key Pattern 8: New `TrezarrSettings` Fields (D-50)

```python
# Source: trezarr/config.py  [ASSUMED — new section]
# ── Phase 5: Three-Pass Pronoun Engine (D-40…D-50) ─────────────────────────
# Pass 1 — Bible analysis
enable_pass1_analysis: bool = True         # D-50: toggle for staged rollout/tests
pass1_max_cues_per_chunk: int = 400        # D-50: cues per Pass-1 chunk (0 = no chunk)

# Pass 2 — Attribution
enable_attribution: bool = True            # D-50: toggle; False → all lines get safe default
attribute_context_lines_k: int = 8        # D-50: wider context than translate (default 3)
attribute_max_cues_per_batch: int = 30    # D-50: attribution batches may be smaller

# Pass 3 — Pronoun application
pronoun_confidence_threshold: str = "medium"  # D-45/D-50: "high"|"medium"|"low"
# pronoun_safe_default: None means use the built-in kinship-table defaults (D-45)
pronoun_safe_default: tuple[str, str] | None = None  # D-50: (self_term, address_term)
```

**Notes:**
- `pronoun_safe_default` as `tuple[str, str] | None` — pydantic-settings supports tuple deserialization from JSON env var. [ASSUMED — pydantic v2 handles this]. If operators want a fixed override, they set e.g. `TREZARR_PRONOUN_SAFE_DEFAULT='["tôi","bạn"]'`.
- `enable_pass1_analysis=False` + `enable_attribution=False` → Phase-2 mechanical behavior (useful for rollback and per-file testing).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Concurrent LLM calls with rate-limit cap | Another `asyncio.Semaphore` in the engine | `LLMClient._semaphore` (D-06, Pitfall 1) — already exists and is the sole gate |
| Retry on Pass-1/2 transient errors | External retry wrapper around analyze/attribute | SDK `max_retries=4` handles transport retries; `BatchValidationError` + tenacity handles logic retries — same as Pass 3 |
| JSON parsing of structured LLM output | Custom regex/JSON parser | `LLMClient.call(response_model=BibleAnalysis)` Tier-1 path gives a typed Pydantic object; Tier-2 gives JSON string for manual `BibleAnalysis.model_validate_json()` |
| Address Map persistence logic | Direct SQLAlchemy in `engine.py` | `upsert_address_pair(session_factory, ...)` in `store.py` (D-39 — no SQLAlchemy outside `store.py`) |
| String-replacement pronoun substitution | Post-hoc regex replace | Pronoun hints in the prompt (D-46) — Vietnamese grammar is context-sensitive; string replacement corrupts it |
| Pronoun pair lookup during translation | Second DB query inside Pass 3 | In-memory `resolved_map` dict built during reconciliation — no DB access in hot path |
| New migration for Address Map | New Alembic migration | Address Map table already exists from Phase 4 baseline migration — only INSERTs needed |

---

## Common Pitfalls

### Pitfall A: New semaphore in analyze.py / attribute.py
**What goes wrong:** Adding `asyncio.Semaphore(4)` in `analyze.py` or `attribute.py` to "limit LLM calls" — this creates a SECOND concurrency gate on top of `LLMClient._semaphore`, causing deadlock or unexpected throttling. [VERIFIED: codebase — engine.py module-level comment explicitly forbids this]
**How to avoid:** All LLM calls in Pass 1 and Pass 2 go through `llm_client.call(...)` which holds the existing semaphore. Do not add another.

### Pitfall B: Quarantining on transient API errors
**What goes wrong:** Catching `openai.APIError` inside the Pass 1 or Pass 2 try/except and quarantining. This permanently marks files as quarantined due to a temporary endpoint outage. [VERIFIED: codebase — PITFALLS.md Pitfall 5, engine.py comment D-18]
**How to avoid:** Only quarantine on `BatchValidationError` / `BibleAnalysisError` (logic failures after retries exhausted). Let `openai.APIError` propagate — the SDK will retry the request, and if the file stays in `in_progress` it will be retried on the next poll cycle.

### Pitfall C: Calling `merge_inferred` for Address Map entries
**What goes wrong:** Trying to use the public `merge_inferred(session_factory, address_map_dto, ...)` for Address Map updates. `merge_inferred` only supports `CharacterDTO`, `TermDTO`, and `SeriesDTO`. [VERIFIED: codebase — store.py:793 TypeError branch]
**How to avoid:** Add `upsert_address_pair` as a new standalone function in `store.py` mirroring `upsert_character`. Also add `MERGEABLE_FIELDS["address_map"]` to the whitelist. Do not try to extend the `isinstance` chain in `merge_inferred` with `AddressMapDTO` — the merge engine was not designed for FKs like `speaker_character_id`.

### Pitfall D: SQLAlchemy import in analyze.py or attribute.py
**What goes wrong:** `from sqlalchemy import select` or `from trezarr.bible.models import AddressMap` appearing in `analyze.py` or `attribute.py`. Violates D-39 — SQLA must never escape `store.py`. [VERIFIED: codebase — dto_boundary test enforces this]
**How to avoid:** Import only `from trezarr.bible.dto import ...` and call `store.py` functions. The import-graph contract test (`tests/bible/test_dto_boundary.py`) will catch violations.

### Pitfall E: Pass 2 batch count misalignment
**What goes wrong:** Pass 2 produces a different number of `LineAttribution` objects than there are cues in the source doc (e.g. because the attribution prompt was sent a different set of batches). If cue→attribution mapping is wrong, pronoun hints in Pass 3 land on the wrong lines.
**How to avoid:** Pass 2 must use the **identical batches** produced by `batch_subdoc(source_doc, settings)`. The `line_index` in `LineAttribution` is 1-based within each batch (matching the numbered-line protocol), not document-global. Reconciliation must re-index to document-global before building `resolved_map`.

### Pitfall F: `episode_number` not on MediaItem
**What goes wrong:** Attempting to call `eligible_item.media_item.episode_number` and getting `AttributeError` because `MediaItem` (sonarr.py) has `season_number` but not `episode_number`. [VERIFIED: codebase — sonarr.py MediaItem fields]
**How to avoid:** Either (a) add `episode_number: int | None = None` to `MediaItem` in Phase 5 Plan-1 (requires updating sonarr.py discovery to populate it), or (b) parse the episode number from `eligible_item.source_sub_path.stem` using the `S\d{2}E\d{2}` pattern. Option (b) is recommended to avoid touching the Phase-3 discovery layer.

### Pitfall G: BibleEvent `series_id` missing from AddressMap entity
**What goes wrong:** `BibleEvent` requires `series_id` on the entity being merged. `AddressMap` has `series_id`. However if trying to reuse `_merge_inferred_in_session` for address_map, the entity_type/dto_cls check will fail. [VERIFIED: codebase — store.py `isinstance` chain only handles Character/Term/Series]
**How to avoid:** Write a dedicated `_upsert_address_pair_in_session` private helper (same pattern as `_upsert_character_in_session`) instead of extending `_merge_inferred_in_session`.

### Pitfall H: `SeriesBibleDTO` does not include Address Map
**What goes wrong:** After Pass 1 merges Address Map entries, `load_series_bible` is called again but returns a `SeriesBibleDTO` without `address_map` (because the relationship is not loaded). Pass 3 then has no pronoun hints for any line.
**How to avoid:** Extend `SeriesBibleDTO` to include `address_map: list[AddressMapDTO] = []` and add `selectinload(Series.address_maps)` to `load_series_bible`. Requires adding the ORM relationship on `Series`.

---

## Runtime State Inventory

This section is omitted — Phase 5 is not a rename/refactor/migration phase. It writes new rows to the existing (empty) `address_map` table and extends existing code. No stored keys or registered names are changing.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `BibleAnalysis`, `LineAttribution`, `BatchAttribution`, `AddressMapDTO`, `AddressMapInference` Pydantic shapes | Standard Stack / Patterns 1, 2, 3 | Shapes need adjustment during implementation — low structural risk, high iteration cost |
| A2 | Vietnamese kinship-pair reciprocal table contents | Pattern 5 | Incomplete table → wrong reciprocal inference → incorrect Address Map entries (correctable via Phase-8 UI) |
| A3 | `attribute_context_lines_k` default of 8 and `attribute_max_cues_per_batch` of 30 | Pattern 7 / Settings | May need tuning per endpoint; wrong defaults degrade attribution quality |
| A4 | `pronoun_safe_default: tuple[str, str] | None` pydantic-settings env deserialization | Settings | May require a custom validator if pydantic-settings doesn't deserialize tuple from JSON array env var |
| A5 | Pass-1 token budget: full episode (~300–800 cues) fits in 32K context in one call | Pattern 1 | Longer episodes or larger models may require chunking even at default window size |
| A6 | Episode number should be parsed from subtitle filename stem, not from MediaItem | Pattern 7 | If future *arr integration always provides episode_number, this parse is redundant but harmless |
| A7 | Extending `build_translate_prompt` with `pronoun_hints` is backward-compatible with default `None` | Pattern 6 | Any call site that passes positional args instead of keyword args for the existing params will break — audit existing calls |
| A8 | `Series.address_maps` ORM relationship (back-populates from `AddressMap`) doesn't exist yet | Pattern 2 | Adding it requires modifying `models.py` — no migration needed, but the models.py change is load-order sensitive |

---

## Open Questions (RESOLVED)

1. **Episode number on MediaItem**
   - What we know: `MediaItem.season_number` is populated; `episode_number` is not a field.
   - What's unclear: Is the episode number available via the existing Sonarr discovery payload?
   - Recommendation: Plan-1 should explicitly decide: add `episode_number` to `MediaItem` (and populate in sonarr.py/radarr.py) vs. parse from filename. The filename-parse approach is a safe MVP.
   - **RESOLVED (plan 05-06):** Episode number is parsed from the subtitle filename stem via `derive_episode_key` using `re.search(r'S(\d{2})E(\d{2})', stem)`. Do NOT add `episode_number` to `MediaItem` — the filename-parse approach avoids touching the Phase-3 discovery layer (Pitfall F).

2. **Pass-1 chunking merge strategy for `address_map` entries**
   - What we know: Characters and terms can be unioned. Register can be majority-voted.
   - What's unclear: How to merge `AddressMapInference` entries when two chunks observe the same pair with different terms (possibly due to different scenes using different registers).
   - Recommendation: Union all observed entries, aggregating confidence (take max confidence across chunks for the same pair). The reconciliation step then picks the winner by first-high-confidence-wins rule.
   - **RESOLVED (plans 05-03 / 05-06):** Union all observed `AddressMapInference` entries across chunks; max-confidence wins per ordered pair when the same pair appears in multiple chunks. Final winner selection is performed during `reconcile_attributions` (first-high-confidence-wins, then frequency tie-break on MEDIUM).

3. **Tier-3 degradation for Pass 1 — quarantine vs. mechanical fallback**
   - What we know: D-47 says "degrade gracefully: treat all attribution as low-confidence → safe default" for Tier-3-only endpoints.
   - What's unclear: D-48 also says "whole-Bible failure quarantines." Are these contradictory?
   - Recommendation: Distinguish by failure type. Tier-3 endpoint → known limitation → graceful degrade (don't quarantine). Logic failure (malformed JSON, response_model validation error after Tier-2 attempt) after retries → quarantine. The `enable_pass1_analysis` toggle allows operators to disable Pass 1 entirely for Tier-3 endpoints.
   - **RESOLVED (plans 05-04 / 05-05):** A Tier-3-only endpoint (plain text) triggers graceful degradation — `analyze_file` returns an empty `BibleAnalysis` (no LLM data, no merge) and `attribute_batch` returns all-LOW-confidence, all-None attributions. The file translates mechanically (Pass-2-era behavior) and is NOT quarantined. Only a true logic/analysis failure (`BibleAnalysisError` after exhausting Tier-2 retries) triggers quarantine.

4. **`address_map` ORM relationship on `Series` model**
   - What we know: `AddressMap` has `series_id` FK but `Series` has no `address_maps` relationship.
   - What's unclear: Whether adding this back-relationship requires a test model migration.
   - Recommendation: Add `address_maps: Mapped[list["AddressMap"]] = relationship(...)` to `Series`. No Alembic migration needed (relationship is ORM-only; the table and FK already exist). The existing test `db_engine`/`session_factory` fixtures will pick this up automatically.
   - **RESOLVED (plan 05-02):** The `Series.address_maps` relationship is ORM-metadata only — added to `models.py` with no Alembic migration and no test-DB change. The existing `db_engine`/`session_factory` fixtures pick up the relationship automatically at import time.

---

## Environment Availability

Step 2.6: SKIPPED — Phase 5 has no external dependencies beyond what is already installed and verified by prior phases. All packages (`sqlalchemy`, `aiosqlite`, `openai`, `pydantic`, `pydantic-settings`) were verified in the project's existing phase research.

---

## Validation Architecture

`workflow.nyquist_validation` is `true` in `.planning/config.json` — this section is required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/translate/test_pronoun_engine.py tests/translate/test_reconcile.py tests/bible/test_address_map.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| ENG-04 | Pass 1 runs and Bible is updated BEFORE any line is translated | integration (mocked LLM) | `pytest tests/translate/test_pronoun_engine.py::test_pass1_runs_before_pass3 -x` | Mock LLM; verify Bible mutation recorded before any translation call |
| ENG-04 | Pass 1 failure quarantines file without writing any translation | unit | `pytest tests/translate/test_pronoun_engine.py::test_pass1_failure_quarantines -x` | Inject `BibleAnalysisError`; assert `quarantined` result, no sidecar written |
| BIBLE-03 | Address Map populated with directed pairs after Pass 1 | unit+integration | `pytest tests/bible/test_address_map.py::test_upsert_address_pair -x` | Use in-memory SQLite; verify `address_map` rows |
| BIBLE-03 | Locked Address Map entry is never overwritten | unit | `pytest tests/bible/test_address_map.py::test_locked_pair_not_overwritten -x` | Seed locked row; run upsert; verify unchanged |
| PRON-01 | `LineAttribution` correctly parsed from mock LLM response | unit | `pytest tests/translate/test_attribute.py::test_attribution_parsing -x` | No LLM — parse from string fixture |
| PRON-01 | Unknown speaker/addressee resolved to safe default (no crash) | unit | `pytest tests/translate/test_attribute.py::test_unmatched_name_safe_default -x` | Speaker name not in Bible; assert safe-default used |
| PRON-02 | Reconciled pronoun pair injected as hint in Pass-3 prompt | unit | `pytest tests/translate/test_engine.py::test_pronoun_hint_in_prompt -x` | Extend existing test_engine.py; verify prompt contains hint format |
| PRON-02 | Same character pair uses identical pronoun pair across all batches in one episode | integration | `pytest tests/translate/test_pronoun_engine.py::test_pronoun_consistency_within_episode -x` | Golden-fixture episode with 3+ exchanges; verify all use same pair |
| PRON-03 | Low-confidence attribution uses safe default, not intimate pronoun | unit | `pytest tests/translate/test_reconcile.py::test_low_confidence_safe_default -x` | Confidence=LOW; assert self_term="tôi", no intimate pair |
| PRON-03 | `confidence=HIGH` above threshold uses Address Map pair | unit | `pytest tests/translate/test_reconcile.py::test_high_confidence_uses_address_map -x` | Confidence=HIGH; assert resolved pair matches Address Map entry |
| Success #3 | Reciprocal directions are coherent (A→B "anh/em" ⇒ B→A "em/anh") | unit | `pytest tests/translate/test_reconcile.py::test_reciprocal_coherence -x` | Seed one direction; verify reciprocal inferred |
| Success #4 | Below threshold → safe pair regardless of Address Map content | unit | `pytest tests/translate/test_reconcile.py::test_below_threshold_ignores_address_map -x` | Confidence=MEDIUM with threshold=HIGH; assert safe default used |

### Key Testing Strategy: Determinism Over LLM Nondeterminism

The central testing challenge for this phase is that LLM nondeterminism cannot be allowed to flake tests verifying pronoun consistency. The solution is to test the determinism *property* at the reconciliation layer, not at the LLM inference layer:

1. **Pass 1 and Pass 2 are tested with mocked LLM responses.** The mocks return deterministic `BibleAnalysis` and `BatchAttribution` objects. Tests assert that the reconciliation and Address Map persistence are correct regardless of which LLM produced them.

2. **Success criterion #3 (no flips)** is verified by constructing a fixture `list[LineAttribution]` where the same `(speaker_id, addressee_id)` pair appears in multiple batches with varying confidence. The reconciliation algorithm must produce the same `(self_term, address_term)` for all occurrences. This is a pure algorithm test — no LLM required.

3. **Golden-file integration test:** A fixture episode (20–30 cues, 2 known characters exchanging dialogue, LLM fully mocked) is passed through the complete `translate_file` pipeline. The output `.vi.srt` is checked to contain `"anh"` or `"em"` consistently in all dialogue lines between those characters. This test verifies the end-to-end plumbing without needing a live endpoint.

4. **Tier-3 degradation test:** Set `llm_structured_output_mode="text"` and verify that `translate_file` completes without quarantine, all lines use the safe default pair, and the output is valid.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/translate/test_reconcile.py tests/bible/test_address_map.py -x -q`
- **Per wave merge:** `uv run pytest tests/translate/ tests/bible/ -x -q`
- **Phase gate:** `uv run pytest -x -q` (full suite green before `/gsd-verify-work`)

### Wave 0 Gaps
- [ ] `tests/translate/test_analyze.py` — covers ENG-04 Pass-1 prompt construction and merge orchestration
- [ ] `tests/translate/test_attribute.py` — covers PRON-01 attribution parsing and name matching
- [ ] `tests/translate/test_reconcile.py` — covers D-44 deterministic reconciliation and D-45 confidence gate
- [ ] `tests/translate/test_pronoun_engine.py` — covers end-to-end 3-pass integration (mocked LLM)
- [ ] `tests/bible/test_address_map.py` — covers BIBLE-03 `upsert_address_pair` and `load_address_map`
- [ ] Shared fixture: `AddressMap` session_factory re-export in `tests/bible/conftest.py` (already exists for character/term; needs extension)

---

## Security Domain

`security_enforcement: true` in `.planning/config.json`, `security_asvs_level: 1`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No new auth surface |
| V3 Session Management | No | No new sessions |
| V4 Access Control | No | No new access control |
| V5 Input Validation | Yes | `BibleAnalysis`/`LineAttribution` are validated via Pydantic model parsing; raw LLM output is never trusted without schema validation |
| V6 Cryptography | No | No new crypto |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via subtitle text containing `[LINES TO TRANSLATE]` or `[CONTEXT]` markers | Tampering | Sentinels (`extract_sentinels`) are already applied before building the prompt. No additional change needed for the pronoun-hint injection line — the `(speaker says: X; addresses as: Y)` prefix is model-instruction-style text, not structural formatting. The LLM treats the full prefix-line as the text to translate. |
| Malicious `arr_metadata` snapshot injected into Pass-1 prompt via oversized payload | Tampering / DoS | Already mitigated by the 32 KB `MAX_ARR_METADATA_BYTES` cap in `store.py` (verified in codebase). Include only known fields in the Pass-1 prompt, not raw metadata dump. |
| Address Map poisoning via lock bypass | Tampering | `upsert_address_pair` must respect `locked_fields` via the same `_merge_inferred_in_session` pattern. A locked pair must never be overwritten by inference — this is D-34 applied to Address Map. |
| `pronoun_safe_default` env var injection with malicious Vietnamese string | Tampering | Pydantic validates the tuple shape. Content validation (ensuring it's a genuine Vietnamese term) is out of v1 scope — operators supply their own endpoint. |

---

## Sources

### Primary (HIGH confidence)
- Codebase: `trezarr/translate/engine.py` — current `translate_file` signature, `build_translate_prompt`, `_translate_batch_inner`, quarantine+ledger pattern
- Codebase: `trezarr/translate/batching.py` — `batch_subdoc`, `Batch`, context window mechanics
- Codebase: `trezarr/llm/client.py` — `LLMClient.call(response_model=...)`, three-tier path, sole semaphore
- Codebase: `trezarr/bible/store.py` — `merge_inferred`, `upsert_character`, `upsert_term`, `MERGEABLE_FIELDS`, `VALID_SOURCES`, transaction patterns
- Codebase: `trezarr/bible/dto.py` — `SeriesBibleDTO`, `CharacterDTO`, `TermDTO`, `BibleEventDTO` shapes
- Codebase: `trezarr/bible/models.py` — `AddressMap` ORM table, all columns confirmed
- Codebase: `trezarr/arr/sonarr.py` — `MediaItem` fields (confirmed `season_number` present, `episode_number` absent)
- Codebase: `trezarr/config.py` — `TrezarrSettings` existing fields, Phase-3/4 grouping pattern
- Codebase: `trezarr/cli.py` — L176 `session_factory`, L291 `eligible_item` in scope at translate loop
- `.planning/phases/05-three-pass-pronoun-engine/05-CONTEXT.md` — all D-40…D-50 decisions
- `.planning/REQUIREMENTS.md` — ENG-04, BIBLE-03, PRON-01, PRON-02, PRON-03
- `.planning/research/PITFALLS.md` — Pitfall 1 (semaphore), Pitfall 5 (no quarantine on transient API errors)

### Secondary (MEDIUM confidence)
- `.planning/research/FEATURES.md` — pronoun/Address Map problem framing
- `.planning/research/ARCHITECTURE.md` — Series Bible as consistency substrate
- Wikipedia "Vietnamese pronouns" + Migaku pronoun guide (cited in PITFALLS.md) — kinship pair table basis

### Tertiary (LOW confidence / ASSUMED)
- Vietnamese kinship-pair table contents (A2 above) — curated from PITFALLS.md source citations, not independently verified in this session
- Pass-1 token budget estimate (A5 above) — computed from typical episode cue counts and character estimates

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — no new packages; existing packages verified against codebase
- Architecture: HIGH — grounded in actual code signatures and existing patterns
- Pitfalls: HIGH — most derived from verified codebase constraints (engine.py comments, store.py patterns)
- Vietnamese pronoun table: MEDIUM — linguistics sourced from prior research citations, not independently verified

**Research date:** 2026-06-01
**Valid until:** 2026-07-01 (stable domain; kinship table is timeless, code signatures won't change before planning)
