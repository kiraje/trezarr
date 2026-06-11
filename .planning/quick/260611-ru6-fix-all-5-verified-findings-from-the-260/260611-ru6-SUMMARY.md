---
phase: quick-260611-ru6
plan: 01
subsystem: translate/reconcile, translate/engine, translate/validate, bible/analyze, bible/store
tags: [tdd, reconcile, validate, bible, pronoun, episode-key, gate, name-terms, vfe]
dependency_graph:
  requires: [260611-l74-cross-episode-proving-audit]
  provides: [all-5-audit-blockers-fixed, cross-episode-prove-unblocked]
  affects: [reconcile.py, engine.py, validate.py, analyze.py, store.py]
tech_stack:
  added: []
  patterns:
    - locked_sources guard in plan_character_name_terms (R3 first-locked-wins)
    - dedup_canonical_name_terms async repair function (store.py)
    - is_genuine_evolution flag for vfe stability (LOW fix, reconcile.py)
    - ATTRIBUTION_META_RE + UNCLOSED_SENTINEL_RE regex patterns (validate.py)
    - NxNN Plex stem parsing (engine.py derive_episode_key)
    - S00E00 cold-Bible guard in reconcile_attributions transition branch
key_files:
  created:
    - tests/bible/test_analyze_name_terms.py
  modified:
    - trezarr/translate/reconcile.py
    - trezarr/translate/engine.py
    - trezarr/translate/validate.py
    - trezarr/bible/analyze.py
    - trezarr/bible/store.py
    - tests/translate/test_reconcile.py
    - tests/translate/test_engine.py
    - tests/translate/test_validate.py
decisions:
  - "R1: _derive_transition_terms Step-3 carry-forward — established dyads never fall to safe-default due to term-less event (D-01 first-locked-wins ladder restored)"
  - "R2: derive_episode_key parses Plex NxNN stems via m_plex regex; S00E00 guard skips transition branch (cold-Bible collision closed)"
  - "R4: ATTRIBUTION_META_RE anchored on parenthetical English review phrases (no false positives on Vietnamese dialogue); UNCLOSED_SENTINEL_RE catches raw <<TN without >>"
  - "R3: locked_sources set in plan_character_name_terms blocks CJK spec when Latin name already locked; dedup_canonical_name_terms repairs existing dual-row data idempotently"
  - "LOW: is_genuine_evolution flag in transition branch — vfe bumps only when terms actually change (D-05/D-53 combined contract)"
metrics:
  duration: ~60 minutes (continuation session)
  completed: 2026-06-11
  tasks: 5
  tests_before: 533 (pre-session, from context summary)
  tests_after: 541 (536 after R4, 539 after R3, 541 after LOW)
  new_tests: 13 (R1: 4, R2: 4, R4: 3, R3: 3, LOW: 2)
---

# Phase quick-260611-ru6 Plan 01: Fix All 5 Verified Audit Findings — Summary

**One-liner:** All 5 BLOCK-verdict findings from the 260611-l74 cross-episode proving audit fixed via strict TDD — carry-forward ladder restored, Plex NxNN parsing added, gate leak classes closed, name-term dedup guarded, vfe churn eliminated.

## Tasks Completed

| # | Name | Commit (RED) | Commit (GREEN) | Tests Added |
|---|------|--------------|----------------|-------------|
| 1 | R1: transition carry-forward | 9c8c99d | f55b91a | 4 (A/B/C/D) |
| 2 | R2: NxNN parse + S00E00 guard | ab91c26 | 21ba736 | 4 (E/F/G/H) |
| 3 | R4: gate leak classes | 1169973 | 901f85c | 3 (I/J/K) |
| 4 | R3: canonical name rendering | 240d6c3 | 8231b15 | 3 (L/M/N) |
| 5 | LOW: vfe stability | 07e55b2 | b7ea492 | 2 (O/P) |

## What Was Fixed

### R1 — transition-branch carry-forward (_derive_transition_terms Step 3)

**Finding:** When a `relationship_event` matched for an established dyad but had no usable terms (no suggested terms, no attribution-confirmed survivors), Step 3 fell to `get_safe_default()`. This flattened established pronoun pairs (e.g., tôi/ông from E01) to a stranger safe-default (tôi/anh or tôi/bạn) on every subsequent episode where a term-less event matched.

