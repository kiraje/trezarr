---
phase: 02-mechanical-translation-core-validation-gate
verified: 2026-05-31T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 2: Mechanical Translation Core + Validation Gate — Verification Report

**Phase Goal:** Given a parsed source file, produce a translated Vietnamese SRT through a single LLM pass and write it as a correctly-named, atomic, UTF-8 sidecar — but only if it passes a hard pre-write validation gate.
**Verified:** 2026-05-31T00:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A long file is batched within token limits without splitting a sentence or scene across batch boundaries, each batch translated with surrounding-line context | VERIFIED | `batch_subdoc()` in `batching.py` uses a greedy-walk algorithm respecting `budget_chars`, `translate_max_cues_per_batch`, and `translate_scene_gap_ms`; `_make_batch()` attaches `context_before`/`context_after` up to K neighbor lines. 5 passing tests in `test_batching.py` cover token budget, scene gap, max-cue cap, single-cue overflow, and context attachment. |
| 2 | Every output is gated before write: cue-count match, no untranslated/empty lines, monotonic timestamps, valid format — failing files are quarantined and logged, never written | VERIFIED | `validate_subdoc()` in `validate.py` enforces 7 checks (count, empty, VI-diacritic ratio, timecode identity, monotonic/backward-jump, orphan sentinel, UTF-8). `translate_file()` in `engine.py` calls `validate_subdoc()` at Step 9, before `write_vi_sidecar()` at Step 10. `GateError` routes to `_write_quarantine()` + `ledger.record(status="quarantined")`, never touching the output path. 10 passing tests in `test_validate.py` cover all 7 checks including the WR-01 backward-jump fix. |
| 3 | A passing translation is written as `Show.S01E01.vi.srt` (matching the video basename, ISO-639 `vi`) atomically (temp+rename) and as valid UTF-8 | VERIFIED | `derive_vi_sidecar_path()` strips a 2-letter lang-code suffix from the stem and appends `.vi.srt`. `write_vi_sidecar()` uses `NamedTemporaryFile(dir=dest.parent, delete=False)` + `os.replace()` for a POSIX-atomic rename. Output SubDoc is constructed with `encoding='utf-8'` regardless of source. Spot-checked: `derive_vi_sidecar_path('/media/Show.S01E01.en.srt')` returns `Show.S01E01.vi.srt`. 4 passing tests in `test_write.py` cover naming with/without lang code, no leftover `.tmp` files, and UTF-8 output from a latin-1 source doc. |
| 4 | A failed or rejected translation can be re-run idempotently without duplicating or corrupting output | VERIFIED | `translate_file()` consults the ledger at entry (D-20 table): `status="done"` + hash match → skip; `status="quarantined"` → retry; foreign `.vi.srt` (dest exists + not in ledger) → skip + log. `Ledger._load()` parses entries individually (WR-07 fix) and falls back to empty dict on corrupt JSON without exception. 7 passing tests in `test_ledger.py` cover skip, regenerate-on-hash-change, foreign-file protection, quarantine retry, atomic persistence, schema-drift survival, and corrupt-JSON fallback. |

