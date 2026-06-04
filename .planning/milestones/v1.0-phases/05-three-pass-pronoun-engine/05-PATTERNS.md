# Phase 5: Three-Pass Pronoun Engine - Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 11 new/modified files
**Analogs found:** 11 / 11

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trezarr/bible/analyze.py` | service | request-response (LLM call + store write) | `trezarr/translate/engine.py` `_translate_batch_inner` + `store.py` `upsert_character` | role-match |
| `trezarr/translate/attribute.py` | service | request-response (batched LLM + Pydantic parse) | `trezarr/translate/engine.py` `_translate_batch_inner` | exact |
| `trezarr/translate/reconcile.py` | utility | transform (pure algorithm, no LLM) | `trezarr/translate/batching.py` `batch_subdoc` | role-match |
| `trezarr/bible/dto.py` (ADD `AddressMapDTO`) | model | CRUD | `trezarr/bible/dto.py` `CharacterDTO` / `TermDTO` | exact |
| `trezarr/bible/store.py` (ADD `upsert_address_pair`, `_upsert_address_pair_in_session`, `load_address_map`) | service | CRUD | `trezarr/bible/store.py` `upsert_character` / `_upsert_character_in_session` | exact |
| `trezarr/bible/models.py` (ADD `Series.address_maps` relationship) | model | CRUD | `trezarr/bible/models.py` `Series.characters` / `Series.terms` relationships | exact |
| `trezarr/translate/engine.py` (EXTEND `translate_file`, `build_translate_prompt`) | service | request-response | `trezarr/translate/engine.py` (self) | exact |
| `trezarr/cli.py` (EXTEND translate loop ~L294) | controller | request-response | `trezarr/cli.py` (self) | exact |
| `trezarr/config.py` (ADD Phase-5 fields) | config | — | `trezarr/config.py` existing Phase-3/4 field groups | exact |
| `tests/bible/test_address_map.py` | test | CRUD | `tests/bible/test_merge_inferred.py` | role-match |
| `tests/translate/test_reconcile.py` + `test_attribute.py` + `test_analyze.py` + `test_pronoun_engine.py` | test | request-response | `tests/translate/test_engine.py` | role-match |

---

## Pattern Assignments

### `trezarr/bible/analyze.py` (service, request-response + store write)

**Analog:** `trezarr/translate/engine.py` (LLM call pattern) and `trezarr/bible/store.py` (merge pattern)

**Imports pattern** — copy exactly (lines 24-51 of engine.py + lines 65-79 of store.py):
```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from trezarr.bible.dto import SeriesBibleDTO, AddressMapDTO
from trezarr.bible.store import (
    upsert_character,
    upsert_term,
    upsert_address_pair,
    merge_inferred,
    VALID_SOURCES,
)

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
    from trezarr.llm.client import LLMClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

logger = logging.getLogger(__name__)
```

**Critical constraint — NO SQLAlchemy imports:** `analyze.py` must NEVER import from `sqlalchemy` or `trezarr.bible.models`. Only `trezarr.bible.dto` and `trezarr.bible.store` public functions. This is enforced by `tests/bible/test_dto_boundary.py` (D-39, Pitfall D from RESEARCH.md).

**LLM call pattern for structured output** (from `engine.py` lines 263-267, adapted):
```python
# Call LLMClient — sole concurrency gate is inside LLMClient._semaphore (D-06, Pitfall A).
# NEVER add asyncio.Semaphore here. response_model triggers Tier-1/2 path (D-47).
result = await llm_client.call(
    messages=[{"role": "user", "content": prompt}],
    response_model=BibleAnalysis,
)
# On Tier 1 success: result is a BibleAnalysis instance.
# On Tier 2: result is a JSON string — use BibleAnalysis.model_validate_json(result).
# On Tier 3 (plain text): degrade gracefully per D-47 — skip Bible merge, do not quarantine.
```

**Quarantine pattern for Pass-1 failure** (from `engine.py` lines 476-469):
```python
# Only quarantine on logic failures (BibleAnalysisError) AFTER retries exhausted.
# Never quarantine on openai.APIError — Pitfall B from RESEARCH.md.
try:
    analysis = await analyze_file(...)
    await merge_bible_analysis(session_factory, series_dto, analysis, episode_key)
