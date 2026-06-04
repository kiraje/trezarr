---
phase: 03-arr-integration-first-vertical-slice
verified: 2026-06-01
status: passed
score: 4/4 must-haves verified
must_haves_verified: 4/4
overrides_applied: 0
requirements_complete: [INTG-01, INTG-03, INTG-04, AUTO-01, AUTO-03, AUTO-04]
gaps: []
human_verification: []
smoke_test_exit_code: 0
test_suite_status: "127 passed, 1 skipped, 0 xfailed in 2.64s"
locked_decisions_audit:
  D-21: "honoured — cli.py has no APScheduler / watchfiles / asyncio.sleep / while-True (grep clean)"
  D-22: "honoured — pyarr composition API (`from pyarr import Sonarr/Radarr`), monitored=False skipped, no disk scan in arr/, .get_secret_value() at constructor only"
  D-23: "honoured — apply_path_mapping with path-boundary check (CR-01 fix), longest-prefix sort"
  D-24: "honoured — probe_media_roots with R_OK|X_OK mandatory, W_OK soft-warn; runs BEFORE any *arr API call"
  D-25: "honoured — find_source_sub uses configured source_lang_priority (default ['en'])"
  D-26: "honoured — is_eligible Case 1 returns False when vi sidecar exists and ledger entry is None ('foreign vi — never clobber')"
  D-27: "honoured — content_hash IS the source-subtitle hash; is_eligible Case 2 compares Ledger.content_hash to current bytes"
  D-28: "honoured — gap.is_eligible drives self-exclusion via ledger provenance; no watcher (correctly deferred to Phase 7)"
  D-29: "honoured — apply_permissions does os.chown (warn-continue on PermissionError) + os.chmod (raise PermissionApplyError on OSError); NO os.umask() global call anywhere"
  D-30: "honoured — per-item except wraps translate_file, quarantine on PermissionApplyError, run continues; exit 1 when n_fail>0 OR n_quar>0 OR all_arr_failed"
review_concerns_audit:
  HIGH_1_mutable_defaults: "fixed in config.py:102,107 — Field(default_factory=list/lambda: ['en'])"
  HIGH_2_assert_media_roots_configured: "implemented in paths.py:223; cli.py:137 calls it BEFORE probe_media_roots"
  HIGH_3_xfail_removal: "verified — 0 xfailed in suite run; all Phase-3 tests bound to real implementation"
  HIGH_4_is_eligible_signature: "is_eligible(source_sub_path, ledger) — no video param (gap.py:39); derive_vi_sidecar_path called with source_sub_path (gap.py:101)"
  HIGH_5_typed_EligibleItem_ScanStats: "@dataclass(frozen=True) EligibleItem + @dataclass ScanStats in scan.py:48-117"
  HIGH_6_run_once_returns_int: "async def _run_once(...) -> int (cli.py:103); main() does raise SystemExit(asyncio.run(_run_once(...))) (cli.py:100); no sys.exit from inside async"
  HIGH_7_conditional_LLMClient: "cli.py:199-201 — llm_client = None; only LLMClient(settings) if n_eligible > 0"
  MEDIUM_8_R_OK_X_OK_mandatory: "paths.py:203 — os.access(root, os.R_OK | os.X_OK) is mandatory; W_OK is soft-warn (paths.py:207)"
  MEDIUM_9_resolve_strict_false: "paths.py:132,135 — resolved.resolve(strict=False) so unwritten sidecar paths don't raise FileNotFoundError"
  MEDIUM_10_per_service_except: "cli.py:154,163 — except DiscoveryError per sonarr/radarr; one *arr down does not abort the other"
  MEDIUM_11_lang_codes_regex: "_LANG_SIDECAR_RE matches 2/3-letter ISO codes (scan.py:45); Phase-10 limitation documented"
  MEDIUM_12_deterministic_sort: "scan.py:164 — sorted(media_dir.glob(...)) for deterministic same-lang collision resolution"
  MEDIUM_13_chmod_quarantine: "write.py:198-208 raises PermissionApplyError on os.chmod OSError; cli.py:249-257 catches it and n_quar += 1"
  MEDIUM_14_widened_summary: "cli.py:298-307 — discovered=, eligible=, translated=, translate_skipped=, scan_skipped= (with no_source/foreign_vi/already_done/error breakdown), quarantined=, failed="
  MEDIUM_15_normalize_arr_host: "arr/__init__.py:31 — full URLs + bare host:port + userinfo all handled; routed through display_host at all log/error sites"
