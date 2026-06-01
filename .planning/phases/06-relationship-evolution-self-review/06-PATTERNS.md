# Phase 6: Relationship Evolution + Self-Review — Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 11 (new + modified)
**Analogs found:** 11 / 11

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `trezarr/bible/models.py` (MODIFY `Series`) | model | CRUD | `Series.address_maps` relationship (same file, lines 93–95) | exact |
| `trezarr/bible/dto.py` (ADD `RelationshipEventDTO`; MODIFY `SeriesBibleDTO`) | model | request-response | `AddressMapDTO` (same file, lines 120–146); `SeriesBibleDTO` (lines 180–215) | exact |
| `trezarr/bible/store.py` (ADD `record_relationship_event`; MODIFY `load_series_bible`) | service | CRUD | `_upsert_address_pair_in_session` / `upsert_address_pair` (lines 581–929); `load_series_bible` selectinload block (lines 173–230) | exact |
| `trezarr/bible/analyze.py` (ADD `RelationshipEventInference`; MODIFY `BibleAnalysis`, `_build_analysis_prompt`, `merge_bible_analysis`) | service | request-response | `AddressMapInference` / `BibleAnalysis` (lines 53–99); `_build_analysis_prompt` (lines 107–205); `merge_bible_analysis` Step 4 (lines 422–487) | exact |
| `trezarr/translate/reconcile.py` (MODIFY `reconcile_attributions`) | service | request-response | lock-check + survivors block in `reconcile_attributions` (lines 204–261); `KINSHIP_RECIPROCAL` reciprocal step (lines 263–291) | exact |
| `trezarr/translate/engine.py` (ADD `build_review_prompt`, `_review_batch`; MODIFY `translate_file` Step 8.5) | service | request-response | `build_translate_prompt` (lines 134–191); `_translate_batch_inner` (lines 273–339); TaskGroup dispatch (lines 680–704); Step 8 assembly (lines 706–725) | exact |
| `trezarr/config.py` (MODIFY `TrezarrSettings`) | config | — | Phase-5 settings group (lines 128–143) | exact |
| `tests/bible/test_relationship_events.py` (NEW) | test | CRUD | `tests/bible/test_address_map.py`; `tests/db/conftest.py` fixture chain | role-match |
| `tests/translate/test_self_review.py` (NEW) | test | request-response | `tests/translate/test_analyze.py`; `tests/translate/test_engine.py` | role-match |
| `tests/translate/test_reconcile.py` (EXTEND) | test | request-response | same file — existing `_make_bible`, `_make_character`, `_make_attribution` helpers (lines 23–137) | exact |
| `tests/bible/conftest.py` (implicit re-export for new test file) | config | — | `tests/translate/conftest.py` (same re-export pattern) | exact |

---

## Pattern Assignments

### `trezarr/bible/models.py` — ADD `Series.relationship_events` relationship

**Analog:** `Series.address_maps` relationship (`trezarr/bible/models.py` lines 93–95)

**Add `relationship_events` to `Series`** (after `address_maps` at line 95):
```python
# trezarr/bible/models.py — append to Series class after address_maps relationship
relationship_events: Mapped[list["RelationshipEvent"]] = relationship(
    back_populates="series", cascade="all, delete-orphan"
)
```

**Add `series` back-reference to `RelationshipEvent`** (after `description` column at line 211):
```python
# trezarr/bible/models.py — append to RelationshipEvent class
series: Mapped["Series"] = relationship(back_populates="relationship_events")
```

**Pattern note:** The existing `RelationshipEvent` model (lines 187–213) has NO `series` back-reference and `Series` has NO `relationship_events` ORM relationship — both additions are required before `selectinload(Series.relationship_events)` can work in `load_series_bible`. This was VERIFIED in the research (A3 assumption confirmed at models.py lines 87–95).

---

### `trezarr/bible/dto.py` — ADD `RelationshipEventDTO`; MODIFY `SeriesBibleDTO`

**Analog:** `AddressMapDTO` (`trezarr/bible/dto.py` lines 120–146); `SeriesBibleDTO` (lines 180–215)

**Imports pattern** (lines 27–32, unchanged — `datetime` already imported):
```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
```

**`RelationshipEventDTO` pattern** — mirror `AddressMapDTO` `from_attributes=True` ConfigDict (lines 136–146):
```python
# trezarr/bible/dto.py — append after AddressMapDTO (line 146)
class RelationshipEventDTO(BaseModel):
    """Relationship transition entry DTO (BIBLE-07).

    model_config mirrors AddressMapDTO: from_attributes=True only — no aliases needed,
    column names match Python field names 1:1.

    Note: suggested_self_term / suggested_address_term are NOT persisted to DB
    (the relationship_event schema is locked from Phase 4, D-31). They are
    populated from RelationshipEventInference in-memory and carried through
    reconciliation only.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    character_a_id: int
    character_b_id: int
    episode_marker: str
    description: str | None = None
    created_at: datetime | None = None  # datetime | None — Pydantic v2 coerces ISO-8601 (BibleEventDTO precedent)
    # In-memory only (from inference, not stored in DB):
    suggested_self_term: str | None = None
    suggested_address_term: str | None = None
```

