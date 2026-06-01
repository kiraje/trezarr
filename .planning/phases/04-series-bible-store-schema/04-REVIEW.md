---
phase: 04-series-bible-store-schema
reviewed: 2026-06-01T00:00:00Z
depth: standard
files_reviewed: 41
files_reviewed_list:
  - alembic/env.py
  - alembic/script.py.mako
  - alembic/versions/0001_baseline_bible_schema.py
  - tests/arr/test_media_item_arr_metadata.py
  - tests/bible/__init__.py
  - tests/bible/conftest.py
  - tests/bible/test_arr_metadata_snapshot.py
  - tests/bible/test_bible_event_audit.py
  - tests/bible/test_carry_forward.py
  - tests/bible/test_dto_boundary.py
  - tests/bible/test_lazy_series_create.py
  - tests/bible/test_merge_inferred.py
  - tests/bible/test_merge_policy_pure.py
  - tests/bible/test_models.py
  - tests/db/__init__.py
  - tests/db/conftest.py
  - tests/db/test_engine.py
  - tests/db/test_migrations.py
  - tests/integration/test_translate_engine_async_ledger.py
  - tests/output/test_ledger.py
  - tests/test_cli.py
  - tests/translate/test_engine.py
  - trezarr/arr/radarr.py
  - trezarr/arr/sonarr.py
  - trezarr/bible/__init__.py
  - trezarr/bible/dto.py
  - trezarr/bible/merge.py
  - trezarr/bible/models.py
  - trezarr/bible/store.py
  - trezarr/cli.py
  - trezarr/config.py
  - trezarr/db/__init__.py
  - trezarr/db/base.py
  - trezarr/db/engine.py
  - trezarr/db/migration_runner.py
  - trezarr/db/session.py
  - trezarr/discover/gap.py
  - trezarr/discover/scan.py
  - trezarr/output/_ledger_protocol.py
  - trezarr/output/ledger.py
  - trezarr/output/ledger_sqla.py
  - trezarr/translate/engine.py
findings:
  critical: 2
  warning: 9
  info: 6
  total: 17
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-06-01T00:00:00Z
**Depth:** standard
**Files Reviewed:** 41
**Status:** issues_found

## Summary

Phase 4 lands a SQLAlchemy 2.0 / Alembic-backed Series Bible store, a JSON→SQLite
ledger migration path, and breaks `Ledger.check`/`record` to async. The merge
engine, lock precedence, and audit trail are correctly implemented and well
tested. However the review surfaces two BLOCKER-class lifecycle defects rooted in
the production startup path (the AsyncEngine built in `_run_once` is never
disposed, and the same leak exists in `tests/test_cli.py`'s end-to-end smoke
test); together these explain the `RuntimeError: Event loop is closed` traceback
called out as execution evidence. A second BLOCKER is the Pydantic v2 `register`
field shadowing `BaseModel.register` (the source of the `UserWarning` flagged by
the execution evidence) — this currently fires at every model construction and
can become a hard error in a future Pydantic release.

Most remaining findings are quality issues: minor duplicated whitelist validation
across `merge_inferred` and `_merge_inferred_in_session`, a redundant
`session.get(...)` in `merge_inferred`, a fragile `session.begin` monkey-patch
in test 10 of `test_merge_inferred.py`, and a small ordering/atomicity nuance in
`migrate_json_ledger_if_needed` that does not violate the documented Pitfall-5
ordering but does leave a window where partial rename failures log at warning
rather than error.

The async-ledger breaking change was correctly threaded through every call site;
the repo-wide grep gate test enforces this at test time.

## Critical Issues

### CR-01: `_run_once` and CLI smoke test never dispose the AsyncEngine — root cause of the `Event loop is closed` warnings

**File:** `trezarr/cli.py:152-164` (production), `tests/test_cli.py:880-894` (test)

**Issue:**
`build_engine(settings)` creates an `AsyncEngine` that holds aiosqlite worker
threads. In `_run_once`, the engine is created on line 153 and assigned to a
local; **there is no `await engine.dispose()` at the end of the function, in
the success path, the failure path, or any `finally` block.** When
`asyncio.run(_run_once(...))` (cli.py:103) returns, the event loop is torn down
while the aiosqlite pool still holds open connections. On the next finalization
attempt, aiosqlite's worker thread tries to schedule a coroutine onto the
already-closed loop and raises `RuntimeError: Event loop is closed`.

