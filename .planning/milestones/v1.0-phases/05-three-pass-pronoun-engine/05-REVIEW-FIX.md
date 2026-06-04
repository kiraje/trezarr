---
phase: 05-three-pass-pronoun-engine
fixed_at: 2026-06-01T00:00:00Z
review_path: .planning/phases/05-three-pass-pronoun-engine/05-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-06-01
**Source review:** .planning/phases/05-three-pass-pronoun-engine/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 11 (CR-01, CR-02, WR-01..WR-07, IN-01; skipped IN-02 and IN-03 per objective)
- Fixed: 11
- Skipped: 0

**Test suite:** 226 passed, 1 skipped, 1 warning
**Ruff:** All checks passed on modified files; 29 pre-existing errors in unmodified files (unchanged from pre-fix)

## Fixed Issues

### CR-01: `merge_bible_analysis` resolves address-pair names case-sensitively

**Files modified:** `trezarr/bible/analyze.py`
**Commit:** 272e4fd
**Applied fix:** Built the `name_to_id` index with `.strip().lower()` (line 358) and resolved `pair.speaker_name` / `pair.addressee_name` with `(pair.X or "").strip().lower()` (lines 397-398). Now matches the normalisation in `reconcile.py` and `engine.py`.

---

### CR-02: Headline consistency test does not verify pronoun consistency

**Files modified:** `tests/translate/test_pronoun_engine.py`
**Commit:** 53480a5
**Applied fix:** Rewrote `test_pronoun_consistency_within_episode` with a mock LLM that:
1. Captures every Pass-3 prompt it receives into `captured_prompts`
2. Echoes hint terms back in its output via `_build_pass3_response()` — lines WITHOUT hints produce neutral Vietnamese output that does NOT contain "anh"/"em"
3. Adds two structural assertions: `(speaker says: anh; addresses as: em)` and the reciprocal `(speaker says: em; addresses as: anh)` must appear in at least one captured Pass-3 prompt
4. Adds output assertions: `"anh"` and `"em"` must appear in the output file (they only appear if hints reached Pass 3)

A broken hint injection, reconcile, or resolved_map→hint bridge now causes this test to fail.

---

### WR-01: Attribution "wider context window" (D-50) is silently capped at translate context width

**Files modified:** `trezarr/translate/batching.py`, `trezarr/translate/engine.py`
**Commit:** f17ca9f
**Applied fix:** Added optional `context_lines_k: int | None = None` parameter to `_make_batch` and `batch_subdoc` (default `None` = use `settings.translate_context_lines_k`, preserving existing callers). Engine now builds `attr_batches` for Pass 2 with `context_lines_k=settings.attribute_context_lines_k` (default 8), while Pass-3 batches use the standard `translate_context_lines_k` (default 3). Cue grouping is unaffected by K (K only affects context attachment, not scene-gap/budget boundaries), so `flat_attributions` alignment is preserved.

---

### WR-02: `enable_pass1_analysis=False` also disables Pass 2 attribution and reconciliation

**Files modified:** `trezarr/translate/engine.py`
**Commit:** 60ec5b5
**Applied fix:** Changed the engine Phase-5 gate from `eligible_item is not None and session_factory is not None and settings.enable_pass1_analysis` to `eligible_item is not None and session_factory is not None`. Each pass now honours its own toggle internally: `analyze_file()` early-returns on `enable_pass1_analysis=False` (already did); `attribute_batch()` skips on `enable_attribution=False` (already did). The outer engine gate no longer silently disables both attribution and reconciliation when only Pass 1 is toggled off.

---

### WR-03: `attribute_max_cues_per_batch` is defined but never used

**Files modified:** `trezarr/translate/batching.py`, `trezarr/translate/engine.py`
**Commit:** b753cec
**Applied fix:** Added optional `max_cues_per_batch: int | None = None` parameter to `batch_subdoc` (default `None` = use `settings.translate_max_cues_per_batch`, preserving existing callers). Engine now passes `max_cues_per_batch=settings.attribute_max_cues_per_batch` when building `attr_batches` for Pass 2, honouring the D-50 "attribution batches may be smaller" design.

---

### WR-04: `asyncio.gather` without `return_exceptions` leaves sibling coroutines orphaned

**Files modified:** `trezarr/translate/engine.py`, `tests/translate/test_engine.py`
**Commits:** 800ff90, amend (except* fix), test update
**Applied fix:**
- **Pass 2**: Replaced `asyncio.gather(*[attribute_batch(...)])` with `async with asyncio.TaskGroup() as tg: attr_tasks = [tg.create_task(...)]` + `attr_per_batch = [t.result() for t in attr_tasks]`. Attribution degrades gracefully, no `BatchValidationError` to handle.
- **Pass 3**: Replaced `asyncio.gather(*[_translate_batch(...)])` with `TaskGroup`, using `except* BatchValidationError as eg` to catch the `ExceptionGroup` and quarantine. Since `return` is not valid inside `except*` (Python 3.11+ restriction), the quarantine result is stored in `_batch_quarantine` and returned after the block exits.
- Updated `test_translate_file_non_batch_error_propagates` to accept `ExceptionGroup` wrapping by catching `BaseException` and unwrapping the ExceptionGroup for assertion.
- Removed unused `import pytest` from `test_pronoun_engine.py` (ruff F401).

---

### WR-05: Prompt-injection mitigation defeated by embedded newlines in cue text

**Files modified:** `trezarr/bible/analyze.py`, `trezarr/translate/attribute.py`
**Commit:** 05e9c27
**Applied fix:** Applied `.replace("\n", " ⏎ ")` before embedding cue text in Pass-1 `[DIALOGUE SAMPLE]` items (analyze.py line 188) and Pass-2 `[LINES TO ATTRIBUTE]` items (attribute.py line 126). Also applied `replace(chr(10), ' ⏎ ')` to context lines in `[CONTEXT]` blocks (attribute.py lines 120, 134). Prevents injected fake section headers from column-aligning with real prompt section markers (T-05-04-01 hardening).

---

### WR-06: Broad `except Exception` in merge silently degrades the Bible on systemic failures

**Files modified:** `trezarr/bible/analyze.py`
**Commit:** 5a7cb46
**Applied fix:** Added per-loop failure counters (`char_fail_count`, `term_fail_count`, `pair_fail_count`). After each loop, if ALL rows failed (total failure rate = 100%), raise `BibleAnalysisError` which triggers episode quarantine in the engine. Isolated per-row faults still warn and continue (best-effort behavior preserved). This prevents a systemic DB failure (locked DB, schema drift, programming error in store function) from being masked as `status="done"` with an empty Bible.

---

### WR-07: `merge_inferred` register update not guarded against empty/whitespace `register_value`

**Files modified:** `trezarr/bible/analyze.py`
**Commit:** 83fb1bb
**Applied fix:** Replaced `if analysis.register_value is not None:` with `reg = (analysis.register_value or "").strip(); if reg:` so an LLM-returned empty-string register value cannot overwrite a good prior register in the Series Bible.

---

### IN-01: Unused import `Counter` in reconcile.py

**Files modified:** `trezarr/translate/reconcile.py`
**Commit:** 2212f9b
**Applied fix:** Removed `from collections import Counter` (unused, ruff F401).

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-06-01_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