**`SeriesBibleDTO` modification** — add `relationship_events` field (after `address_map` at line 214, mirroring the `address_map` list field):
```python
# trezarr/bible/dto.py — in SeriesBibleDTO, append after address_map field
address_map: list[AddressMapDTO] = []
relationship_events: list[RelationshipEventDTO] = []  # [Phase 6 ADDITIVE — safe default []]
locked_fields: list[str] = []
```

---

### `trezarr/bible/store.py` — ADD `record_relationship_event`; MODIFY `load_series_bible`

**Analog:** `_upsert_address_pair_in_session` (lines 581–697) and `upsert_address_pair` (lines 870–929) for the writer; `load_series_bible` selectinload block (lines 193–230) for the loader extension.

**Imports to ADD** (extend line 75 import):
```python
# trezarr/bible/store.py line 75 — extend existing import
from trezarr.bible.models import BibleEvent, Series, Character, TermDictionary, AddressMap, RelationshipEvent
# trezarr/bible/dto.py line 76 — extend existing import
from trezarr.bible.dto import (
    BibleEventDTO, SeriesDTO, SeriesBibleDTO, CharacterDTO, TermDTO, AddressMapDTO,
    RelationshipEventDTO,  # [Phase 6 NEW]
)
```

**`load_series_bible` modification** — extend selectinload options (lines 196–203) and SeriesBibleDTO construction (lines 210–230):
```python
# trezarr/bible/store.py load_series_bible — extend stmt.options():
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
# ...then in SeriesBibleDTO construction, add after address_map=[...]:
relationship_events=[
    RelationshipEventDTO.model_validate(e, from_attributes=True)
    for e in row.relationship_events
],
```

**`record_relationship_event` store writer** — mirrors the `_upsert_address_pair_in_session` / `upsert_address_pair` two-level pattern (private session helper + public transaction owner). Key differences from address pair: INSERT-only (no merge/update path), dedup key is `(series_id, character_a_id, character_b_id, episode_marker)`, no `locked_fields` column:

```python
# trezarr/bible/store.py — add as a NEW public function after upsert_address_pair (line 929)
# MUST live in store.py — NOT in a new file (Pitfall 5: SQLAlchemy import leakage via D-39)

async def record_relationship_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    character_a_id: int,
    character_b_id: int,
    episode_marker: str,
    description: str | None = None,
) -> RelationshipEventDTO:
    """INSERT a relationship_event row (no-op if dedup key already exists).

    Dedup key: (series_id, character_a_id, character_b_id, episode_marker).
    INSERT-only — no merge/update path (relationship_event has no locked_fields).
    The SELECT+INSERT runs inside a SINGLE session.begin() block (D-32, Pitfall 9).

    Args:
        session_factory:   Async session factory.
        series_id:         FK → series.id.
        character_a_id:    FK → character.id (first party in the relationship).
        character_b_id:    FK → character.id (second party in the relationship).
        episode_marker:    Episode key where the transition occurs (e.g. "S01E04").
        description:       Optional narrative description of the transition.

    Returns:
        RelationshipEventDTO for the found or newly-created row.
    """
    async with session_factory() as session:
        async with session.begin():
            # Dedup check: SELECT before INSERT (D-32, Pitfall 9 — single txn)
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
            await session.flush()  # populate row.id before txn commits (Pitfall 7)
        # expire_on_commit=False — attributes accessible post-commit (Pitfall 2)
        return RelationshipEventDTO.model_validate(row, from_attributes=True)
```

**Module docstring addition:** Extend the `store.py` public API docstring (lines 1–64) to include `record_relationship_event`.

---

### `trezarr/bible/analyze.py` — ADD `RelationshipEventInference`; MODIFY `BibleAnalysis`, `_build_analysis_prompt`, `merge_bible_analysis`

**Analog:** `AddressMapInference` (lines 53–59); `BibleAnalysis` (lines 80–99); `_build_analysis_prompt` [INSTRUCTIONS] block (lines 191–204); `merge_bible_analysis` Step 4 (lines 422–487)

**`RelationshipEventInference` model** — append after `AddressMapInference` (line 59), mirror its `BaseModel` shape:
```python
# trezarr/bible/analyze.py — append after AddressMapInference (line 59)
class RelationshipEventInference(BaseModel):
    """A relationship transition detected by Pass-1 analysis (BIBLE-07, D-51)."""

    character_a_name: str
    character_b_name: str
    episode_marker: str        # set to the current episode_key
    description: str           # narrative description of the shift
    suggested_self_term: str | None = None    # new self_term for A→B (if LLM can suggest)
    suggested_address_term: str | None = None # new address_term for A→B
```

**`BibleAnalysis` extension** — strictly additive field append (line 99), safe default `[]` + `extra="ignore"` guarantees backward compat:
```python
# trezarr/bible/analyze.py BibleAnalysis — add after address_map field (line 99)
class BibleAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)  # unchanged

    register_value: str | None = Field(default=None, alias="register")  # unchanged
    characters: list[CharacterInference] = []                           # unchanged
    terms: list[TermInference] = []                                     # unchanged
    address_map: list[AddressMapInference] = []                         # unchanged
    relationship_events: list[RelationshipEventInference] = []          # [Phase 6 ADDITIVE]
```