**Fix:** Inserted a carry-forward check in `_derive_transition_terms` before the `get_safe_default()` fallback. If `existing` is not None and has both `self_term` and `address_term`, returns the existing pair unchanged. Only truly-new dyads (no prior entry or entry with None terms) fall to safe-default. BIBLE-07 (Step 1: suggested terms win) and lock precedence unaffected.

### R2a — derive_episode_key NxNN Plex stems (engine.py)

**Finding:** Filenames using the Plex naming convention (e.g., `Show - 6x19 - Title.en.srt`) produced `S00E00` (cold-Bible default) because the existing `SxxExx` regex didn't match them.

**Fix:** Added `m_plex = re.search(r'(\d{1,2})[xX](\d{1,3})', stem)` as an `elif` branch after the primary `SxxExx` match in `derive_episode_key`. Returns `f"S{int(m_plex.group(1)):02d}E{int(m_plex.group(2)):02d}"`. `SxxExx` still takes priority (elif); fallback `S{season:02d}E00` still fires for stems with neither form.

### R2b — S00E00 transition guard (reconcile.py)

**Finding:** When episode_key was `S00E00` (from an unparsed Plex stem), every `relationship_event` stamped `S00E00` fired — for Leg A series-1, all 12 events fired on every run, re-flattening the established pair to whatever the event's safe-default was.

**Fix:** Added `and episode_key != "S00E00"` to the outer `if getattr(settings, "enable_relationship_events", True)` condition in `reconcile_attributions`. The S00E00 key is the cold-Bible default and must never match real events. Lock check still runs before this guard (lock always wins even on S00E00).

### R4 — validate.py gate leak classes

**Finding (Check 8, Classes 1 and 2):** Attribution meta-commentary leaked past Check 8 (the scaffold-leak gate) because it contained Vietnamese diacritics (e.g., `(Correct; "tôi"→"anh" is the right pair; no violation)`), causing Check 10 and Check 12 to skip the cue entirely. E03 cues 146 and 147 verified.

**Fix:** Added `ATTRIBUTION_META_RE = re.compile(r'\(\s*(?:no\s+violation|correct\s*;)', re.IGNORECASE)` to Check 8's condition. The phrase `"no violation"` and `"correct;"` inside a parenthetical cannot appear in genuine Vietnamese dialogue — zero false positives. Non-recursive pattern, ASVS L1 V5 compliant.

**Finding (Check 6, Class 3):** A raw unclosed sentinel `<<T153` (no closing `>>`) bypassed `SENTINEL_RE` (which requires `>>`) and also bypassed Check 10 (0 ASCII words ≥ 2 letters). E03 cue 459 verified.

**Fix:** Added `UNCLOSED_SENTINEL_RE = re.compile(r"<<T\d+(?!>>)|&lt;&lt;T\d+")` and added it as an `or` condition in Check 6's loop. Negative lookahead prevents matching already-closed sentinels (no double-fire); HTML-escaped form is belt-and-suspenders.

### R3 — canonical name rendering (analyze.py + store.py)

**Finding:** The `plan_character_name_terms` function (Step 3.5 kfn auto-lock) created a CJK locked row for a character's `original_script_name` even when the Latin name already had a locked row. This produced competing locked renderings in the Term Dictionary (e.g., `Steven Grant` → `Steven Grant` AND `史蒂文·格兰特` → `Sử Địch Văn · Cách Lan Đặc`), which the translate-prompt glossary injected both, producing split renderings in output.

**Fix (analyze.py):** Added a `locked_sources` set tracking which Latin names already have a `vietnamese_rendering`-locked row. Before appending a `NameTermSpec`, checks if `latin.lower() in locked_sources` — if so, skips the spec entirely. Also adds the Latin name to `locked_sources` after emitting a spec so subsequent CJK forms in the same batch are also blocked.

**Fix (store.py):** Added `dedup_canonical_name_terms(session_factory, *, series_id)` async repair function. Loads all locked TermDictionary rows, partitions into Latin-source (canonical) vs CJK-source (secondary) rows, and rewrites secondary rows whose `vietnamese_rendering` differs from the canonical. Emits a `BibleEvent(source="lock")` audit record per rewrite. Idempotent (second call returns empty list). Series-id scoped (T-ru6-04).

### LOW — vfe churn on carry-affirm (reconcile.py)

**Finding:** The transition branch passed `valid_from_episode=episode_key` unconditionally to `upsert_address_pair`, even when `_derive_transition_terms` returned the exact same terms as the existing entry (the R1 carry-affirm path). The 260611-l74 audit observed 7 pairs per E02 run having their `valid_from_episode` bumped with no term change.

