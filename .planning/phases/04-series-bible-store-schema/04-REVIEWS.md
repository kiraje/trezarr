---
phase: 4
reviewers: [codex]
reviewed_at: 2026-06-01T00:47:59Z
plans_reviewed: [04-01-PLAN.md, 04-02-PLAN.md, 04-03-PLAN.md, 04-04-PLAN.md]
reviewer_models:
  codex: gpt-5.5
skipped_reviewers:
  claude: "running inside Claude Code CLI — skipped for independence"
  gemini: "CLI not installed"
  coderabbit: "CLI not installed"
  opencode: "CLI not installed"
  qwen: "CLI not installed"
  cursor: "CLI not installed"
  ollama: "server not running"
  lm_studio: "server not running"
  llama_cpp: "port 8080 in use but not OpenAI-compatible (HTTP 404 on /v1/models)"
---

# Cross-AI Plan Review — Phase 4: Series Bible Store & Schema

> Only one external reviewer (codex / gpt-5.5) was available in this environment.
> No multi-reviewer consensus is possible; treat the single review as authoritative
> rather than corroborated. Re-run `/gsd-review --phase 4 --gemini` (or `--all`)
> after installing additional CLIs to gather independent perspectives before
> incorporating these findings into a replan.

## Codex Review (gpt-5.5)

**Summary**

The phase plan is unusually thorough and mostly coherent. It correctly treats Phase 4 as a persistence substrate, not an LLM/business-logic phase, and it gives strong attention to SQLite/Alembic sharp edges, provenance, lock precedence, and migration safety. The main risks are not conceptual but executional: the plans are very large, some tests are brittle or overspecified, 04-04 changes the ledger interface more broadly than the original "call-site unchanged" language implied, and there are a few schema/API details that need tightening before implementation.

**Strengths**

- Clear wave structure: 04-01 establishes DB/migration foundation; 04-02 builds series/register metadata; 04-03 adds character/term merge semantics; 04-04 swaps the ledger backend.
- Good alignment with roadmap success criteria: persistence, character/term schema, register metadata, and carry-forward/lock precedence are all explicitly covered.
- Correct SQLite fundamentals: temp-file test DBs, WAL/FK PRAGMAs per connection, `expire_on_commit=False`, Alembic `run_sync`, and `render_as_batch=True`.
- D-37 migration ordering is correctly specified: commit SQLite rows first, rename JSON ledger second.
- Strong auditability design: mutable current rows plus append-only `bible_event` is the right model for downstream review/UI/replay.
- Good DTO boundary intent: Phase 5 should consume Pydantic DTOs rather than SQLAlchemy models.
- Explicit handling of the `MediaItem` metadata gap is valuable; pushing metadata capture into Phase 4 avoids Phase 5 re-fetching from *arr APIs.

**Concerns**

