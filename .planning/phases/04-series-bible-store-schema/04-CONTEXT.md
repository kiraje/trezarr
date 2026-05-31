# Phase 4: Series Bible Store & Schema - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 introduces **SQLite-backed persistence** to Trezarr and ships the **Series Bible store** that future translation passes will consume. It is purely the **schema + store + merge layer** — not the LLM analyzer that populates the Bible (Phase 5), not the Address Map or pronoun engine (Phase 5), not relationship-evolution events (Phase 6), and not the editing UI (Phase 8).

Concretely, Phase 4 delivers:

1. **SQLAlchemy 2.0 async + aiosqlite + Alembic** introduced into the project; a single SQLite DB at the `/config` volume convention; one **baseline Alembic migration** stands up the entire long-term Bible schema (see D-31).
2. **Per-series Bible store** for `character`, `term_dictionary`, and `series` (with `register`) — read/write/merge implemented for these three; downstream phases populate the other tables that already exist. (BIBLE-01, BIBLE-02, BIBLE-04, BIBLE-05, BIBLE-06)
3. **Mutable-current + append-only `bible_event` log** so every Bible mutation leaves a provenance trail (episode, source=inference|lock|import, before/after) — the substrate for Phase 6 self-review audits and Phase 8 lock provenance.
4. **Per-field lock semantics** as a JSON `locked_fields` set on each entity row, plus a `merge_inferred()` function that enforces precedence `human lock > prior value > new inference` (success criterion 4). Phase 4 doesn't write locks (the UI in Phase 8 does), but it ships the storage + merge logic + tests proving "locked field survives a contradicting inference."
5. **One-shot migration of Phase-2's `/config/processed_files.json`** into the new `processed_file` SQLite table (D-20 always promised this swap; D-37). The existing `Ledger` interface in `trezarr/output/ledger.py` is swapped to a SQLAlchemy backend with identical call-site contract.
6. **Per-series `arr_metadata` JSON snapshot** captured at series-row creation from Phase-3 discovery payloads (genre, overview, year, network, runtime), so Phase 5's Pass-1 can ground `register` without re-calling `*arr` APIs.

Requirements covered: **BIBLE-01** (per-series Bible persists + loaded as context + updated after each episode), **BIBLE-02** (Characters), **BIBLE-04** (Term Dictionary), **BIBLE-05** (Register/tone schema + metadata snapshot), **BIBLE-06** (carry-forward semantics — same character/term flows unchanged from S01E01 to finale unless a lock or event changes it).

**In scope:**
- New dependencies: `sqlalchemy[asyncio]` 2.0.x, `aiosqlite` 0.22.x, `alembic` 1.18.x.
- Module: `trezarr/bible/` (models, session, store, merge) + `trezarr/db/` (engine/session lifecycle).
- Alembic baseline migration creating: `series`, `character`, `term_dictionary`, `address_map`, `relationship_event`, `bible_event`, `processed_file`.
- `Ledger` backend swap (JSON → SQLAlchemy) with no call-site changes in `engine.py`.
- One-shot JSON-ledger import on first SQLite startup (idempotent; renames legacy file to `.migrated.bak`).
- `merge_inferred()` enforcing the lock-precedence contract, atomically writing (current row UPDATE + `bible_event` INSERT) in one transaction.
- `TrezarrSettings` additions for DB URL/path.

**Out of scope (deferred to owning phases):**
- **The LLM Pass-1 analyzer** that populates `character` / `term_dictionary` / `register` from a source subtitle + arr metadata — that is **Phase 5** (Three-Pass Pronoun Engine).
- **Address Map writes + speaker/addressee attribution** (BIBLE-03, PRON-01/02/03) — table is created empty in Phase 4; **Phase 5** populates and reads.
- **Relationship-evolution events** (BIBLE-07) — table is created empty; **Phase 6** records transitions.
- **LLM self-review pass** (ENG-05) — **Phase 6**.
- **Bible editor UI + lock-setting** (BIBLE-08, BIBLE-09) — **Phase 8**. Phase 4 ships the storage and the merge function that *respects* locks; nothing in Phase 4 actually sets `locked_fields=...` on a row except tests.
- **Multi-instance arr support / Bible portability across reinstalls** — accepted v1 trade-off (D-33). Future migration path enabled by capturing `tvdb_id` / `tmdb_id` at series creation.
- **Docker image / s6-overlay / `/config` volume creation** — Phase 7. Phase 4 just uses the conventional `/config/trezarr.db` path; `mkdir -p` at startup if needed.

