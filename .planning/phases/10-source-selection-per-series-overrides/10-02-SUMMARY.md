---
phase: 10-source-selection-per-series-overrides
plan: "02"
subsystem: source-selection
tags: [bazarr, source-selection, rank, ledger, gap-detection, d-110, d-108, intg-02, src-01, src-02, svc-05]

# Dependency graph
requires:
  - plan: "10-01"
    provides: Wave 0 RED test stubs for all Phase-10 modules
provides:
  - BazarrClient with fetch_episodes/fetch_movies + error wrapping (INTG-02)
  - source_selection.rank.rank_sources + normalize_original_language (SRC-02, D-107)
  - source_selection.resolve.resolve_effective_settings (D-112)
  - MediaItem.original_language capture from Sonarr/Radarr (D-108)
  - LedgerSQLA.check_by_output_path + Ledger.check_by_output_path (D-110)
  - gap.py Case 1.5 seam — re-translate from richer source, D-26 intact (D-110)
  - scan.py select_source_for_item + ScanStats.source_upgraded + EligibleItem.source_upgraded
  - config.py bazarr_use_inventory flag (D-104)
affects:
  - 10-03-PLAN (Wave 1 — migration 0003, LLMClient model override, PATCH overrides route)
  - 10-04-PLAN (Wave 2 — Overrides UI)

# Tech tracking
tech-stack:
  added: []  # No new packages — all pre-existing from Phases 1–8
  patterns:
    - "BazarrClient direct-constructor API (base_url, api_key, path_mappings) for test-friendly instantiation"
    - "SecretStr.get_secret_value() at client boundary only (D-11); host via _normalize_arr_host (T-10-02)"
    - "check_by_output_path mirrors check() pattern — WHERE output_path == key"
    - "Case 1.5 two-step guard: check_by_output_path first, fallback to Case 1 D-26 if None"
    - "select_source_for_item: apply_path_mapping + assert_within_media_roots + exists() per Bazarr entry (T-10-03)"
    - "getattr(series_dto, 'register_value', None) for partial-DTO compatibility in resolve.py"

key-files:
  created:
    - trezarr/arr/bazarr.py
    - trezarr/source_selection/__init__.py
    - trezarr/source_selection/rank.py
    - trezarr/source_selection/resolve.py
  modified:
    - trezarr/arr/sonarr.py
    - trezarr/arr/radarr.py
    - trezarr/config.py
    - trezarr/output/ledger_sqla.py
    - trezarr/output/ledger.py
    - trezarr/output/_ledger_protocol.py
    - trezarr/discover/gap.py
    - trezarr/discover/scan.py
    - .planning/phases/10-source-selection-per-series-overrides/10-VALIDATION.md

key-decisions:
  - "BazarrClient uses direct constructor (base_url, api_key, path_mappings) not from_settings() for test-friendly API — stubs use BazarrClient(base_url=..., api_key=...) not settings object"
  - "resolve.py uses getattr(series_dto, 'register_value', None) instead of direct attribute access — minimal test DTOs lack register_value without crashing"
  - "Ledger (JSON backend) implements check_by_output_path via linear scan — acceptable for legacy/test backend only"
  - "gap.py Case 1.5 inserted between existing Cases 1 and 2 — only Case 1 branch grows a sub-branch; Cases 2/3/4 unchanged (D-26/D-27/D-28 fully preserved)"

# Metrics
duration: ~25min
completed: 2026-06-02
---

# Phase 10 Plan 02: BazarrClient + Source Selection + Case 1.5 Idempotency Summary

**BazarrClient inventory client, relational-fidelity ranking (rank_sources), override resolver (resolve_effective_settings), original_language capture (D-108), LedgerSQLA.check_by_output_path, gap.py Case 1.5 source-upgrade seam (D-110), and scan.py select_source_for_item — turning all Wave-0 INTG-02/SRC-01/SRC-02/SVC-05 stubs GREEN with zero regressions**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-02
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

### Task 1: BazarrClient + source_selection package + original_language capture

- Created `trezarr/arr/bazarr.py`: BazarrError (mirrors DiscoveryError), SubtitleEntry dataclass, BazarrInventoryItem dataclass, BazarrClient with `fetch_episodes(series_id)` and `fetch_movies()`. SecretStr resolved at `from_settings()` boundary only (D-11/T-10-02). Host through `_normalize_arr_host` (T-10-04 SSRF choke-point). Path mapping applied to every subtitle path (D-105). Tests use direct constructor `BazarrClient(base_url, api_key, path_mappings)`.
- Created `trezarr/source_selection/__init__.py`: package init with `__all__`.
- Created `trezarr/source_selection/rank.py`: `_TIER` dict (Tier-1: zh/ko/ja/th, Tier-2: id/ms/hi/ta/ar/tr, Tier-3: en), `_ORIG_LANG_NAME_TO_CODE2` mapping 30+ language names, `sort_key()` (final algorithm: native Tier-3 → 0.0, native Tier-1/2 → tier-0.5, else tier), `rank_sources()` with deterministic tie-breaking, `normalize_original_language()`.
- Created `trezarr/source_selection/resolve.py`: `resolve_effective_settings(series_dto, settings)` pure function — per-series source_lang_override/model_override win over global; uses `getattr(series_dto, 'register_value', None)` for DTO compatibility.
- Modified `trezarr/arr/sonarr.py`: `MediaItem.original_language: str | None = None`; captured from `series.get("originalLanguage", {}).get("name")` in `discover_sonarr_items`.
- Modified `trezarr/arr/radarr.py`: same `original_language` capture from `movie.get("originalLanguage", {}).get("name")` in `discover_radarr_items`.
- Modified `trezarr/config.py`: `bazarr_use_inventory: bool = True` (D-104 soft-dependency toggle).