This is the exact failure mode called out as execution evidence
("aiosqlite worker threads raise RuntimeError: Event loop is closed during
pytest teardown"). It is **not** a fixture issue — `tests/db/conftest.py`,
`tests/db/test_engine.py`, and `tests/db/test_migrations.py` correctly dispose
their engines. The leak is in **production** (`_run_once`) and in the
**production-path smoke test** at `tests/test_cli.py:809` (`test_run_once_end_to_end_smoke_with_temp_sqlite`), which calls `_run_once` AND
then builds a second `verify_engine` on line 885 to inspect the DB. Both engines
end up undisposed across the run (the second is disposed at line 894, but the
first one built inside `_run_once` is leaked, and the verify_engine is only
disposed on the happy path — no `try/finally`).

In production this also leaks file descriptors and an aiosqlite thread per CLI
invocation — harmless for a one-shot daemon, but the warning is real and the
"async lifecycle is owned end-to-end" invariant the rest of the engine code
goes to lengths to preserve is broken.

**Fix:**
```python
# trezarr/cli.py: wrap the engine in a try/finally that always disposes.
try:
    engine = build_engine(settings)
    await run_migrations_to_head(engine)
    session_factory = build_session_factory(engine)
    ledger: LedgerSQLA = LedgerSQLA(session_factory)
except Exception as exc:
    logger.error("DB startup failed — cannot continue. ...", exc, exc_info=True)
    return 1

try:
    # Step 3.5b — JSON ledger one-shot migration
    try:
        await migrate_json_ledger_if_needed(session_factory, settings)
    except Exception as exc:
        logger.error("JSON ledger migration failed ...", exc, exc_info=True)

    # ... all of Steps 4-8 (discovery, scan, translate, summary, exit code) ...
    return exit_code
finally:
    await engine.dispose()
```

In `tests/test_cli.py::test_run_once_end_to_end_smoke_with_temp_sqlite` wrap
the `verify_engine` in a try/finally too:

```python
verify_engine = _build_engine(settings)
try:
    await _run_migrations(verify_engine)
    verify_factory = _async_sessionmaker(verify_engine, expire_on_commit=False)
    async with verify_factory() as session:
        result = await session.execute(...)
        row = result.fetchone()
finally:
    await verify_engine.dispose()
```

---

### CR-02: `SeriesDTO.register` / `SeriesBibleDTO.register` shadow `BaseModel.register` — `UserWarning` at every model load, may become a hard error

**File:** `trezarr/bible/dto.py:58`, `trezarr/bible/dto.py:165`

**Issue:**
Pydantic v2's `BaseModel` exposes a deprecated `register` classmethod (kept for
v1 compatibility). Declaring a field literally named `register` shadows that
parent attribute, and Pydantic emits:

```
UserWarning: Field name "register" in "SeriesDTO" shadows an attribute in parent "BaseModel"
UserWarning: Field name "register" in "SeriesBibleDTO" shadows an attribute in parent "BaseModel"
```

(the exact warning called out as execution evidence). Two problems:

1. Pydantic has been progressively tightening this — there is a real risk that
   a future Pydantic minor or major version converts this warning into a hard
   `NameError` / `ConfigError`, breaking every model construction.
2. Even today the warning fires *every time the class is constructed/imported*,
   spamming test logs and operator log output. The standard quality bar is
   "no UserWarnings out of production code at startup."

`protected_namespaces=()` does NOT fix this — that config controls the
`model_`-prefixed namespace, not shadowing of inherited attribute names. The
proper fix is one of:

- Rename the field to `register_` or `register_value` and use a Pydantic alias
  (`Field(..., alias="register")`) so the JSON / SQLA-attribute name stays
  `register` while the Python attribute does not shadow `BaseModel.register`.
- Suppress with `Field(..., json_schema_extra={...})` + a per-class
  `model_config = ConfigDict(..., ignored_types=(...))` — clunkier.

Option 1 is cleaner because the SQLA column is already named `register` on the
`Series` model and the `from_attributes=True` ORM bridge can reach it through
the alias.

**Fix:**
```python
from pydantic import BaseModel, ConfigDict, Field

class SeriesDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    # ... other fields ...
    register_: str | None = Field(default=None, alias="register")
    # Same for SeriesBibleDTO.
```

Call sites that already use `dto.register` need to use `dto.register_`. The
`model_validate(row, from_attributes=True)` path keeps working because
`populate_by_name=True` lets Pydantic accept both the alias and the field name.

