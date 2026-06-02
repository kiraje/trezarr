# Phase 10: Source Selection & Per-Series Overrides — Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 17 new/modified files
**Analogs found:** 17 / 17

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trezarr/arr/bazarr.py` (NEW) | service | request-response | `trezarr/web/routes/test_connection.py::test_bazarr` + `trezarr/arr/sonarr.py` | exact |
| `trezarr/arr/sonarr.py` (MODIFY) | service | request-response | self (existing MediaItem dataclass + discover pattern) | exact |
| `trezarr/arr/radarr.py` (MODIFY) | service | request-response | `trezarr/arr/radarr.py` (existing movie snapshot pattern) | exact |
| `trezarr/source_selection/__init__.py` (NEW) | config | — | `trezarr/arr/__init__.py` (package init with exports) | role-match |
| `trezarr/source_selection/rank.py` (NEW) | utility | transform | `trezarr/translate/reconcile.py` (pure precedence-function pattern) | role-match |
| `trezarr/source_selection/resolve.py` (NEW) | utility | transform | `trezarr/translate/reconcile.py::reconcile_attributions` | role-match |
| `trezarr/discover/scan.py` (MODIFY) | service | batch | self (existing `find_source_sub` + `scan_for_eligible_items`) | exact |
| `trezarr/discover/gap.py` (MODIFY) | service | request-response | self (existing `is_eligible` Cases 0–5) + `trezarr/output/ledger_sqla.py::check` | exact |
| `trezarr/output/ledger_sqla.py` (MODIFY) | service | CRUD | self (existing `check` method pattern) | exact |
| `trezarr/bible/models.py` (MODIFY) | model | CRUD | self (existing nullable columns: `register`, `tvdb_id`) | exact |
| `trezarr/bible/dto.py` (MODIFY) | model | transform | self (existing `SeriesDTO`/`SeriesBibleDTO` nullable field additions) | exact |
| `trezarr/bible/store.py` (MODIFY) | service | CRUD | self (`apply_human_edit_series` lock-aware writer) | exact |
| `alembic/versions/0003_per_series_overrides.py` (NEW) | migration | CRUD | `alembic/versions/0002_job_queue.py` | exact |
| `trezarr/llm/client.py` (MODIFY) | service | request-response | self (existing `call()` + `_call_with_fallback`, `self._model`) | exact |
| `trezarr/translate/engine.py` (MODIFY) | service | batch | self (existing `_translate_batch_inner` + `translate_file` signature) | exact |
| `trezarr/web/routes/bible.py` (MODIFY) | route | request-response | self (`patch_series_register` — the register PATCH handler) | exact |
| `frontend/src/pages/BibleEditor.tsx` (MODIFY) | component | event-driven | self (`RegisterSection` + tab-switch pattern + `SectionCard`/`TextField`) | exact |
| `frontend/src/api/client.ts` (MODIFY) | utility | request-response | self (`patchRegister` wrapper pattern + `SeriesBibleDTO` interface) | exact |

---

## Pattern Assignments

### `trezarr/arr/bazarr.py` (NEW — service, request-response)

**Primary analog:** `trezarr/web/routes/test_connection.py` lines 172–214 (httpx + X-Api-Key Bazarr call shape)
**Secondary analog:** `trezarr/arr/sonarr.py` lines 1–225 (client-build + DiscoveryError-wrapping + MediaItem pattern)
**Tertiary analog:** `trezarr/arr/__init__.py` lines 1–83 (`_normalize_arr_host` + `DiscoveryError`)

**Imports pattern** (`trezarr/arr/__init__.py` lines 15–19, `trezarr/arr/sonarr.py` lines 15–38):
```python
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
import httpx
from trezarr.arr import DiscoveryError, _normalize_arr_host
from trezarr.paths import apply_path_mapping
if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
```

**Error type pattern** (`trezarr/arr/__init__.py` lines 22–29):
```python
class BazarrError(Exception):
    """Raised when a Bazarr inventory call fails (mirrors DiscoveryError)."""
```

**Client-build pattern — SecretStr at boundary** (`trezarr/arr/sonarr.py` lines 102–125):
```python
def build_sonarr_client(settings: "TrezarrSettings") -> Sonarr:
    host = _normalize_arr_host(settings.sonarr_host)
    return Sonarr(
        host=host,
        api_key=settings.sonarr_api_key.get_secret_value(),  # D-11: resolved ONLY here
        port=settings.sonarr_port,
        ...
    )