**Fix:** Added `is_genuine_evolution = not (existing is not None and new_self == existing.self_term and new_addr == existing.address_term)` after `_derive_transition_terms` returns. Passes `valid_from_episode=episode_key if is_genuine_evolution else None`. Genuine evolution (new terms from suggested terms or survivors) still bumps vfe as before (D-53 provenance contract preserved).

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

- R3 Test M (plan_character_name_terms: CJK spec adopts canonical rendering) passed even in RED state — the H2 `rendering_by_latin` lookup already correctly handles the unlocked-row case. The critical fix was the locked-row guard for Test L.
- The LOW fix's `is_genuine_evolution` mirrors the same logic added in the carry-forward path of `_derive_transition_terms` (R1 fix) — they are consistent by construction.

## Self-Check

**Files exist:**
- trezarr/translate/reconcile.py: FOUND
- trezarr/translate/engine.py: FOUND
- trezarr/translate/validate.py: FOUND
- trezarr/bible/analyze.py: FOUND
- trezarr/bible/store.py: FOUND
- tests/translate/test_reconcile.py: FOUND
- tests/translate/test_engine.py: FOUND
- tests/translate/test_validate.py: FOUND
- tests/bible/test_analyze_name_terms.py: FOUND

**Commits exist:** All 10 commits visible in git log (9c8c99d through b7ea492).

**Test count:** 541 passed, 1 skipped, 3 xfailed, 52 xpassed — verified.

## Self-Check: PASSED

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes beyond those planned and threat-modelled in the PLAN.md `<threat_model>` section.

---

## Review Fixes (Round 2)

Harness review of the round-1 code produced four findings across pipeline-reliability-reviewer, bible-consistency-auditor, vietnamese-linguist, and codec-fidelity-guardian. All four fixed via TDD.

**Tests before round 2:** 541 (baseline at start of this session)
**Tests after round 2:** 548 (+7 new tests)

### Finding 1 — [HIGH, pipeline] Unanchored NxNN regex false-matches resolution/aspect strings

**Finding:** `engine.py:162` used `re.search(r"(\d{1,2})[xX](\d{1,3})", stem)` — unanchored. Verified false matches: `Show.1024x768.WEB` → S24E768, `Some.Show.720x480.DVDRip` → S20E480, `Show.1920x1080.WEB` → S20E108. The sibling parser at `library.py:51` already uses digit-boundary lookarounds to avoid this exact problem.

**Fix:** Added `(?<!\d)` lookbehind and `(?!\d)` lookahead to the `m_plex` search pattern, mirroring `library.py:51`. Added a TODO comment pointing to the MEDIUM shared-parser tech debt. Existing NxNN happy-path tests (6x19, 1x5, 12x103) unaffected.

**RED tests (3):** `test_r2_resolution_1024x768_does_not_parse_as_episode`, `test_r2_resolution_720x480_does_not_parse_as_episode`, `test_r2_resolution_1920x1080_does_not_parse_as_episode` — all failed before fix, pass after.

| Commit | Description |
|--------|-------------|
| 3c5700b | RED: resolution/aspect-ratio stems must not parse as episode keys |
| a1d2b98 | FIX: anchor NxNN regex with digit-boundary lookarounds (engine.py) |

### Finding 2 — [HIGH×2, bible-auditor + linguist] dedup false-merge + CJK-first guard hole

**Finding (a) — dedup false-merge:** `dedup_canonical_name_terms` (store.py:1534-1538) used a `len(canonical_rows) == 1 → rewrite ALL secondary rows` heuristic. In xianxia series with multiple CJK-named characters (韩立/Hàn Lập, 南宫婉/Nam Cung Uyển) plus one unrelated Latin-named character (Mei/Mai), the single Latin row triggered the heuristic and ALL CJK rows were rewritten to 'Mai' — catastrophic identity collapse.

**Finding (b) — wrong-register canonical:** The heuristic elected the Latin/pinyin row as canonical. For a CJK-first-locked character (韩立→Hàn Lập locked first, then Han Li→Han Li added later), the correct Hán-Việt rendering was overwritten to bare pinyin.

**Finding (c) — guard ordering hole in plan_character_name_terms:** `locked_sources` was built from existing_terms `source_term` values only. A CJK-first locked row (`source_term='韩立'`) populated `locked_sources = {'韩立'}`. On a second run with English-only source (no `original_script_name`), the character inference for 'Han Li' saw `'han li' ∉ {'韩立'}` → guard did NOT fire → competing Latin spec was emitted → dual-lock created.

