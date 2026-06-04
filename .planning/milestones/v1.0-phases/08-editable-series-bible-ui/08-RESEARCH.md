# Phase 8: Editable Series Bible UI - Research

**Researched:** 2026-06-02
**Domain:** FastAPI REST router + SQLAlchemy 2.0 async write path + React 19 SPA editor + Vietnamese pronoun-pair consistency
**Confidence:** HIGH — all findings are direct codebase reads; no external verification required for the core store/reconcile patterns

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-79** — Keep Phase-4 `locked_fields: JSON` array per row. No `bible_lock` table. No migration for locks.
`locked_fields` JSON is already on `series`/`character`/`term_dictionary`/`address_map` (models.py:85,126,154,185).
`get_locked_fields` in `merge.py:30-46` is the future swap seam.

**D-80** — Add a NEW dedicated store writer: `apply_human_edit` / `set_lock` / `clear_lock` (+ an AddressMap variant).
Do NOT reuse `merge_inferred`. Must in ONE `async with session.begin()`: (1) re-read row via `session.get`; (2) set new value;
(3) reassign `locked_fields` as a new list (NOT `.append()`); (4) emit `BibleEvent(source="lock")` in the same txn;
(5) return a DTO. Mirror `_upsert_address_pair_in_session` (store.py:601-717) for AddressMap.

**D-81** — Route UI Bible writes through the same per-series `asyncio.Lock` the worker uses (`worker.py:51`), plus
the in-txn re-read (D-80). Expose a `get_series_lock(series_id)` accessor. Lock held for the duration of the write.

**D-82** — Lock badge + `source` shown inline from `locked_fields` (zero new query). Add a read-only
`load_field_history(series_id, entity_type, entity_id, field?) -> list[BibleEventDTO]` over `bible_event`
table (index `ix_bible_event_series_entity_time`). No schema change.

**D-83** — View + edit + lock + ADD; DELETE limited to Term and Address-pair (leaf rows); Character delete DEFERRED.
ADD must route through identity-aware upsert helpers (normalization SELECT-before-INSERT). Address-pair ADD requires
two existing `character.id`s (use character pickers, not free-text).

**D-84** — Extend the Phase-7 React 19 + Vite 7 SPA. Reuse `AppShell`, `StatusBadge`, `Toast`, and `api/client.ts`.
New pages: Series list → Series-Bible editor with Characters / Address Map / Term Dictionary / Register sections.
Register uses the `register_value` Pydantic alias `"register"` (CR-02). Client-side refetch, functional-first.

**D-85** — When editing a directed pair, SUGGEST the reciprocal side-by-side pre-filled from `KINSHIP_RECIPROCAL`;
let the user confirm. Do not force-write; do not silently leave untouched. If no `KINSHIP_RECIPROCAL` entry exists,
show "no known reciprocal — set reverse manually".

**D-86** — Self-term / address-term inputs are a COMBO: dropdown of `KNOWN_PRONOUN_TERMS` constant + "custom…" escape hatch.
`KNOWN_PRONOUN_TERMS` is a new constant co-located with `KINSHIP_RECIPROCAL` in `reconcile.py`, surfaced via the API.

**D-87** — Warn-but-allow on relational risks; BLOCK only on an empty/whitespace term when locking a pair.
`reconcile.py:275` requires both `self_term` and `address_term` non-None for a lock to win; a locked pair with an
empty term is silently ignored. This is the single subtlest correctness trap.

**D-88** — Defer relationship-event AUTHORING; make the editor event-AWARE (read-only display of existing
`relationship_events` for the pair, + `valid_from_episode` marker). Locking is the only way to pin an edited pair.

**D-89** — Confirmed: a locked Address-Map pair defeats the PRON-03 safe-default gate and reaches Pass-3 application,
contingent on both terms non-None (D-87). No new engine work required.

**D-90** — Additively fill the H1 `KINSHIP_RECIPROCAL` gaps (bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày + missing
reverse keys). Add a junior-only-attribution regression test. DB UNIQUE constraint on Bible identity: planner's
discretion, lean defer.

### Claude's Discretion

Exact new store-function names/signatures; whether the writer is one function with a `lock: bool` flag or separate
set/lock/clear functions; precise REST route shapes and response DTO envelopes; whether history endpoint is generic
or per-entity; SPA component decomposition, routing, and form/validation library (functional-first, no design mandate);
how warnings (D-87) are surfaced (inline vs toast); whether `KNOWN_PRONOUN_TERMS` is one flat list or split self/address
with gender hints; exact set of H1 reciprocal keys added (D-90); whether to add DB UNIQUE constraints now or defer;
whether to expose the per-series-lock accessor as a worker helper or a small service object.

### Deferred Ideas (OUT OF SCOPE)

- Relationship-event AUTHORING (create/edit episode-marked transitions) → follow-up phase
- `bible_lock` table with `locked_by`/`locked_at`/`reason` → multi-user phase
- DB `UniqueConstraint` on Character/Term/AddressMap identity → migration + data-dedup, mitigated for single-user
- Character delete (cascading dependent address-pairs/events) → deferred; edit-only for v1
- Optimistic-concurrency version column / multi-process locking → only if single-process model outgrown
- Per-series source/register/model OVERRIDE config (SVC-05) → Phase 10
- ASS/SSA + VTT → Phase 9; Bazarr inventory / source selection → Phase 10
- SSE/WebSocket live updates for the Bible editor → v1 uses client-side refetch (D-84)
- Retroactive re-translation of already-finished episodes after a lock → forward-only
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BIBLE-08 | User can view and edit the Series Bible (characters, address map, term dictionary, register); edits are lockable and survive re-analysis | New REST `bible` router (read + write + lock/unlock endpoints) + lock-aware store writer (D-80) + SPA Bible editor pages |
| BIBLE-09 | Locked corrections propagate forward to all subsequent episode translations (the human override valve) | Already guaranteed by merge.py:84, store.py:698, reconcile.py:267-277; UI only needs to set the lock correctly (D-80 write path) |
</phase_requirements>

---

## Summary

Phase 8 is the **payoff of Phase 4's architectural runway**: Phase 4 shipped `locked_fields`, `bible_event`, and the merge-precedence contract explicitly promising *"Phase 8's UI is the production setter"* (D-34). This phase delivers one new FastAPI router, one new store write path, and one new SPA section. Everything else — persistence engine, merge precedence, lock propagation to subtitles — is already operational.

