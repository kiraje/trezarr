---
phase: 05-three-pass-pronoun-engine
verified: 2026-06-02T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run translate_file against a real episode SRT with a live OpenAI-compatible endpoint; inspect the produced .vi.srt for correct Vietnamese pronoun pairing (anh/em, chị/em, etc.) on character dialogue"
    expected: "The same character pair (e.g. John speaking to Mary) consistently uses the same Vietnamese pronoun pair (e.g. anh/em) across all dialogue lines in the episode; no intimate-pronoun flip between consecutive lines of the same speaker"
    why_human: "End-to-end pronoun quality requires a real LLM response with actual Vietnamese output; the consistency test uses a mock that echoes hints but cannot validate that a live model correctly follows the pronoun-pair instruction"
  - test: "Toggle enable_pass1_analysis=False in settings and run translate_file with eligible_item + session_factory supplied; verify Pass 2 attribution still runs"
    expected: "analyze_file returns empty BibleAnalysis (no LLM call), merge_bible_analysis is called but writes nothing; attribute_batch still runs and reconcile_attributions still runs (WR-02 fix)"
    why_human: "The WR-02 fix changes gate semantics (removed outer enable_pass1_analysis gate); confirming the toggle chain works end-to-end under a real run requires a live session, not a grep"
---

# Phase 5: Three-Pass Pronoun Engine Verification Report

**Phase Goal:** The translation pipeline becomes Bible-aware: Pass 1 analyzes the full file into the Bible (building the directed Address Map), Pass 2 infers speaker/addressee per line and applies the correct Vietnamese pronoun pair. This is the core differentiator.
**Verified:** 2026-06-02
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Pass 1 analyzes the full source file + metadata to build/update the Bible (directed Address Map, per-ordered-pair self/address terms) BEFORE Pass 2/3 translate any line (ENG-04 barrier ordering) | VERIFIED | `engine.py:583-605`: `analyze_file` + `merge_bible_analysis` complete inside a `try/except BibleAnalysisError` block; Bible reloaded at line 605; only then does Pass 2 `attribute_batch` gather begin at line 622. Both `test_pass1_runs_before_pass3` and `test_pronoun_consistency_within_episode` PASSED. |
| 2 | Pass 2 infers speaker/addressee per line and applies the correct pronoun pair from the Address Map (PRON-01/02) | VERIFIED | `attribute.py`: `AttributionConfidence`, `LineAttribution`, `BatchAttribution`, `attribute_batch()` all present; name-matching post-processing converts unknown names to None. `reconcile.py`: `reconcile_attributions()` builds `resolved_map`; engine builds `per_batch_hints` from resolved_map and injects into `build_translate_prompt` as `"(speaker says: X; addresses as: Y)"` prefix. All 8 attribute/reconcile/pronoun-engine tests PASSED. |
| 3 | The same character pair keeps the same pronoun pair across an episode (no flips; reciprocal coherence) — a DETERMINISTIC code property in reconcile.py; CR-02's fix made `test_pronoun_consistency_within_episode` actually exercise hint injection | VERIFIED | CR-02 fix confirmed in `test_pronoun_engine.py:142-255`: mock LLM captures `captured_prompts`, `_build_pass3_response` echoes hint terms back only when hints are injected, assertions at lines 236/240 check both `"(speaker says: anh; addresses as: em)"` and the reciprocal `"(speaker says: em; addresses as: anh)"` appear in captured Pass-3 prompts; lines 251/255 assert `"anh"` and `"em"` appear in output file. A broken hint/reconcile/bridge pipeline fails this test. `test_pronoun_consistency_within_episode` PASSED. |
| 4 | Low-confidence attribution falls back to a safe register, never a wrong intimate pronoun (PRON-03 / D-45), and a Tier-3-only endpoint degrades gracefully rather than quarantining (D-47) | VERIFIED | `reconcile.py:96-124`: `get_safe_default(None, settings)` returns `("tôi", "bạn")` (neutral/polite, confirmed by spot-check). `analyze.py:251-256`: Tier-3 mode check at line 252 returns empty `BibleAnalysis` without raising. `test_tier3_endpoint_degrades_gracefully` PASSED: status=="done", .vi.srt written, no quarantine. `test_low_confidence_safe_default` and `test_below_threshold_ignores_address_map` PASSED. |

