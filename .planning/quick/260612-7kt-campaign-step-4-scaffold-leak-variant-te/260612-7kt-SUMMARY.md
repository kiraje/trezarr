---
phase: 260612-7kt
plan: 01
subsystem: translate/validate + translate/engine + bible/store
tags: [tdd, scaffold-leak, carry-forward, case-insensitive, term-stability]
dependency_graph:
  requires: []
  provides:
    - VN_HINT_SCAFFOLD_RE closes translated-label hint scaffold gap in Check 8
    - _LEAKED_VN_HINT_RE closes translated-label hint strip gap in engine
    - _upsert_term_in_session carry-forward (prior > inference for unlocked renderings)
    - _upsert_term_in_session case-insensitive lookup via func.lower()
  affects:
    - trezarr/translate/validate.py (Check 8 extended)
    - trezarr/translate/engine.py (parse_numbered_response strip chain extended)
    - trezarr/bible/store.py (_upsert_term_in_session policy + lookup)
tech_stack:
  added: []
  patterns:
    - Two-constant sibling pattern for scaffold regex (EN + VN variants alongside each other)
    - Carry-forward guard as a per-entity pre-delegate policy (mirrors address-map scy/ru6 approach)
    - func.lower() at write boundary only; read path (get_term) retains exact-case semantics
key_files:
  created: []
  modified:
    - trezarr/translate/validate.py
    - trezarr/translate/engine.py
    - trezarr/bible/store.py
    - tests/translate/test_validate.py
    - tests/translate/test_engine.py
    - tests/bible/test_merge_inferred.py
decisions:
  - VN_HINT_SCAFFOLD_RE colon-discriminator: `nói:` / `xưng hô:` + mandatory colon distinguishes
    label structure from stage directions (`nói to` has no colon → not matched)
  - _LEAKED_VN_HINT_RE as a separate constant (Option B): keeps _LEAKED_HINT_RE + its moat-invariant
    comment unchanged, chained after the English strip; mirrors the two-constant pattern in validate.py
  - Carry-forward guard placed in _upsert_term_in_session pre-delegate, NOT in compute_field_changes
    / _merge_inferred_in_session — localizes policy to term entity, keeps merge machinery generic
  - Case-insensitive lookup: write boundary only (func.lower); get_term read path unchanged
  - Prevention-only for case dedup: no migration of existing duplicate rows
metrics:
  duration: ~25 minutes
  completed: 2026-06-12
  tasks: 3 (6 commits: 3 RED + 3 GREEN)
  files: 6
---

# Phase 260612-7kt Plan 01: Campaign Step 4 — Scaffold Leak Variant + Term Stability Summary

Three TDD-verified fixes for Mode B audit findings: VN-label hint scaffold detection in both
defense layers, term rendering carry-forward preventing inference churn on unlocked rows, and
case-insensitive term upsert lookup eliminating duplicate rows from case-variant source terms.

## Tasks Completed

| Task | Type | RED Commit | GREEN Commit | Files |
|------|------|-----------|-------------|-------|
| 1: VN-label hint detection | tdd | c0490e2 | b82fcc0 | validate.py, engine.py, test_validate.py, test_engine.py |
| 2: Term rendering carry-forward | tdd | b069688 | 5d461c4 | store.py, test_merge_inferred.py |
| 3: Case-insensitive term upsert | tdd | 98a1e3a | 9247472 | store.py, test_merge_inferred.py |

## What Was Built

**Task 1 (D-01 — BLOCKER fix):**

`VN_HINT_SCAFFOLD_RE` added to `validate.py` alongside `HINT_SCAFFOLD_RE`:

```python
VN_HINT_SCAFFOLD_RE = re.compile(
    r"\(\s*(?:[^():]*(?:nói|xưng\s+hô)\s*:)",
    re.IGNORECASE,
)
```

OR'd into Check 8's condition (five signatures now). The colon-discriminator ensures `(nói to)` stage directions are NOT matched; `(Hồi 01: Mở Đầu)` title-cards are NOT matched (the token before `:` must be `nói` or `xưng hô`).

`_LEAKED_VN_HINT_RE` added to `engine.py` as a separate constant, chained after `_LEAKED_HINT_RE` in `parse_numbered_response`:

```python
_LEAKED_VN_HINT_RE = re.compile(
    r"^\s*\(\s*(?:[^():]*(?:nói|xưng\s+hô)\s*:)[^)]*\)\s*",
    re.IGNORECASE,
)
```