**The riskiest code is the new write path, not the UI.** The four failure modes to design against:
1. **JSON dirty-tracking**: `locked_fields` is a plain `JSON` column. `.append()` in-place is NOT dirty-tracked. Always reassign a new list: `row.locked_fields = [*row.locked_fields, field]`.
2. **Locking an empty term**: `reconcile.py:275` silently ignores a locked AddressMap pair where either term is `None`. The write path must block this at the API layer.
3. **Stale-DTO interleave**: The write endpoint must acquire `get_series_lock(series_id)` BEFORE its store write. Without the lock, a UI write can interleave between two Pass-1 inference transactions.
4. **AddressMap special-casing**: `merge_inferred()` raises `TypeError` on `AddressMapDTO` (store.py:1086). The AddressMap human-edit writer must NOT route through `merge_inferred` — mirror `_upsert_address_pair_in_session` instead.

The lock-propagation invariant (criterion 3 / BIBLE-09) is already guaranteed by the existing engine and is a testing concern, not a build concern.

**Primary recommendation:** Implement the write path (D-80/D-81) first in Wave 1 with full test coverage of the four failure modes above; the REST router and SPA can follow in Waves 2-3 against a proven store layer.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bible read (view series list, full Bible) | API / Backend (FastAPI `bible` router) | Browser (React pages consuming JSON) | Data lives in SQLite; browser has no direct DB access |
| Bible write / lock / unlock | API / Backend (FastAPI + new store writer) | Browser (form submit) | Lock state must be authoritative; single transaction with audit event |
| Concurrency serialization | API / Backend (per-series `asyncio.Lock`) | — | asyncio.Lock is process-scoped; single uvicorn process (D-61) |
| Provenance badge + lock state display | Browser / Client | — | Derived from `locked_fields` in the DTO; zero extra query |
| Field history drill-down | API / Backend (read-only `load_field_history`) | Browser (timeline render) | Query against `bible_event` table |
| Term vocabulary / reciprocal suggestions | API / Backend (expose `KNOWN_PRONOUN_TERMS` + `KINSHIP_RECIPROCAL`) | Browser (combo dropdown pre-fill) | Must be one source of truth; never duplicated in frontend |
| Vietnamese relational validation warnings | Browser / Client | API (block rule on non-None lock guard) | Warn-but-allow runs client-side for latency; block-on-empty enforced server-side |
| KINSHIP_RECIPROCAL gap fill (H1 fix) | Backend engine (`reconcile.py`) | — | Pure Python constant; additive, no DB |
| SPA routing / navigation | Browser / Client | FastAPI StaticFiles (SPA fallback via html=True) | react-router-dom client-side routing; FastAPI serves index.html for unknown paths |

---

## Standard Stack

No new dependencies are required. Phase 8 builds entirely on the installed stack.

### Core (already installed)
| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| FastAPI | 0.136.x | New `bible` APIRouter + existing app.py mount | `include_router` before `StaticFiles` (Pitfall E) |
| SQLAlchemy 2.0 async | 2.0.x | Lock-aware store writer; `session.get` + `session.begin()` | `expire_on_commit=False` already set by `build_session_factory` |
| aiosqlite | 0.22.x | Async SQLite driver (already in use) | No change |
| Pydantic v2 | 2.13.x | DTOs: `SeriesBibleDTO`, `CharacterDTO`, `AddressMapDTO`, `TermDTO`, `BibleEventDTO` | `register_value` alias (CR-02) respected throughout |
| React 19 / Vite 7 | 19.x / 7.x | SPA Bible editor pages | reuse existing shell, Toast, StatusBadge, api/client.ts |
| react-router-dom | (installed) | `/bible`, `/bible/:id`, `/bible/:id/characters`, etc. | Already used in App.tsx |

### No New Packages
Phase 8 installs nothing new. The entire feature surface is internal code additions.

---

## Package Legitimacy Audit

No new packages are introduced in this phase. Section not applicable.

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (React SPA)
  │  GET /api/series                                         ─┐
  │  GET /api/series/{id}/bible                              │ read
  │  GET /api/series/{id}/bible/{entity_type}/{id}/history   ─┘
  │  PATCH /api/series/{id}/characters/{cid}                 ─┐
  │  POST  /api/series/{id}/address-map                      │ write
  │  DELETE /api/series/{id}/terms/{tid}                     │
  │  POST  /api/series/{id}/characters/{cid}/lock            │ lock
  │  DELETE /api/series/{id}/characters/{cid}/lock           ─┘
  │  GET /api/pronouns  (KNOWN_PRONOUN_TERMS + KINSHIP_RECIPROCAL)
  ▼
FastAPI  /api  bible_router (trezarr/web/routes/bible.py)
  │  Registered BEFORE StaticFiles (Pitfall E)
  │  _get_session_factory(request) → request.app.state.session_factory
  │  _get_series_lock(request, series_id) → worker.get_series_lock(series_id)
  ▼
  ├─ READ path ──────────────────────────────────────────────────────
  │    store.load_series_bible(session_factory, series_id) [exists]
  │    store.load_field_history(session_factory, series_id, entity_type, entity_id, field) [NEW]
  │    reconcile.KNOWN_PRONOUN_TERMS, reconcile.KINSHIP_RECIPROCAL [exposed via /api/pronouns]
  │
  └─ WRITE path ─────────────────────────────────────────────────────
       async with get_series_lock(series_id):  ← D-81 guard
         store.apply_human_edit(session_factory, entity_type, entity_id,
                                field, new_value, lock=True|False)  [NEW]
         ┌─ single async with session.begin():
         │    row = await session.get(Model, entity_id)       ← WR-01 re-read
         │    row.field = new_value                           ← setattr
         │    row.locked_fields = [*row.locked_fields, field] ← reassign NEW list!
         │    session.add(BibleEvent(source="lock", ...))     ← D-32 audit
         └─ commit
         return DTO

Translation pipeline (Pass-1 merge_inferred / Pass-3 reconcile)
  ├─ merge.py:84: skips locked fields → locked value survives re-analysis (BIBLE-08 criterion 2)
  ├─ store.py:698: _upsert_address_pair_in_session skips locked fields → survives re-run
  └─ reconcile.py:267-277: lock-first branch wins before confidence gate (BIBLE-09 criterion 3)
```

### Recommended Project Structure

```
trezarr/
├── web/
│   ├── routes/
│   │   └── bible.py          # NEW: APIRouter for all Bible endpoints
│   └── worker.py             # MODIFY: add get_series_lock(series_id) accessor
├── bible/
│   └── store.py              # MODIFY: add apply_human_edit, load_field_history
└── translate/
    └── reconcile.py          # MODIFY: add KNOWN_PRONOUN_TERMS, fill KINSHIP_RECIPROCAL gaps