```
Replicate for BazarrClient `__init__`:
```python
self._api_key = settings.bazarr_api_key.get_secret_value()  # D-11: resolved ONLY here
self._base_url = f"http://{_normalize_arr_host(settings.bazarr_host)}:{settings.bazarr_port}"
```

**httpx + X-Api-Key call shape** (`trezarr/web/routes/test_connection.py` lines 197–213):
```python
url = f"http://{_normalize_arr_host(body.host)}:{body.port}/api/system/status"
async with httpx.AsyncClient(timeout=5.0) as client:
    r = await client.get(url, headers={"X-Api-Key": api_key})
# Error wrapping:
except httpx.RequestError as exc:
    display_host = _normalize_arr_host(body.host)
    error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
    logger.warning("Bazarr connection test failed at %s:%d — %s", display_host, body.port, error_msg)
```
For the inventory client, wrap in `BazarrError` instead of returning JSONResponse:
```python
try:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(url, params=[("seriesid[]", sonarr_series_id)],
                              headers={"X-API-KEY": self._api_key})
    r.raise_for_status()
    data = r.json().get("data", [])
    return [_parse_inventory_item(ep) for ep in data]
except httpx.RequestError as exc:
    display_host = _normalize_arr_host(self._host)
    raise BazarrError(
        f"Bazarr inventory fetch failed at {display_host}: {type(exc).__name__}: {exc}"
    ) from exc
except httpx.HTTPStatusError as exc:
    display_host = _normalize_arr_host(self._host)
    raise BazarrError(
        f"Bazarr inventory HTTP {exc.response.status_code} at {display_host}"
    ) from exc
```

**DiscoveryError log-then-raise pattern** (`trezarr/arr/sonarr.py` lines 205–225):
```python
except PyarrError as exc:
    display_host = _normalize_arr_host(settings.sonarr_host)  # WR-01: strip credentials
    logger.error(
        "Sonarr discovery failed at %s:%d — %s: %s",
        display_host, settings.sonarr_port, type(exc).__name__, exc,
    )
    raise DiscoveryError(
        f"Sonarr discovery failed at {display_host}:{settings.sonarr_port}: "
        f"{type(exc).__name__}: {exc}"
    ) from exc
```

**CRITICAL pitfall:** Bazarr array query param must use list-of-tuples syntax:
```python
params=[("seriesid[]", sonarr_series_id)]   # CORRECT — httpx encodes as ?seriesid%5B%5D=N
params={"seriesid[]": sonarr_series_id}     # WRONG  — httpx encodes as ?seriesid%5B%5D=N but works
# Both work but list-of-tuples is explicit for multi-value arrays
```

---

### `trezarr/arr/sonarr.py` + `trezarr/arr/radarr.py` (MODIFY — add `original_language`)

**Analog:** `trezarr/arr/sonarr.py` lines 52–99 (MediaItem dataclass + D-35 snapshot fields)

**MediaItem `original_language` field addition** (after `runtime: int | None = None` at line 99):
```python
# ── Phase 10: original_language capture (D-108) ──
original_language: str | None = None  # e.g. "Korean", "English" — from arr originalLanguage.name
```

**Sonarr capture pattern** (`trezarr/arr/sonarr.py` lines 192–203 — the D-35 snapshot block):
```python
# ── Phase 4: arr_metadata snapshot fields (D-33, D-35) ──
arr_kind="sonarr",
tvdb_id=series.get("tvdbId"),    # camelCase JSON key from Sonarr API
genres=series.get("genres"),
overview=series.get("overview"),
year=series.get("year"),
network=series.get("network"),
runtime=series.get("runtime"),
# tmdb_id intentionally omitted for Sonarr (defaults to None — D-33)
```
Add after `runtime=series.get("runtime")`:
```python
# Phase 10 — D-108: originalLanguage.name for SRC-02 relational-richness ranking
original_language=series.get("originalLanguage", {}).get("name"),
```

**Radarr capture pattern** (`trezarr/arr/radarr.py` lines 164–172):
```python
tmdb_id=movie.get("tmdbId"),
genres=movie.get("genres"),
overview=movie.get("overview"),
year=movie.get("year"),
runtime=movie.get("runtime"),
# network intentionally omitted for Radarr movies (defaults to None — D-35)
```
Add after `runtime`:
```python
original_language=movie.get("originalLanguage", {}).get("name"),
```

**`arr_metadata_snapshot` pass-through** (`trezarr/bible/store.py` lines 104–169): `original_language` is a field on `MediaItem`; the caller assembles `arr_metadata_snapshot` from `MediaItem` fields. Ensure `original_language` is included in that dict (no schema migration needed — `arr_metadata` is already a JSON column, D-35).

---

### `trezarr/source_selection/__init__.py` (NEW — package init)

**Analog:** `trezarr/arr/__init__.py` lines 1–20

```python
"""Trezarr source-language selection layer — relational-fidelity ranking and override resolution."""
from __future__ import annotations
__all__ = ["rank_sources", "resolve_effective_settings"]
```

---

### `trezarr/source_selection/rank.py` (NEW — utility, transform)

**Analog:** Pure function pattern from `trezarr/translate/reconcile.py` (precedence/ranking logic). No specific line excerpt needed — the pattern is: module-level lookup dict + pure function with no I/O.

**Module-level tier table pattern** (mirrors `reconcile.py` KNOWN_PRONOUN_TERMS_SELF / constant dicts):
```python
from __future__ import annotations

