"""R3: canonical name-term rendering — one locked rendering per character entity (260611-ru6).

Tests cover:
  R3 Test L — plan_character_name_terms: when existing_terms contains a LOCKED row for
              a character's Latin name, the CJK script-form is NOT planned (no competing lock).
  R3 Test M — plan_character_name_terms: when a spec IS emitted for the CJK form, it adopts
              the canonical (existing locked) rendering, not the inferred Hán-Việt rendering.
  R3 Test N — dedup_canonical_name_terms: async DB repair function collapses existing dual
              locked rows to the canonical rendering with BibleEvent audit trail; idempotent.

asyncio_mode="auto" is configured project-wide in pyproject.toml — no @pytest.mark.asyncio.
DB fixtures provided via tests/bible/conftest.py (re-exports from tests/db/conftest.py).
"""
from __future__ import annotations

from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Helpers — shared across tests
# ---------------------------------------------------------------------------


def _make_term_dto(source_term: str, vietnamese_rendering: str, locked: bool = False):
    """Make a duck-typed term object matching TermDTO interface."""
    return SimpleNamespace(
        source_term=source_term,
        vietnamese_rendering=vietnamese_rendering,
        locked_fields=["vietnamese_rendering"] if locked else [],
    )


def _make_char_inference(
    original_latin_name: str,
    original_script_name: str | None = None,
    vietnamese_rendering: str | None = None,
):
    """Make a duck-typed CharacterInference object."""
    return SimpleNamespace(
        original_latin_name=original_latin_name,
        original_script_name=original_script_name,
        vietnamese_rendering=vietnamese_rendering,
    )


async def _create_series(session_factory, arr_series_id: int = 901) -> int:
    """Create a minimal Series row and return its id."""
    from trezarr.bible.store import get_or_create_series

    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=arr_series_id,
        arr_metadata_snapshot={"title": "Moon Knight Test"},
    )
    return dto.id


# ── R3: canonical name rendering (260611-ru6) ────────────────────────────────


def test_r3_canonical_l_skips_cjk_when_latin_already_locked():
    """R3 Test L: plan_character_name_terms must NOT plan a CJK locked row when the
    character's Latin name already has a locked vietnamese_rendering row.

    Scenario: Steven Grant Latin → 'Steven Grant' (locked in existing terms).
    Inference arrives with original_script_name='史蒂文·格兰特', vietnamese_rendering='Sử Địch Văn'.
    Expected: empty spec list — no competing row planned for the CJK form.

    Failure mode before fix: returns NameTermSpec(source_term='史蒂文·格兰特',
    vietnamese_rendering='Sử Địch Văn'), creating a second locked row that conflicts
    with the established 'Steven Grant' rendering. (260611-l74 audit R3 verified finding.)
    """
    from trezarr.bible.analyze import plan_character_name_terms

    existing_terms = [
        _make_term_dto("Steven Grant", "Steven Grant", locked=True),
    ]
    characters = [
        _make_char_inference(
            original_latin_name="Steven Grant",
            original_script_name="史蒂文·格兰特",
            vietnamese_rendering="Sử Địch Văn",
        )
    ]

    specs = plan_character_name_terms(characters, existing_terms)

    # After fix: no new spec — character already has a locked row.
    assert specs == [], (
        f"Expected no spec when Latin name already has a locked row, got: {specs!r}\n"
        "R3 regression: plan_character_name_terms must skip CJK form when Latin form "
        "is already locked (260611-l74 audit finding)."
    )