**Score: 4/4 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trezarr/translate/__init__.py` | Package marker | VERIFIED | Exists, 0 bytes |
| `trezarr/translate/sentinel.py` | `extract_sentinels`, `reinsert_sentinels`, `TAG_RE` | VERIFIED | All 3 exports present; 7/7 sentinel tests pass |
| `trezarr/translate/batching.py` | `Batch`, `batch_subdoc` | VERIFIED | Both exports present; 5/5 batching tests pass |
| `trezarr/translate/validate.py` | `validate_subdoc`, `GateError`, `GateFailure` | VERIFIED | All 3 exports present; 10/10 validate tests pass (includes WR-01 backward-jump test) |
| `trezarr/translate/engine.py` | `translate_file`, `BatchValidationError`, `build_translate_prompt`, `parse_numbered_response` | VERIFIED | All exports present; 9/9 engine tests pass (including CR-01 and WR-04 fix tests) |
| `trezarr/translate/_timecode.py` | `tc_to_ms` shared helper | VERIFIED | New file created as part of IN-04 fix; imported by both `batching.py` and `validate.py` |
| `trezarr/output/__init__.py` | Package marker | VERIFIED | Exists, 0 bytes |
| `trezarr/output/write.py` | `write_vi_sidecar`, `derive_vi_sidecar_path` | VERIFIED | Both exports present; `derive_vi_sidecar_path` extracted per WR-06 fix; 4/4 write tests pass |
| `trezarr/output/ledger.py` | `Ledger`, `LedgerEntry` | VERIFIED | Both present; per-entry schema-drift parsing (WR-07); 7/7 ledger tests pass |
| `trezarr/config.py` | 8 Phase-2 `translate_*` fields | VERIFIED | All 8 fields verified: `translate_chars_per_token=3.5`, `translate_max_cues_per_batch=50`, `translate_scene_gap_ms=2000`, `translate_context_lines_k=3`, `translate_batch_retry_attempts=2`, `translate_vi_diacritic_ratio=0.70`, `translate_quarantine_dir`, `translate_ledger_path` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `engine.py` | `batching.py` | `from trezarr.translate.batching import Batch, batch_subdoc` | WIRED | Line 41; called at Step 6 of `translate_file()` |
| `engine.py` | `validate.py` | `from trezarr.translate.validate import GateError, validate_subdoc` | WIRED | Line 43; called at Step 9 of `translate_file()` |
| `engine.py` | `sentinel.py` | `from trezarr.translate.sentinel import extract_sentinels, reinsert_sentinels` | WIRED | Line 42; called inside `_translate_batch_inner` Steps 1 and 5 |
| `engine.py` | `write.py` | `from trezarr.output.write import derive_vi_sidecar_path, write_vi_sidecar` | WIRED | Line 38; `derive_vi_sidecar_path` used at Step 2, `write_vi_sidecar` at Step 10 |
| `engine.py` | `ledger.py` | `from trezarr.output.ledger import Ledger, LedgerEntry` | WIRED | Line 37; `ledger.check()` at Step 3, `ledger.record()` at Steps 4, 11, quarantine paths |
| `batching.py` | `subtitles/model.py` | `from trezarr.subtitles.model import SubDoc, SubLine` | WIRED | Line 19; `SubLine.start_tc`/`end_tc` parsed via `_tc_to_ms` |
| `write.py` | `subtitles/srt.py` | `from trezarr.subtitles.srt import write_srt` | WIRED | Line 23; `write_srt(doc_out, tmp_path)` called in `write_vi_sidecar` |
| `batching.py` | `_timecode.py` | `from trezarr.translate._timecode import tc_to_ms as _tc_to_ms` | WIRED | Line 20; used in `_gap_ms()` |
| `validate.py` | `_timecode.py` | `from trezarr.translate._timecode import tc_to_ms as _tc_to_ms` | WIRED | Line 22; used in `_check_monotonic()` |
| `engine.py` | `LLMClient` (semaphore) | `from trezarr.llm.client import LLMClient` | WIRED | Line 36; `llm_client.call()` called at Step 3 of `_translate_batch_inner`; no second Semaphore in engine (confirmed by absence of `asyncio.Semaphore` in engine.py) |
| `engine.py` | only `BatchValidationError` caught by tenacity | `retry_if_exception_type(BatchValidationError)` | WIRED | Lines 213-214 in `_make_translate_batch_fn`; gather handler catches only `BatchValidationError` (line 476); CR-01 fix confirmed |

---

### Data-Flow Trace (Level 4)

The core data flow in `translate_file()` was traced end-to-end:

| Stage | Source | Produces Real Data | Status |
|-------|--------|--------------------|--------|
| `read_srt(path)` → `SubDoc` | Filesystem SRT file bytes | Yes — parses real SRT content | FLOWING |
| `batch_subdoc(source_doc, settings)` → `list[Batch]` | Real `SubDoc.lines` from previous step | Yes — packs actual cues | FLOWING |
| `_translate_batch(batch, llm_client, settings)` → `list[str]` | LLM response via `llm_client.call()` | Yes — returns translated text strings | FLOWING (LLM-gated; not testable without endpoint) |
| `validate_subdoc(translated_doc, source_doc, settings)` | Assembled translated `SubDoc` | Yes — raises on real structural failures | FLOWING |
| `write_vi_sidecar(translated_doc, path)` | Validated translated `SubDoc` | Yes — writes actual bytes to disk | FLOWING |
| `ledger.record(LedgerEntry(..., status="done"))` | Completed write path | Yes — persists real content hash | FLOWING |

No hollow props or disconnected data sources found. The LLM call itself cannot be verified without a live endpoint (correctly marked as the `@pytest.mark.live` skip in the test suite).

---

### Behavioral Spot-Checks

| Behavior | Result | Status |
|----------|--------|--------|
| All module exports importable | All imports resolved without error | PASS |
| `TrezarrSettings` defaults: `translate_chars_per_token=3.5`, `translate_max_cues_per_batch=50`, `translate_scene_gap_ms=2000`, `translate_context_lines_k=3`, `translate_batch_retry_attempts=2`, `translate_vi_diacritic_ratio=0.7` | All values confirmed via `uv run python` | PASS |
| `derive_vi_sidecar_path('/media/Show.S01E01.en.srt')` returns `Show.S01E01.vi.srt` | `Show.S01E01.vi.srt` | PASS |
| `extract_sentinels('<i>hello</i> world')` produces 2-entry sentinel map; `reinsert_sentinels` restores original with `integrity_ok=True` | Cleaned `<<T0>>hello<<T1>> world`, restored `<i>hello</i> world`, `ok=True` | PASS |
| `parse_numbered_response('[1] X\n[2] Y', 2)` returns `['X', 'Y']` | `['Xin chao', 'Toi den day']` | PASS |
| Full test suite (69 passed, 1 skip) | All 69 pass; 1 pre-existing `@live` skip | PASS |
| Phase-2-specific tests (42 items) | 42/42 passed | PASS |

---

### Requirements Coverage

| Requirement | Phase | Description | Status | Evidence |
|-------------|-------|-------------|--------|----------|
| ENG-02 | Phase 2 | Batch/chunk within token limits, no sentence/scene split | SATISFIED | `batch_subdoc()` implements greedy-walk with scene-gap + char-budget + max-cue-count; 5 passing tests |
| ENG-03 | Phase 2 | Each batch translated with surrounding-line context window | SATISFIED | `build_translate_prompt()` embeds `context_before`/`context_after` as `[CONTEXT]` blocks; `test_context_window_prompt` passes |
| ENG-06 | Phase 2 | Hard pre-write validation gate; failing files quarantined, never written | SATISFIED | `validate_subdoc()` enforces 7 checks; `translate_file()` calls it before any write; quarantine path writes atomically; 10 validate tests + 2 engine quarantine tests pass |
| ENG-07 | Phase 2 | Failed/rejected translation retried idempotently | SATISFIED | Ledger tracks `status` + `content_hash`; `quarantined` entries proceed to retry; `done`+hash-match skips; foreign `.vi.srt` skipped not clobbered; 7 ledger tests + `test_translate_file_skip_unchanged` pass |
| FMT-05 | Phase 2 | Output named `Show.S01E01.vi.srt`, written atomically, valid UTF-8 | SATISFIED | `derive_vi_sidecar_path()` + `write_vi_sidecar()` implement naming, `NamedTemporaryFile`+`os.replace()` atomic write, forced UTF-8 encoding; 4 write tests pass |

All 5 requirement IDs from the plan frontmatter are SATISFIED. REQUIREMENTS.md traceability table marks all 5 as "Complete" under Phase 2.

---

### Anti-Patterns Found

No debt-marker anti-patterns found. Scan of all 7 phase-2 source files found zero `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, or `PLACEHOLDER` markers. The single grep hit was a legitimate string literal in the LLM prompt (`"never translate or modify them"`), not a code debt marker.

