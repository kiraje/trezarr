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
