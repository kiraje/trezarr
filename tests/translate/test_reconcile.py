"""Tests for PRON-03 deterministic reconciliation and D-44/D-45 confidence gate.

Tests cover:
  PRON-03 — Low-confidence attribution → safe default, not intimate pronoun
  PRON-03 — confidence=HIGH above threshold → Address Map pair used
  Success #3 — Reciprocal directions coherent (A→B "anh/em" ⇒ B→A "em/anh")
  Success #4 — Below threshold → safe pair regardless of Address Map content

asyncio_mode="auto" is configured project-wide in pyproject.toml, so
async def test functions run without @pytest.mark.asyncio.

DB fixtures (session_factory) are provided via tests/translate/conftest.py which
re-exports them from tests/db/conftest.py.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers — mirror test_address_map.py helper pattern
# ---------------------------------------------------------------------------


async def _create_series(session_factory, arr_series_id: int = 100) -> int:
    """Create a minimal Series row and return its id."""
    from trezarr.bible.store import get_or_create_series

    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=arr_series_id,
        arr_metadata_snapshot={"title": "Reconcile Test Series"},
    )
    return dto.id


async def _create_characters(
    session_factory,
    series_id: int,
    spk_name: str = "Minh",
    spk_gender: str = "male",
    addr_name: str = "Lan",
    addr_gender: str = "female",
) -> tuple[int, int]:
    """Create two Character rows and return (speaker_id, addressee_id)."""
    from trezarr.bible.store import upsert_character

    spk, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name=spk_name,
        gender=spk_gender,
        source="inference",
    )
    addr, _ = await upsert_character(
        session_factory,
        series_id=series_id,
        original_latin_name=addr_name,
        gender=addr_gender,
        source="inference",
    )
    return spk.id, addr.id


def _make_attribution(speaker: str, addressee: str, confidence_value: str, line_index: int = 1):
    """Construct a LineAttribution-like object for tests.

    attribute.py (Plan 05-04) defines LineAttribution as a Pydantic BaseModel.
    Since attribute.py does not yet exist, we build a simple namespace object
    that satisfies reconcile.py's duck-typed access pattern (attr.speaker,
    attr.addressee, attr.confidence).  We use a dataclass-like approach
    compatible with the Pydantic str Enum AttributionConfidence.
    """
    from types import SimpleNamespace

    class _FakeConfidence:
        """Duck-typed AttributionConfidence with .value and str()."""

        def __init__(self, val: str):
            self.value = val

        def __str__(self) -> str:
            return f"AttributionConfidence.{self.value}"

    return SimpleNamespace(
        line_index=line_index,
        speaker=speaker,
        addressee=addressee,
        confidence=_FakeConfidence(confidence_value),
    )


def _make_bible(
    series_id: int, characters: list, address_map: list, relationship_events: list | None = None
):
    """Construct a minimal SeriesBibleDTO-like object for tests."""
    from types import SimpleNamespace

    return SimpleNamespace(
        id=series_id,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=100,
        characters=characters,
        terms=[],
        address_map=address_map,
        locked_fields=[],
        relationship_events=relationship_events or [],  # [Phase 6 ADDITIVE — safe default []]
    )


def _make_character(id: int, name: str, gender: str | None = None):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=id,
        series_id=1,
        original_latin_name=name,
        gender=gender,
        rough_age=None,
        role=None,
        locked_fields=[],
    )


def _make_address_map_entry(
    id: int,
    series_id: int,
    spk_id: int,
    addr_id: int,
    self_term: str | None,
    address_term: str | None,
    locked_fields: list[str] | None = None,
):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=id,
        series_id=series_id,
        speaker_character_id=spk_id,
        addressee_character_id=addr_id,
        self_term=self_term,
        address_term=address_term,
        valid_from_episode=None,
        locked_fields=locked_fields or [],
    )


def _make_settings(threshold: str = "medium", safe_default=None, enable_relationship_events: bool = True):
    """Build a minimal TrezarrSettings-like object."""
    from types import SimpleNamespace

    return SimpleNamespace(
        pronoun_confidence_threshold=threshold,
        pronoun_safe_default=safe_default,
        enable_relationship_events=enable_relationship_events,
    )


def _make_relationship_event(
    id: int,
    series_id: int,
    char_a_id: int,
    char_b_id: int,
    episode_marker: str,
    suggested_self_term: str | None = None,
    suggested_address_term: str | None = None,
):
    """Construct a minimal RelationshipEventDTO-like object for tests.

    Uses SimpleNamespace to avoid importing RelationshipEventDTO (which does
    not yet exist in Phase 6 Wave 0).
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        id=id,
        series_id=series_id,
        character_a_id=char_a_id,
        character_b_id=char_b_id,
        episode_marker=episode_marker,
        description=None,
        created_at=None,
        suggested_self_term=suggested_self_term,
        suggested_address_term=suggested_address_term,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_low_confidence_safe_default(session_factory):
    """Low-confidence attribution → safe default returned, not an intimate pronoun (PRON-03).

    Threshold is "medium". Attribution confidence is LOW.
    Expected: get_safe_default returns ("tôi", "bạn") for neutral/unknown gender.
    reconcile_attributions returns safe default for the pair.
    """
    from trezarr.translate.reconcile import (
        reconcile_attributions,
        get_safe_default,
        SAFE_DEFAULT_SELF,
        SAFE_DEFAULT_ADDRESS_NEUTRAL,
    )

    settings = _make_settings(threshold="medium")

    # Verify get_safe_default directly
    result = get_safe_default(None, settings)
    assert result[0] == SAFE_DEFAULT_SELF, (
        f"Expected self_term '{SAFE_DEFAULT_SELF}', got '{result[0]}'"
    )
    assert result[1] == SAFE_DEFAULT_ADDRESS_NEUTRAL, (
        f"Expected address_term '{SAFE_DEFAULT_ADDRESS_NEUTRAL}', got '{result[1]}'"
    )

    # Set up DB and reconcile
    series_id = await _create_series(session_factory, arr_series_id=201)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="Alice",
        spk_gender=None,
        addr_name="Bob",
        addr_gender=None,
    )

    # LOW confidence attribution — all below "medium" threshold
    attributions = [_make_attribution("Alice", "Bob", "low")]
    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "Alice", None),
            _make_character(addr_id, "Bob", None),
        ],
        address_map=[],
    )

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E01",
        settings=settings,
    )

    # LOW confidence with "medium" threshold → safe default, not an intimate pair
    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected resolved entry for pair"
    self_t, addr_t = pair_result
    assert self_t == SAFE_DEFAULT_SELF, f"Expected '{SAFE_DEFAULT_SELF}', got '{self_t}'"
    assert addr_t == SAFE_DEFAULT_ADDRESS_NEUTRAL, (
        f"Expected '{SAFE_DEFAULT_ADDRESS_NEUTRAL}', got '{addr_t}'"
    )