Alternative if renaming churn is unacceptable: add `import warnings; warnings.filterwarnings("ignore", message=".*shadows an attribute in parent.*BaseModel.*")`
in `trezarr/bible/__init__.py` — but this is a band-aid that hides any *future*
real shadowing warning.

---

## Warnings

### WR-01: `_merge_inferred_in_session` re-fetches a row that the caller already fetched — wasted query + identity-map confusion

**File:** `trezarr/bible/store.py:744` and `trezarr/bible/store.py:291`

**Issue:**
`merge_inferred` performs `row = await session.get(model_cls, entity_dto.id)`
at line 744, then immediately delegates to `_merge_inferred_in_session(session, row, ...)`
which calls `fresh_row = await session.get(type(row), row.id)` at line 291 in
the SAME session. Because SQLAlchemy's identity map returns the same object for
the same primary key inside a single session, the second `get()` returns the
EXACT same Python object as the first — `fresh_row is row` is True. The "fresh
re-read" is therefore an alias of the row the caller already loaded; it is not
fresher.

Concretely: this implementation is fine for the documented stale-DTO scenario
(the stale state is on the *caller-supplied DTO*, not on the SQLA row, and that
DTO is correctly never trusted — the snapshot is built from `fresh_row` at
line 294), but the test `test_stale_dto_old_value_correctness` happens to pass
**because the out-of-band UPDATE was committed and the next session sees it
via the read**, not because a second `session.get` returns a different object.

The wasted query is benign; the misleading "re-read inside the session for
freshness" comment in the docstring is misleading. If the intent is to defeat
identity-map caching (e.g. after an out-of-band write committed in a different
session), use `await session.refresh(row)` or `await session.get(model_cls, id, populate_existing=True)`. Otherwise drop the redundant get and pass `row`
directly to the snapshot.

**Fix:**
```python
# In _merge_inferred_in_session, replace lines 291-294 with:
# session.get inside the open transaction reads the latest committed state
# (this session was opened *after* any concurrent commit). We pass the row in
# directly — the identity map guarantees it's the same Python object the
# caller fetched, and the fresh state is whatever this transaction's SELECT
# saw.
fresh_row = row  # identity-map invariant — no second get needed
fresh_snapshot = dto_cls.model_validate(fresh_row, from_attributes=True)
```

Or, if the intent is to genuinely re-read the row after a possible concurrent
commit, use `populate_existing=True` (which is the right tool for this job):

```python
fresh_row = await session.get(type(row), row.id, populate_existing=True)
```

Either way, document the actual invariant accurately.

---

### WR-02: `merge_inferred` whitelist validation is duplicated against `_merge_inferred_in_session` — drift risk

**File:** `trezarr/bible/store.py:732-739` and `trezarr/bible/store.py:280-286`

**Issue:**
The MERGEABLE_FIELDS whitelist check is performed once in `merge_inferred`
(lines 732-739) BEFORE opening a session, then performed AGAIN in
`_merge_inferred_in_session` (lines 280-286). The two checks are byte-for-byte
identical. If a future change updates the validation rule in one site and not
the other (e.g. adds a per-field type check, or relaxes the error message),
the two will silently drift. The downstream `_upsert_character_in_session` /
`_upsert_term_in_session` codepath calls `_merge_inferred_in_session` directly
without going through `merge_inferred`, so the second copy of the check is the
only one that gates that path.

**Fix:** Remove the validation block in `merge_inferred` and rely on
`_merge_inferred_in_session` as the single source of truth, OR extract the
check into a small helper `_validate_mergeable_fields(entity_type, inferred)`
and call it from both sites. The "fail fast before opening a session" benefit
of the duplicate check is real but small — opening a SQLAlchemy session is
cheap when the transaction has not yet begun.

---

### WR-03: `migrate_json_ledger_if_needed` opens a *new* transaction per JSON entry's collision-check SELECT and commits them as one batch — correct, but the comment claims "single transaction"

**File:** `trezarr/db/migration_runner.py:199-228`

**Issue:**
The function uses `async with session_factory() as session: async with session.begin(): for entry in entries: ...`. The transaction is correctly opened ONCE around the whole loop (good — atomic per Pitfall 5). However the per-entry SELECT-then-INSERT pattern means each JSON entry that already exists in SQLite causes one extra round trip (SELECT) before being skipped. This is N round trips for N entries, which can be slow on a large JSON ledger (5000+ entries).