_TIER: dict[str, int] = {
    "zh": 1, "cmn": 1, "zho": 1,
    "ko": 1, "kor": 1,
    "ja": 1, "jpn": 1,
    "th": 1, "tha": 1,
    "id": 2, "ind": 2,
    ...
    "en": 3, "eng": 3,
}
_DEFAULT_TIER = 2

_ORIG_LANG_NAME_TO_CODE2 = {
    "english": "en", "korean": "ko", "japanese": "ja", "chinese": "zh",
    "thai": "th", ...
}
```

**Pure ranking function** (designed in RESEARCH.md — no existing analog; copy this exact shape):
```python
def sort_key(lang: str, original_language: str | None) -> float:
    """Lower = more preferred source."""
    t = _TIER.get(lang.lower(), _DEFAULT_TIER)
    if original_language and lang.lower() == original_language.lower():
        if t == 3:      # flat-relational native (e.g. en for US show) → absolute top
            return 0.0
        else:           # rich-relational native (e.g. ko for K-drama) → bonus within tier
            return t - 0.5
    return float(t)

def rank_sources(
    available: list[str],
    original_language: str | None,
) -> list[str]:
    return sorted(
        set(lang.lower() for lang in available),
        key=lambda lang: (sort_key(lang, original_language), lang),
    )

def normalize_original_language(name: str | None) -> str | None:
    if name is None:
        return None
    return _ORIG_LANG_NAME_TO_CODE2.get(name.lower())
```

---

### `trezarr/source_selection/resolve.py` (NEW — utility, transform)

**Analog:** Pure precedence-function pattern (mirrors `reconcile_attributions` from `trezarr/translate/reconcile.py`). No I/O, no ORM imports, fully unit-testable in isolation.

**Imports** (TYPE_CHECKING pattern from `trezarr/arr/sonarr.py` lines 26–38):
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from trezarr.bible.dto import SeriesDTO
    from trezarr.config import TrezarrSettings
```

**Pure resolution function** (designed in RESEARCH.md):
```python
def resolve_effective_settings(
    series_dto: "SeriesDTO | None",
    settings: "TrezarrSettings",
) -> tuple[list[str], str | None, str]:
    """Return (source_priority, register, model) for one series.
    Per-series non-NULL overrides win over global config (D-112).
    """
    if series_dto is None:
        return settings.source_lang_priority, None, settings.llm_model
    source_priority = (
        series_dto.source_lang_override
        if series_dto.source_lang_override is not None
        else settings.source_lang_priority
    )
    register = series_dto.register_value   # alias-aware: Python attr name, not "register"
    model = (
        series_dto.model_override
        if series_dto.model_override is not None
        else settings.llm_model
    )
    return source_priority, register, model
```

**Key:** `series_dto.register_value` (CR-02 alias — the Python attribute is `register_value`, not `register`; see `trezarr/bible/dto.py` line 69).

---

### `trezarr/discover/scan.py` (MODIFY — extend source selection)

**Analog:** self — `trezarr/discover/scan.py` lines 120–319

