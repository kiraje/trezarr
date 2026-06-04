# Phase 8: Editable Series Bible UI — Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 18 (new/modified)
**Analogs found:** 18 / 18

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trezarr/bible/store.py` (modify) | service | CRUD | itself (existing `_upsert_address_pair_in_session`, `_merge_inferred_in_session`) | exact |
| `trezarr/web/worker.py` (modify) | service | request-response | itself (existing `_series_locks` dict + setdefault pattern) | exact |
| `trezarr/web/routes/bible.py` (new) | controller | request-response | `trezarr/web/routes/settings.py` + `trezarr/web/routes/queue.py` | exact |
| `trezarr/web/app.py` (modify) | config | request-response | itself (existing `include_router` block lines 279-300) | exact |
| `trezarr/translate/reconcile.py` (modify) | service | transform | itself (existing `KINSHIP_RECIPROCAL` dict lines 35-54) | exact |
| `trezarr/bible/dto.py` (reuse) | model | transform | itself (no changes needed) | exact |
| `frontend/src/api/client.ts` (modify) | utility | request-response | itself (existing typed fetch wrapper pattern) | exact |
| `frontend/src/App.tsx` (modify) | config | request-response | itself (existing route block + `/bible` placeholder) | exact |
| `frontend/src/components/AppShell.tsx` (modify) | component | request-response | itself (existing NavItem + disabled prop pattern) | exact |
| `frontend/src/pages/BibleList.tsx` (new) | component | CRUD | `frontend/src/pages/Queue.tsx` | role-match |
| `frontend/src/pages/BibleEditor.tsx` (new) | component | CRUD | `frontend/src/pages/Settings.tsx` | role-match |
| `frontend/src/components/LockBadge.tsx` (new) | component | transform | `frontend/src/components/StatusBadge.tsx` | exact |
| `frontend/src/components/LockToggleButton.tsx` (new) | component | request-response | `frontend/src/components/MaskedSecretInput.tsx` (icon button pattern) | role-match |
| `frontend/src/components/FieldHistoryPanel.tsx` (new) | component | CRUD | `frontend/src/pages/Queue.tsx` (table + fetch pattern) | role-match |
| `frontend/src/components/PronounCombo.tsx` (new) | component | transform | `frontend/src/components/MaskedSecretInput.tsx` (controlled input with modes) | role-match |
| `frontend/src/components/ReciprocalSuggestionPanel.tsx` (new) | component | request-response | `frontend/src/pages/Settings.tsx` (SectionCard + confirm pattern) | partial |
| `tests/bible/test_human_edit.py` (new) | test | CRUD | `tests/bible/test_address_map.py` | exact |
| `tests/web/test_bible_api.py` (new) | test | request-response | `tests/web/test_settings_api.py` | exact |

---

## Pattern Assignments

### `trezarr/bible/store.py` — New functions: `apply_human_edit_character`, `apply_human_edit_address_pair`, `load_field_history`, `load_all_series`

**Analog:** itself — `_upsert_address_pair_in_session` (lines 601-717) for the transaction shape; `_merge_inferred_in_session` (lines 298-402) for the WR-01 re-read pattern; `load_series_bible` (lines 189-246) for the session + selectinload shape.

**Imports pattern** (lines 66-95 — already in place, nothing new to import):
```python
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from trezarr.bible.models import (
    BibleEvent, Series, Character, TermDictionary, AddressMap, RelationshipEvent,
)
from trezarr.bible.dto import (
    BibleEventDTO, SeriesDTO, SeriesBibleDTO, CharacterDTO, TermDTO, AddressMapDTO,
)
from trezarr.bible.merge import get_locked_fields, compute_field_changes
```

**MERGEABLE_FIELDS whitelist** (lines 259-264 — reuse for field validation in human-edit writer):
```python
MERGEABLE_FIELDS: dict[str, frozenset[str]] = {
    "character": frozenset({"gender", "rough_age", "role"}),
    "term_dictionary": frozenset({"vietnamese_rendering", "category"}),
    "series": frozenset({"register"}),
    "address_map": frozenset({"self_term", "address_term", "valid_from_episode"}),
}
```
The human-edit writer MUST validate `field` against this whitelist (identical to the security field-name injection defense in RESEARCH.md §Security Domain). `original_latin_name` and `source_term` are identity columns — not mergeable, not lockable via this path.

**Core transaction pattern — `_upsert_address_pair_in_session`** (lines 601-717 — the template for the new `apply_human_edit_address_pair`):
```python
async def _upsert_address_pair_in_session(session, *, series_id, speaker_character_id,
        addressee_character_id, self_term, address_term, valid_from_episode,
        episode_key, source) -> tuple[AddressMap, list[BibleEvent]]:
    # Step 1: SELECT by identity key
    stmt = select(AddressMap).where(
        AddressMap.series_id == series_id,
        AddressMap.speaker_character_id == speaker_character_id,
        AddressMap.addressee_character_id == addressee_character_id,
    )
    existing_row = (await session.execute(stmt)).scalar_one_or_none()

    # Step 2: read locked fields OFF THE ROW (never off caller's DTO — WR-01)
    locked = set(existing_row.locked_fields or [])

    # Step 3: for each field, skip if locked (D-34) or no-op
    for field, new_val in mergeable_fields:
        if new_val is None: continue
        if field in locked: continue          # human lock > inference
        old_val = getattr(existing_row, field)
        if old_val == new_val: continue
        setattr(existing_row, field, new_val)
        # Step 4: emit BibleEvent in the same transaction (D-32)
        evt = BibleEvent(series_id=series_id, episode_key=episode_key,
                         entity_type="address_map", entity_id=existing_row.id,
                         field=field, old_value=old_val, new_value=new_val, source=source)
        session.add(evt)