No stub patterns found. All implementation files contain full logic with no `return null`, `return {}`, `return []`, or placeholder handlers. No function bodies that only call `console.log` or `pass`.

All 12 code review findings (1 BLOCKER CR-01, 7 warnings WR-01 through WR-07, 4 info IN-01 through IN-04) were fixed as documented in `02-REVIEW-FIX.md` and confirmed by:
- `except BatchValidationError` (not `except Exception`) in the gather handler — CR-01 fixed
- Monotonic backward-jump guard in `_check_monotonic()` — WR-01 fixed
- Over-count and duplicate line-number rejection in `parse_numbered_response()` — WR-02/WR-03 fixed
- `read_srt`/`batch_subdoc` wrapped in `try/except Exception` routing to quarantine — WR-04 fixed
- `datetime.now(timezone.utc).isoformat()` replacing `datetime.utcnow().isoformat() + "Z"` — WR-05 fixed
- `derive_vi_sidecar_path()` extracted as single source of truth — WR-06 fixed
- Per-entry `LedgerEntry` construction with unknown-key filtering — WR-07 fixed
- Dead `cue_idx` variable removed — IN-01 fixed
- Top-level `import re` (no mid-function aliases) — IN-02 fixed
- `CALLER INVARIANT` docstring in `extract_sentinels` — IN-03 fixed
- `trezarr/translate/_timecode.py` created, both callers import from it — IN-04 fixed

---

### Human Verification Required

One item cannot be verified programmatically:

**1. End-to-end LLM translation produces valid Vietnamese output**

**Test:** Configure a real OpenAI-compatible endpoint, run `translate_file()` against an actual `.srt` file, and verify the resulting `.vi.srt` contains coherent Vietnamese text that passes all 7 gate checks.
**Expected:** `translate_file()` returns `TranslationResult(status="done")`, the `.vi.srt` file is created, and its content is recognizable Vietnamese.
**Why human:** The LLM call itself is mocked in all tests. The `@pytest.mark.live` test (1 skip in the suite) is the designated hook for this but requires a live endpoint. No offline verification can confirm translation quality or that the numbered-line protocol works against a real model.

---

## Gaps Summary

No gaps found. All 4 observable truths are verified, all 5 requirement IDs are satisfied, all 10 required artifacts are present and substantive, all key links are wired and data-flowing, and all 12 code review findings confirmed fixed.

The one human verification item (live LLM end-to-end test) is expected and by design — the `@pytest.mark.live` skip exists precisely for this.

---

_Verified: 2026-05-31T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
