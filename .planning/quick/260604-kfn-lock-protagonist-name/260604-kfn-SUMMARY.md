---
quick_id: 260604-kfn
slug: lock-protagonist-name
status: complete
date: 2026-06-04
commit: 4d6e9cd
---

# Summary — Lock character names (contract, not prompt)

## Outcome: ✅ Character names are now LOCKED Bible terms — confirmed on the live Bible

Closed the ikq audit's "consistent-by-prompt, not by-contract" gap. During analyze, every
character's on-screen name is now persisted as a **LOCKED** Term Dictionary entry.

**Live confirmation (job 8, done):** the real `term_dictionary` gained 5 locked name terms
(pre-run: 0) — `雏菊 → Daisy`, `樱 → Anh Đào`, `狼星 → Lang Tinh`, `冻蝶 → Đông Điệp`, `雪 → Yuki`,
each with `locked_fields=["vietnamese_rendering"]`. Total terms 20 → 25. The protagonist's name is
now contract-protected (safe from future inference drift) AND injected into the translate glossary.

Output stayed consistent: `Daisy ×88` (↑ from 56 — the explicit `雏菊→Daisy` term increased
adoption), `Cúc 0`, `Anh Đào ×57`, `(source: 0`, `<<T>> 0`.

## Honest residual / known ceiling
`raw 雏菊 ×2` slipped through this run (job 7 had 0) — run-to-run model non-determinism. A LOCKED
term still reaches the model as a **prompt** instruction; `locked_fields` protects the Bible value,
it does not force the output. Driving raw-name leakage to a hard zero needs the **output-enforcement**
option (deterministic post-translation normalization) that was deferred. The Bible-side lock (the
chosen scope) is fully in place.

## Changes (commit 4d6e9cd; TDD, full suite 396 passed; bible-consistency-auditor PASS)
- `plan_character_name_terms(characters, existing_terms)` (pure) — pins each character's
  `original_script_name` (else `original_latin_name`) → canonical (existing term rendering for that
  Latin name, else the Latin name); skips source forms already present (idempotent; never clobbers
  a human-edited term — dedup is stricter than the store's identity lookup, audit-confirmed).
- `merge_bible_analysis` Step 3.5 — create-and-LOCK each missing name term via
  `apply_human_edit_term(..., field="vietnamese_rendering", lock=True)`. Best-effort (never aborts
  the merge / quarantines), runs after term upsert + before address pairs, self-heals each run.
- No schema migration (reused `term_dictionary` + the inferred `original_script_name`).
- Tests: `test_plan_character_name_terms`, `test_merge_bible_analysis_locks_character_name_terms`.

## Review
bible-consistency-auditor: **PASS** (no BLOCKER/HIGH/MEDIUM). Confirmed D-34 lock safety,
idempotency/carry-forward, single-txn ownership, stale-DTO defence, ordering. LOW nits: auto-lock
borrows `source="lock"`+`episode_key=None` provenance (documented inline; preferred fix = a
`source="system"` kwarg on `apply_human_edit_term` → follow-up); second `load_series_bible` is
correct (no action).

## Verification path
Rebuilt `trezarr:local` → re-ran S01E06 (job 8) → confirmed 5 locked name terms in the live DB
(read-only) + output consistency. Reset filesystem-only (deleted `.vi.srt`); no host DB writes.
Note: the working tree held another machine's uncommitted `web/routes/bible.py` WIP (parses +
imports OK, unrelated to translation) — built over ephemerally, NOT committed (only my 2 files in
4d6e9cd).

## Follow-ups (recorded)
- [optional, for hard guarantee] **Output-enforcement**: deterministic post-translation
  normalization that rewrites known name variants → canonical (would zero out the residual raw 雏菊).
- [LOW] Add `source="system"` (+episode_key) provenance kwarg to `apply_human_edit_term` so system
  auto-locks are distinguishable from human UI locks in `bible_event`.
