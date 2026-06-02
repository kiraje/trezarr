---
phase: 10-source-selection-per-series-overrides
fixed_at: 2026-06-02T00:00:00Z
review_path: .planning/phases/10-source-selection-per-series-overrides/10-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 10: Code Review Fix Report

**Fixed at:** 2026-06-02
**Source review:** .planning/phases/10-source-selection-per-series-overrides/10-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01, CR-02, WR-01, WR-02, WR-03)
- Fixed: 5
- Skipped: 0

CR-03 (BibleEditor saveTerm/category — pre-existing Phase-8 issue) and all INFO
findings (IN-01, IN-02) were out of scope and left untouched.

## Fixed Issues

### CR-02: Bazarr API key leak in RequestError handlers

**Files modified:** `trezarr/arr/bazarr.py`
**Commit:** 6570d4f
**Applied fix:** Removed `{exc}` from all four `except httpx.RequestError` blocks in
`bazarr.py` (in `fetch_episodes`, `fetch_movies`, `fetch_episode_inventory`,
`fetch_movie_inventory`). Each handler now logs only `{type(exc).__name__}` without
the exception body, which could include request URLs containing credentials.

---

### CR-01: `select_source_for_item` filesystem fallback discovers only one language

**Files modified:** `trezarr/discover/scan.py`
**Commit:** 2aff26a
**Applied fix:** Replaced the single-result `find_source_sub(media_path, [...broad list...])` probe
with a direct glob + `_LANG_SIDECAR_RE` scan that collects ALL language codes present on disk.
The old probe called `find_source_sub` with a hard-coded priority list which returns only the
first-match language, leaving `available_langs` with at most one code and making `rank_sources`
a no-op for filesystem sources. The new scan iterates all `{stem}.*.srt` candidates and adds
every matched language code to `available_langs`, giving `rank_sources` the full candidate set.

---

### WR-01: Native original-language source outranked by non-native Tier-1 fansub

**Files modified:** `trezarr/source_selection/rank.py`
**Commit:** 931ff44
**Applied fix:** The old `sort_key` only returned `0.0` (absolute top) for native languages
when their tier was 3 (e.g. English for a US show). Languages absent from `_TIER` (Spanish,
French, German, etc.) defaulted to `_DEFAULT_TIER=2`, so `sort_key("es", "es") = 1.5` which
was worse than a Korean fansub's `1.0` — the opposite of native-language preference.

Fixed by unconditionally returning `0.0` when `lang == original_language`, regardless of tier.
Non-native sources still rank by relational-richness tier. All existing test cases
(K-drama, US show, tier order, fallback chain) continue to pass.

---

### WR-02: `translate_file` foreign-vi skip bypasses Case 1.5

**Files modified:** `trezarr/translate/engine.py`
**Commit:** 890c5f4
**Applied fix:** The `if entry is None and dest.exists():` guard in `translate_file` returned
`"skipped"` without calling `check_by_output_path`, so a richer-source upgrade approved by
`gap.is_eligible` was silently aborted by the engine's own check.

Mirrored the `gap.py` Case 1.5 logic: before returning `"skipped"`, call
`ledger.check_by_output_path(dest)`. If an entry exists, Trezarr owns this vi from a different
source — proceed with the upgrade (D-110). If no entry exists, it is truly foreign (D-26) and
the skip is preserved. D-26/D-27/D-28 invariants are all preserved; requires human verification
of the logical correctness for the richer-source path.

---

### WR-03: Per-series source priority and Bazarr inventory dead code in `process_one_item`

**Files modified:** `trezarr/cli.py`
**Commit:** 7620118
**Applied fix:** `process_one_item` resolved `_source_priority` and fetched `_bazarr_inventory`
but passed `eligible_item.source_sub_path` (the global scan's choice) directly to `translate_file`.
The D-109 fallback chain was entirely inert.

Wired the resolution: after computing `_source_priority` and `_bazarr_inventory`, call
`select_source_for_item(media_item, settings, bazarr_inventory=_bazarr_inventory, per_series_source_override=...)`.
If a better language is found, resolve it to a filesystem path via `find_source_sub([best_lang])`
and pass that path to `translate_file`. D-104 graceful degradation is preserved: any exception
in the selection block falls back to `eligible_item.source_sub_path`. The per-series model
override (D-113) was already wired and is unchanged.

## Verification

**Backend tests:** `uv run pytest -q` — 335 passed, 0 failed, 1 skipped, 43 xpassed in 8.65s
**Frontend build:** `cd frontend && npm run build` — exit 0 (✓ built in 1.07s)

## Skipped Issues

None.

---

_Fixed: 2026-06-02_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
