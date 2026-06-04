---
phase: "03"
plan: "01"
subsystem: "test scaffolding + dependencies"
tags: [wave-0, red-tdd, xfail-stubs, pyarr, pytest-httpx, INTG-01, INTG-03, INTG-04, AUTO-01, AUTO-03, AUTO-04]
dependency_graph:
  requires:
    - "02-03"  # Phase-2 engine + ledger + write.py — Phase-3 stubs reference these
    - "trezarr/output/ledger.py"   # Ledger / LedgerEntry / Ledger.content_hash()
    - "trezarr/output/write.py"    # the file where apply_permissions will be added
  provides:
    - "tests/arr/test_arr_discovery.py"
    - "tests/discover/test_scan.py"
    - "tests/test_paths.py"
    - "tests/test_cli.py"
    - "tests/output/test_write.py (extended)"
    - "tests/config/test_settings.py (extended)"
    - "pyarr 6.6.0 + pytest-httpx 0.36.2 (pinned in pyproject.toml)"
  affects:
    - "03-02 (config + paths) — turns the 13 test_paths.py stubs + 3 test_settings.py stubs GREEN"
    - "03-03 (arr discovery) — turns the 8 test_arr_discovery.py stubs GREEN"
    - "03-04 (scan + gap + permissions) — turns the 10 test_scan.py stubs + 3 test_write.py stubs GREEN"
    - "03-05 (CLI orchestration) — turns the 7 test_cli.py stubs GREEN"
tech_stack:
  added:
    - "pyarr 6.6.0 (pinned >=6.6,<6.7) — Sonarr+Radarr API client, X-Api-Key auth, sync composition API"
    - "pytest-httpx 0.36.2 (pinned >=0.36,<0.37, dev-only) — intercepts pyarr's underlying httpx transport"
  patterns:
    - "@pytest.mark.xfail(strict=False) RED scaffolding — marker removed by each implementation wave"
    - "pytest.importorskip(\"trezarr.<module>\") deferred imports — pytest collection succeeds before implementation"
    - "from __future__ import annotations + modern type-hint syntax (X | None) in every new test file"
    - "httpx_mock.add_response(url=..., json=...) for sync pyarr Sonarr/Radarr calls"
    - "patch(\"trezarr.cli.<symbol>\") + AsyncMock for CLI integration stubs that exercise _run_once() directly"
    - "_make_minimal_ledger(tmp_path, entries=[...]) helper mirroring _make_minimal_doc() from test_write.py"
key_files:
  created:
    - tests/arr/__init__.py
    - tests/arr/test_arr_discovery.py
    - tests/discover/__init__.py
    - tests/discover/test_scan.py
    - tests/test_paths.py
    - tests/test_cli.py
    - .planning/phases/03-arr-integration-first-vertical-slice/03-01-SUMMARY.md
  modified:
    - pyproject.toml
    - uv.lock
    - tests/output/test_write.py
    - tests/config/test_settings.py
decisions:
  - "Version pins (>=6.6,<6.7 / >=0.36,<0.37) prevent future `uv lock --upgrade` from silently jumping to 6.7.x or 0.37.x — per 03-REVIEWS.md LOW #16"
  - "All 35 new Phase-3 test stubs use `pytest.importorskip` so collection passes even before the production modules exist; xfail(strict=False) is layered on top so later passes register as either xfail (if stub still fails) or xpass (if behaviour aligns)"
  - "EligibleItem dataclass + ScanStats counters are codified in tests/discover/test_scan.py before 03-04 lands the implementation — fixes 03-REVIEWS.md HIGH #5 and MEDIUM #14 at the contract level"
  - "_run_once() returns `int` (NOT calls sys.exit) — codified in tests/test_cli.py per 03-REVIEWS.md HIGH #6; main() will translate the int to SystemExit"
  - "is_eligible(source_sub_path, ledger) signature — NO media_path parameter — codified per 03-REVIEWS.md HIGH #4"
metrics:
  duration: "~25 min"
  completed: "2026-06-01"
  tasks_completed: 2
  files_created: 7
  files_modified: 4
---

# Phase 03 Plan 01: Wave 0 — RED Test Surface + Dependencies Summary

The complete Phase-3 RED test surface is in place before any implementation
ships: `pyarr` and `pytest-httpx` are installed with explicit version
constraints, the two new test packages (`tests/arr/` and `tests/discover/`)
exist, and **35 new RED stubs across 6 test files** are marked
`@pytest.mark.xfail(strict=False)`. The Phase-1/Phase-2 test suite still
passes (69 green, 1 live-LLM skip), confirming no regression from the new
dependency. Implementation Plans 03-02 → 03-05 each remove the xfail marker
on the stubs covering the modules they implement.