async def test_high_confidence_uses_address_map(session_factory):
    """confidence=HIGH above threshold → Address Map pair is used (PRON-03).

    The bible.address_map already has ("anh", "em") for the pair.
    Attribution confidence is HIGH (>= "medium" threshold).
    Expected: resolved_map returns ("anh", "em") from the Address Map entry.
    """
    from trezarr.translate.reconcile import reconcile_attributions

    settings = _make_settings(threshold="medium")

    series_id = await _create_series(session_factory, arr_series_id=202)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="Anh",
        spk_gender="male",
        addr_name="Em",
        addr_gender="female",
    )

    # Pre-populate address map with ("anh", "em") for the pair
    from trezarr.bible.store import upsert_address_pair

    await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=spk_id,
        addressee_character_id=addr_id,
        self_term="anh",
        address_term="em",
        episode_key="S01E01",
        source="inference",
    )

    # HIGH confidence attribution
    attributions = [_make_attribution("Anh", "Em", "high")]
    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "Anh", "male"),
            _make_character(addr_id, "Em", "female"),
        ],
        address_map=[
            _make_address_map_entry(1, series_id, spk_id, addr_id, "anh", "em"),
        ],
    )

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E01",
        settings=settings,
    )

    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected resolved entry for pair"
    assert pair_result == ("anh", "em"), f"Expected ('anh', 'em'), got {pair_result!r}"


