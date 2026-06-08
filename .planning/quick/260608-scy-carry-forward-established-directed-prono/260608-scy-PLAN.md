---
phase: quick-260608-scy
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - trezarr/translate/reconcile.py
  - trezarr/bible/analyze.py
  - tests/translate/test_reconcile.py
  - tests/bible/test_address_map.py
autonomous: true
requirements: [MOAT-CORE-SCY]

must_haves:
  truths:
    # Precedence ladder (linguist §3)
    - "Human lock always wins: a locked (anh/em) pair is not overwritten by no-survivors or carry logic (test_lock_beats_transition green)"
    - "Genuine evolution via relationship_event always wins: a this-episode relationship_event still authorizes term change through the transition branch (all 4 transition tests green)"
    - "Carried Bible pair wins over safe-default: established unlocked (anh/em) in existing_map + Ep N+1 no high-confidence witness → resolved_map carries (anh, em), NOT (toi, ban)"
    - "Carried Bible pair wins when below-threshold witness: unlocked prior (anh/em) + MEDIUM attribution (survivors empty) → resolved_map carries (anh, em)"
    - "Truly-new dyad still safe-defaults: address_map=[] + no witness → get_safe_default result (test_no_transition_no_survivors_safe_default green, UNCHANGED)"
    - "Reciprocal coherence: S->A carried (anh/em) results in A->S entry (em/anh) via the existing reciprocal pass; both rows carried from their own Bible entries, not re-inferred from each other"
    - "Directed asymmetry preserved: carry-forward operates on ordered (spk_id, addr_id) entry; no symmetrization introduced"
    # Pass-1 create-or-affirm
    - "Pass-1 Step 4 create-or-affirm: existing unlocked pair + Ep N+1 infers DIFFERENT terms, no relationship_event → existing pair's self_term/address_term unchanged in the DB (Vector 1 closed)"
    - "Pass-1 Step 4 create: brand-new pair (no prior DB row) → row IS created with inferred terms (regression test green)"
    # Vector 2b (engine.py hint path)
    - "Pass-3 hints fire for carried pairs: resolved_map already carries the pair; engine.py 1781-1789 keys on resolved_map.get((spk_id, addr_id)) which returns the carried pair for any line whose attribution resolves both IDs — no engine.py change required (confirm in task, document as verified)"
    # Re-pointed tests (deliberate contract change, not regression)
    - "test_reconcile_within_episode_dyad_lock_no_flip sub-case 2 asserts carried (anh, em) for unlocked prior + LOW witness (re-pointed from toi/ban to anh/em)"
    - "test_below_threshold_ignores_address_map asserts carried (anh, em) for unlocked prior + MEDIUM witness (re-pointed; test renamed to reflect new contract)"
  artifacts:
    - path: trezarr/translate/reconcile.py
      provides: "carry-forward logic in no-survivors else-branch"
      contains: "existing.self_term is not None"
    - path: trezarr/bible/analyze.py
      provides: "create-or-affirm mode in Step 4 for existing pairs"
      contains: "existing_pair_keys"
    - path: tests/translate/test_reconcile.py
      provides: "re-pointed contract tests + new regression tests"
      contains: "test_carry_forward_established_unlocked_pair"
    - path: tests/bible/test_address_map.py
      provides: "existing lock-precedence test stays green"
      contains: "test_locked_pair_not_overwritten"
  key_links:
    - from: "trezarr/translate/reconcile.py:else-branch (~441)"
      to: "existing_map dict (~339-341)"
      via: "existing = existing_map.get(pair)"
      pattern: "existing\\.self_term is not None"
    - from: "trezarr/bible/analyze.py:Step 4 (~712)"
      to: "existing_pair_keys set"
      via: "upsert_address_pair(self_term=None, address_term=None) when pair already exists"
      pattern: "existing_pair_keys"
---

<objective>
Close the two live cross-episode pronoun-drift vectors that break the relational moat.

Purpose: The core value is pronoun consistency episode-to-episode. Two default-on code paths
currently discard an established unlocked pair in favor of a fresh safe-default whenever
the current episode lacks a high-confidence witness — making an established (anh/em) pair
silently revert to (toi/ban) mid-series with no narrative cause. A 3-agent audit (bible-
consistency-auditor + vietnamese-linguist + finding-verifier) confirmed both vectors and
verified the fix design. This plan implements that exact design.

Output:
- reconcile.py: no-survivors else-branch carries prior unlocked pair forward instead of
  safe-defaulting when the pair has a non-None Bible entry and no relationship_event this episode