**EligibleItem additions** (lines 48–76, add `source_upgraded: bool = False`):
```python
@dataclass(frozen=True)
class EligibleItem:
    media_item: Any
    source_sub_path: Path
    reason: str
    source_lang: str
    # Phase 10 additions:
    source_upgraded: bool = False   # True when Case 1.5 triggers (richer source appeared)
```

**ScanStats additions** (lines 77–117, add `source_upgraded: int = 0`):
```python
@dataclass
class ScanStats:
    scanned: int = 0
    no_source: int = 0
    foreign_vi: int = 0
    already_done: int = 0
    error: int = 0
    source_upgraded: int = 0   # Phase 10: Case 1.5 re-translation from richer source
```

**scan_for_eligible_items reason classifier** (lines 278–307): add classifier for new Case 1.5 reason string:
```python
elif "richer source" in reason_lower:
    stats.source_upgraded += 1
    # Do NOT skip — this is eligible
```

**`find_source_sub` signature is unchanged** for the filesystem-glob fallback (D-104). Phase 10 adds a new `select_source_for_item` function that wraps `find_source_sub` with Bazarr inventory + richness ranking.

---

### `trezarr/discover/gap.py` (MODIFY — add Case 1.5 + `check_by_output_path` call)

**Analog:** self — `trezarr/discover/gap.py` lines 40–137

**Case 1 guard** (lines 107–112) becomes Case 1 + Case 1.5:
```python
# Case 1 — foreign vi sidecar (D-26): vi present, ledger has no record.
# Phase 10 extension: first check if Trezarr wrote this vi from a DIFFERENT source.
if vi_path.exists() and entry is None:
    # Case 1.5 (D-110): check if Trezarr wrote this vi path from any source
    prior_entry = await ledger.check_by_output_path(str(vi_path))
    if prior_entry is not None:
        # Trezarr owns this vi (from a different source path) — re-translate from richer source
        logger.info(
            "richer source available for %s (prior source: %s) — re-translating",
            source_sub_path, prior_entry.source_path,
        )
        return (True, "richer source available — re-translating")
    # Original Case 1: truly foreign vi — never clobber (D-26)
    logger.info(
        "foreign vi.srt at %s — skipping %s (D-26, never clobber)",
        vi_path, source_sub_path,
    )
    return (False, f"foreign vi sidecar at {vi_path} — not ours, skipping")
```

**`LedgerProtocol` extension** — add `check_by_output_path` to `trezarr/output/_ledger_protocol.py` as an abstract method so the protocol contract stays correct.

---

### `trezarr/output/ledger_sqla.py` (MODIFY — add `check_by_output_path`)

**Analog:** self — `trezarr/output/ledger_sqla.py` lines 68–86 (`check` method)

**Copy the `check` method pattern** exactly, substituting `source_path` for `output_path`:
```python
async def check_by_output_path(self, output_path: str | Path) -> LedgerEntry | None:
    """Return any ledger entry whose output_path matches — secondary D-110 check.
    Used by gap.is_eligible Case 1.5 to detect Trezarr-owned vi sidecars
    written from a different (lower-priority) source path.
    """
    key = str(output_path)
    async with self._session_factory() as session:
        result = await session.execute(
            select(ProcessedFile).where(ProcessedFile.output_path == key)
        )
        row = result.scalar_one_or_none()
        return _row_to_entry(row) if row is not None else None
```

**Imports** already present (`select`, `ProcessedFile`, `_row_to_entry` — no new imports needed).

---

### `trezarr/bible/models.py` (MODIFY — add override columns to `Series`)

**Analog:** `trezarr/bible/models.py` lines 77–85 (existing nullable columns on `Series`)

**Existing nullable column pattern** (lines 81–85):
```python
tvdb_id: Mapped[int | None] = mapped_column(Integer, default=None)   # D-33: denormalized
tmdb_id: Mapped[int | None] = mapped_column(Integer, default=None)   # D-33: denormalized
register: Mapped[str | None] = mapped_column(String, default=None)   # D-35: Phase 5 sets
arr_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # D-35 snapshot
locked_fields: Mapped[list[str]] = mapped_column(JSON, default=list)      # D-34 callable!
```

**Phase 10 additions** (after `locked_fields` at line 85):
```python
# ── Phase 10: per-series override columns (D-111, migration 0003) ──
source_lang_override: Mapped[list[str] | None] = mapped_column(JSON, default=None)
model_override: Mapped[str | None] = mapped_column(String, default=None)
```

