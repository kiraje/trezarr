---
phase: 03-arr-integration-first-vertical-slice
fixed: 2026-06-01
iteration: 1
fix_scope: critical_warning
status: complete
findings_addressed:
  critical_attempted: 3
  critical_fixed: 3
  warning_attempted: 8
  warning_fixed: 8
  info_skipped: 6
final_suite_status: "127 passed, 1 skipped in 2.66s"
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-06-01
**Source review:** `.planning/phases/03-arr-integration-first-vertical-slice/03-REVIEW.md`
**Iteration:** 1
**Scope:** Critical + Warning (Info skipped per scope policy)

## Summary

- Findings in scope: 11 (3 Critical + 8 Warning)
- Fixed: 11
- Skipped: 0
- Info findings deferred: 6 (IN-01..IN-06 — out of scope this iteration)
- Final full-suite status: `127 passed, 1 skipped` (up from baseline `113 passed, 1 skipped`; +14 regression / coverage tests added)

All 11 in-scope findings landed as atomic per-finding commits with their regression tests GREEN.

## Fixed Issues

### CR-01: `apply_path_mapping` uses `str.startswith` without a path-boundary check

**Severity:** Critical
**Files modified:** `trezarr/paths.py:88-93`, `tests/test_paths.py`
**Commit:** `58b444f`
**Applied fix:** Replaced the naked `normalized.startswith(remote)` check with `normalized == remote or normalized.startswith(remote + "/")`. This makes `/tv` stop shadowing `/tvshow` — a real TRaSH-Guides setup scenario where neighbouring roots (e.g. `/tv` + `/tvshow-anime`) silently routed paths to the wrong directory. Added `test_path_mapping_prefix_is_path_boundary` covering passthrough, exact-equality, and child-path cases.

### CR-02: `find_source_sub` glob fails for stems with `[`, `]`, `*`, `?`

**Severity:** Critical
**Files modified:** `trezarr/discover/scan.py:135-150`, `tests/discover/test_scan.py`
**Commit:** `0843c49`
**Applied fix:** Imported `glob as _glob` and ran `_glob.escape(media_stem)` before interpolating into the `Path.glob` pattern. This is now matched as a literal so common *arr filenames like `Show [2024].S01E01.mkv` (where `[2024]` was previously a character class matching `{2,0,4}`) are correctly resolved. Added `test_find_source_sub_stem_with_glob_metachars`.

### CR-03: `Ledger._load` crashes on malformed JSON values (uncaught `AttributeError`)

**Severity:** Critical
**Files modified:** `trezarr/output/ledger.py:97-131`, `tests/output/test_ledger.py`
**Commit:** `c6ee159`
**Applied fix:** Two guards added before iteration. First: if top-level `raw` is not a dict (e.g. a JSON array, scalar, or null), log a warning and start fresh — previously `raw.items()` raised AttributeError before the loop even began. Second: for each entry, check `isinstance(v, dict)` and skip with a warning if not — previously `v.items()` on a scalar/list/None raised AttributeError that escaped the per-entry try/except. Widened the per-entry catch from `(TypeError, KeyError)` to `(TypeError, KeyError, AttributeError, ValueError)`. Added `test_ledger_load_with_non_object_top_level` and `test_ledger_load_with_non_object_entry`. Restores the documented "never raises (Pitfall 4)" contract.

### WR-01 + WR-02: Sonarr/Radarr error logs leak userinfo + bare `host:port` not normalized

**Severity:** Warning (combined commit — same normalizer)
**Files modified:** `trezarr/arr/__init__.py:31-65`, `trezarr/arr/sonarr.py:169-188`, `trezarr/arr/radarr.py:167-186`, `tests/arr/test_arr_discovery.py`
**Commit:** `a0d5c63`
**Applied fix:** Rewrote `_normalize_arr_host` to handle three input shapes: full URLs go through `urlparse` (which strips userinfo and port via `parsed.hostname`) with a defensive netloc-split fallback that explicitly drops `user:pass@` before colon-splitting; bare hosts with `:port` (no scheme — most common docker-compose shape) get the port stripped via `host.split(":", 1)[0]`; bare hostnames pass through unchanged. Then routed the host through `_normalize_arr_host` at the error-log + DiscoveryError-message sites in both `sonarr.py` and `radarr.py` so any embedded `admin:hunter2@host` credentials no longer reach logs or the CLI's `partial-discovery-failures` suffix. Added three tests: `test_normalize_arr_host_bare_with_port`, `test_normalize_arr_host_strips_userinfo`, and `test_sonarr_discovery_error_log_redacts_userinfo_credentials`.

### WR-03: `is_eligible` Case 0 reasons silently un-counted by `ScanStats`

**Severity:** Warning
**Files modified:** `trezarr/discover/scan.py:76-110, 251-292`, `trezarr/cli.py:308-330`, `tests/discover/test_scan.py`
**Commit:** `5b15a6e`
**Applied fix:** Added an `error: int = 0` field to `ScanStats` for transient I/O errors (`"source subtitle unreadable: ..."`), and extended the classifier in `scan_for_eligible_items` to explicitly match `"no source"` (TOCTOU case → `stats.no_source += 1`) and `"unreadable"` (read failure → `stats.error += 1`). Pre-fix, both reasons fell through to a default INFO log and were never counted. Updated cli's summary line to surface the new `error=N` field inside the parenthesised scan-skipped breakdown and to include it in the headline `scan_skipped=` total via `getattr(scan_stats, "error", 0)` (defensive on the MagicMock attribute). Added `test_scan_counts_unreadable_source_into_error_bucket` and `test_scan_counts_toctou_no_source_into_no_source_bucket` using `monkeypatch.setattr(gap_mod, "is_eligible", ...)` to drive each reason path deterministically.

