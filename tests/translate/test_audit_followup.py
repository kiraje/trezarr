"""Regression tests for the Ep-142 audit second-round fixes (adversarial-verify findings).

These lock in the fixes for the four MEDIUM + the LOW findings the finding-verifier
confirmed AFTER the first fix pass — the false-positives the fixes themselves introduced:

  MEDIUM-2  validate Check 12 must NOT flag a diacritic-free Vietnamese parenthetical
            ("(anh em ta)") while still catching the English gloss ("(Miss Mei's brother)").
  MEDIUM-3  validate Check 10 must NOT flag laughter/onomatopoeia ("Ha ha ha") while still
            catching a genuine English passthrough.
  MEDIUM-4  parse_numbered_response must NOT splice trailing model prose into a single-line
            cue (multiline_indices guard), while a true multi-line cue still round-trips.
  LOW-3     _resolve_char_id must resolve an honorific-prefixed name ("Mr. Han" -> "Han")
            WITHOUT colliding two distinct characters that differ only by an honorific.
"""
import pytest

from trezarr.subtitles.model import SubDoc, SubLine
from trezarr.translate.engine import (
    _normalize_name,
    _resolve_char_id,
    parse_numbered_response,
)
from trezarr.translate.validate import GateError, validate_subdoc


def _line(index: int, text: str, start="00:00:01,000", end="00:00:03,000") -> SubLine:
    return SubLine(index=str(index), start_tc=start, end_tc=end, text=text)


def _doc(texts: list[str]) -> SubDoc:
    lines = [_line(i + 1, t) for i, t in enumerate(texts)]
    return SubDoc(
        lines=lines,
        encoding="utf-8",
        line_ending="\n",
        separators=["\n\n"] * max(0, len(lines) - 1),
        leading="",
        trailer="\n",
    )


def _settings():
    from trezarr.config import TrezarrSettings
    return TrezarrSettings(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
    )


# Four diacritic-bearing Vietnamese cues used to keep the per-file Check-3 ratio above
# threshold so a single non-diacritic cue under test reaches the per-cue checks 9-12.
# Each carries a NARROW-range diacritic (U+1E00–U+1EFF or Ơơ/Ưư) so it counts toward Check-3:
#   trưởng → ư/ở · Tại hạ → ạ · Ngươi muốn → ư/ố · Đừng vội → ừ/ộ
_VI_FILLER = ["Chào huynh trưởng.", "Tại hạ hiểu rồi.", "Ngươi muốn gì?", "Đừng đi vội."]


# ── MEDIUM-3: Check 10 onomatopoeia false-positive ──────────────────────────────

def test_check10_passes_repeated_onomatopoeia():
    """A legitimately-untranslated 'Ha ha ha' laughter cue must NOT quarantine the file."""
    src = _doc(_VI_FILLER + ["Ha ha ha"])
    trn = _doc(_VI_FILLER + ["Ha ha ha"])
    validate_subdoc(trn, src, _settings())  # must not raise


def test_check10_passes_interjection_only_cue():
    """A cue made only of interjections ('Hmm uh') is exempt from the passthrough check."""
    src = _doc(_VI_FILLER + ["Hmm uh"])
    trn = _doc(_VI_FILLER + ["Hmm uh"])
    validate_subdoc(trn, src, _settings())  # must not raise


def test_check10_passes_listed_laughter_onomatopoeia():
    """'Ho ho ho' / 'Hee hee' laughter (listed interjection syllables) must not quarantine."""
    for laugh in ["Ho ho ho", "Hee hee", "Haw haw"]:
        src = _doc(_VI_FILLER + [laugh])
        trn = _doc(_VI_FILLER + [laugh])
        validate_subdoc(trn, src, _settings())  # must not raise