**`_build_analysis_prompt` signature change** — add `episode_key: str` parameter (line 107 currently: `(cue_texts, bible, arr_metadata)`):
```python
# trezarr/bible/analyze.py — modify _build_analysis_prompt signature
def _build_analysis_prompt(
    cue_texts: list[str],
    bible: "SeriesBibleDTO",
    arr_metadata: dict,
    episode_key: str = "",   # [Phase 6 NEW — for relationship_events episode_marker]
) -> str:
```

**`_build_analysis_prompt` INSTRUCTIONS extension** — append to the instructions string (after line 203, before `return "\n".join(parts)`):
```python
# trezarr/bible/analyze.py — extend [INSTRUCTIONS] block, add to the parts.append() call
"  - relationship_events: list of relationship transitions detected in this episode\n"
"    (ONLY emit when a relationship has CHANGED relative to the existing Bible context above).\n"
f"    Each entry: character_a_name, character_b_name, episode_marker (use \"{episode_key}\"),\n"
"    description (narrative description, e.g. 'They become lovers in this episode'),\n"
"    suggested_self_term (optional: new Vietnamese self-reference term for A→B),\n"
"    suggested_address_term (optional: new Vietnamese address term for A→B).\n"
"    IMPORTANT: Do NOT emit entries for stable, unchanged relationships."
```

**`analyze_file` call-site change** — thread `episode_key` into `_build_analysis_prompt` (line 274):
```python
# trezarr/bible/analyze.py line 274 — modify prompt = _build_analysis_prompt(...)
prompt = _build_analysis_prompt(cue_texts, bible, arr_metadata, episode_key=episode_key)
```

**`merge_bible_analysis` Step 5 extension** — add after Step 4 (line 487), mirroring the Step 4 address-pair loop exactly (same case-insensitive `name_to_id` map, same per-row exception handling pattern):
```python
# trezarr/bible/analyze.py — add Step 5 after Step 4 (line 487)
# Step 5: Record relationship events (D-51, D-52, BIBLE-07)
# Uses the SAME name_to_id map built in Step 2 (case-insensitive, CR-01).
# Pitfall 4: resolve via .strip().lower() — same as address_map Step 4 lines 427–428.
# Pitfall 5: record_relationship_event MUST be imported from store.py (not a new module).
from trezarr.bible.store import record_relationship_event

event_fail_count = 0
for event in analysis.relationship_events:
    char_a_id = name_to_id.get((event.character_a_name or "").strip().lower())
    char_b_id = name_to_id.get((event.character_b_name or "").strip().lower())

    if char_a_id is None:
        logger.warning(
            "Pass 1: could not resolve character_a_name %r to ID for series %d — "
            "skipping relationship_event (%r ↔ %r)",
            event.character_a_name, series_id,
            event.character_a_name, event.character_b_name,
        )
        continue
    if char_b_id is None:
        logger.warning(
            "Pass 1: could not resolve character_b_name %r to ID for series %d — "
            "skipping relationship_event (%r ↔ %r)",
            event.character_b_name, series_id,
            event.character_a_name, event.character_b_name,
        )
        continue

    try:
        await record_relationship_event(
            session_factory,
            series_id=series_id,
            character_a_id=char_a_id,
            character_b_id=char_b_id,
            episode_marker=episode_key,
            description=event.description,
        )
        logger.debug(
            "Pass 1: recorded relationship_event %r ↔ %r at %r for series %d",
            event.character_a_name, event.character_b_name, episode_key, series_id,
        )
    except Exception as exc:
        event_fail_count += 1
        logger.warning(
            "Pass 1: failed to record relationship_event %r ↔ %r for series %d: %s",
            event.character_a_name, event.character_b_name, series_id, exc,
        )
# WR-06 pattern: total failure check is omitted for relationship_events —
# events are advisory, not required for a successful translation (unlike address pairs).
```

---

### `trezarr/translate/reconcile.py` — MODIFY `reconcile_attributions`

**Analog:** Lock-check block in `reconcile_attributions` (lines 243–254); survivors block (lines 214–241); reciprocal step (lines 263–291)

**New import** (add to TYPE_CHECKING block, lines 21–25):
```python
if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
    from trezarr.bible.dto import SeriesBibleDTO, AddressMapDTO, RelationshipEventDTO  # extend
    from trezarr.translate.attribute import LineAttribution
    from sqlalchemy.ext.asyncio import async_sessionmaker
```

**New private helpers** — add before `reconcile_attributions` (after line 122):
```python
# trezarr/translate/reconcile.py — add helpers before reconcile_attributions

def _find_transition_for_pair(
    relationship_events: "list[RelationshipEventDTO]",
    spk_id: int,
    addr_id: int,
    episode_key: str,
) -> "RelationshipEventDTO | None":
    """Find a logged relationship_event for the ordered pair at this episode.

    Events are undirected (character_a_id, character_b_id) — match EITHER direction.
    Filter to current episode only (Pitfall 6: never apply future-episode transitions).
    """
    for event in relationship_events:
        if event.episode_marker != episode_key:
            continue  # Pitfall 6: only current episode's event authorizes a change
        if (event.character_a_id == spk_id and event.character_b_id == addr_id) or \
           (event.character_a_id == addr_id and event.character_b_id == spk_id):
            return event
    return None


def _derive_transition_terms(
    transition: "RelationshipEventDTO",
    resolved_map: dict,
    addr_id: int,
    id_to_gender: dict,
    settings: "TrezarrSettings",
) -> tuple[str, str]:
    """Derive (self_term, address_term) for a transition (D-54 preferred order):
      1. LLM-suggested terms from transition (suggested_self_term / suggested_address_term)
      2. This episode's already-resolved pair from resolved_map
      3. get_safe_default
    """
    if transition.suggested_self_term and transition.suggested_address_term:
        return (transition.suggested_self_term, transition.suggested_address_term)
    # Fallback: use get_safe_default
    addr_gender = id_to_gender.get(addr_id)
    return get_safe_default(addr_gender, settings)
```

