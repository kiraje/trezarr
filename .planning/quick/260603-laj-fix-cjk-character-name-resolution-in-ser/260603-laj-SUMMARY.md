---
phase: quick
plan: 260603-laj
subsystem: bible/analyze
tags: [cjk, name-resolution, character-inference, series-bible, address-map, regression-test]
dependency_graph:
  requires: []
  provides: [CJK-script-name-resolution-in-name_to_id]
  affects: [trezarr/bible/analyze.py, tests/translate/test_analyze.py]
tech_stack:
  added: []
  patterns: [dual-key name_to_id indexing (Latin + script name), CR-01 .strip().lower() contract]
key_files:
  created: []
  modified:
    - trezarr/bible/analyze.py
    - tests/translate/test_analyze.py
decisions:
  - "Dual-key indexing is ADDITIVE — existing Latin-name path unchanged, CJK path added alongside"
  - "original_script_name stored only in-memory name_to_id dict, not persisted to DB (no schema change)"
  - "Empty-after-strip guard prevents empty-string key collision (T-laj-01)"
metrics:
  duration: 8 min
  completed: 2026-06-03
---

# Phase quick Plan 260603-laj: CJK Character Name Resolution in Series Bible Summary

**One-liner:** Dual-key `name_to_id` indexing on `original_script_name` so CJK-named character address pairs and relationship events are persisted instead of silently skipped.

## What Was Built

### Task 1 — `CharacterInference.original_script_name` + dual-key `name_to_id` + prompt tightening (`72177f7`)

Three targeted edits to `trezarr/bible/analyze.py`:

1. **Model field:** `CharacterInference` gains `original_script_name: str | None = None` as an optional field for CJK/non-Latin on-screen character names (e.g. '樱' for a Chinese series character romanized as "Sakura").

2. **Key fix — dual indexing:** In `merge_bible_analysis` Step 2 upsert loop, after writing `name_to_id[char.original_latin_name.strip().lower()] = char_dto.id`, also writes `name_to_id[char.original_script_name.strip().lower()] = char_dto.id` when `original_script_name` is non-None and non-empty-after-strip. Steps 4 (address_map) and 5 (relationship_events) already use `.strip().lower()` lookups — they now hit CJK keys automatically.

3. **Prompt tightening:** `_build_analysis_prompt` [INSTRUCTIONS] updated to (a) include `original_script_name` in the characters bullet with an example, and (b) instruct the LLM to use the EXACT same name string in `address_map` and `relationship_events` as listed in the characters array.

### Task 2 — Regression test: `test_cjk_script_name_address_pair_resolves` (`66a47ba`)

New test in `tests/translate/test_analyze.py`:

- Two CJK characters: `CharacterInference(original_latin_name="Sakura", original_script_name="樱")` and `CharacterInference(original_latin_name="Daisy", original_script_name="雏菊")`.
- `AddressMapInference(speaker_name="樱", addressee_name="雏菊", ...)` — the previously-failing form.
- `RelationshipEventInference(character_a_name="樱", character_b_name="雏菊", ...)`.
- Asserts after `merge_bible_analysis`: `len(updated_bible.address_map) == 1` and `len(rel_events) == 1`.
- Also verifies `self_term == "em"` and `address_term == "chị"` on the persisted pair.
- `arr_series_id=3003` distinct from other test series to avoid DB contamination.

## Test Results

```
tests/translate/test_analyze.py::test_pass1_runs_before_pass3               PASSED
tests/translate/test_analyze.py::test_pass1_failure_quarantines              PASSED
tests/translate/test_analyze.py::test_cjk_script_name_address_pair_resolves PASSED

Full suite: 347 passed, 1 skipped, 3 xfailed, 43 xpassed — no regressions
```

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced.
`original_script_name` is an in-memory field only (not persisted to DB). The T-laj-01 empty-after-strip guard is implemented. Acceptable per the plan's threat model.

## Self-Check: PASSED

- `trezarr/bible/analyze.py` modified: FOUND
- `tests/translate/test_analyze.py` modified: FOUND
- Commit `72177f7`: FOUND
- Commit `66a47ba`: FOUND
- `test_cjk_script_name_address_pair_resolves` PASSES: CONFIRMED
- `test_pass1_runs_before_pass3` still PASSES: CONFIRMED (CR-01 Latin path not regressed)
- No Alembic migration created: CONFIRMED