frontend/src/
├── api/
│   └── client.ts             # MODIFY: add Bible API wrappers + types
├── pages/
│   ├── BibleList.tsx         # NEW: Series list page
│   └── BibleEditor.tsx       # NEW: Series Bible editor page (Characters / AddressMap / Terms / Register)
├── components/
│   ├── LockBadge.tsx         # NEW: locked/inference provenance badge
│   ├── FieldHistoryPanel.tsx # NEW: per-field timeline drill-down
│   └── PronounCombo.tsx      # NEW: KNOWN_PRONOUN_TERMS combo + custom escape
└── App.tsx                   # MODIFY: replace /bible placeholder with real routes
```

### Pattern 1: Lock-Aware Store Writer (D-80)

**What:** A new store write function that sets a field value and optionally locks it, in one transaction, mirroring `_upsert_address_pair_in_session`.
**When to use:** Every UI write that the human intends to pin (lock=True) or merely update (lock=False).

```python
# Source: trezarr/bible/store.py (existing _upsert_address_pair_in_session pattern, :601-717)
# New function: apply_human_edit_character (example — CharacterDTO variant)

async def apply_human_edit_character(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    character_id: int,
    series_id: int,
    field: str,
    new_value: Any,
    lock: bool = False,
) -> tuple[CharacterDTO, BibleEventDTO]:
    """Set a Character field (and optionally lock it) in one transaction.

    WR-01: re-reads the row via session.get INSIDE the transaction.
    D-80: reassigns locked_fields as a NEW list (not .append — JSON dirty-tracking).
    D-32: emits BibleEvent(source="lock") in the same transaction.
    D-39: returns DTO, never the SQLA row.
    """
    async with session_factory() as session:
        async with session.begin():
            # WR-01: re-read inside the transaction
            row = await session.get(Character, character_id)
            if row is None:
                raise ValueError(f"No Character with id={character_id}")
            if row.series_id != series_id:
                raise ValueError("series_id mismatch")

            old_value = getattr(row, field)
            setattr(row, field, new_value)

            # D-80: reassign NEW list — never .append() (JSON column, not dirty-tracked)
            locked = list(row.locked_fields or [])
            if lock and field not in locked:
                locked.append(field)
                row.locked_fields = locked  # reassignment triggers dirty-tracking
            elif not lock and field in locked:
                locked.remove(field)
                row.locked_fields = locked

            evt = BibleEvent(
                series_id=series_id,
                episode_key=None,  # human edits are not episode-scoped
                entity_type="character",
                entity_id=character_id,
                field=field,
                old_value=old_value,
                new_value=new_value,
                source="lock",  # D-32 source enum
            )
            session.add(evt)

        # expire_on_commit=False: row attributes accessible post-commit
        return (
            CharacterDTO.model_validate(row, from_attributes=True),
            BibleEventDTO.model_validate(evt, from_attributes=True),
        )
```

### Pattern 2: Per-Series Lock Accessor (D-81)

**What:** A public function exposing the private `_series_locks` dict.
**When to use:** Every Bible write endpoint acquires this lock before calling the store writer.

```python
# Source: trezarr/web/worker.py:51 (_series_locks private dict)
# Add to worker.py:

def get_series_lock(series_id: int) -> asyncio.Lock:
    """Return the per-series asyncio.Lock for the given series_id.

    Lazily creates the lock on first call (same pattern as _execute_job:412-417).
    D-81: Bible write endpoints acquire this lock before store writes to prevent
    interleaving with ongoing Pass-1 inference transactions.
    """
    return _series_locks.setdefault(series_id, asyncio.Lock())
```

The write endpoint pattern:
```python
# Source: mirroring trezarr/web/routes/queue.py pattern
from trezarr.web.worker import get_series_lock

@router.patch("/series/{series_id}/characters/{character_id}")
async def patch_character(series_id: int, character_id: int, request: Request):
    body = await request.json()
    session_factory = _get_session_factory(request)
    lock = get_series_lock(series_id)
    async with lock:  # D-81: serializes with worker's Pass-1 writes
        dto, evt = await apply_human_edit_character(
            session_factory,
            character_id=character_id,
            series_id=series_id,
            field=body["field"],
            new_value=body["value"],
            lock=body.get("lock", False),
        )
    return dto.model_dump(by_alias=True)
```

### Pattern 3: Field History Read (D-82)

**What:** A read-only query over `bible_event` returning `list[BibleEventDTO]`, filtered by entity.
**When to use:** History timeline drill-down per entity.

```python
# Source: based on existing BibleEvent model (models.py:221-264) and BibleEventDTO (dto.py:175-203)
# Index ix_bible_event_series_entity_time already covers this query pattern.

async def load_field_history(
    session_factory: async_sessionmaker[AsyncSession],
    series_id: int,
    entity_type: str,
    entity_id: int,
    field: str | None = None,
    limit: int = 100,
) -> list[BibleEventDTO]:
    """Return bible_event rows for an entity, ordered by created_at desc.

    Uses the existing ix_bible_event_series_entity_time index.
    D-82: no schema change needed.
    """
    async with session_factory() as session:
        stmt = (
            select(BibleEvent)
            .where(
                BibleEvent.series_id == series_id,
                BibleEvent.entity_type == entity_type,
                BibleEvent.entity_id == entity_id,
            )
        )
        if field is not None:
            stmt = stmt.where(BibleEvent.field == field)
        stmt = stmt.order_by(BibleEvent.created_at.desc()).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [BibleEventDTO.model_validate(r, from_attributes=True) for r in rows]
```

### Pattern 4: KNOWN_PRONOUN_TERMS + KINSHIP_RECIPROCAL Gap Fill (D-86, D-90)

**What:** A new `KNOWN_PRONOUN_TERMS` constant co-located with `KINSHIP_RECIPROCAL` in `reconcile.py`.
**When to use:** Surfaced via `/api/pronouns`; powers the combo dropdown in the SPA.

```python
# Source: trezarr/translate/reconcile.py:35-54 (existing KINSHIP_RECIPROCAL)
# ADD to reconcile.py:

