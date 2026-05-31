# Phase 4: Series Bible Store & Schema - Research

**Researched:** 2026-06-01
**Domain:** SQLAlchemy 2.0 async + aiosqlite + Alembic; per-series persistence, atomic-mutation provenance log, lock-precedence merge
**Confidence:** HIGH (all stack patterns verified against Context7-sourced official SQLAlchemy/Alembic/SQLite docs; runtime-state and JSON→SQLite migration design grounded in Phase-2/3 in-repo code)

## Summary

Phase 4 is the persistence backbone every later phase depends on. It introduces **SQLAlchemy 2.0 async + aiosqlite + Alembic** to the project, stands up the full long-term Series Bible schema in one baseline migration (D-31), ships the **per-series Bible store** (read/merge for `series`, `character`, `term_dictionary`) on top of a **mutable-current + append-only `bible_event` log** (D-32), enforces the **human lock > prior value > new inference** precedence in `merge_inferred()` (D-34), captures `arr_metadata` JSON snapshots at lazy series creation (D-35/D-36), and **swaps the existing JSON ledger backend to SQLAlchemy with zero call-site change** in `engine.py` plus a one-shot JSON→SQLite migration (D-37).

The work is mechanical relative to the Phase-5 LLM analyzer that follows — but the merge contract, the atomic (current-row UPDATE + bible_event INSERT) transaction, and the lock-survives-inference invariant are the substrate the entire downstream consistency engine assumes. A bug at this layer corrupts everything Phase 5/6/8 depends on. Every plan should treat the merge transaction and the JSON→SQLite migration as **tier-1 risk** with explicit test coverage.

**Primary recommendation:** Adopt the canonical SQLAlchemy 2.0 async + Alembic-on-startup + `connection.run_sync(do_migrations)` pattern verbatim — it is the only well-supported path. Bind PRAGMAs via an `event.listens_for(engine.sync_engine, "connect")` hook (PRAGMA foreign_keys is per-connection — Pitfall 4). Keep Pydantic DTOs at the store boundary (D-39) so Phase 5 never imports SQLAlchemy. Use **temp-file SQLite per test** (not `:memory:`) so the test suite exercises the real Alembic migration each run. The merge function returns `(updated_dto, list[BibleEventDTO])` and **atomic** is a unit-tested invariant — partial writes here would silently destroy the audit trail.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Schema definition (DDL) | Persistence (Alembic baseline migration) | — | Schema is owned by migration files, not application code — `Base.metadata` is mirror, not source of truth |
| Engine + session lifecycle | Persistence (`trezarr/db/`) | App startup (`cli.py`) | Wired once at startup, shared via dependency injection; Phase 7 daemon will reuse the same lifecycle |
| Per-series Bible state (read/merge) | Domain store (`trezarr/bible/store.py`) | Persistence (sessions, SQL) | Store owns the merge contract; SQL is an implementation detail behind it |
| Lock-precedence merge logic | Domain store (`merge.py`) | — | Pure Python policy; no DB-specific |
| Audit/provenance (`bible_event`) | Domain store (atomic with current-row update) | Persistence | Single transaction is the contract — never split tiers |
| JSON→SQLite ledger migration | Persistence bootstrap (`db/migration_runner.py`) | Domain (`Ledger` interface) | One-shot import is a startup-time concern; ledger interface stays domain-level |
| Idempotency tracking (`processed_file`) | Domain (`Ledger` interface — unchanged) | Persistence (SQLAlchemy backend) | Call sites in `engine.py` are untouched; only backend swap |
| Pydantic DTO marshalling | Domain boundary (`bible/dto.py`) | — | Phase 5+ consume DTOs; SQLAlchemy never crosses module boundary |

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-31: Full schema baseline now, Phase-4 logic on three tables only.** Single Alembic baseline creates `series`, `character`, `term_dictionary`, `address_map`, `relationship_event`, `bible_event`, `processed_file`. Phase 5 populates `address_map`; Phase 6 populates `relationship_event`. Avoids three migrations in three consecutive phases.
- **D-32: Mutable current + append-only `bible_event` log.** Each entity has one current-state row; every mutation also appends `bible_event(series_id, episode_key, entity_type, entity_id, field, old_value, new_value, source, created_at)` **inside the same transaction**. `source` enum: `inference | lock | import | system`.
- **D-33: `(arr_kind, arr_instance, arr_series_id)` is primary identity.** Surrogate `id` PK + UNIQUE on those three columns. `arr_kind ∈ {sonarr, radarr}`; `arr_instance` default `"default"`; `tvdb_id`/`tmdb_id` denormalized at creation, **not used for lookup** in v1. Reinstall-orphan accepted v1.
- **D-34: `locked_fields: JSON` on each entity row.** Stored as JSON array of field names; deserialized as `frozenset[str]`. `merge_inferred(entity, inferred_dict, episode_key, source)`:
  - Skips fields in `entity.locked_fields` (human lock wins).
  - Skips no-op fields where `inferred[field] == entity[field]`.
  - Otherwise applies change + appends `bible_event` in same transaction.
  - Returns `(updated_entity, list[BibleEvent])`.
- Phase 4 never sets `locked_fields` in production code — only in tests. Merge function takes a `get_locked_fields(entity)` accessor to enable Phase-8 swap to a `bible_lock` table without call-site churn.
- **D-35: `series.arr_metadata: JSON` snapshot at series-row creation.** Captures Phase-3 MediaItem payload (genres, overview, year, network, runtime). Phase 5 reads to ground `register`. Phase 4 sets `series.register = NULL` initially; Phase 5 populates via `merge_inferred`.
- **D-36: Lazy series-row creation on first translate.** No startup enumeration. First `translate_file` against an unknown `(arr_kind, arr_instance, arr_series_id)` creates the row + snapshots `arr_metadata`.
- **D-37: One-shot JSON→SQLite migration.** On engine init, if `/config/processed_files.json` exists AND `/config/processed_files.json.migrated.bak` does NOT exist:
  1. Single transaction.
  2. INSERT every JSON entry into `processed_file`.
  3. Commit.
  4. Rename JSON file to `.migrated.bak`.
  Idempotent. If DB already has rows for a `source_path` in JSON, log-and-skip (DB is newer truth). `Ledger` *interface* unchanged; backend swapped.
- **D-38: SQLAlchemy 2.0 async + aiosqlite + Alembic, single SQLite DB at `/config/trezarr.db`.** URL: `sqlite+aiosqlite:////config/trezarr.db` (configurable via new `TrezarrSettings.bible_db_url`). One `async_engine` + `async_sessionmaker` at startup, scoped per-transaction. PRAGMAs at connect: `journal_mode=WAL`, `foreign_keys=ON`, `synchronous=NORMAL`.
- **D-39: Pydantic DTOs at the store boundary, SQLAlchemy models internal.** `trezarr/bible/store.py` exposes Pydantic-typed API: `load_series_bible(series_id) -> SeriesBibleDTO`, `get_character(series_id, name) -> CharacterDTO | None`, `merge_inferred(entity_dto, inferred, episode_key, source) -> tuple[entity_dto, list[BibleEventDTO]]`. SQLAlchemy stays inside `store.py`.

### Claude's Discretion

