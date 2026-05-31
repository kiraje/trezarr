---
phase: "03"
plan: "02"
subsystem: "config + path-mapping foundation"
tags: [wave-1, tdd-green, config, path-mapping, traversal-guard, startup-probe, INTG-03, AUTO-03, D-22, D-23, D-24, D-25, D-27, D-29]
dependency_graph:
  requires:
    - "03-01"                        # Wave-0 RED stubs that go GREEN here
    - "trezarr/config.py"            # extended (additive)
    - "trezarr/output/ledger.py"     # D-27 docstring (additive comment)
  provides:
    - "trezarr/paths.py"             # PathMapping + apply_path_mapping + traversal guard + startup probes
    - "trezarr.config.TrezarrSettings (Phase-3 fields)" # sonarr/radarr conn, path_mappings, source_lang_priority, PUID/PGID/UMASK
    - "LedgerEntry.content_hash (D-27 source-subtitle doc)"
  affects:
    - "03-03 (arr discovery) — build_sonarr_client/build_radarr_client consume sonarr_api_key/radarr_api_key SecretStr fields; discover_*_items calls apply_path_mapping(ep_file['path'], settings.path_mappings)"
    - "03-04 (scan + gap + permissions) — apply_permissions consumes settings.puid/pgid/umask; gap detection compares against LedgerEntry.content_hash"
    - "03-05 (CLI) — main() must call assert_media_roots_configured(settings) BEFORE probe_media_roots(build_media_roots(settings)) per HIGH #2"
tech_stack:
  added: []   # no new runtime deps (pydantic-settings + pydantic already pinned in Phase 1)
  patterns:
    - "Field(default_factory=...) for all mutable defaults on TrezarrSettings (Pydantic v2 safety, 03-REVIEWS.md HIGH #1)"
    - "PathMapping defined in paths.py (stdlib-only layer); config.py imports it — no cycle"
    - "SecretStr for sonarr_api_key + radarr_api_key — resolved only inside build_*_client() per existing project SecretStr convention"
    - "Decision-citation docstrings (D-23/D-24/D-29) on every new module + function — mirrors write.py / ledger.py style"
    - "resolve(strict=False) on traversal guard so not-yet-existing sidecars (write targets) resolve symbolically (MEDIUM #9)"
    - "Hard-fail sys.exit with multi-line actionable error vs soft-fail logger.warning split in startup probe (MEDIUM #8)"
key_files:
  created:
    - trezarr/paths.py
    - .planning/phases/03-arr-integration-first-vertical-slice/03-02-SUMMARY.md
  modified:
    - trezarr/config.py
    - trezarr/output/ledger.py
    - tests/test_paths.py             # all xfail markers removed (HIGH #3 policy)
    - tests/config/test_settings.py   # 3 xfail markers removed (HIGH #3 policy)
decisions:
  - "PathMapping owned by trezarr/paths.py (not config.py) to keep paths.py stdlib-only and break the would-be import cycle paths.py → config.py → paths.py. The minor 'config schema model in a non-config module' smell (codex LOW #18) is accepted in exchange for a clean dep graph."
  - "PUID/PGID default to -1 (POSIX 'leave unchanged' sentinel from os.chown). umask defaults to 0o022 (standard *arr default → 0o644 rw-r--r-- via 0o666 & ~umask). umask is stored as an int only — never applied via os.umask(), which is process-global and unsafe in async code."
  - "probe_media_roots() splits checks into MANDATORY (R_OK|X_OK, sys.exit on fail) and SOFT (W_OK, logger.warning on fail). Read-only mounts are sometimes intentional (PUID/PGID in Phase 7 makes host paths legitimately read-only at probe time) — failing closed on W_OK would prevent valid configurations."
  - "assert_media_roots_configured() is a new HIGH-#2-driven guard called from cli.py BEFORE probe_media_roots(). Without it, an empty path_mappings + sonarr_enabled=True config would silently degrade D-29 to a no-op because build_media_roots() would return [] and assert_within_media_roots() would have nothing to check."
  - "LedgerEntry.content_hash IS the source-subtitle hash (per D-27) — no parallel source_sub_hash field added, per RESEARCH Pitfall 7. Adding a second hash field would create divergence risk between translate_file()'s skip logic and gap-detection's re-translate check."