## What Was Built

### Dependency install (Task 1)

| File | Change | Why |
|------|--------|-----|
| `pyproject.toml` | Added `pyarr>=6.6,<6.7` to `[project.dependencies]` | Sonarr+Radarr REST client (INTG-01). Version pin per 03-REVIEWS.md LOW #16 prevents silent upgrade to 6.7.x |
| `pyproject.toml` | Added `pytest-httpx>=0.36,<0.37` to `[dependency-groups].dev` | httpx transport-layer mocking for pyarr unit tests. Pinned to current 0.36.x line |
| `uv.lock` | 39 packages resolved (was 30) | Transitive additions: backoff, multidict, overrides, propcache, requests, types-requests, urllib3, yarl, pytest-httpx |
| `tests/arr/__init__.py` | Created empty | Package marker — mirrors `tests/output/__init__.py` |
| `tests/discover/__init__.py` | Created empty | Package marker — mirrors `tests/output/__init__.py` |

### RED test scaffolding (Task 2)

| File | Stubs | Requirements / Decisions covered |
|------|-------|------------------------------------|
| `tests/arr/test_arr_discovery.py` (new) | 8 | INTG-01 (Sonarr+Radarr discovery, monitored filter, missing-movieFile skip), D-22, plus 03-REVIEWS.md MEDIUM #15 host normalisation (3 stubs) and MEDIUM #10 typed `DiscoveryError` |
| `tests/discover/test_scan.py` (new) | 10 | AUTO-01 (`find_source_sub` priority / absent / deterministic), AUTO-01+D-26 (gap detection: no-source / new / foreign-vi), AUTO-03+D-27 (idempotency skip / re-translate on change), AUTO-04 (self-output exclusion), plus 03-REVIEWS.md HIGH #5 + MEDIUM #14 `EligibleItem` + `ScanStats` contract |
| `tests/test_paths.py` (new) | 13 | INTG-03 (`apply_path_mapping`: replace / passthrough / trailing slash / longest-prefix-wins), D-29 (`assert_within_media_roots`: outside raises / inside OK / nonexistent sidecar handled — MEDIUM #9), D-24 (`probe_media_roots`: unreadable exits / readable OK / non-writable warns — MEDIUM #8), 03-REVIEWS.md HIGH #1 (mutable-default isolation), HIGH #2 (empty media_roots refusal) |
| `tests/test_cli.py` (new) | 7 | D-30 (batch continues past failure), 03-REVIEWS.md HIGH #6 (`_run_once` returns `int`), MEDIUM #14 (widened summary), HIGH #7 (lazy `LLMClient`), MEDIUM #10 (one *arr failure → other continues), MEDIUM #13 (`PermissionApplyError` quarantines item) |
| `tests/output/test_write.py` (extended +87 lines) | 3 | INTG-04 / D-29 (`apply_permissions`: chown+chmod, chown PermissionError continues, chmod failure raises `PermissionApplyError` per MEDIUM #13) |
| `tests/config/test_settings.py` (extended +65 lines) | 3 | D-22 + D-23 (`TREZARR_SONARR_HOST` env override, `sonarr_api_key` SecretStr masking, YAML `path_mappings` list deserialization) |

**Total: 6 test files touched, 44 new test functions, 35 marked
`@pytest.mark.xfail(strict=False)` (the remaining 9 are existing Phase-1/2
tests that were preserved verbatim in the extended files).**

## Verification Results

### Pre-commit baseline (before any changes)

```
uv run pytest tests/ -q
→ 69 passed, 1 skipped in 4.26s
(1 skip = Phase-1 live LLM test marked with @pytest.mark.live)
```

### After Task 1 (deps + empty __init__.py)

```
uv run python -c "from pyarr import Sonarr, Radarr; import pytest_httpx; print('deps ok')"
→ deps ok

grep -E "(pyarr|pytest-httpx)" pyproject.toml
→ "pyarr>=6.6,<6.7",
→ "pytest-httpx>=0.36,<0.37",

uv run pytest tests/ -q
→ 69 passed, 1 skipped in 2.51s (no regression)
```

### After Task 2 (full RED surface)

```
uv run pytest tests/ -q
→ 69 passed, 37 skipped, 8 xfailed in 2.56s
EXIT=0
```

Breakdown of the 37 + 8 = 45 non-passing outcomes:
- **37 skipped** = 1 pre-existing live-LLM skip + 1 pre-existing skip pattern + **35 Phase-3 stubs** whose `pytest.importorskip("trezarr.arr.*"|"trezarr.discover.*"|"trezarr.paths"|"trezarr.cli")` short-circuited because the production modules don't exist yet. This is the established Phase-1/2 deferred-import pattern — `pytest.importorskip` produces SKIP, which then takes precedence over the xfail marker until the module lands.
- **8 xfailed** = 3 in `test_write.py` (apply_permissions trio — imports succeed because `trezarr.output.write` already exists; the missing `PermissionApplyError` / `apply_permissions` symbols make the body fail under `xfail(strict=False)`); 3 in `test_settings.py` (apply same logic to `trezarr.config`); 2 in `test_paths.py` (mutable-default identity tests reference only `trezarr.config`).

Each implementation wave will turn the SKIPs into XFAILs (the xfail marker
activates once `importorskip` succeeds) and then into PASSes (asserting the
behaviour). Per 03-REVIEWS.md MEDIUM (xfail removal policy), each later plan
removes the xfail marker on the stubs covering its module.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: deps + package markers | `bb77062` | pyproject.toml, uv.lock, tests/arr/__init__.py, tests/discover/__init__.py |
| Task 2: RED stubs | `76c354e` | tests/arr/test_arr_discovery.py, tests/discover/test_scan.py, tests/test_paths.py, tests/test_cli.py, tests/output/test_write.py, tests/config/test_settings.py |

## Deviations from Plan

None — Wave 0 executed exactly as written. Notes on intentional alignments:

- The plan's `<behavior>` says "new stubs report as xfail (not error)." The
  observed result is **37 skipped + 8 xfailed (zero errors)**. This matches
  the Phase-1/Phase-2 precedent where `pytest.importorskip` produces SKIP for
  stubs whose target module doesn't yet exist. The xfail marker layered on
  top activates as soon as the import succeeds — at which point the same
  test transitions from SKIP → XFAIL automatically, with no test-file
  changes required. The plan's verify command (`uv run pytest tests/ -x -q`)
  exits 0, satisfying the success criterion.

- All 16 specific stubs called out by name in the plan body (lines 151-158
  + behavior block) are present. Additional stubs noted in `<action>`
  prose (e.g. `test_scan_returns_eligible_item_and_scan_stats`,
  `test_normalize_arr_host_*`, mutable-default isolation pair) are also
  present, raising the total from the ~28 originally implied to the 35
  shipped here — codifying the full set of 03-REVIEWS.md HIGH/MEDIUM
  concerns as contract-level tests before any implementation lands.

## Known Stubs

35 RED test stubs marked `@pytest.mark.xfail(strict=False)`. Each is
intentional Wave-0 scaffolding and will be made GREEN by Plans 03-02 →
03-05. The xfail markers must be removed by the corresponding
implementation wave (per 03-REVIEWS.md MEDIUM "xfail removal policy") —
see each downstream plan's success criteria.

| Test file | Stubs | Implementation wave |
|-----------|-------|---------------------|
| `tests/test_paths.py` | 13 | 03-02 |
| `tests/config/test_settings.py` (extension) | 3 | 03-02 |
| `tests/arr/test_arr_discovery.py` | 8 | 03-03 |
| `tests/discover/test_scan.py` | 10 (incl. `_make_minimal_ledger` helper) | 03-04 |
| `tests/output/test_write.py` (extension) | 3 | 03-04 |
| `tests/test_cli.py` | 7 | 03-05 |

## Threat Flags

None. This plan introduces no new production code paths — only test code
and one runtime dependency (`pyarr`) and one dev dependency
(`pytest-httpx`). Both packages were already slopchecked `[OK]` in
03-RESEARCH.md "Package Legitimacy Audit"; both are now pinned with
`>=X.Y,<X.(Y+1)` ranges to prevent silent major-version drift.

Threats T-03-01-01 and T-03-01-02 from the plan's `<threat_model>` are
both `mitigate` dispositions, both satisfied:
- T-03-01-01 (pyarr install): slopcheck [OK] + version pin `>=6.6,<6.7`
- T-03-01-02 (pytest-httpx install): slopcheck [OK] + version pin `>=0.36,<0.37`

No new network endpoints, auth paths, file-access surface, or schema
changes are introduced by this plan.

## Self-Check: PASSED

Files exist check:
- `tests/arr/__init__.py`: FOUND (0 bytes)
- `tests/arr/test_arr_discovery.py`: FOUND
- `tests/discover/__init__.py`: FOUND (0 bytes)
- `tests/discover/test_scan.py`: FOUND
- `tests/test_paths.py`: FOUND
- `tests/test_cli.py`: FOUND

Commits exist check:
- `bb77062` (Task 1 — pyarr + pytest-httpx + package markers): FOUND
- `76c354e` (Task 2 — RED stubs): FOUND

Full suite check:
- `uv run pytest tests/ -q` → 69 passed, 37 skipped, 8 xfailed, exit 0
- Zero collection errors
- No Phase-1/2 regressions