**`reconcile_attributions` precedence branch insertion** — insert AFTER the lock-check block (line 254) and BEFORE the survivors gate (line 208). The canonical insertion point is immediately after the `for pair in all_pairs:` loop header, after lock handling, before `survivors = [...]`:

```python
# trezarr/translate/reconcile.py — inside reconcile_attributions for loop
# CURRENT PHASE-5 STRUCTURE (lines 204–261):
for pair in all_pairs:
    spk_id, addr_id = pair
    attributions = pair_attributions.get(pair, [])

    # (c) Apply threshold gate — EXISTING Phase-5 code
    survivors = [...]

    if survivors:
        existing = existing_map.get(pair)
        if (existing and existing.self_term and existing.address_term):
            self_term = existing.self_term  # carry-forward wins (Phase 5)
            ...

# PHASE-6 ADDITION: insert the new LOCK CHECK + TRANSITION CHECK block BEFORE survivors:
for pair in all_pairs:
    spk_id, addr_id = pair
    attributions = pair_attributions.get(pair, [])

    # LOCK CHECK (unchanged from Phase 5) — lock always wins (D-34)
    existing = existing_map.get(pair)
    if existing is not None:
        locked = set(existing.locked_fields or [])
        if "self_term" in locked or "address_term" in locked:
            if existing.self_term is not None and existing.address_term is not None:
                resolved_map[pair] = (existing.self_term, existing.address_term)
                continue  # lock wins — skip transition + confidence gate

    # [Phase 6 NEW BRANCH] TRANSITION CHECK — logged event authorizes term change (D-54)
    # Precedence: human lock > logged transition > carried-forward > low-confidence
    if getattr(settings, "enable_relationship_events", True):
        transition = _find_transition_for_pair(
            getattr(bible, "relationship_events", []),
            spk_id, addr_id, episode_key,
        )
        if transition is not None:
            new_self, new_addr = _derive_transition_terms(
                transition, resolved_map, addr_id, id_to_gender, settings
            )
            resolved_map[pair] = (new_self, new_addr)
            await upsert_address_pair(
                session_factory,
                series_id=series_id,
                speaker_character_id=spk_id,
                addressee_character_id=addr_id,
                self_term=new_self,
                address_term=new_addr,
                valid_from_episode=episode_key,  # D-53: bump version marker
                episode_key=episode_key,
                source="inference",
            )
            logger.debug(
                "reconcile: transition-authorized change for %d→%d: (%s/%s) at %s",
                spk_id, addr_id, new_self, new_addr, episode_key,
            )
            continue  # transition handled — skip confidence gate

    # Existing confidence-gate logic (unchanged from Phase 5, lines 208–261)
    survivors = [...]
```

**Reciprocal coherence for transitions** — after the existing reciprocal step (lines 263–291), the reciprocal of a transition-updated pair is already handled by the existing reciprocal coherence check at step (e) since the resolved_map entry for `(spk_id, addr_id)` is set before step (e) runs. `KINSHIP_RECIPROCAL.get((new_self, new_addr))` will find the reciprocal and write it for `(addr_id, spk_id)` if not yet resolved — no additional code needed.

---

### `trezarr/translate/engine.py` — ADD `build_review_prompt`, `_review_batch`; MODIFY `translate_file` Step 8.5

**Analog:** `build_translate_prompt` (lines 134–191); `_translate_batch_inner` (lines 273–339); TaskGroup dispatch (lines 680–704); Step 8 assembly (lines 706–725)

**Module docstring addition** — extend existing "Critical constraints" block (lines 18–22):
```python
# No asyncio.Semaphore in this module.  LLMClient._semaphore is the sole gate (Pitfall 1).
# Pass 4 self-review: _review_batch returns list[str] | None — NEVER raises (D-59).
# No quarantine path in Pass 4 — validate_subdoc remains the sole arbiter (D-55/D-59).
```