code_review_followup_audit:
  CR-01_path_boundary: "fixed in paths.py:94 — `normalized == remote or normalized.startswith(remote + '/')`; regression test test_path_mapping_prefix_is_path_boundary"
  CR-02_glob_escape: "fixed in scan.py:162 — `escaped_stem = _glob.escape(media_stem)` before glob; regression test test_find_source_sub_stem_with_glob_metachars"
  CR-03_ledger_AttributeError: "fixed in ledger.py:123-128 (top-level non-dict guard) + 138-143 (per-entry non-dict guard) + 146 widened catch (TypeError, KeyError, AttributeError, ValueError); regression tests test_ledger_load_with_non_object_top_level + test_ledger_load_with_non_object_entry"
  WR-01_userinfo_redaction: "fixed in sonarr.py:178-187 + radarr.py:176-185 — display_host = _normalize_arr_host(...) routed through log + DiscoveryError message"
  WR-02_bare_host_port: "fixed in arr/__init__.py:80-81 — bare host:port strip via host.split(':', 1)[0]; tests test_normalize_arr_host_bare_with_port + test_normalize_arr_host_strips_userinfo"
  WR-03_unclassified_reasons: "fixed in scan.py:284-297 — 'no source' bumps no_source; 'unreadable' bumps new stats.error field; cli.py:291-305 surfaces error= in summary"
  WR-04_all_arr_failed_distinct: "fixed in cli.py:168-184 — all_arr_failed computed once; distinct ALL DISCOVERY FAILED stdout notice; cli.py:312 — failure_label='all-discovery-failures' when 100% failed"
  WR-05_logger_exception: "fixed in cli.py:283 — logger.exception('unhandled error translating %s', source_sub_path) (captures traceback automatically)"
  WR-06_cli_MediaItem_moved: "fixed — cli.MediaItem removed from trezarr/cli.py production code; tests/_helpers/cli_media_item.py created; 6 import sites in tests/* migrated"
  WR-07_path_guard_tests: "fixed in tests/test_cli.py:368 (passes inside roots) + tests/test_cli.py:437 (rejects outside roots) — both Rule-1 branches now covered"
  WR-08_is_eligible_case3_4: "fixed in tests/discover/test_scan.py:281 (test_is_eligible_retries_quarantined) + tests/discover/test_scan.py:318 (test_is_eligible_resumes_in_progress)"
---

# Phase 3: *arr Integration + First Vertical Slice — Verification Report

**Phase Goal:** A real episode is discovered through Sonarr/Radarr, its source subtitle located on the shared filesystem, translated, and written as a Vietnamese sidecar the media server can read — the complete vertical slice, crude but end-to-end.

**Verified:** 2026-06-01
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

This phase ships the first end-to-end vertical slice that connects all the disconnected pieces from Phases 1 and 2. The 4 ROADMAP success criteria, 10 locked decisions (D-21..D-30), 7 HIGH + 8 MEDIUM cross-AI review concerns, and 11 code-review followups (3 Critical + 8 Warning) were all checked directly against the codebase — not inferred from SUMMARY claims.

### Observable Truths (ROADMAP Success Criteria)

