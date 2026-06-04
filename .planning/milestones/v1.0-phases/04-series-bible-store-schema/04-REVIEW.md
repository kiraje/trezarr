---
phase: 04-series-bible-store-schema
reviewed: 2026-06-01T05:30:11Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - alembic/versions/0001_baseline_bible_schema.py
  - trezarr/config.py
  - trezarr/db/base.py
  - trezarr/db/engine.py
  - trezarr/db/session.py
  - trezarr/db/migration_runner.py
  - trezarr/bible/models.py
  - trezarr/bible/dto.py
  - trezarr/bible/store.py
  - trezarr/bible/merge.py
  - trezarr/arr/sonarr.py
  - trezarr/arr/radarr.py
  - trezarr/output/_ledger_protocol.py
  - trezarr/output/ledger_sqla.py
  - trezarr/output/ledger.py
  - trezarr/cli.py
  - trezarr/translate/engine.py
  - trezarr/discover/gap.py
  - trezarr/discover/scan.py
findings:
  critical: 1
  warning: 8
  info: 4
  total: 13
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-06-01T05:30:11Z
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Fresh re-review of the current state (WR-06..WR-09 fixes already applied and verified correct).
This phase delivers the SQLAlchemy 2.0 async DB foundation, the Series Bible schema + store,
the lock-precedence merge engine, and the SQLA-backed ledger. The code is heavily documented
and the prior-round fixes are in place. The merge/lock policy, the DTO/SQLA boundary (D-39),
the `register`/`register_value` alias round-trip (verified empirically via Pydantic v2
`from_attributes`), and the single-transaction-owner model are all sound on close reading.

The adversarial pass surfaced one BLOCKER — a schema divergence between the ORM model and the
hand-authored baseline migration that undermines D-31's "one source of truth" goal and risks
autogenerate corruption on the first user migration — plus eight correctness/robustness
WARNINGs (a sidecar-as-source mis-selection loop, a credential-mangling gap in
`_normalize_arr_host`, a stale `in_progress` ledger row on the write-failure path, two
JSON→SQLite migration edge defects that re-open the WR-09 infinite-re-fire class of bug on the
*corrupt* path, and a Protocol-conformance gap masked by `# noqa` dead imports).

## Critical Issues

### CR-01: ORM model and hand-authored migration disagree on server-side defaults / nullability — undermines D-31 and risks autogenerate corruption on the first user migration

**File:** `trezarr/bible/models.py:79,84,85,120,148,179` and `alembic/versions/0001_baseline_bible_schema.py:46,51,52,72,83,106`
**Issue:**
The migration declares DB-level `server_default`s and explicit `nullable=False` that the ORM
models omit. Examples:

Migration (`series`):
```python
sa.Column("arr_instance", sa.String, nullable=False, server_default="default")
sa.Column("arr_metadata", sa.JSON, nullable=False, server_default="{}")
sa.Column("locked_fields", sa.JSON, nullable=False, server_default="[]")
```

Model (`Series`):
```python
arr_instance: Mapped[str] = mapped_column(String, default="default")        # no server_default, no nullable=False
arr_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)    # no server_default, no nullable=False
locked_fields: Mapped[list[str]] = mapped_column(JSON, default=list)        # no server_default, no nullable=False
```

The same gap repeats on `character.locked_fields`, `term_dictionary.locked_fields`, and
`address_map.locked_fields` (model: `default=list` only; migration: `nullable=False,
server_default="[]"`).

Why this is a BLOCKER, not cosmetic:

1. **It breaks D-31's stated contract.** `db/base.py:9-11` and `migration_runner.py` both assert
   that `Base.metadata` is the autogenerate comparison target and that the hand-authored baseline
   exists *specifically to avoid drift*. Because the models do not mirror the migration, the very
   first `alembic revision --autogenerate` a user runs in Phase 5+ will emit spurious
   `alter_column` operations (adding/removing server defaults, toggling NULL) against live columns
   — including `arr_instance`, which participates in the UNIQUE identity key
   `(arr_kind, arr_instance, arr_series_id)` (models.py:67). An auto-generated `alter_column` that
   drops the server default or changes nullability on an identity-key column on a populated
   production SQLite DB is a data-integrity event, not a style nit.