More importantly: if any *one* INSERT fails (e.g. CHECK constraint violation
because the JSON entry has `status="weird-status"`), the whole transaction
rolls back — `inserted` and `skipped` counters were already incremented in the
Python loop but the corresponding DB rows are gone. The summary log will then
claim "inserted=N" but the DB will have 0 inserted rows.

**Fix:**
Wrap the per-entry INSERT in try/except so an individual bad row is logged-
and-skipped rather than killing the whole migration:

```python
async with session_factory() as session:
    async with session.begin():
        for entry in entries:
            try:
                result = await session.execute(
                    select(ProcessedFile).where(ProcessedFile.source_path == entry.source_path)
                )
                if result.scalar_one_or_none() is not None:
                    skipped += 1
                    continue
                # Defensive: validate enum before INSERT
                if entry.status not in {"done", "quarantined", "in_progress"}:
                    logger.warning("JSON ledger entry %r has invalid status %r — skipping",
                                   entry.source_path, entry.status)
                    skipped += 1
                    continue
                session.add(ProcessedFile(...))
                inserted += 1
            except Exception as exc:
                logger.warning("JSON ledger entry %r failed to migrate: %s — skipping",
                               entry.source_path, exc)
                skipped += 1
                # Note: cannot continue after an IntegrityError without rolling
                # back inside the txn; a SAVEPOINT-per-entry would be needed.
```

Alternatively, validate every entry against the enum/status whitelist BEFORE
opening the transaction so the transaction is guaranteed to succeed.

---

### WR-04: `Ledger.record` (JSON backend) is declared `async def` but performs synchronous blocking file I/O

**File:** `trezarr/output/ledger.py:180-193` (and the underlying `_write` at lines 195-218)

**Issue:**
`Ledger.record` is `async def` to satisfy the LedgerProtocol contract, but its
body is `self._data[...] = entry; self._write()` — a synchronous blocking
write (NamedTemporaryFile + json.dump + os.replace). The "async everywhere — no
sync sqlite3/file I/O in the event loop" mandate quoted in the
`_ledger_protocol.py` docstring is therefore being violated by Ledger itself.
In Phase 4 this only matters during the JSON→SQLite one-shot migration (and in
legacy tests), but as long as `Ledger` remains importable production code will
keep finding it and calling it. The `_write` runs the entire JSON serialize +
fsync sequence on the asyncio event loop thread.

**Fix:** Either deprecate `Ledger` entirely now that `LedgerSQLA` is the
authoritative backend (mark with `DeprecationWarning` on construction), or
wrap `self._write()` in `await asyncio.to_thread(self._write)` so it actually
yields back to the loop. The performance impact is small for tiny ledgers but
the contract is broken.

---

### WR-05: `_upsert_character_in_session` defaults `locked_fields=[]` rather than `None` — silently clobbers a future caller-supplied lock list

**File:** `trezarr/bible/store.py:370-377` and `trezarr/bible/store.py:460-466`