E143 cue 148 exact string `(tại hạ nói: tại hạ; xưng hô: cô nương) xin cô nương nén bi thương.` is now quarantined by Check 8 AND stripped by the engine. False-positive battery: 6 cases including `(nói to)`, `(Hồi 01: Mở Đầu)`, and the t53 credit cue all pass.

**Task 2 (D-02 — HIGH fix):**

Carry-forward guard added in `_upsert_term_in_session` before delegating to `_merge_inferred_in_session`. The guard fires when:
- `vietnamese_rendering` is provided (not None)
- existing row's rendering is non-empty
- field is NOT in `locked_fields`

In this case, the new inference is suppressed and a `BibleEvent` is emitted recording both `old_value` (prior kept) and `new_value` (suppressed inference) for audit trail. The `apply_human_edit_term` PATCH path is unaffected (it writes directly via `session.get()`, never through `_upsert_term_in_session`).

**Task 3 (D-03 — MEDIUM fix):**

SELECT in `_upsert_term_in_session` changed from exact `source_term == source_term` to `func.lower(TermDictionary.source_term) == func.lower(source_term)`. First-inserted casing wins. `get_term()` read path unchanged. CJK terms: SQLite `lower()` is identity on CJK codepoints — no regression. Prevention-only: no migration of existing duplicates.

## Test Suite

| Metric | Value |
|--------|-------|
| Baseline (before) | 566 passed |
| After all tasks | 588 passed, 1 skipped, 3 xfailed, 52 xpassed |
| New tests added | 22 |
| Failures | 0 |

### New Tests

**test_validate.py (Task 1):**
- `test_vn_label_hint_scaffold_raises_check8` (4 parametrized cases — nói:/xưng hô: structural forms)
- `test_vn_label_false_positive_battery` (6 parametrized cases — stage dirs, title-cards)
- `test_t53_credit_exemption_unaffected_by_vn_hint_change`

**test_engine.py (Task 1):**
- `test_parse_strips_vn_label_hint_e143_c148` (exact E143 c148 string)
- `test_parse_strips_bare_noi_colon_hint`
- `test_parse_preserves_envelope_title_card_no_noi_colon`
- `test_parse_english_label_hint_still_stripped_regression`

**test_merge_inferred.py (Tasks 2+3):**
- `test_term_rendering_carryforward_prior_kept`
- `test_term_rendering_carryforward_first_write_fills`
- `test_term_rendering_carryforward_locked_still_protected`
- `test_term_rendering_api_edit_not_carryforward_guarded`
- `test_case_variant_upsert_resolves_to_existing_row`
- `test_case_variant_upsert_carryforward_applies_across_case`
- `test_cjk_term_unaffected_by_case_insensitive_lookup`

## TDD Gate Compliance

All three tasks follow the RED/GREEN sequence:

| Task | RED commit | GREEN commit | Gate |
|------|-----------|-------------|------|
| 1 | c0490e2 `test(260612-7kt): RED — VN-label hint scaffold detection missing` | b82fcc0 `fix(260612-7kt): catch translated-label hint scaffold in both defense layers` | PASS |
| 2 | b069688 `test(260612-7kt): RED — term rendering carry-forward missing` | 5d461c4 `fix(260612-7kt): term rendering carry-forward (prior > inference for unlocked rows)` | PASS |
| 3 | 98a1e3a `test(260612-7kt): RED — case-variant upsert creates duplicate term rows` | 9247472 `fix(260612-7kt): case-insensitive term upsert lookup prevents duplicate rows` | PASS |

## Deviations from Plan

None — plan executed exactly as written.

## Hard Constraints Verified

- validate.py checks 1-7/9-12 logic: NOT touched. Only Check 8 OR condition extended.
- reconcile.py: NOT touched.
- attribute.py: NOT touched.
- Address-map carry-forward ladder: NOT touched.
- Alembic migrations: NOT added (prevention-only for Task 3; no schema change needed).
- merge.py compute_field_changes generic behavior: NOT changed.
- Task 1 regexes: false-positive battery passed — `(nói to)`, `(nói chậm rãi)`, `(Hồi 01: Mở Đầu)`, `(Phàm Nhân Tu Tiên Ký)`, t53 credit cue all unaffected.
- Task 2 carry-forward: apply_human_edit_term path NOT routed through guard (confirmed by test).

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

All 6 modified files found. All 6 commits verified (c0490e2, b82fcc0, b069688, 5d461c4, 98a1e3a, 9247472). Full suite: 588 passed, 0 failures.
