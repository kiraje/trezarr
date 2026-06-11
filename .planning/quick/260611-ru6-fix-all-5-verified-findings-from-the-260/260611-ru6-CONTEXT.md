# Quick Task 260611-ru6: Fix all 5 verified audit findings — Context

**Gathered:** 2026-06-11
**Status:** Ready for planning

<domain>
## Task Boundary

Fix ALL findings from the 260611-l74 cross-episode proving audit (verdict BLOCK, finding-verifier 13 VERIFIED / 0 REFUTED). Code-level fixes + tests on branch `fix/audit-l74-regressions`. The findings, with line-precise verified evidence, live in:
- `.trezarr-harness/CONSISTENCY-AUDIT-20260611_121500.md` (synthesis + fix backlog)
- `.trezarr-harness/_workspace/02_bible-consistency-auditor.md` (R1/R2 data + code evidence)
- `.trezarr-harness/_workspace/02_vietnamese-linguist.md` (R3/R4 cue evidence)
- `.trezarr-harness/_workspace/03_verdicts.md` (adversarial verification, incl. WHY each leak bypasses each check)

</domain>

<decisions>
## Implementation Decisions (LOCKED)

### R1 — transition branch must respect the precedence ladder (reconcile.py:442-472, _derive_transition_terms Step 3 at 319-321)
- The scy ladder is canon: **lock > genuine evolution (event WITH usable terms) > carried Bible pair > safe-default (truly-new dyad only)**.
- When a relationship_event matches but yields NO usable terms (no attribution-confirmed survivors, no suggested terms persistable): the established existing_map pair MUST carry forward (same as the no-event case). Falling to get_safe_default for an ESTABLISHED dyad is the verified regression.
- Preserve: genuine evolution with attribution-confirmed terms still wins over the carried pair (BIBLE-07, see memory relationship-transition-terms-from-attribution); locks always win; truly-new dyads still safe-default.

### R2 — derive_episode_key must parse Plex `NxNN` stems (engine.py:130-157)
- Extend parsing to ` - 6x19 - ` style stems (case-insensitive, 1-2 digit season, 1-3 digit episode) → normalize to S06E19.
- ALSO guard the collision class: a relationship_event stamped S00E00 (cold-Bible default) must NOT match every S00E00-keyed run. Decide the guard in planning (e.g., S00E00 episode key = "unknown" → transition branch skipped entirely, carry-forward path used). Both halves required: the parser fix alone leaves other unparseable stems re-firing events.

### R4 — close the three gate leak classes (validate.py)
- Class 1+2 (`(Correct; "tôi"→"anh" is the right pair; no violation)`, `(No violation)`): parenthetical attribution-commentary must be caught even when the cue/parenthetical contains Vietnamese diacritics (the verified bypass: Check 12 skips parentheticals w/ VN diacritics, Check 10 skips diacritic-bearing cues). Add a targeted pattern for review/attribution meta-commentary (e.g. anchored English "no violation", "correct;", "right pair" inside parentheses) — NOT a blanket un-skip that re-breaks legit Vietnamese parentheticals (envelope preservation, title cards must keep passing).
- Class 3 (raw `<<T153` unclosed sentinel): catch unclosed/orphan sentinel fragments (`<<T\d+` without closing `>>`), both raw and HTML-escaped (`&lt;&lt;T\d+`).
- Fail-safe direction preserved: gate may only get STRICTER; all 12 existing checks + t53 exemption + envelope preservation behavior unchanged (regression tests must prove this).

### R3 — one canonical rendering per character entity (name terms)
- Rule: **first-established LOCKED rendering wins per character**. When a name-term upsert (kfn auto-lock or inference) targets a character that already has a locked name term with a different vietnamese_rendering, the new row ADOPTS the existing canonical rendering instead of creating a competing locked row. Matching = via character linkage (and case-insensitive name normalization per bible-name-matching contract), across script variants (Latin source_term AND CJK source_term rows for the same character).
- Includes a REPAIR path for existing data (the live Moon Knight Bible has dual rows now): idempotent dedup that rewrites conflicting locked renderings to the canonical one — exposed so it can run via migration or on next merge for the affected series. No silent unlock; audit trail per bible invariants.
- Flag for vietnamese-linguist review in the harness pass: confirm first-locked-wins is linguistically safe for both registers (xianxia Hán-Việt vs casual Latin).

### LOW — vfe churn (7 pairs)
- The transition branch and survivors upsert sites must pass valid_from_episode=None when AFFIRMING an existing pair (extend the scy LOW fix to the two uncovered upsert call sites). vfe set only on genuine creation or genuine evolution.

### Process
- TDD: RED test per finding first (the audit gives exact reproduction data — use the snapshot JSONs / quoted cues as fixtures), then fix, then full suite.
- reconcile.py is MOAT CORE: trezarr-quality mode A review (linguist + bible-auditor + codec for validate.py) is REQUIRED after implementation, findings fixed before done.
- All existing contracts preserved: scy carry-forward tests, lock precedence, t53, envelope preservation, IMP-02/02b paths untouched except where named.

</decisions>

<specifics>
## Specific Ideas

- R1 RED fixture: Leg B reproduction — post-e01 Steven→Khonshu (tôi/ông) + S01E02 event with no suggested terms + no survivors → expect carried (tôi/ông), NOT (tôi/anh)/safe-default. Snapshots in `.planning/quick/260611-l74-cross-episode-proving-run-deploy-main-tr/`.
- R2 RED: `derive_episode_key("A Record of a Mortal’s Journey to Immortality - 6x19 - Episode 143")` → "S06E19" (currently S00E00).
- R4 RED: the three verbatim E03 cues (146/147/459 — quoted in 03_verdicts.md) must each fail validate_subdoc.
- R3 RED: store-level — second locked name-term upsert for same character with different rendering → adopts canonical, total locked renderings for that character == 1.

</specifics>

<canonical_refs>
## Canonical References

- `.trezarr-harness/CONSISTENCY-AUDIT-20260611_121500.md` + `_workspace/02_*.md`, `03_verdicts.md`
- `.planning/quick/260608-scy-*/260608-scy-SUMMARY.md` (the precedence ladder this restores)
- Memory contracts: relationship-transition-terms-from-attribution (BIBLE-07), bible-name-matching-case-insensitive

</canonical_refs>