**CRITICAL:** Use `default=None` NOT `default=list` for `source_lang_override`. An empty list `[]` would be truthy-but-empty, silently breaking the `is not None` check in `resolve_effective_settings` (Pitfall 7 in RESEARCH.md).

---

### `trezarr/bible/dto.py` (MODIFY — add override fields to DTOs)

**Analog:** `trezarr/bible/dto.py` lines 35–71 (`SeriesDTO`) and lines 206–243 (`SeriesBibleDTO`)

**Add to `SeriesDTO`** (after `locked_fields: list[str] = []` at line 71):
```python
# Phase 10: per-series override fields (D-111)
source_lang_override: list[str] | None = None
model_override: str | None = None
```

**Add to `SeriesBibleDTO`** (after `locked_fields: list[str] = []` at line 242):
```python
# Phase 10: per-series override fields (D-111)
source_lang_override: list[str] | None = None
model_override: str | None = None
```

**No alias needed** for either field (`register_value` needed an alias because it shadows a Pydantic classmethod; `source_lang_override` and `model_override` do not shadow anything — confirmed in RESEARCH.md).

**`model_config`** already has `populate_by_name=True` and `from_attributes=True` on both DTOs — `model_validate(row, from_attributes=True)` picks up the new columns automatically.

---

### `trezarr/bible/store.py` (MODIFY — add `set_series_overrides` writer)

**Analog:** `trezarr/bible/store.py` lines 1273–1349 (`apply_human_edit_series`)

**New store function** follows the exact same pattern:
```python
async def set_series_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    series_id: int,
    source_lang_override: list[str] | None,  # None = clear override
    model_override: str | None,              # None = clear override
) -> SeriesDTO:
    """Set per-series source-lang and model overrides (D-111, SVC-05).

    NULL = inherit global config. Empty list [] treated as NULL (cleared).
    Emits BibleEvent for audit (D-32). No MERGEABLE_FIELDS check needed —
    these columns are NOT in the merge_inferred pathway; they are override-only.
    """
    async with session_factory() as session:
        async with session.begin():
            row = await session.get(Series, series_id)  # WR-01: re-read in-txn
            if row is None:
                raise ValueError(f"Series {series_id} not found")

            # Normalize empty list to NULL
            src_override = source_lang_override if source_lang_override else None

            row.source_lang_override = src_override
            row.model_override = model_override or None

            # D-32: audit event in the same transaction
            evt = BibleEvent(
                series_id=series_id,
                episode_key=None,
                entity_type="series",
                entity_id=series_id,
                field="overrides",
                old_value=None,
                new_value={"source_lang_override": src_override, "model_override": model_override},
                source="import",  # human edit via UI
            )
            session.add(evt)

        return SeriesDTO.model_validate(row, from_attributes=True)
```

---

### `alembic/versions/0003_per_series_overrides.py` (NEW — migration)

**Analog:** `alembic/versions/0002_job_queue.py` lines 1–96 (migration authoring template)

**Exact structure to copy** (lines 1–30):
```python
"""Add per-series override columns: source_lang_override, model_override (D-111, Phase 10).

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-02
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("series", sa.Column(
        "source_lang_override", sa.JSON, nullable=True, server_default=sa.text("NULL")
    ))
    op.add_column("series", sa.Column(
        "model_override", sa.String, nullable=True, server_default=sa.text("NULL")
    ))

def downgrade() -> None:
    op.drop_column("series", "model_override")
    op.drop_column("series", "source_lang_override")
```

**No indexes needed** (per-series lookup is always by `series.id` — the PK). Reversible as required by D-69/D-37. Migration is applied by the existing `run_migrations_to_head()` call in the startup lifespan.

---

### `trezarr/llm/client.py` (MODIFY — add optional `model` param to `call()`)

**Analog:** self — `trezarr/llm/client.py` lines 59–182

**`call()` signature change** (line 59–63):
```python
# BEFORE:
async def call(
    self,
    messages: list[dict],
    response_model: type[BaseModel] | None = None,
) -> BaseModel | str:

# AFTER:
async def call(
    self,
    messages: list[dict],
    response_model: type[BaseModel] | None = None,
    model: str | None = None,   # D-113: per-call model override; None = use self._model
) -> BaseModel | str:
```