async def test_reciprocal_coherence(session_factory):
    """Reciprocal directions are coherent: A→B 'anh/em' implies B→A 'em/anh' (Success #3).

    One HIGH-confidence A→B attribution. Bible address_map has ("anh", "em") for A→B.
    After reconcile_attributions:
    - resolved_map[(spk_id, addr_id)] == ("anh", "em")  [direct pair]
    - resolved_map[(addr_id, spk_id)] == ("em", "anh")   [reciprocal — inferred]

    Also verifies KINSHIP_RECIPROCAL contains the expected entry.
    """
    from trezarr.translate.reconcile import reconcile_attributions, KINSHIP_RECIPROCAL

    # Verify KINSHIP_RECIPROCAL has the expected entry
    assert ("anh", "em") in KINSHIP_RECIPROCAL, "KINSHIP_RECIPROCAL must contain ('anh', 'em')"
    assert KINSHIP_RECIPROCAL[("anh", "em")] == ("em", "anh"), (
        f"Expected KINSHIP_RECIPROCAL[('anh','em')] == ('em','anh'), "
        f"got {KINSHIP_RECIPROCAL[('anh', 'em')]!r}"
    )

    settings = _make_settings(threshold="medium")

    series_id = await _create_series(session_factory, arr_series_id=203)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="ChiA",
        spk_gender="male",
        addr_name="EmB",
        addr_gender="female",
    )

    # Pre-populate A→B with ("anh", "em")
    from trezarr.bible.store import upsert_address_pair

    await upsert_address_pair(
        session_factory,
        series_id=series_id,
        speaker_character_id=spk_id,
        addressee_character_id=addr_id,
        self_term="anh",
        address_term="em",
        episode_key="S01E01",
        source="inference",
    )

    # ONE high-confidence A→B attribution
    attributions = [_make_attribution("ChiA", "EmB", "high")]
    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "ChiA", "male"),
            _make_character(addr_id, "EmB", "female"),
        ],
        address_map=[
            _make_address_map_entry(1, series_id, spk_id, addr_id, "anh", "em"),
        ],
    )

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E01",
        settings=settings,
    )

    # Direct pair
    direct = resolved.get((spk_id, addr_id))
    assert direct == ("anh", "em"), f"Expected direct ('anh', 'em'), got {direct!r}"

    # Reciprocal pair — inferred via KINSHIP_RECIPROCAL
    recip = resolved.get((addr_id, spk_id))
    assert recip is not None, "Expected reciprocal entry (B→A) to be inferred"
    assert recip == ("em", "anh"), f"Expected reciprocal ('em', 'anh'), got {recip!r}"


async def test_below_threshold_ignores_address_map(session_factory):
    """Below-threshold confidence → safe pair regardless of Address Map content (Success #4).

    Threshold is "high". Attribution confidence is MEDIUM (below threshold).
    An UNLOCKED Address Map entry exists for the pair with ("anh", "em").
    Expected: resolved_map returns safe default — NOT the Address Map pair.
    """
    from trezarr.translate.reconcile import (
        reconcile_attributions,
        get_safe_default,
        SAFE_DEFAULT_SELF,
    )

    # Threshold is "high", attribution confidence is "medium" → below threshold
    settings = _make_settings(threshold="high")

    series_id = await _create_series(session_factory, arr_series_id=204)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="SpeakerX",
        spk_gender=None,
        addr_name="AddresseeY",
        addr_gender=None,
    )

    # MEDIUM confidence attribution — below "high" threshold
    attributions = [_make_attribution("SpeakerX", "AddresseeY", "medium")]

    # Existing UNLOCKED address map entry with intimate pair ("anh", "em")
    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "SpeakerX", None),
            _make_character(addr_id, "AddresseeY", None),
        ],
        address_map=[
            _make_address_map_entry(
                1,
                series_id,
                spk_id,
                addr_id,
                "anh",
                "em",
                locked_fields=[],  # UNLOCKED
            ),
        ],
    )

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E01",
        settings=settings,
    )

    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected resolved entry for pair"
    self_t, addr_t = pair_result

    # CRITICAL: must NOT return ("anh", "em") from the address map — threshold not met
    assert pair_result != ("anh", "em"), (
        "Below-threshold attribution must NOT use Address Map pair ('anh', 'em'); "
        f"got {pair_result!r}"
    )

    # Must return safe default
    expected = get_safe_default(None, settings)
    assert pair_result == expected, (
        f"Expected safe default {expected!r} for below-threshold pair, got {pair_result!r}"
    )
    assert self_t == SAFE_DEFAULT_SELF, f"Expected self_term '{SAFE_DEFAULT_SELF}', got '{self_t}'"