def test_r3_canonical_m_adopts_canonical_rendering_for_cjk_spec():
    """R3 Test M: when the Latin form is NOT yet locked but an existing unlocked term
    row for the Latin name exists, and the inference provides both a CJK script form
    AND a Hán-Việt rendering, the spec for the CJK source adopts the existing Latin
    rendering (not the inferred Hán-Việt rendering).

    Scenario:
      - existing: 'Steven Grant' → 'Steven Grant' (NOT locked — the Latin row predates locking)
      - inference: latin='Steven Grant', script='史蒂文·格兰特', hv='Sử Địch Văn'
    Before fix: spec emitted with vietnamese_rendering='Sử Địch Văn' (Hán-Việt override).
    After fix: if a spec IS emitted for the CJK form, it must carry the existing latin
    rendering 'Steven Grant' (rendering_by_latin lookup wins over ch_rendering per H2 fix).
    This test verifies the H2 fix is respected in the CJK-path scenario.
    """
    from trezarr.bible.analyze import plan_character_name_terms

    # Unlocked existing row — canonical rendering already established but not locked yet.
    existing_terms = [
        _make_term_dto("Steven Grant", "Steven Grant", locked=False),
    ]
    characters = [
        _make_char_inference(
            original_latin_name="Steven Grant",
            original_script_name="史蒂文·格兰特",
            vietnamese_rendering="Sử Địch Văn",  # Hán-Việt inferred — must NOT win
        )
    ]

    specs = plan_character_name_terms(characters, existing_terms)

    # The CJK source_term is NOT yet in existing_sources, so a spec MAY be planned.
    # But the rendering must be 'Steven Grant' (from rendering_by_latin), not 'Sử Địch Văn'.
    if specs:
        cjk_specs = [s for s in specs if s.source_term == "史蒂文·格兰特"]
        assert cjk_specs, f"Expected a CJK spec (source_term='史蒂文·格兰特'), got: {specs!r}"
        assert cjk_specs[0].vietnamese_rendering == "Steven Grant", (
            f"Expected CJK spec to adopt existing Latin rendering 'Steven Grant', "
            f"got: {cjk_specs[0].vietnamese_rendering!r}\n"
            "H2 fix: rendering_by_latin lookup must win over ch_rendering (hán-việt)."
        )


async def test_r3_canonical_n_dedup_collapses_dual_locked_rows(session_factory):
    """R3 Test N: dedup_canonical_name_terms collapses dual locked rows to canonical.

    Seed the DB with two locked TermDictionary rows for the same character entity:
      Row 1: source_term='Steven Grant', vietnamese_rendering='Steven Grant' (Latin, locked)
      Row 2: source_term='史蒂文·格兰特', vietnamese_rendering='Sử Địch Văn · Cách Lan Đặc' (CJK, locked)

    After dedup_canonical_name_terms(session_factory, series_id=X):
      - Row 2's vietnamese_rendering is rewritten to 'Steven Grant' (canonical)
      - At least one BibleEvent audit record exists for the change
      - A second call (idempotent) returns an empty list of events

    This is the repair path for the live Moon Knight Bible (260611-l74 audit R3 evidence).
    """
    from trezarr.bible.store import apply_human_edit_term, load_series_bible

    # Import the new function — will fail (ImportError) until implemented (RED).
    from trezarr.bible.store import dedup_canonical_name_terms  # noqa: PLC0415

    series_id = await _create_series(session_factory, arr_series_id=902)

    # Seed Row 1: Latin canonical (locked)
    await apply_human_edit_term(
        session_factory,
        series_id=series_id,
        source_term="Steven Grant",
        field="vietnamese_rendering",
        new_value="Steven Grant",
        lock=True,
    )

    # Seed Row 2: CJK competing locked row with different rendering
    await apply_human_edit_term(
        session_factory,
        series_id=series_id,
        source_term="史蒂文·格兰特",
        field="vietnamese_rendering",
        new_value="Sử Địch Văn · Cách Lan Đặc",
        lock=True,
    )

    # Run dedup — should rewrite Row 2 to 'Steven Grant'
    events = await dedup_canonical_name_terms(session_factory, series_id=series_id)

    assert len(events) >= 1, (
        f"Expected at least 1 BibleEvent for the dedup repair, got {len(events)}.\n"
        "R3 regression: dedup_canonical_name_terms must emit an audit event for each "
        "row it rewrites to the canonical rendering."
    )

    # Verify the CJK row was rewritten
    bible = await load_series_bible(session_factory, series_id=series_id)
    cjk_terms = [t for t in bible.terms if t.source_term == "史蒂文·格兰特"]
    assert len(cjk_terms) == 1, f"Expected 1 CJK term row, got: {cjk_terms!r}"
    assert cjk_terms[0].vietnamese_rendering == "Steven Grant", (
        f"Expected CJK row rewritten to canonical 'Steven Grant', "
        f"got: {cjk_terms[0].vietnamese_rendering!r}"
    )

    # Idempotency: second call returns empty events list
    events2 = await dedup_canonical_name_terms(session_factory, series_id=series_id)
    assert events2 == [], (
        f"Expected dedup_canonical_name_terms to be idempotent (empty events on re-run), "
        f"got: {events2!r}"
    )


