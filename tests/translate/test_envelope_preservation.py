"""RED/GREEN tests for 260608-pbz: deterministic envelope preservation in translate_file().

Tests cover:
  1. test_multiline_title_card_wrapped       — multi-line source in ( ) → translation re-wrapped
  2. test_single_line_title_card_wrapped     — single-line "(Tập 142)" → translation re-wrapped
  3. test_square_bracket_wrapped             — source "[Note]" → translation re-wrapped in [ ]
  4. test_idempotent_already_wrapped         — translated already has ( ) → no double-wrap
  5. test_mid_sentence_aside_skipped         — "Anh ấy (cười) nói" → Step A fails → skipped
  6. test_source_not_wrapped_skipped         — source has no wrapper → skipped
  7. test_raw_cue_skipped                    — SubLine(raw=...) → skipped verbatim
  8. test_gate_compatibility                 — re-wrapped VI title card passes real validate_subdoc
  9. test_flag_off_noop                      — enable_envelope_preservation=False → no-op
  10. test_two_parens_not_full_wrapper        — "(a) and (b)" → depth hits 0 at index 2 → skipped
  11. test_envelope_survives_gate_repair_loop — harness finding: repaired cue gets envelope
      re-applied after _repair_failing_cues splices a new translated_doc (Step-9 loop gap)

Uses asyncio_mode=auto (pyproject.toml); no @pytest.mark.asyncio needed.

Detection algorithm (3 steps):
  Step A: stripped source[0] in opener_map AND source[-1] == matching closer
  Step B: bracket-depth scan counting only the Step-A bracket type; depth must return to 0
          EXACTLY at the final character (not before — that flags a two-group form)
  Step C: idempotency — if translated already starts with opener and ends with closer → no-op
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ── Shared helpers (same pattern as test_gate_repair.py) ─────────────────────


def _make_line(
    index: int,
    start_tc: str = "00:00:01,000",
    end_tc: str = "00:00:03,000",
    text: str = "Xin chào.",
    raw: str | None = None,
) -> object:
    from trezarr.subtitles.model import SubLine

    return SubLine(index=str(index), start_tc=start_tc, end_tc=end_tc, text=text, raw=raw)


def _make_doc(lines: list) -> object:
    from trezarr.subtitles.model import SubDoc

    return SubDoc(
        lines=lines,
        encoding="utf-8",
        line_ending="\n",
        separators=["\n\n"] * max(0, len(lines) - 1),
        leading="",
        trailer="\n",
    )


def _settings(**overrides: Any) -> object:
    from trezarr.config import TrezarrSettings

    defaults = dict(
        llm_base_url="http://localhost:1234/v1",
        llm_api_key="test-key",
        llm_model="test-model",
        llm_max_concurrency=1,
    )
    defaults.update(overrides)
    return TrezarrSettings(**defaults)


# ── Test 1: multi-line title card is re-wrapped ───────────────────────────────


def test_multiline_title_card_wrapped() -> None:
    """Multi-line source enclosed in ( ) gets the opener/closer re-applied to the translation.

    Source: "(A Record of Mortal's Journey to Immortality\\nUpheaval in Outer Sea Season 3)"
    Translated: "Phàm Nhân Tu Tiên Truyện\\nNgoại Hải Phong Vân Phần 3"
    Expected: "(Phàm Nhân Tu Tiên Truyện\\nNgoại Hải Phong Vân Phần 3)"
    index/start_tc/end_tc must be byte-identical to the source line (D-ENV-06).
    """
    from trezarr.translate.engine import _preserve_source_envelopes

    src_text = "(A Record of Mortal's Journey to Immortality\nUpheaval in Outer Sea Season 3)"
    trn_text = "Phàm Nhân Tu Tiên Truyện\nNgoại Hải Phong Vân Phần 3"

    src_line = _make_line(1, start_tc="00:00:01,000", end_tc="00:00:05,000", text=src_text)
    trn_line = _make_line(1, start_tc="00:00:01,000", end_tc="00:00:05,000", text=trn_text)

    src_doc = _make_doc([src_line])
    trn_doc = _make_doc([trn_line])
    settings = _settings()

    result = _preserve_source_envelopes(trn_doc, src_doc, settings)

    assert len(result.lines) == 1
    out_line = result.lines[0]
    assert out_line.text == f"({trn_text})", (
        f"Expected text to be '({trn_text})', got {out_line.text!r}"
    )
    # Byte identity (D-ENV-06): timecodes copied verbatim from source
    assert out_line.index == src_line.index, "index must be byte-identical to source"
    assert out_line.start_tc == src_line.start_tc, "start_tc must be byte-identical to source"
    assert out_line.end_tc == src_line.end_tc, "end_tc must be byte-identical to source"
    assert out_line.raw is None, "raw must be None for a translated (non-opaque) cue"


# ── Test 2: single-line title card is re-wrapped ──────────────────────────────


def test_single_line_title_card_wrapped() -> None:
    """Single-line source "(Tập 142)" → missing-parens translation "Tập 142" → "(Tập 142)".

    This is the canonical Ep-142 cue-1 shape (D-ENV-01).
    """
    from trezarr.translate.engine import _preserve_source_envelopes

    src_line = _make_line(1, text="(Tập 142)")
    trn_line = _make_line(1, text="Tập 142")

    result = _preserve_source_envelopes(_make_doc([trn_line]), _make_doc([src_line]), _settings())

    assert result.lines[0].text == "(Tập 142)", (
        f"Expected '(Tập 142)', got {result.lines[0].text!r}"
    )


# ── Test 3: square bracket envelope preserved ─────────────────────────────────


def test_square_bracket_wrapped() -> None:
    """Source "[Note]" → translated "Ghi chú" → "[Ghi chú]" (D-ENV-04: [ ] pair)."""
    from trezarr.translate.engine import _preserve_source_envelopes

    src_line = _make_line(1, text="[Note]")
    trn_line = _make_line(1, text="Ghi chú")

    result = _preserve_source_envelopes(_make_doc([trn_line]), _make_doc([src_line]), _settings())

    assert result.lines[0].text == "[Ghi chú]", (
        f"Expected '[Ghi chú]', got {result.lines[0].text!r}"
    )


# ── Test 4: idempotent — already-wrapped translation is not double-wrapped ────


def test_idempotent_already_wrapped() -> None:
    """Source "(Tập 142)", translated "(Tập 142)" → no double-wrap (D-ENV-03 / Step C)."""
    from trezarr.translate.engine import _preserve_source_envelopes

    src_line = _make_line(1, text="(Tập 142)")
    trn_line = _make_line(1, text="(Tập 142)")

    result = _preserve_source_envelopes(_make_doc([trn_line]), _make_doc([src_line]), _settings())

    assert result.lines[0].text == "(Tập 142)", (
        f"Idempotency: expected '(Tập 142)', got {result.lines[0].text!r}"
    )
    assert not result.lines[0].text.startswith("(("), "Must NOT produce double-wrap '((Tập 142))'"


# ── Test 5: mid-sentence aside is skipped (Step A fails) ─────────────────────


def test_mid_sentence_aside_skipped() -> None:
    """Source "Anh ấy (cười) nói gì đó." → Step A fails (source[0] not an opener) → no change.

    D-ENV-02: a mid-sentence aside never trips the full-enclosure check.
    """
    from trezarr.translate.engine import _preserve_source_envelopes

    text = "Anh ấy (cười) nói gì đó."
    src_line = _make_line(1, text=text)
    trn_line = _make_line(1, text=text)

    result = _preserve_source_envelopes(_make_doc([trn_line]), _make_doc([src_line]), _settings())

    assert result.lines[0].text == text, (
        f"Mid-sentence aside must be unchanged. Got {result.lines[0].text!r}"
    )


# ── Test 6: source without wrapper — no change ────────────────────────────────


def test_source_not_wrapped_skipped() -> None:
    """Source "Han Lập nói rằng." has no outer bracket → output untouched."""
    from trezarr.translate.engine import _preserve_source_envelopes

    src_line = _make_line(1, text="Han Lập nói rằng.")
    trn_line = _make_line(1, text="Hàn Lập nói rằng.")

    result = _preserve_source_envelopes(_make_doc([trn_line]), _make_doc([src_line]), _settings())

    assert result.lines[0].text == "Hàn Lập nói rằng.", (
        f"Un-wrapped source must produce unchanged output. Got {result.lines[0].text!r}"
    )


# ── Test 7: raw/opaque cues are skipped verbatim ─────────────────────────────


def test_raw_cue_skipped() -> None:
    """SubLine(raw='some karaoke block') is opaque → left verbatim, never re-wrapped (D-ENV-05)."""
    from trezarr.translate.engine import _preserve_source_envelopes
    from trezarr.subtitles.model import SubLine, SubDoc

    raw_line = SubLine(
        index="1",
        start_tc="00:00:01,000",
        end_tc="00:00:03,000",
        text="",
        raw="some karaoke block",
    )
    # Source line looks like a wrapped title card
    src_line = _make_line(1, text="(Episode Title)")

    # Build docs manually so raw is preserved
    trn_doc = SubDoc(
        lines=[raw_line],
        encoding="utf-8",
        line_ending="\n",
        separators=[],
        leading="",
        trailer="\n",
    )
    src_doc = _make_doc([src_line])

    result = _preserve_source_envelopes(trn_doc, src_doc, _settings())

    out = result.lines[0]
    assert out.raw == "some karaoke block", (
        f"Raw cue must be returned verbatim. Got raw={out.raw!r}"
    )
    # text should not have parens prepended
    assert not out.text.startswith("("), f"Raw cue must not be re-wrapped. Got text={out.text!r}"


# ── Test 8: gate compatibility — real validate_subdoc must not raise ──────────


def test_gate_compatibility() -> None:
    """Re-wrapped Vietnamese title card "(Phàm Nhân Tu Tiên Truyện)" passes real validate_subdoc.

    Verifies:
      - Check 10 (diacritics disqualify the source-passthrough branch): Vietnamese diacritics
        present in the re-wrapped text → the check correctly identifies it as translated, not
        an untranslated passthrough.
      - Check 12 (GLOSS_PAREN_RE / LATIN_DIACRITIC_RE): diacritic-bearing parens are exempt.

    Doc structure: 5 cues total.
      Cue 1: re-wrapped title card "(Phàm Nhân Tu Tiên Truyện)" (source: "(A Record...)")
      Cues 2-5: good Vietnamese text "Xin chào." (diacritic ratio = 5/5 = 1.0 → Check 3 passes)
    """
    from trezarr.translate.validate import validate_subdoc

    # Source doc: 5 cues with appropriate content
    src_lines = [
        _make_line(1, text="(A Record of Mortal's Journey to Immortality)"),
        _make_line(2, text="He said something."),
        _make_line(3, text="She replied."),
        _make_line(4, text="Then they left."),
        _make_line(5, text="The end."),
    ]
    # Translated doc: wrapped Vietnamese title card + 4 good VI cues.
    # "Được rồi." and "Thế giới." contain U+1EC3 (ề) / U+1EDD (ờ) / U+1EE3 (ợ) which are
    # confirmed Vietnamese diacritics (VN_DIACRITIC_RE range U+1E00–U+1EFF). This gives
    # a diacritic ratio of 5/5 = 1.0 ≥ 0.70 → Check 3 passes.
    trn_lines = [
        _make_line(1, text="(Phàm Nhân Tu Tiên Truyện)"),
        _make_line(2, text="Được rồi."),
        _make_line(3, text="Thế giới."),
        _make_line(4, text="Được rồi."),
        _make_line(5, text="Thế giới."),
    ]
    src_doc = _make_doc(src_lines)
    trn_doc = _make_doc(trn_lines)
    settings = _settings()

    # Must not raise GateError — diacritic-bearing parens are exempt from Check 12
    try:
        validate_subdoc(trn_doc, src_doc, settings)
    except Exception as exc:
        raise AssertionError(
            f"validate_subdoc raised {type(exc).__name__}: {exc}\n"
            f"Re-wrapped Vietnamese title card with diacritics must pass the gate "
            f"(Check 10 diacritic exemption + Check 12 LATIN_DIACRITIC_RE exemption)."
        ) from exc


# ── Test 9: flag off → complete no-op ────────────────────────────────────────


def test_flag_off_noop() -> None:
    """enable_envelope_preservation=False → function is a pure pass-through (D-ENV-08).

    The translated text keeps no parens even though the source was wrapped.
    """
    from trezarr.translate.engine import _preserve_source_envelopes

    src_line = _make_line(1, text="(Tập 142)")
    trn_line = _make_line(1, text="Tập 142")

    settings = _settings(enable_envelope_preservation=False)
    result = _preserve_source_envelopes(_make_doc([trn_line]), _make_doc([src_line]), settings)

    assert result.lines[0].text == "Tập 142", (
        f"With flag off, output must be unchanged. Got {result.lines[0].text!r}"
    )


# ── Test 10: two-parens form — depth closes before final char → skipped ───────


def test_two_parens_not_full_wrapper() -> None:
    """Source "(a) and (b)" — depth returns to 0 at index 2 (before final index 10) → SKIP.

    D-ENV-02 / Step B: the depth scan catches the "two groups share the same bracket type"
    pattern; these are NOT a single spanning envelope and must never be re-wrapped.
    """
    from trezarr.translate.engine import _preserve_source_envelopes

    src_line = _make_line(1, text="(a) and (b)")
    trn_line = _make_line(1, text="(a) và (b)")  # translated version also has two groups

    result = _preserve_source_envelopes(_make_doc([trn_line]), _make_doc([src_line]), _settings())

    expected = "(a) và (b)"
    assert result.lines[0].text == expected, (
        f"Two-group source must be left untouched. Got {result.lines[0].text!r}"
    )
    assert not result.lines[0].text.startswith("(("), (
        "Must NOT prepend extra opener to two-group source"
    )


# ── Test 11: envelope survives the Step-9 gate-repair loop (harness finding) ────


async def test_envelope_survives_gate_repair_loop(tmp_path: Path) -> None:
    """Harness finding: a repaired cue must ship WITH its source envelope.

    Scenario:
      - 5-cue SRT where cue 1 source is "(Tập 142)" (paren-wrapped title card).
      - Pass-3 translation for cue 1 returns "Tập 142" (no parens) — missing envelope.
      - Step 8.6 re-applies _preserve_source_envelopes → cue 1 becomes "(Tập 142)".
      - Cue 5 is still defective (HONORIFIC_CAPNAME_RE), so the gate fires, and
        _repair_failing_cues is called.  The repair returns a clean diacritic-bearing
        text for cue 5 — still WITHOUT parens on cue 1 (repair only touches cue 5).
      - The splice rebuilds translated_doc with the repaired lines.
      - WITHOUT the harness fix, _preserve_source_envelopes is NOT re-applied after the
        splice → the next validate_subdoc iteration sees cue 1 without parens, and if
        the gate later passes, the shipped cue 1 is unwrapped.
      - WITH the fix, _preserve_source_envelopes is re-applied immediately after the
        splice → the idempotency guard no-ops on all cues that already have envelopes,
        and cue 1 (which the repair left unwrapped) is re-wrapped.

    The test drives translate_file() with:
      - _repair_failing_cues patched to return a doc where cue 1 has LOST its envelope
        (simulating the splice gap) and cue 5 is now correctly repaired.
      - validate_subdoc patched to: first call raises GateError on cue 5 (triggering
        repair), second call passes (repair succeeded) — so the shipped doc is whatever
        comes out of the splice + optional re-application.

    Asserts: result.status == "done" AND the shipped .vi.srt cue 1 text starts with "("
    (envelope was re-applied after repair).

    Note: We drive translate_file() end-to-end because the fix is inside the repair loop
    in translate_file(), not in _preserve_source_envelopes itself. Patching the two
    internal collaborators (_repair_failing_cues and the LLM pass) is the lightest way to
    exercise the exact loop body without requiring a live LLM.
    """
    from unittest.mock import patch
    from trezarr.translate.engine import translate_file
    from trezarr.subtitles.model import SubLine

    # ── Build a 5-cue source SRT ──────────────────────────────────────────────
    # Cue 1: paren-wrapped title card.  Cues 2-5: plain English.
    src = tmp_path / "Show.S01E01.en.srt"
    src_cues = [
        "(Episode Title)",
        "Hello.",
        "World.",
        "Hello.",
        "Goodbye.",
    ]
    blocks = []
    for i, text in enumerate(src_cues, 1):
        start_ms = (i - 1) * 3000 + 1000
        end_ms = start_ms + 2000
        h, rem = divmod(start_ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        hs, rem2 = divmod(end_ms, 3_600_000)
        me, rem2 = divmod(rem2, 60_000)
        se, mse = divmod(rem2, 1000)
        blocks.append(
            f"{i}\n{h:02d}:{m:02d}:{s:02d},{ms:03d} --> "
            f"{hs:02d}:{me:02d}:{se:02d},{mse:03d}\n{text}"
        )
    src.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

    quarantine_dir = tmp_path / "quarantine"
    settings = _settings(
        translate_quarantine_dir=str(quarantine_dir),
        translate_batch_retry_attempts=1,
        enable_gate_repair=True,
        gate_repair_max_attempts=3,
        enable_pass1_analysis=False,
        enable_attribution=False,
        enable_self_review=False,
        enable_envelope_preservation=True,
    )

    # ── Fake LLM: Pass-3 returns cue 1 WITHOUT parens (LLM drops it) ────────
    # (Pass-3 is the only LLM call when pass1/attribution/self_review are off)
    # Cue 1 also carries the HONORIFIC_CAPNAME_RE defect so the gate fires on it,
    # making it land in failing_indices — the exact scenario the harness found.
    _good_vi = ["Được rồi.", "Thế giới.", "Được rồi.", "Thế giới."]
    # Cue 1: missing parens AND has honorific defect → Step 8.6 re-wraps it,
    # but then the gate fires on the honorific and _repair_failing_cues re-translates
    # cue 1 — returning a CLEAN diacritic-bearing text still WITHOUT parens.
    _defective_title = "Miss Episode Title"  # HONORIFIC_CAPNAME_RE: "Miss" + CapName

    async def _fake_llm_call(messages: list, response_model=None, model=None) -> str:
        return (
            f"[1] {_defective_title}\n"
            f"[2] {_good_vi[0]}\n"
            f"[3] {_good_vi[1]}\n"
            f"[4] {_good_vi[2]}\n"
            f"[5] {_good_vi[3]}"
        )

    from trezarr.llm.client import LLMClient

    client = LLMClient(settings)

    # ── Fake _repair_failing_cues: re-translates cue 1 WITHOUT parens ────────
    # This is the crux of the bug: the repair returns a clean Vietnamese text
    # for cue 1 (the honorific defect fixed) but the LLM again drops the parens.
    # The splice builds a new translated_doc — WITHOUT calling _preserve_source_envelopes.
    # Without the fix, the shipped cue 1 is "Tiêu đề tập" (no envelope).
    _repair_called = False

    async def _fake_repair(
        failing_indices,
        source_doc,
        translated_doc,
        check_number,
        llm_client,
        settings,
        glossary_lines,
        register_value,
        resolved_map,
        bible,
        model,
        flat_attributions=None,
        name_to_char_id=None,
    ):
        nonlocal _repair_called
        _repair_called = True
        repaired = []
        for i, line in enumerate(translated_doc.lines):
            if i in failing_indices:
                # Repair returns a clean diacritic-bearing translation — WITHOUT parens.
                # This is the exact gap: the LLM re-translates and drops the envelope again.
                repaired.append(
                    SubLine(
                        index=line.index,
                        start_tc=line.start_tc,
                        end_tc=line.end_tc,
                        text="Tiêu đề tập",  # valid VI (ê/ề = U+1EBF), no honorific, NO parens
                        raw=None,
                    )
                )
            else:
                repaired.append(
                    SubLine(
                        index=line.index,
                        start_tc=line.start_tc,
                        end_tc=line.end_tc,
                        text=line.text,
                        raw=line.raw,
                    )
                )
        return repaired

    with patch("trezarr.translate.engine._repair_failing_cues", side_effect=_fake_repair):
        with patch.object(client, "call", side_effect=_fake_llm_call):
            result = await translate_file(src, settings, client, FakeLedger())

    assert result.status == "done", (
        f"Expected status='done' after repair, got {result.status!r}\n"
        f"(repair_called={_repair_called})"
    )

    # Read the shipped .vi.srt and check cue 1 has the envelope restored.
    vi_path = src.parent / "Show.S01E01.vi.srt"
    assert vi_path.exists(), f"Expected .vi.srt to be written at {vi_path}"
    content = vi_path.read_text(encoding="utf-8")
    # The first subtitle block's text should start with "(" — envelope re-applied.
    # SRT block: index line, timecode line, then text line(s).
    # Find the text line of cue 1 (third non-empty line in first block).
    first_block = content.split("\n\n")[0]
    text_lines = first_block.strip().split("\n")[2:]  # skip index + timecode
    cue1_text = "\n".join(text_lines)
    assert cue1_text.startswith("("), (
        f"Cue 1 must be paren-wrapped after gate-repair re-application. "
        f"Got: {cue1_text!r}\n"
        f"(Without the harness fix, the repaired splice drops the envelope.)"
    )
    assert cue1_text.endswith(")"), (
        f"Cue 1 must end with ')' after gate-repair re-application. Got: {cue1_text!r}"
    )


class FakeLedger:
    """In-memory ledger stub for envelope-preservation tests."""

    def __init__(self) -> None:
        self._entries: dict = {}

    @staticmethod
    def content_hash(data: bytes) -> str:
        import hashlib

        return hashlib.sha256(data).hexdigest()

    async def check(self, source_path: str):
        return self._entries.get(source_path)

    async def check_by_output_path(self, output_path: str):
        return None

    async def record(self, entry) -> None:
        self._entries[entry.source_path] = entry