# KNOWN_PRONOUN_TERMS — shared vocabulary for the Bible editor combo (D-86)
# Single source of truth: never duplicated in the frontend.
# Split into self_terms and address_terms for gender-aware picker hints.
KNOWN_PRONOUN_TERMS_SELF = [
    "tôi", "con", "em", "anh", "chị", "cháu", "mày", "tao", "bạn",
]
KNOWN_PRONOUN_TERMS_ADDRESS = [
    "bạn", "anh", "chị", "em", "con", "cháu", "ông", "bà", "bố", "mẹ",
    "cha", "mày", "thầy", "dì", "cậu", "bác", "chú", "cô",
]

# D-90: KINSHIP_RECIPROCAL ADDITIVE FILLS (missing forward + reverse keys)
# Existing keys (reconcile.py:35-54) are not touched.
# These are the relationships exposed by the editor reciprocal-suggestion UX
# that had no KINSHIP_RECIPROCAL coverage (H1 gap, verified C4):
#   bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày
# Add to KINSHIP_RECIPROCAL dict:
_KINSHIP_RECIPROCAL_ADDITIONS: dict[tuple[str, str], tuple[str, str]] = {
    # uncle/aunt — bác (older than parent) ↔ cháu
    ("bác", "cháu"): ("cháu", "bác"),
    ("cháu", "bác"): ("bác", "cháu"),
    # uncle — chú (younger than parent) ↔ cháu
    ("chú", "cháu"): ("cháu", "chú"),
    ("cháu", "chú"): ("chú", "cháu"),
    # aunt — cô ↔ cháu
    ("cô", "cháu"): ("cháu", "cô"),
    ("cháu", "cô"): ("cô", "cháu"),
    # teacher ↔ student (thầy/em)
    ("thầy", "em"): ("em", "thầy"),
    ("em", "thầy"): ("thầy", "em"),
    # intimate/rude: tao ↔ mày
    ("tao", "mày"): ("mày", "tao"),
    ("mày", "tao"): ("tao", "mày"),
}
# Patch the dict at module load (additive only — existing keys are preserved):
KINSHIP_RECIPROCAL.update(_KINSHIP_RECIPROCAL_ADDITIONS)
```

Note: The planner has discretion over whether to inline these into the dict literal or use the `.update()` patch approach. Either is valid as long as the keys are additive and no existing keys are changed (regression safety).

### Pattern 5: Expose Pronouns via API

```python
# New endpoint in bible.py (or a dedicated pronouns.py router)
# Source: pattern mirrors settings.py GET /api/settings

@router.get("/pronouns")
async def get_pronouns():
    """Return KNOWN_PRONOUN_TERMS and KINSHIP_RECIPROCAL for the Bible editor combo (D-86).

    Single source of truth: the frontend never hard-codes pronoun lists.
    """
    from trezarr.translate.reconcile import (
        KNOWN_PRONOUN_TERMS_SELF,
        KNOWN_PRONOUN_TERMS_ADDRESS,
        KINSHIP_RECIPROCAL,
    )
    return {
        "self_terms": KNOWN_PRONOUN_TERMS_SELF,
        "address_terms": KNOWN_PRONOUN_TERMS_ADDRESS,
        # Serialize tuple keys as "self_term|address_term" strings for JSON
        "kinship_reciprocal": {
            f"{k[0]}|{k[1]}": {"self_term": v[0], "address_term": v[1]}
            for k, v in KINSHIP_RECIPROCAL.items()
        },
    }