- [HIGH] 04-04 violates the earlier "engine.py call sites unchanged" contract by converting `Ledger.check/record` to async and editing six translate-engine call sites. The plan justifies this as Option C, but it is a real breaking API change and broadens blast radius.
- [HIGH] 04-03 and 04-04 both modify behavior that can affect `translate/engine.py` workflows, but only 04-04 owns the ledger async conversion. Any missed direct or indirect ledger call outside the listed six sites will fail at runtime or silently create unawaited coroutines.
- [HIGH] `upsert_character` / `upsert_term` as described call `merge_inferred(...)` after opening their own transaction if the row already exists. If implemented literally, this creates nested session usage and can race or confuse transaction ownership. Better to share a private helper that operates inside the current session.
- [HIGH] `merge_inferred` computes changes from the incoming DTO before re-reading the row. If the DB row changed after the DTO was loaded, stale DTO values could produce wrong `old_value` audit entries or overwrite newer data. The plan says "re-read inside txn" in research, but 04-03 action computes before the transaction.
- [MEDIUM] Hand-authored Alembic baseline is reasonable, but the plan needs a schema drift guard comparing migration-created DB schema against SQLAlchemy metadata or running Alembic autogenerate/check. Otherwise models and migration can diverge immediately.
- [MEDIUM] JSON defaults are inconsistent: SQLAlchemy models use callable defaults, migrations use `server_default="[]"` / `"{}"`, DTOs use literal `{}` / `[]`. Pydantic v2 copies defaults, but this still deserves explicit tests and consistency.
- [MEDIUM] `BibleEventDTO.created_at: Any` weakens the DTO contract. Use `datetime | None` unless there is a concrete serialization issue.
- [MEDIUM] `bible_event.entity_id` is polymorphic without FK. That is acceptable for an audit log, but deletes or ID reuse assumptions should be documented. Consider `entity_table`/`entity_pk` naming or add indexes.
- [MEDIUM] `source` enum is validated in Python but not constrained in DB. A CHECK constraint would protect imports/manual edits.
- [MEDIUM] `arr_metadata` cap uses `json.dumps(...).encode()` without specifying `ensure_ascii=False`; Vietnamese or non-ASCII metadata may inflate unexpectedly. Not fatal at 32 KB, but worth being deliberate.
- [MEDIUM] Corrupt JSON ledger migration renames the unreadable file to `.migrated.bak`. That avoids repeated startup warnings but can hide recoverable data. A `.corrupt.bak` suffix would be clearer than pretending migration succeeded.
- [MEDIUM] The `migrate_json_ledger_if_needed` idempotency rule short-circuits if `.migrated.bak` exists, even if the DB was recreated empty. That is consistent with the written D-37, but it means a deleted DB plus existing backup loses automatic recovery.
- [MEDIUM] `processed_file.source_path` uniqueness may be too weak if path mappings change or case sensitivity differs across filesystems. Acceptable for v1, but worth documenting.
- [LOW] Several tests inspect implementation details via grep/source inspection. Useful as guardrails, but brittle and can block harmless refactors.
- [LOW] The plans over-specify exact line numbers in `engine.py`; those will drift. Use grep-based call-site discovery as the source of truth.
- [LOW] `journal_mode=WAL` in a connect listener may run repeatedly and can be awkward for some SQLite URLs. Fine for file DBs, but tests should avoid asserting WAL for in-memory URLs.
- [LOW] The phase creates `address_map` and `relationship_event` tables early, but their schema may be under-informed before Phase 5/6. This is an accepted D-31 trade-off, but it increases future migration risk.

**Suggestions**

- In 04-04, add a repository-wide check for ledger calls: `rg "ledger\.(check|record)\(" trezarr tests` and require every production call to be awaited. Do not rely only on the six current line numbers.
- In [trezarr/bible/store.py], implement private session-scoped helpers, for example `_merge_inferred_in_session(session, row, inferred, ...)`, `_upsert_character_in_session(...)`, and keep public functions as thin session owners. Avoid public `upsert_*` calling public `merge_inferred` from inside another transaction.
- In `merge_inferred`, re-read the row first, compute locked fields and field changes from the fresh SQLAlchemy row or a fresh DTO built inside the transaction, then update and insert events. This preserves correct `old_value`.
- Add DB indexes in the baseline migration:
  - `character(series_id, original_latin_name)`
  - `term_dictionary(series_id, source_term)`
  - `processed_file(source_path)` unique index
  - `bible_event(series_id, entity_type, entity_id, created_at)`
- Add DB CHECK constraints where stable:
  - `series.arr_kind IN ('sonarr', 'radarr')`
  - `bible_event.source IN ('inference', 'lock', 'import', 'system')`
  - optionally `processed_file.status IN ('done', 'quarantined', 'in_progress')`
- Add an Alembic/model drift test after 04-01. At minimum, run Alembic autogenerate in check mode if available, or inspect columns/types/nullability for all seven tables against expected metadata.
- Rename corrupt JSON ledger backups to `processed_files.json.corrupt.bak` instead of `.migrated.bak`, and log the exact path. Keep `.migrated.bak` for successful imports only.
- Reconsider the async Ledger conversion. If minimizing blast radius matters more than async purity, keep a sync `Ledger` protocol and make `LedgerSQLA` expose async internals through a small adapter at CLI/engine boundaries. If Option C stays, update type hints/protocols/tests everywhere and document the breaking internal API change clearly.
- Replace source-inspection tests like "no SQLAlchemy names in DTO namespace" with simpler contract tests: importing DTOs should not import `trezarr.bible.models`, and DTO construction should work without a DB engine.
- Add a test for first-time insert event behavior in `upsert_character` and `upsert_term`: verify event count and old/new values for each non-None field.
- Add tests for clearing a field to `None` through `merge_inferred`, since `old_value`/`new_value` allow null and this matters for corrections.
- Add a test for unsupported inferred fields. The current pure policy treats missing attributes as old `None`, but `setattr(row, "nickname", ...)` on a SQLAlchemy model may not persist and may silently create a transient Python attribute. Either reject unknown fields or explicitly whitelist mergeable fields per entity type.

