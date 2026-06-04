---
quick_id: 260604-ikq
slug: term-name-injection-fix
status: in-progress
date: 2026-06-04
---

# Quick Task 260604-ikq: Inject Bible name/term glossary into the translate prompts

## Goal

Fix the Stage-2 consistency audit's BLOCKERs (260604-gza audit): the protagonist 雏菊 rendered
**11 different ways** in one episode, raw Chinese shipped in 4 cues, named characters drifting to
Japanese romaji — because the **Pass-3 translation prompt injected NO glossary** (only pronoun
hints), and Pass-4's term injection was substring-filtered (Latin term keys can never match a
Chinese source, so it injected nothing for CJK).

## Root cause (from the audit)

- `build_translate_prompt` (Pass-3, the primary pass) received `pronoun_hints` but never the Term
  Dictionary or character names → deepseek invented a fresh transliteration per cue.
- `build_review_prompt` (Pass-4) filtered terms by `source_term.lower() in source_combined` —
  impossible to match `"Sakura"` against `"樱"` → no names pinned for CJK sources.
- Same lesson as orphan-sentinel + Pass-4 scaffolding: the Bible HELD the canonical renderings;
  the harness just wasn't telling the model.

## Changes (TDD — RED→GREEN, full suite 394 passed)

1. **`build_glossary_lines(bible)`** (new) — emits `"source → canonical rendering"` lines: every
   Term Dictionary entry + every character name (a char with no term entry is pinned to its own
   `original_latin_name`, e.g. `Daisy → Daisy`; chars covered by a term aren't double-listed).
2. **`build_translate_prompt(..., glossary=...)`** — injects a `[GLOSSARY - use EXACTLY]` block +
   a rule: "use the exact Vietnamese rendering, identical in every line; never invent
   transliterations, use Japanese romaji, or leave source-language script." No glossary → prompt
   unchanged (back-compat).
3. **Wiring** — `_translate_batch` / `_translate_batch_inner` forward `glossary`; the Pass-3
   dispatch computes `build_glossary_lines(bible)` once per file and passes it to every batch.
4. **`build_review_prompt`** — inject character names UNCONDITIONALLY (not substring-filtered) so
   CJK sources still pin names.

Tests added: `test_glossary_block_in_translate_prompt`, `test_build_glossary_lines_from_bible`,
`test_translate_batch_forwards_glossary_to_prompt` (test_engine.py),
`test_build_review_prompt_injects_character_names_regardless_of_source` (test_self_review.py).

## Verification (the re-audit)

Rebuild → re-run S01E06 → re-run the trezarr-quality Mode-B audit. Expect the name BLOCKERs to
drop sharply (esp. Sakura/Rōsei/Tōchō which HAVE term entries → should pin to Anh Đào / Lang Tinh
/ Đông Điệp).

## Known limit (likely a follow-up)

The protagonist 雏菊 has **no Term Dictionary entry** and `character` has no source-script column,
so the glossary can only pin the Latin name "Daisy", not map `雏菊 → Daisy` explicitly. Pass-3 now
says "render the character as Daisy," which should reduce the 11-way drift, but full pinning may
need analyze to persist a `源script → canonical` term per character (Bible-completeness follow-up).
The re-audit will show whether the Latin-name pin alone is enough.

## Out of scope

- Cross-episode (Phase-06) — only S01E06 source on the volume.
- Bible-completeness (persisting source-script name terms) — follow-up if the re-audit shows the
  protagonist still drifts.