```

### Pattern 6: Register CR-02 Alias

**What:** `SeriesDTO.register_value` has `alias="register"` (CR-02). API responses must use `by_alias=True` so the JSON key is `"register"` not `"register_value"`.

```python
# Source: dto.py:69 — register_value: str | None = Field(default=None, alias="register")
# In all Bible route handlers:
return series_bible_dto.model_dump(by_alias=True)  # serializes as "register" not "register_value"
```

The SPA must read `response["register"]` not `response["register_value"]`.

### Pattern 7: React Bible Editor — Component Structure

**What:** Functional-first React pages reusing the Phase-7 SPA shell.
**When to use:** All Bible editor SPA code.

```typescript
// Source: frontend/src/App.tsx (existing route pattern)
// Add to App.tsx:
import BibleList from "./pages/BibleList";
import BibleEditor from "./pages/BibleEditor";
// ...
<Route path="/bible" element={<BibleList />} />
<Route path="/bible/:seriesId" element={<BibleEditor />} />
```

Key component contracts:
- `BibleList.tsx`: `GET /api/series` → table of series with nav to editor
- `BibleEditor.tsx`: `GET /api/series/{id}/bible` → tabbed editor (Characters / Address Map / Terms / Register)
- `LockBadge.tsx`: shows `locked` | `inference` based on `locked_fields` array from DTO
- `PronounCombo.tsx`: dropdown from `/api/pronouns` + "custom…" escape hatch (D-86)
- Field history: `GET /api/series/{id}/bible/{entity_type}/{entity_id}/history` on click

### Pattern 8: Address-Map Edit with Reciprocal Suggestion (D-85)

The edit flow for an AddressMap pair:
1. User opens pair (e.g. John→Mary). UI shows current `self_term`/`address_term` with lock badge.
2. User changes `self_term` to `"anh"`, `address_term` to `"em"`.
3. Client-side: look up `KINSHIP_RECIPROCAL["anh|em"]` → `{self_term: "em", address_term: "anh"}`.
4. UI shows side-by-side panel: "Reciprocal (Mary→John) will be set to em/anh — confirm?"
5. User confirms. PATCH both pairs.
6. If KINSHIP_RECIPROCAL has no entry for the chosen pair, UI shows: "No known reciprocal — set the reverse pair manually."
7. If user locks only the forward direction (John→Mary), the reverse (Mary→John) stays inference-updatable.

On save: call PATCH for the forward pair (with lock=true if user locked); call PATCH for reverse pair only if user confirmed reciprocal suggestion.

### Anti-Patterns to Avoid

- **`merge_inferred` for human edits**: `merge_inferred` raises `TypeError` on `AddressMapDTO` (store.py:1086) and silently skips locked fields (merge.py:84) — both wrong for a human override.
- **`.append()` to `locked_fields`**: JSON column is NOT `MutableList`. In-place mutation is not dirty-tracked. Always reassign: `row.locked_fields = [*row.locked_fields, field]`.
- **Locking a pair with a None term**: `reconcile.py:275` only lets a lock win if both `self_term` and `address_term` are non-None. Block at API layer.
- **Hardcoding pronoun lists in the frontend**: `KNOWN_PRONOUN_TERMS` lives in `reconcile.py` and is exposed via `/api/pronouns`. Never duplicate in TypeScript.
- **Registering the `bible` router after `StaticFiles`**: `StaticFiles(html=True)` matches all remaining paths. The router MUST be `include_router`'d before the mount in `app.py`.
- **Reading `register` via `model_validate(row, from_attributes=True)` without explicit field construction**: Due to CR-02, `load_series_bible` explicitly constructs `SeriesBibleDTO(register_value=row.register, ...)`. New code must follow the same pattern.
- **Exposing SQLA rows from route handlers**: D-39 — `store.py` is the only module that may import SQLAlchemy models. Routes receive and return Pydantic DTOs only.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Transaction atomicity for write+audit | Manual `session.commit()` + separate audit call | `async with session.begin():` owning a single txn | D-32: commit and audit in one txn or audit can be lost |
| Lock detection on entities | Custom lock-check query | `row.locked_fields or []` read from the SQLA row inside the txn | Already on every entity row; `get_locked_fields` accessor in merge.py is the canonical reader |
| Concurrency control for Bible writes | DB-level optimistic concurrency / version column | Per-series `asyncio.Lock` from `worker.get_series_lock(series_id)` | D-61: single uvicorn process; asyncio.Lock is sufficient and already in place |
| Pronoun vocabulary | Frontend hardcoded lists | `KNOWN_PRONOUN_TERMS` in `reconcile.py` via `/api/pronouns` | Single source of truth prevents combo/reciprocity drift |
| Per-field audit trail | Hand-rolled change log | Existing `bible_event` table + `BibleEventDTO` | Phase 4 shipped this; `ix_bible_event_series_entity_time` covers the read |
| ORM dirty detection for JSON columns | Manual `flag_modified()` calls | List reassignment (`row.locked_fields = new_list`) | The JSON column type tracks reassignment; explicit `flag_modified` is needed only if appending in-place (which is the footgun) |
| Browser routing fallback | nginx catch-all | `StaticFiles(directory=..., html=True)` on FastAPI | Already in place — `html=True` returns `index.html` for unknown paths |

**Key insight:** The Phase 4 persistence layer was designed explicitly for this phase. Every "hard" part (lock storage, audit events, merge precedence, propagation) is already built and tested. This phase is wiring the human write path into an already-correct engine.

---

## Runtime State Inventory

This is a greenfield feature addition (new router + new store functions + new SPA pages) with no rename, refactor, or migration. No runtime state needs migration.

**No stored data affected** — `locked_fields` already exists as `[]` on every row. Phase 8 writes non-empty values for the first time; no existing data needs updating.
**No live service config affected** — no external service configuration changes.
**No OS-registered state affected** — no new system-level registrations.
**No secrets/env vars affected** — no new config keys.
**No build artifacts affected** — the Vite SPA build output path (`frontend/dist/`) is unchanged; new pages are compiled into the same build.

---

## Common Pitfalls

### Pitfall 1: JSON Column Dirty-Tracking (D-80 footgun)
**What goes wrong:** Developer appends to `locked_fields` in-place: `row.locked_fields.append("role")`. SQLAlchemy doesn't see the mutation — the column value in the DB stays unchanged silently.
**Why it happens:** `locked_fields` is `Mapped[list[str]] = mapped_column(JSON, ...)` — plain `JSON` type, not `MutableList`. SQLAlchemy only tracks object identity for plain JSON; `.append()` mutates the existing list object without replacing it.
**How to avoid:** Always reassign: `row.locked_fields = [*row.locked_fields, field]` or `row.locked_fields = [f for f in row.locked_fields if f != field]`. The existing code at `store.py:461,554,669` already uses `locked_fields=[]` (constructor assigns, not append) — follow this pattern in all new code.
**Warning signs:** Lock appears set in memory but reads back as empty from DB on next load.

### Pitfall 2: Locking a Pair with a Missing Term (D-87 — the subtlest trap)
**What goes wrong:** User sets `self_term="anh"` but leaves `address_term` empty, then clicks "Lock". The write path sets `locked_fields=["self_term", "address_term"]`. In reconcile, the lock-first branch checks `reconcile.py:275`: `if st is not None and at is not None: resolved_map[pair] = (st, at)` — but `at is None`, so the condition fails. The lock is set but **silently ignored**. The pair reverts to safe-default on the next episode.
**Why it happens:** The non-None guard is in `reconcile.py:275`, not in the store writer. The writer doesn't know about reconcile's requirements.
**How to avoid:** Block locking an AddressMap pair at the API layer when either term is empty/whitespace. Return HTTP 422 with a message: "Both self_term and address_term must be non-empty before locking a pair."
**Warning signs:** User reports "locked pair keeps reverting every episode" — first thing to check.

### Pitfall 3: StaticFiles Router Order (Pitfall E from CONTEXT.md)
**What goes wrong:** The `bible` router is registered AFTER the `StaticFiles` mount. `StaticFiles(html=True)` matches `/api/series` as a file path and returns `index.html` with status 200, making every Bible API call appear to succeed but return HTML.
**Why it happens:** FastAPI matches routes in registration order; `StaticFiles` is a catch-all.
**How to avoid:** Add `include_router(bible_router, prefix="/api")` BEFORE the `app.mount("/", StaticFiles(...))` call in `app.py`. The existing pattern in `app.py:279-300` shows all routers registered before the mount.
**Warning signs:** Browser dev tools show Bible API responses with `Content-Type: text/html` and a 200 status.

### Pitfall 4: merge_inferred on AddressMapDTO (Pitfall G from CONTEXT.md)
**What goes wrong:** A developer calls `merge_inferred(session_factory, address_map_dto, {...}, ...)`. `merge_inferred` raises `TypeError: Unsupported entity_dto type: AddressMapDTO` (store.py:1086).
**Why it happens:** `merge_inferred`'s isinstance dispatch only handles `CharacterDTO`, `TermDTO`, `SeriesDTO`.
**How to avoid:** The AddressMap write path must call `apply_human_edit_address_pair` (new function) which mirrors `_upsert_address_pair_in_session`. Never route AddressMap edits through `merge_inferred`.
**Warning signs:** `TypeError` at the store boundary during AddressMap writes.

### Pitfall 5: Series Lock Acquisition Scope
**What goes wrong:** The write endpoint acquires the series lock AFTER starting the store write — or acquires it too late (after the session is opened). A concurrent Pass-1 inference run can interleave.
**Why it happens:** The lock must be held for the duration of the write, including the `session.begin()` block.
**How to avoid:** Acquire `async with get_series_lock(series_id):` as the outermost context manager in the write handler, before any session is opened. The store function runs inside the lock.
**Warning signs:** Under concurrent load (multiple episodes processing while user edits), the lock edit reverts.

### Pitfall 6: Case-Sensitive Term Identity vs. Case-Insensitive Character Identity
**What goes wrong:** Developer assumes terms are case-insensitive like characters. A user edits `"Minh"` → succeeds. A user edits `"minh"` → creates a second character row (no DB UNIQUE constraint).
**Why it happens:** Character identity uses `func.lower()` normalization (store.py:445). Term identity is exact-match (`TermDictionary.source_term == source_term`, store.py:539-541). These are different contracts.
**How to avoid:** ADD path for both must route through the existing `upsert_character` / `upsert_term` wrappers which apply the correct normalization. Never `session.add(Character(...))` or `session.add(TermDictionary(...))` directly.
**Warning signs:** Duplicate character rows with different casing; term edits that appear to not take effect (editing the wrong case variant).

### Pitfall 7: Register Alias CR-02
**What goes wrong:** Route handler calls `series_bible_dto.model_dump()` (no `by_alias=True`). The JSON response contains `"register_value": null` instead of `"register": null`. The React SPA reads `response.register` → undefined.
**Why it happens:** `SeriesBibleDTO.register_value` has `alias="register"` (CR-02). `model_dump()` uses Python field names by default.
**How to avoid:** Always `dto.model_dump(by_alias=True)` for any DTO containing `register_value`. Alternatively, return a FastAPI `JSONResponse` with `content=dto.model_dump(by_alias=True)`.
**Warning signs:** SPA shows Register as empty/undefined even when a value is set.

---

## Code Examples

All examples are sourced from the actual codebase reads in this session.

### Example 1: Session-scoped row re-read inside transaction (WR-01 pattern)
```python
# Source: store.py:366 (_merge_inferred_in_session)
# The canonical re-read pattern — reading off the SQLA row, never the caller's DTO.
fresh_row = await session.get(type(row), row.id)
locked = get_locked_fields(fresh_row)  # read from row, not DTO
# ... setattr on fresh_row ...
```

### Example 2: JSON list reassignment for dirty-tracking (D-80 key constraint)
```python
# Source: D-80 mandate; pattern from store.py constructor sites (:461, :554, :669)
# CORRECT — reassignment triggers dirty-tracking:
row.locked_fields = [*row.locked_fields, field]

