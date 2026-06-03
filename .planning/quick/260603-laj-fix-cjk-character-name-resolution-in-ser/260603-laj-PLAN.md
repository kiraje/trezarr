---
phase: quick
plan: 260603-laj
type: execute
wave: 1
depends_on: []
files_modified:
  - trezarr/bible/analyze.py
  - tests/translate/test_analyze.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "CJK-named characters (e.g. '樱') inferred in Pass-1 resolve to their character IDs when address_map/relationship_event entries reference them by original-script name"
    - "Latin-named character resolution is not regressed — existing test_pass1_runs_before_pass3 still passes"
    - "CR-01 case-insensitive name-matching contract (.strip().lower()) is preserved for both Latin and CJK keys"
    - "Prompt instructs the LLM to use character names in address_map/relationship_events that match the characters list"
  artifacts:
    - path: "trezarr/bible/analyze.py"
      provides: "CharacterInference.original_script_name field + dual-key name_to_id indexing + prompt tightening"
    - path: "tests/translate/test_analyze.py"
      provides: "Regression test: CJK characters with script-name address pair and relationship_event persisted (not skipped)"
  key_links:
    - from: "CharacterInference.original_script_name"
      to: "name_to_id dict in merge_bible_analysis"
      via: "char.original_script_name.strip().lower() added as second key alongside original_latin_name key"
      pattern: "original_script_name.*strip.*lower"
---

<objective>
Fix the CJK character-name resolution bug in Pass-1 `merge_bible_analysis`.

The LLM infers CJK characters with a romanized `original_latin_name` (e.g. "Sakura") but
writes `address_map` and `relationship_events` using the on-screen script name (e.g. "樱").
The `name_to_id` dict is keyed only on the Latin name, so script-name references resolve
to `None` → pairs/events are silently skipped, destroying the Address Map / pronoun engine
for the product's primary CJK audience.

Purpose: Ensure address pairs and relationship events for CJK-named characters resolve to
character IDs and are persisted — no skips.