</domain>

<decisions>
## Implementation Decisions

Continues the project decision ledger (Phase 1 D-01…D-11, Phase 2 D-12…D-20, Phase 3 D-21…D-30). All numbered values are sensible defaults the planner/researcher may tune; all are overridable in planning.

### Schema scope (D-31)
- **D-31: Full schema baseline now, Phase-4 logic on three tables only.** A single Alembic baseline migration creates **all** long-term Bible tables — `series`, `character`, `term_dictionary`, `address_map`, `relationship_event`, `bible_event`, `processed_file` — even though Phase 4 only reads/writes `series` / `character` / `term_dictionary` / `bible_event` / `processed_file`. Phase 5 populates `address_map`; Phase 6 populates `relationship_event`. This avoids three schema migrations in three consecutive phases and keeps every future phase to an INSERT.

### Versioning & provenance (D-32)
- **D-32: Mutable current + append-only `bible_event` log.** Each entity (`character`, `term_dictionary`, `series.register`) has **one current-state row**; every mutation also appends a `bible_event(series_id, episode_key, entity_type, entity_id, field, old_value, new_value, source, created_at)` row inside the **same transaction**. Phase 5/6 read the simple current row; the event log is the audit trail for future review/UI/replay. The `source` enum is `inference | lock | import | system` — extensible without schema change.

### Identity key (D-33)
- **D-33: `(arr_kind, arr_instance, arr_series_id)` is the primary identity.** The `series` table uses a surrogate `id` PK plus a UNIQUE constraint on those three columns. `arr_kind ∈ {sonarr, radarr}`; `arr_instance` defaults to `"default"` (v2 multi-instance hook); `arr_series_id` is pyarr's integer ID. `tvdb_id` / `tmdb_id` are **stored as denormalized columns at series creation** (free at discovery, enables future migration to external-keyed identity) but are **not used for lookup** in v1. Reinstall-orphan trade-off (reinstalling Sonarr renumbers IDs and orphans the Bible) is **accepted for v1**; portability for COMM-01 (Bible export/sharing) is a v2+ concern.

### Lock & precedence semantics (D-34)
- **D-34: `locked_fields: JSON` on each entity row.** Stored as a JSON array of field names (e.g. `["role", "name"]`); deserialised in Python as `frozenset[str]`. The `merge_inferred(entity, inferred_dict, episode_key, source)` function:
  - Skips fields in `entity.locked_fields` (human lock wins — success criterion 4).
  - Skips fields where `inferred[field] == entity[field]` (no-op, no event).
  - Otherwise applies the change AND appends a `bible_event` row in the same transaction.
  - Returns `(updated_entity, list[BibleEvent])` so callers can log/observe.
- Phase 4 never sets `locked_fields` in production code — only in tests that demonstrate lock survival. Phase 8's UI is the production setter. The merge function takes a `get_locked_fields(entity)` accessor so the backing store can swap to a parallel `bible_lock` table in Phase 8 without touching call sites if richer lock provenance is needed.

### Register grounding (D-35)
- **D-35: `series.arr_metadata: JSON` snapshot at series-row creation.** When a series row is created (lazily on first translate — D-36), Phase 3's MediaItem payload (genres, overview, year, network, runtime, any other arr fields) is captured into a single JSON column. Phase 5's LLM Pass-1 reads `arr_metadata` to ground the inferred `register` value (formal/casual/historical/…). Phase 4 itself sets `series.register = NULL` initially; **Phase 5 populates it via `merge_inferred`** like any other Bible field, so locks and event-logging apply uniformly.

### Series-row bootstrapping (D-36)
- **D-36: Lazy series-row creation on first translate.** No startup enumeration of Sonarr/Radarr libraries — the first time `translate_file` runs against an item whose `(arr_kind, arr_instance, arr_series_id)` is not in `series`, the store creates the row, snapshots `arr_metadata` from the calling MediaItem, and the translate path continues. This stays consistent with Phase 3's "API for knowledge, filesystem for action" pattern (D-22) and avoids a global discovery sweep.