**Risk Assessment**

Overall risk: **MEDIUM-HIGH**. The architecture is sound and the plans address the roadmap criteria, but the implementation surface is large for one phase: new ORM, migrations, schema, DTOs, store APIs, metadata plumbing, audit semantics, JSON migration, CLI startup wiring, and a sync-to-async ledger API change. The highest-risk items are the ledger async conversion, stale DTO merge semantics, and transaction ownership in `upsert_*`/`merge_inferred`. Tightening those before execution would bring the phase down to medium risk.

---

## Consensus Summary

Only one external reviewer (codex / gpt-5.5) was available, so this section restates that reviewer's highest-leverage findings rather than reporting agreement across multiple AIs. Re-run `/gsd-review` with additional CLIs installed to obtain true consensus.

### Top-Priority Concerns (codex HIGH)

1. **`merge_inferred` uses a stale DTO** — Changes and `old_value` audit entries are computed from the caller's DTO before the transaction opens, so a concurrent (or merely time-shifted) write can produce wrong audit entries or overwrite newer data. 04-03 should be amended to re-read the SQLA row inside the transaction and derive both `locked` and `changes` from the fresh state. This is a correctness defect, not a style nit.

2. **`upsert_*` nests transactions through `merge_inferred`** — As specified, `upsert_character` opens a session/`session.begin()` block and, on the "row exists" path, calls public `merge_inferred(...)` which opens its own session. Refactor 04-03 to introduce session-scoped private helpers (e.g. `_merge_inferred_in_session`, `_upsert_character_in_session`) so the public functions are the only transaction owners.

3. **Ledger async conversion broadens blast radius beyond the documented 6 call sites** — 04-04's "Option C" replaces the Phase-2 sync `Ledger.check/record` contract with async; any call outside the enumerated lines that silently creates an unawaited coroutine is a latent bug. Add a repo-wide `rg "ledger\.(check|record)\(" trezarr tests` guard, update the `Ledger` Protocol/typing once, and document the breaking internal API change in `ledger.py`'s docstring and a CHANGELOG entry.

### Notable Schema / Migration Gaps (codex MEDIUM)

- No schema-drift guard between the hand-authored Alembic baseline and `Base.metadata` — add an autogenerate/check test after 04-01.
- Missing DB-level constraints that the plan only enforces in Python: `series.arr_kind` and `bible_event.source` CHECK constraints, and indexes on `character(series_id, original_latin_name)`, `term_dictionary(series_id, source_term)`, `bible_event(series_id, entity_type, entity_id, created_at)`.
- JSON-default inconsistency across SQLA models (`default=list`), Alembic migration (`server_default="[]"`), and Pydantic DTOs (literal `[]`) — needs a deliberate test that all three layers agree.
- Corrupt-JSON ledger migration reuses the `.migrated.bak` suffix, conflating "successfully imported" with "moved aside because unreadable" — use `.corrupt.bak` instead.

### Test Quality (codex LOW)

- Source-inspection / grep-based tests ("no SQLAlchemy names in DTO namespace", "exactly 6 awaits in engine.py") are brittle. Replace with behavioural contract tests where possible; keep grep-style tests only when there is no behavioural substitute.
- Hardcoded line numbers (421/438/454/479/520/537) in 04-04 will drift the moment `engine.py` is touched. Treat grep-based call-site enumeration as the source of truth and let the test discover the count.

### Divergent Views

None — single reviewer.

### Next Step

Re-run `/gsd-plan-phase 4 --reviews` to fold these findings into a planning revision. Prioritise the four HIGH concerns; treat the MEDIUM items as warnings to address before execution; defer or accept the LOW items per planner discretion.