**Inside `_call_with_fallback`** — the `model` parameter must be threaded through. The existing pattern (lines 88–89):
```python
async with self._semaphore:  # D-06: enforce concurrency cap — UNCHANGED
    return await self._call_with_fallback(messages, response_model)
```
Becomes:
```python
async with self._semaphore:
    return await self._call_with_fallback(messages, response_model, model)
```

**`_call_with_fallback`** gains a `model: str | None` param; at the top:
```python
effective_model = model or self._model  # D-113: per-call override, falls back to global
```
All three calls (`parse()` at line 125, `create()` at line 161, `create()` at line 175) change `model=self._model` → `model=effective_model`.

**D-06 invariant:** The `_semaphore` is NOT changed. One semaphore, one client, regardless of which model is used.

---

### `trezarr/translate/engine.py` (MODIFY — thread `model` per call)

**Analog:** self — `trezarr/translate/engine.py` lines 421–489 (`_translate_batch_inner` + `_make_translate_batch_fn`)

**`translate_file` signature** (line 578–585) gains `model: str | None = None`:
```python
async def translate_file(
    path: str | Path,
    settings: "TrezarrSettings",
    llm_client: LLMClient,
    ledger: LedgerProtocol,
    eligible_item: "EligibleItem | None" = None,
    session_factory: "async_sessionmaker[AsyncSession] | None" = None,
    model: str | None = None,   # D-113: per-call model override
) -> TranslationResult:
```

**Threading into LLM calls:** The engine calls `llm_client.call(...)` in `_translate_batch_inner` (line 468) and `analyze_file` / other batch functions. Each call site adds `model=model` to the `llm_client.call()` invocation. The `model` value propagates from `translate_file` → `_make_translate_batch_fn` / `_translate_batch_inner`.

**The key call site** (`trezarr/translate/engine.py` line 468):
```python
# BEFORE:
raw_response = await llm_client.call([{"role": "user", "content": prompt}])
# AFTER:
raw_response = await llm_client.call([{"role": "user", "content": prompt}], model=model)
```

**Register threading** is already handled: `build_translate_prompt` reads `series_bible_dto.register_value` (line 226); the Phase-8 lock mechanism ensures the register is whatever the effective value is. No additional wiring needed.

---

### `trezarr/web/routes/bible.py` (MODIFY — add `PATCH /series/{id}/overrides`)

**Analog:** self — `trezarr/web/routes/bible.py` lines 349–380 (`patch_series_register`)

**Full handler pattern to copy** (lines 349–380):
```python
@router.patch("/series/{series_id}/register")
async def patch_series_register(series_id: int, request: Request) -> JSONResponse:
    body = await request.json()
    # WR-04: reject a missing "value" key rather than silently passing None
    value = body.get("value")
    if value is None:
        raise HTTPException(status_code=422, detail="'value' is required")
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")
    from trezarr.web.worker import get_series_lock  # noqa: PLC0415
    from trezarr.bible.store import apply_human_edit_series  # noqa: PLC0415
    async with get_series_lock(series_id):  # D-81: outermost CM
        try:
            dto, _evt = await apply_human_edit_series(...)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(dto.model_dump(by_alias=True))
```

**New route** — use Pydantic body model (D-39), no inline SQLAlchemy:
```python
from pydantic import BaseModel

class SeriesOverridesRequest(BaseModel):
    source_lang_override: list[str] | None = None  # None = clear override
    model_override: str | None = None              # None = clear override

@router.patch("/series/{series_id}/overrides")
async def patch_series_overrides(
    series_id: int,
    body: SeriesOverridesRequest,
    request: Request,
) -> JSONResponse:
    """PATCH source_lang_override and model_override (D-114, SVC-05)."""
    session_factory = _get_session_factory(request)
    if session_factory is None:
        raise HTTPException(status_code=503, detail="No DB session available")
    from trezarr.web.worker import get_series_lock    # noqa: PLC0415
    from trezarr.bible.store import set_series_overrides  # noqa: PLC0415
    async with get_series_lock(series_id):
        try:
            dto = await set_series_overrides(
                session_factory,
                series_id=series_id,
                source_lang_override=body.source_lang_override,
                model_override=body.model_override,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return JSONResponse(dto.model_dump(by_alias=True))
```

**Validation guard:** `source_lang_override` elements must be 2-letter codes. Add HTTP 422 guard before the store call:
```python
if body.source_lang_override is not None:
    invalid = [c for c in body.source_lang_override if not re.match(r'^[a-z]{2}$', c)]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"source_lang_override contains invalid language codes: {invalid}"
        )
```