# WRONG — in-place mutation NOT dirty-tracked on plain JSON column:
row.locked_fields.append(field)  # NEVER DO THIS
```

### Example 3: _series_locks accessor pattern (worker.py:412-417)
```python
# Source: worker.py:412-417 (_execute_job)
lock = _series_locks.setdefault(
    series_id if series_id is not None else -1,
    asyncio.Lock(),
)
async with lock:
    ...  # D-68: binary ownership per series
```

### Example 4: Router registration pattern (app.py:279-300)
```python
# Source: app.py:279-300
from trezarr.web.routes.bible import router as bible_router
app.include_router(bible_router, prefix="/api")  # BEFORE StaticFiles
# ...
app.mount("/", StaticFiles(directory=_static_dir, html=True), name="spa")
```

### Example 5: reconcile.py lock-first branch (the propagation guarantee)
```python
# Source: reconcile.py:267-277
existing = existing_map.get(pair)
if existing is not None:
    locked = set(existing.locked_fields or [])
    if "self_term" in locked or "address_term" in locked:
        st = existing.self_term
        at = existing.address_term
        if st is not None and at is not None:  # <- THE GUARD (Pitfall 2)
            resolved_map[pair] = (st, at)
            continue  # lock wins — skip transition + confidence gate
```

### Example 6: React client refetch pattern (from Phase-7 pages)
```typescript
// Source: frontend/src/pages/Queue.tsx pattern (Phase-7)
// Bible pages follow the same polling/refetch model:
const [bible, setBible] = useState<SeriesBibleDTO | null>(null);
const [error, setError] = useState<string | null>(null);

useEffect(() => {
  let cancelled = false;
  async function load() {
    try {
      const data = await getSeriesBible(seriesId);
      if (!cancelled) setBible(data);
    } catch (e) {
      if (!cancelled) setError("Failed to load Bible");
    }
  }
  load();
  return () => { cancelled = true; };
}, [seriesId]);
```

### Example 7: AppShell NavItem activation (enable Bible nav item)
```typescript
// Source: frontend/src/components/AppShell.tsx:78-99
// Remove disabled={true} from the Bible NavItem and change the route:
<NavItem
  to="/bible"
  icon={<BookOpen size={16} />}
  label="Bible"
  // disabled prop removed — now a real route
/>
```

### Example 8: DTO boundary enforcement test pattern
```python
# Source: tests/bible/test_dto_boundary.py (existing contract test pattern)
# New Bible routes must pass the same boundary check:
import inspect
import trezarr.web.routes.bible as bible_module

def test_bible_route_does_not_import_sqla():
    """Route module must not import SQLAlchemy models (D-39 boundary)."""
    src = inspect.getsource(bible_module)
    assert "from trezarr.bible.models" not in src
    assert "from sqlalchemy" not in src
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 4: all `locked_fields=[]` hard-coded at insert | Phase 8: `apply_human_edit` sets non-empty `locked_fields` for first time | Phase 8 (this phase) | The lock mechanism becomes production-effective |
| `KINSHIP_RECIPROCAL` missing bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày | D-90: additive fill of missing keys | Phase 8 (H1 fix) | Reciprocal-suggestion UX has full coverage for all relationships exposed in the editor |
| `/bible` route in App.tsx: placeholder div ("will be available in future release") | Phase 8: real BibleList + BibleEditor pages | Phase 8 (this phase) | Bible nav item becomes functional |
| AppShell `Bible` NavItem: `disabled={true}` | Phase 8: `disabled` prop removed | Phase 8 (this phase) | Bible is a real section |

**Deprecated/outdated:**
- `locked_fields=[]` hard-coded in `_upsert_character_in_session`, `_upsert_term_in_session`, `_upsert_address_pair_in_session` — still correct (these are inference paths; only Phase 8's UI path sets non-empty locks).

---

## Assumptions Log

All findings in this document are directly read from the codebase in this session. No assumptions were required.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| (none) | | | |

**All claims in this research were verified by direct codebase read — no user confirmation needed.**

---

## Open Questions

1. **Lock-toggle-without-value-change case (D-80 note)**
   - What we know: D-80 says "decide & document the lock-toggle-without-value-change case explicitly."
   - What's unclear: Should a LOCK-only request (same value, just toggling the lock flag) emit a `BibleEvent`? If yes, what goes in `old_value`/`new_value` (they're the same)?
   - Recommendation: Emit a `BibleEvent(source="lock", old_value=current_value, new_value=current_value, field=field)` to preserve audit completeness. The event's presence signals "user explicitly locked this field." This is cheap and valuable for the history timeline (D-82).