```

**Public transaction-owner wrapper pattern** (lines 825-838 — copy for new public `apply_human_edit_*` functions):
```python
async def upsert_character(session_factory, *, series_id, ...) -> tuple[CharacterDTO, list[BibleEventDTO]]:
    async with session_factory() as session:
        async with session.begin():
            row, events = await _upsert_character_in_session(session, ...)
        # expire_on_commit=False: row attributes accessible post-commit
        return (
            CharacterDTO.model_validate(row, from_attributes=True),
            [BibleEventDTO.model_validate(e, from_attributes=True) for e in events],
        )
```

**JSON dirty-tracking constraint** (D-80 — documented at lines 657-669 and 693):
```python
# CORRECT: reassign a NEW list — triggers SQLAlchemy dirty-tracking on plain JSON column
row.locked_fields = [*row.locked_fields, field]      # add lock
row.locked_fields = [f for f in row.locked_fields if f != field]  # remove lock

# WRONG: in-place .append() on plain JSON column is NOT dirty-tracked — silent data loss
row.locked_fields.append(field)  # NEVER DO THIS
```

**`load_field_history` pattern** — mirror `load_address_map` (lines 1007-1023):
```python
async def load_address_map(session_factory, series_id) -> list[AddressMapDTO]:
    async with session_factory() as session:
        stmt = select(AddressMap).where(AddressMap.series_id == series_id)
        rows = (await session.execute(stmt)).scalars().all()
        return [AddressMapDTO.model_validate(r, from_attributes=True) for r in rows]
```
For `load_field_history`: replace `AddressMap` with `BibleEvent`, add `.where()` filters for `entity_type` / `entity_id` / optional `field`, `.order_by(BibleEvent.created_at.desc()).limit(limit)`.

**`load_all_series` pattern** — mirror `load_series_bible` session shape (lines 210-221):
```python
async with session_factory() as session:
    stmt = select(Series).order_by(Series.id)
    rows = (await session.execute(stmt)).scalars().all()
    return [SeriesDTO.model_validate(r, from_attributes=True) for r in rows]
```
Use `SeriesDTO.model_validate(row, from_attributes=True)` — NOT `SeriesBibleDTO` (no eager-loading needed for the list view).

**CR-02 `register_value` alias construction** (lines 227-234 — copy this pattern for any code that constructs `SeriesBibleDTO` or `SeriesDTO` directly):
```python
# CR-02: register_value carries alias="register" — construct with Python field name
return SeriesBibleDTO(
    id=row.id,
    register_value=row.register,   # <-- Python attribute name, not alias
    ...
)
# OR use model_validate if the SQLA column is named `register` and populate_by_name=True is set:
# SeriesDTO.model_validate(row, from_attributes=True)  -- works because populate_by_name=True
```

**`apply_human_edit_character` full shape** (synthesized from the above patterns, satisfying D-80):
```python
async def apply_human_edit_character(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    character_id: int,
    series_id: int,
    field: str,
    new_value: Any,
    lock: bool = False,
) -> tuple[CharacterDTO, BibleEventDTO]:
    # Pre-session validation (field whitelist — security defense)
    allowed = MERGEABLE_FIELDS["character"]
    if field not in allowed:
        raise ValueError(f"Field '{field}' is not editable for character.")

    async with session_factory() as session:
        async with session.begin():
            # WR-01: re-read INSIDE the transaction off the SQLA row
            row = await session.get(Character, character_id)
            if row is None or row.series_id != series_id:
                raise ValueError(f"Character {character_id} not found in series {series_id}")

            old_value = getattr(row, field)
            setattr(row, field, new_value)

            # D-80: reassign NEW list — never .append() on plain JSON column
            locked_list = list(row.locked_fields or [])
            if lock and field not in locked_list:
                locked_list.append(field)
                row.locked_fields = locked_list      # reassignment = dirty-tracked
            elif not lock and field in locked_list:
                locked_list.remove(field)
                row.locked_fields = locked_list

            # D-32: audit event in the same transaction
            evt = BibleEvent(
                series_id=series_id, episode_key=None, entity_type="character",
                entity_id=character_id, field=field,
                old_value=old_value, new_value=new_value, source="lock",
            )
            session.add(evt)

        # expire_on_commit=False: attributes accessible post-commit (Pitfall 2)
        return (
            CharacterDTO.model_validate(row, from_attributes=True),
            BibleEventDTO.model_validate(evt, from_attributes=True),
        )
```

---

### `trezarr/web/worker.py` — Modify: add `get_series_lock(series_id)` accessor

**Analog:** itself — `_series_locks` dict (line 51) + `setdefault` acquire pattern (lines 412-415).

**Existing private dict** (line 51):
```python
# Per-series asyncio.Lock map — keyed by series_id; lazily populated.
# ONLY asyncio.Lock (binary ownership) — never a counting semaphore (D-68/Pitfall C).
_series_locks: dict[int, asyncio.Lock] = {}
```

**Existing acquire pattern** (lines 412-415 — copy `setdefault` exactly):
```python
lock = _series_locks.setdefault(
    series_id if series_id is not None else -1,  # -1 for movies (no series)
    asyncio.Lock(),
)
async with lock:
    ...