---

### `frontend/src/pages/BibleEditor.tsx` (MODIFY — add Overrides tab)

**Analog:** self — `trezarr/frontend/src/pages/BibleEditor.tsx` lines 1936–2055 (`RegisterSection`)

**Tab union type** (line 99):
```typescript
// BEFORE:
type Tab = "characters" | "address_map" | "terms" | "register";
// AFTER:
type Tab = "characters" | "address_map" | "terms" | "register" | "overrides";
```

**Tab array** (lines 195–201):
```typescript
[
  ["characters", "Characters"],
  ["address_map", "Address Map"],
  ["terms", "Terms"],
  ["register", "Register"],
  ["overrides", "Overrides"],   // ADD
] as [Tab, string][]
```

**Tab content block** (lines 247–254 — add after register):
```tsx
{activeTab === "overrides" && (
  <OverridesSection
    seriesId={seriesId}
    bible={bible}
    setBible={setBible}
    showToast={showToast}
  />
)}
```

**`OverridesSection` component** — copy the `RegisterSection` props interface and save flow exactly:
```tsx
interface OverridesSectionProps {
  seriesId: number;
  bible: SeriesBibleDTO;
  setBible: React.Dispatch<React.SetStateAction<SeriesBibleDTO | null>>;
  showToast: (t: Omit<ToastState, "id">) => void;
}

function OverridesSection({ seriesId, bible, setBible, showToast }: OverridesSectionProps) {
  const [sourcePriority, setSourcePriority] = useState<string[]>(bible.source_lang_override ?? []);
  const [modelValue, setModelValue] = useState(bible.model_override ?? "");
  const [saving, setSaving] = useState(false);
  const [globalSettings, setGlobalSettings] = useState<SettingsResponse | null>(null);

  const dirty =
    JSON.stringify(sourcePriority) !== JSON.stringify(bible.source_lang_override ?? []) ||
    modelValue !== (bible.model_override ?? "");

  // Load global settings for provenance badges
  useEffect(() => {
    getSettings().then(setGlobalSettings).catch(() => {/* degrade gracefully */});
  }, []);

  async function handleSave() {
    setSaving(true);
    try {
      await patchSeriesOverrides(seriesId, {
        source_lang_override: sourcePriority.length > 0 ? sourcePriority : null,
        model_override: modelValue.trim() || null,
      });
      setBible((prev) => prev ? {
        ...prev,
        source_lang_override: sourcePriority.length > 0 ? sourcePriority : null,
        model_override: modelValue.trim() || null,
      } : prev);
      showToast({ message: "Overrides saved.", variant: "success" });
    } catch {
      showToast({ message: "Failed to save overrides. Check the server logs.", variant: "error" });
    } finally {
      setSaving(false);
    }
  }
  // ... SourcePriorityEditor, ModelField, RegisterField (inline reduced RegisterSection)
}
```

**`SourcePriorityEditor` local component** — new component, scoped to this file only (not shared). Pattern: chip list with add-input + remove buttons. Chip anatomy from UI-SPEC: `h-7 px-2 gap-2 bg-[#1e293b] text-xs text-text-primary`.

**`SectionCard` and `TextField`** — already exist as local functions in `BibleEditor.tsx` (lines 56–97). Use them directly.

**Register sub-section in `OverridesSection`** — renders an inline reduced `RegisterSection` that calls `patchRegister()` directly (same `client.ts` function the Register tab uses). Does NOT call `patchSeriesOverrides` for register (D-111: register override = Phase-8 lock).

---

### `frontend/src/api/client.ts` (MODIFY — add `patchSeriesOverrides` + extend DTOs)

**Analog:** self — `frontend/src/api/client.ts` lines 309–321 (`patchRegister` wrapper)

**Existing `patchRegister` pattern** (lines 309–321):
```typescript
export async function patchRegister(
  seriesId: number,
  payload: { value: string; lock?: boolean },
): Promise<SeriesListItem> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/register`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`PATCH register: ${resp.status}`);
  return resp.json();
}
```

**New `patchSeriesOverrides` wrapper** (copy structure exactly):
```typescript
export interface SeriesOverridesRequest {
  source_lang_override: string[] | null;
  model_override: string | null;
}