2. **Two sources of truth for "the default."** Any INSERT that does not go through the ORM
   constructor (raw SQL fixups, a future Alembic data migration, bulk import) relies on the DB
   server default; ORM inserts rely on the Python `default`. They are currently the same *value*
   by luck of authoring, but nothing enforces that they stay in sync, and the schema explicitly
   has no test asserting model/migration parity.

**Fix:** Make the models a faithful mirror of the migration so autogenerate is a no-op:

```python
arr_instance: Mapped[str] = mapped_column(
    String, nullable=False, server_default="default", default="default"
)
arr_metadata: Mapped[dict[str, Any]] = mapped_column(
    JSON, nullable=False, server_default="{}", default=dict
)
locked_fields: Mapped[list[str]] = mapped_column(
    JSON, nullable=False, server_default="[]", default=list
)
```

Apply the same `nullable=False` + `server_default="[]"` to every `locked_fields` column. Then add
a regression test that runs autogenerate against `Base.metadata` and asserts an empty diff — this
is the only durable guard against the class of bug D-31 was created to prevent.

## Warnings

### WR-01: `find_source_sub` can select a previously-written `.vi.srt` as a "source" subtitle

**File:** `trezarr/discover/scan.py:45,170-191`
**Issue:** `_LANG_SIDECAR_RE = r'^(.+?)\.([a-z]{2,3})\.srt$'` matches `vi` as a valid 2-letter
language token. For media stem `Show.S01E01`, our own output `Show.S01E01.vi.srt` matches and is
recorded in `found["vi"]`. Today this is masked only because `lang_priority` defaults to `["en"]`.
But `source_lang_priority` is user-configurable (config.py:107). If an operator adds `"vi"` (typo,
or a register-normalization use case), the engine feeds its own output back as the source — a
self-reinforcing corruption loop the D-26 foreign-vi guard does NOT catch, because the file IS in
the ledger as ours (so `is_eligible` Case 2 compares the *vi* file's hash as if it were a source
hash, gap.py:116-124).
**Fix:** Exclude the output language from source candidates:

```python
cand_stem, cand_lang = match.group(1), match.group(2).lower()
if cand_lang == "vi":        # never treat our own output language as a source
    continue
if cand_stem != media_stem:
    continue
```

### WR-02: `_normalize_arr_host` mangles a scheme-less `user:pass@host` into the username, defeating its own redaction contract

**File:** `trezarr/arr/__init__.py:79-82`
**Issue:** The docstring claims this is the "log-redaction choke-point" that strips
`user:password@host` userinfo (WR-01 in that file). That holds only for the `://` branch. A
scheme-less input like `admin:hunter2@sonarr.lan` falls to the bare branch:

```python
if ":" in host:
    return host.split(":", 1)[0]   # -> "admin"
```

which returns `"admin"` (the username) as the host. No password leaks, but pyarr is pointed at a
host literally named `admin`, discovery fails, and the resulting `DiscoveryError`/log line contains
`admin` — a wrong, misleading host for a plausible input shape the function claims to handle.
**Fix:** Strip userinfo before the port split:

```python
bare = host.rsplit("@", 1)[-1]
if ":" in bare:
    return bare.split(":", 1)[0]
return bare
```

(IPv6 literals like `::1` are also mangled by the naive `:` split — a separate pre-existing
limitation worth a follow-up.)

### WR-03: `translate_file` leaves a stale `in_progress` ledger row when the post-gate write or record fails

**File:** `trezarr/translate/engine.py:442-447,537-547`
**Issue:** Step 4 records `status="in_progress"`. Steps 10-11 (`write_vi_sidecar` then
`ledger.record(status="done")`) are NOT wrapped in a `try`. If `write_vi_sidecar` raises (disk
full, permission, EXDEV) — or the process dies between the write and the `record` — the row stays
`in_progress` and an output file may exist on disk that the ledger does not know about. The cli
loop's broad `except Exception` (cli.py:359) counts it as `n_fail`, but the ledger now disagrees
with disk state, and `is_eligible` Case 4 will re-translate next run, potentially re-writing over a
file the operator believes is final. Every other failure path in this function (Steps 5-6, 7, 9)
correctly transitions to a terminal `quarantined` state — only the final write/record is
unprotected.
**Fix:** Wrap Steps 10-11 to record a terminal state on failure:

```python
try:
    output_path = write_vi_sidecar(translated_doc, path)
    await ledger.record(LedgerEntry(..., status="done", ...))
except OSError as exc:
    qp = _write_quarantine(path, f"write failure: {exc}", [], settings)
    await ledger.record(LedgerEntry(..., status="quarantined", quarantine_path=str(qp)))
    return TranslationResult(status="quarantined", quarantine_path=qp, reason=str(exc))
```

### WR-04: JSON→SQLite migration files an all-invalid ledger under `.migrated.bak` (the success suffix) — misleading forensic loss

**File:** `trezarr/db/migration_runner.py:233-239`
**Issue:** When `entries` is empty after pre-validation because every row was malformed/invalid
(not because the file was genuinely empty), the code renames the JSON to `<path>.migrated.bak` — the
"successfully migrated" suffix — and short-circuits forever via the `.migrated.bak` idempotency
check (lines 142-147). An operator investigating "where did my ledger go" sees `.migrated.bak` and
reasonably concludes the data was imported, when in fact zero rows were inserted. This conflates
"migrated 0 rows (empty file)" with "every row rejected" and routes a forensically-interesting file
to the wrong bucket.
**Fix:** Distinguish the two cases via the `pre_skipped` counter that is already tracked:

```python
if not entries:
    if pre_skipped > 0:
        logger.warning("JSON ledger %s had %d entries, none valid — parking as %s",
                       json_path, pre_skipped, corrupt_bak)
        os.replace(json_path, corrupt_bak)
    else:
        logger.info("JSON ledger %s is empty — renaming to %s", json_path, migrated_bak)
        os.replace(json_path, migrated_bak)
    return
```

### WR-05: corrupt/empty-path `os.replace` calls in the migration are NOT guarded — re-opens the WR-09 infinite-re-fire bug on the corrupt path

**File:** `trezarr/db/migration_runner.py:184,193,238`
**Issue:** WR-09 carefully wrapped the *post-commit* rename (lines 289-304) in `try/except OSError`
+ a `.rename_blocked` sentinel so a cross-device/permission failure does not re-fire on every
startup. But the three earlier `os.replace(json_path, corrupt_bak/migrated_bak)` calls (corrupt
JSON at 184, non-dict top-level at 193, empty-entries at 238) have NO such guard. If `/config` is a
cross-device mount (EXDEV) or read-only at these points, the `os.replace` raises an uncaught
`OSError`, which propagates to `cli.py:191`'s broad `except` and is logged as "continuing with an
empty SQLite ledger." For the corrupt-JSON case this is wrong: the corrupt file is still in place
(rename failed), so the next startup re-reads it, re-fails, and re-attempts the same rename — the
exact infinite-re-fire loop WR-09 was created to prevent, but only the post-commit path got fixed.
**Fix:** Apply the same `try/except OSError` (+ sentinel or at minimum a terminal logged warning) to
the corrupt-bak and empty-migrated-bak renames so a rename failure there is also non-recurring.

### WR-06: migration trusts JSON dict key == inner `source_path` and silently drops duplicate keys

**File:** `trezarr/db/migration_runner.py:212`
**Issue:** `for k, v in raw.items()` iterates a JSON object whose keys are assumed to equal
`entry.source_path`, but nothing enforces that. `json.loads` collapses duplicate keys to the last
value, so two ledger entries sharing a `source_path` lose the earlier one before the migration sees
it. A hand-edited ledger (the module explicitly tolerates hand-edits) where `k != v["source_path"]`
inserts under `entry.source_path` while leaving the mismatch undetected — a latent consistency gap.
**Fix:** Log when `k != entry.source_path`, treat `entry.source_path` as authoritative throughout,
and document that duplicate JSON keys are unrecoverable (last wins).

