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


def _make_bible(series_id: int, characters: list, address_map: list):
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


def _make_settings(threshold: str = "medium", safe_default=None):
    """Build a minimal TrezarrSettings-like object."""
    from types import SimpleNamespace
    return SimpleNamespace(
        pronoun_confidence_threshold=threshold,
        pronoun_safe_default=safe_default,
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
    from trezarr.translate.reconcile import reconcile_attributions, get_safe_default, SAFE_DEFAULT_SELF, SAFE_DEFAULT_ADDRESS_NEUTRAL

    settings = _make_settings(threshold="medium")

    # Verify get_safe_default directly
    result = get_safe_default(None, settings)
    assert result[0] == SAFE_DEFAULT_SELF, f"Expected self_term '{SAFE_DEFAULT_SELF}', got '{result[0]}'"
    assert result[1] == SAFE_DEFAULT_ADDRESS_NEUTRAL, f"Expected address_term '{SAFE_DEFAULT_ADDRESS_NEUTRAL}', got '{result[1]}'"

    # Set up DB and reconcile
    series_id = await _create_series(session_factory, arr_series_id=201)
    spk_id, addr_id = await _create_characters(
        session_factory, series_id,
        spk_name="Alice", spk_gender=None,
        addr_name="Bob", addr_gender=None,
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
    assert addr_t == SAFE_DEFAULT_ADDRESS_NEUTRAL, f"Expected '{SAFE_DEFAULT_ADDRESS_NEUTRAL}', got '{addr_t}'"


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
        session_factory, series_id,
        spk_name="Anh", spk_gender="male",
        addr_name="Em", addr_gender="female",
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
        f"got {KINSHIP_RECIPROCAL[('anh','em')]!r}"
    )

    settings = _make_settings(threshold="medium")

    series_id = await _create_series(session_factory, arr_series_id=203)
    spk_id, addr_id = await _create_characters(
        session_factory, series_id,
        spk_name="ChiA", spk_gender="male",
        addr_name="EmB", addr_gender="female",
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
    from trezarr.translate.reconcile import reconcile_attributions, get_safe_default, SAFE_DEFAULT_SELF

    # Threshold is "high", attribution confidence is "medium" → below threshold
    settings = _make_settings(threshold="high")

    series_id = await _create_series(session_factory, arr_series_id=204)
    spk_id, addr_id = await _create_characters(
        session_factory, series_id,
        spk_name="SpeakerX", spk_gender=None,
        addr_name="AddresseeY", addr_gender=None,
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
                1, series_id, spk_id, addr_id,
                "anh", "em",
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