**Score: 4/4 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/bible/analyze.py` | `BibleAnalysis` model, `BibleAnalysisError`, `analyze_file()`, `merge_bible_analysis()` | VERIFIED | 20.2 KB; all four symbols present at lines 39, 80, 213, 310 |
| `trezarr/translate/attribute.py` | `AttributionConfidence`, `LineAttribution`, `BatchAttribution`, `attribute_batch()`, `build_attribution_prompt()` | VERIFIED | 12.8 KB; all symbols at lines 37, 45, 61, 69, 256 |
| `trezarr/translate/reconcile.py` | `KINSHIP_RECIPROCAL`, `get_safe_default()`, `reconcile_attributions()` | VERIFIED | 12.4 KB; all at lines 34, 96, 125; 18 kinship pairs |
| `trezarr/translate/engine.py` | Extended `build_translate_prompt` (pronoun_hints), extended `translate_file` (3-pass flow), `derive_episode_key()` | VERIFIED | 32.8 KB; pronoun_hints at lines 139-183; 3-pass block at lines 544-635; derive_episode_key at line 59 |
| `trezarr/cli.py` | `translate_file` call passes `eligible_item=eligible_item, session_factory=session_factory` | VERIFIED | Lines 302-303; `_run_pipeline_steps` signature has `session_factory=None` at line 213 |
| `trezarr/bible/store.py` | `upsert_address_pair`, `_upsert_address_pair_in_session`, `load_address_map`, `selectinload(Series.address_maps)` in `load_series_bible` | VERIFIED | Lines 581, 870, 932, 201 |
| `trezarr/bible/dto.py` | `AddressMapDTO` class; `SeriesBibleDTO.address_map: list[AddressMapDTO]` field | VERIFIED | `AddressMapDTO` at line 120 area; `SeriesBibleDTO.address_map` at line 214 |
| `trezarr/bible/models.py` | `Series.address_maps` relationship; `AddressMap.series` back-reference | VERIFIED | Lines 93 and 184 |
| `trezarr/config.py` | Phase-5 fields: `enable_pass1_analysis`, `enable_attribution`, `attribute_context_lines_k`, `attribute_max_cues_per_batch`, `pronoun_confidence_threshold`, `pronoun_safe_default` | VERIFIED | All 6 fields present at lines 130-143; spot-check confirms correct defaults |
| `tests/translate/test_analyze.py` | 2 tests GREEN | VERIFIED | `test_pass1_runs_before_pass3` PASSED, `test_pass1_failure_quarantines` PASSED |
| `tests/translate/test_attribute.py` | 6 tests GREEN (2 original stubs + 4 additional) | VERIFIED | All 6 PASSED |
| `tests/translate/test_reconcile.py` | 4 tests GREEN | VERIFIED | All 4 PASSED |
| `tests/translate/test_pronoun_engine.py` | 3 tests GREEN | VERIFIED | `test_pronoun_hint_in_prompt`, `test_pronoun_consistency_within_episode`, `test_tier3_endpoint_degrades_gracefully` — all PASSED |
| `tests/bible/test_address_map.py` | 2 tests GREEN | VERIFIED | `test_upsert_address_pair` PASSED, `test_locked_pair_not_overwritten` PASSED |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py (translate_file)` | `bible/analyze.py (analyze_file + merge_bible_analysis)` | `await analyze_file(...) → await merge_bible_analysis(...)` BARRIER | WIRED | Lines 586-587; BibleAnalysisError caught at 588 → quarantine |
| `engine.py (translate_file)` | `translate/attribute.py (attribute_batch)` | `asyncio.TaskGroup` gather | WIRED | Lines 622-627; `from trezarr.translate.attribute import attribute_batch` at line 560 |
| `engine.py (translate_file)` | `translate/reconcile.py (reconcile_attributions)` | `await reconcile_attributions(flat_attributions, ...)` | WIRED | Lines 633-635 |
| `engine.py (build_translate_prompt)` | `pronoun_hints dict` | `"(speaker says: X; addresses as: Y)"` prefix in `[LINES TO TRANSLATE]` loop | WIRED | Lines 179-181; spot-check confirms format |
| `cli.py` | `engine.py (translate_file)` | `eligible_item=eligible_item, session_factory=session_factory` | WIRED | Lines 302-303 |
| `analyze.py (merge_bible_analysis)` | `store.py (upsert_address_pair)` | Direct async call with case-normalised name resolution (CR-01 fix) | WIRED | Lines 427-428 use `.strip().lower()`; line 460 calls `upsert_address_pair` |
| `reconcile.py (reconcile_attributions)` | `store.py (upsert_address_pair)` | Direct async call to persist reconciled pairs | WIRED | `from trezarr.bible.store import upsert_address_pair` at line 19 |
| `store.py (load_series_bible)` | `models.py (Series.address_maps)` | `selectinload(Series.address_maps)` | WIRED | Line 201 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `engine.py (translate_file)` | `resolved_map` | `reconcile_attributions` → `upsert_address_pair` → SQLite `address_map` table | Yes — writes to and reads from DB; `test_high_confidence_uses_address_map` confirms DB roundtrip with in-memory SQLite | FLOWING |
| `engine.py (translate_file)` | `per_batch_hints` | `resolved_map` + `flat_attributions` name-to-char-id bridge | Yes — mock LLM consistency test confirms hints reach Pass-3 prompts | FLOWING |
| `analyze.py (merge_bible_analysis)` | `name_to_id` | `upsert_character` return DTOs | Yes — built from returned `char_dto.id`; CR-01 fix ensures case-insensitive match | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `build_translate_prompt` emits correct hint format | `build_translate_prompt(['Hello'], [], [], pronoun_hints={1: ('anh','em')})` contains `"speaker says: anh; addresses as: em"` | Confirmed | PASS |
| `derive_episode_key` parses SxxExx from path | `derive_episode_key(mock_episode, '/media/Show.S01E03.en.srt')` == `"S01E03"` | `S01E03` | PASS |
| `get_safe_default` returns neutral pair for low-confidence | `get_safe_default(None, settings)` == `('tôi', 'bạn')` | `('tôi', 'bạn')` | PASS |
| Phase-5 config fields accessible | `TrezarrSettings()` instantiates with `enable_pass1_analysis=True`, `pronoun_confidence_threshold='medium'` | Confirmed | PASS |
| Full test suite | `uv run pytest -x -q` | `226 passed, 1 skipped, 1 warning` | PASS |