# ── FIX 2 RED: xianxia multi-character dedup + CJK-first guard ─────────────────
# Defect (a): dedup false-merges DIFFERENT characters — when there is exactly one
#   Latin-locked row for a different character (Mei/Mai), ALL CJK-locked rows
#   (Han Li/韩立 + Nam Cung Uyen/南宫婉) get rewritten to 'Mai'. This is catastrophic.
# Defect (b): canonical-by-script is wrong-register — a later Latin/pinyin row beats
#   the first-locked CJK Hán-Việt row, rewriting correct 'Hàn Lập' to bare 'Han Li'.
# Defect (c): guard ordering hole — plan_character_name_terms tracks locked_sources by
#   source_term only; a CJK-first locked row (source_term='韩立') does not block the
#   later 'Han Li' Latin form because 'han li' ∉ {'韩立'}.
#
# Fix decision (linguist option 1 + auditor linkage requirement combined):
#   - Canonical = first-locked row (lowest id), NOT the Latin row.
#   - Rewrite only when rows are provably the same character (Character FK linkage OR
#     exact same-series resolution). Without FK linkage, SKIP (log, no rewrite).
#   - Guard: locked_sources must track BOTH the CJK source_term AND the Latin name so a
#     CJK-first lock blocks the later pinyin competitor.


async def test_r3_fix2_i_xianxia_multi_char_no_false_merge(session_factory):
    """FIX2-I RED: dedup must perform ZERO rewrites when CJK rows are different characters.

    Scenario (xianxia — A Record of a Mortal's Journey to Immortality):
      - Row 1: '韩立' → 'Hàn Lập'  (CJK, locked) — character Han Li
      - Row 2: '南宫婉' → 'Nam Cung Uyển'  (CJK, locked) — character Nan Gong Wan
      - Row 3: 'Mei' → 'Mai'  (Latin, locked) — character Mei (unrelated)

    The current code: canonical_rows = [Row 3] (len==1, Latin).
    It rewrites BOTH Row 1 and Row 2 to 'Mai' — destroying both Hán-Việt renderings.

    After fix: dedup cannot establish character linkage for Rows 1/2 vs Row 3 (no FK,
    no Character table entry wired). SKIP all rewrites → events == [].
    """
    from trezarr.bible.store import apply_human_edit_term, dedup_canonical_name_terms

    series_id = await _create_series(session_factory, arr_series_id=910)

    # Seed three locked rows: two distinct CJK characters + one Latin character
    await apply_human_edit_term(
        session_factory, series_id=series_id,
        source_term="韩立", field="vietnamese_rendering",
        new_value="Hàn Lập", lock=True,
    )
    await apply_human_edit_term(
        session_factory, series_id=series_id,
        source_term="南宫婉", field="vietnamese_rendering",
        new_value="Nam Cung Uyển", lock=True,
    )
    await apply_human_edit_term(
        session_factory, series_id=series_id,
        source_term="Mei", field="vietnamese_rendering",
        new_value="Mai", lock=True,
    )

    events = await dedup_canonical_name_terms(session_factory, series_id=series_id)

    assert events == [], (
        f"FIX2-I: dedup must perform ZERO rewrites when CJK rows belong to different "
        f"characters than the single Latin row. Got {len(events)} rewrite event(s): "
        f"{[e.new_value for e in events]!r}\n"
        "Current bug: rewrites both 'Hàn Lập' and 'Nam Cung Uyển' to 'Mai' (false-merge)."
    )

    # Verify that the original renderings are untouched
    from trezarr.bible.store import load_series_bible
    bible = await load_series_bible(session_factory, series_id=series_id)
    renderings = {t.source_term: t.vietnamese_rendering for t in bible.terms}
    assert renderings.get("韩立") == "Hàn Lập", (
        f"FIX2-I: '韩立' rendering must remain 'Hàn Lập', got {renderings.get('韩立')!r}"
    )
    assert renderings.get("南宫婉") == "Nam Cung Uyển", (
        f"FIX2-I: '南宫婉' rendering must remain 'Nam Cung Uyển', got {renderings.get('南宫婉')!r}"
    )