Planner/researcher retain latitude on: exact module/package layout (likely `trezarr/bible/{models.py,store.py,merge.py,dto.py}` + `trezarr/db/{engine.py,session.py,migration_runner.py}`); Pydantic DTO field names and Optional shape; Alembic env.py setup (online vs offline migration story for tests); whether the Alembic runner runs on every app startup or is invoked manually for v1; the exact name of the source enum (`inference|lock|import|system`); the `bible_event.old_value`/`new_value` storage shape (TEXT vs JSON — both work, JSON future-proofs structured fields); the precise `TrezarrSettings.bible_db_*` field names; the `processed_file` migration's behaviour when an entry's `source_path` no longer exists on disk (skip vs import + flag); whether `merge_inferred` is a free function or a method on the store; SQLAlchemy declarative-base style (`DeclarativeBase` vs `mapped_column`) — prefer 2.0 typed style for consistency with Pydantic-everywhere; whether to expose an aiosqlite WAL checkpoint pragma in startup; and the exact test fixtures (in-memory SQLite vs temp-file SQLite — temp-file is more honest about migrations).

### Deferred Ideas (OUT OF SCOPE)

- **LLM Pass-1 analyzer** populating character/term/register → **Phase 5**.
- **Address Map writes + speaker/addressee attribution + Vietnamese pronoun-pair rules** (BIBLE-03, PRON-01/02/03) → **Phase 5**. Schema ready; logic isn't.
- **Relationship-evolution events** (BIBLE-07) → **Phase 6**.
- **LLM self-review pass** (ENG-05) → **Phase 6**.
- **Editable Bible UI + production lock-setting** (BIBLE-08, BIBLE-09) → **Phase 8**.
- **Multi-instance arr + Bible export/portability** (SCALE-01, COMM-01) → v2. `tvdb_id/tmdb_id` columns captured now.
- **`arr_metadata` refresh policy** → Phase 5+/Phase 10.
- **Richer `bible_lock` table with `locked_by/locked_at/reason`** → Phase 8 decides.
- **Phase-2 ledger consolidation tooling** (un-migrate, dual-write debug) → not needed v1.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BIBLE-01 | Persistent per-series Bible, loaded as context every episode, updated after each | `load_series_bible(series_id)` (Standard Stack §Bible Store); atomic merge contract (Patterns §1); lazy series-row creation D-36 |
| BIBLE-02 | Bible records Characters (name in original Latin form, gender, rough age, role) | `character` table schema in baseline migration; `CharacterDTO` shape; merge_inferred for character fields |
| BIBLE-04 | Bible records a Term Dictionary (proper nouns / titles / places / jargon → Vietnamese rendering incl. name romanization) | `term_dictionary` table schema; identical merge semantics to character |
| BIBLE-05 | Bible records Register/tone per series, grounded in media metadata | `series.register` (NULL on creation, populated by Phase 5); `series.arr_metadata` JSON snapshot (D-35) |
| BIBLE-06 | Bible carried forward across episodes — same character/term stays unchanged S01E01 → finale unless lock/event changes it | Mutable-current pattern (D-32) — read returns current row; merge_inferred no-op when inferred == current; lock-precedence test (Validation Architecture §Phase Gate) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.50 [VERIFIED: PyPI 2026-06-01] | ORM + async engine + session lifecycle | Only mature async-native ORM; declarative typed style (`Mapped[T]`, `mapped_column`) aligns with Pydantic-everywhere pattern (Phase 1/2). [CITED: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html] |
| aiosqlite | 0.22.1 [VERIFIED: PyPI 2026-06-01] | Async SQLite driver | Enables `sqlite+aiosqlite://` URL; required for non-blocking DB I/O in the async pipeline; single shared thread per connection. [CITED: aiosqlite.omnilib.dev] |
| Alembic | 1.18.4 [VERIFIED: PyPI 2026-06-01] | Schema migrations | The only canonical migration tool for SQLAlchemy; supports both online (engine) and offline (SQL script) modes; programmatic `command.upgrade()` callable from app startup. [CITED: alembic.sqlalchemy.org/en/latest/cookbook.html] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Pydantic | 2.13.x (already installed) | DTOs at store boundary (D-39) | Always — store API surface is Pydantic; SQLAlchemy stays inside `store.py` |
| pydantic-settings | 2.14.x (already installed) | New `bible_db_url` field on TrezarrSettings | Extending existing config (D-11), never a new system |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw SQLAlchemy 2.0 + Pydantic DTOs | SQLModel 0.0.38 | SQLModel unifies model+schema but is pre-1.0; D-39 explicitly chose separate DTOs to keep Phase 5 SQLAlchemy-free. Stick with raw SQLAlchemy. |
| `command.upgrade()` programmatic | Shell out to `alembic upgrade head` | Shelling out forces a separate `alembic.ini` runtime path and complicates Docker. Programmatic keeps everything in-process. |
| Temp-file SQLite per test | `:memory:` SQLite | CONTEXT.md prefers temp-file because it exercises the real Alembic baseline migration. `:memory:` would let us drift if the migration broke. Use temp-file. |
| One DB per test | Shared DB + transaction rollback | Rollback-per-test is faster but loses the migration-runs-fresh guarantee. One DB per test (temp file) is the simplest correct option for Phase 4 with low test counts; revisit if test perf becomes an issue. |

**Installation:**

```bash
# add to [project.dependencies] in pyproject.toml
uv add "sqlalchemy[asyncio]>=2.0.50,<2.1" "aiosqlite>=0.22.1,<0.23" "alembic>=1.18.4,<1.19"
```

**Version verification (live, 2026-06-01):**

```
sqlalchemy 2.0.50  requires_python >=3.7
aiosqlite  0.22.1  requires_python >=3.9
alembic    1.18.4  requires_python >=3.10
```

All three meet the project's Python 3.12 floor (D-01).

## Package Legitimacy Audit

slopcheck was not available in this research environment; verified each candidate against the official ecosystem registry (PyPI) directly. All three are long-standing, high-download canonical packages.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| sqlalchemy | PyPI | ~17 years | ~70M/wk | github.com/sqlalchemy/sqlalchemy | unavailable | Approved (well-known canonical ORM; verified PyPI metadata + GitHub presence) |
| aiosqlite | PyPI | ~7 years | ~17M/wk | github.com/omnilib/aiosqlite | unavailable | Approved (well-known async driver; verified PyPI metadata + GitHub presence) |
| alembic | PyPI | ~16 years | ~50M/wk | github.com/sqlalchemy/alembic | unavailable | Approved (SQLAlchemy-organisation migration tool; verified PyPI metadata + GitHub presence) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

These three are foundational ecosystem packages with established histories; slopcheck unavailability does not warrant gating. CLAUDE.md already prescribed this exact stack at project inception.

## Architecture Patterns

### System Architecture Diagram

