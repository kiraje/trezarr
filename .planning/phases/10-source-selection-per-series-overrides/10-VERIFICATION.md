---
phase: 10-source-selection-per-series-overrides
verified: 2026-06-02T00:00:00Z
status: passed
score: 10/10
overrides_applied: 0
---

# Phase 10: Source Selection & Per-Series Overrides — Verification Report

**Phase Goal:** When multiple source subtitles exist, read Bazarr's inventory and pick the source language whose honorific/relational system best preserves what Vietnamese needs (zh/ko/ja/th > en for East-Asian content), falling back gracefully — and let power users override source/register/model per series.
**Verified:** 2026-06-02
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Trezarr connects to Bazarr via its API and reads which source-language subtitles already exist for each item (never re-downloading) | VERIFIED | `BazarrClient` in `trezarr/arr/bazarr.py` — pure GET /api/episodes and /api/movies only; `__all__` exports `BazarrClient, BazarrError, SubtitleEntry, BazarrInventoryItem`; all four `except httpx.RequestError` blocks omit `{exc}` body (CR-02 fix: api key never in errors). |
| 2 | Trezarr can translate from any available source-language subtitle to Vietnamese (source-agnostic) | VERIFIED | `scan.select_source_for_item` accepts any language code from Bazarr inventory union filesystem glob. `rank_sources` in `trezarr/source_selection/rank.py` handles arbitrary 2/3-letter codes; `normalize_original_language` maps *arr human-readable names. `sonarr.py:204` and `radarr.py:173` capture `original_language` from `originalLanguage.name`. |
| 3 | When multiple sources exist, Trezarr selects the relationally-richest source (prefers zh/ko/ja/th for East-Asian content) and falls back to whatever is available | VERIFIED | `rank.sort_key` returns `0.0` for native source unconditionally (WR-01 fix: `if original_language and lang.lower() == original_language.lower(): return 0.0`). `rank_sources` sorts by `(sort_key, lang)`. `select_source_for_item` in `scan.py:336` implements the D-109 fallback chain: Bazarr inventory union filesystem glob (CR-01 fix: glob all `{stem}.*.srt`, not `find_source_sub`) → per-series override → `rank_sources` → global priority → first available. |
| 4 | A user can set per-series overrides for source-language preference, register, and model | VERIFIED | Migration 0003 adds `source_lang_override` (JSON nullable) and `model_override` (String nullable) to `series` table; ORM model carries both at `models.py:87-88`; `set_series_overrides()` at `store.py:1685` persists + emits BibleEvent; `PATCH /api/bible/series/{id}/overrides` at `routes/bible.py:401` validates 2-letter codes (T-10-06 422 on invalid), delegates to store; `patchSeriesOverrides()` in `client.ts:333`; `OverridesSection` component in `BibleEditor.tsx` with fifth "Overrides" tab. |

**Score:** 4/4 ROADMAP success criteria verified

### Critical Context Truths (Review Fix Verification)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| CR-01 | Filesystem fallback discovers ALL on-disk languages (not just first-match) | VERIFIED | `scan.py:436-451` — explicit comment "Do NOT use find_source_sub here"; globs `{escaped_stem}.*.srt` and iterates every match via `_LANG_SIDECAR_RE`; adds every matched `m.group(2).lower()` to `available_langs`. |
| CR-02 | BazarrClient API key never leaks into error messages | VERIFIED | All four `except httpx.RequestError` blocks in `bazarr.py` use `f"{type(exc).__name__}"` with no `{exc}` body; commit 6570d4f. |
| WR-01 | Native original-language source is never outranked by non-native fansub | VERIFIED | `rank.py:138-141` — `if original_language and lang.lower() == original_language.lower(): return 0.0` regardless of tier; docstring documents the WR-01 fix explicitly. |
| WR-02 | `translate_file` D-110 Case 1.5: `check_by_output_path` called before foreign-vi skip | VERIFIED | `engine.py:659-670` — `prior_entry = await ledger.check_by_output_path(str(dest))`, only returns `"skipped"` when `prior_entry is None` (truly foreign), otherwise proceeds with richer-source upgrade. |
| WR-03 | Per-series source priority and Bazarr inventory wired into production translate path | VERIFIED | `cli.py:128-221` — `resolve_effective_settings(series_dto, settings)` at line 153; Bazarr inventory fetched at line 162; `select_source_for_item` called at line 190 with `_bazarr_inventory` and `per_series_override`; result resolves to filesystem path via `find_source_sub([best_lang])` at line 202; D-104 `except` block falls back to scan's choice; `source_sub_path` passed to `translate_file` at line 213 with `model=effective_model`. |
| D-113 | Model override threaded from cli.py → translate_file → LLMClient.call() preserving single semaphore | VERIFIED | `translate_file` signature: `model: str | None = None` (engine.py:590); threaded to `_translate_batch` (line 850: `model`) and `_review_batch` (line 984: `model=model`); `LLMClient.call()` accepts `model: str | None` (client.py:63); `_call_with_fallback` computes `effective_model = model or self._model` (line 118); single `self._semaphore` unchanged (D-06). |