### Ledger migration (D-37)
- **D-37: One-shot JSON→SQLite migration on first SQLite startup.** On engine init, if `/config/processed_files.json` exists AND `/config/processed_files.json.migrated.bak` does NOT exist, the startup hook:
  1. Begins a single transaction.
  2. Iterates every JSON entry; INSERTs into `processed_file` (column names already match — D-20).
  3. Commits.
  4. Renames the JSON file to `.migrated.bak` (atomic — same directory).
- Idempotent on re-run (presence of `.migrated.bak` short-circuits). If the SQLite DB already has rows for a `source_path` present in the JSON, the JSON row is logged-and-skipped (the DB is the newer truth). The `Ledger` *interface* in `trezarr/output/ledger.py` is unchanged — its backend is replaced with a SQLAlchemy implementation; `engine.py` call sites continue to use `ledger.check(...)` / `ledger.record(...)`.

### Persistence stack (D-38)
- **D-38: SQLAlchemy 2.0 async + aiosqlite + Alembic, single SQLite DB at `/config/trezarr.db`.** Stack matches CLAUDE.md prescription. Connection URL: `sqlite+aiosqlite:////config/trezarr.db` (configurable via new `TrezarrSettings.bible_db_url`, default derived from `/config/trezarr.db`). One `async_engine` + `async_sessionmaker` constructed at app startup, scoped per-transaction. SQLite pragmas applied at connect: `journal_mode=WAL`, `foreign_keys=ON`, `synchronous=NORMAL`. Single-writer assumption holds — the daemon (Phase 7) and the CLI (Phase 3) are both single-process consumers.

### Bible read API shape (D-39)
- **D-39: Pydantic DTOs at the store boundary, SQLAlchemy models internal.** `trezarr/bible/store.py` exposes a small Pydantic-typed API (`load_series_bible(series_id) -> SeriesBibleDTO`, `get_character(series_id, name) -> CharacterDTO | None`, `merge_inferred(entity_dto, inferred, episode_key, source) -> tuple[entity_dto, list[BibleEventDTO]]`). The SQLAlchemy `select`/`Session` machinery stays inside `store.py`. This mirrors the Phase 1/2 pattern (SubDoc/SubLine Pydantic-shaped, transport-agnostic) and means Phase 5 never imports SQLAlchemy.