**Issue:**
On first INSERT both `_upsert_character_in_session` and
`_upsert_term_in_session` hard-code `locked_fields=[]`. There is no parameter
to override this; if Phase 8's UI starts calling `upsert_character` to pre-seed
a row with a locked field set (a plausible feature: "user marked role as
canonical before any episode encountered the character"), the lock list will
be silently dropped without ever being persisted. This is not a defect today
because Phase 4 contractually says "Phase 4 never sets locked_fields in
production — only tests" (merge.py:3-4), but the boundary is brittle — any
upsert call that should respect a caller-supplied locked_fields argument
silently doesn't.

**Fix:** Either accept `locked_fields: list[str] | None = None` and respect it
on INSERT, or document the constraint explicitly in the public `upsert_character`
docstring ("locked_fields is not settable through this API; use the Phase 8
lock-management API"). Today the constraint is silently enforced by hard-
coding `[]`.

---

### WR-06: Test 10 `test_no_nested_transactions_in_upsert` monkey-patches `session.begin` on a real session object — fragile and may pass even if a nested transaction is opened indirectly

**File:** `tests/bible/test_merge_inferred.py:481-535`

**Issue:**
The test wraps the session factory in a `_CountingSessionFactory` and patches
`session.begin` on the returned session object. Problems:

1. SQLAlchemy AsyncSession's `begin` is a method on the session class; replacing
   `session.begin` with a closure at the instance level works only because
   Python's attribute lookup checks the instance dict first. Any code path that
   calls `type(session).begin(session)` instead of `session.begin()` would
   silently bypass the counter. Production code goes through `session.begin()`
   today (so the test catches the documented invariant), but the test is one
   refactor away from silently passing on broken code.

2. The counter only increments on `__aenter__` of the `_CountingBeginCM`. If a
   nested transaction is opened via `session.begin_nested()` (SAVEPOINT) or via
   `engine.begin()`, it isn't counted. The test invariant should be "no nested
   `session.begin()` *or* `session.begin_nested()`" — only the first half is
   asserted.

3. The test only exercises the merge path (an EXISTING row). The CREATE path
   (fresh Mary) is exercised in the setup phase but with the un-patched factory,
   so it is not actually verified to use one transaction.

**Fix:** Use SQLAlchemy's `event.listens_for(AsyncSession.sync_session, "after_transaction_create")`
or `before_transaction_create` to count real transaction creations at the
SQLAlchemy event-bus level — this catches both `begin()` and `begin_nested()`
and cannot be bypassed by alternate code paths. Also exercise the CREATE path
with the counter to assert exactly one transaction.

---

### WR-07: Tests inject the SQLA Character `locked_fields = ["role"]` mid-transaction without an explicit COMMIT/refresh boundary — relies on `expire_on_commit=False` for correctness

**File:** `tests/bible/test_merge_inferred.py:72-75` (and similar at lines 214-217)

**Issue:**
The test sets `row.locked_fields = ["role"]` inside an `async with session.begin():` block then exits. Because `expire_on_commit=False` is mandatory (Pitfall 2), the in-Python attribute survives commit — but the test relies on the *commit* having taken place before the next session reads from `get_character`. If a future contributor changes the fixture to `expire_on_commit=True`, this test starts silently passing for the wrong reason (the value is read from a still-uncommitted in-memory cache rather than from a re-fetched DB row).

The test invariant — "lock survives across sessions" — should explicitly verify
that the locked_fields value was committed by issuing a `SELECT` from a separate
session **after** the explicit `await session.commit()` boundary, rather than
relying on `session.begin()` context exit.

**Fix:** add an explicit `await session.commit()` (instead of relying on the
context manager's implicit commit-on-exit) and then re-query in a new session.
Optionally, add a fixture-level assertion that `session_factory().begin().__aexit__`
actually committed.

This is a test-quality finding — it does not affect production behavior — but
it weakens the test's value as a regression guard for D-34.

---

### WR-08: `cli.py` uses `getattr(scan_stats, "error", 0)` even though `ScanStats.error` is always present — defensive code that hides a contract bug if `scan_for_eligible_items` ever returns a non-ScanStats

**File:** `trezarr/cli.py:327`

**Issue:**
`scan_stats` is typed as `ScanStats` (a frozen-ish dataclass with `error: int = 0`).
The `getattr(scan_stats, "error", 0)` fallback never fires for the real return
type. The defensive fallback exists because some CLI tests pass a `MagicMock`
without `error=N` (e.g. `tests/test_cli.py:124`: `MagicMock(scanned=3, no_source=0, foreign_vi=0, already_done=0)` — note: no `error=`). This makes the **production** code apologise for **test** sloppiness.

The risk: if `scan_for_eligible_items`'s real return shape ever changes (a sixth
counter is renamed, or `ScanStats` is replaced with a Pydantic model with a
different field name), the production code will silently report
`scan_error=0` instead of raising AttributeError — operator loses visibility.

**Fix:** drop the `getattr` and require all tests to provide the full
`ScanStats` shape (or use the real `ScanStats(scanned=..., no_source=..., error=0)`
in tests instead of `MagicMock`).

---

### WR-09: `migrate_json_ledger_if_needed` silently logs and returns on rename failure after COMMIT — operator sees only WARNING when SQLite is now divergent from JSON file state

**File:** `trezarr/db/migration_runner.py:240-247`

**Issue:**
After the SQLite commit succeeds (Pitfall 5: COMMIT FIRST), the code attempts
`os.replace(json_path, migrated_bak)`. If the rename fails (cross-device,
permissions, EXDEV), the warning log says "Rows are committed; re-run will
idempotently skip them." That's accurate, but:

1. The log level is `warning`, not `error` — easy to miss in operator output
   when the next startup will log the same warning on every subsequent boot
   until the operator manually moves the file.
2. The JSON file remains in place. On every subsequent startup, the migration
   reads ALL the entries again, performs N idempotent collision-check SELECTs,
   logs the same warning when the rename fails again, and returns. This is
   wasted I/O at startup for every run forever.
3. There is no metric / breadcrumb so the operator can detect the persistent
   state from log scraping easily.

**Fix:** Promote the rename-failed log to `error` level (it's a one-time
unrecoverable operator-action condition, not a recurring transient). Consider
writing a sentinel file (`<json_path>.rename_blocked`) so subsequent startups
short-circuit faster and so log scrapers can detect the condition.

---

## Info

### IN-01: `MERGEABLE_FIELDS["series"]` is `frozenset({"register"})` — once Phase 5 adds more inferred series fields this whitelist will grow with no test enforcement

**File:** `trezarr/bible/store.py:224-228`

**Issue:** No test asserts the contents of `MERGEABLE_FIELDS`. A future PR can
add a new key to the whitelist (or remove one) without a test catching the
contract change. Suggest a `test_mergeable_fields_contract` that pins the
expected sets per entity type — change-detector tests are appropriate for
constants that gate behavior.

---

### IN-02: `derive_vi_sidecar_path` is imported lazily inside `discover/scan.py::scan_for_eligible_items` to "avoid module-load-order cycle" — but no cycle exists

**File:** `trezarr/discover/scan.py:249-252`

**Issue:** The comment claims a cycle would exist if `gap` were imported at
module top-level, but `gap.py` does not import from `scan.py`. Lazy imports
inside hot loops have a measurable overhead (each call performs an import
lookup). The cycle-avoidance rationale is a misdiagnosis. Move the import to
the module top to make the dependency graph explicit.

---

### IN-03: `_lang_sidecar_re` claims to be "case-insensitive to handle the (rare) `.EN.SRT` variants" but the second regex group then `.lower()` so the case-insensitivity is forced into ASCII even for non-Latin codes

**File:** `trezarr/discover/scan.py:45` and line 174

**Issue:** Quality concern — the language code is restricted to `[a-z]{2,3}`
under `re.IGNORECASE`. This is fine for ISO-639 codes (always ASCII) but the
documented intent of "case-insensitive" is partially redundant with the
explicit `.lower()` post-processing. The regex `re.IGNORECASE` flag can be
dropped to make intent clearer, OR the post-processing `.lower()` can be
dropped — both are unnecessary together.

---

### IN-04: `alembic/env.py` skips `fileConfig(config.config_file_name)` when running under pytest — but the detection mechanism is `"_pytest" in sys.modules`

**File:** `alembic/env.py:35-39`

**Issue:** The pytest-detection heuristic is correct for the common case but
brittle: any import that pulls in `_pytest` (e.g. a developer running a script
inside an IDE that auto-imports pytest plugins, or a Sphinx build that loads
pytest as a dependency for autodoc) will silently disable fileConfig. The
heuristic happens to be the same one pytest internally uses, so it's defensible,
but consider `os.environ.get("PYTEST_CURRENT_TEST")` as a stricter alternative.

---

### IN-05: `tests/test_cli.py::test_run_once_constructs_ledger_sqla_not_json_ledger` imports `session_factory` fixture but assigns to `_sf_fixture` unused

**File:** `tests/test_cli.py:700-701`

**Issue:** Dead code — the test never uses `_sf_fixture`. The same test
comment says "use fixture indirectly via MagicMock", which is exactly what
makes the import unused. Remove the import (and the misleading comment).

---

### IN-06: `tests/output/test_ledger.py::test_ledger_schema_drift_skips_bad_entry_keeps_good` and the two CR-03 regression tests access `ledger._data` directly — these tests bypass the async `check()` API to dodge "async complexity in sync test"

**File:** `tests/output/test_ledger.py:232-238, 277-279, 299-302`

**Issue:** Reaching into `_data` is white-box, but the underlying motivation
("the constructor is sync; verifying via `await ledger.check(...)` adds
asyncio_mode requirements to the test") is the design ergonomics being weak —
not a problem with the test. `Ledger._load` happens to be sync because it
runs in `__init__`; that's a defensible Phase-2 design. But the
`async def check` wrapper that does only `self._data.get(...)` is doing nothing
useful — it could have been kept sync and the LedgerProtocol kept the async
shape only for LedgerSQLA. The cleaner fix is to provide a synchronous
`Ledger._peek(source_path)` method for tests and white-box callers, then the
tests don't need to monkey through `_data`.

---

_Reviewed: 2026-06-01T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