# ---------------------------------------------------------------------------
# Phase 6 tests — BIBLE-07-C, D, E (promoted to real PASS — xfail removed)
# ---------------------------------------------------------------------------



async def test_transition_authorizes_terms_change(session_factory):  # formerly @pytest.mark.xfail — promoted to passing in Phase 6
    """BIBLE-07-C: reconcile_attributions — transition authorizes terms change.

    Arrange: bible with a relationship_event for pair (A, B) at the current episode
             whose suggested_self_term / suggested_address_term differ from the
             existing address_map entry.
    Act: call reconcile_attributions.
    Assert: the pair in resolved_map uses the suggested transition terms,
            NOT the prior address_map entry terms.
    """
    from trezarr.translate.reconcile import reconcile_attributions

    settings = _make_settings(threshold="medium")

    series_id = await _create_series(session_factory, arr_series_id=301)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="CharA",
        spk_gender="male",
        addr_name="CharB",
        addr_gender="female",
    )

    # Existing address_map entry with old (pre-transition) terms
    old_self_term = "tôi"
    old_addr_term = "bạn"
    new_self_term = "anh"
    new_addr_term = "em"

    # A relationship_event at the current episode with suggested new terms
    event = _make_relationship_event(
        id=1,
        series_id=series_id,
        char_a_id=spk_id,
        char_b_id=addr_id,
        episode_marker="S01E05",
        suggested_self_term=new_self_term,
        suggested_address_term=new_addr_term,
    )

    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "CharA", "male"),
            _make_character(addr_id, "CharB", "female"),
        ],
        address_map=[
            _make_address_map_entry(1, series_id, spk_id, addr_id, old_self_term, old_addr_term),
        ],
        relationship_events=[event],
    )

    # HIGH-confidence attribution so the pair is considered
    attributions = [_make_attribution("CharA", "CharB", "high")]

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E05",
        settings=settings,
    )

    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected resolved entry for transitioning pair"
    assert pair_result == (new_self_term, new_addr_term), (
        f"Transition should authorize new terms {(new_self_term, new_addr_term)!r}, "
        f"got {pair_result!r}"
    )


async def test_transition_adopts_attribution_confirmed_terms(session_factory):
    """CR-02 + WR-03: transition with no suggested terms adopts this episode's confident attribution.

    Arrange: a relationship_event with NO suggested terms + a high-confidence attribution
             for the pair + an existing address_map entry with confirmed terms.
    Act: reconcile_attributions.
    Assert: the pair adopts the existing address_map entry terms (this episode's confident
            inference), NOT a safe-default — D-54 step 2 of the fallback order.
    """
    from trezarr.translate.reconcile import reconcile_attributions

    settings = _make_settings(threshold="medium")

    series_id = await _create_series(session_factory, arr_series_id=304)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="TranA",
        spk_gender="male",
        addr_name="TranB",
        addr_gender="female",
    )

    # A relationship_event with NO suggested terms — forces path 2 (attribution-confirmed)
    event_no_suggest = _make_relationship_event(
        id=20,
        series_id=series_id,
        char_a_id=spk_id,
        char_b_id=addr_id,
        episode_marker="S01E09",
        suggested_self_term=None,     # no suggested terms
        suggested_address_term=None,  # no suggested terms
    )

    # Existing address_map entry with confirmed terms (this episode's confident inference)
    confirmed_self = "anh"
    confirmed_addr = "em"

    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "TranA", "male"),
            _make_character(addr_id, "TranB", "female"),
        ],
        address_map=[
            _make_address_map_entry(20, series_id, spk_id, addr_id, confirmed_self, confirmed_addr),
        ],
        relationship_events=[event_no_suggest],
    )

    # HIGH-confidence attribution — survivors exist for this pair
    attributions = [_make_attribution("TranA", "TranB", "high")]

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E09",
        settings=settings,
    )

    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected resolved entry for pair with transition"
    # Must use confident existing terms (path 2), NOT safe-default
    assert pair_result == (confirmed_self, confirmed_addr), (
        f"Transition with no suggested terms + confident attribution must adopt "
        f"existing terms {(confirmed_self, confirmed_addr)!r}, got {pair_result!r}"
    )