**`build_review_prompt` function** — add after `build_translate_prompt` (line 191), mirror its structure:
```python
# trezarr/translate/engine.py — add after build_translate_prompt (line 191)

def build_review_prompt(
    source_texts: list[str],
    translated_texts: list[str],
    resolved_map: "dict[tuple[int, int], tuple[str, str]]",
    bible: object,
    settings: "TrezarrSettings",
    dominant_pair: "tuple[int, int] | None" = None,
) -> str:
    """Build the Pass-4 self-review prompt (D-57, D-58).

    Instructs the reviewer to correct Bible violations only — NOT to paraphrase
    or "improve" adherent lines (D-58). Reuses the numbered-line [N] protocol.

    Args:
        source_texts:    Source cue texts for context.
        translated_texts: Pass-3 Vietnamese cue texts to review (sentinel-cleaned).
        resolved_map:    (speaker_id, addressee_id) → (self_term, address_term).
        bible:           SeriesBibleDTO for register + term dictionary context.
        settings:        TrezarrSettings (unused directly; reserved for future knobs).
        dominant_pair:   (speaker_id, addressee_id) dominant pair for this batch.
    """
    parts = [
        "[INSTRUCTIONS]",
        "You are a Vietnamese subtitle reviewer. Check each numbered line for Series Bible violations ONLY.",
        "",
        "Series Bible for this batch:",
    ]

    register = getattr(bible, "register_value", None) or "neutral"
    parts.append(f"  - Register/tone: {register}")

    if dominant_pair is not None and dominant_pair in resolved_map:
        self_t, addr_t = resolved_map[dominant_pair]
        parts.append(f"  - Pronoun pair (speaker→addressee): speaker says \"{self_t}\", addresses as \"{addr_t}\"")

    # Filter term dictionary to relevant terms (those appearing in source texts)
    source_combined = " ".join(source_texts).lower()
    relevant_terms = [
        t for t in getattr(bible, "terms", [])
        if (t.source_term or "").lower() in source_combined
    ]
    for term in relevant_terms[:10]:  # cap at 10 to control token count
        parts.append(f"  - Term: {term.source_term} → {term.vietnamese_rendering}")

    parts.extend([
        "",
        "RULES:",
        "1. Output ONLY numbered lines [1], [2], ... [N] in order.",
        "2. Keep <<T0>>, <<T1>>, ... tokens EXACTLY as-is.",
        "3. Return each line VERBATIM unless it has a SPECIFIC Bible violation:",
        "   - Wrong pronoun: uses different first-person or second-person term than the Bible pair above.",
        "   - Wrong term: a proper noun/title/place from the Bible is not rendered as specified above.",
        "   - Wrong register: significantly more formal or informal than the series register.",
        "4. Do NOT rephrase, 'improve', or paraphrase lines that already comply.",
        "",
        "[LINES TO REVIEW]",
    ])

    for i, (src, vi) in enumerate(zip(source_texts, translated_texts), 1):
        parts.append(f"[{i}] (source: {src.strip()}) {vi.strip()}")

    return "\n".join(parts)
```

**`_review_batch` function** — add after `_translate_batch` (line 368), mirror `_translate_batch_inner` but return `list[str] | None` and catch all exceptions (D-59 best-effort contract):
```python
# trezarr/translate/engine.py — add after _translate_batch (line 368)
# No asyncio.Semaphore here. LLMClient._semaphore is the sole gate (D-06, Pitfall 1).

async def _review_batch(
    review_batch: "Batch",
    source_lines_by_index: dict,
    resolved_map: "dict[tuple[int, int], tuple[str, str]]",
    bible: object,
    llm_client: LLMClient,
    settings: "TrezarrSettings",
) -> "list[str] | None":
    """Review a batch of translated cues against the Series Bible.

    Returns corrected texts, or None on ANY failure (D-59 best-effort — never raises,
    never quarantines). Mirrors _translate_batch_inner but with softer error handling.

    Steps (mirror of _translate_batch_inner lines 303–338):
      1. extract_sentinels per translated cue (D-12)
      2. build_review_prompt with source text + Bible context (D-57, D-58)
      3. llm_client.call(messages) — NO response_model (D-57)
      4. parse_numbered_response
      5. reinsert_sentinels — return None on integrity failure (D-59)
    """
    try:
        # Step 1: Extract sentinels from TRANSLATED texts (<<T...>> tokens are in translated)
        cleaned_texts: list[str] = []
        sentinel_maps: list[dict[str, str]] = []
        source_texts: list[str] = []

        for cue in review_batch.cues:
            cleaned, smap = extract_sentinels(cue.text)
            cleaned_texts.append(cleaned)
            sentinel_maps.append(smap)
            src = source_lines_by_index.get(cue.index)
            source_texts.append(src.text if src else "")

        # Step 2: Build review prompt with Bible context
        prompt = build_review_prompt(
            source_texts=source_texts,
            translated_texts=cleaned_texts,
            resolved_map=resolved_map,
            bible=bible,
            settings=settings,
        )

        # Step 3: LLM call — no response_model (D-57, mirrors line 320)
        raw_response = await llm_client.call([{"role": "user", "content": prompt}])

        # Step 4: Parse numbered-line response (reuse parse_numbered_response, line 200)
        corrected_texts = parse_numbered_response(str(raw_response), len(review_batch.cues))

        # Step 5: Reinsert sentinels — return None on integrity failure (D-59)
        restored: list[str] = []
        for text, smap in zip(corrected_texts, sentinel_maps):
            if smap:
                restored_text, integrity_ok = reinsert_sentinels(text, smap)
                if not integrity_ok:
                    logger.warning(
                        "Pass 4: sentinel integrity failure — using pre-review output for this batch (D-59)"
                    )
                    return None  # fallback, not exception
                restored.append(restored_text)
            else:
                restored.append(text)

        return restored

    except Exception:
        logger.warning(
            "Pass 4 review batch failed — using pre-review output (D-59)",
            exc_info=True,
        )
        return None  # NEVER raises, NEVER quarantines (D-59)
```