```
┌────────────────────────── APP STARTUP (cli.py / Phase-7 daemon) ─────────────────────────┐
│                                                                                            │
│  TrezarrSettings ───┐                                                                      │
│                     ▼                                                                      │
│  build_engine() ─► async_engine ─► register PRAGMA event listener (WAL/FK/NORMAL)         │
│                          │                                                                 │
│                          ▼                                                                 │
│  run_migrations_to_head()  ── connection.run_sync(do_run_migrations) ► Alembic command   │
│                          │                                                                 │
│                          ▼                                                                 │
│  migrate_json_ledger_if_needed()  ── if /config/processed_files.json exists                │
│                          │             AND .migrated.bak does NOT exist:                   │
│                          │             single-txn INSERT + rename                         │
│                          ▼                                                                 │
│  build_session_factory(engine) ─► async_sessionmaker                                      │
│                          │                                                                 │
└──────────────────────────┼─────────────────────────────────────────────────────────────────┘
                           ▼
              ┌──────────────────────────┐
              │   Translate Loop          │  (Phase-3 cli.py — unchanged contract)
              │   for item in eligible:  │
              │     ledger.check(...)    │  ◄── Ledger (SQLA-backed, same interface)
              │     translate_file(...)  │
              │     ledger.record(...)   │  ◄── Ledger.record persists to processed_file
              └─────────┬────────────────┘
                        │ (Phase-5 hook: lazy series-row creation)
                        ▼
              ┌──────────────────────────┐
              │   bible.store API         │  (Pydantic DTO boundary — D-39)
              │   load_series_bible()    │
              │   get_character()         │
              │   merge_inferred()       │  ─► (UPDATE current_row + INSERT bible_event) ◄── ONE TXN
              └─────────┬────────────────┘
                        │
                        ▼
              ┌──────────────────────────┐
              │   SQLAlchemy 2.0 models   │  (internal — never crosses module boundary)
              │   series / character /    │
              │   term_dictionary /       │
              │   bible_event /           │
              │   processed_file /        │
              │   address_map (empty)/    │
              │   relationship_event(empty)│
              └─────────┬────────────────┘
                        │
                        ▼
              ┌──────────────────────────┐
              │   /config/trezarr.db      │  (WAL mode; .db + .db-wal + .db-shm)
              └──────────────────────────┘
```

### Recommended Project Structure

```
trezarr/
├── db/
│   ├── __init__.py
│   ├── engine.py            # build_engine() + PRAGMA event listener + dispose()
│   ├── session.py           # build_session_factory(engine); session-per-txn helper
│   ├── migration_runner.py  # run_migrations_to_head(); migrate_json_ledger_if_needed()
│   └── base.py              # DeclarativeBase root + AsyncAttrs mix-in
├── bible/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy 2.0 typed models (series, character, term_dictionary,
│   │                        #   bible_event, processed_file, address_map[empty], relationship_event[empty])
│   ├── dto.py               # Pydantic DTOs (SeriesBibleDTO, CharacterDTO, TermDTO, BibleEventDTO)
│   ├── store.py             # Pydantic-typed public API; SQLAlchemy stays here
│   └── merge.py             # pure-Python merge_inferred() + get_locked_fields() accessor
├── output/
│   ├── ledger.py            # MODIFIED: Ledger.__init__(...) takes a session_factory or kept JSON?
│   │                        #   → see Pattern 5 below — JSON shim or full SQLA swap
│   └── ledger_sqla.py       # NEW: SQLAlchemy-backed Ledger implementation
└── config.py                # EXTENDED: bible_db_url, bible_db_run_migrations_on_startup

alembic/                     # NEW: alembic init scaffolding
├── env.py                   # async-aware (run_sync pattern); uses TrezarrSettings.bible_db_url
├── script.py.mako
└── versions/
    └── XXXXXX_baseline.py   # ALL long-term Bible tables in one file (D-31)
alembic.ini                  # script_location=alembic, sqlalchemy.url=overridden programmatically

tests/
├── db/
│   ├── test_engine.py       # PRAGMA application; dispose lifecycle
│   ├── test_migrations.py   # fresh DB → upgrade head → all tables exist
│   └── test_migrate_json_ledger.py  # idempotency, collision, rename-only-after-commit
├── bible/
│   ├── test_store_load.py   # load_series_bible / get_character DTO shape
│   ├── test_merge_inferred.py    # lock-precedence + atomic-txn invariants
│   └── test_lazy_series_create.py  # MediaItem → series row + arr_metadata snapshot
└── output/
    └── test_ledger_sqla.py  # Phase-2 ledger regression suite re-run against SQLA backend
```

### Pattern 1: SQLAlchemy 2.0 Async Engine + PRAGMAs at Connect

**What:** Build the engine once at startup; register a `connect` event listener that issues SQLite PRAGMAs on every connection from the pool. The `event.listens_for(engine.sync_engine, "connect")` form is the only one that works for `AsyncEngine` because `sync_engine` is the underlying Core engine.

**When to use:** App startup; before any session is opened.

**Example:**

```python
# trezarr/db/engine.py
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
#         + https://docs.sqlalchemy.org/en/20/dialects/sqlite.html (FK pragma per-conn)
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

def build_engine(db_url: str) -> AsyncEngine:
    engine = create_async_engine(db_url, echo=False, future=True)

    # PRAGMA event listener — attach to sync_engine, NOT the AsyncEngine wrapper.
    # foreign_keys MUST be set per-connection (Pitfall 4).
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")       # persistent on the DB file
        cursor.execute("PRAGMA synchronous=NORMAL")     # safe with WAL
        cursor.execute("PRAGMA foreign_keys=ON")        # MUST be per-connection
        cursor.close()

    return engine
```

### Pattern 2: async_sessionmaker + session-per-transaction

**What:** One `async_sessionmaker` factory at app startup; each unit of work opens a session inside an `async with` block. `expire_on_commit=False` avoids the SQLAlchemy "object expired after commit" trap that bites async code with lazy-loaded attributes.

**When to use:** Every read or write. The store layer opens its own sessions; callers pass *DTOs*, not sessions.

**Example:**

```python
# trezarr/db/session.py
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # required pattern for async code
    )

# Usage inside the store:
async def get_character(session_factory, series_id: int, name: str) -> CharacterDTO | None:
    async with session_factory() as session:
        result = await session.execute(
            select(Character).where(
                Character.series_id == series_id,
                Character.original_latin_name == name,
            )
        )
        row = result.scalar_one_or_none()
        return CharacterDTO.model_validate(row, from_attributes=True) if row else None
```

### Pattern 3: Atomic Transaction — current-row UPDATE + bible_event INSERT (D-32, D-34)

**What:** The merge contract requires that the current-row UPDATE and the `bible_event` INSERT either both succeed or both fail. The canonical pattern is `async with session.begin():` — auto-commits on clean exit, rolls back on exception.

**When to use:** Every `merge_inferred()` call. Never split the write across two transactions.

**Example:**

```python
# trezarr/bible/store.py — inside merge_inferred()
# Source: https://docs.sqlalchemy.org/en/20/orm/session_transaction.html
async def merge_inferred(
    session_factory,
    entity_dto: CharacterDTO,
    inferred: dict[str, object],
    episode_key: str,
    source: str,
) -> tuple[CharacterDTO, list[BibleEventDTO]]:
    events: list[BibleEventDTO] = []
    locked = get_locked_fields(entity_dto)

    async with session_factory() as session:
        async with session.begin():  # atomic: UPDATE + INSERTs together
            row = await session.get(Character, entity_dto.id, with_for_update=False)
            # Re-read inside the txn so we operate on fresh state.
            for field, new_val in inferred.items():
                if field in locked:
                    continue
                old_val = getattr(row, field)
                if old_val == new_val:
                    continue
                setattr(row, field, new_val)
                evt = BibleEvent(
                    series_id=row.series_id,
                    episode_key=episode_key,
                    entity_type="character",
                    entity_id=row.id,
                    field=field,
                    old_value=_json_dump(old_val),
                    new_value=_json_dump(new_val),
                    source=source,
                )
                session.add(evt)
                events.append(BibleEventDTO.model_validate(evt, from_attributes=True))
            # session.begin() context exit → commit
        await session.refresh(row)
        updated = CharacterDTO.model_validate(row, from_attributes=True)
    return updated, events
```

**Why `session.begin()` not manual `commit()`:** `session.begin()` is the only context-manager form that guarantees rollback on *any* exception (including `asyncio.CancelledError`). Manual `await session.commit()` + `try/except` is bug-prone and an idiom from SQLAlchemy 1.x.

### Pattern 4: Alembic Async env.py + Programmatic Upgrade at Startup