### Claude's Discretion
Planner/researcher retain latitude on: exact module/package layout (likely `trezarr/bible/{models.py,store.py,merge.py,dto.py}` + `trezarr/db/{engine.py,session.py,migration_runner.py}`); Pydantic DTO field names and Optional shape; Alembic env.py setup (online vs offline migration story for tests); whether the Alembic runner runs on every app startup or is invoked manually for v1; the exact name of the source enum (`inference|lock|import|system`); the `bible_event.old_value`/`new_value` storage shape (TEXT vs JSON — both work, JSON future-proofs structured fields); the precise `TrezarrSettings.bible_db_*` field names; the `processed_file` migration's behaviour when an entry's `source_path` no longer exists on disk (skip vs import + flag — both defensible); whether `merge_inferred` is a free function or a method on the store; SQLAlchemy declarative-base style (`DeclarativeBase` vs `mapped_column`) — prefer 2.0 typed style for consistency with Pydantic-everywhere; whether to expose an aiosqlite WAL checkpoint pragma in startup; and the exact test fixtures (in-memory SQLite vs temp-file SQLite — temp-file is more honest about migrations).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/REQUIREMENTS.md` §Series Bible — **BIBLE-01, BIBLE-02, BIBLE-04, BIBLE-05, BIBLE-06** (the five requirements this phase delivers); also §Series Bible **BIBLE-03, BIBLE-07, BIBLE-08, BIBLE-09** for forward-context on tables Phase 4 creates but does not populate
- `.planning/ROADMAP.md` §"Phase 4: Series Bible Store & Schema" — goal + 4 success criteria

### Prior-phase foundations this phase consumes & extends
- `.planning/phases/03-arr-integration-first-vertical-slice/03-CONTEXT.md` — **D-22** (pyarr discovery shape — `arr_kind` / `arr_series_id` / metadata payload feeding `series.arr_metadata`); **D-27/D-28** (ledger source-sub hash + provenance — preserved through the SQLite migration); **D-30** (per-item failure isolation pattern — must hold across the new DB seam)
- `.planning/phases/02-mechanical-translation-core-validation-gate/02-CONTEXT.md` — **D-20** (processed-files ledger schema-compatibility with the Phase-4 `processed_file` table — the contract Phase 4 honors); **D-19** (atomic-write pattern, mirrored by the JSON→SQLite migration's `os.replace`-based rename)
- `.planning/phases/01-codec-llm-client-foundation/01-CONTEXT.md` — **D-11** (layered `pydantic-settings` config — `bible_db_url` is added here, not in a new config system)

### Existing code to reuse / extend (do not reinvent)
- `trezarr/output/ledger.py` — `Ledger` class (interface unchanged), `LedgerEntry` dataclass (fields `source_path`, `output_path`, `status`, `content_hash`, `series_id`, `source_lang`, `episode_key`, `translated_at`, `quarantine_path` already match the future `processed_file` table — D-20 wrote them this way). Backend gets swapped to SQLAlchemy; `engine.py` call sites do not change.
- `trezarr/translate/engine.py` — calls `ledger.check(...)` / `ledger.record(...)`; **must continue to work unchanged** after the backend swap (regression test required).
- `trezarr/config.py` — `TrezarrSettings`; extend with `bible_db_url` (default derived from `/config/trezarr.db`) + any DB pragma toggles. Mirror the Phase-3 pattern of grouping fields by phase with a comment header.
- `trezarr/paths.py` / `trezarr/cli.py` — the startup wiring point where the SQLite engine + ledger migration get initialised before the translate loop runs.

### Project-wide stack prescription
- `CLAUDE.md` §"Recommended Stack" — SQLAlchemy 2.0.x async, `aiosqlite` 0.22.x, `alembic` 1.18.x, single SQLite file under `/config` convention. **PROJECT.md §Constraints / Key Decisions** — Dockerized self-hosted service / `/config` volume / OpenAI-compatible endpoint (the Bible will eventually be the context fed into that endpoint by Phase 5).

### Research (risk & stack grounding)
- `.planning/research/STACK.md` — SQLAlchemy 2.0 async patterns (`async_sessionmaker`, `sqlalchemy[asyncio]` extra, `sqlite+aiosqlite://` URL); aiosqlite WAL guidance; Alembic baseline + autogenerate caveats; Pydantic-everywhere pattern
- `.planning/research/ARCHITECTURE.md` — Series Bible as the consistency-engine substrate; "API for knowledge, filesystem for action" still applies (DB is the new persistence surface, but discovery still flows from arr APIs)
- `.planning/research/PITFALLS.md` — re-check anything tagged DB / SQLite / migrations / locking; specifically any SQLite-concurrency notes relevant to mixing the new async engine with the existing async LLM client semaphore

### External docs (canonical references for the new stack)
- SQLAlchemy 2.0 async docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html — the async-session lifecycle, `async_sessionmaker`, transactional patterns
- Alembic docs: https://alembic.sqlalchemy.org/en/latest/tutorial.html — baseline migration + offline/online modes (offline for CI parity)
- aiosqlite: https://aiosqlite.omnilib.dev/ — pragmas at connect, WAL caveats

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`Ledger` interface (`trezarr/output/ledger.py`)** — public surface (`check`, `record`, `content_hash`) is preserved verbatim; only the storage backend changes. The `LedgerEntry` dataclass field names were deliberately chosen in Phase 2 (D-20) to match the future `processed_file` table 1:1 — Phase 4 cashes that bet. Call sites in `engine.py` should require **zero changes**; if they do, the swap broke the contract.
- **`MediaItem` (`trezarr/cli/MediaItem`)** — the post-scan eligible-item payload carries `series_id`, `episode_key`, source path, and (per Phase 3 notes) the raw arr payload. Phase 4 reuses this as the input shape for lazy series-row creation (D-36).
- **`TrezarrSettings` (`trezarr/config.py`)** — extend, don't replace. New fields: `bible_db_url` (default `sqlite+aiosqlite:////config/trezarr.db`), optionally `bible_db_pool_size`, optionally toggles for WAL/foreign-keys pragmas (default ON).
- **`trezarr/paths.py`** — already owns `/config` path conventions; the SQLite DB path resolution belongs here.