---

### Probe Execution

No conventional probe scripts found (`scripts/*/tests/probe-*.sh`) — Step 7c skipped.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ENG-04 | 05-01..06 | Two-pass pipeline — Pass 1 analyzes full file + media metadata before Pass 2 translates | SATISFIED | `engine.py:583-605`: BARRIER block; `test_pass1_runs_before_pass3` PASSED; reload Bible before Pass 2 at line 605 |
| BIBLE-03 | 05-02, 05-04 | Directed Address Map — ordered pair self_term/address_term, asymmetric | SATISFIED | `upsert_address_pair` keyed by `(series_id, speaker_character_id, addressee_character_id)`; `test_upsert_address_pair` and `test_locked_pair_not_overwritten` PASSED |
| PRON-01 | 05-05 | Infer speaker/addressee per line from dialogue content | SATISFIED | `attribute_batch()` calls LLM with `BatchAttribution` response model; name-matching post-processing; `test_attribution_parsing` PASSED |
| PRON-02 | 05-03, 05-06 | Apply correct Vietnamese pronoun pair from Address Map | SATISFIED | `reconcile_attributions` → `resolved_map` → `per_batch_hints` → `build_translate_prompt` hint format; `test_pronoun_consistency_within_episode` PASSED |
| PRON-03 | 05-03, 05-06 | Low-confidence → safe register, not wrong intimate pronoun | SATISFIED | `get_safe_default` returns `('tôi', 'bạn')`; `test_low_confidence_safe_default` PASSED; `test_below_threshold_ignores_address_map` PASSED; `test_tier3_endpoint_degrades_gracefully` PASSED |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `trezarr/bible/store.py` | 84, 128 | `\\uXXXX` in comment (not a debt marker — explains Python `ensure_ascii=True` encoding notation) | Info | None — documentation text, not a TODO/FIXME |

No `TBD`, `FIXME`, or `XXX` debt markers in any Phase-5-modified file.
No `TODO`, `HACK`, or `PLACEHOLDER` markers in Phase-5-modified production files.
No stub patterns (`return null`, `return {}`, `return []` without real data source) found in production modules.

---

### Code Review Fixes Held

All 11 findings from `05-REVIEW.md` were fixed in `05-REVIEW-FIX.md`. Verification confirms all fixes hold in the current codebase:

| Finding | Fix | Verified |
|---------|-----|---------|
| CR-01: `merge_bible_analysis` case-sensitive name resolution | `name_to_id` built with `.strip().lower()` (line 371); pair resolution uses `(pair.X or "").strip().lower()` (lines 427-428) | Yes — code confirmed |
| CR-02: Consistency test did not verify hint injection | `captured_prompts` captures all Pass-3 prompts; `_build_pass3_response` echoes hints only when present; structural assertions on hint text + output content | Yes — `test_pronoun_consistency_within_episode` PASSED with real guard |
| WR-01: Context window capped at translate width | `attr_batches` built with `context_lines_k=settings.attribute_context_lines_k` (line 616-618) | Yes — engine.py:614-618 |
| WR-02: `enable_pass1_analysis=False` disabled Pass 2 too | Engine gate now `eligible_item is not None and session_factory is not None` only (line 557) | Yes — engine.py:557 |
| WR-03: `attribute_max_cues_per_batch` unused | Wired at engine.py:617 `max_cues_per_batch=settings.attribute_max_cues_per_batch` | Yes |
| WR-04: `asyncio.gather` orphaned tasks | Replaced with `asyncio.TaskGroup` (lines 622-627 for Pass 2; Pass 3 uses TaskGroup + `except*`) | Yes |
| WR-05: Prompt injection via embedded newlines | `replace("\n", " ⏎ ")` applied to cue text in both analyze.py and attribute.py | Yes (confirmed in analyze.py:188 context per REVIEW-FIX; attribute.py:126) |
| WR-06: Broad `except Exception` masking systemic failures | Per-loop failure counters; raises `BibleAnalysisError` when ALL rows in a loop fail (lines 387-391, 416-420) | Yes |
| WR-07: Empty/whitespace register could overwrite good prior register | `reg = (analysis.register_value or "").strip(); if reg:` guard at lines 341-342 | Yes |
| IN-01: Unused `Counter` import in reconcile.py | Removed — grep confirms no `Counter` in reconcile.py | Yes |
| WR-04 test update | `test_translate_file_non_batch_error_propagates` updated for `ExceptionGroup` unwrapping | Yes (226 tests pass) |

---

### Project Invariants

| Invariant | Status | Evidence |
|-----------|--------|---------|
| No SQLAlchemy imports in analyze.py, attribute.py at module level (D-39) | VERIFIED | `grep "from sqlalchemy" analyze.py attribute.py` → 0 runtime hits; reconcile.py's `from sqlalchemy.ext.asyncio import async_sessionmaker` is under `if TYPE_CHECKING:` (line 25) |
| Single `asyncio.Semaphore` in `llm/client.py` only (D-06) | VERIFIED | No `asyncio.Semaphore(` instantiation in any pass module; comments in analyze.py, attribute.py, engine.py confirm the invariant; semaphore lives in `llm/client.py:55` |
| Numbered-line / sentinel / document-gate preserved | VERIFIED | `build_translate_prompt` extends existing loop without breaking `<<T0>>` sentinel protocol; test suite includes integration tests for batch validation gate — all pass |

---

### Human Verification Required

#### 1. Live-LLM Pronoun Consistency End-to-End

**Test:** Configure a live OpenAI-compatible endpoint. Run `trezarr translate` on a real episode SRT file (ideally a TV series episode with recurring characters and dialogue in English, Japanese, or Korean). Inspect the produced `.vi.srt` for the same character pair across multiple scenes.

**Expected:** The same directed pair (e.g. John speaking to Mary) consistently receives the same Vietnamese pronoun pair (e.g. `anh`/`em`) across all dialogue lines throughout the episode. No flip between scenes. The Address Map DB entry should be visible via the CLI or DB inspection.

**Why human:** The automated `test_pronoun_consistency_within_episode` uses a mock LLM that echoes hint terms back. It proves the hint-injection plumbing is correct but cannot validate that a real LLM model actually follows the `"(speaker says: anh; addresses as: em)"` instruction in its Vietnamese output. Real model behavior is not testable without a live endpoint.

#### 2. Independent-Toggle Behavior of enable_pass1_analysis=False with enable_attribution=True

**Test:** Set `enable_pass1_analysis=False` (via env var `TREZARR_ENABLE_PASS1_ANALYSIS=false`) while keeping `enable_attribution=True`. Run a translate job with `eligible_item` + `session_factory` provided. Observe logs.

**Expected:** Pass 1 is skipped (no LLM analysis call, empty BibleAnalysis returned by analyze.py early-return at line 244). Pass 2 (`attribute_batch`) still runs. Reconciliation still runs. Translation completes with `status="done"`. The WR-02 fix (removing the outer `enable_pass1_analysis` gate from the engine) means attribution and reconciliation remain active even when Pass 1 is off.

**Why human:** While the code structure confirms the WR-02 fix (engine gate at line 557 does not check `enable_pass1_analysis`), confirming the full toggle interaction chain works correctly under a real run with real DB session requires a live integration test scenario that is impractical to fully automate in the current test harness.

---

### Gaps Summary

No gaps found. All 4 roadmap success criteria are verified in code. All 5 required requirement IDs (ENG-04, BIBLE-03, PRON-01, PRON-02, PRON-03) are satisfied by confirmed implementations. All 18 Phase-5 critical tests pass. Both code-review blockers (CR-01, CR-02) are fixed and confirmed. The two human verification items are quality/integration checks, not correctness failures — the code implements the behaviors correctly; the human tests validate real-world fidelity.

---

_Verified: 2026-06-02_
_Verifier: Claude (gsd-verifier)_
