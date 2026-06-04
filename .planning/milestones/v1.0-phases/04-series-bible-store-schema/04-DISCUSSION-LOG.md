# Phase 4: Series Bible Store & Schema - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 04-series-bible-store-schema
**Areas discussed:** Schema scope, Versioning & provenance model, Series identity key, Lock & precedence semantics, Ledger swap, Register grounding

---

## Schema scope

| Option | Description | Selected |
|--------|-------------|----------|
| Strict Phase-4 only | character + term_dictionary + series (with register). processed_files.json stays as JSON. Phase 5 adds address_map. Phase 7 migrates the ledger. | |
| Full schema, Phase-4 logic only | All tables (incl. address_map, relationship_event, processed_file) created via one Alembic baseline. Phase 4 logic only touches character/term/series. Ledger migrated to SQLite now. | ✓ |
| Strict tables + ledger swap | Character + term + series + processed_file (ledger swap). Defer address_map/relationship_event. | |

**User's choice:** Full schema, Phase-4 logic only
**Notes:** Avoids three migrations in three consecutive phases (4 → 5 → 6). Phase 5/6 just INSERT into already-existing tables. Drives D-31.

---

## Versioning & provenance model

| Option | Description | Selected |
|--------|-------------|----------|
| Mutable current + event log | Single mutable row per entity; separate bible_event log records every change. Current is materialized; log is for audit/UI/replay. | ✓ |
| Row-versioned (valid_from / valid_to) | Append-only entity table with episode-marker validity intervals. Current = WHERE valid_to IS NULL. Provenance intrinsic. | |
| Per-episode JSON snapshot | Full Bible JSON blob per episode. Load = latest snapshot. Merge happens in Python. No field-level queries. | |

**User's choice:** Mutable current + event log
**Notes:** Simple read path for Phase 5 (single-row SELECT); event log is the audit substrate Phase 6 self-review and Phase 8 UI will consume. Drives D-32 — current row + `bible_event` append in one transaction.

---

## Series identity key

| Option | Description | Selected |
|--------|-------------|----------|
| External ID is the key | tvdb_id / tmdb_id as primary identity. Bibles portable across arr reinstalls. | |
| Arr-internal ID is the key | (arr_kind, arr_instance, arr_series_id) as identity. Matches Phase 3's MediaItem. Reinstall orphans Bible. | ✓ |
| External-first, arr-id fallback | Prefer tvdb/tmdb when present; fall back to arr id. Most resilient, most code. | |

**User's choice:** Arr-internal ID is the key
**Notes:** Pragmatic v1 — matches what Phase 3 already passes. External IDs (tvdb_id, tmdb_id) still captured at creation as denormalized columns to enable future migration to external-keyed identity (v2 multi-instance / COMM-01 Bible sharing). Drives D-33.

---

## Lock & precedence semantics

| Option | Description | Selected |
|--------|-------------|----------|
| JSON locked_fields on the row | Each entity row carries a JSON-encoded set of locked field names. Merge skips locked fields. Atomic, simplest. | ✓ |
| Parallel bible_lock table | Separate table with locked_by/locked_at/reason. Merge LEFT JOINs to check lock state. Lock provenance first-class. | |
| JSON now, separate table later | Ship JSON in Phase 4; migrate to parallel table in Phase 8 if richer provenance needed. Defer-not-deny. | |

**User's choice:** JSON locked_fields on the row
**Notes:** Implicit option (3) is in play via D-34's `get_locked_fields(entity)` accessor — Phase 8 can swap the backing store without touching merge call sites. Drives D-34.

---

## Ledger swap (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| One-shot migration | Import processed_files.json into processed_file SQLite table on first startup; rename JSON to .migrated.bak. Idempotent. | ✓ |
| Clean slate | SQLite starts empty; JSON ignored. Worst case a few items re-translate once. | |
| Side-by-side until verified | Phase 4 writes to both for one milestone; Phase 7 removes JSON. Safest, most code. | |

**User's choice:** One-shot migration
**Notes:** Drives D-37. Idempotency via presence of `.migrated.bak`; corrupt JSON logs loudly and starts empty rather than crashing.

---

## Register grounding (follow-up)

| Option | Description | Selected |
|--------|-------------|----------|
| JSON blob on series row | series.arr_metadata JSON captures genre/overview/year/network/runtime. Phase 5 reads to ground register. Simple. | ✓ |
| Denormalized columns on series | Typed columns for known fields. Queryable, but locks shape; new fields = Alembic migration. | |
| Separate series_metadata table | 1:1 table with typed columns + raw_json catch-all. Cleanest separation, most code. | |

**User's choice:** JSON blob on series row
**Notes:** Drives D-35. Phase 4 snapshots at series-row creation (D-36 lazy); Phase 4 leaves `series.register = NULL`; Phase 5's LLM Pass-1 populates register via `merge_inferred()` so locks + event-logging apply uniformly.

---

## Claude's Discretion

Areas delegated per discussion + standing delegation:
- Exact module/package layout (likely `trezarr/bible/{models,store,merge,dto}` + `trezarr/db/{engine,session,migration_runner}`)
- Pydantic DTO field shape and Optional handling
- Alembic env.py online/offline mode and whether migrations run on every app startup or via a manual command
- `source` enum exact wording (`inference|lock|import|system` is the working set)
- `bible_event.old_value`/`new_value` storage shape (TEXT vs JSON)
- Precise `TrezarrSettings.bible_db_*` field names + optional pragma toggles
- Behaviour when a `processed_file` migration entry's `source_path` no longer exists on disk (skip vs import+flag — both defensible)
- `merge_inferred` as free function vs method on the store
- SQLAlchemy declarative-base style (prefer 2.0 typed `DeclarativeBase` + `mapped_column` for Pydantic-everywhere consistency)
- Test fixture strategy (in-memory SQLite vs temp-file SQLite — temp-file is more honest about migrations)

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` section. Highlights:
- LLM Pass-1 analyzer that populates Bible → Phase 5
- Address Map writes + speaker/addressee attribution → Phase 5
- Relationship-evolution events → Phase 6
- LLM self-review pass → Phase 6
- Editable Bible UI + production lock-setting → Phase 8
- Multi-instance arr + Bible export/sharing → v2 (`tvdb_id`/`tmdb_id` columns captured now to keep the door open)
- `arr_metadata` refresh policy → Phase 5+ / Phase 10
- Richer `bible_lock` table with provenance fields → Phase 8 evaluates
