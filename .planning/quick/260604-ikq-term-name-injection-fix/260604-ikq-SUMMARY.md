---
quick_id: 260604-ikq
slug: term-name-injection-fix
status: complete
date: 2026-06-04
commit: 8ad599d
---

# Summary — Inject Bible name/term glossary into the translate prompts

## Outcome: ✅ Stage-2 consistency BLOCKERs CLEARED (verified)

Fixed the 260604-gza audit's name/term drift by injecting the Series Bible glossary into the
translation prompts. Re-translated S01E06 and re-ran the full Mode-B audit (linguist →
finding-verifier, **11 VERIFIED / 0 REFUTED**).

**Re-audit verdict: CONSISTENT (regression-free).** BLOCKER 2→**0**, HIGH 3→**0**, MEDIUM 1, LOW 3.

| Entity | Before | After |
|---|---|---|
| Protagonist 雏菊 | **11 renderings** (Daisy ×12, Cúc cluster, raw 雏菊 ×18, Daisy-sama ×25) | **Daisy ×56** + Daisy-sama ×1; Cúc 0; raw 雏菊 0 |
| Sakura | mostly romaji | **Anh Đào ×28** (canonical); 6 self-intro "Sakura" |
| Tōchō | 5 ways + typo + romaji | **Đông Điệp ×5 only** |
| Rōsei | Lang Tinh + Ookami | **Lang Tinh only** |
| Raw CJK ideographs | 4 cues | **0** |
| Pronoun layer | coherent | **coherent — no regression** |

## Changes (code: commit 8ad599d; TDD, full suite 394 passed)
- `build_glossary_lines(bible)` — "source → canonical" from Term Dictionary + character names
  (char w/o a term row pinned to its `original_latin_name`; no double-listing).
- `build_translate_prompt(glossary=...)` — `[GLOSSARY - use EXACTLY]` block + a rule banning
  invented transliterations / Japanese romaji / source-script (Pass-3 was glossary-blind).
- Wiring: `_translate_batch`/`_translate_batch_inner` forward glossary; Pass-3 dispatch computes
  `build_glossary_lines(bible)` once per file.
- `build_review_prompt` — inject character names unconditionally (old substring filter could never
  match a Latin key against Chinese source).
- 4 new tests (RED→GREEN).

## Verification path
Rebuilt `trezarr:local` → re-ran S01E06 (job 7, done, 180s, clean: 0 `(source:`, 0 `<<T>>`,
374/374 cue parity, 0 CJK residue) → re-audit. Report:
`.trezarr-harness/CONSISTENCY-AUDIT-20260604_071352.md`.

## Incident (recovered, no data loss)
First re-run (job 6) was wedged by a transient `file is not a database` corruption I caused by
running host-side `sqlite3` WRITES against the live `/config/trezarr.db` while the daemon held it
open (macOS Docker bind-mount + concurrent SQLite). Recovered: stopped daemon → `integrity_check
ok`, Bible intact → backup → cleared the wedged job → restarted → re-ran via API only. Rule
recorded in memory: never host-write the live DB; reset a re-run by deleting the `.vi.srt` +
API trigger; DB writes only with the daemon stopped; reads use `?mode=ro`.

## Deferred / follow-ups (recorded as debt)
1. **[recommended] Lock the protagonist's name** — still NO `term_dictionary` row for 雏菊/Daisy;
   convergence is prompt-driven, not lock-enforced (recurrence risk). Have analyze persist + lock
   a name term per character. Domain: bible-consistency.
2. **[Phase-6] Address-map mutates across re-runs** — Daisy→Rōsei `em/anh`→`tôi/ngài` etc., backed
   by 3 `relationship_event` rows created during the runs. Output matches the *current* Bible, but
   the relational state shifted on re-translating the same episode; whether those inferred events
   are correct needs a Phase-6 reliability audit (needs ≥2 episodes).
3. Minor residuals: cue-240 register slip (MEDIUM), cue-79 `Daisy-sama` (LOW), surname
   Himeotaka/Himehawk split (LOW), `「」` corner-bracket punctuation carried from source (LOW).

## Files
- Code: `trezarr/translate/engine.py`, `tests/translate/test_engine.py`,
  `tests/translate/test_self_review.py` (commit 8ad599d).
- Output (UAT, clean): `…/Season 1/…1x06 - A Place to Call Home.vi.srt` (374 cues).
