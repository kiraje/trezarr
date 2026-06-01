---
phase: 05-three-pass-pronoun-engine
plan: "05"
subsystem: translate
tags: [attribution, pass2, pron-01, llm, pydantic, d-43, d-47]
dependency_graph:
  requires: [05-02, 05-03]
  provides: [trezarr.translate.attribute, attribute_batch, LineAttribution, BatchAttribution]
  affects: [trezarr.translate.engine (Pass 2 dispatch), tests/translate/test_attribute.py]
tech_stack:
  added: []
  patterns:
    - Tier-1/2/3 LLM structured output with graceful degradation
    - Name-matching post-processing gate (D-43, T-05-05-02)
    - Batch-local 1-based line_index (Pitfall E)
    - Missing-index fill with LOW defaults (Pitfall E)
key_files:
  created:
    - trezarr/translate/attribute.py
  modified:
    - tests/translate/test_attribute.py
decisions:
  - D-43 enforced: unmatched LLM-inferred names → None/LOW, no crash
  - D-47 enforced: Tier-3 (text mode) → all-LOW-unknown, no LLM call
  - D-50 enforced: enable_attribution=False fast-path returns all-LOW without calling LLM
  - Pitfall E enforced: line_index is 1-based within batch; _fill_missing_indices pads to batch_size
  - D-06 enforced: no asyncio.Semaphore in attribute.py; LLMClient._semaphore is sole gate
  - D-39 enforced: no sqlalchemy import; only trezarr.bible.dto consumed
metrics:
  duration: "4 min"
  completed: "2026-06-01"
  tasks_completed: 1
  files_changed: 2
---

# Phase 05 Plan 05: Pass 2 Attribution Module (attribute.py) Summary

**One-liner:** Per-cue speaker/addressee attribution with Tier-1/2/3 LLM degradation, name-matching gate, and batch-local line_index — turns two test stubs GREEN.

## What Was Built

`trezarr/translate/attribute.py` — the Pass 2 attribution module. This is a pure LLM + Pydantic module (no DB access, no SQLAlchemy, no asyncio.Semaphore) that:

1. Defines `AttributionConfidence(str, Enum)` with HIGH/MEDIUM/LOW values.
2. Defines `LineAttribution(BaseModel)` — line_index (1-based, batch-local), speaker/addressee (str|None), confidence.
3. Defines `BatchAttribution(BaseModel)` — LLM response container.
4. Implements `build_attribution_prompt()` — wider context window than translate (attribute_context_lines_k), character roster in preamble, labeled context sections, numbered `[LINES TO ATTRIBUTE]`.
5. Implements `attribute_batch()` — calls `LLMClient.call(response_model=BatchAttribution)`, handles all three tiers (Tier-1 parsed model, Tier-2 JSON string, Tier-3 text fallback), applies name-matching post-processing gate (T-05-05-02), and fills missing indices to match batch size (Pitfall E).

## Tests

`tests/translate/test_attribute.py` — 6 tests, all passing:
- `test_attribution_parsing` — Tier-1 structured response → speaker/addressee/confidence populated (PRON-01) **[previously xfail stub → GREEN]**
- `test_unmatched_name_safe_default` — LLM returns unrecognized name → speaker=None, confidence=LOW (D-43) **[previously xfail stub → GREEN]**
- `test_tier3_degradation_returns_all_low` — `_mode="text"` → all-LOW, LLM not called (D-47)
- `test_enable_attribution_false_returns_all_low` — `enable_attribution=False` → all-LOW, LLM not called (D-50)
- `test_missing_indices_filled_with_low` — LLM returns fewer entries than batch → missing filled with LOW (Pitfall E)
- `test_tier2_invalid_json_returns_all_low` — invalid JSON string → graceful degrade to all-LOW (D-47)

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

T-05-05-01 (prompt injection via cue text): Mitigated by structural labeling — cue text appears under `[LINES TO ATTRIBUTE]` as data, attribution instruction is in the preamble. Unrecognizable output falls back to LOW confidence.

T-05-05-02 (LLM returns fabricated names): Mitigated — name-matching post-processing sets unmatched speaker/addressee to None + LOW. This is the `test_unmatched_name_safe_default` assertion.

T-05-05-03 (extra JSON fields): Mitigated — Pydantic ignores extra fields by default.

No new threat surface introduced beyond what is documented in the plan's threat register.

## Verification Results

- `uv run pytest tests/translate/test_attribute.py -v` → 6 passed
- `uv run pytest tests/translate/ -x -q` → 43 passed, 3 xfailed
- `uv run pytest -q` → 222 passed, 1 skipped, 3 xfailed, 1 warning
- D-39 boundary: `grep -n "sqlalchemy" trezarr/translate/attribute.py` → 0 matches
- D-06 boundary: no `asyncio.Semaphore(` usage (only appears in docstrings/comments)

## Self-Check: PASSED

- [x] `trezarr/translate/attribute.py` exists with `AttributionConfidence`, `LineAttribution`, `BatchAttribution`, `build_attribution_prompt`, `attribute_batch`
- [x] Commit `9b96a38` exists
- [x] No sqlalchemy import in attribute.py
- [x] No asyncio.Semaphore usage in attribute.py
- [x] test_attribution_parsing PASSED
- [x] test_unmatched_name_safe_default PASSED
- [x] Full suite 222 passed