@pytest.mark.parametrize("eng", ["We attack now", "Go go", "No no", "Stop stop", "Run run"])
def test_check10_still_catches_english_passthrough(eng):
    """Regression preserved + tightened: untranslated English — INCLUDING repeated imperatives
    like 'Go go' / 'No no' that the old blanket repeated-token exemption let escape — raises GateError(10)."""
    src = _doc(_VI_FILLER + [eng])
    trn = _doc(_VI_FILLER + [eng])
    with pytest.raises(GateError) as exc:
        validate_subdoc(trn, src, _settings())
    assert exc.value.failure.check == 10


# ── MEDIUM-2: Check 12 diacritic-free Vietnamese parenthetical false-positive ────

@pytest.mark.parametrize("vn_paren", ["(anh em ta)", "(cho con)", "(thua ong)", "(anh ba)"])
def test_check12_passes_diacritic_free_vietnamese_parenthetical(vn_paren):
    """A short diacritic-free Vietnamese aside in parens must NOT be flagged as an English gloss."""
    src = _doc(_VI_FILLER + ["(brothers)"])
    trn = _doc(_VI_FILLER + [vn_paren])
    validate_subdoc(trn, src, _settings())  # must not raise


def test_check12_still_catches_english_possessive_gloss():
    """Regression preserved: the audit's '(Miss Mei's brother)' gloss still raises GateError(12)."""
    src = _doc(_VI_FILLER + ["Mei"])
    trn = _doc(_VI_FILLER + ["Đi nào (Miss Mei's brother)"])
    with pytest.raises(GateError) as exc:
        validate_subdoc(trn, src, _settings())
    assert exc.value.failure.check == 12


# ── MEDIUM-4: parse_numbered_response trailing-prose guard ───────────────────────

def test_parse_drops_trailing_prose_for_single_line_cue():
    """Trailing model prose after the last cue must NOT be spliced into a single-line cue."""
    resp = "[1] Xin chào\n[2] Tạm biệt\nHy vọng bản dịch này hữu ích!"
    out = parse_numbered_response(resp, 2, multiline_indices=set())
    assert out == ["Xin chào", "Tạm biệt"]


def test_parse_accumulates_real_newline_for_multiline_cue():
    """A genuine multi-line cue (in multiline_indices) still accumulates its continuation line."""
    resp = "[1] Dòng một\nDòng hai\n[2] Kết thúc"
    out = parse_numbered_response(resp, 2, multiline_indices={1})
    assert out == ["Dòng một\nDòng hai", "Kết thúc"]


def test_parse_br_token_round_trips_byte_identical():
    """A <<BR>> internal-break sentinel restores to a newline regardless of multiline_indices."""
    assert parse_numbered_response("[1] A<<BR>>B", 1) == ["A\nB"]
    assert parse_numbered_response("[1] A<<BR>>B", 1, multiline_indices=set()) == ["A\nB"]


# ── LOW-3: _resolve_char_id honorific resolution without collision ───────────────

def test_resolve_char_id_honorific_falls_back_to_base():
    index = {"han": 5}
    assert _resolve_char_id(index, "Mr. Han") == 5
    assert _resolve_char_id(index, "Elder Han") == 5
    assert _resolve_char_id(index, "Han") == 5


def test_resolve_char_id_does_not_collide_distinct_characters():
    """'Zhou' and 'Elder Zhou' are distinct characters — exact match wins, no honorific collision."""
    index = {"zhou": 2, "elder zhou": 1}
    assert _resolve_char_id(index, "Zhou") == 2
    assert _resolve_char_id(index, "Elder Zhou") == 1


def test_resolve_char_id_handles_none_and_miss():
    assert _resolve_char_id({"han": 5}, None) is None
    assert _resolve_char_id({}, "Anyone") is None


def test_normalize_name_keeps_bare_honorific():
    assert _normalize_name("Elder Zhou") == "zhou"
    assert _normalize_name("Mr. Han") == "han"
    assert _normalize_name("Elder") == "elder"  # bare honorific maps to itself (never empty)
