"""Tests for arr_metadata JSON snapshot round-trip, register NULL invariant, and UTF-8 cap (D-35).

Verifies:
  - arr_metadata persists and round-trips as a dict through the JSON column
    (lists and nested values preserved, no string conversion).
  - register is None after get_or_create_series — Phase 5 sets it via merge_inferred.
  - The 32 KB size cap uses json.dumps(..., ensure_ascii=False) so Vietnamese text
    (3 bytes/char in UTF-8) measures correctly as UTF-8 bytes, NOT as 6-char
    \\uXXXX escape sequences.

References:
  D-35: arr_metadata snapshot at series-row creation.
  T-04-05: 32 KB cap DoS hardening; Vietnamese UTF-8 byte measurement.
  Cross-AI review MEDIUM finding: ensure_ascii=False for byte cap calculation.
"""
from __future__ import annotations


async def test_arr_metadata_round_trips_as_dict(session_factory):
    """arr_metadata persists and reloads as a dict with lists and strings preserved.

    Creates a series with a rich arr_metadata_snapshot; reloads via load_series_bible();
    verifies the returned SeriesBibleDTO.arr_metadata equals the original dict.

    Verifies: D-35 JSON column round-trip for all value types (list, str, int).
    """
    from trezarr.bible.store import get_or_create_series, load_series_bible

    snapshot = {
        "genres": ["drama", "thriller"],
        "overview": "A spy story.",
        "year": 2020,
        "network": "BBC",
        "runtime": 60,
    }

    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=10,
        arr_metadata_snapshot=snapshot,
    )

    bible_dto = await load_series_bible(session_factory, dto.id)

    assert bible_dto.arr_metadata == snapshot, (
        f"arr_metadata round-trip failed.\n"
        f"  Expected: {snapshot}\n"
        f"  Got:      {bible_dto.arr_metadata}"
    )
    # Specifically verify list type is preserved (not a string)
    assert isinstance(bible_dto.arr_metadata["genres"], list), (
        f"genres must remain a list after JSON round-trip, got {type(bible_dto.arr_metadata['genres'])}"
    )


async def test_register_starts_null(session_factory):
    """Newly-created series has register=None — Phase 4 NEVER sets it.

    Phase 5 populates register via merge_inferred() after running LLM Pass-1
    on the arr_metadata snapshot. Phase 4 only persists what discovery provides.

    Verifies: D-35 — Phase 4 sets series.register = NULL; Phase 5 uses merge_inferred.
    """
    from trezarr.bible.store import get_or_create_series, load_series_bible

    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=20,
        arr_metadata_snapshot={"year": 2021},
    )

    bible_dto = await load_series_bible(session_factory, dto.id)

    # CR-02: the Python attribute on the DTO is ``register_value`` (alias
    # ``register``) to avoid shadowing Pydantic v2's deprecated
    # ``BaseModel.register`` classmethod.
    assert bible_dto.register_value is None, (
        f"register must be None after Phase-4 creation (Phase 5 sets it via merge_inferred). "
        f"Got: {bible_dto.register_value!r}"
    )


async def test_arr_metadata_utf8_byte_cap_with_vietnamese(session_factory):
    """The 32 KB cap uses ensure_ascii=False so Vietnamese text counts as UTF-8 bytes, not escapes.

    Constructs an arr_metadata_snapshot containing Vietnamese text with non-ASCII
    characters. Under ensure_ascii=True, each non-ASCII char becomes a 6-byte
    \\uXXXX escape sequence, inflating the byte count. Under ensure_ascii=False,
    Vietnamese characters count as 2–3 bytes each (their actual UTF-8 representation).

    This test creates a payload that would EXCEED 32 KB if measured with ensure_ascii=True
    (6 bytes per Vietnamese char) but STAYS UNDER 32 KB when measured with
    ensure_ascii=False (3 bytes per Vietnamese char). It must be ACCEPTED.

    Verifies: Cross-AI review MEDIUM finding — ensure_ascii=False in get_or_create_series
    size validation; T-04-05 DoS hardening with correct Vietnamese byte measurement.
    """
    import json
    from trezarr.bible.store import get_or_create_series, MAX_ARR_METADATA_BYTES

    # Vietnamese characters are 3 bytes each in UTF-8 (e.g. 'ắ' = U+1EAF = 3 bytes)
    # but become 6 chars as \uXXXX escapes under ensure_ascii=True.
    # We need a payload where:
    #   len(json.dumps(payload, ensure_ascii=True).encode('utf-8')) > 32768  (would fail if cap used ascii)
    #   len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) <= 32768  (passes with correct cap)
    #
    # Each Vietnamese char: 3 bytes UTF-8 vs 6 chars ASCII escape.
    # We need N chars where: N * 6 > 32768 AND N * 3 <= 32768
    # => N > 5461 AND N <= 10922   => use N = 8000 (exactly between)
    #
    # Build a payload of 8000 Vietnamese characters (ắ = U+1EAF, 3 bytes each)
    vietnamese_chars = "ắ" * 8_000   # 8000 * 3 = 24000 bytes UTF-8; 8000 * 6 = 48000 bytes ASCII-escaped

    payload = {"overview": vietnamese_chars}

    # Verify our test setup: ensure_ascii=True version would exceed the cap
    ascii_size = len(json.dumps(payload, ensure_ascii=True).encode("utf-8"))
    utf8_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    assert ascii_size > MAX_ARR_METADATA_BYTES, (
        f"Test setup error: ASCII-escaped version ({ascii_size} bytes) should exceed "
        f"cap ({MAX_ARR_METADATA_BYTES} bytes) for this test to be meaningful"
    )
    assert utf8_size <= MAX_ARR_METADATA_BYTES, (
        f"Test setup error: UTF-8 version ({utf8_size} bytes) should fit within "
        f"cap ({MAX_ARR_METADATA_BYTES} bytes) for this test to be meaningful"
    )

    # The call must SUCCEED (not raise ValueError) because the cap uses ensure_ascii=False
    dto = await get_or_create_series(
        session_factory,
        arr_kind="sonarr",
        arr_instance="default",
        arr_series_id=30,
        arr_metadata_snapshot=payload,
    )

    # Verify the row was persisted and can be reloaded
    from trezarr.bible.store import load_series_bible
    bible_dto = await load_series_bible(session_factory, dto.id)
    assert bible_dto.arr_metadata["overview"] == vietnamese_chars, (
        "Vietnamese overview text must survive JSON round-trip unchanged"
    )