### WR-07: JSON `Ledger.check` caches the whole file in memory while `LedgerSQLA.check` always reads fresh — undocumented behavioral divergence behind a shared Protocol

**File:** `trezarr/output/ledger.py:112,167-179` vs `trezarr/output/ledger_sqla.py:68-86`
**Issue:** `Ledger` loads the entire ledger into `self._data` once at `__init__` and `check` is a
pure dict lookup with no reload. `LedgerSQLA.check` hits the DB on every call. The two are
documented as swap-transparent via `LedgerProtocol`, but they are not behaviorally equivalent: a
long-lived `Ledger` instance returns stale data if the underlying file changes (and the migration
renames the file out from under any live instance). Phase-4 production uses `LedgerSQLA`, so impact
is low, but the migration path keeps `Ledger` live (migration_runner.py:124-125), and the Protocol
gives no signal that the staleness semantics differ.
**Fix:** Document the caching difference on `LedgerProtocol`, or have `Ledger.check` re-`stat` and
reload on mtime change so the backends are genuinely interchangeable.

### WR-08: `# noqa: F401` dead imports of `LedgerProtocol` mask the absence of any actual Protocol-conformance check

**File:** `trezarr/output/ledger.py:48` and `trezarr/output/ledger_sqla.py:35`
**Issue:** Both modules import `LedgerProtocol` with `# noqa: F401` and a comment claiming the class
"implements this Protocol," but neither class subclasses it and neither file uses the name. There is
therefore NO static guarantee `Ledger`/`LedgerSQLA` satisfy the Protocol; the `@runtime_checkable`
`isinstance` check only validates method *names* exist, not signatures, so a drift (e.g. `check`
losing `async`, a param rename, a return-type change) is uncaught until runtime. The `# noqa`
suppresses the one linter signal (unused import) that would have flagged the situation.
**Fix:** Drop the unused runtime imports and add a type-checked conformance assertion in a test
module, e.g. `def _conforms(x: LedgerProtocol) -> None: ...` then `_conforms(LedgerSQLA(sf))`, so
mypy verifies the structural match instead of relying on a comment.

## Info

### IN-01: `_run_pipeline_steps` types `media_roots: list` (bare `list`, no element type)

**File:** `trezarr/cli.py:212`
**Issue:** Annotated as bare `list` rather than `list[Path]`, inconsistent with the precise typing
used elsewhere in the file.
**Fix:** `media_roots: list[Path]`.

### IN-02: `import dataclasses` performed inside the function body

**File:** `trezarr/db/migration_runner.py:197`
**Issue:** `dataclasses` is imported mid-function while `json`/`os`/`Path` are top-level. The
in-function `ProcessedFile`/`Ledger` imports (124-125) are justified to avoid a cycle, but
`dataclasses` is stdlib with no cycle risk — the inline import is inconsistent noise.
**Fix:** Move `import dataclasses` to the module top.

### IN-03: `bible_db_url` four-slash comment conflates the `://` separator with the absolute-path leading slash

**File:** `trezarr/config.py:120-121`
**Issue:** The comment "Four slashes ... protocol://[empty-host]/abs-path" is right about the URL but
the wording invites a maintainer to mis-derive the relative-path (three-slash) form.
**Fix:** Clarify: `sqlite+aiosqlite:///` (3 slashes) = relative; the 4th slash is the leading `/`
of the absolute path `/config/trezarr.db`.

### IN-04: `address_map` / `relationship_event` self-referential FKs to `character.id` have no covering index, unlike `character`/`term_dictionary`

**File:** `trezarr/bible/models.py:153-208`, `alembic/versions/0001_baseline_bible_schema.py:87-134`
**Issue:** Both tables carry FK columns to `character.id` with no index, while `character` and
`term_dictionary` received explicit `series_id`-prefixed indexes. These tables are empty in Phase 4
(Phase 5/6 populate), so this is forward-looking only (index/perf is out of v1 scope), but the
asymmetry should be a deliberate Phase-5 decision rather than an oversight.
**Fix:** No action this phase; track as a Phase-5 task to add lookup indexes when the tables go live.

---

_Reviewed: 2026-06-01T05:30:11Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