metrics:
  duration: "~30 min"
  completed: "2026-06-01"
  tasks_completed: 2
  files_created: 1            # trezarr/paths.py
  files_modified: 4           # config.py, ledger.py, tests/test_paths.py, tests/config/test_settings.py
---

# Phase 03 Plan 02: Wave 1 — Config + Path-Mapping Foundation Summary

The configuration contract and path-resolution contract that the entire rest of
Phase 3 (arr discovery, scan/gap, CLI) consumes are in place. `TrezarrSettings`
gains 14 new Phase-3 fields (sonarr/radarr connection × 4 each, `path_mappings`,
`source_lang_priority`, `puid`/`pgid`/`umask`); `trezarr/paths.py` is new and
ships the full path-mapping API (`apply_path_mapping`, `assert_within_media_roots`,
`build_media_roots`, `probe_media_roots`, `assert_media_roots_configured`).
`LedgerEntry.content_hash` is documented as the source-subtitle hash (D-27)
with an explicit note that no parallel `source_sub_hash` field is added
(Pitfall 7).

**Codex review HIGH/MEDIUM concerns folded in:**

- HIGH #1: `path_mappings` and `source_lang_priority` use `Field(default_factory=...)` — verified by `test_path_mappings_no_shared_default_identity` and `test_source_lang_priority_no_shared_default_identity` (two `TrezarrSettings()` instances must return distinct list objects).
- HIGH #2: `assert_media_roots_configured()` exits at startup when `path_mappings` is empty AND any *arr is enabled, preventing the silent D-29 no-op degradation.
- HIGH #3: All 13 path-test xfail markers (8 path-API + 2 mutable-default + 3 in `test_settings.py`) removed after the implementation landed — Phase-3 tests are now plain green, not non-binding xfail scaffolding.
- MEDIUM #8: `probe_media_roots()` mandatorily checks `R_OK | X_OK`; soft-warns on missing `W_OK` (read-only mounts can be intentional).
- MEDIUM #9: `assert_within_media_roots()` uses `resolve(strict=False)` so not-yet-existing sidecar paths (the typical write-target case) resolve symbolically.

## What Was Built

### Task 1: Extend TrezarrSettings (`trezarr/config.py`) + minimal `trezarr/paths.py`

| Field group (D) | Fields added | Notes |
|-----------------|--------------|-------|
| *arr connection (D-22) | `sonarr_host`, `sonarr_port=8989`, `sonarr_api_key: SecretStr`, `sonarr_enabled=False`, `radarr_host`, `radarr_port=7878`, `radarr_api_key: SecretStr`, `radarr_enabled=False` | Both API keys are `SecretStr` — `.get_secret_value()` is resolved only inside Plan 03-03's `build_sonarr_client()` / `build_radarr_client()`, never stored as plain `str` on `self`. Verified by `test_sonarr_api_key_not_in_repr`. |
| Path mapping (D-23) | `path_mappings: list[PathMapping] = Field(default_factory=list)` | `PathMapping` is a pydantic `BaseModel` (not a dataclass) so pydantic-settings can deserialize the JSON env var `TREZARR_PATH_MAPPINGS='[{"remote":"/tv","local":"/data/tv"}]'`. YAML `path_mappings: [{remote: /tv, local: /data/tv}]` also works via the existing `YamlConfigSettingsSource`. Verified by `test_path_mappings_yaml_load`. |
| Source-lang priority (D-25) | `source_lang_priority: list[str] = Field(default_factory=lambda: ["en"])` | Default `["en"]` — each instance gets a fresh list. |
| Permissions (D-29) | `puid: int = -1`, `pgid: int = -1`, `umask: int = 0o022` | `-1` is the POSIX "leave unchanged" sentinel for `os.chown`. `umask` is an int only; never applied via `os.umask()` (process-global, unsafe in async code). `apply_permissions()` in Plan 03-04 will compute `0o666 & ~umask`. |