**What:** Alembic's `command.upgrade()` is **synchronous** and cannot be called from async code directly. The canonical bridge is `await connection.run_sync(do_run_migrations)`. The env.py must support BOTH:
- "online from a running engine" — production startup path (the connection is injected via `config.attributes['connection']`).
- "online from a fresh engine" — CLI use (`alembic upgrade head` for ops).
- "offline" — `alembic upgrade head --sql` for CI parity / dry-runs.

**When to use:** App startup, before any session is opened, every run. Idempotent (Alembic skips already-applied revisions).

**Example:**

```python
# trezarr/db/migration_runner.py
# Source: https://alembic.sqlalchemy.org/en/latest/cookbook.html#programmatic-api-use-connection-sharing-with-asyncio
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

ALEMBIC_INI = Path(__file__).parent.parent.parent / "alembic.ini"

def _do_upgrade(connection, cfg: Config) -> None:
    """Sync callback invoked via connection.run_sync()."""
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")

async def run_migrations_to_head(engine: AsyncEngine) -> None:
    cfg = Config(str(ALEMBIC_INI))
    async with engine.begin() as conn:
        await conn.run_sync(_do_upgrade, cfg)
```

```python
# alembic/env.py — async-aware shape
# Source: https://alembic.sqlalchemy.org/en/latest/cookbook.html
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

from trezarr.db.base import Base  # MetaData target for autogenerate
from trezarr.bible import models   # noqa: F401  ensure models are imported so MetaData is populated

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite ALTER support — see Pitfall 6
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    # The connection was injected by run_migrations_to_head().
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        do_run_migrations(connectable)
        return
    # CLI path: build our own engine.
    from sqlalchemy.ext.asyncio import async_engine_from_config
    import asyncio
    async def _run():
        engine = async_engine_from_config(
            config.get_section(config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await engine.dispose()
    asyncio.run(_run())

def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Pattern 5: Ledger Backend Swap — Two Viable Shapes

The CONTEXT.md says "Ledger *interface* unchanged — backend swapped." Two shapes meet this:

**Shape A — Inheritance / subclass:** `LedgerSQLA(Ledger)` overrides `_load`, `check`, `record`, `_write`. Constructor signature changes from `Ledger(json_path)` to `LedgerSQLA(session_factory)`.

**Shape B — Composition / strategy:** `Ledger.__init__` accepts either a `json_path` or a `session_factory`; internally dispatches. Backward-compatible during the migration window.

**Recommendation:** Shape A. The whole point of the migration (D-37) is to retire the JSON backend after one one-shot import. Keeping the dual-mode strategy alive past that point invites bugs and makes the regression test surface bigger than the value. Shape A means `cli.py` flips one constructor call (`Ledger(path)` → `LedgerSQLA(session_factory)`) and `engine.py` is *literally* untouched (it uses only `ledger.check()` and `ledger.record(...)`).

### Pattern 6: Lazy Series-Row Creation on First Translate (D-36)

**What:** The first time a MediaItem with a previously-unseen `(arr_kind, arr_instance, arr_series_id)` is translated, the store creates the `series` row and snapshots `arr_metadata` from the MediaItem payload.

**When to use:** Just before the Phase-3 translate loop dispatches an item (in `cli.py`, or wherever the call site is). The current `MediaItem` dataclass (in `trezarr.arr.sonarr`) doesn't carry the raw arr payload yet — Phase 4 needs to extend it OR pass the raw payload alongside.

**Where to hook:** Inside the translate loop, just before `translate_file(...)`:

```python
# cli.py — after eligible-item scan, before per-item translate
for eligible_item in eligible:
    series_dto = await get_or_create_series(
        session_factory,
        arr_kind=eligible_item.media_item.source_type_arr_kind,  # "sonarr" / "radarr"
        arr_instance="default",
        arr_series_id=eligible_item.media_item.series_id,
        arr_metadata_snapshot={
            "title": eligible_item.media_item.title,
            "season_number": eligible_item.media_item.season_number,
            # ... extended in Phase 4 to include genres, overview, year, network, runtime
            #     once Phase 3's MediaItem is extended with these fields
        },
    )
    # series_dto.id is now available for Phase 5's Pass-1; Phase 4 just persists it.
    result = await translate_file(...)