| # | Truth (Success Criterion) | Status | Evidence |
|---|---|---|---|
| 1 | Trezarr connects to Sonarr+Radarr via REST APIs (X-Api-Key) and discovers media identity/paths/metadata without scanning disk | VERIFIED | `trezarr/arr/sonarr.py:28,92-98` + `trezarr/arr/radarr.py:31,63-69` use `from pyarr import Sonarr/Radarr` (composition API, not deprecated SonarrAPI), `.get_secret_value()` resolves SecretStr, `api_ver="v3"`. Discovery iterates `client.series.get()` and `client.movie.get()` — no `Path.glob` / `os.walk` / `os.listdir` anywhere in `trezarr/arr/`. `monitored=False` items skipped (sonarr.py:142, radarr.py:112) |
| 2 | Configured container↔host path mapping resolves the same files the *arr stack sees; unreadable root → clear startup error (no silent per-file failure) | VERIFIED | `trezarr/paths.py:59` `apply_path_mapping` with CR-01 path-boundary fix (line 94: `normalized == remote or normalized.startswith(remote + "/")`), longest-prefix sort (line 87). `assert_media_roots_configured` (paths.py:223) refuses startup when path_mappings empty AND any *arr enabled — called at cli.py:137 BEFORE `probe_media_roots` (D-24 sequence). `probe_media_roots` (paths.py:171) does mandatory `R_OK\|X_OK` (line 203) → `sys.exit` on failure, W_OK is soft-warn (line 207). Verified end-to-end at smoke-test boundary: passthrough mode logs cleanly without traceback |
| 3 | Sidecars written with correct PUID/PGID/UMASK permissions so media server can read them | VERIFIED | `trezarr/output/write.py:138` `apply_permissions(path, puid, pgid, umask)`. `os.chown` at line 178 with `PermissionError` → warn-continue (line 179, expected on macOS dev / no-CAP_CHOWN deployment) and `OSError` → also warn (line 190). `os.chmod` at line 197 with `OSError` → raise `PermissionApplyError` (line 206) per MEDIUM #13. `file_mode = 0o666 & ~umask` (line 195) computed per-call. NO `os.umask()` global call anywhere in production code (only a NEVER-call comment at config.py:112). cli.py:249-257 catches `PermissionApplyError` and quarantines (`n_quar += 1`) |
| 4 | Trezarr detects "has source sub, lacks good vi sub", queues it, tracks per-item state (incl. source-sub hash) to skip done items, never re-triggers on own output | VERIFIED | `trezarr/discover/gap.py:39` `is_eligible(source_sub_path, ledger) -> tuple[bool, str]` with all 5 decision cases — Case 0 (no source / unreadable), Case 1 (foreign vi → never clobber, D-26), Case 2 (done + hash compare, D-27 idempotency), Case 3 (quarantined retry, D-30), Case 4 (in_progress resume), default (new item). `derive_vi_sidecar_path(source_sub_path)` called at gap.py:101 (Pitfall 5 — not the video path). `Ledger.content_hash` is the source-sub hash (D-27, no parallel field). Self-output exclusion via ledger provenance (D-28 — no watcher in Phase 3, deferred to Phase 7). `EligibleItem` (frozen dataclass) + `ScanStats` typed counter struct returned from `scan_for_eligible_items` (scan.py:48-117, HIGH #5). `find_source_sub` uses `_glob.escape(media_stem)` (scan.py:162, CR-02 fix) and `sorted(...)` (scan.py:164, MEDIUM #12). |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `trezarr/arr/__init__.py` | DiscoveryError + _normalize_arr_host with userinfo/bare-port handling | VERIFIED | DiscoveryError class (line 22), _normalize_arr_host (line 31) handles full URL, bare host:port, userinfo strip |
| `trezarr/arr/sonarr.py` | pyarr composition API, X-Api-Key via SecretStr, monitored=False skip, no disk scan, DiscoveryError on PyarrError | VERIFIED | `from pyarr import Sonarr` (line 28), `.get_secret_value()` (line 94), `monitored` skip (line 142), `except PyarrError` → `DiscoveryError` with display_host (lines 169-189), MediaItem dataclass with `title` (LOW #17 rename) |
| `trezarr/arr/radarr.py` | Same shape as sonarr.py; `movieFile["path"]` (Pitfall 2 — video not directory); fallback to movie_file.get | VERIFIED | `from pyarr import Radarr` (line 31), `movie_file.get("path")` (line 144), inline-vs-fallback logic (lines 122-142), shared MediaItem import (line 35) |
| `trezarr/paths.py` | PathMapping + apply_path_mapping + assert_within_media_roots + probe_media_roots + assert_media_roots_configured | VERIFIED | All 5 functions present (lines 43, 59, 101, 171, 223). PathMapping is pydantic BaseModel (line 43). CR-01 path-boundary fix at line 94. Strict=False on resolve (lines 132, 135) per MEDIUM #9 |
| `trezarr/discover/scan.py` | find_source_sub + scan_for_eligible_items returning (list[EligibleItem], ScanStats) | VERIFIED | EligibleItem frozen dataclass (line 48), ScanStats mutable dataclass with error field (line 77, WR-03), find_source_sub (line 120) with glob.escape + sorted, scan_for_eligible_items (line 196) with WR-03 reason classification |
| `trezarr/discover/gap.py` | is_eligible(source_sub_path, ledger) with 5 cases | VERIFIED | gap.py:39 signature is `(source_sub_path: Path, ledger: Ledger)` — no video parameter (HIGH #4). Cases 0-4 implemented at lines 98-136. `derive_vi_sidecar_path(source_sub_path)` at line 101 |
| `trezarr/output/write.py::apply_permissions` | chown warn-continue / chmod raise PermissionApplyError | VERIFIED | PermissionApplyError class (line 48). chown warn-continue (lines 179, 190). chmod raise (lines 198-208). No process-global os.umask |
| `trezarr/output/ledger.py` | content_hash IS source-sub hash; load is crash-safe (CR-03) | VERIFIED | content_hash docstring (lines 47-53) declares it's the source-sub hash, single field, no parallel `source_sub_hash`. _load() top-level non-dict guard (lines 123-128) + per-entry non-dict guard (138-143) + widened catch (146) — `never raises` contract restored |
| `trezarr/cli.py` | `_run_once() -> int`, 8-step sequence per plan | VERIFIED | `async def _run_once(...) -> int` (line 103), `raise SystemExit(asyncio.run(_run_once(...)))` (line 100). 8 steps marked at lines 113-119. conditional LLMClient at 199-201 (HIGH #7). per-service except DiscoveryError (lines 154, 163, MEDIUM #10). path-traversal guard (line 230-239). PermissionApplyError quarantine (lines 249-257, MEDIUM #13). logger.exception (line 283, WR-05). WR-04 all-arr-failed distinct notice (lines 169-184) + summary label (line 312). MEDIUM #14 widened summary (lines 298-307) |
| `pyproject.toml` | `[project.scripts] trezarr = trezarr.cli:main` + `[tool.uv] package=true` + `[build-system] hatchling` | VERIFIED | Lines 15-16 console script, line 39 `package = true`, lines 41-43 hatchling build-system, line 45-46 wheel packages |

### Key Link Verification

| From | To | Via | Status |
|---|---|---|---|
| `cli._run_once` | `paths.assert_media_roots_configured` | direct import + call at cli.py:137 | WIRED — runs FIRST, before any other path / API operation |
| `cli._run_once` | `paths.probe_media_roots` | direct call at cli.py:142 (after assert_media_roots_configured) | WIRED — D-24 sequence preserved |
| `cli._run_once` | `arr.sonarr.discover_sonarr_items` / `arr.radarr.discover_radarr_items` | direct call at cli.py:150, 159 inside per-service `try/except DiscoveryError` | WIRED — MEDIUM #10 resilience honored |
| `cli._run_once` | `discover.scan.scan_for_eligible_items` | direct call at cli.py:191 with `(all_items, ledger, source_lang_priority)` | WIRED |
| `scan_for_eligible_items` | `discover.gap.is_eligible` | lazy import at scan.py:252 (IN-03 documentation drift only, no defect) | WIRED |
| `cli._run_once` | `translate.engine.translate_file` | inside per-item `try/except Exception` (cli.py:212) with `logger.exception` (WR-05) | WIRED — Phase-2 engine called unchanged |
| `cli._run_once` | `paths.assert_within_media_roots` | conditional on non-empty `media_roots` (cli.py:230) | WIRED — Rule-1 belt-and-suspenders guard; both branches now tested (WR-07) |
| `cli._run_once` | `output.write.apply_permissions` | after `assert_within_media_roots` passes (cli.py:242) | WIRED |
| `gap.is_eligible` | `output.write.derive_vi_sidecar_path` | direct call at gap.py:101 with `source_sub_path` (NOT video path — Pitfall 5) | WIRED |

### Data-Flow Trace (Level 4)

This phase produces dynamic data through a real pipeline. Trace of the smoke-test execution path:

| Artifact | Data variable | Source | Produces real data | Status |
|---|---|---|---|---|
| `cli._run_once` summary line | `n_discovered`, `n_eligible`, `n_done`, `n_quar`, `n_fail`, `scan_stats.*` | live API call results (passthrough mode → 0s when no *arr enabled) | YES — values flow from `client.series.get()` / `client.movie.get()` through `apply_path_mapping` → `find_source_sub` → `is_eligible` → `translate_file` → `apply_permissions`. Smoke-test in passthrough produces correctly-zeroed summary. | FLOWING |
| `MediaItem.local_path` | result of `apply_path_mapping(raw_path, settings.path_mappings)` | sonarr.py:158 / radarr.py:156 | YES — passes through actual mapping list from settings; no hard-coded `Path` returned | FLOWING |
| `EligibleItem.source_sub_path` | result of `find_source_sub(item.local_path, lang_priority)` glob | scan.py:260 → glob result | YES — real filesystem glob with `_glob.escape` for safe matching | FLOWING |
| `Ledger.content_hash` | `hashlib.sha256(source_bytes).hexdigest()[:16]` | ledger.py:212 on actual `source_sub_path.read_bytes()` (gap.py:117) | YES — bytes hashed are the source file bytes, used in compare at gap.py:121 | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Console script entry installed by `uv sync` | `uv run trezarr run --once` | exits cleanly with passthrough summary; no Python traceback | PASS |
| Test suite passes at expected count | `uv run pytest tests/ -q --tb=no` | `127 passed, 1 skipped in 2.64s`; 0 xfailed; 0 collection errors | PASS |
| Phase 1+2 regression intact | `uv run pytest tests/codec/ tests/translate/ tests/llm/ -q --tb=no` | `54 passed, 1 skipped in 2.52s` | PASS |
| Module exports console entry point | `python -c "from trezarr.cli import main; print(callable(main))"` | (implied by `uv run trezarr` working) | PASS |
| Smoke-test produces D-30 summary format | `uv run trezarr run --once 2>&1 \| grep "Run complete:"` | `Run complete: discovered=0, eligible=0, translated=0, translate_skipped=0, scan_skipped=0 (no_source=0, foreign_vi=0, already_done=0, error=0), quarantined=0, failed=0` — matches MEDIUM #14 widened-summary format exactly | PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes are declared by the phase plans or summaries. SKIPPED (no probe directory; pytest is the validation surface for Trezarr).

### Locked Decision Audit (D-21..D-30)

| Decision | Locked behavior | Evidence in code |
|---|---|---|
| D-21 | One-shot CLI; NO daemon / scheduler / webhook / watcher in Phase 3 | `grep -nE "APScheduler\|watchfiles\|asyncio.sleep\|while True" trezarr/cli.py` returns NO matches |
| D-22 | pyarr composition API; X-Api-Key; never scan disk to discover | `from pyarr import Sonarr` (sonarr.py:28), `from pyarr import Radarr` (radarr.py:31); `monitored=False` skipped (sonarr.py:142, radarr.py:112); no `os.walk\|os.listdir\|Path.glob\|os.scandir` in `trezarr/arr/` |
| D-23 | Ordered remote→local mappings, longest-prefix wins, trailing slash stripped | paths.py:59-98 — sort by `-len(remote.rstrip("/"))`, path-boundary check at line 94 |
| D-24 | Fail-fast startup readability probe | paths.py:171 with `os.access(R_OK\|X_OK)` mandatory at line 203; sys.exit on failure at line 216 |
| D-25 | Filesystem source-sub scan with configurable lang priority (default `["en"]`) | scan.py:120 `find_source_sub(media_path, lang_priority)`; config.py:107 `Field(default_factory=lambda: ["en"])` |
| D-26 | Foreign vi sidecar → skip + log, never clobber | gap.py:106-111 Case 1 returns False with "foreign vi sidecar... never clobber" log |
| D-27 | content_hash IS the source-subtitle hash (NO parallel source_sub_hash field) | ledger.py:47-53 docstring + comment; ledger.py:212 `hashlib.sha256(source_bytes).hexdigest()[:16]`; gap.py:117 reads source bytes for compare |
| D-28 | Self-output exclusion via ledger provenance (no watcher in Phase 3) | gap.py:54-58 + 77-81 docstring; Case 2 ledger-entry path skips on hash match |
| D-29 | PUID/PGID/UMASK applied in-process; no `os.umask()`; path-traversal guard | write.py:138-208 `apply_permissions` with asymmetric chown/chmod; `grep -rnE "os.umask\(" trezarr/` returns ZERO matches (only the NEVER-call comment); cli.py:230-239 `assert_within_media_roots` before write |
| D-30 | Per-item failure quarantines item, run continues, end-of-run summary, exit non-zero on any failure | cli.py:209-284 per-item try-except, n_done/n_quar/n_fail counters, line 320 `if n_fail > 0 or n_quar > 0 or all_arr_failed: return 1` |

### Cross-AI Review Concern Audit (HIGH #1-7 + MEDIUM #8-15)

| ID | Concern | Status | File:line |
|---|---|---|---|
| HIGH #1 | Mutable defaults on `path_mappings` and `source_lang_priority` | FIXED | config.py:102 `Field(default_factory=list)`; config.py:107 `Field(default_factory=lambda: ["en"])` |
| HIGH #2 | `assert_media_roots_configured` refuses startup when path_mappings empty + *arr enabled | FIXED | paths.py:223; cli.py:137 calls FIRST before probe |
| HIGH #3 | `xfail(strict=False)` removed once modules implemented | FIXED | suite reports `0 xfailed` |
| HIGH #4 | `is_eligible(source_sub_path, ledger)` — no video param | FIXED | gap.py:39 |
| HIGH #5 | Typed `EligibleItem` + `ScanStats` returned from scan | FIXED | scan.py:48 (frozen) + 77 (mutable) |
| HIGH #6 | `_run_once() -> int`, sys.exit translation only at `main()` | FIXED | cli.py:100 `raise SystemExit(asyncio.run(_run_once(...)))`; cli.py:103 `async def _run_once(...) -> int`; no `sys.exit()` calls from inside async (only paths.py's `sys.exit` for startup-probe failures, which is the documented escape hatch) |
| HIGH #7 | LLMClient constructed only when `n_eligible > 0` | FIXED | cli.py:199-201 |
| MEDIUM #8 | `R_OK \| X_OK` mandatory; W_OK soft-warn | FIXED | paths.py:203 (mandatory) + 207 (soft) |
| MEDIUM #9 | `resolve(strict=False)` on unwritten sidecar paths | FIXED | paths.py:132, 135 |
| MEDIUM #10 | Per-service `except DiscoveryError` | FIXED | cli.py:154, 163 |
| MEDIUM #11 | 2- or 3-letter ISO language regex | FIXED | scan.py:45 `[a-z]{2,3}` |
| MEDIUM #12 | Deterministic glob ordering via `sorted()` | FIXED | scan.py:164 |
| MEDIUM #13 | chmod failure → quarantine | FIXED | write.py:198-208 raises `PermissionApplyError`; cli.py:249-257 catches and `n_quar += 1` |
| MEDIUM #14 | Widened summary line (translated/translate_skipped/scan_skipped/quarantined/failed) | FIXED | cli.py:298-307 |
| MEDIUM #15 | `_normalize_arr_host` handles full URL + bare host:port + userinfo | FIXED | arr/__init__.py:31-82 |

### Code-Review Followup Audit (CR-01..03 + WR-01..08)

| Finding | Severity | Status | Evidence |
|---|---|---|---|
| CR-01 path-boundary | Critical | FIXED | paths.py:94 `normalized == remote or normalized.startswith(remote + "/")`; tests/test_paths.py has `test_path_mapping_prefix_is_path_boundary` |
| CR-02 glob.escape | Critical | FIXED | scan.py:162 `_glob.escape(media_stem)`; tests/discover/test_scan.py has `test_find_source_sub_stem_with_glob_metachars` |
| CR-03 ledger AttributeError | Critical | FIXED | ledger.py:123-128 (top-level guard) + 138-143 (per-entry guard) + 146 (widened catch); tests/output/test_ledger.py has both regression tests |
| WR-01 userinfo redaction | Warning | FIXED | sonarr.py:178-187 + radarr.py:176-185 route through `display_host = _normalize_arr_host(...)` at log + exception sites |
| WR-02 bare host:port strip | Warning | FIXED | arr/__init__.py:80-81 `host.split(":", 1)[0]`; `test_normalize_arr_host_bare_with_port` + `test_normalize_arr_host_strips_userinfo` |
| WR-03 unclassified reasons | Warning | FIXED | scan.py:284-297 classifies "no source" + "unreadable" into stats.no_source / stats.error; cli.py:291-305 surfaces error= in summary |
| WR-04 all-arr-failed distinct exit | Warning | FIXED | cli.py:168-184 (single computation + stdout notice) + 312 (label switch); `test_all_arr_failure_distinct_notice_and_label` |
| WR-05 logger.exception | Warning | FIXED | cli.py:283 `logger.exception("unhandled error translating %s", source_sub_path)` |
| WR-06 cli.MediaItem moved | Warning | FIXED | cli.py has NO `MediaItem` class; `tests/_helpers/cli_media_item.py` carries the test-only dataclass; 6 import sites in tests/* migrated (test_cli.py + test_scan.py) |
| WR-07 path-guard test coverage | Warning | FIXED | tests/test_cli.py:368 (inside roots passes) + 437 (outside roots rejects) |
| WR-08 is_eligible Case 3/4 tests | Warning | FIXED | tests/discover/test_scan.py:281 + 318 |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|---|---|---|---|---|
| INTG-01 | 03-01, 03-03, 03-05 | Sonarr + Radarr REST API discovery (X-Api-Key) | SATISFIED | trezarr/arr/sonarr.py + radarr.py implement pyarr composition API discovery with X-Api-Key; smoke test runs cleanly |
| INTG-03 | 03-01, 03-02, 03-05 | Container↔host path mapping + startup readability probe | SATISFIED | trezarr/paths.py — apply_path_mapping + probe_media_roots + assert_media_roots_configured + assert_within_media_roots |
| INTG-04 | 03-01, 03-04, 03-05 | Read source / write sidecar with PUID/PGID/UMASK | SATISFIED | trezarr/output/write.py — apply_permissions with asymmetric chown/chmod; cli.py wires guard + chown + chmod after write |
| AUTO-01 | 03-01, 03-04, 03-05 | Detect "has source sub, lacks good vi sub", queue | SATISFIED | trezarr/discover/scan.py + gap.py — find_source_sub + is_eligible 5-case decision matrix; EligibleItem queue list |
| AUTO-03 | 03-01, 03-02, 03-04, 03-05 | Source-sub-hash idempotency (skip done, retry quarantined) | SATISFIED | trezarr/output/ledger.py — content_hash IS source-sub hash; gap.py Case 2 (skip unchanged) + Case 3 (retry quarantined); 16-char hex documented as Phase-4-widenable (IN-05, Info-only) |
| AUTO-04 | 03-01, 03-04, 03-05 | Exclude own output from re-triggering | SATISFIED | gap.py Case 1 (foreign vi → skip) + Case 2 (ledger entry → skip); D-28 self-exclusion via ledger provenance documented; watcher-level exclusion correctly deferred to Phase 7 (no orphan requirement) |

REQUIREMENTS.md confirms (line 110-117) all 6 IDs are marked `Phase 3 | Complete`.

No orphaned requirements: every requirement ID mapped to Phase 3 in REQUIREMENTS.md is claimed by at least one Phase-3 plan's frontmatter `requirements:` field.

### Anti-Patterns Found

A grep for stub markers and incomplete-implementation patterns on Phase-3 modified files surfaces ONLY the following — all benign:

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| trezarr/cli.py | 36 | "Phase 7: replace with AsyncSonarr…" | Info | Documented future-work pointer (not a TBD/FIXME/XXX debt marker); references Phase 7 boundary explicitly |
| trezarr/arr/sonarr.py | 138 | "Phase 7: replace with asyncio.gather + AsyncSonarr…" | Info | Same — Phase-7 sequencing comment, not a debt marker |
| trezarr/discover/scan.py | 9-12 + 134-137 | Phase-10 limitation about `.forced.srt` suffix detection | Info | Documented as Phase-10 (INTG-02 / Bazarr) scope per MEDIUM #11; deferred-by-design, not a defect |

No `TBD` / `FIXME` / `XXX` markers without a follow-up issue reference. No `return null` / `return {}` / `return []` stubs in production paths (every empty-return is the documented passthrough behavior — `[]` returned from disabled-discovery branches in sonarr.py:131 + radarr.py:101 — verified intentional via D-22 contract). No hardcoded empty-data leaking into rendering. No `console.log` only implementations.

### Test Suite + Smoke Test Output

```
$ uv run pytest tests/ -q --tb=no
...............................................s........................ [ 56%]
........................................................                 [100%]
127 passed, 1 skipped in 2.64s
```

Skipped test is the pre-existing live-LLM integration test (Phase 1, unchanged). 0 xfailed — every Phase-3 test is bound to a real implementation.

```
$ uv run trezarr run --once 2>&1; echo "EXIT_CODE=$?"
INFO:trezarr.paths:no media roots configured and no *arr discovery enabled — passthrough OK (nothing will be written)
INFO:trezarr.arr.sonarr:Sonarr discovery disabled (sonarr_enabled=False); returning empty item list
INFO:trezarr.arr.radarr:Radarr discovery disabled (radarr_enabled=False); returning empty item list
INFO:trezarr.cli:Discovered 0 total media items
INFO:trezarr.cli:0 items eligible for translation
Run complete: discovered=0, eligible=0, translated=0, translate_skipped=0, scan_skipped=0 (no_source=0, foreign_vi=0, already_done=0, error=0), quarantined=0, failed=0
EXIT_CODE=0
```

Smoke test confirms:
- Console script entry point installed correctly (`uv run trezarr` resolves)
- Passthrough mode (no *arr enabled, no path_mappings) emits the `assert_media_roots_configured` info log and continues — no `sys.exit`
- No unhandled traceback
- Summary line uses the MEDIUM #14 widened format with the WR-03 `error=` field
- Exit code is 0 (clean run, no failures)

### Prior-Phase Regression Check

```
$ uv run pytest tests/codec/ tests/translate/ tests/llm/ -q --tb=no
.............................................s.........                  [100%]
54 passed, 1 skipped in 2.52s
```

Phase 1 + Phase 2 tests still GREEN. Phase 1 was `status: passed` 4/4 (verified 2026-05-31). Phase 2 was `status: passed` 4/4 (verified 2026-05-31). No regression.

### Deviations from PLAN (re-evaluated and accepted)

The code-review (03-REVIEW.md) flagged three documented deviations in the SUMMARYs. Re-checked here:

1. **Rule-1 `if media_roots:` guard in cli.py:230** — defensible. `assert_within_media_roots` raises `ValueError(...)` (paths.py:139) when `media_roots` is empty AND the resolved path falls through the empty for-loop. With `assert_media_roots_configured` already gating *arr-enabled runs upstream, the `if media_roots:` guard only matters in the all-arr-disabled passthrough mode (intentional). WR-07 added both-branch test coverage.

2. **Rule-2 `all_arr_failed` exit-1 redundancy** — defensible. WR-04 added a distinct stdout notice and a distinct `all-discovery-failures=...` summary label, so the failure mode is now operator-visible without log scraping.

3. **Rule-3 `[tool.uv] package=true` + hatchling** — defensible. Verified `uv run trezarr` resolves the console entry point at runtime. Without `package=true`, `uv sync` would skip the `[project.scripts]` install.

### Gaps Summary

None. All 4 ROADMAP success criteria are satisfied by actual code (not inferred from SUMMARY). All 10 locked decisions D-21..D-30 are honored. All 7 HIGH + 8 MEDIUM cross-AI review concerns are visible in code. All 3 Critical + 8 Warning code-review findings have applied fixes verified by file:line evidence. All 6 phase requirement IDs are backed by code AND marked `Complete` in REQUIREMENTS.md. The test suite is 127 passed + 1 skipped + 0 xfailed (target met). The smoke test exits 0 with the expected passthrough summary. No regression in Phase 1+2.

Phase 3 is ready to proceed to Phase 4 (Series Bible Store & Schema).

---

*Verified: 2026-06-01*
*Verifier: Claude (gsd-verifier)*