`trezarr/paths.py` was created with only the `PathMapping` `BaseModel` so
`config.py` could import it without forming a cycle (paths.py is the lower
layer in the dep graph). Task 2 expanded it with the rest of the path-mapping
API.

### Task 2: Implement full `trezarr/paths.py` + ledger D-27 docstring

`trezarr/paths.py` exports five functions plus the `PathMapping` model:

| Function | Purpose | Notes |
|----------|---------|-------|
| `apply_path_mapping(api_path, mappings) -> Path` | D-23 — translate *arr-API path to local path | Sorts mappings by descending `len(remote.rstrip("/"))` so longest-prefix wins regardless of input order. Trailing slashes stripped on both sides before compare (Pitfall 3). No lowercasing (Linux is case-sensitive). Passthrough `Path(api_path)` on no match. |
| `assert_within_media_roots(resolved, media_roots) -> None` | D-29 — path-traversal guard | `resolve(strict=False)` on both target and each root so not-yet-existing sidecars (typical write target case) resolve symbolically (MEDIUM #9). Raises `ValueError` naming the resolved path + configured roots on escape. |
| `build_media_roots(settings) -> list[Path]` | derive allowed roots from config | Deduplicated list of `local` values from `settings.path_mappings`. Order-preserved by first occurrence. |
| `probe_media_roots(media_roots) -> None` | D-24 — fail-fast startup probe | Mandatory: `exists() and is_dir() and os.access(R_OK \| X_OK)` — `sys.exit` with multi-line actionable error on any failure. Soft: missing `W_OK` → `logger.warning` only (MEDIUM #8). |
| `assert_media_roots_configured(settings) -> None` | HIGH #2 — refuse empty-roots config when *arr enabled | `sys.exit` when `path_mappings is empty AND (sonarr_enabled or radarr_enabled)`. Logs INFO when both *arr disabled AND mappings empty (passthrough OK). |

`trezarr/output/ledger.py` D-27 update:

- `LedgerEntry.content_hash` docstring clarified to say `source-subtitle
  content hash (SHA-256[:16] of source file bytes)` and `This IS the
  source-subtitle hash — not the vi-sidecar hash`. Explicit Pitfall-7 note:
  no parallel `source_sub_hash` field is added because two hash fields would
  drift between `translate_file()`'s skip logic and gap-detection's
  re-translate check.

### xfail removal (HIGH #3 policy)

All Plan-03-02 xfail markers removed once the implementation landed:

| Test file | xfails removed | Verification |
|-----------|----------------|--------------|
| `tests/config/test_settings.py` | 3 (`test_sonarr_host_env_override`, `test_sonarr_api_key_not_in_repr`, `test_path_mappings_yaml_load`) | Task 1 |
| `tests/test_paths.py` | 10 (4 mapping + 3 traversal + 3 probe + 1 `assert_media_roots_configured` + 2 mutable-default identity) | 2 mutable-default removed in Task 1 (they only need the config fields); 8 path-API removed in Task 2 (they need the full paths.py) |

Verification command: `! grep -E "xfail" tests/test_paths.py` exits 0.

## Verification Results

```
$ uv run pytest tests/test_paths.py tests/config/ -x -q
20 passed in 0.40s

$ uv run pytest tests/ -q
85 passed, 26 skipped, 3 xfailed in 2.65s
EXIT=0
```

Test counts:

| Run | Before this plan | After this plan | Delta |
|-----|------------------|-----------------|-------|
| `tests/config/` (passed) | 4 | 7 | +3 (Task 1) |
| `tests/test_paths.py` (passed) | 0 | 13 | +13 (2 Task 1 + 11 Task 2) |
| Full suite (passed) | 69 | 85 | +16 |
| Full suite (xfailed) | 8 | 3 | -5 (5 became green; 3 remaining are `test_write.py` apply_permissions stubs for Plan 03-04) |
| Full suite (skipped) | 37 | 26 | -11 (11 path-API stubs went from importorskip-SKIP to PASS) |

Ruff: `uv run ruff check trezarr/config.py trezarr/paths.py trezarr/output/ledger.py` → All checks passed.

Grep verifications (per plan `<verification>`):

```
$ grep -c "source-subtitle" trezarr/output/ledger.py
2

$ grep -c assert_within_media_roots trezarr/paths.py
7

$ grep -c assert_media_roots_configured trezarr/paths.py
2

$ grep -E "Field\(default_factory" trezarr/config.py | grep -c -E "path_mappings|source_lang_priority"
2

$ grep -E "xfail" tests/test_paths.py
(no output — exits 1)
```

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: TrezarrSettings + minimal paths.py | `b9c3c96` | `trezarr/config.py`, `trezarr/paths.py` (PathMapping only), `tests/config/test_settings.py` (3 xfail removed), `tests/test_paths.py` (2 mutable-default xfail removed) |
| Task 2: full paths.py + ledger D-27 + xfail cleanup | `2fb2da2` | `trezarr/paths.py` (expanded), `trezarr/output/ledger.py` (D-27 docstring), `tests/test_paths.py` (8 remaining xfail removed) |

## Deviations from Plan

### `[Rule 3 — Atomic-commit ordering]` Created paths.py in Task 1, expanded in Task 2

**Found during:** Task 1 staging.
**Issue:** The plan as written said Task 1 only touches `trezarr/config.py`. But `config.py` now imports `PathMapping` from `trezarr.paths`; Task 1's verify command (`uv run pytest tests/config/`) would have failed with `ImportError` if `trezarr/paths.py` didn't exist yet. The plan covers this as a "circular import note" but doesn't say how to ship Task 1 atomically.
**Fix:** Created `trezarr/paths.py` in Task 1's commit with the `PathMapping` `BaseModel` only (~25 LoC). Task 2 then expanded the file in-place with the four functions + `apply_path_mapping`. Both commits are independently runnable and `uv run pytest` passes after each.
**Files modified:** `trezarr/paths.py` (created in `b9c3c96`, extended in `2fb2da2`).
**Why this is Rule 3 (auto-fix blocking issue) not Rule 4 (architectural):** the planner already specified the PathMapping-in-paths.py ownership and the import direction (D-23 / 03-PATTERNS.md). The only thing the plan didn't specify was the per-commit split. Splitting the file across two commits preserves the planner's architectural intent and keeps each commit verifiable.

### `[Rule 3 — Verify-spec match]` Lowercased "Source-subtitle" → "source-subtitle" in ledger.py

**Found during:** Task 2 verification.
**Issue:** The plan's `<verification>` command was `grep -n "source-subtitle" trezarr/output/ledger.py`. I initially wrote "Source-subtitle" (sentence-case) which doesn't match the case-sensitive grep.
**Fix:** Updated both occurrences in `ledger.py` to lowercase "source-subtitle" so the verify command finds them.
**Files modified:** `trezarr/output/ledger.py` (line 47-48). Already squashed into commit `2fb2da2` before staging.

### No other deviations

All HIGH and MEDIUM concerns from 03-REVIEWS.md affecting this plan are implemented as specified:

- HIGH #1: `Field(default_factory=...)` on both `path_mappings` and `source_lang_priority` (with identity-isolation tests)
- HIGH #2: `assert_media_roots_configured()` exits on empty-mappings + arr-enabled
- HIGH #3: All Plan-03-02 xfail markers removed after GREEN
- MEDIUM #8: `probe_media_roots()` soft-warns (no exit) on missing W_OK
- MEDIUM #9: `assert_within_media_roots()` uses `resolve(strict=False)`

## Threat Flags

None. This plan touches:

- Configuration model surface (additive only — no behaviour change in existing fields, no schema migration)
- Pure path-string transforms (`apply_path_mapping`) — no I/O
- Filesystem inspection only (`probe_media_roots`, `assert_within_media_roots`) — no writes, no network
- A docstring-only update to `LedgerEntry.content_hash` — no behaviour change

The threat-register dispositions from the plan are all satisfied:

- T-03-02-01 (path-traversal via crafted mapping): `assert_within_media_roots()` ships with `resolve(strict=False)` and parent-resolution semantics so it works on the not-yet-existing write-target case. Test `test_traversal_guard_handles_nonexistent_sidecar` covers this.
- T-03-02-02 (API key in logs): `sonarr_api_key` and `radarr_api_key` are `SecretStr`. Test `test_sonarr_api_key_not_in_repr` covers `str()`, `repr()`, and `model_dump()`.
- T-03-02-03 (empty/broad mappings): `assert_media_roots_configured()` refuses startup. Test `test_assert_media_roots_configured_refuses_when_empty_and_arr_enabled` covers the empty-and-enabled case. Codex review note on overly-broad mappings (e.g. `remote: /, local: /`) is acknowledged but deferred — explicit dangerous-root rejection isn't in this plan's scope; the planner's choice was to rely on the operator configuring sane mappings + assert_within_media_roots enforcement at write time.
- T-03-02-04 (probe fails closed): by design — `sys.exit` with actionable error.

No new network endpoints, no new authentication paths, no new schema migrations.

## Known Stubs

None introduced by this plan. The 3 remaining xfails in the full suite are
all in `tests/output/test_write.py` and target `apply_permissions` /
`PermissionApplyError` — those are Plan 03-04's responsibility (Wave 3) and
correctly remain xfailed at this gate.

## Self-Check: PASSED

Files exist check:
- `trezarr/paths.py`: FOUND
- `trezarr/config.py` (with Phase-3 fields): FOUND (`grep -c "Field(default_factory" trezarr/config.py` → 2)
- `trezarr/output/ledger.py` (with D-27 docstring): FOUND (`grep -c "source-subtitle" trezarr/output/ledger.py` → 2)

Commits exist check:
- `b9c3c96` (Task 1 — TrezarrSettings + minimal paths.py): FOUND
- `2fb2da2` (Task 2 — full paths.py + ledger D-27): FOUND

Test suite check:
- `tests/test_paths.py tests/config/` → 20 passed, exit 0
- Full suite → 85 passed, 26 skipped, 3 xfailed, exit 0
- No xfail markers remaining on this plan's tests
- No regressions on Phase-1/Phase-2 tests

Plan success criteria coverage:
- [x] TrezarrSettings has all Phase-3 fields with `Field(default_factory=...)` for list fields
- [x] SecretStr for sonarr_api_key / radarr_api_key; not exposed in str/repr/model_dump
- [x] `trezarr/paths.py` exports PathMapping, apply_path_mapping, assert_within_media_roots, build_media_roots, probe_media_roots, assert_media_roots_configured
- [x] `assert_media_roots_configured` exits when path_mappings empty AND any *arr enabled
- [x] `probe_media_roots` mandatorily checks R_OK|X_OK, soft-warns on missing W_OK
- [x] `assert_within_media_roots` handles not-yet-existing sidecars via `resolve(strict=False)`
- [x] Longest-prefix matching via descending-length sort
- [x] LedgerEntry.content_hash has D-27 source-subtitle docstring
- [x] All tests/test_paths.py stubs GREEN; xfail markers removed
- [x] All tests/config/ stubs GREEN; xfail markers removed
- [x] Full suite green (no regressions)
- [x] All HIGH-severity concerns from 03-REVIEWS.md affecting this plan addressed

Wave 1 (config + paths foundation) complete. Plan 03-03 (*arr discovery) can
now consume: `settings.sonarr_*` / `settings.radarr_*` for client construction,
`settings.path_mappings` for `apply_path_mapping(ep_file['path'], settings.path_mappings)`,
and the `PathMapping` model for typed mapping records.
