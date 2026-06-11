# Cross-Episode Consistency Audit — 260611-l74 Proving Run

**Date:** 2026-06-11 · **Image:** `ghcr.io/kiraje/trezarr:9dbcb911…` (contains scy carry-forward + t53) · **Endpoint:** api.deepseek.com, concurrency 4
**Verdict: DRIFT FOUND / BLOCK — moat NOT cleanly proven. IMP-04 gate stays CLOSED.**
**Verifier tally:** 13 VERIFIED · 0 REFUTED · 1 UNCERTAIN (specialists: vietnamese-linguist + bible-consistency-auditor; adversarial verify: finding-verifier)

## Run evidence

| Episode | Job | Result | Cues | Notes |
|---------|-----|--------|------|-------|
| Mortal's Journey S06E19 | 12 | done | 167/167 | source = extracted embedded eng track |
| Moon Knight S01E01 | 6 | done (4th attempt lifetime) | 438/438 | Bible created: 9 chars/29 pairs/51 terms |
| Moon Knight S01E02 | 13 | done (3rd attempt this run) | 579/579 | 2 quarantines at concurrency 8 — gate held both times |
| Moon Knight S01E03 | 14 | done | 551/551 | first try |

t53 credit exemption **live-verified** (E02 cue 579 `字幕翻译： 虫二` shipped; file not quarantined). Concurrency 8 **degrades deepseek-v4-pro** (empty lines, mass Pass-4 failures) — 4 is the ceiling.

## Criteria verdicts

| Criterion | Leg A (xianxia, established Bible) | Leg B (Moon Knight, fresh Bible 2-hop) |
|-----------|-----------------------------------|----------------------------------------|
| A — no Vector-1 overwrite | **FAIL** (3 pairs flattened) | **FAIL** (Steven→Khonshu tôi/ông→tôi/anh) |
| B — no safe-default drop | **FAIL** (tại hạ/các hạ classical default) | PASS |
| C — name consistency | PARTIAL (Bạo Phong Sơn↔Phong Bạo Sơn flip) | **FAIL** (Layla = 3 renderings; every name 2–4) |
| D — leak gate | PASS (E19 clean) | **FAIL** (E03 cues 146/147/459 — new leak classes) |
| E — cue-count sanity | PASS | PASS |

## What HELD (the partial win)

- **Cue-text pronoun carry worked across all hops**: Khonshu→Marc/Steven `ta/ngươi` stable through E01→E02→E03 (1/7/11 instances); Marc↔Steven, Layla dyads stable; Leg A no visible drift. Reciprocity coherent. No intimate-on-guess.
- **Bible E02→E03 hop: 40/40 pairs byte-identical** — carry-forward works when the episode key is correct and no spurious event fires.
- All 23 Leg-A locks + all Leg-B locks held; no character re-ID/re-gender; idempotent ledger; gate blocked every corrupt intermediate.

## VERIFIED BLOCKERS

**R1 — Transition branch bypasses scy carry-forward (`reconcile.py:442→472` above the carry `else` at 526-540).** When a `relationship_event` matches but carries no suggested terms and the episode has no confident survivors, `_derive_transition_terms` Step 3 (319-321) falls to `get_safe_default`, flattening established pairs: Leg A `Mei→Han (muội/huynh)→(tại hạ/các hạ)`, `Elder2→Zhou (lão phu/lão hữu)→(tại hạ/các hạ)`, `Han→Mei` lost `Mai cô nương`; Leg B `Steven→Khonshu (tôi/ông)→(tôi/anh)` (now reciprocally incoherent vs `Khonshu→Steven ta/ngươi`). **Latent in this run's cue text** (dyads barely voiced) — a forward-propagating time bomb for E04+/E20+.

**R2 — `derive_episode_key` (`engine.py:130-157`) can't parse Plex `6x19` stems → falls back to `S00E00`**, colliding with cold-Bible relationship_events (all stamped S00E00) → every cold event re-fires its transition branch on EVERY run of that series. Verified by running the function on the real stem. Signature: all new Leg-A pairs carry vfe `S00E00`; zero `S06E19` anywhere. (Leg B had correct keys — proving R1 is a code defect independent of R2.)

**R3 — Name canonicalization: dual competing LOCKED term rows** (Latin `Steven Grant` AND `史蒂文·格兰特→Sử Địch Văn` both locked; Khonshu/Ammit Latin rows unlocked) → every Moon Knight recurring name ships 2–4 renderings (Layla/Lai Lạp/La Ni). Fix = ONE canonical rendering per entity, not "add a lock".

**R4 — Three leak classes bypass the 12-check gate** (E03): cue 146 `(Correct; "tôi"→"anh" is the right pair; no violation)` and 147 `(No violation)` — Check 12 skips parentheticals containing VN diacritics, Check 10 skips diacritic-bearing cues; cue 459 raw `<<T153` — unclosed sentinel yields 0 ASCII tokens for Check 6.

**HIGH:** Khonshu 2 renderings within single episodes; Leg-A place/elder name drift vs gold. **MEDIUM:** unlocked term oscillation (Scarab/Ammit/Osiris Hán-Việt↔English). **LOW:** vfe churn on 7 affirmed pairs (transition + survivors upsert sites — scy LOW fix didn't cover them).

## IMP-04 gate decision

**CLOSED.** Record: "IMP-04 gate: BLOCKED 2026-06-11 — proving run executed; pronoun carry verified in cue text and in the clean E02→E03 hop, but transition-branch regression (R1) + episode-key collision (R2) corrupt established pairs at the data level. Re-open only after R1+R2 fixed, both legs re-run, zero unjustified pair changes."

## Fix backlog (ordered)

1. R1: transition branch must respect the precedence ladder — carried Bible pair beats event-with-no-terms (reconcile.py).
2. R2: extend `derive_episode_key` to parse `NxNN` stems; guard S00E00 event collision.
3. R4: close the three gate gaps (Check 10/12 diacritic skips, Check 6 unclosed sentinel).
4. R3: canonical-rendering dedup for name terms (one locked winner per entity).
5. LOW: vfe stability on the two upsert sites.
6. Then: re-run both legs, re-audit, reconsider IMP-04.

Detailed findings + verdicts: `.trezarr-harness/_workspace/{02_vietnamese-linguist,02_bible-consistency-auditor,03_verdicts,02_profile}.md`
