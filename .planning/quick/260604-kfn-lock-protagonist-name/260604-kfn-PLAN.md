---
quick_id: 260604-kfn
slug: lock-protagonist-name
status: in-progress
date: 2026-06-04
---

# Quick Task 260604-kfn: Lock character names (contract, not prompt)

## Goal

The ikq re-audit (CONSISTENT) noted the protagonist's name converged on "Daisy" **by prompt**, not
**by contract** — there was no `term_dictionary` row for 雏菊, so a future episode/model could
drift again. Make every character's on-screen name a **LOCKED Term Dictionary entry**, so the
canonical rendering is injected into the glossary AND protected from future inference drift.

## Key design finding (drove the approach)

`original_script_name` (e.g. 雏菊) is inferred at analyze time (`CharacterInference`) but NOT
persisted to the `character` table. So instead of a schema migration, reuse `term_dictionary`:
during analyze, create a locked term `雏菊 → Daisy` from the inferred script name. No migration.

## Changes (TDD — RED→GREEN; full suite 396 passed; bible-consistency-auditor PASS)

1. **`plan_character_name_terms(characters, existing_terms)`** (new, pure, in `bible/analyze.py`):
   for each character, pin `original_script_name` (else `original_latin_name`) → canonical
   (existing Term-Dictionary rendering for that Latin name, else the Latin name). Skips source
   forms already present (idempotent; never clobbers a human-edited term).
2. **Step 3.5 in `merge_bible_analysis`** (after term upsert, before address pairs): load current
   terms, plan, and `apply_human_edit_term(..., field="vietnamese_rendering", lock=True)` to
   create-and-lock each missing name term. Best-effort (never aborts the merge), idempotent,
   self-heals on the next translation run.

Tests: `test_plan_character_name_terms`, `test_merge_bible_analysis_locks_character_name_terms`
(tests/bible/test_merge_inferred.py).

## Review

bible-consistency-auditor: **PASS** (no BLOCKER/HIGH/MEDIUM). Confirmed D-34 lock safety (dedup is
stricter than the store's identity lookup → can't clobber an existing/locked term), idempotency
(no dup rows/events on re-run), single-txn ownership, stale-DTO defence, correct ordering. LOW
nits: (a) auto-lock borrows `source="lock"` + `episode_key=None` provenance — documented inline;
preferred fix (a `source="system"` kwarg on `apply_human_edit_term`) recorded as follow-up;
(b) the second `load_series_bible` is correct (sees Step-3 inserts) — no action.

## Verification

Rebuild → re-run S01E06 → confirm the live `term_dictionary` now has LOCKED script-name terms
(esp. `雏菊 → Daisy`) and the output stays consistent. Reset filesystem-only (delete `.vi.srt`),
no host DB writes (per the corruption rule).

## Follow-ups (recorded)
- Add `source="system"` (+ episode_key) provenance kwarg to `apply_human_edit_term` so system
  auto-locks are distinguishable from human UI locks in `bible_event`.