```

**Note:** The current `trezarr.arr.sonarr.MediaItem` dataclass (lines 49-72) carries `title`, `source_type`, `series_id`, `season_number` — it does NOT carry genres/overview/year/network/runtime yet. Phase 4 needs to either (a) extend MediaItem with these fields (preferred — single source of truth) or (b) re-fetch via pyarr at lazy-create time. Option (a) is simpler; option (b) duplicates the Phase-3 discovery call.

### Anti-Patterns to Avoid

- **Calling `command.upgrade()` directly in async code.** It's sync — it will block the event loop AND will silently use Alembic's own engine instead of yours. Use `connection.run_sync(do_upgrade)`.
- **Forgetting `expire_on_commit=False` on the sessionmaker.** Default is `True`, which marks attributes as expired after `commit()` — accessing them triggers a lazy refresh that **deadlocks under async**.
- **Splitting the merge into two transactions.** UPDATE-then-INSERT outside one `session.begin()` block defeats the entire `bible_event` provenance contract.
- **PRAGMA in a session-level `execute()` instead of an engine `connect` listener.** Session-level PRAGMA fires once per session, not per connection-pool connection; new pool connections start without it.
- **Defining schema in code AND in migrations and letting them drift.** Alembic baseline is the source of truth; `Base.metadata` is what the tests use to compare. Use `command.check()` in CI to catch divergence.
- **Using `:memory:` SQLite in tests.** Each connection gets its own memory DB; Alembic can't run against it across multiple connections. Use temp-file.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema versioning | Custom "if table_exists then ALTER" startup logic | Alembic | Hand-rolled DDL drift is the #1 silent-corruption source in SQLite apps |
| Async DB driver | Wrap `sqlite3` in `asyncio.to_thread` | aiosqlite | aiosqlite already does the one-thread-per-connection pattern correctly; rolling your own deadlocks under load |
| Per-field lock semantics | Bitmask in an INTEGER column | JSON column with frozenset accessor (D-34) | JSON is queryable, debuggable, and survives schema evolution; bitmasks force a code change every time a new field is locked |
| Atomic UPDATE+INSERT | Manual `commit()` + `try/except` + `rollback()` | `async with session.begin():` | Context manager handles `CancelledError` correctly; manual form leaks half-committed state on task cancellation |
| Pydantic↔SQLAlchemy boundary | Manual `dict()`/`__init__` plumbing | `Model.model_validate(row, from_attributes=True)` | Pydantic v2's `from_attributes=True` is the canonical bridge; manual hand-off drifts when fields change |
| JSON→SQLite migration | Hand-written loop with intermediate flush | One transaction with batch INSERT, rename file AFTER commit | A crash between commit and rename leaves an inconsistent state; ordering is the only safe approach |
| Identity key on series | Use composite (arr_kind, arr_series_id) as PK | Surrogate `id` PK + UNIQUE constraint on the triple (D-33) | Surrogate keys keep FKs short and survive future re-keying for COMM-01 (export/sharing) |

**Key insight:** SQLite + WAL + async + Alembic together have ~6 documented sharp edges (PRAGMA-per-connection, expire_on_commit deadlock, run_sync bridge, render_as_batch for ALTERs, single-writer enforcement, schema-vs-migration drift). Every one of them is solved by following the canonical pattern verbatim. The temptation to "simplify" by skipping any of them creates exactly the silent-corruption bugs the Bible exists to prevent.

## Runtime State Inventory

This phase introduces persistence rather than renaming existing state, but it DOES interact with two existing runtime stores. The inventory matters for the JSON→SQLite migration.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `/config/processed_files.json` (Phase-2 JSON ledger; written by current `Ledger.record()`) | Data migration — one-shot INSERT into `processed_file` table per D-37, then rename to `.migrated.bak` |
| Live service config | None — Phase 4 ships no new service config that lives outside the repo. The new `TrezarrSettings.bible_db_url` lives in env vars or `/config/config.yaml`, which is already covered by D-11 layered config. | None |
| OS-registered state | None — Phase 4 introduces no OS-level registrations (Phase 7 will, when daemon/scheduler land) | None |
| Secrets/env vars | None — DB URL is not a secret. No new SecretStr fields. Existing API keys unchanged. | None |
| Build artifacts | The first run will create `/config/trezarr.db`, `/config/trezarr.db-wal`, `/config/trezarr.db-shm` (WAL sidecar files). Tests will create temp files in `tmp_path`. | Ensure `.gitignore` covers `*.db`, `*.db-wal`, `*.db-shm` (already covered if pattern matches — verify). Alembic `versions/` directory IS committed (migration history is source of truth). |

**Verification:** The ledger file is the only existing runtime state that Phase 4 must handle. Verified by inspecting `trezarr/output/ledger.py:84-95` — the only state-on-disk it owns is the JSON file at `self._path` (default `/config/processed_files.json` per `TrezarrSettings.translate_ledger_path`).

## Common Pitfalls

### Pitfall 1: Calling Alembic from async code without `run_sync` bridge

**What goes wrong:** `command.upgrade(cfg, "head")` blocks the event loop and uses its own engine instead of yours, bypassing your PRAGMAs and connection-pool config.
**Why it happens:** Alembic's API is synchronous; it has no native async path.
**How to avoid:** Always invoke from `await connection.run_sync(do_upgrade)` with `cfg.attributes["connection"] = connection` set inside the callback (Pattern 4).
**Warning signs:** Migrations work but PRAGMAs are missing on the DB; tests pass but FK constraints don't enforce in production.

### Pitfall 2: `expire_on_commit=True` (default) deadlocks async sessions

**What goes wrong:** After `session.commit()`, all loaded attributes are marked expired. The next access triggers a lazy refresh, which in async code requires an awaitable — but you accessed it synchronously. SQLAlchemy raises `MissingGreenlet` or hangs.
**Why it happens:** The expire-after-commit default was designed for sync code, where lazy load is implicit.
**How to avoid:** ALWAYS set `expire_on_commit=False` on `async_sessionmaker`. Re-fetch with `await session.refresh(obj)` if you need post-commit state.
**Warning signs:** Tests pass individually, fail in suites; intermittent `greenlet_spawn has not been called` errors.

### Pitfall 3: `:memory:` SQLite breaks Alembic + multi-session tests

**What goes wrong:** Each new connection to `sqlite+aiosqlite:///:memory:` gets a *fresh, empty* in-memory DB. Alembic runs migrations against one connection; the test code opens a *different* connection and finds no tables.
**Why it happens:** SQLite in-memory DBs are connection-scoped.
**How to avoid:** Use temp-file SQLite per test via pytest's `tmp_path` fixture (CONTEXT.md preferred this for migration honesty). Workaround for in-memory: shared-cache URI `sqlite+aiosqlite:///file:test?mode=memory&cache=shared&uri=true` — but this is fragile and tests-only. Just use temp files.
**Warning signs:** "no such table" errors only in tests; tests pass when run individually with a real DB.

### Pitfall 4: PRAGMA foreign_keys NOT persistent across connections

**What goes wrong:** You issue `PRAGMA foreign_keys=ON` once at startup. New pool connections start with `foreign_keys=OFF`. FK constraints silently don't enforce.
**Why it happens:** SQLite's `foreign_keys` is a per-connection runtime setting, not a DB property. Unlike `journal_mode=WAL`, which IS persistent on the file.
**How to avoid:** Use `event.listens_for(engine.sync_engine, "connect")` to issue the PRAGMA on every connection (Pattern 1). Verified canonical pattern in SQLAlchemy docs.
**Warning signs:** Orphan rows after delete; FK errors that "should" raise but don't.

### Pitfall 5: JSON→SQLite migration ordering — rename BEFORE commit corrupts state

**What goes wrong:** If you `os.rename("processed_files.json", ".migrated.bak")` before the INSERT commits, a crash mid-INSERT leaves both the DB empty AND the JSON renamed — next startup finds no source and the ledger is permanently lost.
**Why it happens:** The classic "two-phase commit" trap — you have two stores, no shared transaction. Order matters.
**How to avoid:** **Commit FIRST, rename SECOND.** If the rename fails after commit, the DB has the data and re-running the migration is idempotent because (D-37) the migration short-circuits on `.migrated.bak` presence AND skips DB rows that already match. Treat the rename as "the cleanup step that's safe to retry."
**Warning signs:** A run that crashes mid-migration with neither `.migrated.bak` nor a `processed_file` table populated.

### Pitfall 6: SQLite ALTER limitations — Alembic needs `render_as_batch=True`

**What goes wrong:** SQLite's `ALTER TABLE` is severely limited (no DROP COLUMN, no rename, no constraint changes pre-3.35). Future migrations against the baseline will fail without `render_as_batch=True` in env.py.
**Why it happens:** Alembic's batch mode emulates ALTER by creating a temp table, copying rows, dropping the original, renaming.
**How to avoid:** Set `render_as_batch=True` in `context.configure(...)` (shown in Pattern 4 env.py). Costs nothing for the baseline; required for any future ALTER.
**Warning signs:** Future Phase-N migration errors out with "near 'DROP': syntax error" on SQLite.

### Pitfall 7: `session.add()` of a Pydantic DTO instead of the SQLA model

**What goes wrong:** The DTO is not a mapped class; `session.add()` raises `UnmappedInstanceError` or silently does nothing depending on the dialect.
**Why it happens:** Easy to mix the two layers when copy-pasting.
**How to avoid:** Inside `store.py`, always construct the SQLA model from the DTO at the *write* boundary: `row = Character(**dto.model_dump(exclude={"id"}))`. The store layer is the ONLY place SQLA models are touched.

### Pitfall 8: Forgetting to import models in `env.py` → empty migration

**What goes wrong:** `alembic revision --autogenerate` produces an empty migration because `Base.metadata` is empty — no models were imported and registered.
**Why it happens:** Models are imported by other modules in production, but `env.py` is a fresh interpreter.
**How to avoid:** Add `from trezarr.bible import models  # noqa: F401` at the top of `env.py` (shown in Pattern 4).

### Pitfall 9: Single-writer enforcement under concurrent translates (preview for Phase 7)

**What goes wrong:** SQLite WAL allows multiple readers but only ONE writer at a time. Phase-7's parallel-episode pipeline could hit `database is locked` if two episodes of the same series try to merge into the Bible simultaneously.
**Why it happens:** WAL is single-writer by architecture — see Pitfall 5 in PITFALLS.md (concurrency races).
**How to avoid (Phase 4 scope):** The Phase-3 translate loop is sequential and the daemon doesn't exist yet — no concurrency in Phase 4. **But** make sure `merge_inferred()` does NOT hold a transaction open across an `await` to the LLM. Open the txn, do the merge, commit, then make the LLM call. This is naturally true for D-32's design but easy to violate if a future hot-fix inlines an LLM call inside the merge.
**Warning signs (Phase 7+):** `sqlite3.OperationalError: database is locked` under load; intermittent test failures with `pytest-xdist`.