2. **AddressMap writer function shape**
   - What we know: D-80 says `apply_human_edit` / `set_lock` / `clear_lock` (+ AddressMap variant) — planner has discretion.
   - What's unclear: Whether to implement as one function with `lock: bool` or three separate functions.
   - Recommendation: One `apply_human_edit(session_factory, *, entity_type, entity_id, series_id, field, new_value, lock: bool)` plus a dedicated `apply_human_edit_address_pair(...)` (since AddressMap has two fields that must be set together + the non-None-on-lock guard). The AddressMap variant takes `self_term`/`address_term` as a pair, not individual fields.

3. **Series list endpoint — what to return**
   - What we know: D-84 says "Series list" as the entry page.
   - What's unclear: The full Series list is not currently exposed via the existing store API (`get_or_create_series` creates lazily; there's no `load_all_series`).
   - Recommendation: Add a `load_all_series(session_factory) -> list[SeriesDTO]` store function that does `select(Series).order_by(Series.id)`. Simple, consistent with existing patterns.

---

## Environment Availability

Phase 8 has no new external dependencies. All tools are confirmed present from Phase 7.

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| Python 3.12 | Backend runtime | ✓ | Confirmed operational (Phase 7 complete) |
| SQLite + aiosqlite | Bible store | ✓ | Migrations run to 0002 head |
| FastAPI 0.136.x | REST router | ✓ | Phase 7 app.py in production |
| React 19 + Vite 7 | SPA editor | ✓ | Phase 7 frontend fully built |
| pytest + pytest-asyncio | Tests | ✓ | asyncio_mode=auto in pyproject.toml |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (asyncio_mode=auto) |
| Config file | `pyproject.toml` (asyncio_mode = "auto") |
| Quick run command | `uv run pytest tests/bible/test_human_edit.py tests/web/test_bible_api.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| BIBLE-08 criterion 1 | GET /api/series returns all series | integration | `pytest tests/web/test_bible_api.py::test_get_series_list` | Wave 0 gap |
| BIBLE-08 criterion 1 | GET /api/series/{id}/bible returns full Bible with characters/address_map/terms/register | integration | `pytest tests/web/test_bible_api.py::test_get_series_bible` | Wave 0 gap |
| BIBLE-08 criterion 1 | locked_fields visible in DTO response (locked/inference provenance) | unit | `pytest tests/bible/test_human_edit.py::test_lock_state_in_dto` | Wave 0 gap |
| BIBLE-08 criterion 2 | edit→lock: locked field survives a contradicting Pass-1 merge_inferred call | integration | `pytest tests/bible/test_human_edit.py::test_locked_field_survives_merge` | Wave 0 gap — critical |
| BIBLE-08 criterion 2 | Locking AddressMap with missing term returns HTTP 422 | integration | `pytest tests/web/test_bible_api.py::test_lock_address_map_missing_term_rejected` | Wave 0 gap — Pitfall 2 |
| BIBLE-08 criterion 2 | JSON dirty-tracking: locked_fields persisted correctly (not silently lost) | unit | `pytest tests/bible/test_human_edit.py::test_locked_fields_persisted` | Wave 0 gap — Pitfall 1 |
| BIBLE-08 criterion 2 | apply_human_edit emits BibleEvent(source="lock") in same transaction | unit | `pytest tests/bible/test_human_edit.py::test_bible_event_emitted_on_lock` | Wave 0 gap |
| BIBLE-09 criterion 3 | edit→lock→re-analyze: locked pair survives reconcile_attributions | integration | `pytest tests/bible/test_human_edit.py::test_locked_pair_survives_reconcile` | Wave 0 gap — key criterion |
| BIBLE-09 criterion 3 | edit→lock→next episode: locked pair still applied (BIBLE-06 carry-forward + lock combo) | integration | `pytest tests/bible/test_human_edit.py::test_locked_pair_propagates_to_next_episode` | Wave 0 gap — two-episode scenario |
| D-90 H1 fix | Junior-only attribution on bác/cháu does NOT overwrite a locked bác/cháu pair | unit | `pytest tests/translate/test_reconcile.py::test_kinship_reciprocal_bac_chau` | Wave 0 gap — regression test |
| D-81 | Per-series lock: UI write during Pass-1 inference does not interleave | integration | `pytest tests/web/test_bible_api.py::test_write_acquires_series_lock` | Wave 0 gap |
| D-82 | GET history endpoint returns BibleEventDTOs for an entity | integration | `pytest tests/web/test_bible_api.py::test_get_field_history` | Wave 0 gap |
| D-39 boundary | bible route module does not import SQLAlchemy models | unit | `pytest tests/bible/test_dto_boundary.py::test_bible_route_does_not_import_sqla` | Wave 0 gap |

### Test Fixture Strategy

Tests for BIBLE-08 criterion 2 and BIBLE-09 criterion 3 require:
1. A `session_factory` fixture from `tests/db/conftest.py` (already exists — temp-file SQLite + Alembic migration).
2. A `tests/bible/conftest.py` re-export (already exists).
3. A new `tests/bible/test_human_edit.py` test file (Wave 0 gap).
4. A new `tests/web/test_bible_api.py` test file (Wave 0 gap).

**Criterion 3 test pattern** (edit→lock→next episode→still applied):
```python
# tests/bible/test_human_edit.py
async def test_locked_pair_propagates_to_next_episode(session_factory):
    """BIBLE-09: a locked AddressMap pair applied in episode N survives
    reconcile_attributions for episode N+1 without reverting.

    Scenario:
    1. Create series + two characters + address pair (self=anh, address=em)
    2. Lock the pair via apply_human_edit_address_pair(lock=True)
    3. Call reconcile_attributions for episode N+1 with ZERO attributions
       (simulates "no witness in this episode")
    4. Assert pair is still (anh, em) in resolved_map — lock won
    """
    # ... uses session_factory from conftest; real reconcile_attributions call
```

**Criterion 2 test pattern** (lock survives re-analysis):
```python
async def test_locked_field_survives_merge(session_factory):
    """BIBLE-08 criterion 2: a human-locked Character field is not overwritten
    by a subsequent merge_inferred call with a contradicting value.
    """
    # 1. Create character with gender="male"
    # 2. Lock gender="male" via apply_human_edit_character
    # 3. Call merge_inferred with {"gender": "female"}
    # 4. Assert character.gender is still "male"