**Fix (store.py):** Removed the `len(canonical_rows) == 1` unconditional-rewrite heuristic entirely. `TermDictionary` has no `character_id` FK, so character linkage cannot be established. Function returns `[]` with a diagnostic log. Docstring updated with the canonical-by-first-locked rule for when a FK migration is added, and with FIX3 atomicity note. Test N updated to expect `events == []` (no rewrites without FK linkage).

**Fix (analyze.py):** Extended `locked_sources` population after the existing-terms loop by cross-referencing the characters list with two linkage mechanisms: (1) `character.original_script_name` in `locked_sources` → add character's Latin name; (2) `character.vietnamese_rendering` matches a locked CJK row's rendering → add character's Latin name. This covers the second-run case where `original_script_name` is absent.

**RED tests (4):** `test_r3_fix2_i_xianxia_multi_char_no_false_merge`, `test_r3_fix2_ii_cjk_first_locked_is_canonical`, `test_r3_fix2_iii_cjk_first_lock_blocks_latin_competitor`, `test_r3_canonical_n_dedup_no_rewrite_without_character_linkage` (test N updated).

| Commit | Description |
|--------|-------------|
| 9e36342 | RED: xianxia multi-char false-merge + CJK-first guard hole (including updated test N) |
| 42fc991 | FIX: remove false-merge heuristic + close CJK-first guard hole |

### Finding 3 — [LOW, bible-auditor] Non-atomic dedup repair loop

**Finding:** The repair loop opened N separate `session.begin()` contexts (one per row rewrite). A crash mid-loop left a partial repair.

**Resolution:** FIX 2 removed the write loop entirely (no rewrites without character FK linkage). FIX 3 is moot. A comment was added to the docstring specifying that when the FK migration enables writes, the repair MUST use a single `async with session.begin()` wrapping all rewrites.

| Commit | Description |
|--------|-------------|
| 153c636 | FIX: document FIX3 atomicity as resolved by FIX2 write-removal |

### Finding 4 — [LOW, codec] Misleading `(?!>>)` comment on UNCLOSED_SENTINEL_RE

**Finding:** The comment at `validate.py:100-101` claimed `(?!>>)` "prevents matching the closed form `<<T153>>`". This is factually wrong. Greedy backtracking: `\d+` tries `153`, lookahead fails (sees `>>`), engine backtracks to `\d+='15'`, lookahead sees `3` (not `>>`) → matches `<<T15` inside `<<T153>>`. The double-fire is harmless (SENTINEL_RE already catches the closed form), but the comment's claimed guarantee is false.

**Fix:** Rewrote the comment to accurately describe: (a) the backtracking mechanism, (b) that UNCLOSED_SENTINEL_RE DOES match the closed form at a shorter offset, (c) that closed orphans are definitively caught by SENTINEL_RE regardless, and (d) that the double-fire is intentional belt-and-suspenders. No code change.

**RED test:** `test_fix4_red_unclosed_sentinel_re_comment_claimed_closed_no_match` — asserted the comment's claim (search returns None), failed because regex DOES match.

**GREEN test:** `test_fix4_unclosed_sentinel_re_closed_form_does_match_via_backtrack` — asserts actual behavior: closed form matches at `'<<T15'`; genuine unclosed form matches at `'<<T153'`.

| Commit | Description |
|--------|-------------|
| acadf4b | RED: UNCLOSED_SENTINEL_RE comment false-claims no closed-form match |
| d2ffd3b | FIX: correct misleading UNCLOSED_SENTINEL_RE comment on lookahead |

### Round 2 Summary

| Finding | Severity | Files | Result |
|---------|----------|-------|--------|
| FIX 1: NxNN unanchored regex | HIGH | engine.py, test_engine.py | Fixed — digit-boundary lookarounds |
| FIX 2a: dedup false-merge heuristic | HIGH (bible-auditor) | store.py, test_analyze_name_terms.py | Fixed — heuristic removed; safe skip |
| FIX 2b: wrong-register canonical | HIGH (linguist) | store.py | Fixed — via heuristic removal |
| FIX 2c: guard ordering hole (CJK-first) | HIGH (linguist) | analyze.py, test_analyze_name_terms.py | Fixed — rendering-match linkage |
| FIX 3: non-atomic repair | LOW (bible-auditor) | store.py | Resolved by FIX 2 + comment |
| FIX 4: misleading comment | LOW (codec) | validate.py, test_validate.py | Fixed — comment corrected |
