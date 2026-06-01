# Phase 4: Series Bible Store & Schema - Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 18 (new + modified + test analogs)
**Analogs found:** 14 strong matches / 4 NEW (no direct analog — use research)

Phase 4 introduces a brand-new persistence stack (SQLAlchemy 2.0 async + aiosqlite + Alembic) and a new `trezarr/db/` + `trezarr/bible/` module tree. Most files are NEW. This map focuses on:

1. **Existing patterns to preserve verbatim** — the `Ledger` interface, `TrezarrSettings` extension idiom, the cli.py startup wiring sequence, and how Phase 3's MediaItem flows into the translate loop.
2. **In-repo idiom analogs for new files** — the `AsyncOpenAI` client lifecycle pattern (closest analog for the SQLAlchemy engine), the `PathMapping` Pydantic BaseModel shape (closest analog for Bible DTOs), and the existing dataclass-based domain models (closest analog for the new SQLAlchemy models).
3. **Test fixture analogs** — the existing async tests (`tests/llm/test_client_concurrency.py`) and tmp_path-driven file tests (`tests/output/test_ledger.py`) for the new `tests/db/conftest.py` and per-test fixtures.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| **MODIFIED** | | | | |
| `trezarr/output/ledger.py` | interface preservation + JSON shim | CRUD | self (existing JSON impl) | exact (interface kept; backend swap doc-only) |
| `trezarr/config.py` | settings extension | config | self (existing grouped sections) | exact |
| `trezarr/cli.py` | startup wiring | request-response orchestration | self (existing 8-step sequence) | exact |
| `trezarr/translate/engine.py` | call-site contract preserved | event-driven | self (lines 421/438/479/520/537) | exact (no changes — regression test only) |
| `trezarr/arr/sonarr.py` (MediaItem extension) | dataclass field addition | data-shape | self (`MediaItem` dataclass) | exact |
| **NEW — db layer** | | | | |
| `trezarr/db/engine.py` | engine + PRAGMA event lifecycle | startup | `trezarr/llm/client.py` (AsyncOpenAI lifecycle) | role-match (async client lifecycle idiom) |
| `trezarr/db/session.py` | session-factory builder | startup | `trezarr/llm/client.py` (factory-from-settings) | role-match |
| `trezarr/db/migration_runner.py` | startup side-effect (migrate + import) | startup | `trezarr/paths.py::probe_media_roots` (startup-time fail-fast) | role-match |
| `trezarr/db/base.py` | DeclarativeBase root | type root | NEW — no analog | RESEARCH Pattern 1 only |
| `trezarr/output/ledger_sqla.py` | SQLA-backed Ledger | CRUD | `trezarr/output/ledger.py` (interface) | exact (interface clone) |
| **NEW — bible layer** | | | | |
| `trezarr/bible/models.py` | SQLAlchemy 2.0 typed models | data-shape | `trezarr/subtitles/model.py` (dataclass domain models) | role-match (domain-shape style) |
| `trezarr/bible/dto.py` | Pydantic DTOs at boundary | data-shape | `trezarr/paths.py::PathMapping` | exact (Pydantic BaseModel for boundary) |
| `trezarr/bible/store.py` | typed public API hiding SQLA | CRUD | `trezarr/output/ledger.py::Ledger` (small typed API hiding storage) | role-match |
| `trezarr/bible/merge.py` | pure-function merge with audit | transform | NEW — no analog | RESEARCH Pattern 3 only |
| **NEW — alembic scaffolding** | | | | |
| `alembic.ini` | migration config | config | NEW — pure scaffolding | RESEARCH Pattern 4 only |
| `alembic/env.py` | migration online/offline runner | startup | NEW — pure scaffolding | RESEARCH Pattern 4 only |
| `alembic/versions/0001_baseline.py` | DDL baseline | migration | NEW — first migration | RESEARCH Pattern 4 only |
| **NEW — tests** | | | | |
| `tests/db/conftest.py` | async DB fixtures | test-setup | `tests/conftest.py` (factory fixture) + `tests/llm/test_client_concurrency.py` (async test shape) | role-match |
| `tests/db/test_engine.py` | PRAGMA verification | unit | `tests/llm/test_client_concurrency.py` (async unit) | role-match |
| `tests/db/test_migrations.py` | migration smoke | integration | `tests/llm/test_client_concurrency.py` + `tests/output/test_ledger.py` (tmp_path) | role-match |
| `tests/db/test_migrate_json_ledger.py` | one-shot import integration | integration | `tests/output/test_ledger.py` (file-based + JSON) | exact |
| `tests/bible/test_models.py` | round-trip unit | unit | `tests/output/test_ledger.py` (record/check round-trip) | role-match |
| `tests/bible/test_store_load.py` | async store API | unit | `tests/llm/test_client_concurrency.py` (async unit) | role-match |
| `tests/bible/test_merge_inferred.py` | invariant assertions | unit | `tests/output/test_ledger.py::test_skip_unchanged` (state precondition + assertion) | role-match |
| `tests/bible/test_lazy_series_create.py` | create-or-fetch idempotency | unit | `tests/output/test_ledger.py::test_ledger_persists_atomically` (write→reload→assert) | role-match |
| `tests/output/test_ledger_sqla.py` | Phase-2 regression suite | regression | `tests/output/test_ledger.py` (verbatim test reuse against new backend) | exact |

---

## Pattern Assignments

### `trezarr/output/ledger.py` (MODIFIED — interface frozen)

**Decision:** Per RESEARCH Pattern 5 (Shape A), the existing JSON `Ledger` class is **retired post-import** in favour of a new `LedgerSQLA(Ledger)` (or sibling) class. The interface contract is what must be preserved verbatim.