### Established Patterns
- **Layered config via `pydantic-settings`** (D-11) — DB URL goes here, never a new YAML/env-loader.
- **Atomic-write via temp + `os.replace`** (D-19) — mirrored by the JSON-ledger migration's "rename to `.migrated.bak`" step.
- **Failure = quarantine + log + continue, never silent corruption** (D-16/D-18/D-30) — apply to the migration step too: a corrupt JSON ledger logs loudly and starts the SQLite DB empty rather than crashing the run.
- **Pydantic models at module boundaries; transport-shape Pydantic everywhere** (Phase 1/2 pattern) — DTO layer in `trezarr/bible/dto.py` matches this convention so Phase 5 never imports SQLAlchemy.
- **Async-first stack** — the LLM client + concurrency semaphore are async; the DB must be async too (aiosqlite). No sync `sqlite3` calls anywhere.

### Integration Points
- **Engine startup** (CLI today, daemon in Phase 7): create the SQLite engine, run Alembic migrations, run the one-shot JSON-ledger import, then construct the now-SQLite-backed `Ledger` and pass it into `translate_file` exactly as today.
- **`translate_file` → ledger** call sites: unchanged signature, unchanged behaviour. The DB is invisible to translate logic.
- **`MediaItem` → series row**: in Phase 4, the lazy create-or-fetch happens at the boundary where the translate loop dispatches items (`cli.py` or its successor), so the `series.id` is available before any future Phase-5 Pass-1 needs it.
- **Forward-compat empty tables**: `address_map` (Phase 5) and `relationship_event` (Phase 6) tables exist after Phase 4's baseline migration. Their schema is set in stone here — Phase 5/6 just write rows. Schema shape mirrors CLAUDE.md's prescribed Series Bible model.

</code_context>

<specifics>
## Specific Ideas

- The **one Alembic baseline** does the entire long-term Bible schema in a single migration file. No drip-feeding tables across phases — three migrations in three consecutive phases would mean schema sprawl + repeated review burden.
- The **`bible_event` log is the foundation for Phase 8's UI** ("show me everything Mary's role has been across the series") and Phase 6's self-review audit. Don't underspec it — `(episode_key, entity_type, entity_id, field, old, new, source, created_at)` is the minimum, and the table cost is negligible.
- The **`locked_fields` JSON column** is intentionally the simplest correct thing. Phase 8 may grow it into a parallel `bible_lock` table with provenance; the merge function's `get_locked_fields(entity)` accessor exists specifically to make that swap painless.
- **`arr_metadata` is a Phase-4 snapshot, not a live mirror.** Refreshing it on every translate is not Phase 4's concern. Phase 5 + Phase 10 may add refresh policy later.

</specifics>

<deferred>
## Deferred Ideas

- **LLM Pass-1 analyzer** that actually populates `character` / `term_dictionary` / `series.register` from the source subtitle + `arr_metadata` → **Phase 5** (already roadmap-scoped).
- **Address Map writes + speaker/addressee attribution + the Vietnamese pronoun-pair rules** (BIBLE-03, PRON-01/02/03) → **Phase 5**. Schema is ready; logic is not.
- **Relationship-evolution events** (BIBLE-07) → **Phase 6**. Table exists; the analyzer that emits transitions does not.
- **LLM self-review pass** (ENG-05) → **Phase 6**. Reads `bible_event` log to spot drift before write.
- **Editable Bible UI + production lock-setting** (BIBLE-08, BIBLE-09) → **Phase 8**. Phase 4 ships the storage and merge contract; the UI sets the locks.
- **Multi-instance arr + Bible export / portability / sharing** (SCALE-01, COMM-01) → **v2**. `tvdb_id` / `tmdb_id` columns captured now to keep the door open.
- **`arr_metadata` refresh policy** (re-pull on series update, or per-N-episodes) → tuning concern for Phase 5+ or Phase 10 per-series overrides.
- **Richer `bible_lock` table with `locked_by` / `locked_at` / `reason`** → Phase 8 evaluates need; if the JSON `locked_fields` set is enough, no migration needed. The merge-function accessor exists to enable the swap without call-site churn.
- **Phase-2 ledger consolidation strategy** beyond the one-shot import (e.g. tooling to *un*-migrate, dual-write debug mode) → not needed for v1; cleanup tooling can come with the Web UI in Phase 7.

</deferred>

---

*Phase: 04-series-bible-store-schema*
*Context gathered: 2026-06-01*