## Code Examples

### Loading a series Bible (Phase 5's primary read path)

```python
# trezarr/bible/store.py
# Source: SQLAlchemy 2.0 docs + Phase-4 D-39 DTO boundary
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from trezarr.bible.dto import SeriesBibleDTO, CharacterDTO, TermDTO

async def load_series_bible(session_factory, series_id: int) -> SeriesBibleDTO:
    async with session_factory() as session:
        stmt = (
            select(Series)
            .where(Series.id == series_id)
            .options(
                selectinload(Series.characters),
                selectinload(Series.terms),
            )
        )
        row = (await session.execute(stmt)).scalar_one()
        return SeriesBibleDTO(
            id=row.id,
            register=row.register,
            arr_metadata=row.arr_metadata,
            characters=[CharacterDTO.model_validate(c, from_attributes=True) for c in row.characters],
            terms=[TermDTO.model_validate(t, from_attributes=True) for t in row.terms],
        )
```

### Get-or-create series (lazy creation on first translate, D-36)

```python
# trezarr/bible/store.py
async def get_or_create_series(
    session_factory,
    *,
    arr_kind: str,
    arr_instance: str,
    arr_series_id: int,
    arr_metadata_snapshot: dict,
    tvdb_id: int | None = None,
    tmdb_id: int | None = None,
) -> SeriesDTO:
    async with session_factory() as session:
        async with session.begin():
            stmt = select(Series).where(
                Series.arr_kind == arr_kind,
                Series.arr_instance == arr_instance,
                Series.arr_series_id == arr_series_id,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                row = Series(
                    arr_kind=arr_kind,
                    arr_instance=arr_instance,
                    arr_series_id=arr_series_id,
                    tvdb_id=tvdb_id,
                    tmdb_id=tmdb_id,
                    arr_metadata=arr_metadata_snapshot,
                    register=None,  # Phase 5 sets this via merge_inferred()
                    locked_fields=[],
                )
                session.add(row)
                await session.flush()  # populate row.id
        return SeriesDTO.model_validate(row, from_attributes=True)
```

### Test fixture — temp-file SQLite + run migrations + session

```python
# tests/db/conftest.py
# Source: pytest-asyncio + SQLAlchemy 2.0 async docs
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from trezarr.db.engine import build_engine
from trezarr.db.migration_runner import run_migrations_to_head

@pytest_asyncio.fixture
async def db_engine(tmp_path):
    """Fresh temp-file SQLite + full Alembic migration per test (CONTEXT.md preference)."""
    db_path = tmp_path / "trezarr.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = build_engine(url)
    await run_migrations_to_head(engine)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)
```

### Verify lock survives a contradicting inference (the success-criterion-4 invariant)