**`translate_file` Step 8.5 insertion** — add between Step 8 (line 725, `translated_doc = SubDoc(...)`) and Step 9 (line 727, `validate_subdoc`):
```python
# trezarr/translate/engine.py — insert between Step 8 and Step 9 (after line 725)

# Step 8.5 (Phase 6, D-55): Pass 4 Self-Review — best-effort Bible adherence correction.
# Runs ONLY in the Bible-aware branch (eligible_item + session_factory + enable_self_review).
# On ANY failure (LLM error, parse failure, sentinel failure): keep pre-review translated_doc.
# NEVER quarantines — validate_subdoc (Step 9) remains the sole arbiter (D-59).
if (
    settings.enable_self_review
    and eligible_item is not None
    and session_factory is not None
    and bible is not None
):
    review_batches = batch_subdoc(
        translated_doc,  # review the TRANSLATED document (Assumption A4)
        settings,
        context_lines_k=settings.self_review_context_lines_k,
        max_cues_per_batch=settings.self_review_max_cues_per_batch,
    )
    source_lines_by_index = {line.index: line for line in source_doc.lines}

    # TaskGroup dispatch — mirrors Pass-2 attribution gather (lines 621–628).
    # CRITICAL DIFFERENCE from Pass-3 TaskGroup: NO except* block here.
    # _review_batch catches all exceptions internally and returns None (D-59, Pitfall 2).
    try:
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
    except Exception:
        # Bare except: if TaskGroup itself fails unexpectedly, keep pre-review doc (D-59)
        logger.warning("Pass 4 TaskGroup failed — keeping pre-review translated_doc (D-59)", exc_info=True)
        review_results = [None] * len(review_batches)

    # Splice corrections into translated_doc (Pitfall 8 — new SubLine objects, never mutate)
    corrected_lines = list(translated_doc.lines)
    offset = 0
    for rb, corrected_texts in zip(review_batches, review_results):
        if corrected_texts is None:
            offset += len(rb.cues)
            continue
        for i, (cue, new_text) in enumerate(zip(rb.cues, corrected_texts)):
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

# Step 9: Document-level validation gate (unchanged — sole quarantine arbiter)
```

---

### `trezarr/config.py` — MODIFY `TrezarrSettings`

**Analog:** Phase-5 settings group (lines 128–143)

**Phase-6 settings group** — append after Phase-5 group (line 143), mirroring the comment header + grouped fields pattern exactly:

```python
# trezarr/config.py — append after Phase-5 group (line 143)

# ── Phase 6: Relationship Evolution + Self-Review (D-51…D-60) ──────────────────
# Capability A — Relationship Evolution (BIBLE-07)
enable_relationship_events: bool = True         # D-60: toggle for staged rollout/tests
relationship_event_min_confidence: float = 0.0  # min confidence to emit (0.0 = all)

# Capability B — Self-Review Pass (ENG-05)
enable_self_review: bool = True                 # D-60: toggle for staged rollout/tests
self_review_context_lines_k: int = 3            # context K for review batches (translate default)
self_review_max_cues_per_batch: int = 20        # smaller batches → fewer tokens per review call
```

---

### `tests/bible/test_relationship_events.py` (NEW)

**Analog:** `tests/bible/test_address_map.py` (module structure, helper factories, DB fixture chain); `tests/db/conftest.py` (fixture pattern); `tests/translate/test_analyze.py` (AsyncMock LLM pattern)

**Imports pattern** — mirror `test_analyze.py` (lines 1–26):
```python
"""Tests for Phase-6 BIBLE-07 relationship event store, DTO, load, and name matching.

Tests cover:
  BIBLE-07-A — record_relationship_event writes a row; load_series_bible includes it
  BIBLE-07-B — load_series_bible returns relationship_events in SeriesBibleDTO
  BIBLE-07-F — case-insensitive name matching in merge_bible_analysis for events (CR-01)

asyncio_mode="auto" is configured project-wide in pyproject.toml.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from trezarr.bible.store import get_or_create_series, load_series_bible, upsert_character, record_relationship_event
from trezarr.bible.dto import RelationshipEventDTO
from trezarr.config import TrezarrSettings
```

**DB fixture re-export** — create `tests/bible/conftest.py` if it does not already exist (mirror `tests/translate/conftest.py` exactly):
```python
# tests/bible/conftest.py — re-export shared db fixtures
from tests.db.conftest import db_engine, session_factory  # noqa: F401
```

**Helper factories** — mirror `test_reconcile.py` module-level helper pattern (lines 23–137):
```python
async def _create_series(session_factory, arr_series_id: int = 200) -> int:
    from trezarr.bible.store import get_or_create_series
    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=arr_series_id,
        arr_metadata_snapshot={"title": "Relationship Event Test Series"},
    )
    return dto.id

async def _create_characters(session_factory, series_id: int, name_a="Alice", name_b="Bob") -> tuple[int, int]:
    from trezarr.bible.store import upsert_character
    a, _ = await upsert_character(session_factory, series_id=series_id, original_latin_name=name_a, source="inference")
    b, _ = await upsert_character(session_factory, series_id=series_id, original_latin_name=name_b, source="inference")
    return a.id, b.id
```

**Wave-0 stub pattern** — mirror Phase-5 precedent (`05-01-PLAN.md`): stubs use `pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))` so the suite stays green before implementation:
```python
@pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))
async def test_relationship_event_written_to_db(session_factory):
    ...  # BIBLE-07-A stub
```