async def test_transition_no_survivors_falls_to_safe_default(session_factory):
    """CR-02 fallback: transition with no suggested terms + no survivors → safe default.

    Arrange: a relationship_event with NO suggested terms + LOW-confidence attribution
             (no survivors above threshold) + an existing address_map entry.
    Act: reconcile_attributions.
    Assert: the pair falls back to safe default — D-54 step 3.
    """
    from trezarr.translate.reconcile import reconcile_attributions, get_safe_default

    # HIGH threshold — "low" attribution won't be a survivor
    settings = _make_settings(threshold="high")

    series_id = await _create_series(session_factory, arr_series_id=305)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="TranC",
        spk_gender=None,
        addr_name="TranD",
        addr_gender=None,
    )

    # A relationship_event with NO suggested terms
    event_no_suggest = _make_relationship_event(
        id=21,
        series_id=series_id,
        char_a_id=spk_id,
        char_b_id=addr_id,
        episode_marker="S01E10",
        suggested_self_term=None,
        suggested_address_term=None,
    )

    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "TranC", None),
            _make_character(addr_id, "TranD", None),
        ],
        address_map=[
            _make_address_map_entry(21, series_id, spk_id, addr_id, "anh", "em"),
        ],
        relationship_events=[event_no_suggest],
    )

    # LOW confidence — below "high" threshold → no survivors
    attributions = [_make_attribution("TranC", "TranD", "low")]

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E10",
        settings=settings,
    )

    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected a resolved entry (safe default)"
    expected = get_safe_default(None, settings)
    assert pair_result == expected, (
        f"Transition with no suggested terms + no survivors must fall back to safe default "
        f"{expected!r}, got {pair_result!r}"
    )


async def test_lock_beats_transition(session_factory):  # formerly @pytest.mark.xfail — promoted to passing in Phase 6
    """BIBLE-07-D: reconcile_attributions — lock beats transition (D-34/D-54).

    Arrange: bible with a LOCKED address_map entry AND a relationship_event for
             the same pair at the current episode.
    Act: call reconcile_attributions.
    Assert: the locked terms win — NOT the transition's suggested terms.
    """
    from trezarr.translate.reconcile import reconcile_attributions

    settings = _make_settings(threshold="medium")

    series_id = await _create_series(session_factory, arr_series_id=302)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="LockedSpeaker",
        spk_gender="male",
        addr_name="LockedAddressee",
        addr_gender="female",
    )

    # Locked address_map entry — human override
    locked_self_term = "anh"
    locked_addr_term = "em"

    # Relationship event trying to change to different terms
    event = _make_relationship_event(
        id=2,
        series_id=series_id,
        char_a_id=spk_id,
        char_b_id=addr_id,
        episode_marker="S01E06",
        suggested_self_term="chị",
        suggested_address_term="bạn",
    )

    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "LockedSpeaker", "male"),
            _make_character(addr_id, "LockedAddressee", "female"),
        ],
        address_map=[
            _make_address_map_entry(
                2,
                series_id,
                spk_id,
                addr_id,
                locked_self_term,
                locked_addr_term,
                locked_fields=["self_term", "address_term"],  # LOCKED
            ),
        ],
        relationship_events=[event],
    )

    attributions = [_make_attribution("LockedSpeaker", "LockedAddressee", "high")]

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E06",
        settings=settings,
    )

    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected resolved entry for locked pair"
    assert pair_result == (locked_self_term, locked_addr_term), (
        f"Lock must beat transition: expected locked terms {(locked_self_term, locked_addr_term)!r}, "
        f"got {pair_result!r}"
    )