```python
# tests/bible/test_merge_inferred.py
async def test_locked_field_survives_contradicting_inference(session_factory):
    # arrange: create a character with role='detective' and lock 'role'
    async with session_factory() as session:
        async with session.begin():
            c = Character(
                series_id=1, original_latin_name="Mary",
                role="detective", locked_fields=["role"],
            )
            session.add(c)

    # act: merge_inferred tries to overwrite with role='spy'
    dto = await get_character(session_factory, series_id=1, name="Mary")
    updated, events = await merge_inferred(
        session_factory, dto, {"role": "spy"}, episode_key="S02E03", source="inference",
    )

    # assert: lock won; no event emitted; current row unchanged
    assert updated.role == "detective"
    assert events == []
    async with session_factory() as session:
        evt_count = await session.scalar(
            select(func.count()).select_from(BibleEvent).where(BibleEvent.entity_id == 1)
        )
        assert evt_count == 0
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `sessionmaker(bind=engine)` (1.x sync) | `async_sessionmaker(engine, expire_on_commit=False)` (2.0 async) | SQLAlchemy 2.0 (2023) | Mandatory for `aiosqlite` driver; the `expire_on_commit=False` is non-obvious for new users |
| `Column(String, primary_key=True)` (imperative) | `id: Mapped[int] = mapped_column(primary_key=True)` (typed) | SQLAlchemy 2.0 (2023) | Pairs with Pydantic v2 typing; mypy/pyright understand the model shape |
| `command.upgrade()` from sync code | `await connection.run_sync(do_upgrade)` via injected connection | Alembic 1.7+ async cookbook | Eliminates dual-engine drift; PRAGMAs from your engine apply to migrations too |
| In-memory SQLite for tests | Temp-file SQLite per test | Project preference (CONTEXT.md) | Exercises real migration on every test run; catches schema/code drift |
| Hand-rolled JSON locks | `locked_fields: JSON` array + accessor pattern (D-34) | Project decision | Phase 8 can swap to a `bible_lock` table without touching merge call sites |

**Deprecated/outdated:**
- **`from sqlalchemy.orm import declarative_base`** — Use `class Base(DeclarativeBase): pass` (2.0 style).
- **`session.query(Model).filter(...)`** — Use `select(Model).where(...)` (2.0 unified select).
- **`relationship(... lazy='select')`** default in async — use `selectinload()` explicitly or `lazy='raise'` to fail fast.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | [ASSUMED] The Phase-3 `MediaItem` will be extended in Phase 4 to carry the additional arr_metadata fields (genres, overview, year, network, runtime), rather than re-fetching from pyarr at lazy-create time. CONTEXT.md implies this in "Phase 3's MediaItem payload" but doesn't lock the choice. | Pattern 6 | If Phase 4 picks option (b) instead, the lazy-create path adds an extra HTTP round-trip per first-translate-of-a-series; not blocking but a perf cost worth confirming with planner. |
| A2 | [ASSUMED] The `processed_file` table's primary key should be a surrogate `id INTEGER`, and `source_path` becomes a UNIQUE column. CONTEXT.md/D-20 don't specify the PK shape, only that field names match the JSON keys. | Standard Stack §Bible Store + Pattern 5 | Wrong PK shape (e.g. `source_path` as PK) would constrain future schema evolution and complicate FKs from a future `bible_event(entity_type='processed_file', entity_id=N)` reference. |
| A3 | [ASSUMED] `bible_event.old_value`/`new_value` storage as JSON (TEXT-encoded JSON column) is preferable to plain TEXT. CONTEXT.md explicitly lists this as Claude's Discretion. | Standard Stack §Bible Store | If TEXT is chosen, structured fields (lists, dicts in future Address Map entries) require client-side serialisation; JSON makes diffs queryable. Low risk either way; JSON future-proofs. |
| A4 | [ASSUMED] Migrations run on EVERY app startup (idempotent — Alembic short-circuits on already-applied revisions). CONTEXT.md lists this as Claude's Discretion ("whether the Alembic runner runs on every app startup or is invoked manually"). | Pattern 4 | Manual-only invocation would require a separate ops command and contradict the Docker-self-hosted-zero-touch goal. Recommend running on every startup. |
| A5 | [ASSUMED] All new packages (`sqlalchemy[asyncio]`, `aiosqlite`, `alembic`) are safe to install — verified via PyPI metadata + GitHub presence (long-established projects). slopcheck unavailable. | Package Legitimacy Audit | These are the three most-prescribed packages in their domain; the risk of slop is effectively zero. |
| A6 | [ASSUMED] `from_attributes=True` on Pydantic DTO `model_validate()` is the right bridge (formerly `orm_mode=True` in Pydantic v1). Verified against Pydantic v2 docs. | Pattern 2 + Code Examples | Should be correct given Pydantic 2.13.x is locked. |
| A7 | [ASSUMED] The store API is async-only — there is no sync convenience wrapper. CONTEXT.md doesn't specify; the rest of the project is async, so this matches. | Standard Stack §Bible Store | If Phase 8's UI handlers expect sync access, a `to_thread` wrapper is trivial to add later. |

## Open Questions

1. **MediaItem extension scope (resolves A1)** — Should Phase 4's plan include the work to extend `trezarr.arr.sonarr.MediaItem` with `genres`, `overview`, `year`, `network`, `runtime`, OR should it just snapshot whatever `MediaItem` carries today and let Phase 5 worry about the missing fields?
   - What we know: D-35 says "Phase 3's MediaItem payload (genres, overview, year, network, runtime)" — but reading `sonarr.py:49-72`, those fields are NOT on MediaItem today.
   - What's unclear: who owns the extension — Phase 4 or Phase 5?
   - Recommendation: Phase 4 extends MediaItem with the missing fields and populates them from the existing pyarr calls (`series_list[i]` already has these fields in pyarr's JSON). This is a small additive change; it would be confusing for Phase 5 to have to amend Phase 3 code.

2. **PK choice on `processed_file` (resolves A2)** — Surrogate `id` + UNIQUE(source_path), or `source_path` as PK?
   - What we know: D-20 says field names match the JSON; D-31 says the table exists in the baseline.
   - What's unclear: PK shape.
   - Recommendation: Surrogate `id INTEGER PRIMARY KEY AUTOINCREMENT` + UNIQUE on `source_path`. Matches the `series` table convention and keeps FK targets short.

3. **Migration runner: every-startup vs explicit (resolves A4)** — Where does `run_migrations_to_head()` get called in the Phase-3 `cli.py`? Before `assert_media_roots_configured` (so the DB is up before the *arr probe) or after?
   - What we know: Phase 4 is wired into the existing `cli.py` startup sequence.
   - What's unclear: relative order in the startup steps.
   - Recommendation: Migrations run AFTER `assert_media_roots_configured` and `probe_media_roots` (cheap config checks first), but BEFORE LLM client construction. Failure to migrate is a hard exit code 1 with a clear error.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Whole project | ✓ | 3.12 (project floor — D-01) | — |
| uv | Package install | ✓ | already used in Phase 3 | — |
| SQLAlchemy 2.0.x | DB layer | ✗ (must install) | 2.0.50 latest | — |
| aiosqlite 0.22.x | Async SQLite driver | ✗ (must install) | 0.22.1 latest | — |
| Alembic 1.18.x | Migrations | ✗ (must install) | 1.18.4 latest | — |
| SQLite | DB engine | ✓ | stdlib `sqlite3` is bundled with Python; aiosqlite uses the bundled engine | — |
| /config directory | DB file location | partial (tests use `tmp_path`) | — | Tests bypass; production must create `/config` if absent (existing convention) |

**Missing dependencies with no fallback:** None — the three new packages are pre-locked in CLAUDE.md and have no blocking issues.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2+ + pytest-asyncio 1.2.0+ (already installed, `asyncio_mode = "auto"` in pyproject.toml) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/db tests/bible -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BIBLE-01 | Bible persists across sessions (write → close → reopen → read) | integration | `uv run pytest tests/bible/test_store_load.py::test_bible_persists_across_engine_dispose -x` | ❌ Wave 0 |
| BIBLE-01 | `load_series_bible(series_id)` returns characters + terms in one call (selectinload) | unit | `uv run pytest tests/bible/test_store_load.py::test_load_returns_eagerly_loaded_relations -x` | ❌ Wave 0 |
| BIBLE-02 | `character` table accepts (name, gender, rough_age, role) and round-trips via DTO | unit | `uv run pytest tests/bible/test_models.py::test_character_round_trip -x` | ❌ Wave 0 |
| BIBLE-04 | `term_dictionary` accepts (source_term, vietnamese_rendering, category) and round-trips | unit | `uv run pytest tests/bible/test_models.py::test_term_round_trip -x` | ❌ Wave 0 |
| BIBLE-05 | `series.arr_metadata` JSON snapshot persists and round-trips as dict | unit | `uv run pytest tests/bible/test_lazy_series_create.py::test_arr_metadata_snapshot -x` | ❌ Wave 0 |
| BIBLE-05 | `series.register` starts NULL and is settable via `merge_inferred` | unit | `uv run pytest tests/bible/test_merge_inferred.py::test_register_starts_null_then_merges -x` | ❌ Wave 0 |
| BIBLE-06 | Same character row across two consecutive merges with identical inferred value emits ZERO events | unit | `uv run pytest tests/bible/test_merge_inferred.py::test_noop_inference_emits_no_event -x` | ❌ Wave 0 |
| BIBLE-06 (lock invariant) | Locked field survives contradicting inference; no event emitted | unit | `uv run pytest tests/bible/test_merge_inferred.py::test_locked_field_survives_contradicting_inference -x` | ❌ Wave 0 |
| (D-32 atomicity) | If bible_event INSERT fails, the current-row UPDATE rolls back | unit | `uv run pytest tests/bible/test_merge_inferred.py::test_event_insert_failure_rolls_back_update -x` | ❌ Wave 0 |
| (D-37 ledger migration) | JSON ledger with 5 entries → SQLite has 5 rows; JSON file renamed to `.migrated.bak` | integration | `uv run pytest tests/db/test_migrate_json_ledger.py::test_one_shot_migration_happy_path -x` | ❌ Wave 0 |
| (D-37 idempotency) | Re-run migration with `.migrated.bak` present → no-op, no duplicate rows | integration | `uv run pytest tests/db/test_migrate_json_ledger.py::test_idempotent_when_bak_present -x` | ❌ Wave 0 |
| (D-37 collision) | JSON entry conflicts with existing DB row (same source_path) → log-and-skip | integration | `uv run pytest tests/db/test_migrate_json_ledger.py::test_collision_logged_and_skipped -x` | ❌ Wave 0 |
| (Ledger contract regression) | All Phase-2 Ledger tests (`tests/output/test_ledger.py`) pass against SQLA backend | regression | `uv run pytest tests/output/test_ledger_sqla.py -x` | ❌ Wave 0 |
| (Engine PRAGMAs) | Connecting to the DB and querying `PRAGMA foreign_keys` returns 1 | unit | `uv run pytest tests/db/test_engine.py::test_foreign_keys_enabled_per_connection -x` | ❌ Wave 0 |
| (Engine PRAGMAs) | `PRAGMA journal_mode` returns `wal` on fresh DB | unit | `uv run pytest tests/db/test_engine.py::test_wal_mode_set -x` | ❌ Wave 0 |
| (Migrations runnable) | `run_migrations_to_head` on a fresh temp DB creates all 7 expected tables | unit | `uv run pytest tests/db/test_migrations.py::test_baseline_creates_all_tables -x` | ❌ Wave 0 |
| (Lazy series creation) | First call with new `(arr_kind, arr_instance, arr_series_id)` inserts row; second call returns same row | unit | `uv run pytest tests/bible/test_lazy_series_create.py::test_get_or_create_idempotent -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/db tests/bible tests/output/test_ledger_sqla.py -x` (the Phase-4-owned tests; ~2-5 s)
- **Per wave merge:** `uv run pytest -x` (full suite; existing Phase-1/2/3 tests must continue to pass)
- **Phase gate:** Full suite green before `/gsd-verify-work`; plus a manual smoke: run `trezarr run --once` against a configured fixture; verify `/config/trezarr.db` is created and `processed_file` rows are written.

### Wave 0 Gaps

- [ ] `tests/db/__init__.py` — package marker
- [ ] `tests/db/conftest.py` — `db_engine` and `session_factory` fixtures (Code Examples §Test fixture)
- [ ] `tests/db/test_engine.py` — PRAGMA verification (FK, WAL, synchronous)
- [ ] `tests/db/test_migrations.py` — baseline migration runs cleanly + all 7 tables exist
- [ ] `tests/db/test_migrate_json_ledger.py` — happy path + idempotency + collision tests for D-37
- [ ] `tests/bible/__init__.py` — package marker
- [ ] `tests/bible/test_models.py` — round-trip tests for character + term_dictionary + series
- [ ] `tests/bible/test_store_load.py` — load_series_bible behavior, persistence-across-dispose
- [ ] `tests/bible/test_merge_inferred.py` — lock-precedence + no-op-detection + atomicity invariants
- [ ] `tests/bible/test_lazy_series_create.py` — get_or_create_series + arr_metadata snapshot
- [ ] `tests/output/test_ledger_sqla.py` — Phase-2 ledger regression suite re-run against SQLA backend
- [ ] Framework install: `uv add "sqlalchemy[asyncio]>=2.0.50,<2.1" "aiosqlite>=0.22.1,<0.23" "alembic>=1.18.4,<1.19"`
- [ ] Alembic scaffolding: `uv run alembic init alembic` then edit env.py per Pattern 4

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No new auth surface in Phase 4 — DB file is local to `/config` volume; no network surface introduced |
| V3 Session Management | no | No HTTP sessions in Phase 4 (Phase 7's web UI introduces them) |
| V4 Access Control | partial | The DB is a local file; access control = filesystem permissions (Phase-3 PUID/PGID already handles this for sidecar writes; same applies to the DB file) |
| V5 Input Validation | yes | Pydantic DTOs at the store boundary enforce shape; `arr_metadata` JSON snapshot must not exceed a sane size cap (large untrusted JSON could OOM future loads) |
| V6 Cryptography | no | No new crypto in Phase 4. `bible_db_url` is NOT a secret (it's a file path); existing `llm_api_key` / `sonarr_api_key` SecretStr handling is untouched |

### Known Threat Patterns for SQLAlchemy 2.0 + aiosqlite + Alembic

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via string concatenation | Tampering | Use only parametrised queries via `select(...).where(Model.col == value)` — never f-string into SQL. SQLAlchemy 2.0 makes this nearly impossible without `text()`. Forbid raw `text()` in code review unless escaped. |
| Information disclosure via DB file leakage | Information Disclosure | Treat `/config/trezarr.db` as containing user-private metadata (series/character info; future user edits). Match Phase-3 PUID/PGID permissions; document that `/config` is not for sharing. |
| `arr_metadata` JSON ingestion of untrusted data | Tampering / DoS | Cap the snapshot size (e.g. 32 KB) before INSERT; reject obviously-pathological payloads. arr responses are server-side trusted but `pyarr` doesn't validate shape. |
| Migration tampering (malicious `versions/` file) | Tampering | `versions/*.py` is executed at every startup. Keep the directory in git, code-review every migration, never `pip install` random Alembic migration packages. |
| Lock-bypass via direct SQL update (production code that skips `merge_inferred`) | Tampering / Repudiation | Code review must reject any `session.add()` / `session.execute(update(...))` against Bible tables outside `bible/store.py`. The merge contract IS the audit trail. |
| Path traversal via `bible_db_url` | Tampering | `bible_db_url` is a TrezarrSettings field controlled by env/YAML; user can already write anywhere they have permission to. Document that `bible_db_url` must point inside `/config` for safety. |
| Resource exhaustion via unbounded `bible_event` growth | Denial of Service | Phase 4 ships no pruning; Phase 8 may add. Add a comment in `models.py` noting the long-term plan; not Phase-4 scope. |

## Project Constraints (from CLAUDE.md)

| Constraint | Application to Phase 4 |
|------------|------------------------|
| Python 3.12 floor | All three new packages support 3.12; no version conflict |
| FastAPI + Pydantic 2.x stack | Pydantic DTOs at store boundary (D-39) align with the prescribed pattern |
| `sqlalchemy[asyncio]` 2.0.x + aiosqlite 0.22.x + Alembic 1.18.x | EXACT match — CLAUDE.md prescribed this stack |
| `/config` volume convention | DB at `/config/trezarr.db`; JSON ledger migration `.bak` stays in `/config` |
| Single SQLite file, single-writer | Phase 4 doesn't run a daemon — sequential CLI translate loop respects single-writer naturally; Phase 7 will need per-series serialization |
| No Flask/sync DB | All DB I/O is async via aiosqlite — no exception |
| pydantic-settings 2.14.x | New `bible_db_url` field added to TrezarrSettings — no new config system (D-11) |
| Async everywhere — no sync sqlite3 calls | Honored — sqlite3 imports forbidden in production code (tests-only if at all) |
| GSD workflow enforcement | All Phase-4 work routes through GSD plans |

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy 2.0 — Asynchronous I/O](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — AsyncEngine/async_sessionmaker, PRAGMA event listener pattern, lazy-loading caveats, AsyncAttrs
- [SQLAlchemy 2.0 — Session Transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html) — `session.begin()` context manager + savepoint test pattern
- [SQLAlchemy 2.0 — SQLite Dialect](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html) — FK PRAGMA per-connection requirement
- [Alembic Cookbook — Connection Sharing with asyncio](https://alembic.sqlalchemy.org/en/latest/cookbook.html#programmatic-api-use-connection-sharing-with-asyncio) — programmatic `command.upgrade()` via `connection.run_sync(do_run_migrations)` bridge
- [SQLite WAL documentation](https://www.sqlite.org/wal.html) — WAL is persistent on DB file (vs FK PRAGMA which isn't); single-writer architecture; checkpoint behavior
- PyPI JSON API (live, 2026-06-01) — version verification for sqlalchemy 2.0.50, aiosqlite 0.22.1, alembic 1.18.4

### Secondary (MEDIUM confidence)
- [SQLAlchemy GitHub Discussion #12413 — Enforcing FK on SQLite](https://github.com/sqlalchemy/sqlalchemy/discussions/12413) — community confirmation of event-listener-per-connect pattern
- [aiosqlite documentation](https://aiosqlite.omnilib.dev/en/stable/) — single-thread-per-connection model

### Tertiary (LOW confidence)
- None — every claim in this research is grounded in either official docs or in-repo code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified live against PyPI; CLAUDE.md prescribed the same stack at project inception; canonical patterns sourced from official docs
- Architecture patterns: HIGH — every pattern shown is a verbatim or near-verbatim transcription of the official SQLAlchemy/Alembic documentation
- Pitfalls: HIGH — all 9 pitfalls are documented in SQLAlchemy / SQLite / Alembic official sources or have been observed in the broader Python community; the FK-per-connection one is the most-cited
- D-37 JSON→SQLite migration: MEDIUM-HIGH — pattern is grounded in `trezarr/output/ledger.py:_write()` (the atomic os.replace already used) plus standard two-phase-commit reasoning; the specific "rename AFTER commit" ordering should be planner-confirmed
- Lazy series creation arr_metadata gap: MEDIUM — Open Question 1 needs planner resolution

**Research date:** 2026-06-01
**Valid until:** 2026-07-01 (30 days — stack is stable; SQLAlchemy/Alembic don't ship breaking changes inside a minor)
