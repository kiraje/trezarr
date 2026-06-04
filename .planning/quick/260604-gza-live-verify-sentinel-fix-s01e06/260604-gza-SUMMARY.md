---
quick_id: 260604-gza
slug: live-verify-sentinel-fix-s01e06
status: complete
date: 2026-06-04
commit: 730f062  # the fix (landed by sync); this task added no code commit
---

# Summary — Live-verify the orphan-sentinel fix on S01E06

## Verdict: THESIS CONFIRMED — the harness, not deepseek, was the blocker

Re-ran the live deepseek translation of the one episode that previously quarantined
(`…1x06 - A Place to Call Home.zh.srt`, series 62), now with orphan-sentinel recovery
(`730f062`) running in the container.

**Job 4: `done`, manual, 1 attempt, ~2m48s, no quarantine** (vs job 3 on the old code:
`quarantined` — "Orphan sentinel"). A `.vi.srt` was written; ledger flipped
`quarantined → done`.

- **57 hallucinated orphan sentinels stripped, 0 sentinel-integrity failures** — the fix
  did exactly its job. deepseek hallucinated `<<TN>>` tokens into untagged cues; all were
  removed instead of quarantining the file.
- **374/374 cue parity**, **0 leftover `<<T>>` tokens**, UTF-8 clean, gate passed.

deepseek-v4-pro can drive this pipeline to a written sidecar. The "use a frontier model"
conclusion in the v1.0 findings doc was confounded — the harness was discarding the model's
output (400s, whole-file quarantines) before its quality could be judged.

## BUT: output is not shippable — a SECOND harness bug surfaced

**CRITICAL — Pass-4 self-review corrupts ~28% of cues.** 104 / 374 output cues contain the
literal review-prompt scaffolding spliced into the final subtitle, e.g.:

    (source: 不要) Đừng
    (source: 母亲…) Mẹ...

Mechanism: `build_review_prompt` formats lines as `[N] (source: <orig>) <vi>`. When deepseek
echoes the whole line back (scaffolding included), `parse_numbered_response` accepts it and
`_splice_review_corrections` overwrites the good Pass-3 Vietnamese with the scaffolded line.
The 7-check gate misses it because the trailing `Đừng`/`Mẹ` still clears the per-line VI
diacritic ratio. **We traded a hard quarantine for silent corruption** — the worse failure.

Irony: the batches where Pass-4 *fails to parse* (BatchValidationError → D-59 fallback to
pre-review) stay CLEAN; the batches where it "succeeds" get corrupted. Pass-4 is currently
**net-negative**.

## Bugs found (recorded as debt — out of this task's scope)

1. **[CRITICAL] Pass-4 splice corruption** — `_splice_review_corrections` accepts corrections
   containing `(source:` scaffolding / raw CJK. Fix: defensive splice (reject a "correction"
   that contains the scaffolding, raw CJK above threshold, or diverges too far from pre-review)
   AND add a gate check for the `(source:` literal so corruption can never ship. Fastest
   stopgap: `enable_self_review=false` (D-60) → clean Pass-3 output. Domains: pipeline-
   reliability + codec-fidelity (gate).
2. **[LOW] Pass-1 register merge** — `WARNING trezarr.bible.analyze: Pass 1: failed to merge
   register for series 1: 'Series' object has no attribute 'series_id'`. Register never
   persists (series.register empty). The known merge_inferred `.series_id` bug. Domain:
   bible-consistency.
3. **[LOW] Numbered-line parser fragility (Pass 4)** — deepseek review responses have
   missing/duplicate line numbers → BatchValidationError. Harmless here (D-59 fallback keeps
   clean text) but it silently disables self-review on those batches.

## Stage-2 quality observations (deferred — needs clean output first)

- Inconsistent name rendering: 雏菊 (Daisy) → "Cúc" 48×, raw 雏菊 18×; 樱 (Sakura) → "Sakura"
  23×, raw 樱 15×; "Daisy" (the Bible's `original_latin_name`) appears 0× (term-dictionary not
  applied consistently). Much of the raw CJK is actually inside the Pass-4 `(source:)` leak.
- Baseline Address-Map asymmetry: Daisy→Rōsei `em/anh` vs Rōsei→Daisy `tôi/chị` — resolve in
  the pronoun audit.

## Recommended next step

Spin up a follow-up to fix Pass-4 (defensive splice + gate hardening), OR disable self-review
(`enable_self_review=false`) and re-run to get a clean output to assess deepseek's *real*
translation/pronoun quality (Stage 2). Either way the path to "best result" is harness work,
not a model swap — confirming the original thesis.

## Files / actions
- No code committed by this task (fix `730f062` landed via sync; verified green: sentinel 10
  passed, translate suite 79 passed/10 xpassed).
- Redeployed: `docker compose up -d --build` (container recreated from the fix, healthy).
- Output (UAT media, not real Plex): `…/Season 1/…1x06 - A Place to Call Home.vi.srt`
  (30 KB, 374 cues, 104 corrupted by Pass-4).