async def test_no_transition_no_survivors_safe_default(session_factory):  # formerly @pytest.mark.xfail — promoted to passing in Phase 6
    """BIBLE-07-E: no transition + no high-confidence survivors → safe default (Phase-5 Success #4 preserved).

    Arrange: bible with NO relationship_event and NO high-confidence attribution for the pair.
    Act: call reconcile_attributions.
    Assert: the pair falls back to the safe default pair (tôi + anh/chị/bạn),
            preserving the Phase-5 guarantee that no wrong intimate pronoun is ever used.
    """
    from trezarr.translate.reconcile import (
        reconcile_attributions,
        get_safe_default,
        SAFE_DEFAULT_SELF,
    )

    # Threshold "high" — attribution is "low" → below threshold → no survivors
    settings = _make_settings(threshold="high")

    series_id = await _create_series(session_factory, arr_series_id=303)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="SpeakerNoTrans",
        spk_gender=None,
        addr_name="AddresseeNoTrans",
        addr_gender=None,
    )

    # NO relationship_events in the bible
    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "SpeakerNoTrans", None),
            _make_character(addr_id, "AddresseeNoTrans", None),
        ],
        address_map=[],
        relationship_events=[],  # empty — no transition
    )

    # LOW confidence — below "high" threshold → no survivors
    attributions = [_make_attribution("SpeakerNoTrans", "AddresseeNoTrans", "low")]

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E07",
        settings=settings,
    )

    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected a safe default entry for the pair"
    self_t, addr_t = pair_result

    expected = get_safe_default(None, settings)
    assert pair_result == expected, (
        f"No transition + no survivors must yield safe default {expected!r}, got {pair_result!r}"
    )
    assert self_t == SAFE_DEFAULT_SELF, (
        f"Phase-5 Success #4 preserved: self_term must be {SAFE_DEFAULT_SELF!r}, got {self_t!r}"
    )


# ---------------------------------------------------------------------------
# CR-01 regression tests — B1 BLOCKER: .strip().lower() at all three lookup sites
# ---------------------------------------------------------------------------


async def test_reconcile_strips_whitespace_from_speaker_and_addressee(session_factory):
    """Whitespace-padded LLM names (e.g. ' Minh') resolve to the correct pronoun pair (B1 fix).

    Characters are stored as 'Minh'/'Lan'. Attributions arrive with leading-space names
    ' Minh' and ' Lan'. HIGH confidence, threshold 'medium', existing address_map entry
    (anh/em). Expected: resolved_map is non-empty and contains ('anh', 'em').
    """
    from trezarr.translate.reconcile import reconcile_attributions

    settings = _make_settings(threshold="medium")

    series_id = await _create_series(session_factory, arr_series_id=401)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="Minh",
        spk_gender="male",
        addr_name="Lan",
        addr_gender="female",
    )

    # bible has characters stored as "Minh"/"Lan" (no padding)
    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "Minh", "male"),
            _make_character(addr_id, "Lan", "female"),
        ],
        address_map=[
            _make_address_map_entry(1, series_id, spk_id, addr_id, "anh", "em"),
        ],
    )

    # Attributions arrive with leading whitespace (simulating LLM padding)
    attributions = [_make_attribution(" Minh", " Lan", "high")]

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E01",
        settings=settings,
    )

    assert resolved, "resolved_map must be non-empty — whitespace-padded names must resolve"
    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, (
        "Whitespace-padded speaker/addressee must resolve to pronoun pair, not safe-default drop"
    )
    assert pair_result == ("anh", "em"), (
        f"Expected ('anh', 'em') from address map entry, got {pair_result!r}"
    )