Output: Two file edits + a regression test. No DB schema change.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@trezarr/bible/analyze.py
@tests/translate/test_analyze.py
@tests/translate/conftest.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add original_script_name to CharacterInference and dual-key name_to_id + tighten prompt</name>
  <files>trezarr/bible/analyze.py</files>
  <behavior>
    - CharacterInference gains an optional field: original_script_name: str | None = None
    - In merge_bible_analysis Step 2 (pre-seed loop over existing_bible.characters), also
      index: if c has an original_script_name attribute and it is non-empty, add
      name_to_id[c.original_script_name.strip().lower()] = c.id (CharacterDTO does not carry
      this field so this path is a no-op for existing characters — acceptable; the write-path
      below handles it)
    - In merge_bible_analysis Step 2 (upsert loop over analysis.characters), after writing
      name_to_id[char.original_latin_name.strip().lower()] = char_dto.id, ALSO write
      name_to_id[char.original_script_name.strip().lower()] = char_dto.id when
      char.original_script_name is not None and not empty-after-strip — this is the key fix
    - The existing Step 4 and Step 5 resolution code (.strip().lower() lookups) does NOT
      change — it already calls .strip().lower(), so CJK script names now hit the map
    - Tighten the [INSTRUCTIONS] section of _build_analysis_prompt: add a note after the
      address_map bullet:
        "IMPORTANT: use the EXACT same name string in speaker_name/addressee_name as used in
        the characters list (either original_latin_name or original_script_name). Do NOT
        reference a character with a name form that was not listed in the characters list."
      Add the same note after the relationship_events character_a_name/character_b_name
      description.
    - Also add an optional original_script_name field to CharacterInference that the LLM
      populates: add it to the characters instructions bullet:
        "original_script_name (if the character's on-screen name is non-Latin, include the
        original-script form here, e.g. '樱' for a Chinese character named Sakura)"
    - Preserve CR-01: all dict keys are .strip().lower() — CJK .lower() is a no-op (correct)
    - Preserve existing Step 2 pre-seed loop for already-persisted Latin-name characters
  </behavior>
  <action>
    In trezarr/bible/analyze.py, make THREE targeted edits:

    EDIT 1 — CharacterInference model (around line 74):
    Add `original_script_name: str | None = None` as the last optional field, after `role`.
    No other fields change.

    EDIT 2 — merge_bible_analysis Step 2 upsert loop (around lines 408-434):
    After the existing line:
        name_to_id[char.original_latin_name.strip().lower()] = char_dto.id
    add the guard block:
        if char.original_script_name and char.original_script_name.strip():
            name_to_id[char.original_script_name.strip().lower()] = char_dto.id
    This is the only code change needed to fix the resolution bug. Steps 4 and 5 already
    do .strip().lower() lookups, so they will now find CJK keys.

    EDIT 3 — _build_analysis_prompt instructions (around lines 204-224):
    a) In the characters bullet, after "rough_age (if determinable), role (if determinable)"
       add: ", original_script_name (the original-script form of the name if non-Latin,
       e.g. '樱'; omit for Latin-named characters)"
    b) After the address_map bullet's description of speaker_name/addressee_name, add:
       " — use the EXACT name string from the characters list (latin or original_script_name)"
    c) After the relationship_events character_a_name/character_b_name bullet, add the same
       note: " — use the EXACT name string from the characters list"

    Do NOT add asyncio.Semaphore. Do NOT import SQLAlchemy. Do NOT touch store.py or models.py.
    Do NOT change any resolution logic in Steps 4 or 5 — only the dict population in Step 2.
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -c "from trezarr.bible.analyze import CharacterInference; c = CharacterInference(original_latin_name='Sakura', original_script_name='樱'); assert c.original_script_name == '樱'"</automated>
  </verify>
  <done>
    CharacterInference accepts original_script_name. name_to_id in merge_bible_analysis
    indexes both the Latin key and the script key. Prompt includes original_script_name
    guidance. Existing tests are not broken (no removed fields, no interface changes).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Regression test — CJK address pair and relationship_event must be persisted, not skipped</name>
  <files>tests/translate/test_analyze.py</files>
  <behavior>
    - Test: CJK character set with original_script_name, address pair referencing script name, relationship_event referencing script names → after merge_bible_analysis both are persisted
    - Specifically: create two characters with Latin names + original_script_name aliases
      (e.g. CharacterInference(original_latin_name="Sakura", original_script_name="樱") and
       CharacterInference(original_latin_name="Daisy", original_script_name="雏菊"))
    - Address pair speaker_name="樱", addressee_name="雏菊" (script names — the failing case)
    - RelationshipEventInference character_a_name="樱", character_b_name="雏菊"
    - After merge_bible_analysis: assert len(updated_bible.address_map) == 1
    - Assert the address pair has the correct self_term and address_term
    - Assert len(updated_bible.relationship_events or []) == 1 (after enabling
      enable_relationship_events=True in the settings stub — pass settings=_make_settings()
      to merge_bible_analysis)
    - Name the test: test_cjk_script_name_address_pair_resolves
    - Follow the existing test style: async def, use session_factory fixture, use
      get_or_create_series + merge_bible_analysis + load_series_bible, use _make_subdoc
      and _make_settings helpers already in the file, mock llm_client not needed (call
      merge_bible_analysis directly with the pre-built BibleAnalysis — same pattern as
      test_pass1_runs_before_pass3)
    - No xfail marker — this is a GREEN test once Task 1 ships
  </behavior>
  <action>
    Append a new test function test_cjk_script_name_address_pair_resolves to
    tests/translate/test_analyze.py. Add RelationshipEventInference to the import list at
    the top (already imports CharacterInference and AddressMapInference; add
    RelationshipEventInference alongside them).

    The test must:
    1. Create a series with arr_series_id=3003 (distinct from existing tests).
    2. Build a BibleAnalysis with two CJK characters (Latin + script names) and:
       - One AddressMapInference with speaker_name="樱", addressee_name="雏菊"
       - One RelationshipEventInference with character_a_name="樱", character_b_name="雏菊"
    3. Call merge_bible_analysis with series_dto, analysis, episode_key="S01E01",
       settings=_make_settings(enable_relationship_events=True).
    4. Load the updated bible.
    5. Assert len(updated_bible.address_map) == 1 with a descriptive failure message
       (e.g. "CJK script-name address pair must be persisted, not skipped").
    6. Assert the single address pair has self_term == the value from AddressMapInference.
    7. Assert len(updated_bible.relationship_events or []) == 1 with a descriptive message.

    Check that TrezarrSettings accepts enable_relationship_events before using it in
    _make_settings — if not a known field, pass it directly to merge_bible_analysis's
    settings arg via a simple mock object (use a SimpleNamespace or a minimal dataclass
    with enable_relationship_events=True and any other attrs merge_bible_analysis reads via
    getattr with defaults).
  </action>
  <verify>
    <automated>cd /Users/dustin/Library/CloudStorage/SynologyDrive-Dustin-Nas/WorkspaceX/projects/Trezarr && python -m pytest tests/translate/test_analyze.py::test_cjk_script_name_address_pair_resolves -x -v 2>&1 | tail -20</automated>
  </verify>
  <done>
    test_cjk_script_name_address_pair_resolves PASSES. address_map and relationship_events
    for CJK-script-named characters are persisted. No existing tests regressed.
    Full suite: python -m pytest tests/translate/test_analyze.py -v passes.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| LLM response → BibleAnalysis | Untrusted: LLM may inject arbitrary strings in original_script_name |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-laj-01 | Tampering | CharacterInference.original_script_name | accept | Field is optional; stored only in-memory name_to_id (not persisted to DB). Empty-after-strip guard prevents empty-string key collisions. Character row identity remains original_latin_name — unchanged. |
| T-laj-02 | Spoofing | name_to_id key collision | accept | If LLM gives two characters the same original_script_name, the later one wins the id mapping — same behavior as duplicate Latin names. Both are user-provided LLM output, low risk. |
</threat_model>

<verification>
Full analyze test suite must pass:
  python -m pytest tests/translate/test_analyze.py -v

Targeted regression test must pass:
  python -m pytest tests/translate/test_analyze.py::test_cjk_script_name_address_pair_resolves -x -v

Existing Latin-name test must not regress:
  python -m pytest tests/translate/test_analyze.py::test_pass1_runs_before_pass3 -x -v

CR-01 contract (case-insensitive .strip().lower()) is preserved for both keys.
No new DB migration generated — the change is in-memory Pydantic + dict only.
</verification>

<success_criteria>
- CharacterInference.original_script_name: str | None = None exists in analyze.py
- merge_bible_analysis Step 2 upsert loop indexes both Latin and script keys in name_to_id
- _build_analysis_prompt instructs LLM to use consistent name forms and supply original_script_name
- test_cjk_script_name_address_pair_resolves passes: script-name address pair + relationship_event are persisted, not skipped
- tests/translate/test_analyze.py full suite green
- No Alembic migration created (no DB schema change)
</success_criteria>

<output>
Create .planning/quick/260603-laj-fix-cjk-character-name-resolution-in-ser/260603-laj-SUMMARY.md when done.
</output>