```

### Sampling Rate
- **Per task commit:** `uv run pytest tests/bible/test_human_edit.py tests/web/test_bible_api.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/bible/test_human_edit.py` — covers BIBLE-08 criterion 2 (locked field survives merge; BibleEvent emitted; JSON dirty-tracking; locked pair survives reconcile; locked pair propagates)
- [ ] `tests/web/test_bible_api.py` — covers BIBLE-08 criterion 1 (series list; full Bible read; history); BIBLE-08 criterion 2 (missing term rejected; series lock acquired); D-39 boundary
- [ ] `tests/translate/test_reconcile.py` additions — covers D-90 H1 fix regression (bác/cháu, chú/cháu, etc.)

No new framework installation needed. `tests/bible/conftest.py` (re-exports `session_factory` from `tests/db/conftest.py`) already covers the store tests.

---

## Security Domain

`security_enforcement: true` and `security_asvs_level: 1` in `.planning/config.json`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Single-user/no-auth (D-78); trusted-LAN deployment |
| V3 Session Management | No | No session — stateless REST |
| V4 Access Control | No | Single-user deployment; no role differentiation |
| V5 Input Validation | Yes | `entity_type` enum validation; field name whitelist (`MERGEABLE_FIELDS`); non-None guard for locked pairs |
| V6 Cryptography | No | No crypto operations in this phase |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Arbitrary entity_type in write endpoint | Tampering | Validate entity_type against allowlist (character / term_dictionary / series / address_map) before calling store |
| Arbitrary field name in write endpoint | Tampering | Validate field against `MERGEABLE_FIELDS[entity_type]` (already exists in store.py:267-291) |
| Oversized `new_value` in write body | Denial of Service | Cap string fields at a reasonable length (e.g. 512 chars for pronoun terms, 1024 for names/renderings) |
| Path traversal via series_id / entity_id | Elevation of Privilege | Use integer IDs only; SQLAlchemy parameterized queries already prevent injection |
| History endpoint returning unbounded rows | DoS | `LIMIT 100` on `load_field_history`; the `list_series` endpoint should `LIMIT 500` |
| Foreign-key orphan via address-pair add with non-existent character_id | Tampering | SQLite FK enforcement + character existence check before insert (D-83: use `upsert_address_pair` which requires existing character IDs) |

The existing `MERGEABLE_FIELDS` whitelist at `store.py:259-264` is the primary defense for field-name injection. The write endpoint must pass `field` through this validation before any store call.

---

## Sources

### Primary (HIGH confidence — direct codebase reads)

- `trezarr/bible/store.py` — all store functions, patterns, and invariants read directly. Lines cited: :172, :189-246, :267-291, :298-402, :405-502, :504-598, :601-717, :779-952, :1007-1023, :1026-1121
- `trezarr/bible/models.py` — entity models, `locked_fields` JSON columns, `BibleEvent` schema. Lines cited: :85, :117, :126, :154, :185, :221-264
- `trezarr/bible/dto.py` — all DTOs including `register_value` alias (CR-02). Lines cited: :69, :175-203, :206-243
- `trezarr/bible/merge.py` — `get_locked_fields`, `compute_field_changes`, lock precedence. Lines cited: :30-46, :49-90
- `trezarr/translate/reconcile.py` — `KINSHIP_RECIPROCAL`, `KNOWN_PRONOUN_TERMS` gap (H1), lock-first branch. Lines cited: :35-54, :267-277, :353-358
- `trezarr/web/app.py` — lifespan, router registration order, `StaticFiles` mount. Lines cited: :270-316
- `trezarr/web/worker.py` — `_series_locks` dict, `setdefault` acquire pattern. Lines cited: :51, :412-417
- `trezarr/web/routes/queue.py` — `_get_session_factory` pattern, `APIRouter` usage. Lines cited: :46-52
- `trezarr/web/routes/settings.py` — GET/PUT editable resource pattern. Lines cited: :55-121
- `frontend/src/App.tsx` — existing routes + `/bible` placeholder. Full file.
- `frontend/src/api/client.ts` — existing typed fetch wrappers + interface pattern. Full file.
- `frontend/src/components/AppShell.tsx` — NavItem pattern, disabled prop. Full file.
- `frontend/src/components/Toast.tsx` — ToastState, variant types. Full file.
- `frontend/src/components/StatusBadge.tsx` — badge pattern to adapt for lock state. Full file.
- `frontend/src/components/MaskedSecretInput.tsx` — combo input pattern for PronounCombo. Full file.
- `tests/db/conftest.py` — `db_engine` + `session_factory` fixtures. Full file.
- `tests/bible/conftest.py` — re-export pattern. Full file.
- `tests/bible/test_address_map.py` — test helper pattern (`_create_series`, `_create_characters`). Lines cited: :22-80.
- `alembic/versions/0002_job_queue.py` — `down_revision = "0001"` chain pattern for `0003_*`.
- `.planning/config.json` — `nyquist_validation: true`, `security_enforcement: true`.
- `08-CONTEXT.md` — all D-79 through D-90 decisions, canonical refs, code_context, specifics.

### Secondary (MEDIUM confidence)

- `.planning/REQUIREMENTS.md` — BIBLE-08, BIBLE-09 requirement text.
- `.planning/STATE.md` — project decision ledger context.
- `.planning/phases/04-series-bible-store-schema/04-CONTEXT.md` — D-32, D-34, D-39 lock semantics origin.

---

## Metadata

**Confidence breakdown:**
- Store write path (D-80): HIGH — entire pattern read directly from existing `_upsert_address_pair_in_session` and `_merge_inferred_in_session`; WR-01/D-32/D-39 invariants all confirmed in code
- Concurrency model (D-81): HIGH — `_series_locks` dict and acquire pattern read from worker.py:51,412-417
- Reconcile propagation (D-89): HIGH — lock-first branch read from reconcile.py:267-277; non-None guard at :275 confirmed
- KINSHIP_RECIPROCAL gaps (D-90): HIGH — table read from reconcile.py:35-54; missing keys identified by inspection
- SPA patterns: HIGH — all components read directly; App.tsx placeholder route confirmed
- Register alias (CR-02): HIGH — alias="register" confirmed in dto.py:69,236; load_series_bible construction pattern confirmed in store.py:227-234

**Research date:** 2026-06-02
**Valid until:** 2026-07-02 (stable internal codebase; no external dependencies)