async def test_r3_fix2_ii_cjk_first_locked_is_canonical(session_factory):
    """FIX2-II RED: when CJK row is locked FIRST, it should be canonical (first-locked-wins).

    Scenario: same character Han Li — CJK form locked first, then a Latin/pinyin row added.
      - Row 1: '韩立' → 'Hàn Lập'  (locked FIRST — row id is lower)
      - Row 2: 'Han Li' → 'Han Li'  (locked LATER — row id is higher)

    After fix with Character FK linkage: rows are provably the same character →
    canonical = first-locked (Row 1, lowest id) = 'Hàn Lập'.
    Row 2 should be rewritten to 'Hàn Lập'.

    Without FK linkage (current TermDictionary schema): the test documents the expected
    SKIP behaviour — no linkage, no rewrite. The FIX2-I behaviour (skip when unresolvable)
    also applies here. At minimum, we assert the CJK row's rendering is NOT overwritten
    by the Latin/pinyin row.

    NOTE: If FK linkage is added in a future migration, this test should be updated to
    assert the canonical == 'Hàn Lập' and Row 2 → 'Hàn Lập'. For now: no rewrite since
    no FK → events == [] and 'Hàn Lập' is preserved.
    """
    from trezarr.bible.store import apply_human_edit_term, dedup_canonical_name_terms, load_series_bible

    series_id = await _create_series(session_factory, arr_series_id=911)

    # Seed: CJK form locked FIRST (lower id), Latin/pinyin locked SECOND
    await apply_human_edit_term(
        session_factory, series_id=series_id,
        source_term="韩立", field="vietnamese_rendering",
        new_value="Hàn Lập", lock=True,
    )
    await apply_human_edit_term(
        session_factory, series_id=series_id,
        source_term="Han Li", field="vietnamese_rendering",
        new_value="Han Li", lock=True,
    )

    events = await dedup_canonical_name_terms(session_factory, series_id=series_id)

    # With the fix (no FK linkage → skip unresolvable): events == [], and 'Hàn Lập' preserved.
    assert events == [], (
        f"FIX2-II: without FK linkage, dedup must skip the rewrite and return no events. "
        f"Got {len(events)} event(s): {[(e.old_value, e.new_value) for e in events]!r}\n"
        "Current bug: Latin row is canonical so CJK 'Hàn Lập' gets overwritten to 'Han Li'."
    )

    bible = await load_series_bible(session_factory, series_id=series_id)
    renderings = {t.source_term: t.vietnamese_rendering for t in bible.terms}
    assert renderings.get("韩立") == "Hàn Lập", (
        f"FIX2-II: '韩立' rendering must remain 'Hàn Lập' (CJK-first locked wins); "
        f"got {renderings.get('韩立')!r}"
    )


def test_r3_fix2_iii_cjk_first_lock_blocks_latin_competitor():
    """FIX2-III RED: plan_character_name_terms must block a Latin/pinyin spec when the
    same character's CJK form is already locked in existing_terms, even when the
    CHARACTER INFERENCE provides no original_script_name (e.g., second cold-run with
    English-only source that drops the CJK form).

    Scenario:
      - existing_terms: source_term='韩立', rendering='Hàn Lập', locked=True
        (CJK form locked on first run when script name was available)
      - characters: latin='Han Li', script=None (English source; no CJK form this pass)

    Current bug path:
      existing_sources = {'韩立'}
      locked_sources   = {'韩立'}   ← from CJK locked row
      source = script or latin = 'Han Li'
      key    = 'han li'
      'han li' ∉ existing_sources  → not skipped by key-in-existing
      latin.lower() = 'han li' ∉ locked_sources = {'韩立'}  → guard does NOT fire
      → spec NameTermSpec(source_term='Han Li', ...) is emitted → competing Latin lock

    After fix: the guard must also check whether any existing LOCKED row's source_term
    matches this character's original_script_name (when script is non-empty) OR resolve
    the CJK source_term back to the character Latin name. One concrete approach: when
    building locked_sources, if the locked row's source_term is CJK AND a character in
    the batch has original_script_name == that source_term, add that character's
    original_latin_name to locked_sources too.
    """
    from trezarr.bible.analyze import plan_character_name_terms

    existing_terms = [
        # CJK row locked FIRST (source_term is script form from a prior run)
        _make_term_dto("韩立", "Hàn Lập", locked=True),
    ]
    characters = [
        # Second pass: English source — script name NOT available; only Latin name
        _make_char_inference(
            original_latin_name="Han Li",
            original_script_name=None,  # ← key: no script form available this run
            vietnamese_rendering="Hàn Lập",
        )
    ]

    specs = plan_character_name_terms(characters, existing_terms)

    # After fix: the guard must recognise that '韩立' (CJK locked) corresponds to
    # character 'Han Li' via the character list and suppress the competing Latin spec.
    # Without the fix: 'Han Li' spec IS emitted (Latin is not in locked_sources).
    assert specs == [], (
        f"FIX2-III: plan_character_name_terms must NOT emit a spec for 'Han Li' when "
        f"the character is already locked under CJK source_term '韩立'. Got: {specs!r}\n"
        "Current bug: locked_sources = {{'韩立'}}; 'han li' not in it → "
        "competing Latin spec emitted → later dedup false-merges or creates split lock."
    )