```

**New public accessor** (add after the `_series_locks` declaration):
```python
def get_series_lock(series_id: int) -> asyncio.Lock:
    """Return the per-series asyncio.Lock for the given series_id (D-81).

    Lazily creates the lock on first call — same pattern as _execute_job:412-415.
    Bible write endpoints acquire this lock before store writes to prevent
    interleaving with ongoing Pass-1 inference transactions.
    """
    return _series_locks.setdefault(series_id, asyncio.Lock())
```
Note: unlike the internal `_execute_job` use, the accessor does NOT need the `-1` sentinel (Bible series always have a real `series_id`). Import in `bible.py` as `from trezarr.web.worker import get_series_lock`.

---

### `trezarr/web/routes/bible.py` — New file

**Analog:** `trezarr/web/routes/settings.py` (GET/PUT editable resource shape, `_get_settings` accessor, `JSONResponse`, `APIRouter`) and `trezarr/web/routes/queue.py` (`_get_session_factory`, parameterized routes, `session_factory() as session` in-handler).

**Module header + imports pattern** (copy from `settings.py` lines 1-38):
```python
"""Bible REST API — GET/PATCH/POST/DELETE /api/series, /api/series/{id}/bible, etc. (BIBLE-08).

Design decisions honoured:
  D-79  locked_fields JSON array on entity rows — no bible_lock table.
  D-80  apply_human_edit_* writers: one txn, in-txn re-read, locked_fields reassignment, BibleEvent.
  D-81  Per-series asyncio.Lock (get_series_lock) serializes UI writes with Pass-1 inference.
  D-82  load_field_history: read-only bible_event query, LIMIT 100.
  D-39  Routes receive/return Pydantic DTOs only — no SQLAlchemy models imported here.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()
```

**`_get_session_factory` helper** (copy verbatim from `queue.py` lines 46-51):
```python
def _get_session_factory(request: Request):
    """Return the async session_factory from app.state, or None in tests without lifespan."""
    try:
        return request.app.state.session_factory
    except AttributeError:
        return None
```

**GET read endpoint pattern** (mirroring `queue.py` lines 57-92 — session factory guard + store call + dict return):
```python
@router.get("/series")
async def get_series_list(request: Request) -> JSONResponse:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return JSONResponse([])
    from trezarr.bible.store import load_all_series   # noqa: PLC0415
    dtos = await load_all_series(session_factory)
    return JSONResponse([d.model_dump(by_alias=True) for d in dtos])
```
Always `model_dump(by_alias=True)` so `register_value` serializes as `"register"` (CR-02 / Pitfall 7).

**GET bible endpoint** (series-scoped eager-load):
```python
@router.get("/series/{series_id}/bible")
async def get_series_bible(series_id: int, request: Request) -> JSONResponse:
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=404, detail="Series not found")
    from trezarr.bible.store import load_series_bible  # noqa: PLC0415
    try:
        dto = await load_series_bible(session_factory, series_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Series not found")
    return JSONResponse(dto.model_dump(by_alias=True))
```

**PATCH write endpoint pattern with D-81 series lock** (synthesized from RESEARCH.md Pattern 2):
```python
@router.patch("/series/{series_id}/characters/{character_id}")
async def patch_character(series_id: int, character_id: int, request: Request) -> JSONResponse:
    body = await request.json()
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session")

    # Security: validate field against whitelist before touching the DB
    from trezarr.bible.store import MERGEABLE_FIELDS  # noqa: PLC0415
    field = body.get("field")
    if field not in MERGEABLE_FIELDS.get("character", frozenset()):
        raise HTTPException(status_code=422, detail=f"Field '{field}' is not editable.")

    from trezarr.web.worker import get_series_lock        # noqa: PLC0415
    from trezarr.bible.store import apply_human_edit_character  # noqa: PLC0415
    lock = get_series_lock(series_id)
    async with lock:   # D-81: outermost CM — must wrap the full store write
        dto, evt = await apply_human_edit_character(
            session_factory,
            character_id=character_id,
            series_id=series_id,
            field=field,
            new_value=body["value"],
            lock=body.get("lock", False),
        )
    return JSONResponse(dto.model_dump(by_alias=True))
```

**GET history endpoint pattern**:
```python
@router.get("/series/{series_id}/bible/{entity_type}/{entity_id}/history")
async def get_field_history(series_id: int, entity_type: str, entity_id: int,
                            field: str | None = None, request: Request = None) -> JSONResponse:
    # Allowlist entity_type (security: prevent arbitrary table scan)
    VALID_ENTITY_TYPES = {"character", "term_dictionary", "series", "address_map"}
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Invalid entity_type")
    session_factory = _get_session_factory(request)
    if session_factory is None:
        return JSONResponse([])
    from trezarr.bible.store import load_field_history  # noqa: PLC0415
    dtos = await load_field_history(session_factory, series_id, entity_type, entity_id, field)
    return JSONResponse([d.model_dump(by_alias=True) for d in dtos])
```

**GET pronouns endpoint** (no session needed — pure Python constants):
```python
@router.get("/pronouns")
async def get_pronouns() -> JSONResponse:
    from trezarr.translate.reconcile import (    # noqa: PLC0415
        KNOWN_PRONOUN_TERMS_SELF,
        KNOWN_PRONOUN_TERMS_ADDRESS,
        KINSHIP_RECIPROCAL,
    )
    return JSONResponse({
        "self_terms": KNOWN_PRONOUN_TERMS_SELF,
        "address_terms": KNOWN_PRONOUN_TERMS_ADDRESS,
        # Serialize tuple keys as "self_term|address_term" for JSON
        "kinship_reciprocal": {
            f"{k[0]}|{k[1]}": {"self_term": v[0], "address_term": v[1]}
            for k, v in KINSHIP_RECIPROCAL.items()
        },
    })
```

**D-39 boundary constraint:** This file MUST NOT import from `trezarr.bible.models` or `sqlalchemy`. All SQLAlchemy models stay in `store.py`. Use deferred `noqa: PLC0415` local imports for store/worker functions (matches existing pattern in `queue.py`).

---

### `trezarr/web/app.py` — Modify: register bible router

**Analog:** itself — existing `include_router` block (lines 279-300).

**Registration pattern** (insert BEFORE the `StaticFiles` mount — Pitfall E):
```python
# GET/PATCH/POST/DELETE /api/series + /api/series/{id}/bible + /api/pronouns (BIBLE-08)
# Registered BEFORE StaticFiles (Pitfall E)
from trezarr.web.routes.bible import router as bible_router  # noqa: PLC0415
app.include_router(bible_router, prefix="/api")
```
Place after the `jobs_router` include (line 295) and before the `webhook_router` include (line 300). The `StaticFiles` mount is always last (line 307).

---

### `trezarr/translate/reconcile.py` — Modify: add `KNOWN_PRONOUN_TERMS_SELF`, `KNOWN_PRONOUN_TERMS_ADDRESS`, fill `KINSHIP_RECIPROCAL` gaps

**Analog:** itself — `KINSHIP_RECIPROCAL` dict (lines 35-54).

**Existing dict to extend** (lines 35-54 — additive only, no existing keys changed):
```python
KINSHIP_RECIPROCAL: dict[tuple[str, str], tuple[str, str]] = {
    ("anh", "em"): ("em", "anh"),
    ("em", "anh"): ("anh", "em"),
    ("chị", "em"): ("em", "chị"),
    ("em", "chị"): ("chị", "em"),
    ("anh", "anh"): ("anh", "anh"),
    ("chị", "chị"): ("chị", "chị"),
    ("ông", "cháu"): ("cháu", "ông"),
    ("bà", "cháu"): ("cháu", "bà"),
    ("ông", "con"): ("con", "ông"),
    ("bà", "con"): ("con", "bà"),
    ("bố", "con"): ("con", "bố"),
    ("mẹ", "con"): ("con", "mẹ"),
    ("cha", "con"): ("con", "cha"),
    ("tôi", "bạn"): ("bạn", "tôi"),
    ("tôi", "anh"): ("anh", "tôi"),
    ("tôi", "chị"): ("chị", "tôi"),
    ("tôi", "ông"): ("ông", "tôi"),
    ("tôi", "bà"): ("bà", "tôi"),
    # [D-90 ADDITIONS BELOW — insert here or after dict literal via .update()]
}
```

**D-90 gap fill** (add these forward + reverse pairs — H1 fix):
```python
# D-90: Additive fill of KINSHIP_RECIPROCAL gaps (bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày)
# Missing pairs verified C4 in harness review. Forward AND reverse keys added so round-trips work.
KINSHIP_RECIPROCAL.update({
    ("bác", "cháu"): ("cháu", "bác"),   # uncle/aunt (older-than-parent) ↔ niece/nephew
    ("cháu", "bác"): ("bác", "cháu"),
    ("chú", "cháu"): ("cháu", "chú"),   # uncle (younger-than-parent) ↔ niece/nephew
    ("cháu", "chú"): ("chú", "cháu"),
    ("cô", "cháu"):  ("cháu", "cô"),    # aunt (father's sister) ↔ niece/nephew
    ("cháu", "cô"):  ("cô", "cháu"),
    ("thầy", "em"):  ("em", "thầy"),    # teacher ↔ student
    ("em", "thầy"):  ("thầy", "em"),
    ("tao", "mày"):  ("mày", "tao"),    # intimate/rude peer
    ("mày", "tao"):  ("tao", "mày"),
})
```

**New `KNOWN_PRONOUN_TERMS_*` constants** (add immediately AFTER the `KINSHIP_RECIPROCAL` dict, before `SAFE_DEFAULT_*`):
```python
# KNOWN_PRONOUN_TERMS — shared vocabulary for the Bible editor combo (D-86).
# Single source of truth: exposed via /api/pronouns; never duplicated in the frontend.
# Split into self_terms and address_terms for gender-aware picker hints.
KNOWN_PRONOUN_TERMS_SELF: list[str] = [
    "tôi", "con", "em", "anh", "chị", "cháu", "mày", "tao", "bạn",
]
KNOWN_PRONOUN_TERMS_ADDRESS: list[str] = [
    "bạn", "anh", "chị", "em", "con", "cháu", "ông", "bà", "bố", "mẹ",
    "cha", "mày", "thầy", "dì", "cậu", "bác", "chú", "cô",
]
```

---

### `trezarr/bible/dto.py` — Reuse (no changes)

**All DTOs are used as-is.** Key facts for executors:

- `SeriesDTO` and `SeriesBibleDTO` have `register_value: str | None = Field(default=None, alias="register")` and `model_config = ConfigDict(from_attributes=True, populate_by_name=True)` — always `model_dump(by_alias=True)` when serializing to JSON.
- `CharacterDTO` / `TermDTO` / `AddressMapDTO` / `BibleEventDTO` all have `model_config = ConfigDict(from_attributes=True)` with no alias; `model_dump()` and `model_dump(by_alias=True)` are equivalent for these.
- `AddressMapDTO` does NOT work with `merge_inferred()` — Pitfall G (`store.py:1086` raises `TypeError`). The new `apply_human_edit_address_pair` is the only write path for AddressMap.

---

### `frontend/src/api/client.ts` — Modify: add Bible API wrappers

**Analog:** itself (lines 28-147) — `fetchWithTimeout` + typed interface + async wrapper pattern.

**Existing pattern to copy for each new endpoint** (lines 38-56):
```typescript
export interface SettingsResponse {
  [key: string]: unknown;
}

export async function getSettings(): Promise<SettingsResponse> {
  const resp = await fetchWithTimeout("/api/settings");
  if (!resp.ok) throw new Error(`GET /api/settings: ${resp.status}`);
  return resp.json();
}

export async function putSettings(patch: Record<string, unknown>): Promise<{...}> {
  const resp = await fetchWithTimeout("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`PUT /api/settings: ${resp.status}`);
  return resp.json();
}
```

**New interfaces and wrappers to add** (section after the existing `// ── Retry` block):
```typescript
// ── Bible ─────────────────────────────────────────────────────────────────────

export interface SeriesListItem {
  id: number;
  arr_kind: string;
  arr_instance: string;
  arr_series_id: number;
  register: string | null;   // alias="register" — NOT register_value
  locked_fields: string[];
}

export interface CharacterDTO {
  id: number;
  series_id: number;
  original_latin_name: string;
  gender: string | null;
  rough_age: string | null;
  role: string | null;
  locked_fields: string[];
}

export interface AddressMapDTO {
  id: number;
  series_id: number;
  speaker_character_id: number;
  addressee_character_id: number;
  self_term: string | null;
  address_term: string | null;
  valid_from_episode: string | null;
  locked_fields: string[];
}

export interface TermDTO {
  id: number;
  series_id: number;
  source_term: string;
  vietnamese_rendering: string;
  category: string | null;
  locked_fields: string[];
}

export interface BibleEventDTO {
  id: number;
  series_id: number;
  episode_key: string | null;
  entity_type: string;
  entity_id: number;
  field: string;
  old_value: unknown;
  new_value: unknown;
  source: "inference" | "lock" | "import" | "system";
  created_at: string | null;
}

export interface SeriesBibleDTO {
  id: number;
  arr_kind: string;
  arr_instance: string;
  arr_series_id: number;
  register: string | null;   // alias="register"
  arr_metadata: Record<string, unknown>;
  characters: CharacterDTO[];
  terms: TermDTO[];
  address_map: AddressMapDTO[];
  relationship_events: RelationshipEventDTO[];
  locked_fields: string[];
}

export interface PronounsResponse {
  self_terms: string[];
  address_terms: string[];
  kinship_reciprocal: Record<string, { self_term: string; address_term: string }>;
}

/** GET /api/series — list all series in the Bible. */
export async function getSeriesList(): Promise<SeriesListItem[]> {
  const resp = await fetchWithTimeout("/api/series");
  if (!resp.ok) throw new Error(`GET /api/series: ${resp.status}`);
  return resp.json();
}

/** GET /api/series/{id}/bible — load the full Bible for a series. */
export async function getSeriesBible(seriesId: number): Promise<SeriesBibleDTO> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/bible`);
  if (!resp.ok) throw new Error(`GET /api/series/${seriesId}/bible: ${resp.status}`);
  return resp.json();
}

/** PATCH /api/series/{id}/characters/{cid} — edit/lock a character field. */
export async function patchCharacter(
  seriesId: number, charId: number,
  payload: { field: string; value: unknown; lock?: boolean },
): Promise<CharacterDTO> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/characters/${charId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`PATCH character: ${resp.status}`);
  return resp.json();
}

/** GET /api/pronouns — fetch KNOWN_PRONOUN_TERMS + KINSHIP_RECIPROCAL. */
export async function getPronouns(): Promise<PronounsResponse> {
  const resp = await fetchWithTimeout("/api/pronouns");
  if (!resp.ok) throw new Error(`GET /api/pronouns: ${resp.status}`);
  return resp.json();
}

/** GET /api/series/{id}/bible/{entityType}/{entityId}/history */
export async function getFieldHistory(
  seriesId: number, entityType: string, entityId: number, field?: string,
): Promise<BibleEventDTO[]> {
  const url = `/api/series/${seriesId}/bible/${entityType}/${entityId}/history` +
              (field ? `?field=${encodeURIComponent(field)}` : "");
  const resp = await fetchWithTimeout(url);
  if (!resp.ok) throw new Error(`GET field history: ${resp.status}`);
  return resp.json();
}
```

---

### `frontend/src/App.tsx` — Modify: replace `/bible` placeholder with real routes

**Analog:** itself (lines 1-46) — existing `Route` block + import pattern.

**Current placeholder** (lines 33-41 — replace entirely):
```tsx
{/* Phase 8 placeholder */}
<Route
  path="/bible"
  element={
    <div className="text-[#6b7280] text-sm">
      Series Bible editing will be available in a future release.
    </div>
  }
/>
```

**New routes** (add imports at top, replace placeholder):
```tsx
import BibleList from "./pages/BibleList";
import BibleEditor from "./pages/BibleEditor";

// In the Routes block:
<Route path="/bible" element={<BibleList />} />
<Route path="/bible/:seriesId" element={<BibleEditor />} />
```

---

### `frontend/src/components/AppShell.tsx` — Modify: enable Bible NavItem

**Analog:** itself (lines 93-99) — existing `NavItem` with `disabled` prop.

**Current disabled item** (lines 93-99):
```tsx
{/* Phase 8 placeholder — visible but muted */}
<NavItem
  to="/bible"
  icon={<BookOpen size={16} />}
  label="Bible"
  disabled
/>
```

**New enabled item** (remove `disabled` prop):
```tsx
<NavItem
  to="/bible"
  icon={<BookOpen size={16} />}
  label="Bible"
/>
```
No other changes to `AppShell.tsx`. The `NavLink` active styling at lines 41-50 already handles the active state visually.

---

### `frontend/src/pages/BibleList.tsx` — New file

**Analog:** `frontend/src/pages/Queue.tsx` (lines 1-69) — fetch-on-mount, `unreachable` banner, heading + table pattern.

**Data load pattern** (Queue.tsx lines 28-53):
```tsx
export default function Queue() {
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const data = await getQueue();
        setJobs(data);
        setUnreachable(false);
      } catch {
        setUnreachable(true);
      }
    }
    void load();
    // No polling for Bible list — static until user edits
  }, []);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-lg font-semibold text-[#e2e6f0]">Series Bible</h1>
      </div>
      {unreachable && <UnreachableBanner />}
      {/* table rendered here */}
    </div>
  );
}
```

**Table row pattern** (from `JobTable.tsx` — same 40px rows, `bg-bg-stripe` alternating, `border-bottom`):
```tsx
<tr className={`h-10 border-b border-[#2d3148] cursor-pointer hover:bg-[#22263a] ${idx % 2 === 1 ? "bg-bg-stripe" : ""}`}
    onClick={() => navigate(`/bible/${series.id}`)}>
  <td className="px-3 text-sm text-[#e2e6f0]">{series.arr_series_id}</td>
  ...
</tr>
```
Use `useNavigate()` from `react-router-dom` for row-click navigation.

---

### `frontend/src/pages/BibleEditor.tsx` — New file

**Analog:** `frontend/src/pages/Settings.tsx` (lines 1-165) — load on mount, card layout, dirty-state tracking, save + toast pattern.

**Load-on-mount pattern** (Settings.tsx lines 112-134):
```tsx
const [settings, setSettings] = useState<SettingsResponse | null>(null);
const [unreachable, setUnreachable] = useState(false);
const [toast, setToast] = useState<ToastState | null>(null);

const showToast = useCallback((t: Omit<ToastState, "id">) => {
  setToast({ ...t, id: Date.now() });
}, []);

useEffect(() => {
  async function load() {
    try {
      const [s, el] = await Promise.all([getSettings(), getEnvLocked()]);
      setSettings(s);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }
  void load();
}, []);
```

For BibleEditor, replace with `getSeriesBible(seriesId)` + `getPronouns()` in parallel — same `Promise.all` pattern.

**Tab state** (client-side, not URL-based per UI-SPEC):
```tsx
type Tab = "characters" | "address_map" | "terms" | "register";
const [activeTab, setActiveTab] = useState<Tab>("characters");
```

**SectionCard primitive** (Settings.tsx lines 42-48 — reuse verbatim):
```tsx
function SectionCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-bg-surface border border-[#2d3148] rounded p-6 flex flex-col gap-4">
      {children}
    </div>
  );
}
```

**TextField primitive** (Settings.tsx lines 64-96 — reuse verbatim, or import if extracted):
```tsx
function TextField({ id, label, value, onChange, type = "text", disabled = false }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-[#6b7280]">{label}</label>
      <input id={id} type={type} value={value} onChange={(e) => onChange(e.target.value)}
             disabled={disabled}
             className="h-9 w-full bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-[#e2e6f0] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2 disabled:opacity-60 disabled:cursor-not-allowed" />
    </div>
  );
}
```

**Toast usage** (Settings.tsx lines 116-120 — copy exactly):
```tsx
import Toast from "../components/Toast";
import type { ToastState } from "../components/Toast";

const [toast, setToast] = useState<ToastState | null>(null);
const showToast = useCallback((t: Omit<ToastState, "id">) => {
  setToast({ ...t, id: Date.now() });
}, []);
// Then at bottom of JSX:
<Toast toast={toast} onDismiss={() => setToast(null)} />
```

---

### `frontend/src/components/LockBadge.tsx` — New file

**Analog:** `frontend/src/components/StatusBadge.tsx` (lines 1-78) — exact structural match: `STATUS_CONFIG` record + 4px dot + text label + `h-5 px-1.5` span.

**Copy the full StatusBadge structure**, replacing the status types and colors:
```tsx
// Mirror StatusBadge exactly — same 4px dot + text label structure, same h-5/px-1.5/text-xs
export type LockState = "locked" | "inference";

interface LockConfig { bg: string; text: string; dot: string; label: string; }

const LOCK_CONFIG: Record<LockState, LockConfig> = {
  locked: { bg: "#14291e", text: "#4ade80", dot: "#22c55e", label: "Locked" },
  inference: { bg: "#1e293b", text: "#94a3b8", dot: "#64748b", label: "Inference" },
};
// Colors: locked uses StatusBadge "done" palette; inference uses "queued" palette.
// Reuse those hex values — do NOT introduce new hex values (UI-SPEC token discipline).

interface LockBadgeProps { state: LockState; }

export default function LockBadge({ state }: LockBadgeProps) {
  const config = LOCK_CONFIG[state];
  return (
    <span className="inline-flex items-center gap-1 h-5 px-1.5 rounded text-xs font-normal"
          style={{ backgroundColor: config.bg, color: config.text }}>
      <span className="inline-block w-1 h-1 rounded-full flex-shrink-0"
            style={{ backgroundColor: config.dot }} aria-hidden="true" />
      {config.label}
    </span>
  );
}
```
Never dot-only — always include the text label (accessibility contract: color is supplementary).

---

### `frontend/src/components/PronounCombo.tsx` — New file

**Analog:** `frontend/src/components/MaskedSecretInput.tsx` (lines 1-99) — controlled input with two display modes (masked/revealed), state-based mode switch, same input styling.

**Mode-switch pattern** (MaskedSecretInput.tsx lines 30-99 — adapt for select/text switch):
```tsx
// MaskedSecretInput uses useState(showTyped) to toggle between password and text input.
// PronounCombo uses useState(customMode) to toggle between <select> and <input type="text">.
const [customMode, setCustomMode] = useState(!terms.includes(value));

// Input class (copy verbatim from MaskedSecretInput.tsx line 36):
const inputClass = "h-9 w-full bg-bg-surface border border-[#2d3148] rounded px-2 text-sm text-[#e2e6f0] focus:outline-[#3b82f6] focus:outline-2 focus:outline-offset-2";
```

**Combo structure**:
```tsx
export default function PronounCombo({ value, onChange, terms, placeholder = "" }) {
  const [customMode, setCustomMode] = useState(!terms.includes(value) && value !== "");
  // If not in terms list, start in custom mode with text input

  if (customMode) {
    return (
      <div className="flex items-center gap-2">
        <input type="text" value={value} onChange={(e) => onChange(e.target.value)}
               autoFocus className={inputClass} placeholder={placeholder} />
        <button type="button" className="text-xs text-accent"
                onClick={() => { onChange(""); setCustomMode(false); }}>Done</button>
      </div>
    );
  }

  return (
    <select value={value} onChange={(e) => {
        if (e.target.value === "__custom__") { setCustomMode(true); }
        else { onChange(e.target.value); }
      }} className={inputClass}>
      <option value="" disabled>{placeholder || "Select…"}</option>
      {terms.map(t => <option key={t} value={t}>{t}</option>)}
      <option value="__custom__">custom…</option>
    </select>
  );
}
```

---

### `tests/bible/test_human_edit.py` — New file

**Analog:** `tests/bible/test_address_map.py` (lines 1-85) — same file header, same `_create_series` / `_create_characters` helpers, same `async def test_*` pattern.

**File header pattern** (test_address_map.py lines 1-17):
```python
"""Tests for Phase 8 human-edit write path (BIBLE-08/09).