**Frozen interface contract** (from `trezarr/output/ledger.py:78-82`):
```python
# Interface contract (swap-compatible with Phase-4 SQLAlchemy backend):
#     ledger.check(source_path) -> LedgerEntry | None
#     ledger.record(entry: LedgerEntry) -> None
#     Ledger.content_hash(source_bytes: bytes) -> str
```

**`LedgerEntry` field shape — frozen and 1:1 with `processed_file` table** (lines 60-68):
```python
@dataclass
class LedgerEntry:
    source_path: str
    output_path: str | None
    status: Literal["done", "quarantined", "in_progress"]
    content_hash: str
    series_id: str | None = None
    source_lang: str | None = None
    episode_key: str | None = None
    translated_at: str | None = None
    quarantine_path: str | None = None
```

**Atomic-write pattern preserved** (lines 173-196 — `_write`'s `NamedTemporaryFile + os.replace` is the canonical mirror for the JSON→SQLite migration's "rename .bak AFTER commit" step):
```python
with tempfile.NamedTemporaryFile(
    mode='w', encoding='utf-8', suffix='.tmp',
    dir=self._path.parent, delete=False,
) as f:
    tmp_path = Path(f.name)
    json.dump({k: asdict(v) for k, v in self._data.items()}, f, indent=2)
os.replace(tmp_path, self._path)
```

**Never-raises load contract** (lines 97-148) — the JSON loader catches `JSONDecodeError`, non-dict top-level, and non-dict per-entry values, logs and skips. The Phase-4 JSON→SQLite migrator must inherit the **same forgiveness policy**: a corrupt ledger file logs and starts SQLite empty rather than crashing the run.

**Key conventions to preserve:**
- `from __future__ import annotations` at top
- Module-level `logger = logging.getLogger(__name__)`
- Module docstring with `Design decisions honoured:` block citing D-numbers
- Field name 1:1 mapping is **load-bearing**: D-20 explicitly chose these names so the SQLAlchemy `processed_file` column names match without translation.

---

### `trezarr/config.py` (MODIFIED — extend, never replace)

**Analog:** Self — the existing per-phase grouped-fields convention.

**Imports pattern** (lines 13-20):
```python
import os
import threading
from typing import Any, Tuple, Type

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource

from trezarr.paths import PathMapping
```

**Phase-grouping convention** (lines 48-115) — every phase appends a `# ── Phase N: <topic> (D-XX) ──` header with the fields it owns:
```python
# ── Phase 2: Output paths (D-18, D-20) ───────────────────────────────────────────────
translate_quarantine_dir: str = "/config/quarantine"
translate_ledger_path: str = "/config/processed_files.json"

# ── Phase 3: *arr connection (D-22) ────────────────────────────────────────
sonarr_host: str = ""
sonarr_port: int = 8989
sonarr_api_key: SecretStr = SecretStr("")
sonarr_enabled: bool = False
```

**Pattern to mirror — Phase 4 additions:**
```python
# ── Phase 4: Series Bible persistence (D-38) ───────────────────────────────
bible_db_url: str = "sqlite+aiosqlite:////config/trezarr.db"
bible_db_run_migrations_on_startup: bool = True  # A4 default
# Optional toggles for SQLite PRAGMAs (default ON per D-38; only flip in tests)
bible_db_enable_wal: bool = True
bible_db_enforce_fk: bool = True
```