export async function patchSeriesOverrides(
  seriesId: number,
  payload: SeriesOverridesRequest,
): Promise<SeriesBibleDTO> {
  const resp = await fetchWithTimeout(`/api/series/${seriesId}/overrides`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`PATCH overrides: ${resp.status}`);
  return resp.json();
}
```

**DTO extensions** — add to `SeriesListItem` (line 178) and `SeriesBibleDTO` (line 239):
```typescript
// In SeriesListItem:
source_lang_override: string[] | null;
model_override: string | null;

// In SeriesBibleDTO:
source_lang_override: string[] | null;
model_override: string | null;
```

---

## Shared Patterns

### SecretStr at client boundary (D-11)
**Source:** `trezarr/arr/sonarr.py` lines 110–125
**Apply to:** `trezarr/arr/bazarr.py` BazarrClient `__init__`
```python
self._api_key = settings.bazarr_api_key.get_secret_value()  # D-11: resolved ONLY here
```
SecretStr resolved once, stored as plain string on the private `_api_key` attribute, never returned or logged.

### WR-01 credential redaction in error messages
**Source:** `trezarr/arr/sonarr.py` lines 213–225, `trezarr/web/routes/test_connection.py` lines 205–213
**Apply to:** `trezarr/arr/bazarr.py`
```python
display_host = _normalize_arr_host(self._host)  # WR-01: strips user:password@host
raise BazarrError(
    f"Bazarr inventory failed at {display_host}: {type(exc).__name__}: {exc}"
) from exc
```

### D-39 Pydantic-only route boundary
**Source:** `trezarr/web/routes/bible.py` — no direct SQLAlchemy imports at module level; all SQLAlchemy access is via lazy `from trezarr.bible.store import ...` inside handlers
**Apply to:** `trezarr/web/routes/bible.py::patch_series_overrides`
```python
# Top of file: NO from sqlalchemy import ... 
# Inside handler only:
from trezarr.bible.store import set_series_overrides  # noqa: PLC0415
```

### D-81 per-series asyncio.Lock wrapping all write routes
**Source:** `trezarr/web/routes/bible.py` lines 102–103, 369–370
**Apply to:** `patch_series_overrides`
```python
from trezarr.web.worker import get_series_lock  # noqa: PLC0415
async with get_series_lock(series_id):  # D-81: outermost CM
    ...
```

### WR-01 in-txn re-read (store writers)
**Source:** `trezarr/bible/store.py` lines 1311–1316
**Apply to:** `set_series_overrides` in `store.py`
```python
async with session.begin():
    row = await session.get(Series, series_id)  # WR-01: re-read INSIDE the transaction
    if row is None:
        raise ValueError(f"Series {series_id} not found")
```

### D-32 BibleEvent audit in same transaction
**Source:** `trezarr/bible/store.py` lines 1333–1348
**Apply to:** `set_series_overrides`
```python
evt = BibleEvent(
    series_id=series_id, entity_type="series", entity_id=series_id,
    field="overrides", old_value=None, new_value={...}, source="import",
)
session.add(evt)
```

### React save flow with Toast + setSaving pattern
**Source:** `frontend/src/pages/BibleEditor.tsx` lines 1957–1973 (`RegisterSection.handleSave`)
**Apply to:** `OverridesSection.handleSave`
```tsx
async function handleSave() {
  setSaving(true);
  try {
    await patchSeriesOverrides(...);
    setBible((prev) => prev ? { ...prev, ... } : prev);
    showToast({ message: "Overrides saved.", variant: "success" });
  } catch {
    showToast({ message: "Failed to save overrides. Check the server logs.", variant: "error" });
  } finally {
    setSaving(false);
  }
}
```

### `fetchWithTimeout` + error throw pattern
**Source:** `frontend/src/api/client.ts` lines 13–26
**Apply to:** `patchSeriesOverrides` wrapper
```typescript
if (!resp.ok) throw new Error(`PATCH overrides: ${resp.status}`);
```

---

## No Analog Found

All files have close analogs in the codebase. No "no analog" entries.

---

## Metadata

**Analog search scope:** `trezarr/arr/`, `trezarr/bible/`, `trezarr/discover/`, `trezarr/output/`, `trezarr/llm/`, `trezarr/translate/`, `trezarr/web/routes/`, `frontend/src/`, `alembic/versions/`
**Files scanned:** 18 source files read in full or via targeted reads
**Pattern extraction date:** 2026-06-02