Tests cover:
  BIBLE-08 criterion 2 — locked field survives a contradicting merge_inferred call
  BIBLE-08 criterion 2 — JSON dirty-tracking: locked_fields persisted correctly
  BIBLE-08 criterion 2 — BibleEvent(source="lock") emitted in same transaction
  BIBLE-09 criterion 3 — locked pair survives reconcile_attributions
  BIBLE-09 criterion 3 — locked pair propagates to next episode

asyncio_mode="auto" is configured project-wide in pyproject.toml — no @pytest.mark.asyncio.
DB fixtures provided via tests/bible/conftest.py (re-exports from tests/db/conftest.py).
"""
from __future__ import annotations
```

**Helper pattern** (test_address_map.py lines 22-52 — copy verbatim, reuse in test_human_edit.py):
```python
async def _create_series(session_factory, arr_series_id: int = 1) -> int:
    from trezarr.bible.store import get_or_create_series
    dto = await get_or_create_series(session_factory, arr_kind="sonarr",
        arr_instance="default", arr_series_id=arr_series_id,
        arr_metadata_snapshot={"title": "Test Series"})
    return dto.id

async def _create_characters(session_factory, series_id: int) -> tuple[int, int]:
    from trezarr.bible.store import upsert_character
    speaker_dto, _ = await upsert_character(session_factory, series_id=series_id,
        original_latin_name="Minh", gender="male", source="inference")
    addressee_dto, _ = await upsert_character(session_factory, series_id=series_id,
        original_latin_name="Lan", gender="female", source="inference")
    return speaker_dto.id, addressee_dto.id
```

---

### `tests/web/test_bible_api.py` — New file

**Analog:** `tests/web/test_settings_api.py` (lines 1-64) — `create_app()` + `httpx.AsyncClient(ASGITransport(...))` pattern, no `@pytest.mark.asyncio` (asyncio_mode=auto).

**Test structure pattern** (test_settings_api.py lines 8-27):
```python
async def test_get_series_list():
    from trezarr.web.app import create_app      # noqa: PLC0415
    from httpx import AsyncClient, ASGITransport  # noqa: PLC0415

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/series")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

**D-39 boundary test** (from RESEARCH.md Example 8):
```python
async def test_bible_route_does_not_import_sqla():
    """Route module must not import SQLAlchemy models (D-39 boundary)."""
    import inspect
    import trezarr.web.routes.bible as bible_module
    src = inspect.getsource(bible_module)
    assert "from trezarr.bible.models" not in src
    assert "from sqlalchemy" not in src
```

---

## Shared Patterns

### Transaction Ownership (D-80 / D-32)
**Source:** `trezarr/bible/store.py` lines 825-838 (public `upsert_character` wrapper pattern)
**Apply to:** All new `apply_human_edit_*` and `load_all_series` / `load_field_history` functions in `store.py`
```python
async with session_factory() as session:
    async with session.begin():
        # all DB work here: session.get(), setattr, session.add(BibleEvent(...))
    # transaction committed; expire_on_commit=False keeps attributes live
```
Never open nested transactions. Never call `session.commit()` manually inside `session.begin()`.

### `_get_session_factory` Helper (D-81 dependency)
**Source:** `trezarr/web/routes/queue.py` lines 46-51
**Apply to:** `trezarr/web/routes/bible.py` — copy verbatim
```python
def _get_session_factory(request: Request):
    try:
        return request.app.state.session_factory
    except AttributeError:
        return None
```

### JSON `locked_fields` Reassignment (D-80 footgun guard)
**Source:** D-80 mandate + `store.py:693` read pattern
**Apply to:** ALL new store writer functions that touch `locked_fields`
```python
# CORRECT: new list object = dirty-tracked on plain JSON column
row.locked_fields = [*row.locked_fields, field]    # add
row.locked_fields = [f for f in row.locked_fields if f != field]  # remove
# WRONG: in-place .append() not tracked by SQLAlchemy plain JSON type
```

### `model_dump(by_alias=True)` for Register Alias (CR-02)
**Source:** `trezarr/bible/dto.py` lines 56-71 (`register_value` with `alias="register"`)
**Apply to:** All `bible.py` route handlers that serialize `SeriesDTO` or `SeriesBibleDTO`
**And:** All TypeScript interfaces — use `register: string | null` not `register_value`
```python
return JSONResponse(dto.model_dump(by_alias=True))  # "register" in JSON, not "register_value"
```

### `MERGEABLE_FIELDS` Whitelist Validation (Security)
**Source:** `trezarr/bible/store.py` lines 259-264, 267-291
**Apply to:** Every write endpoint in `bible.py` before any store call
```python
from trezarr.bible.store import MERGEABLE_FIELDS
field = body.get("field")
if field not in MERGEABLE_FIELDS.get(entity_type, frozenset()):
    raise HTTPException(status_code=422, detail=f"Field '{field}' is not editable.")
```

### D-39 Boundary: No SQLAlchemy Imports in Route Modules
**Source:** `store.py` docstring lines 1-52; enforced by `tests/bible/test_dto_boundary.py`
**Apply to:** `trezarr/web/routes/bible.py` — all SQLAlchemy model imports must stay in `store.py`

### React Fetch-on-Mount with Cancellation Guard
**Source:** Synthesized from `frontend/src/pages/Queue.tsx` (lines 28-53) and `Settings.tsx` (lines 112-134)
**Apply to:** `BibleList.tsx` and `BibleEditor.tsx`
```tsx
useEffect(() => {
  let cancelled = false;
  async function load() {
    try {
      const data = await getSomething();
      if (!cancelled) setData(data);
    } catch {
      if (!cancelled) setError(true);
    }
  }
  void load();
  return () => { cancelled = true; };
}, [dependency]);
```

### UnreachableBanner Component (amber banner)
**Source:** `frontend/src/pages/Queue.tsx` lines 16-26 and `Settings.tsx` lines 28-38 — identical implementation in both; copy to `BibleList.tsx` and `BibleEditor.tsx`
```tsx
function UnreachableBanner() {
  return (
    <div className="w-full mb-4 px-4 py-3 text-sm rounded"
         style={{ backgroundColor: "#451a03", color: "#fbbf24" }} role="alert">
      Cannot reach the Trezarr service. Check that the server is running.
    </div>
  );
}
```

### Deferred Local Imports in Route Handlers
**Source:** `trezarr/web/routes/queue.py` lines 68, 109, 157 — all model/store imports deferred inside handler bodies with `# noqa: PLC0415`
**Apply to:** `bible.py` — all `from trezarr.bible.store import ...` inside handler bodies

---

## No Analog Found

All Phase 8 files have strong analogs. The following new components have only partial analogs and will need additional design work:

| File | Role | Data Flow | Partial Analog | Gap |
|------|------|-----------|----------------|-----|
| `frontend/src/components/ReciprocalSuggestionPanel.tsx` | component | request-response | `Settings.tsx` `SectionCard` shape | No existing inline panel-below-row pattern; closest is `FieldHistoryPanel` (also new) |
| `frontend/src/components/FieldHistoryPanel.tsx` | component | CRUD | `Queue.tsx` table rendering | No existing inline-expansion-below-row pattern; planner should specify max-height 320px + overflow-y scroll per UI-SPEC |
| `frontend/src/components/LockToggleButton.tsx` | component | request-response | `MaskedSecretInput.tsx` eye-toggle button (lines 80-92) | Icon-only 32×32 button with `aria-label`; pattern exists but not as a standalone component |

For these three components, use UI-SPEC.md §Component Inventory as the spec and `StatusBadge.tsx` + `MaskedSecretInput.tsx` as stylistic templates.

---

## Metadata

**Analog search scope:** `trezarr/bible/`, `trezarr/web/routes/`, `trezarr/web/`, `trezarr/translate/`, `frontend/src/`, `tests/bible/`, `tests/web/`, `tests/translate/`
**Files scanned:** 22 source files read directly
**Pattern extraction date:** 2026-06-02

**Critical pitfalls captured in patterns:**
1. JSON dirty-tracking: `row.locked_fields = [*row.locked_fields, field]` — never `.append()`
2. Locking AddressMap with None term: block at API layer (HTTP 422) before store call
3. StaticFiles router order: `bible_router` include BEFORE `app.mount("/", StaticFiles(...))`
4. `merge_inferred` on AddressMapDTO raises `TypeError` — use `apply_human_edit_address_pair` instead
5. Series lock acquisition: `async with get_series_lock(series_id):` as outermost CM in write handler
6. CR-02 register alias: always `model_dump(by_alias=True)` and TypeScript `register: string | null`
7. D-39 boundary: `bible.py` must not import from `trezarr.bible.models` or `sqlalchemy` directly