- analyze.py: Step 4 is create-or-affirm-only for existing pairs (pass self_term=None/
  address_term=None so store.py's None-skip logic leaves existing terms untouched)
- test_reconcile.py: 2 tests re-pointed to new carry-forward contract + 5 new regression tests
- No schema change, no Alembic migration, no store.py logic change
</objective>

<execution_context>
@/Users/dustin/.claude/get-shit-done/workflows/execute-plan.md
@/Users/dustin/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260608-scy-carry-forward-established-directed-prono/260608-scy-PLAN.md
@trezarr/translate/reconcile.py
@trezarr/bible/analyze.py
@trezarr/bible/store.py
@tests/translate/test_reconcile.py
@tests/bible/test_address_map.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: reconcile.py carry-forward in no-survivors else-branch + re-point + new tests</name>
  <files>trezarr/translate/reconcile.py, tests/translate/test_reconcile.py</files>
  <behavior>
    - Carry-forward new: established unlocked (anh/em) in existing_map + no survivors + no transition → resolved_map[(spk,addr)] == ("anh","em") NOT ("toi","ban")
    - Carry-forward new: below-threshold witness (survivors empty after MEDIUM vs HIGH threshold) + unlocked prior → resolved_map carries ("anh","em")
    - Truly-new-dyad unchanged: address_map=[] + no survivors → safe-default (existing test must stay green)
    - Lock still wins: locked pair + no survivors → locked terms (existing test must stay green)
    - Genuine evolution still wins: relationship_event this episode + no survivors → transition terms (existing tests must stay green)
    - Reciprocal coherence: S->A carried (anh/em) + A->S carried from own Bible row (em/anh); no divergence
    - Directed asymmetry: carry operates on the single ordered pair; no symmetrization
  </behavior>
  <action>
    IN reconcile.py, replace the body of the no-survivors else-branch (~441-458). The existing variable
    `existing` is already in scope (set by the lock check above, reconcile.py:368). Apply this logic
    in the else-branch, BEFORE the get_safe_default call:

    If `existing is not None` AND `existing.self_term is not None` AND `existing.address_term is not None`:
      carry forward: `resolved_map[pair] = (existing.self_term, existing.address_term)`
      log at DEBUG: "reconcile: carried prior pair for {spk_id}→{addr_id}: ({existing.self_term}/{existing.address_term}) at {episode_key}"
      do NOT call upsert_address_pair here (carry into resolved_map only — no extra DB write per
      verifier lower-risk note; valid_from_episode stays as-is in the DB; the existing survivors-branch
      upsert already handles updates when there IS a witness)
      continue to next pair (skip the get_safe_default block)

    Otherwise (truly-new dyad with no prior entry, or prior entry has None terms):
      leave the existing get_safe_default block UNCHANGED.

    The `existing` variable is already computed at line 368; do NOT re-fetch it. The lock check at
    366-376 already `continue`d for locked pairs, so any pair reaching the else-branch is either
    unlocked or has no entry at all. The transition branch (385-411) already `continue`d for
    relationship_event pairs. So the carry-forward is correctly scoped to the no-survivors,
    no-transition, no-lock case only.

    Do NOT touch: the survivors branch (413-439), the reciprocal pass (460-481), the lock check
    (366-376), the transition branch (385-411), get_safe_default, KINSHIP_RECIPROCAL, or
    any function outside reconcile_attributions. The reciprocal pass already handles a carried
    pair correctly — when resolved_map[(S,A)] = (anh,em), the reciprocal pass checks
    KINSHIP_RECIPROCAL.get(("anh","em")) and infers (A,S) = (em,anh) if not already in resolved_map.
    If (A,S) was ALSO carried from the Bible (because the reverse row existed), both directions are
    already in resolved_map before the reciprocal pass, so no incoherence can occur.

    IN tests/translate/test_reconcile.py:

    RE-POINT test_reconcile_within_episode_dyad_lock_no_flip (~1233):
      Change the assertion for the sub-case-2 half (unlocked prior (anh/em) + LOW witness, series_id2):
        FROM: `assert resolved2[(spk2, addr2)] == ("tôi", "bạn")`
        TO:   `assert resolved2[(spk2, addr2)] == ("anh", "em")`
      Update the comment from "must safe-default" to "must carry forward established pair".

    RE-POINT AND RENAME test_below_threshold_ignores_address_map (~402-475):
      Rename to `test_below_threshold_established_pair_carries_forward`.
      Change the assertion block (~464-475):
        FROM: `assert pair_result != ("anh", "em")` + `assert pair_result == get_safe_default(None, settings)` + self_t == SAFE_DEFAULT_SELF
        TO:   `assert pair_result == ("anh", "em")` with comment "below-threshold on established pair must carry forward"
      Update the docstring to describe the new contract.

    ADD five new regression tests (each as a standalone async def in tests/translate/test_reconcile.py):

    test_carry_forward_established_unlocked_pair:
      Setup: series + 2 chars + existing_map with unlocked (anh/em); attributions=[] (zero attributions).
      Assert: resolved_map[(spk,addr)] == ("anh","em"). Tests the pure zero-witness carry case.

    test_truly_new_dyad_no_prior_safe_defaults (add alongside, documents the guard):
      Setup: series + 2 chars; address_map=[] (no prior row); attributions=[LOW confidence].
      Assert: resolved_map[(spk,addr)] == get_safe_default(None, settings). Ensures the
      truly-new guard is correctly gated on existing being None.

    test_relationship_event_still_evolves_carried_pair:
      Setup: series + 2 chars + existing_map with unlocked (anh/em) + a relationship_event for this episode.
      Attributions: LOW confidence (below threshold → no survivors). But the relationship_event fires.
      Assert: resolved_map[(spk,addr)] != ("anh","em"); it is the transition-derived terms.
      (Confirms genuine evolution overrides carry-forward because the transition branch runs before and
      continues, so the else-branch is never reached for a pair with a current-episode event.)

    test_lock_still_wins_carry_forward:
      Setup: series + 2 chars + existing_map with LOCKED (chị/em) pair; attributions=[LOW].
      Assert: resolved_map[(spk,addr)] == ("chị","em"). (Lock branch continues before else-branch.)

    test_reciprocal_coherence_carry_forward:
      Setup: series + 3 chars; existing_map with S->A unlocked (anh/em) AND A->S unlocked (em/anh).
      Attributions = [] (zero witnesses for both directions).
      Assert: resolved_map[(S,A)] == ("anh","em") AND resolved_map[(A,S)] == ("em","anh").
      (Both rows carried from their own Bible entries; no divergence.)
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_reconcile.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>
    All reconcile tests pass including: renamed test_below_threshold_established_pair_carries_forward
    asserts (anh,em); test_reconcile_within_episode_dyad_lock_no_flip sub-case-2 asserts (anh,em);
    test_no_transition_no_survivors_safe_default still passes (address_map=[] path); lock and
    transition tests still pass; all 5 new regression tests pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: analyze.py Pass-1 Step 4 create-or-affirm + new test + Vector 2b confirmation</name>
  <files>trezarr/bible/analyze.py, tests/bible/test_address_map.py</files>
  <behavior>
    - Existing unlocked pair + Ep N+1 infers DIFFERENT terms, no relationship_event → DB pair terms UNCHANGED (not overwritten)
    - Brand-new pair (no prior DB row) → row IS created with the inferred terms (creation path unaffected)
    - test_locked_pair_not_overwritten stays green (lock precedence in store.py untouched)
    - Vector 2b: confirm in comment that once resolved_map carries the pair, engine.py 1781-1789 already fires hints for any attribution that resolves both spk_id and addr_id — no engine.py change needed
  </behavior>
  <action>
    IN analyze.py, in merge_bible_analysis Step 4 loop (~682-738):

    After building `name_to_id` from `existing_bible.characters` (line 565-567), also build an
    `existing_pair_keys` set from `existing_bible.address_map` INSIDE the same try block (right after
    the `for c in existing_bible.characters:` loop):

        existing_pair_keys: set[tuple[int, int]] = {
            (a.speaker_character_id, a.addressee_character_id)
            for a in existing_bible.address_map
        }

    If the `load_series_bible` call raises (the except block at ~569), initialize
    `existing_pair_keys = set()` in the except block alongside the existing warning log.

    In Step 4, inside the per-pair loop, after resolving `spk_id` and `addr_id`, determine whether
    this pair already exists:

        pair_already_exists = (spk_id, addr_id) in existing_pair_keys

    Then call `upsert_address_pair` with:
      - If `pair_already_exists` is True: pass `self_term=None, address_term=None`
        (store.py's `if new_val is None: continue` guard means neither term field is updated;
        only `valid_from_episode` is passed through so the row is refreshed/version-bumped if
        the episode key changed — but the existing terms are left intact).
      - If `pair_already_exists` is False (brand-new dyad): pass `self_term=pair.self_term,
        address_term=pair.address_term` as before.

    valid_from_episode and episode_key are passed in both branches unchanged from the current code.

    Log at DEBUG when skipping terms for an existing pair:
    "Pass 1: existing pair %r→%r — skipping term update (create-or-affirm mode); terms unchanged."

    Do NOT touch: store.py _upsert_address_pair_in_session, the lock branch in that helper,
    relationship_event recording (Step 5), Step 3.5 name-lock logic, or any other merge step.

    VECTOR 2b VERIFICATION (no code change required):
    Read engine.py lines 1781-1789. The hint loop keys on `resolved_map.get((spk_id, addr_id))`.
    After Task 1, `resolved_map` contains carried pairs — so any line whose Pass-2 attribution
    resolves BOTH spk_id and addr_id (via _resolve_char_id) will receive the carried pronoun hint
    in batch_hints. Lines where the dyad is not cleanly attributed (spk_id or addr_id is None)
    receive no hint and fall to the unhinted-line guardrail (out of scope per constraints). No
    engine.py change is needed. Add a one-line comment at engine.py:1785 documenting this:
    "# resolved_map includes carried Bible pairs (scy); hint fires for any fully-attributed line."

    IN tests/bible/test_address_map.py:

    ADD test_pass1_create_or_affirm_existing_pair:
      Test that calling upsert_address_pair with a DIFFERENT non-None self_term/address_term on an
      EXISTING UNLOCKED pair leaves the existing terms UNCHANGED (simulates the post-fix analyze.py
      create-or-affirm call with self_term=None/address_term=None).
      Setup: upsert_address_pair with ("anh","em") to create initial row.
      Act: upsert_address_pair again with self_term=None, address_term=None, valid_from_episode updated.
      Assert: DTO returned has self_term="anh", address_term="em" (terms unchanged; no BibleEvent for
      term fields emitted because new_val is None so the loop skips them).

    ADD test_pass1_creates_brand_new_pair:
      Test that calling upsert_address_pair for a pair that does NOT yet exist creates the row with the
      supplied terms (the non-existing-pair branch of the fix).
      Setup: fresh series + chars + no prior address_map row.
      Act: upsert_address_pair with self_term="tôi", address_term="bạn".
      Assert: DTO has self_term="tôi", address_term="bạn".

    test_locked_pair_not_overwritten must stay green (no changes to that test; store.py lock logic untouched).
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/bible/test_address_map.py tests/translate/test_reconcile.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>
    test_pass1_create_or_affirm_existing_pair passes (self_term=None call leaves terms unchanged);
    test_pass1_creates_brand_new_pair passes; test_locked_pair_not_overwritten still passes;
    all reconcile tests from Task 1 still pass. Full suite regression check:
    `python -m pytest tests/ -x -q` exits 0.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| existing_map → resolved_map | Carried pair comes from the persisted DB via load_series_bible; untrusted only if the DB is corrupt |
| Pass-1 inference → upsert_address_pair | LLM-inferred terms passed to DB; now gated by create-or-affirm to prevent unauthorized overwrites |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-scy-01 | Tampering | reconcile.py carry-forward | mitigate | carry-forward is gated on existing.self_term is not None; a DB row with null terms does not carry forward — safe-default still fires |
| T-scy-02 | Tampering | analyze.py create-or-affirm | mitigate | existing_pair_keys is built from the same load_series_bible call that pre-seeds name_to_id; if load fails, set() default means create-with-terms path applies (safe degradation) |
| T-scy-03 | Elevation of Privilege | lock precedence | accept | lock check still runs first at reconcile.py:366-376 and continues before the else-branch; carry-forward cannot override a lock |
</threat_model>

<verification>
Full suite after both tasks:

```bash
cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr
python -m pytest tests/ -x -q 2>&1 | tail -30
```

Must pass all existing tests (currently 505). The two re-pointed tests must now assert the
carried pair; the 7 new regression tests must all pass.

Spot-check moat-core contracts:
- test_lock_beats_transition: green (lock wins)
- test_no_transition_no_survivors_safe_default: green (truly-new dyad safe-defaults; address_map=[])
- test_locked_pair_not_overwritten: green (store.py lock logic untouched)
- test_carry_forward_established_unlocked_pair: green (zero-witness carry)
- test_reciprocal_coherence_carry_forward: green (both directions carried from own rows)
</verification>

<success_criteria>
- reconcile.py else-branch: `existing.self_term is not None` guard carries prior pair into resolved_map
- analyze.py Step 4: `existing_pair_keys` set built from existing_bible.address_map; upsert called with self_term=None/address_term=None for existing pairs
- engine.py: one-line comment at 1785 confirming Vector 2b is already handled; no other engine change
- test_below_threshold_established_pair_carries_forward: asserts ("anh","em") for below-threshold + established pair
- test_reconcile_within_episode_dyad_lock_no_flip sub-case 2: asserts ("anh","em") for unlocked prior + LOW witness
- All 5 new reconcile regression tests pass
- All 2 new address_map tests pass
- Full suite exits 0 (no regressions)
- ruff check passes: `ruff check trezarr/translate/reconcile.py trezarr/bible/analyze.py`
</success_criteria>

<output>
Create `.planning/quick/260608-scy-carry-forward-established-directed-prono/260608-scy-SUMMARY.md` when done.
</output>