except BibleAnalysisError as exc:
    reason = f"pass1 analysis failure: {exc}"
    quarantine_path = _write_quarantine(path, reason, [], settings)
    await ledger.record(LedgerEntry(
        source_path=str(path),
        output_path=None,
        status="quarantined",
        content_hash=content_hash,
        quarantine_path=str(quarantine_path),
    ))
    return TranslationResult(status="quarantined", quarantine_path=quarantine_path, reason=reason)
```

---

### `trezarr/translate/attribute.py` (service, batched request-response + Pydantic parse)

**Analog:** `trezarr/translate/engine.py` `_translate_batch_inner` (lines 226-285)

**Imports pattern:**
```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel
from enum import Enum

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
    from trezarr.llm.client import LLMClient
    from trezarr.bible.dto import SeriesBibleDTO
    from trezarr.translate.batching import Batch

logger = logging.getLogger(__name__)
```

**Pydantic shapes to define in this module** (per RESEARCH.md Key Pattern 3):
```python
class AttributionConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class LineAttribution(BaseModel):
    line_index: int                            # 1-based within batch
    speaker: str | None = None               # original_latin_name or None
    addressee: str | None = None             # original_latin_name or None
    confidence: AttributionConfidence = AttributionConfidence.LOW

class BatchAttribution(BaseModel):
    attributions: list[LineAttribution]
```

**Batched concurrent dispatch pattern** (mirrors `engine.py` lines 477-479):
```python
# Pass 2 runs over the IDENTICAL batches produced by batch_subdoc (Pitfall E).
# asyncio.gather mirrors the translate pass — same pattern, wider context K.
# No new asyncio.Semaphore — LLMClient._semaphore is the sole gate (Pitfall A).
attributions_per_batch = await asyncio.gather(
    *[attribute_batch(b, bible, llm_client, settings) for b in batches]
)
```

**Per-batch attribution call** (structurally mirrors `_translate_batch_inner`):
```python
async def attribute_batch(
    batch: Batch,
    bible: SeriesBibleDTO,
    llm_client: LLMClient,
    settings: TrezarrSettings,
) -> list[LineAttribution]:
    """Infer speaker/addressee for each cue in the batch. Uses response_model=BatchAttribution."""
    prompt = build_attribution_prompt(batch, bible, settings)
    raw = await llm_client.call(
        messages=[{"role": "user", "content": prompt}],
        response_model=BatchAttribution,
    )
    # Tier 1: raw is BatchAttribution instance
    # Tier 2: raw is JSON string → BatchAttribution.model_validate_json(raw)
    # Tier 3 / any parse failure → return all LOW-confidence unknowns (D-47 graceful degrade)
    ...
```

**Context K parameter** — Pass 2 uses `settings.attribute_context_lines_k` (new field D-50), NOT `settings.translate_context_lines_k`. The `_make_batch` function in `batching.py` line 78 reads `k = settings.translate_context_lines_k`; for Pass 2, build batches with the wider K by passing a settings-like wrapper or by calling `_make_batch` with the wider K directly. The simplest approach: call `batch_subdoc(source_doc, settings)` (same batches as Pass 3 — Pitfall E compliance), but pass `attribute_context_lines_k` as an extra argument to `build_attribution_prompt` to widen the context window in the prompt text only.

**Tier-3 degradation** (D-47): if `llm_client._mode == "text"`, return `[LineAttribution(line_index=i, confidence=AttributionConfidence.LOW) for i, _ in enumerate(batch.cues, 1)]` — all unknown, all LOW.

---

### `trezarr/translate/reconcile.py` (utility, pure transform)

**Analog:** `trezarr/translate/batching.py` (pure synchronous module, no LLM, no imports from `llm/` or `bible/models.py`)

**Imports pattern** (from `batching.py` lines 1-24):
```python
from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
    from trezarr.bible.dto import SeriesBibleDTO, CharacterDTO
    from trezarr.translate.attribute import LineAttribution, AttributionConfidence
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)
```

**Module-level constants to define here** (per RESEARCH.md Key Pattern 5):
```python
# Standard Vietnamese kinship pronoun reciprocal pairs.
# (self_term, address_term) → expected reciprocal (self_term, address_term) for B→A
KINSHIP_RECIPROCAL: dict[tuple[str, str], tuple[str, str]] = {
    ("anh", "em"):   ("em", "anh"),
    ("em", "anh"):   ("anh", "em"),
    ("chị", "em"):   ("em", "chị"),
    ("em", "chị"):   ("chị", "em"),
    # ... (see RESEARCH.md Key Pattern 5 for full table)
}
SAFE_DEFAULT_SELF = "tôi"
SAFE_DEFAULT_ADDRESS_MALE = "anh"
SAFE_DEFAULT_ADDRESS_FEMALE = "chị"
SAFE_DEFAULT_ADDRESS_NEUTRAL = "bạn"
```

**Pure reconciliation function signature** (per RESEARCH.md Key Pattern 4):
```python
async def reconcile_attributions(
    flat_attributions: list[LineAttribution],
    bible: SeriesBibleDTO,
    session_factory: async_sessionmaker,
    series_id: int,
    episode_key: str,
    settings: TrezarrSettings,
) -> dict[tuple[int, int], tuple[str, str]]:
    """
    Returns: {(speaker_char_id, addressee_char_id): (self_term, address_term)}
    This in-memory map is the Pass-3 lookup table — no DB read in the hot path.
    """