---

### `tests/translate/test_self_review.py` (NEW)

**Analog:** `tests/translate/test_analyze.py` (AsyncMock LLM pattern, `_make_subdoc`, `_make_settings`); `tests/translate/test_engine.py` (full pipeline shape)

**Imports pattern** — mirror `test_analyze.py`:
```python
"""Tests for Phase-6 ENG-05 Pass-4 self-review pass.

Tests cover:
  ENG-05-A — Pass 4 corrects a pronoun violation; validate_subdoc sees corrected output
  ENG-05-B — Pass 4 LLM failure → pre-review output used; no quarantine
  ENG-05-C — enable_self_review=False → Pass 4 skipped; translated_doc unchanged
  ENG-05-D — Sentinel integrity failure in review → pre-review batch kept per-batch

asyncio_mode="auto" is configured project-wide in pyproject.toml.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from trezarr.translate.engine import _review_batch, build_review_prompt, parse_numbered_response
from trezarr.translate.batching import Batch
from trezarr.subtitles.model import SubDoc, SubLine
from trezarr.config import TrezarrSettings
```

**`_make_settings` helper** — mirror `test_analyze.py` (lines 46–53):
```python
def _make_settings(**kwargs) -> TrezarrSettings:
    return TrezarrSettings(
        llm_api_key="test-key",
        enable_self_review=True,
        self_review_context_lines_k=0,
        self_review_max_cues_per_batch=10,
        **kwargs,
    )
```

**LLM mock pattern** — mirror `test_analyze.py` AsyncMock usage:
```python
# For _review_batch tests: mock returns a numbered-line string
mock_llm = AsyncMock()
mock_llm.call = AsyncMock(return_value="[1] Anh yêu em.\n[2] Em hiểu anh không?")
```

**Wave-0 xfail stub** — same pattern as test_relationship_events.py stubs.

---

### `tests/translate/test_reconcile.py` (EXTEND)

**Analog:** Same file — existing `_make_bible`, `_make_character`, `_make_address_map_entry` factories (lines 90–137)

**Extension: add `_make_relationship_event` helper** after `_make_address_map_entry` (line 137):
```python
def _make_relationship_event(
    id: int,
    series_id: int,
    char_a_id: int,
    char_b_id: int,
    episode_marker: str,
    suggested_self_term: str | None = None,
    suggested_address_term: str | None = None,
):
    from types import SimpleNamespace
    return SimpleNamespace(
        id=id,
        series_id=series_id,
        character_a_id=char_a_id,
        character_b_id=char_b_id,
        episode_marker=episode_marker,
        description=None,
        created_at=None,
        suggested_self_term=suggested_self_term,
        suggested_address_term=suggested_address_term,
    )
```

**Extension: extend `_make_bible` to accept `relationship_events`** (lines 90–102):
```python
def _make_bible(series_id: int, characters: list, address_map: list, relationship_events: list | None = None):
    from types import SimpleNamespace
    return SimpleNamespace(
        id=series_id,
        ...,
        address_map=address_map,
        relationship_events=relationship_events or [],  # [Phase 6 ADDITIVE]
    )
```

**Wave-0 xfail stubs** for BIBLE-07-C, D, E:
```python
@pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))
async def test_transition_authorizes_terms_change(session_factory): ...  # BIBLE-07-C

@pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))
async def test_lock_beats_transition(session_factory): ...              # BIBLE-07-D

@pytest.mark.xfail(strict=False, raises=(ImportError, AssertionError, TypeError))
async def test_no_transition_no_survivors_safe_default(session_factory): ...  # BIBLE-07-E
```

---

## Shared Patterns

### Transaction ownership (`async with session_factory() as session: async with session.begin():`)
**Source:** `trezarr/bible/store.py` lines 136–170 (`get_or_create_series`), lines 802–818 (`upsert_character`), lines 912–929 (`upsert_address_pair`)
**Apply to:** `record_relationship_event`
```python
async with session_factory() as session:
    async with session.begin():
        # SELECT + INSERT/UPDATE in ONE transaction (D-32, Pitfall 9)
        ...
    # expire_on_commit=False — attributes accessible post-commit (Pitfall 2)
    return DTO.model_validate(row, from_attributes=True)
```

### Pydantic DTO boundary (`model_validate(row, from_attributes=True)`)
**Source:** `trezarr/bible/dto.py` `AddressMapDTO` (line 137: `model_config = ConfigDict(from_attributes=True)`)
**Apply to:** `RelationshipEventDTO`
```python
model_config = ConfigDict(from_attributes=True)  # no aliases needed — column names match 1:1
```

### `extra="ignore"` + safe default for additive BibleAnalysis extensions
**Source:** `trezarr/bible/analyze.py` lines 94–99 (`BibleAnalysis`)
**Apply to:** `RelationshipEventInference` field in `BibleAnalysis`
```python
model_config = ConfigDict(extra="ignore", populate_by_name=True)  # unchanged
relationship_events: list[RelationshipEventInference] = []  # safe default — never raises
```