**Key conventions to preserve:**
- Fields are flat (no nested settings groups) — env prefix `TREZARR_` + the field name.
- Mutable defaults use `Field(default_factory=...)` not literal `[]` (per 03-REVIEWS.md HIGH #1, see lines 102, 107).
- DB URL is **not** a secret — never wrap in `SecretStr` (the file path is non-sensitive).
- Existing `__init__` + `settings_customise_sources` are NOT touched.

---

### `trezarr/cli.py` (MODIFIED — startup wiring point)

**Analog:** Self — the existing 8-step `_run_once` sequence (lines 103-322).

**Existing startup sequence** (lines 129-201) — preserved structure, Phase 4 inserts new steps between current step 5 (Ledger init) and step 6 (LLMClient construction):
```python
async def _run_once(config_path: str | None) -> int:
    # Step 1 — Load settings + logging
    settings = TrezarrSettings(_yaml_file=config_path) if config_path else TrezarrSettings()
    logging.basicConfig(level=logging.INFO)

    # Step 2 — Startup configuration check (HIGH #2)
    assert_media_roots_configured(settings)

    # Step 3 — Startup probe (D-24, fail-fast)
    media_roots = build_media_roots(settings)
    probe_media_roots(media_roots)

    # Step 4 — Discovery with per-service resilience
    # ... (unchanged)

    # Step 5 — Ledger + scan
    ledger = Ledger(settings.translate_ledger_path)
    eligible, scan_stats = scan_for_eligible_items(...)

    # Step 6 — LLMClient construction (ONLY when there is work to do)
    llm_client: LLMClient | None = None
    if n_eligible > 0:
        llm_client = LLMClient(settings)
```

**Pattern to mirror — Phase 4 insertion (per RESEARCH §Open Question 3 recommendation):**

The DB engine + migrations + ledger import run **AFTER `probe_media_roots` but BEFORE the Ledger construction** so the `Ledger` instance can be the new SQLA-backed one from the start:
```python
# Step 3.5 — DB engine + migrations + JSON-ledger import (NEW Phase 4)
from trezarr.db.engine import build_engine
from trezarr.db.session import build_session_factory
from trezarr.db.migration_runner import run_migrations_to_head, migrate_json_ledger_if_needed
engine = build_engine(settings.bible_db_url)
await run_migrations_to_head(engine)                              # Alembic upgrade head
session_factory = build_session_factory(engine)
await migrate_json_ledger_if_needed(session_factory, settings)    # D-37 one-shot
# Step 5 (modified) — Ledger now SQLA-backed
ledger = LedgerSQLA(session_factory)                              # interface unchanged
```

**Failure-policy pattern** (mirror `probe_media_roots`'s `sys.exit` on hard failure, lines 215-220 in `paths.py`):
- Migration failure → `sys.exit(1)` with a clear actionable message ("Trezarr cannot start — SQLite migration failed at …").
- JSON-ledger import failure → logger.error + start with empty SQLite ledger (Phase-2 corrupt-file forgiveness pattern).

**Key conventions to preserve:**
- `int` return code (never `sys.exit` inside `_run_once` — only `main()` translates).
- Per-step header comment with D-number / WR/HIGH reference.
- Logging at `info` for normal step transitions, `error` for hard failures.
- Engine `dispose()` lifecycle: not needed for the one-shot CLI (process exits), but include a comment noting "Phase 7 daemon will need to call `await engine.dispose()` on shutdown".

---

### `trezarr/translate/engine.py` (MODIFIED — call-site contract is FROZEN)

**Analog:** Self — the existing call sites (lines 421, 438, 479, 520, 537).

**Frozen call-site signatures** (must NOT change — regression test required):
```python
# Line 421 — Ledger check
entry = ledger.check(str(path))

# Line 438 — Record in_progress
ledger.record(LedgerEntry(
    source_path=str(path),
    output_path=str(dest),
    status="in_progress",
    content_hash=content_hash,
))

# Line 537 — Record done
ledger.record(LedgerEntry(
    source_path=str(path),
    output_path=str(output_path),
    status="done",
    content_hash=content_hash,
    translated_at=datetime.now(timezone.utc).isoformat(),
))
```

**Constraint:** Zero changes to this file. If a Phase-4 change forces a signature change here, the swap broke the D-37 contract — STOP and re-design.

**Regression test required:** `tests/output/test_ledger_sqla.py` re-runs the entire `tests/output/test_ledger.py` suite against the SQLA-backed `Ledger`. Existing tests pass unchanged → contract preserved.

---

### `trezarr/arr/sonarr.py` (MODIFIED — extend MediaItem dataclass)

**Analog:** Self — existing `MediaItem` dataclass (lines 49-72).

**Current shape** (lines 49-72) — frozen field names, new fields appended:
```python
@dataclass
class MediaItem:
    local_path: Path
    title: str
    source_type: str
    series_id: int | None = None
    season_number: int | None = None
```

**Pattern to mirror — Phase 4 additions (per RESEARCH §Open Question 1 recommendation: Phase 4 owns the MediaItem extension):**
```python
@dataclass
class MediaItem:
    local_path: Path
    title: str
    source_type: str               # "episode" | "movie"
    series_id: int | None = None
    season_number: int | None = None
    # ── Phase 4: arr_metadata snapshot fields (D-35) ──
    arr_kind: str | None = None              # "sonarr" | "radarr"
    tvdb_id: int | None = None
    tmdb_id: int | None = None
    genres: list[str] | None = None
    overview: str | None = None
    year: int | None = None
    network: str | None = None
    runtime: int | None = None
```

**Population at discovery** (mirror existing pattern at `sonarr.py:158-167` and `radarr.py:158-165`):
```python
# Inside discover_sonarr_items — after raw_path/local_path resolution:
items.append(
    MediaItem(
        local_path=local_path,
        title=series["title"],
        source_type="episode",
        series_id=series["id"],
        season_number=ep_file.get("seasonNumber"),
        # New Phase-4 fields, populated from the already-fetched `series` dict
        arr_kind="sonarr",
        tvdb_id=series.get("tvdbId"),
        genres=series.get("genres"),
        overview=series.get("overview"),
        year=series.get("year"),
        network=series.get("network"),
        runtime=series.get("runtime"),
    )
)
```

**Key conventions to preserve:**
- `@dataclass` (not pydantic BaseModel — the arr layer uses plain dataclasses; pydantic is reserved for config + DTO boundary).
- All new fields default to `None` (additive, never breaks existing constructors).
- Field naming follows the *arr API JSON key (e.g. `tvdbId` → `tvdb_id`; standard Python snake_case).
- Per LOW #17 in 03-REVIEWS.md: title is generic (`title`, not `series_title`) so Radarr movies share the same shape.

---

### `trezarr/db/engine.py` (NEW — engine + PRAGMA lifecycle)

**Closest analog:** `trezarr/llm/client.py` — the `LLMClient.__init__` pattern of building a single async client from `TrezarrSettings` at startup, with critical reliability knobs (max_retries, semaphore) bound at construction.

**Imports pattern to mirror** (from `llm/client.py:17-27`):
```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)
```

**Construction pattern** (mirror `LLMClient.__init__` at `llm/client.py:40-57` — factory-from-settings with the critical-knob inline):
```python
def build_engine(settings: "TrezarrSettings") -> AsyncEngine:
    """Build the AsyncEngine + register PRAGMA event listener (D-38).

    PRAGMAs are set via event.listens_for(engine.sync_engine, "connect") because
    foreign_keys is per-connection (Pitfall 4 in RESEARCH). journal_mode=WAL is
    file-persistent but harmless to re-issue.
    """
    engine = create_async_engine(settings.bible_db_url, echo=False, future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        if settings.bible_db_enable_wal:
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        if settings.bible_db_enforce_fk:
            cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
```

**Key conventions to preserve:**
- Module docstring opens with `"""<one-liner>.\n\nDesign decisions honoured:\n  D-38  ...\n"""` mirroring `llm/client.py:1-15`.
- One construct-from-settings function (NOT a class with state) — the engine itself is the state-bearing object.
- Per-line `# D-XX` comments on each load-bearing line (PRAGMA listener, FK enforcement).
- Type-only imports from `trezarr.config` go inside `if TYPE_CHECKING:` block (matches `llm/client.py:26-27` and `arr/sonarr.py:34-35`).

---

### `trezarr/db/session.py` (NEW — session factory)

**Closest analog:** `trezarr/llm/client.py` — the same factory-from-engine idiom (the LLM client builds `self._semaphore = asyncio.Semaphore(...)` from settings; here we build the sessionmaker from the engine).

**Pattern to mirror:**
```python
"""async_sessionmaker factory + session-per-transaction helper (D-38, D-39).

Design decisions honoured:
  D-38  async_sessionmaker bound to AsyncEngine; expire_on_commit=False
        (Pitfall 2 in RESEARCH — default True deadlocks async post-commit).
  D-39  Sessions never cross the bible/store.py boundary — callers receive
        Pydantic DTOs only.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the per-app async_sessionmaker factory.

    expire_on_commit=False is mandatory — see RESEARCH Pitfall 2.
    """
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
```

**Key conventions to preserve:**
- One factory function returning the typed sessionmaker.
- Mandatory `expire_on_commit=False` with an inline comment pointing at RESEARCH Pitfall 2.

---

### `trezarr/db/migration_runner.py` (NEW — startup side-effect)

**Closest analog:** `trezarr/paths.py::probe_media_roots` (lines 171-220) — startup-time fail-fast pattern with `sys.exit` on hard failure, accumulating errors before exit, and an actionable error message.

**Failure-policy pattern to mirror** (from `paths.py:215-220`):
```python
if errors:
    sys.exit(
        "ERROR: Trezarr cannot start — unreadable media root(s):\n"
        + "\n".join(errors)
        + "\nVerify your path_mappings and volume mounts match the *arr stack."
    )
```

**Atomic ledger-import pattern to mirror** (from `ledger.py:173-196` — temp file + `os.replace` for the rename step):
```python
# Phase 4 equivalent: rename JSON→.migrated.bak only AFTER the SQLite txn commits.
# This is RESEARCH Pitfall 5: "Commit FIRST, rename SECOND".
async def migrate_json_ledger_if_needed(session_factory, settings) -> None:
    """One-shot JSON→SQLite migration (D-37).

    Idempotent: short-circuits if .migrated.bak already exists. On corrupt JSON,
    logs loudly and starts SQLite empty (mirrors ledger.py:_load forgiveness).
    """
    json_path = Path(settings.translate_ledger_path)
    bak_path = Path(str(json_path) + ".migrated.bak")
    if not json_path.exists() or bak_path.exists():
        return  # idempotent no-op

    # Read + parse JSON (forgiveness — mirrors ledger.py:_load)
    try:
        raw = json.loads(json_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Ledger %s unreadable (%s) — starting SQLite empty", json_path, exc)
        return
    if not isinstance(raw, dict):
        logger.warning("Ledger %s wrong shape — starting SQLite empty", json_path)
        return

    # One transaction for all INSERTs (D-37 step 1-3)
    async with session_factory() as session:
        async with session.begin():
            for k, v in raw.items():
                if not isinstance(v, dict):
                    logger.warning("entry %r malformed — skipping", k)
                    continue
                # ... INSERT into processed_file with collision-skip ...

    # Rename AFTER commit (Pitfall 5: never reverse this order)
    os.replace(json_path, bak_path)
    logger.info("Migrated JSON ledger → SQLite; %s renamed to %s", json_path, bak_path)
```

**Alembic programmatic-upgrade pattern** — RESEARCH Pattern 4 (no in-repo analog; copy verbatim).

**Key conventions to preserve:**
- Logger at module level: `logger = logging.getLogger(__name__)`.
- `logger.warning(...)` for forgiveness-path skips (mirrors `ledger.py:117`).
- `logger.info(...)` for the happy-path "migrated N entries" line.
- Bake the `os.replace` rename **after** commit and inside the same function so the ordering is obvious to reviewers.

---

### `trezarr/db/base.py` (NEW — DeclarativeBase root)

**No in-repo analog.** Use RESEARCH Pattern 1 / State of the Art table (line 706-708):

```python
"""Shared SQLAlchemy 2.0 DeclarativeBase root for all Bible models.

All trezarr.bible.models classes inherit from Base. env.py imports
trezarr.bible.models (and through it, Base) so MetaData is populated before
Alembic autogenerate runs (Pitfall 8 in RESEARCH).
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root DeclarativeBase for all Trezarr SQLAlchemy 2.0 models."""
```

**Key conventions:** docstring mirrors the `Design decisions honoured:` style of other modules; pinpoints which RESEARCH pitfall the import-order requirement protects against.

---

### `trezarr/output/ledger_sqla.py` (NEW — SQLA-backed Ledger)

**Closest analog:** `trezarr/output/ledger.py::Ledger` — the existing JSON impl is the verbatim interface spec.

**Interface contract to clone verbatim** (from `ledger.py:78-82`):
```python
class LedgerSQLA:
    """SQLAlchemy-backed idempotency ledger for processed subtitle files (D-37).

    Interface contract (identical to Phase-2 trezarr.output.ledger.Ledger):
        ledger.check(source_path) -> LedgerEntry | None
        ledger.record(entry: LedgerEntry) -> None
        Ledger.content_hash(source_bytes: bytes) -> str  # @staticmethod, reused
    """

    def __init__(self, session_factory: "async_sessionmaker[AsyncSession]") -> None:
        self._session_factory = session_factory

    def check(self, source_path: str | Path) -> LedgerEntry | None:
        # synchronous facade — see "Async/sync impedance" below
        ...

    def record(self, entry: LedgerEntry) -> None:
        ...

    @staticmethod
    def content_hash(source_bytes: bytes) -> str:
        return hashlib.sha256(source_bytes).hexdigest()[:16]  # identical to ledger.py:212
```

**Async/sync impedance — the load-bearing detail:**
`trezarr/translate/engine.py` currently calls `ledger.check(...)` and `ledger.record(...)` **synchronously** (lines 421, 438, 479, 520, 537). These call sites are FROZEN (per `translate/engine.py:1-19` and CONTEXT.md). Two options:

| Option | Approach | Trade-off |
|--------|----------|-----------|
| A (preferred) | Sync facade running async via `asyncio.run_coroutine_threadsafe` or `asyncio.get_event_loop().run_until_complete` | Risky inside an existing async caller — `run_until_complete` from inside a running loop raises `RuntimeError` |
| B | Bridge via `asyncio.run_coroutine_threadsafe` using a stored loop handle | Works but adds complexity |
| C | Re-evaluate the "frozen call sites" claim and make `check/record` async | CLEANEST — `engine.py` is already `async def translate_file`, so `await ledger.check(...)` is a trivial change. CONTEXT.md §"Existing code to reuse" says "engine.py call sites should require ZERO changes" — but a `ledger.check` → `await ledger.check` is mechanical and the contract that *matters* is the data shape, not sync-vs-async. |

**Planner decision required:** Confirm with planner whether "zero changes" allows the `await` keyword addition, or whether the sync facade must be implemented. RESEARCH does not pin this; A2 in RESEARCH Open Questions implicitly assumes async-throughout.

**Key conventions to preserve:**
- Same LedgerEntry dataclass (imported from `trezarr.output.ledger` — do NOT redefine).
- `content_hash` is a `@staticmethod` (line 198-212 in original).
- Module docstring opens with the D-numbers honored (D-37, D-38).

---

### `trezarr/bible/models.py` (NEW — SQLAlchemy 2.0 typed models)

**Closest analog (style):** `trezarr/subtitles/model.py` — the existing dataclass-based domain models with rich docstrings explaining each field's role.

**Style to mirror** (from `subtitles/model.py:17-46`):
```python
@dataclass
class SubLine:
    """A single subtitle cue — one timed block of text.

    All fields except ``text`` are immutable by convention: the codec writes them
    back unchanged and the translation pipeline must never touch them.

    Attributes:
        index:    Verbatim index string from the source file (e.g. "5" or "10").
        start_tc: Verbatim start timecode (e.g. "00:00:01,000" or "00:00:01.000").
        end_tc:   Verbatim end timecode (same preservation guarantee as start_tc).
        text:     Cue text including all inline formatting tags.
        raw:      Opaque pass-through of the block's *original* source text.
    """
    index: str
    start_tc: str
    end_tc: str
    text: str
    raw: str | None = None
```

**Pattern to mirror — SQLAlchemy 2.0 typed declarative** (no in-repo analog; copy from RESEARCH State of the Art table line 706-708):
```python
"""SQLAlchemy 2.0 typed declarative models for the Series Bible (D-31, D-32, D-33).

Tables created in the baseline migration:
  - series              — per-series Bible header (D-33 identity, D-35 arr_metadata)
  - character           — Phase 4 read/merge; Phase 5 populates from LLM Pass-1
  - term_dictionary     — Phase 4 read/merge; Phase 5 populates
  - bible_event         — append-only audit log (D-32)
  - processed_file      — JSON-ledger swap target (D-37)
  - address_map         — created EMPTY; Phase 5 populates (BIBLE-03)
  - relationship_event  — created EMPTY; Phase 6 populates (BIBLE-07)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trezarr.db.base import Base


class Series(Base):
    """Per-series Bible header row (one per (arr_kind, arr_instance, arr_series_id))."""

    __tablename__ = "series"
    __table_args__ = (
        UniqueConstraint("arr_kind", "arr_instance", "arr_series_id",
                         name="uq_series_arr_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    arr_kind: Mapped[str]                       # "sonarr" | "radarr"
    arr_instance: Mapped[str]                   # "default" (v1; multi-instance hook for v2)
    arr_series_id: Mapped[int]
    tvdb_id: Mapped[int | None] = mapped_column(default=None)
    tmdb_id: Mapped[int | None] = mapped_column(default=None)
    register: Mapped[str | None] = mapped_column(default=None)   # Phase 5 sets via merge_inferred
    arr_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)   # D-35 snapshot
    locked_fields: Mapped[list[str]] = mapped_column(JSON, default=list)  # D-34

    characters: Mapped[list["Character"]] = relationship(back_populates="series")
    terms: Mapped[list["TermDictionary"]] = relationship(back_populates="series")
```

**Key conventions to preserve:**
- `from __future__ import annotations` at top.
- Rich class-level docstring with `Attributes:` block (mirrors `subtitles/model.py`).
- Per-field inline `# D-XX` comment for load-bearing fields.
- `JSON` columns annotated as `Mapped[dict[...]]` or `Mapped[list[...]]` for type safety.
- `relationship(back_populates=...)` for navigability — use `selectinload()` at the store layer (NEVER `lazy='select'` — RESEARCH "Deprecated" line 716).

---

### `trezarr/bible/dto.py` (NEW — Pydantic DTOs at boundary)

**Closest analog:** `trezarr/paths.py::PathMapping` (lines 43-56) — the only existing Pydantic BaseModel at a module boundary.

**Pattern to mirror exactly** (from `paths.py:43-56`):
```python
class PathMapping(BaseModel):
    """A remote→local path prefix substitution pair (D-23).

    Defined as a pydantic BaseModel (not a dataclass) so pydantic-settings can
    deserialize the JSON array env var `TREZARR_PATH_MAPPINGS` and YAML
    `path_mappings:` lists into a list[PathMapping] field on TrezarrSettings.

    Attributes:
        remote: Prefix as it appears in *arr API-returned paths (e.g. "/tv").
        local:  Corresponding local path in this container / host (e.g. "/data/tv").
    """

    remote: str
    local: str
```

**Pattern to mirror — Phase 4 DTOs:**
```python
"""Pydantic DTOs at the trezarr.bible.store boundary (D-39).

SQLAlchemy models stay inside store.py; everything that crosses out is a DTO.
Field names mirror the SQLAlchemy column names 1:1 so model_validate(row,
from_attributes=True) is a no-op rename.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict


class CharacterDTO(BaseModel):
    """Per-character Bible entry (BIBLE-02)."""

    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 ORM bridge

    id: int
    series_id: int
    original_latin_name: str
    gender: str | None = None
    rough_age: str | None = None
    role: str | None = None
    locked_fields: list[str] = []   # D-34
```

**Key conventions to preserve:**
- BaseModel subclass with `model_config = ConfigDict(from_attributes=True)` (Pydantic v2 ORM bridge — RESEARCH Code Example "Loading a series Bible").
- Field names match SQLA columns 1:1 (no renaming at the boundary — keep cognitive load low).
- Optional fields default to `None` (matching the SQLA `Mapped[X | None]` shape).
- Mutable defaults: `locked_fields: list[str] = []` is acceptable on Pydantic models (Pydantic copies defaults per-instance); compare to `Field(default_factory=list)` rule for `TrezarrSettings` (because pydantic-settings handles env var deserialization differently).
- Module docstring opens with the D-numbers honoured.

---

### `trezarr/bible/store.py` (NEW — Pydantic-typed public API)

**Closest analog:** `trezarr/output/ledger.py::Ledger` — a small typed public API (`check`, `record`, `content_hash`) hiding a storage implementation.

**API-shape pattern to mirror** (from `ledger.py:71-82`):
```python
class Ledger:
    """JSON-backed idempotency ledger for processed subtitle files.

    Interface contract (swap-compatible with Phase-4 SQLAlchemy backend):
        ledger.check(source_path) -> LedgerEntry | None
        ledger.record(entry: LedgerEntry) -> None
        Ledger.content_hash(source_bytes: bytes) -> str
    """
```

**Pattern to mirror — Phase 4 store API (RESEARCH §"Bible read API shape" + D-39):**
```python
"""Series Bible store — Pydantic-typed API hiding SQLAlchemy internals (D-39).

Public API (the ONLY surface Phase 5+ may import):
    load_series_bible(series_id) -> SeriesBibleDTO
    get_character(series_id, name) -> CharacterDTO | None
    get_or_create_series(arr_kind, arr_instance, arr_series_id, ...) -> SeriesDTO
    merge_inferred(entity_dto, inferred, episode_key, source)
        -> tuple[entity_dto, list[BibleEventDTO]]

Internal:
    All SQLAlchemy imports stay inside this module. Sessions are opened with
    `async with session_factory()` and never escape.
"""
```

**merge_inferred atomic-transaction pattern** — RESEARCH Pattern 3 (no in-repo analog; copy verbatim, paying close attention to the `async with session.begin():` context manager that guarantees rollback on `CancelledError`).

**Key conventions to preserve:**
- One module exposes the entire store surface — no sub-modules with their own public APIs.
- Functions take `session_factory` as the first arg (NOT a class with `__init__`) — easier to test with fresh per-test sessionmakers.
- Every public function returns Pydantic DTOs only — SQLA model leakage is a contract violation.
- Module docstring lists the full public API surface and explicitly names the internal/external boundary.

---

### `trezarr/bible/merge.py` (NEW — pure-Python merge policy)

**No in-repo analog.** Use RESEARCH Pattern 3 verbatim. The function lives in its own module (per CONTEXT.md "Claude's Discretion" — "whether `merge_inferred` is a free function or a method on the store") to keep the lock-precedence policy testable in isolation.

**Public API shape:**
```python
"""Pure-Python merge policy with lock precedence: human-lock > prior > inference (D-34).

Phase 4 never sets locked_fields in production — only tests demonstrating that
locks survive contradicting inference. Phase 8's UI is the production setter.
The get_locked_fields() accessor exists so Phase 8 can swap to a parallel
bible_lock table without touching call sites (CONTEXT.md §D-34).
"""
from __future__ import annotations

from typing import Any, Callable


def get_locked_fields(entity_dto) -> frozenset[str]:
    """Read locked_fields off any DTO that carries the convention."""
    return frozenset(getattr(entity_dto, "locked_fields", []))


def compute_field_changes(
    entity_dto,
    inferred: dict[str, Any],
    locked: frozenset[str],
) -> list[tuple[str, Any, Any]]:
    """Return [(field, old, new), ...] for fields that should actually change.

    Skips fields in `locked`; skips no-op fields where inferred == current.
    Pure function — no DB, no side effects. Easy to unit test exhaustively.
    """
    changes: list[tuple[str, Any, Any]] = []
    for field, new_val in inferred.items():
        if field in locked:
            continue
        old_val = getattr(entity_dto, field, None)
        if old_val == new_val:
            continue
        changes.append((field, old_val, new_val))
    return changes
```

The transactional `merge_inferred` lives in `bible/store.py` (needs a session); the **policy** lives here as a pure function so tests can exercise lock precedence and no-op detection without any DB at all.

**Key conventions to preserve:**
- Pure functions only — no SQLAlchemy import, no IO, no async.
- Type hints on every parameter.
- Module docstring explicitly names what's deferred to Phase 8 (lock-setting in production).

---

### `alembic.ini` / `alembic/env.py` / `alembic/versions/0001_baseline.py` (NEW — scaffolding)

**No in-repo analog.** Use RESEARCH Pattern 4 verbatim. Key requirements:

| File | Source |
|------|--------|
| `alembic.ini` | `uv run alembic init alembic` standard template; edit `script_location = alembic`; **delete** `sqlalchemy.url = ...` line (URL is programmatically injected per Pattern 4). |
| `alembic/env.py` | RESEARCH Pattern 4 verbatim — async-aware + render_as_batch=True + `from trezarr.bible import models  # noqa: F401` (Pitfall 8). |
| `alembic/versions/0001_baseline.py` | One migration creating all 7 tables (series / character / term_dictionary / address_map / relationship_event / bible_event / processed_file) per D-31. Hand-written, NOT autogenerate (avoid drift risk on the foundational migration). |

**Key convention:** Migration files are committed to git (the history IS the schema source of truth). The migration filename includes a date prefix for ordering — Alembic's default is `<rev>_<slug>.py` (e.g. `0001_baseline_bible_schema.py`).

---

### Test files — analog patterns

#### `tests/db/conftest.py` (NEW)

**Closest analog (factory shape):** `tests/conftest.py` (lines 18-43) — the existing `settings_factory` fixture.

**Closest analog (async + tmp_path):** RESEARCH Code Examples "Test fixture" (no in-repo analog for `pytest_asyncio.fixture` yet — Phase 1/2/3 tests use plain `async def` driven by `asyncio_mode = "auto"` in `pyproject.toml`).

**Pattern to mirror:**
```python
"""Shared fixtures for trezarr.db.* and trezarr.bible.* tests.

Convention: temp-file SQLite per test (CONTEXT.md preference — exercises the
real Alembic migration each run; not :memory: which breaks Alembic+multi-conn).
"""
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import run_migrations_to_head


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    """Fresh temp-file SQLite + full Alembic migration per test."""
    db_path = tmp_path / "trezarr.db"
    # Build a TrezarrSettings stub with bible_db_url pointed at the temp DB
    from trezarr.config import TrezarrSettings
    settings = TrezarrSettings(
        bible_db_url=f"sqlite+aiosqlite:///{db_path}",
        llm_api_key="test-key",  # required field even though not exercised
    )
    engine = build_engine(settings)
    await run_migrations_to_head(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)
```

**Key conventions to preserve:**
- `pytest_asyncio.fixture` (NOT plain `@pytest.fixture`) — required for async fixtures even with `asyncio_mode = "auto"`.
- Use `tmp_path` for the DB file (CONTEXT.md preference — temp-file over `:memory:`).
- `yield` + `await engine.dispose()` cleanup.
- Pull `bible_db_url` through TrezarrSettings (don't bypass — exercise the config pathway).

#### `tests/output/test_ledger_sqla.py` (NEW — regression)

**Analog:** `tests/output/test_ledger.py` — **the entire file is the spec**. The new file re-runs the same suite against the SQLA backend.

**Pattern to mirror — import-deferral idiom for swap-compat tests** (from `test_ledger.py:21-25`):
```python
def test_skip_unchanged(tmp_path):
    """Ledger.check() returns the entry; matching hash → 'skipped' outcome (ENG-07)."""
    ledger_mod = pytest.importorskip("trezarr.output.ledger_sqla")  # NEW path
    Ledger = ledger_mod.LedgerSQLA                                     # NEW class
    # LedgerEntry is re-exported from ledger.py — no change here
    LedgerEntry = ledger_mod.LedgerEntry                               # or import from .ledger
    ...
```

**Convention:** Every test function from `test_ledger.py` is duplicated here with the same name and the same assertions; only the construction line changes. The whole suite passing IS the contract-preservation proof.

#### `tests/bible/test_merge_inferred.py` (NEW — invariant tests)

**Closest analog:** `tests/output/test_ledger.py::test_skip_unchanged` (lines 21-58) — the "arrange state → invoke → assert" rhythm.

**Pattern to mirror — invariant assertion shape (lock survives contradiction)** from RESEARCH Validation Architecture §"Verify lock survives a contradicting inference" (lines 676-701). Copy verbatim.

**Key conventions:**
- `async def test_...` (no `@pytest.mark.asyncio` — `asyncio_mode="auto"` is configured).
- Use the `session_factory` fixture from `tests/db/conftest.py`.
- One invariant per test (lock-survives / no-op-emits-no-event / atomicity-on-failure).

#### `tests/db/test_migrate_json_ledger.py` (NEW)

**Analog:** `tests/output/test_ledger.py` — file-based + JSON round-trip pattern. Same tmp_path-driven setup, same JSON-file write, same `Ledger(path)` construction; the assertion target swaps from "JSON round-trip" to "JSON dropped, SQLite populated, .migrated.bak exists".

**Pattern to mirror** (from `test_ledger.py:153-184`):
```python
def test_ledger_persists_atomically(tmp_path):
    """After Ledger.record(), the JSON file on disk contains the entry and is valid JSON."""
    # ... write entry, reload from disk, assert
```

Phase 4 equivalent (one of three required tests from RESEARCH Phase Requirements → Test Map):
```python
async def test_one_shot_migration_happy_path(tmp_path, session_factory):
    """JSON ledger with 5 entries → SQLite has 5 rows; JSON renamed to .migrated.bak (D-37)."""
    # arrange: write a 5-entry JSON ledger at tmp_path / "processed_files.json"
    # act: await migrate_json_ledger_if_needed(session_factory, settings)
    # assert: SELECT COUNT(*) FROM processed_file == 5
    # assert: (tmp_path / "processed_files.json").exists() is False
    # assert: (tmp_path / "processed_files.json.migrated.bak").exists() is True
```

---

## Shared Patterns

### Module Docstring Convention

**Source:** Every existing module — `trezarr/output/ledger.py:1-20`, `trezarr/llm/client.py:1-15`, `trezarr/config.py:1-12`, `trezarr/paths.py:1-26`, `trezarr/arr/sonarr.py:1-20`, `trezarr/translate/engine.py:1-20`.

**Apply to:** Every new Phase 4 module (`db/engine.py`, `db/session.py`, `db/migration_runner.py`, `db/base.py`, `bible/models.py`, `bible/dto.py`, `bible/store.py`, `bible/merge.py`, `output/ledger_sqla.py`).

**Shape:**
```python
"""<One-line module purpose>.

Design decisions honoured:
  D-NN  <decision text with module-relevant details>
  D-MM  <next decision>

<Optional: critical-constraints block / pitfalls callout / forward-compat note>
"""
```

### Import Order Convention

**Source:** `trezarr/llm/client.py:17-27`, `trezarr/translate/engine.py:21-46`.

**Pattern:**
```python
from __future__ import annotations  # always first line after docstring

import <stdlib>              # alphabetical
import <stdlib>

from <third-party> import <symbols>  # alphabetical
from <third-party> import <symbols>

from trezarr.<module> import <symbols>  # project — explicit, not wildcards

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings  # type-only — avoids import cycles
```

### Logging Convention

**Source:** Every module — `trezarr/output/ledger.py:33`, `trezarr/llm/client.py` (none — pure compute), `trezarr/translate/engine.py:48`, `trezarr/cli.py:61`, `trezarr/paths.py:40`.

**Pattern:** Module-level `logger = logging.getLogger(__name__)`. Use `logger.warning(...)` for forgiveness-path skips, `logger.error(...)` for hard failures, `logger.info(...)` for normal step transitions, `logger.exception(...)` for unhandled errors (auto-captures traceback per WR-05).

### Failure Policy Convention

**Source:** `trezarr/output/ledger.py:97-148` (forgiveness) + `trezarr/paths.py:171-220` (fail-fast).

**Apply to:**
- Forgiveness (log + continue): JSON-ledger import on corrupt/missing source file (`migration_runner.py`).
- Fail-fast (`sys.exit`): Alembic migration failure on startup (`cli.py` step 3.5).
- Per-item failure isolation (D-30, never abort batch on one item's failure): merge_inferred MUST NOT hold a txn across `await` to other systems (RESEARCH Pitfall 9 / Phase 7 preview).

### Type-Only Import Convention

**Source:** `trezarr/llm/client.py:26-27`, `trezarr/arr/sonarr.py:34-35`, `trezarr/output/ledger.py` (none — leaf module).

**Apply to:** Every new file that needs to reference `TrezarrSettings` type-annotation without forming an import cycle through `config.py`:
```python
if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
```

### Pydantic Boundary Convention

**Source:** `trezarr/paths.py::PathMapping` (lines 43-56) — the only existing Pydantic BaseModel at a module boundary.

**Apply to:** All `trezarr/bible/dto.py` classes.

**Shape:**
```python
class FooDTO(BaseModel):
    """<one-liner> (<D-XX>)."""
    model_config = ConfigDict(from_attributes=True)  # ORM bridge — Pydantic v2 canonical

    # Fields here, matching SQLA column names 1:1
```

### Dataclass Domain-Model Convention

**Source:** `trezarr/subtitles/model.py::SubLine` (lines 17-46) + `trezarr/output/ledger.py::LedgerEntry` (lines 36-68) + `trezarr/arr/sonarr.py::MediaItem` (lines 49-72).

**Apply to:** Anywhere a plain-Python data-shape is needed inside the application (NOT for DB models — those use SQLAlchemy Mapped[T]; NOT for config-boundary — that uses Pydantic). Likely zero new dataclasses in Phase 4 (the bible models are SQLA; the DTOs are Pydantic; LedgerEntry is reused unchanged).

---

## No Analog Found

Files where the codebase has no prior pattern. RESEARCH.md is the sole reference:

| File | Role | Data Flow | RESEARCH Section to Use |
|------|------|-----------|-------------------------|
| `trezarr/db/base.py` | DeclarativeBase root | type-root | RESEARCH State of the Art (line 706-708) |
| `trezarr/bible/models.py` (SQLA 2.0 typed style) | data-shape | data-shape | RESEARCH State of the Art + Code Examples |
| `trezarr/bible/merge.py` (lock-precedence) | transform | transform | RESEARCH Pattern 3 + D-34 |
| `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_baseline.py` | migration | startup | RESEARCH Pattern 4 verbatim |
| `migrate_json_ledger_if_needed()` two-phase commit | startup side-effect | batch | RESEARCH Pitfall 5 — commit FIRST, rename SECOND |

---

## Metadata

**Analog search scope:** `trezarr/**/*.py` and `tests/**/*.py`.
**Files scanned:** 18 production modules + 8 test files (sampled — full suite is 16 test files).
**Pattern extraction date:** 2026-06-01

**Key insight:** Phase 4 introduces a brand-new stack. The few existing-file modifications (ledger interface preservation, config extension, MediaItem field additions, cli.py startup wiring) have crisp self-analogs. The new modules have no SQLAlchemy/Alembic precedent in this repo — RESEARCH Pattern 1-4 are load-bearing. The discipline that matters most: **mirror the project's module-docstring convention, type-only import idiom, and Pydantic-DTO-at-boundary pattern** so the new modules feel native to the Phase 1-3 codebase even though they are introducing a wholly new dependency tree.

## PATTERN MAPPING COMPLETE