async def test_reconcile_strips_casing_from_speaker_and_addressee(session_factory):
    """Casing-variant LLM names (e.g. 'MINH') resolve to the correct pronoun pair (B1 fix, CR-01).

    Characters are stored as 'Minh'/'Lan'. Attributions arrive as 'MINH' and 'LAN'.
    HIGH confidence, threshold 'medium', existing address_map entry (anh/em).
    Expected: resolved_map contains ('anh', 'em').
    """
    from trezarr.translate.reconcile import reconcile_attributions

    settings = _make_settings(threshold="medium")

    series_id = await _create_series(session_factory, arr_series_id=402)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="Minh",
        spk_gender="male",
        addr_name="Lan",
        addr_gender="female",
    )

    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "Minh", "male"),
            _make_character(addr_id, "Lan", "female"),
        ],
        address_map=[
            _make_address_map_entry(1, series_id, spk_id, addr_id, "anh", "em"),
        ],
    )

    # Attributions arrive with ALL-CAPS names (LLM casing variant)
    attributions = [_make_attribution("MINH", "LAN", "high")]

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E01",
        settings=settings,
    )

    assert resolved, "resolved_map must be non-empty — casing-variant names must resolve"
    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, (
        "Casing-variant speaker/addressee must resolve to pronoun pair, not safe-default drop"
    )
    assert pair_result == ("anh", "em"), (
        f"Expected ('anh', 'em') from address map entry, got {pair_result!r}"
    )


# ---------------------------------------------------------------------------
# WR-01 — enable_relationship_events toggle off-path test
# ---------------------------------------------------------------------------


async def test_enable_relationship_events_false_suppresses_transition(session_factory):
    """WR-01: enable_relationship_events=False suppresses transition lookup (D-60 toggle).

    Arrange: bible with a relationship_event for the pair at the current episode
             and an existing address_map entry with old terms.
    Act: reconcile_attributions with enable_relationship_events=False.
    Assert: the transition is NOT applied — pair uses the existing address_map entry
            terms (carried-forward), NOT the transition's suggested terms.
    """
    from trezarr.translate.reconcile import reconcile_attributions

    # Toggle OFF — transition branch must be skipped entirely
    settings = _make_settings(threshold="medium", enable_relationship_events=False)

    series_id = await _create_series(session_factory, arr_series_id=403)
    spk_id, addr_id = await _create_characters(
        session_factory,
        series_id,
        spk_name="ToggleA",
        spk_gender="male",
        addr_name="ToggleB",
        addr_gender="female",
    )

    # A relationship_event that would change terms if the toggle were on
    event = _make_relationship_event(
        id=10,
        series_id=series_id,
        char_a_id=spk_id,
        char_b_id=addr_id,
        episode_marker="S01E08",
        suggested_self_term="anh",
        suggested_address_term="em",
    )

    # Existing address_map entry with old terms
    bible = _make_bible(
        series_id=series_id,
        characters=[
            _make_character(spk_id, "ToggleA", "male"),
            _make_character(addr_id, "ToggleB", "female"),
        ],
        address_map=[
            _make_address_map_entry(10, series_id, spk_id, addr_id, "tôi", "bạn"),
        ],
        relationship_events=[event],
    )

    attributions = [_make_attribution("ToggleA", "ToggleB", "high")]

    resolved = await reconcile_attributions(
        flat_attributions=attributions,
        bible=bible,
        session_factory=session_factory,
        series_id=series_id,
        episode_key="S01E08",
        settings=settings,
    )

    pair_result = resolved.get((spk_id, addr_id))
    assert pair_result is not None, "Expected resolved entry for pair"
    # With toggle OFF, transition is suppressed — carried-forward ("tôi", "bạn") applies
    assert pair_result == ("tôi", "bạn"), (
        f"enable_relationship_events=False must suppress transition; "
        f"expected carried-forward ('tôi', 'bạn'), got {pair_result!r}"
    )


# ---------------------------------------------------------------------------
# Phase 8 additions — D-90 H1 regression stubs
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    raises=(AssertionError,),
    strict=False,
    reason="KINSHIP_RECIPROCAL bác/cháu gaps not yet filled — Plan 08-02 D-90",
)
async def test_kinship_reciprocal_bac_chau():
    """D-90 H1 fix: bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày round-trip in KINSHIP_RECIPROCAL; junior-only attribution on bác/cháu does not overwrite locked pair."""
    from trezarr.translate.reconcile import KINSHIP_RECIPROCAL  # noqa: PLC0415
    assert ("bác", "cháu") in KINSHIP_RECIPROCAL and ("cháu", "bác") in KINSHIP_RECIPROCAL