### Task 2: LedgerSQLA.check_by_output_path + gap.py Case 1.5 + scan.py extensions

- Modified `trezarr/output/ledger_sqla.py`: `check_by_output_path(output_path)` — mirrors `check()` but WHERE `ProcessedFile.output_path == key`.
- Modified `trezarr/output/ledger.py`: `check_by_output_path()` on JSON-backed Ledger — linear scan over values; maintains protocol compliance.
- Modified `trezarr/output/_ledger_protocol.py`: `check_by_output_path()` added to `LedgerProtocol` as abstract method — structural protocol check passes for all implementations.
- Modified `trezarr/discover/gap.py`: Case 1.5 (D-110) — when `vi_path.exists() and entry is None`, first call `ledger.check_by_output_path(vi_path)`; if not None → Trezarr owns this vi, return `(True, "richer source available — re-translating")`; if None → original Case 1 D-26 guard fires. D-26/D-27/D-28 fully preserved.
- Modified `trezarr/discover/scan.py`: `EligibleItem.source_upgraded: bool = False`; `ScanStats.source_upgraded: int = 0`; reason classifier for "richer source" (defensive — Case 1.5 is eligible, not skipped); eligible append tracks `source_upgraded=True` for Case 1.5 items; `select_source_for_item()` with D-109 fallback chain + T-10-03 traversal guard on Bazarr paths + D-104 degradation.

## Task Commits

1. **Task 1: BazarrClient + source_selection + original_language** - `bb692a1`
2. **Task 2: LedgerSQLA.check_by_output_path + gap.py Case 1.5 + scan.py** - `762d66e`

## Test Results

**Task 1 verification:**
- `tests/arr/test_bazarr.py`: 5 XPASS (all stubs GREEN)
- `tests/source_selection/test_rank.py`: 6 XPASS (all stubs GREEN)
- `tests/source_selection/test_resolve.py`: 4 XPASS (all stubs GREEN)
- `tests/arr/test_arr_discovery.py`: 2 XPASS D-108 stubs + 9 PASSED existing

**Task 2 verification:**
- `tests/discover/test_gap.py`: 3 XPASS (D-110 trio: source_upgrade_eligible, foreign_vi_unchanged, no_loop_after_upgrade)
- `tests/discover/test_gap_format.py`: 2 XPASS (D-26 non-regression ASS/VTT formats)
- `tests/discover/test_scan.py`: existing scan tests PASSED

**D-26/D-27/D-28 non-regression:**
- All pre-existing gap tests XPASS/PASSED — D-26 foreign-vi guard intact, D-27 hash idempotency intact, D-28 self-output exclusion intact

**Full suite:** 335 passed, 1 skipped, 5 xfailed, 41 xpassed, 0 failed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] BazarrClient constructor API mismatch with test stubs**
- **Found during:** Task 1 verification
- **Issue:** Plan specified `BazarrClient.__init__(settings: TrezarrSettings)` but Wave-0 test stubs call `BazarrClient(base_url="...", api_key="...", path_mappings=[...])` — direct constructor, not settings object
- **Fix:** Implemented direct constructor taking `base_url`, `api_key`, `path_mappings` (for test-friendly API); added `from_settings(cls, settings)` classmethod for production path
- **Files modified:** `trezarr/arr/bazarr.py`

**2. [Rule 1 - Bug] resolve.py AttributeError on minimal test DTOs**
- **Found during:** Task 1 verification — test `_SeriesDto` objects lack `register_value`
- **Issue:** `series_dto.register_value` raised AttributeError for test DTOs without the attribute
- **Fix:** Changed to `getattr(series_dto, 'register_value', None)` — real `SeriesDTO` has the attribute; test mocks without it get None gracefully
- **Files modified:** `trezarr/source_selection/resolve.py`

**3. [Rule 1 - Bug] Ledger (JSON backend) lacks check_by_output_path — broke protocol check and existing gap tests**
- **Found during:** Task 2 full-suite run — 4 test failures
- **Issue:** Adding `check_by_output_path` to `LedgerProtocol` broke `test_ledger_sqla_implements_ledger_protocol` (Ledger not protocol-compliant) and gap tests using JSON-backed Ledger mocks raised AttributeError
- **Fix:** Added `check_by_output_path()` to `trezarr/output/ledger.py` (linear scan over values) — keeps both backends protocol-compliant
- **Files modified:** `trezarr/output/ledger.py`

## Known Stubs

None — all implemented functionality is wired to real logic, not placeholders.

## Threat Flags

No new security-relevant surfaces beyond what was planned in the threat model.
T-10-02 mitigated: BazarrError messages use `_normalize_arr_host(self._host)` only, never api_key.
T-10-03 mitigated: select_source_for_item applies apply_path_mapping + assert_within_media_roots + exists() for every Bazarr-reported path.
T-10-04 mitigated: bazarr_host flows through _normalize_arr_host in from_settings() classmethod.

## Self-Check

Checking created files exist:
- `trezarr/arr/bazarr.py`: exists
- `trezarr/source_selection/__init__.py`: exists
- `trezarr/source_selection/rank.py`: exists
- `trezarr/source_selection/resolve.py`: exists

Checking commits exist:
- `bb692a1`: Task 1 commit
- `762d66e`: Task 2 commit

## Self-Check: PASSED

All created files verified on disk. All commits verified in git log. Full suite 335 passed, 0 failed.