```

**`get_safe_default` function** (per RESEARCH.md Key Pattern 5):
```python
def get_safe_default(
    addressee_gender: str | None,
    settings: TrezarrSettings,
) -> tuple[str, str]:
    """Return (self_term, address_term) for low-confidence attributions (D-45)."""
    if settings.pronoun_safe_default:
        return settings.pronoun_safe_default  # user override
    address = {
        "male": SAFE_DEFAULT_ADDRESS_MALE,
        "female": SAFE_DEFAULT_ADDRESS_FEMALE,
    }.get(addressee_gender or "", SAFE_DEFAULT_ADDRESS_NEUTRAL)
    return (SAFE_DEFAULT_SELF, address)
```

---

### `trezarr/bible/dto.py` — ADD `AddressMapDTO`

**Analog:** `CharacterDTO` (lines 74-96) and `TermDTO` (lines 98-118)

**Pattern to mirror exactly** (from `dto.py` lines 87-96 and 107-117):
```python
class AddressMapDTO(BaseModel):
    """Directed speaker→addressee pronoun-pair entry DTO (BIBLE-03).

    model_config mirrors CharacterDTO: from_attributes=True only (no populate_by_name
    needed — no alias required, column names match Python field names 1:1).
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    speaker_character_id: int
    addressee_character_id: int
    self_term: str | None = None
    address_term: str | None = None
    valid_from_episode: str | None = None
    locked_fields: list[str] = []   # D-34: mutable default safe in Pydantic v2 (see dto.py:14)
```

**Also extend `SeriesBibleDTO`** (lines 151-186) to add:
```python
address_map: list[AddressMapDTO] = []   # Eagerly loaded by load_series_bible Phase 5+
```

**Import to add** — `AddressMapDTO` needs no new imports beyond the existing `from pydantic import BaseModel, ConfigDict, Field` already in `dto.py`.

---

### `trezarr/bible/store.py` — ADD `upsert_address_pair`, `_upsert_address_pair_in_session`, `load_address_map`

**Analog:** `upsert_character` (lines 631-693) and `_upsert_character_in_session` (lines 382-476)

**`MERGEABLE_FIELDS` addition** (insert at line 242, mirroring existing dict):
```python
MERGEABLE_FIELDS: dict[str, frozenset[str]] = {
    "character": frozenset({"gender", "rough_age", "role"}),
    "term_dictionary": frozenset({"vietnamese_rendering", "category"}),
    "series": frozenset({"register"}),
    "address_map": frozenset({"self_term", "address_term", "valid_from_episode"}),  # ADD
}
```

**New model import** (add to line 75 imports block):
```python
from trezarr.bible.models import BibleEvent, Series, Character, TermDictionary, AddressMap  # ADD AddressMap
from trezarr.bible.dto import BibleEventDTO, SeriesDTO, SeriesBibleDTO, CharacterDTO, TermDTO, AddressMapDTO  # ADD AddressMapDTO
```

**`_upsert_address_pair_in_session` signature** — mirror `_upsert_character_in_session` (lines 382-476) exactly:
```python
async def _upsert_address_pair_in_session(
    session: AsyncSession,
    *,
    series_id: int,
    speaker_character_id: int,
    addressee_character_id: int,
    self_term: str | None,
    address_term: str | None,
    valid_from_episode: str | None,
    episode_key: str | None,
    source: str,
) -> tuple[AddressMap, list[BibleEvent]]:
    """INSERT or merge-update an AddressMap row INSIDE an already-open transaction.

    This helper MUST be called from inside an `async with session.begin():` block.
    It does NOT open a transaction (HIGH finding: no nested txn).
    Identity key: (series_id, speaker_character_id, addressee_character_id) — one
    row per directed ordered pair.
    CRITICAL: do NOT delegate to _merge_inferred_in_session for AddressMap — its
    isinstance chain does not handle AddressMapDTO (Pitfall G / RESEARCH.md).
    Write a self-contained helper that mirrors _upsert_character_in_session.
    """
    # SELECT existing row by identity key
    stmt = select(AddressMap).where(
        AddressMap.series_id == series_id,
        AddressMap.speaker_character_id == speaker_character_id,
        AddressMap.addressee_character_id == addressee_character_id,
    )
    existing_row = (await session.execute(stmt)).scalar_one_or_none()
    ...
```

**`upsert_address_pair` public wrapper** — mirror `upsert_character` (lines 631-693):
```python
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
    async with session_factory() as session:
        async with session.begin():
            row, events = await _upsert_address_pair_in_session(
                session,
                series_id=series_id,
                speaker_character_id=speaker_character_id,
                addressee_character_id=addressee_character_id,
                self_term=self_term,
                address_term=address_term,
                valid_from_episode=valid_from_episode,
                episode_key=episode_key,
                source=source,
            )
        return (
            AddressMapDTO.model_validate(row, from_attributes=True),
            [BibleEventDTO.model_validate(e, from_attributes=True) for e in events],
        )
```

**`load_series_bible` extension** (lines 194-225) — add `selectinload(Series.address_maps)` and populate `address_map` in the returned `SeriesBibleDTO`. The `Series.address_maps` ORM relationship does not yet exist (Pitfall H / Assumption A8 from RESEARCH.md) — it must be added to `models.py` first.

**Extend `load_series_bible`** (lines 198-203):
```python
stmt = (
    select(Series)
    .where(Series.id == series_id)
    .options(
        selectinload(Series.characters),
        selectinload(Series.terms),
        selectinload(Series.address_maps),   # ADD — requires models.py relationship
    )
)
```

And add `address_map=[AddressMapDTO.model_validate(a, from_attributes=True) for a in row.address_maps]` to the `SeriesBibleDTO(...)` constructor call at lines 209-225.

---

### `trezarr/bible/models.py` — ADD `Series.address_maps` relationship

**Analog:** `Series.characters` and `Series.terms` relationships (lines 87-92)

**Pattern to mirror exactly** (lines 87-92 of models.py):
```python
# Current (lines 87-92):
characters: Mapped[list["Character"]] = relationship(
    back_populates="series", cascade="all, delete-orphan"
)
terms: Mapped[list["TermDictionary"]] = relationship(
    back_populates="series", cascade="all, delete-orphan"
)

# ADD (same pattern):
address_maps: Mapped[list["AddressMap"]] = relationship(
    back_populates="series", cascade="all, delete-orphan"
)
```

**Also add `series` back-reference to `AddressMap` model** (lines 153-179). Currently `AddressMap` has no `series` back-reference. Add:
```python
series: Mapped["Series"] = relationship(back_populates="address_maps")
```

**No Alembic migration needed** — the `address_map` table and FK already exist (D-31 baseline migration). The `relationship()` is ORM-only metadata.

---

### `trezarr/translate/engine.py` — EXTEND `translate_file` + `build_translate_prompt`

**Analog:** Self (current file). Read entire current file before modifying.

**`build_translate_prompt` signature extension** (current lines 93-98, RESEARCH.md Key Pattern 6):
```python
# Current signature (lines 93-98):
def build_translate_prompt(
    batch_texts: list[str],
    context_before: list[str],
    context_after: list[str],
    source_lang: str = "English",
) -> str:

# Extended (D-46) — default None maintains backward compatibility (A7 from RESEARCH.md):
def build_translate_prompt(
    batch_texts: list[str],
    context_before: list[str],
    context_after: list[str],
    source_lang: str = "English",
    pronoun_hints: dict[int, tuple[str, str]] | None = None,
    # pronoun_hints: {1-based line index → (self_term, address_term)}
) -> str:
```

**Pronoun hint injection** — extend the `[LINES TO TRANSLATE]` section (lines 130-132 of engine.py):
```python
# Current (lines 130-132):
parts.append("[LINES TO TRANSLATE]")
for i, text in enumerate(batch_texts, 1):
    parts.append(f"[{i}] {text.strip()}")

# Extended:
parts.append("[LINES TO TRANSLATE]")
for i, text in enumerate(batch_texts, 1):
    if pronoun_hints and i in pronoun_hints:
        self_t, addr_t = pronoun_hints[i]
        parts.append(f"[{i}] (speaker says: {self_t}; addresses as: {addr_t}) {text.strip()}")
    else:
        parts.append(f"[{i}] {text.strip()}")
```

**`translate_file` signature extension** (current lines 372-377, RESEARCH.md Key Pattern 7):
```python
# Current (lines 372-377):
async def translate_file(
    path: str | Path,
    settings: "TrezarrSettings",
    llm_client: LLMClient,
    ledger: LedgerProtocol,
) -> TranslationResult:

# Extended (D-48) — default None for backward compat:
async def translate_file(
    path: str | Path,
    settings: "TrezarrSettings",
    llm_client: LLMClient,
    ledger: LedgerProtocol,
    eligible_item: "EligibleItem | None" = None,
    session_factory: "async_sessionmaker[AsyncSession] | None" = None,
) -> TranslationResult:
```

**New imports to add to engine.py** (after line 50 `if TYPE_CHECKING:` block):
```python
if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
    from trezarr.discover.scan import EligibleItem                          # ADD
    from trezarr.bible.store import get_or_create_series, load_series_bible # ADD
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession     # ADD
```

**Flow insertion point** — between current Steps 5-6 (lines 449-454) and Step 7 (line 471):
```python
# [Step 4.5] Bible setup — only when eligible_item and session_factory are provided.
# When either is None, the Phase-5 Bible logic is bypassed (mechanical translation only).
resolved_map: dict[tuple[int, int], tuple[str, str]] = {}
if eligible_item is not None and session_factory is not None and settings.enable_pass1_analysis:
    # ... Pass 1 BARRIER, Pass 2, reconcile → populate resolved_map
    ...
```

---

### `trezarr/cli.py` — EXTEND translate loop (~L294)

**Analog:** Self. Current call at line 294.

**Current call** (line 294):
```python
result = await translate_file(source_sub_path, settings, llm_client, ledger)
```

**Extended call** (D-48 — both `eligible_item` and `session_factory` are already in scope):
```python
# session_factory is in scope at L176 (bound inside _run_once/build_session_factory).
# eligible_item is the loop variable at L291.
result = await translate_file(
    source_sub_path,
    settings,
    llm_client,
    ledger,
    eligible_item=eligible_item,
    session_factory=session_factory,
)
```

**`session_factory` scope in `_run_once`** — defined at line 176 inside `_run_once`; passed via `_run_pipeline_steps` at line 201. The `_run_pipeline_steps` function signature (lines 209-213) must also receive and forward `session_factory`:
```python
# Current (line 201):
return await _run_pipeline_steps(settings, ledger, media_roots)

# Extended:
return await _run_pipeline_steps(settings, ledger, media_roots, session_factory)
```

---

### `trezarr/config.py` — ADD Phase-5 `TrezarrSettings` fields

**Analog:** Phase-3 and Phase-4 field groups (lines 66-127 of config.py)

**Pattern to mirror** — comment header block + fields (e.g. lines 117-127):
```python
# ── Phase 4: Series Bible persistence (D-31, D-38) ─────────────────────────
bible_db_url: str = "sqlite+aiosqlite:////config/trezarr.db"
bible_db_run_migrations_on_startup: bool = True
bible_db_enable_wal: bool = True
bible_db_enforce_fk: bool = True
```

**New Phase-5 block to add** after the Phase-4 block (D-50, RESEARCH.md Key Pattern 8):
```python
# ── Phase 5: Three-Pass Pronoun Engine (D-40…D-50) ──────────────────────────
# Pass 1 — Bible analysis
enable_pass1_analysis: bool = True         # D-50: toggle for staged rollout/tests
pass1_max_cues_per_chunk: int = 400        # D-50: cues per Pass-1 chunk (0 = no chunk)

# Pass 2 — Attribution
enable_attribution: bool = True            # D-50: toggle; False → all lines get safe default
attribute_context_lines_k: int = 8         # D-50: wider context than translate (default 3)
attribute_max_cues_per_batch: int = 30     # D-50: attribution batches may be smaller

# Pass 3 — Pronoun application
pronoun_confidence_threshold: str = "medium"    # D-45/D-50: "high"|"medium"|"low"
# None → use built-in kinship-table defaults (D-45); tuple → user override
# NOTE: tuple[str,str]|None — pydantic-settings handles JSON array env var (A4 from RESEARCH.md)
# Use Field(default=None) explicitly to avoid default_factory/mutable default issues
pronoun_safe_default: tuple[str, str] | None = Field(default=None)  # D-50
```

**Note on mutable default convention** — existing `path_mappings` and `source_lang_priority` use `Field(default_factory=list/lambda)` (lines 102-107). For `tuple[str, str] | None`, `Field(default=None)` is correct (not a mutable default; `None` is immutable).

---

## Shared Patterns

### Pattern 1: No SQLAlchemy Outside `store.py` (D-39)

**Source:** `trezarr/bible/dto.py` module docstring lines 1-26, enforced by `tests/bible/test_dto_boundary.py`

**Apply to:** `analyze.py`, `attribute.py`, `reconcile.py`

All three new modules import ONLY from `trezarr.bible.dto` (not from `trezarr.bible.models` or `sqlalchemy`). The test `tests/bible/test_dto_boundary.py` inspects source via `inspect.getsource` and will catch violations. The store public API (`upsert_address_pair`, `load_address_map`, `upsert_character`, etc.) is the only persistence surface.

### Pattern 2: No New `asyncio.Semaphore` (D-06, Pitfall A)

**Source:** `trezarr/translate/engine.py` lines 19-20 (module-level comment) and `trezarr/llm/client.py` lines 55, 88-89

```python
# engine.py lines 19-20 — copy this comment verbatim to analyze.py and attribute.py:
#   - No asyncio.Semaphore in this module.  LLMClient._semaphore is the sole gate (Pitfall 1).
```

**Apply to:** `analyze.py`, `attribute.py` — all LLM calls go through `await llm_client.call(...)` which acquires `self._semaphore` internally.

### Pattern 3: No Quarantine on Transient API Errors (D-18, Pitfall B)

**Source:** `trezarr/translate/engine.py` lines 472-476:
```python
# ONLY catch BatchValidationError (retry-exhausted batch gate failure → quarantine).
# openai.APIError and any other exception propagate: the file stays out of "done"
# and is retried on the next poll cycle.  Pitfall 5 / D-18: SDK handles transport
# failures; never permanently quarantine on a transient endpoint error.
try:
    batch_results = await asyncio.gather(...)
except BatchValidationError as exc:
    ...  # quarantine
```

**Apply to:** `translate_file` Pass-1 and Pass-2 try/except blocks. Only catch `BibleAnalysisError` / `AttributionError` (logic failures after retries); never catch `openai.APIError`.

### Pattern 4: `async with session_factory() as session: async with session.begin():` Transaction Pattern (D-32)

**Source:** `trezarr/bible/store.py` lines 136-170 (`get_or_create_series`), lines 677-692 (`upsert_character`)

```python
# The canonical transaction-ownership pattern — copy verbatim for upsert_address_pair:
async with session_factory() as session:
    async with session.begin():
        row, events = await _upsert_address_pair_in_session(
            session,
            series_id=series_id,
            ...
        )
    # Transaction committed; expire_on_commit=False ensures attributes are accessible
    return (
        AddressMapDTO.model_validate(row, from_attributes=True),
        [BibleEventDTO.model_validate(e, from_attributes=True) for e in events],
    )
```

**Apply to:** `_upsert_address_pair_in_session` (must be called from inside a transaction, never open its own), `upsert_address_pair` (the sole transaction owner for Address Map writes).

### Pattern 5: Pydantic DTO at Boundary — `model_validate(row, from_attributes=True)` (D-39)

**Source:** `trezarr/bible/store.py` lines 170, 691-692, 739-742:
```python
return SeriesDTO.model_validate(row, from_attributes=True)
return (
    CharacterDTO.model_validate(row, from_attributes=True),
    [BibleEventDTO.model_validate(e, from_attributes=True) for e in events],
)
```

**Apply to:** All store functions returning DTOs. `AddressMapDTO.model_validate(row, from_attributes=True)` is the canonical form. Never return SQLA model objects outside `store.py`.

### Pattern 6: `asyncio.gather` for Concurrent Batch Dispatch (D-14, D-40)

**Source:** `trezarr/translate/engine.py` lines 477-479:
```python
batch_results = await asyncio.gather(
    *[_translate_batch(b, llm_client, settings) for b in batches]
)
```

**Apply to:** Pass-2 attribution dispatch (`attribute_batch`) and Pass-3 translation dispatch (extended `_translate_batch`). Both use the same `asyncio.gather` over the same `batches` list. This is why Pitfall E (batch count misalignment) is critical — both passes MUST use identical batches.

### Pattern 7: `TYPE_CHECKING` for Circular-Import-Safe Settings Annotation (D-11)

**Source:** `trezarr/translate/engine.py` lines 49-51, `trezarr/translate/batching.py` lines 22-24:
```python
if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
```

**Apply to:** All three new modules (`analyze.py`, `attribute.py`, `reconcile.py`) and any new TYPE_CHECKING imports. Use string annotations (`"TrezarrSettings"`) in function signatures when using `TYPE_CHECKING`.

### Pattern 8: `pytest_asyncio.fixture` for DB Fixtures in Tests (asyncio_mode="auto")

**Source:** `tests/db/conftest.py` lines 29-30, 54-55:
```python
@pytest_asyncio.fixture
async def db_engine(tmp_path):
    ...

@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)
```

**Apply to:** New test files `tests/bible/test_address_map.py` and `tests/translate/test_pronoun_engine.py`. These files need DB fixtures. The `tests/bible/conftest.py` already re-exports `db_engine` and `session_factory` from `tests/db/conftest.py` — new `tests/translate/` tests that need DB access must create a similar conftest re-export OR use the conftest in `tests/db/`.

---

## No Analog Found

None — all files have direct or close analogs in the codebase. The reconciliation module is the most novel (pure algorithm), but `batching.py` provides a strong structural analog for a pure-logic synchronous module.

---

## Critical Constraints for Planner Actions

These are verified codebase facts that must be respected:

1. **`AddressMap` has no `series` back-reference yet** (models.py lines 153-179). Both `Series.address_maps` relationship and `AddressMap.series` back-reference must be added to `models.py` in the same plan step. The `selectinload(Series.address_maps)` in `store.py` will fail silently or raise if the ORM relationship is absent.

2. **`merge_inferred` does NOT support `AddressMapDTO`** (store.py lines 793-810 TypeError branch). Use the new standalone `upsert_address_pair` function — never pass `AddressMapDTO` to `merge_inferred` (Pitfall C / Pitfall G from RESEARCH.md).

3. **`MediaItem` has `season_number` but NOT `episode_number`** (sonarr.py lines 88-99). The `derive_episode_key` function in `engine.py` must parse episode number from `eligible_item.source_sub_path.stem` using `r'S(\d{2})E(\d{2})'` regex, not from `media_item.episode_number` (Pitfall F from RESEARCH.md). Alternatively, add `episode_number: int | None = None` to `MediaItem` — the planner must decide.

4. **`SeriesBibleDTO` does NOT include `address_map` yet** (dto.py lines 151-186). Adding this field + `selectinload(Series.address_maps)` is required before `load_series_bible` can serve the Address Map to Pass 3 (Pitfall H from RESEARCH.md).

5. **`_upsert_character_in_session` lock pattern** (store.py lines 429-430): on first INSERT, `locked_fields=[]` is hardcoded — no lock-seeding via this function. The same must hold for `_upsert_address_pair_in_session`.

6. **Numbered-line 1:1 mapping**: Pass 2 `line_index` is 1-based WITHIN a batch (not document-global). Reconciliation must re-index to document-global position by summing prior batch sizes before building `resolved_map` for Pass 3 (Pitfall E from RESEARCH.md).

---

## Metadata

**Analog search scope:** `trezarr/bible/`, `trezarr/translate/`, `trezarr/llm/`, `trezarr/arr/`, `trezarr/discover/`, `trezarr/config.py`, `trezarr/cli.py`, `tests/bible/`, `tests/translate/`, `tests/db/`
**Files read:** 14 source files
**Pattern extraction date:** 2026-06-01