### WR-04: All-*arr-failed condition logged but didn't return — misleading message

**Severity:** Warning
**Files modified:** `trezarr/cli.py:201-220, 319-336`, `tests/test_cli.py`
**Commit:** `5065941`
**Applied fix:** Computed `all_arr_failed` once at the discovery step, kept the `logger.error` (escalated wording to include "N of M"), printed a distinct one-line operator notice `"ALL DISCOVERY FAILED — see logs above; the run will exit non-zero after the summary line."` on stdout BEFORE the summary, and switched the summary-line suffix label from `partial-discovery-failures=[...]` to `all-discovery-failures=[...]` when every enabled *arr failed. The exit-code disjunction at the bottom is unchanged (still exit 1) — `all_arr_failed` is now computed only once at the top. Added `test_all_arr_failure_distinct_notice_and_label` asserting exit code 1, the distinct stdout notice, the new label, AND the cross-check `logger.error`. Did NOT switch to an early-return: the existing fall-through to the summary line preserves symmetry with the partial-failure case, which makes log parsers happier.

### WR-05: Translate loop swallowed tracebacks

**Severity:** Warning
**Files modified:** `trezarr/cli.py:302-310`
**Commit:** `6edf503`
**Applied fix:** Changed `logger.error("unhandled error translating %s: %s", source_sub_path, exc)` to `logger.exception("unhandled error translating %s", source_sub_path)`. `logger.exception` automatically captures the active exception's traceback via `exc_info=True`, restoring operator visibility into root cause for unexpected failure modes (the D-30 batch-resilience intent — "one bad item never aborts the slice" — is preserved; we only widened the log payload).

### WR-06: `cli.MediaItem` was dead code in the production import graph

**Severity:** Warning
**Files modified:** `trezarr/cli.py:25-95`, `tests/_helpers/__init__.py` (new), `tests/_helpers/cli_media_item.py` (new), `tests/test_cli.py:38-50`, `tests/discover/test_scan.py:8, 339, 401, 431`
**Commit:** `918518d`
**Applied fix:** Created `tests/_helpers/cli_media_item.py` carrying the test-only `MediaItem` dataclass (same fields), with a docstring explicitly noting production constructs `trezarr.arr.sonarr.MediaItem` via `discover_*_items`. Migrated all four `from trezarr.cli import MediaItem` references (1 in `tests/test_cli.py::_make_media_item`, 3 in `tests/discover/test_scan.py`) to `from tests._helpers.cli_media_item import MediaItem`. Removed the dataclass + its imports (`dataclass`, `Path`) from `trezarr/cli.py` and updated the module docstring to explain the move. Full suite confirmed at 123 passing immediately after this commit (= original 113 baseline + 10 new tests from CR-01..WR-03 + WR-04 added so far).

### WR-07: Tests didn't exercise the `if media_roots:` Rule-1 path-guard branches

**Severity:** Warning
**Files modified:** `tests/test_cli.py:300-430` (two new tests inserted before chmod test)
**Commit:** `6df7e1f`
**Applied fix:** Added `test_run_once_path_guard_passes_inside_media_roots` and `test_run_once_path_guard_rejects_outside_media_roots`. Both configure a real `PathMapping(remote="/tv", local=str(tmp_path / "media"))` via `settings_factory`, leave `assert_within_media_roots` un-mocked (it's the system under test), and assert behavior end-to-end through `_run_once`. The inside-root test verifies exit 0 + `translated=1`; the outside-root test verifies exit 1, `failed=1`, `apply_permissions` was NEVER called (chmod must not run when the guard rejects), AND that an error log mentioning "path-traversal guard" fires. Required no production changes — the guard branches were already correct, just untested.

### WR-08: Missing tests for `is_eligible` Case 3 (quarantined retry) + Case 4 (in_progress resume)

**Severity:** Warning
**Files modified:** `tests/discover/test_scan.py:255-329` (two new tests inserted before `test_foreign_vi`)
**Commit:** `339186e`
**Applied fix:** Added `test_is_eligible_retries_quarantined` and `test_is_eligible_resumes_in_progress`. Both use the existing `_make_minimal_ledger` helper to seed a ledger entry with the relevant status, then assert `is_eligible(src, ledger)` returns `(True, ...)` with the reason mentioning "quarantin" or "in_progress"/"resuming" respectively. Closes the D-30 quarantine-retry coverage gap (Case 3) and the defensive crashed-run-recovery path (Case 4). Required no production changes.

## Skipped Issues

None — all 11 Critical + Warning findings were addressed in this iteration.

## Out-of-Scope (Info findings deferred to a future review pass)

Per the `critical_warning` fix-scope policy, these 6 Info findings were intentionally not addressed:

- **IN-01** test name `test_foreign_vi` is misleading
- **IN-02** Radarr defensive branch on `movieFileId is None` is untested
- **IN-03** `scan_for_eligible_items` lazy import has stale comment ("module-load-order cycle" — no such cycle exists)
- **IN-04** second-tier `OSError` catch on `os.chown` is dead code in practice
- **IN-05** `Ledger.content_hash` truncates to 64 bits (Phase 4 widening discussion)
- **IN-06** unnecessary ternary on `_yaml_file=None` in cli Step 1

All six are noise/cleanup hazards rather than defects and can be batched into a future maintenance pass.

---

_Fixed: 2026-06-01_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