**Score:** 6/6 critical context truths verified — total 10/10

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/arr/bazarr.py` | BazarrClient, BazarrError, SubtitleEntry, BazarrInventoryItem | VERIFIED | All four exported in `__all__`; pure-read GET endpoints; api-key-safe error messages |
| `trezarr/source_selection/rank.py` | rank_sources(), normalize_original_language(), sort_key() | VERIFIED | WR-01 fix applied; `sort_key` unconditionally returns 0.0 for native language |
| `trezarr/source_selection/resolve.py` | resolve_effective_settings() pure function | VERIFIED | Returns (source_priority, register, model); per-series non-NULL override wins |
| `trezarr/output/ledger_sqla.py` | check_by_output_path() | VERIFIED | Line 88 — queries ProcessedFile.output_path; declared in LedgerProtocol |
| `trezarr/discover/gap.py` | Case 1.5 branch | VERIFIED | Lines 117-137 — `check_by_output_path(vi_path)` returns `(True, "richer source available — re-translating")` |
| `alembic/versions/0003_per_series_overrides.py` | Migration 0003 | VERIFIED | `revision="0003"`, `down_revision="0002"`; adds source_lang_override (JSON nullable) and model_override (String nullable); reversible downgrade |
| `trezarr/bible/store.py` | set_series_overrides() | VERIFIED | Line 1685; persists override columns + BibleEvent audit in same transaction (D-32) |
| `trezarr/llm/client.py` | LLMClient.call() with optional model kwarg | VERIFIED | Line 63: `model: str | None = None`; `effective_model = model or self._model`; semaphore unchanged |
| `trezarr/web/routes/bible.py` | PATCH /bible/series/{id}/overrides | VERIFIED | Line 401; 2-letter code validation; 422 on invalid; delegates to set_series_overrides via D-81 lock |
| `frontend/src/api/client.ts` | patchSeriesOverrides() + SeriesOverridesRequest | VERIFIED | Line 257/333; PATCH /api/bible/series/{seriesId}/overrides |
| `frontend/src/pages/BibleEditor.tsx` | OverridesSection + fifth tab | VERIFIED | Tab type union includes "overrides" (line 102); tab array entry (line 204); OverridesSection component (line 2208) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `cli.py` | `source_selection/resolve.py` | `resolve_effective_settings(series_dto, settings)` | WIRED | Line 131 lazy import; called at line 153 |
| `cli.py` | `discover/scan.py` | `select_source_for_item(media_item, settings, bazarr_inventory=..., per_series_source_override=...)` | WIRED | Line 180-195; result used to resolve `source_sub_path` |
| `cli.py` | `arr/bazarr.py` | `BazarrClient.from_settings(settings).fetch_episodes(arr_series_id)` | WIRED | Lines 160-169; D-104 degrade on exception |
| `cli.py` | `translate/engine.py` | `translate_file(..., model=effective_model)` | WIRED | Line 213-221 |
| `discover/gap.py` | `output/ledger_sqla.py` | `ledger.check_by_output_path(str(vi_path))` | WIRED | Line 121 |
| `discover/scan.py` | `arr/bazarr.py` | SubtitleEntry/BazarrInventoryItem traversal in select_source_for_item | WIRED | Lines 397-434 |
| `discover/scan.py` | `source_selection/rank.py` | `normalize_original_language`, `rank_sources` | WIRED | Line 381 lazy import; used at lines 459, 472 |
| `translate/engine.py` | `output/ledger_sqla.py` | `ledger.check_by_output_path(str(dest))` | WIRED | Line 660 |
| `translate/engine.py` | `llm/client.py` | `llm_client.call(..., model=model)` | WIRED | Lines 314, 471 (_translate_batch_inner, _review_batch) |
| `web/routes/bible.py` | `bible/store.py` | `set_series_overrides(session_factory, series_id=..., ...)` | WIRED | Line 431 lazy import; called at line 435 |
| `frontend/src/pages/BibleEditor.tsx` | `frontend/src/api/client.ts` | `patchSeriesOverrides(seriesId, payload)` | WIRED | OverridesSection calls patchSeriesOverrides |
| `web/worker.py` | `cli.py` | `process_one_item(eligible_stub, settings, ...)` | WIRED | Line 459; D-62 shared callable — worker inherits all resolve_effective_settings logic |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `cli.py:process_one_item` | `source_sub_path` | `select_source_for_item` → Bazarr inventory + filesystem glob → `rank_sources` | Yes — real Bazarr GET + filesystem scan | FLOWING |
| `cli.py:process_one_item` | `effective_model` | `resolve_effective_settings(series_dto, settings)` → `series.model_override` or `settings.llm_model` | Yes — DB row or config | FLOWING |
| `translate/engine.py:_translate_batch_inner` | `effective_model` in llm_client.call | `model or self._model` | Yes — per-series override or global config | FLOWING |
| `discover/gap.py:is_eligible` | `prior_entry` from `check_by_output_path` | ProcessedFile table query on `output_path` column | Yes — real DB query | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite | `uv run pytest -q --tb=no` | 335 passed, 1 skipped, 3 xfailed, 43 xpassed, 0 failed | PASS |
| Phase 10 specific tests | `uv run pytest tests/arr/test_bazarr.py tests/source_selection/ tests/discover/test_gap.py tests/db/test_migration_0003.py tests/llm/test_client.py tests/web/test_bible_api.py -q --tb=no` | 9 passed, 3 xfailed, 21 xpassed | PASS |
| rank_sources: K-drama ko wins over en | `rank_sources(["en","ko"], "ko")` | `["ko","en"]` — sort_key("ko","ko")=0.0 < sort_key("en","ko")=3.0 | PASS |
| sort_key: native unconditional win | `sort_key("es","es")` | 0.0 (WR-01 fix: no tier-gate) | PASS |

### Probe Execution

No conventional probe scripts declared for this phase. Step 7c: SKIPPED (no probe-*.sh files).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| INTG-02 | 10-01, 10-02 | Connect to Bazarr via API; read source-language subtitle inventory per item (read-only) | SATISFIED | BazarrClient with GET-only endpoints; Bazarr soft-dependency (D-104 degrades when disabled/unreachable) |
| SRC-01 | 10-01, 10-02 | Source-language-agnostic translation | SATISFIED | select_source_for_item handles any language code; rank_sources + normalize_original_language cover arbitrary inputs |
| SRC-02 | 10-01, 10-02 | Relational-richness ranking (zh/ko/ja/th > en for East-Asian) | SATISFIED | rank.py Tier table + sort_key native-bias (WR-01 corrected); fallback chain in select_source_for_item |
| SVC-05 | 10-01, 10-03, 10-04 | Per-series overrides (source-language preference, register, model) | SATISFIED | Migration 0003 columns; set_series_overrides store writer; PATCH /overrides route; OverridesSection UI; resolve_effective_settings wired in process_one_item + worker |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `trezarr/bible/store.py` | 1732 | `old_value=None` hardcoded in set_series_overrides BibleEvent | INFO | WR-04 from REVIEW.md — audit trail records no prior state for override changes; history diff useless for rollback. Not a blocker: review explicitly excluded WR-04 from fix scope; REVIEW-FIX.md confirms only CR-01/CR-02/WR-01/WR-02/WR-03 were in scope. |

No `TBD`, `FIXME`, or `XXX` markers found in Phase 10 modified files.

### Human Verification Required

Human UAT was completed and approved. See `10-HUMAN-UAT.md` — status: passed.

All 13 UAT items were verified by the user on 2026-06-02:
- Overrides tab renders as fifth tab after Register
- Three sections render (Source Language Preference, Model Override, Register)
- Valid source-language chips added/removed correctly
- Invalid codes (non-2-letter) rejected with inline error message
- Save Overrides POSTs to PATCH /api/bible/series/{id}/overrides only
- Override persists across refresh
- Clear source override reverts to inherited global config
- Model override persists across refresh
- Register save is independent (PATCH /register, not /overrides)
- Live Bazarr inventory read confirmed (INTG-02)
- Relationally-richer source selected over English for East-Asian content (SRC-02)

No further human verification is required.

### Gaps Summary

No gaps. All ROADMAP success criteria verified. All five code-review fixes (CR-01, CR-02, WR-01, WR-02, WR-03) confirmed in production code. Test suite passes 335/335. Human UAT approved.

The one outstanding non-critical item (WR-04: `old_value=None` in set_series_overrides audit event) is an INFO-severity warning that was explicitly out-of-scope for the review fix iteration; it does not affect correctness or any ROADMAP success criterion.

---

_Verified: 2026-06-02T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