### Case-insensitive name-to-ID resolution (CR-01)
**Source:** `trezarr/bible/analyze.py` line 371 (`name_to_id[char.original_latin_name.strip().lower()] = char_dto.id`) and lines 427–428 (`name_to_id.get((pair.speaker_name or "").strip().lower())`)
**Apply to:** `merge_bible_analysis` Step 5 (relationship event name resolution), `reconcile_attributions` (name_to_id build already uses `.lower()` at line 171)
```python
# Always resolve via .strip().lower() — never case-sensitive dict lookup
char_a_id = name_to_id.get((event.character_a_name or "").strip().lower())
```

### Per-row exception handling with WR-06 total-failure guard
**Source:** `trezarr/bible/analyze.py` lines 358–391 (character upsert loop), lines 393–420 (term upsert loop)
**Apply to:** `merge_bible_analysis` Step 5 (relationship event loop) — note: WR-06 total-failure raise is OMITTED for events (advisory only, not required for translation)
```python
try:
    await record_relationship_event(...)
except Exception as exc:
    logger.warning("Pass 1: failed to record relationship_event ...: %s", exc)
    # no total-failure raise for events — advisory only
```

### D-39 DTO boundary enforcement
**Source:** `trezarr/bible/store.py` module docstring lines 38–39; `tests/bible/test_dto_boundary.py` (import-graph inspection)
**Apply to:** `record_relationship_event` MUST live in `store.py` (Pitfall 5 — not in `relationship.py`)
```python
# Any import of RelationshipEvent from models.py must stay inside store.py only.
# The test_dto_boundary.py test will catch SQLAlchemy leakage automatically.
```

### Best-effort pass — return `None` instead of raising (D-59)
**Source:** Pattern is new to Phase 6 — differs from Pass-3 `_translate_batch_inner` which raises `BatchValidationError`
**Apply to:** `_review_batch` in `engine.py` — every code path ends in `return None` or `return restored`; no `raise` statements inside the function
```python
except Exception:
    logger.warning("Pass 4 review batch failed — using pre-review output (D-59)", exc_info=True)
    return None  # NEVER raises, NEVER quarantines
```

### No asyncio.Semaphore in any module except `trezarr/llm/client.py`
**Source:** Module-level comment in `analyze.py` (line 14), `reconcile.py` (line 12), `engine.py` (lines 19–20)
**Apply to:** `engine.py` new Pass-4 code and any new `review.py` module
```python
# No asyncio.Semaphore in this module.  LLMClient._semaphore is the sole gate (D-06, Pitfall 1).
```

### Phase-N settings group comment header
**Source:** `trezarr/config.py` lines 128–143 (Phase-5 group)
**Apply to:** Phase-6 settings group
```python
# ── Phase 6: Relationship Evolution + Self-Review (D-51…D-60) ──────────────────
```

### DB fixture re-export via conftest.py
**Source:** `tests/translate/conftest.py` (lines 1–13)
**Apply to:** `tests/bible/conftest.py` (if it doesn't exist or lacks re-exports)
```python
from tests.db.conftest import db_engine, session_factory  # noqa: F401
```

---

## No Analog Found

All files have close analogs in the codebase. No files require falling back to RESEARCH.md patterns for primary implementation guidance.

| File | Role | Data Flow | Note |
|---|---|---|---|
| `_review_batch` return semantics (`list[str] | None`) | service | request-response | The "return None instead of raise" best-effort contract is new to Phase 6 — no prior analog with this exact shape. The closest is `_translate_batch_inner` which DOES raise. The difference is intentional and structural per D-59. |

---

## Critical Implementation Notes

1. **`record_relationship_event` must live in `store.py`** — not in a new `relationship.py` or `bible/events.py`. `test_dto_boundary.py` will catch any SQLAlchemy leakage (Pitfall 5).

2. **`Series.relationship_events` ORM relationship does not exist yet** — both the `Series` attribute and the `RelationshipEvent.series` back-reference must be added to `models.py`. Without these, `selectinload(Series.relationship_events)` will fail at runtime (Assumption A3, VERIFIED).

3. **`_build_analysis_prompt` must receive `episode_key`** — the function signature must be extended; `analyze_file` already has `episode_key` in scope at line 274 where it calls `_build_analysis_prompt` (Assumption A5 / Open Question 3).

4. **Pass 4 TaskGroup has NO `except*` block** — unlike the Pass-3 TaskGroup (lines 687–701) which has `except* BatchValidationError`. `_review_batch` must swallow all exceptions internally. Any `except*` or `_write_quarantine` reachable from Pass-4 code paths is Pitfall 2 (D-59 violation).

5. **Transition check is AFTER lock check, BEFORE survivors gate** — the precedence order `lock > transition > carried-forward > safe-default` must be implemented as sequential `continue` branches in the `for pair in all_pairs:` loop.

6. **`_find_transition_for_pair` filters to `episode_marker == episode_key`** — not all events for the series. This prevents Pitfall 6 (future-episode transitions applied retroactively).

7. **Wave-0 stub xfail uses `raises=(ImportError, AssertionError, TypeError)`** — NOT just `ImportError`, because the existing modules import cleanly; the assertion fails on missing functionality (verified from STATE.md / Phase-5 precedent).

---

## Metadata

**Analog search scope:** `trezarr/bible/`, `trezarr/translate/`, `trezarr/config.py`, `tests/bible/`, `tests/translate/`, `tests/db/`
**Files scanned:** 16 source files read in full
**Pattern extraction date:** 2026-06-02
