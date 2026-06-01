---
phase: 04-series-bible-store-schema
fixed_at: 2026-06-01T00:00:00Z
review_path: .planning/phases/04-series-bible-store-schema/04-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-06-01T00:00:00Z
**Source review:** `.planning/phases/04-series-bible-store-schema/04-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 11 (2 Critical + 9 Warnings; 6 Info skipped per
  `fix_scope=critical_warning`)
- Fixed: 11
- Skipped: 0

All in-scope findings were applied. The full test suite (`uv run pytest -q
--tb=short`) finishes at **208 passed, 1 skipped, 1 warning** — same
208/1 result as the pre-fix baseline. The two `UserWarning: Field name
"register" ... shadows an attribute in parent "BaseModel"` warnings that
the original review called out as execution evidence are GONE; only one
unrelated `read_srt: malformed SRT block` warning remains (pre-existing,
from `tests/integration/test_translate_engine_async_ledger.py`).

The execution-evidence regressions cited in the review summary
(`RuntimeError: Event loop is closed` from undisposed AsyncEngine, plus
the two register-shadow UserWarnings) are no longer reproducible.

## Fixed Issues

### CR-01: `_run_once` and CLI smoke test never dispose the AsyncEngine

**Files modified:** `trezarr/cli.py`, `tests/test_cli.py`
**Commit:** `19fb6e2`
**Applied fix:** Wrapped the engine + pipeline in a try/finally so
`await engine.dispose()` runs on every exit path of `_run_once`
(success, error-return, exception). Mirrored the same try/finally
around `verify_engine` in
`test_run_once_end_to_end_smoke_with_temp_sqlite`. Extracted steps 4-8
into `_run_pipeline_steps(settings, ledger, media_roots)` so the engine
ownership block stays compact and readable while leaving every existing
patch target (`trezarr.cli.scan_for_eligible_items`,
`trezarr.cli.translate_file`, `trezarr.cli.discover_*_items`, etc.)
intact. Test mocks updated: `_db_patches()` and three direct
`build_engine` patches now return `MagicMock(dispose=AsyncMock())` so
the new `await engine.dispose()` in the finally block has an awaitable
to resolve.

Logic-bug class: NONE — this is a lifecycle fix with deterministic
shape, verified end-to-end by the smoke test under
`-W error::RuntimeWarning` showing the
`RuntimeError: Event loop is closed` traceback no longer appears.

### CR-02: `SeriesDTO.register` / `SeriesBibleDTO.register` shadow `BaseModel.register`

**Files modified:** `trezarr/bible/dto.py`, `trezarr/bible/store.py`,
`tests/bible/test_dto_boundary.py`,
`tests/bible/test_lazy_series_create.py`,
`tests/bible/test_arr_metadata_snapshot.py`
**Commit:** `3420ab2`
**Applied fix:** Renamed the Python attribute on both DTOs to
`register_value` with `Field(default=None, alias="register")` and
`ConfigDict(..., populate_by_name=True)` so the serialised JSON key +
SQLA-bridge column name stay `register`. Updated `load_series_bible` to
pass `register_value=row.register` under the Python field name (no
warning under `populate_by_name=True`).

To avoid `compute_field_changes` doing `getattr(dto, "register", None)`
and getting the inherited deprecated `BaseModel.register` classmethod
(which the reviewer's recommendation glossed over), changed
`_merge_inferred_in_session` to pass the SQLA row itself (not the
Pydantic DTO snapshot) to `compute_field_changes`. The SQLA model still
has `Series.register` as a column attribute, so the inferred dict's
`{"register": ...}` resolves cleanly under plain getattr without
touching Pydantic alias machinery. The no-op return path still builds
the DTO snapshot for the caller, just AFTER the change check rather
than before.

Tests that asserted `dto.register is None` updated to
`dto.register_value is None`. The full bible test suite now passes
under `pytest -W error::UserWarning`.

Logic-bug class: REQUIRES HUMAN VERIFICATION — the rename is purely a
Python-side attribute relocation, but the swap of "DTO snapshot" for
"SQLA row" in compute_field_changes is a behaviour change. Both paths
read the same field values, so by construction the comparison is
equivalent — but reviewer should confirm that the no-op return path
still behaves correctly (return a fresh `dto_cls.model_validate(row)`
snapshot when no changes, vs. the SQLA row when changes apply).

### WR-01: Misleading "fresh re-read" comment in store.py

**Files modified:** `trezarr/bible/store.py`, `trezarr/bible/merge.py`
**Commit:** `b653d9d`
**Applied fix:** Corrected the docstring and inline comment to state
the actual stale-DTO defence: locked + old_value are read OFF THE SQLA
ROW inside the transaction, NOT off the caller's external DTO. The
caller's DTO may carry pre-write state from a prior session; the SQLA
row's attribute values reflect this session's in-flight view. Within
the same `AsyncSession`, `session.get(model, pk)` returns the SAME
Python object via the identity map — it does NOT bypass any cache, so
the previous "fresh re-read" framing was misleading. Called out that
`populate_existing=True` would be the right knob if a TRUE post-commit
re-read across sessions is ever needed. Updated the module-level
`HIGH` finding note and `merge.py`'s `compute_field_changes`
IMPORTANT block to match.

### WR-02: Duplicated MERGEABLE_FIELDS whitelist check

**Files modified:** `trezarr/bible/store.py`
**Commit:** `c0ee236`
**Applied fix:** Introduced
`_validate_mergeable_fields(entity_type, inferred)` as the single
source of truth for the per-entity-type whitelist check. Both
`merge_inferred` (pre-session fail-fast) and `_merge_inferred_in_session`
(defence-in-depth inside the transaction — required because
`_upsert_*_in_session` bypasses the public `merge_inferred`) delegate
here. The defence-in-depth shape is preserved; both call sites just
delegate instead of re-implementing identical logic.

### WR-03: Per-entry INSERT failure rolls back the whole batch

**Files modified:** `trezarr/db/migration_runner.py`
**Commit:** `7a31fba`
**Applied fix:** Added a defensive enum gate that validates
`ProcessedFile.status` against `{"done", "quarantined", "in_progress"}`
in the pre-transaction parse pass (the same pass that already validated
the `LedgerEntry(**...)` shape). Entries with invalid statuses are
log-and-skipped BEFORE the transaction opens, so the SQLite CHECK
constraint cannot fire mid-loop and roll back every good row inserted
earlier. Pre-skipped rows roll up into the same `skipped` total
reported in the "migration complete" log, so the headline counts stay
accurate.

Per the reviewer's recommendation, chose the "validate before opening
the transaction" alternative rather than a SAVEPOINT-per-entry pattern
— simpler, no nested-txn footgun, same guarantee.

### WR-04: `Ledger.record` performs synchronous blocking I/O

**Files modified:** `trezarr/output/ledger.py`
**Commit:** `ba183b4`
**Applied fix:** Replaced `self._write()` in the async `record()`
method with `await asyncio.to_thread(self._write)` so the
`NamedTemporaryFile + json.dump + os.replace` sequence runs on the
default executor and yields back to the asyncio loop. Added an
`import asyncio` at module top. The
"`async everywhere — no sync file I/O in the event loop`" contract on
`_ledger_protocol.py` is now honoured.

### WR-05: `_upsert_*_in_session` hardcodes `locked_fields=[]`

**Files modified:** `trezarr/bible/store.py`
**Commit:** `16d9ab3`
**Applied fix:** Documented the constraint explicitly per the
reviewer's option B (the alternative of accepting a `locked_fields=...`
parameter would be a footgun without also wiring the merge engine to
respect a just-created lock during the same call — out of Phase 4's
scope). Added a `WR-05 (lock-list constraint)` paragraph to both
`upsert_character` and `upsert_term` docstrings pointing future callers
at the Phase 8 lock-management API. Added inline comments at the two
hardcoded `locked_fields=[]` literals so the rationale is visible at
the site of the value.

No behaviour change — the Phase 4 contract from `merge.py:3-4` ("Phase
4 never sets locked_fields in production — only tests") is preserved.

### WR-06: `test_no_nested_transactions_in_upsert` monkey-patches `session.begin`

**Files modified:** `tests/bible/test_merge_inferred.py`
**Commit:** `2a5022a`
**Applied fix:** Rewrote the test to register an
`after_transaction_create` listener on SQLAlchemy's synchronous
`Session` class (the one wrapped by `AsyncSession`). The listener
catches BOTH top-level transactions (the explicit
`async with session.begin():` block in `store.py`) AND SAVEPOINTs
(`begin_nested()`), and cannot be bypassed by alternate code paths
into the txn machinery. Filters for `transaction.parent is None`
(top-level only) and also counts `transaction.nested=True` entries
explicitly so a hypothetical `begin_nested()` regression would trip
the assertion. Both the CREATE path AND the MERGE path are now
exercised under the listener.

### WR-07: Lock-injection tests rely on `expire_on_commit=False` for correctness

**Files modified:** `tests/bible/test_merge_inferred.py`
**Commit:** `dc95fb7`
**Applied fix:** Replaced the
`async with session.begin(): row.locked_fields = ["role"]` setup with
an EXPLICIT `await session.commit()` so the "lock-survives-across-
sessions" invariant (D-34) is the actual subject of the test rather
than relying on the context manager's implicit commit-on-exit. If a
future contributor flips the fixture to `expire_on_commit=True`, the
previous tests would silently pass because the value would be read
from an un-expired in-memory cache; the explicit commit + new-session
re-read via `get_character` closes that gap. Applied to both
`test_lock_blocks_inferred_update_d_34` and
`test_multiple_field_partial_lock`.

### WR-08: `getattr(scan_stats, "error", 0)` defensive fallback

**Files modified:** `trezarr/cli.py`, `tests/test_cli.py`
**Commit:** `19c7072`
**Applied fix:** Dropped the `getattr(..., "error", 0)` fallback in
`trezarr/cli.py`. `ScanStats` is a typed dataclass with `error: int = 0`
(mandatory); the attribute is always present on real returns, and a
future rename of `ScanStats.error` should fail loudly rather than
silently report `error=0` and lose operator visibility. Read
`scan_stats.error` directly in both the `n_scan_skipped` accumulator
and the summary f-string.

Updated all 9 `MagicMock(scanned=..., ...)` sites in `tests/test_cli.py`
that previously omitted `error=` to include `error=0` explicitly, so
the production code is exercised against the full `ScanStats` shape.

### WR-09: JSON-ledger rename failure logs warning + re-fires every startup

**Files modified:** `trezarr/db/migration_runner.py`
**Commit:** `726d997`
**Applied fix:**
1. Promoted the rename-failure log from `warning` → `error` with
   explicit OPERATOR ACTION guidance (cross-device / permissions / EXDEV
   resolution path).
2. Added a sentinel sibling file
   `<json_path>.rename_blocked` written immediately after the rename
   fails. The file contains the failure details and instructions to the
   operator.
3. Added a short-circuit check at the top of
   `migrate_json_ledger_if_needed` so subsequent startups detect the
   sentinel, log at error level (visibility), and return WITHOUT
   re-parsing the JSON file or re-emitting N collision-skip SELECTs.
4. Sentinel-write itself is best-effort: if it fails (truly broken
   filesystem), we log the secondary error but do NOT raise — the
   SQLite commit already succeeded.

This converts the previous "warn forever on every boot" failure mode
into a "log error once, short-circuit on subsequent runs until operator
clears the sentinel" recovery shape.

---

_Fixed: 2026-06-01T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
_Fix scope: critical_warning_
_Suite status post-fixes: 208 passed, 1 skipped, 1 unrelated warning_
_Pre-fix baseline: 208 passed, 1 skipped, 3 warnings (the 2 `register`-shadow UserWarnings are now eliminated)_
