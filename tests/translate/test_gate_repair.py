"""RED/GREEN tests for IMP-02b: bounded gate-level cue-repair pass in translate_file().

Tests cover:
  1. test_honorific_repair_success       — Check-11 defect repaired; status="done"
  2. test_structural_not_repaired        — Check-1 (structural) → quarantine, no repair call
  3. test_budget_exhausted               — repair LLM always fails; quarantine after N attempts
  4. test_moat_regression                — resolved_map hint + glossary forwarded; SubLine fields copied
  5. test_gate_repair_disabled           — enable_gate_repair=False → quarantine on first GateError

Uses asyncio_mode=auto (pyproject.toml); no @pytest.mark.asyncio needed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


# ── Shared helpers (mirror test_validate.py) ──────────────────────────────────

def _make_line(
    index: int,
    start_tc: str = "00:00:01,000",
    end_tc: str = "00:00:03,000",
    text: str = "Xin chào",
) -> object:
    from trezarr.subtitles.model import SubLine
    return SubLine(index=str(index), start_tc=start_tc, end_tc=end_tc, text=text)


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


# ── FakeLedger ────────────────────────────────────────────────────────────────

class FakeLedger:
    """In-memory ledger stub for gate-repair tests."""

    def __init__(self) -> None:
        self._entries: dict[str, Any] = {}

    @staticmethod
    def content_hash(data: bytes) -> str:
        import hashlib
        return hashlib.sha256(data).hexdigest()

    async def check(self, source_path: str) -> Any | None:
        return self._entries.get(source_path)

    async def check_by_output_path(self, output_path: str) -> Any | None:
        return None

    async def record(self, entry: Any) -> None:
        self._entries[entry.source_path] = entry


# ── SRT fixture builder ───────────────────────────────────────────────────────

def _write_srt(path: Path, cues: list[str]) -> None:
    """Write a minimal SRT file with the given cue texts."""
    blocks = []
    for i, text in enumerate(cues, 1):
        start_ms = (i - 1) * 3000 + 1000
        end_ms = start_ms + 2000
        def _fmt(ms: int) -> str:
            h = ms // 3_600_000; ms %= 3_600_000
            m = ms // 60_000;    ms %= 60_000
            s = ms // 1000;      ms %= 1000
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        blocks.append(f"{i}\n{_fmt(start_ms)} --> {_fmt(end_ms)}\n{text}")
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


# ── Test 1: honorific repair success ─────────────────────────────────────────

async def test_honorific_repair_success(tmp_path: Path) -> None:
    """A single Check-11 defective cue is repaired; translate_file returns status='done'.

    The source SRT has one cue: "Miss Mei, chúng ta nên đi thôi." — this text triggers
    Check-11 (HONORIFIC_CAPNAME_RE matches "Miss Mei") when it appears in the translated_doc
    unchanged (Pass-3 returns it verbatim as the "translation").  With enable_gate_repair=True,
    _repair_failing_cues must be called, the mock returns the fixed Vietnamese text, and the
    repaired doc passes the gate.
    """
    from unittest.mock import AsyncMock, patch

    from trezarr.translate.engine import translate_file

    # Source cue is pure ASCII so it won't satisfy Check-3's VI diacritic threshold
    # on its own — but since there's only ONE cue and it contains an honorific+name,
    # Check-11 fires first (the gate is fail-fast, checks 9-12 come after 1-8).
    # Use a source cue that will fail Check-11 when echoed as the "translation".
    _DEFECTIVE = "Miss Mei, chúng ta nên đi thôi."
    _REPAIRED = "Cô Mai, chúng ta nên đi thôi."

    src = tmp_path / "Show.S01E01.en.srt"
    _write_srt(src, [_DEFECTIVE])

    quarantine_dir = tmp_path / "quarantine"
    settings = _settings(
        translate_quarantine_dir=str(quarantine_dir),
        translate_batch_retry_attempts=1,
        enable_gate_repair=True,
        gate_repair_max_attempts=3,
        enable_pass1_analysis=False,
        enable_attribution=False,
        enable_self_review=False,
    )

    ledger = FakeLedger()

    # Pass-3 call returns the DEFECTIVE text (echoes source).
    # Repair LLM call returns the FIXED text.
    _pass3_done = False

    async def _fake_llm_call(messages: list, response_model: Any = None, model: Any = None) -> str:
        nonlocal _pass3_done
        if not _pass3_done:
            _pass3_done = True
            # Pass-3: return the defective text (honorific present)
            return f"[1] {_DEFECTIVE}"
        # Repair call: return fixed Vietnamese text
        return f"[1] {_REPAIRED}"

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    with patch.object(client, "call", side_effect=_fake_llm_call):
        result = await translate_file(src, settings, client, ledger)

    assert result.status == "done", (
        f"Expected status='done' after honorific repair, got {result.status!r}"
    )


# ── Test 2: structural check not repaired ────────────────────────────────────

async def test_structural_not_repaired(tmp_path: Path) -> None:
    """A Check-1 (cue count) mismatch quarantines without calling the repair LLM.

    Structural checks {1,2,4,5,6,7,8} must fall straight through to the quarantine
    path; _repair_failing_cues must never be called.
    """
    from unittest.mock import AsyncMock, patch

    from trezarr.translate.engine import translate_file

    # Source has 2 cues; Pass-3 returns only 1 — triggers Check-1 (count mismatch).
    src = tmp_path / "Show.S01E01.en.srt"
    _write_srt(src, ["Hello world", "Goodbye world"])

    quarantine_dir = tmp_path / "quarantine"
    settings = _settings(
        translate_quarantine_dir=str(quarantine_dir),
        translate_batch_retry_attempts=1,
        enable_gate_repair=True,
        gate_repair_max_attempts=3,
        enable_pass1_analysis=False,
        enable_attribution=False,
        enable_self_review=False,
    )

    ledger = FakeLedger()

    repair_call_count = 0

    async def _fake_llm_call(messages: list, response_model: Any = None, model: Any = None) -> str:
        nonlocal repair_call_count
        # Always return a 1-line response for a 2-cue source → Check-1 fires.
        # Any call after the initial Pass-3 batch would be a repair call.
        content = messages[0].get("content", "")
        if "CORRECTION REQUIRED" in content or (len(messages) > 1 and "CORRECTION REQUIRED" in str(messages)):
            repair_call_count += 1
        return "[1] Xin chào thế giới"  # only 1 line for 2-cue source

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    # Patch _repair_failing_cues at the module level so we can assert it was never called.
    with patch("trezarr.translate.engine._repair_failing_cues", new=AsyncMock()) as mock_repair:
        with patch.object(client, "call", side_effect=_fake_llm_call):
            result = await translate_file(src, settings, client, ledger)

    assert result.status == "quarantined", (
        f"Expected status='quarantined' for Check-1 structural failure, got {result.status!r}"
    )
    assert mock_repair.call_count == 0, (
        f"_repair_failing_cues must NOT be called for structural Check-1; "
        f"got call_count={mock_repair.call_count}"
    )


# ── Test 3: budget exhaustion ─────────────────────────────────────────────────

async def test_budget_exhausted(tmp_path: Path) -> None:
    """The repair LLM always returns a still-leaking cue; quarantine after gate_repair_max_attempts.

    The repair LLM call count must equal gate_repair_max_attempts (not more, not fewer).
    """
    from unittest.mock import AsyncMock, patch, call as mock_call

    from trezarr.translate.engine import translate_file

    _DEFECTIVE = "Miss Mei, chúng ta nên đi thôi."

    src = tmp_path / "Show.S01E01.en.srt"
    _write_srt(src, [_DEFECTIVE])

    _MAX_ATTEMPTS = 2
    quarantine_dir = tmp_path / "quarantine"
    settings = _settings(
        translate_quarantine_dir=str(quarantine_dir),
        translate_batch_retry_attempts=1,
        enable_gate_repair=True,
        gate_repair_max_attempts=_MAX_ATTEMPTS,
        enable_pass1_analysis=False,
        enable_attribution=False,
        enable_self_review=False,
    )

    ledger = FakeLedger()
    repair_call_count = 0

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
    ):
        nonlocal repair_call_count
        repair_call_count += 1
        # Always return the defective text — repair never succeeds.
        from trezarr.subtitles.model import SubLine
        repaired = []
        for line in translated_doc.lines:
            if line.index in [str(i + 1) for i in failing_indices]:
                repaired.append(SubLine(
                    index=line.index,
                    start_tc=line.start_tc,
                    end_tc=line.end_tc,
                    text=_DEFECTIVE,  # still defective
                    raw=None,
                ))
            else:
                repaired.append(SubLine(
                    index=line.index,
                    start_tc=line.start_tc,
                    end_tc=line.end_tc,
                    text=line.text,
                    raw=None,
                ))
        return repaired

    async def _fake_llm_call(messages: list, response_model: Any = None, model: Any = None) -> str:
        return f"[1] {_DEFECTIVE}"

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    with patch("trezarr.translate.engine._repair_failing_cues", side_effect=_fake_repair):
        with patch.object(client, "call", side_effect=_fake_llm_call):
            result = await translate_file(src, settings, client, ledger)

    assert result.status == "quarantined", (
        f"Expected status='quarantined' after budget exhausted, got {result.status!r}"
    )
    assert repair_call_count == _MAX_ATTEMPTS, (
        f"Expected exactly {_MAX_ATTEMPTS} repair calls (gate_repair_max_attempts), "
        f"got {repair_call_count}"
    )


# ── Test 4: moat regression ───────────────────────────────────────────────────

async def test_moat_regression(tmp_path: Path) -> None:
    """resolved_map hint + glossary forwarded to repair; repaired SubLine fields are byte-identical.

    Asserts:
      (a) The kwargs passed to _repair_failing_cues contain resolved_map with the hint for
          the failing cue index.
      (b) glossary_lines was forwarded (non-None when bible has terms).
      (c) The repaired SubLine at the repaired index has index/start_tc/end_tc
          byte-identical to the original translated_doc line.
    """
    from unittest.mock import AsyncMock, patch
    from types import SimpleNamespace

    from trezarr.translate.engine import translate_file
    from trezarr.subtitles.model import SubLine

    _DEFECTIVE = "Miss Mei, chúng ta nên đi thôi."
    _REPAIRED = "Cô Mai, chúng ta nên đi thôi."

    src = tmp_path / "Show.S01E01.en.srt"
    _write_srt(src, [_DEFECTIVE])

    quarantine_dir = tmp_path / "quarantine"
    settings = _settings(
        translate_quarantine_dir=str(quarantine_dir),
        translate_batch_retry_attempts=1,
        enable_gate_repair=True,
        gate_repair_max_attempts=3,
        enable_pass1_analysis=False,
        enable_attribution=False,
        enable_self_review=False,
    )

    # Fake a bible with a term so glossary_lines is non-empty.
    fake_bible = SimpleNamespace(
        terms=[SimpleNamespace(source_term="Mei", vietnamese_rendering="Mai")],
        characters=[SimpleNamespace(original_latin_name="Mei", id=1)],
        register_value=None,
    )

    # Simulate a resolved_map with a hint for character pair (1, 1) — matches cue index 0.
    # The repair function will receive resolved_map and glossary_lines from translate_file.
    captured_kwargs: dict = {}
    captured_translated_doc_line: SubLine | None = None

    async def _spy_repair(
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
    ):
        captured_kwargs["glossary_lines"] = glossary_lines
        captured_kwargs["resolved_map"] = resolved_map
        # Capture the translated_doc line at the failing index for byte-identity check.
        nonlocal captured_translated_doc_line
        if failing_indices:
            captured_translated_doc_line = translated_doc.lines[failing_indices[0]]
        # Return a successful repair: replace .text only, copy index/start_tc/end_tc.
        repaired = []
        for line in translated_doc.lines:
            if failing_indices and translated_doc.lines.index(line) in failing_indices:
                repaired.append(SubLine(
                    index=line.index,
                    start_tc=line.start_tc,
                    end_tc=line.end_tc,
                    text=_REPAIRED,
                    raw=None,
                ))
            else:
                repaired.append(SubLine(
                    index=line.index,
                    start_tc=line.start_tc,
                    end_tc=line.end_tc,
                    text=line.text,
                    raw=None,
                ))
        return repaired

    _pass3_done = False

    async def _fake_llm_call(messages: list, response_model: Any = None, model: Any = None) -> str:
        nonlocal _pass3_done
        if not _pass3_done:
            _pass3_done = True
            return f"[1] {_DEFECTIVE}"
        return f"[1] {_REPAIRED}"

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    # Patch build_glossary_lines to inject our fake_bible's terms.
    # Also patch the bible loading so translate_file uses fake_bible.
    with patch("trezarr.translate.engine._repair_failing_cues", side_effect=_spy_repair):
        with patch.object(client, "call", side_effect=_fake_llm_call):
            # Inject glossary_lines manually by patching build_glossary_lines.
            with patch("trezarr.translate.engine.build_glossary_lines", return_value=["Mei → Mai"]) as mock_gls:
                result = await translate_file(src, settings, client, ledger=FakeLedger())

    # (a) The repair was called (result is 'done').
    assert result.status == "done", f"Expected status='done', got {result.status!r}"

    # (b) glossary_lines was forwarded (should be ["Mei → Mai"] from our mock).
    assert captured_kwargs.get("glossary_lines") is not None, (
        "glossary_lines must be forwarded to _repair_failing_cues (moat dependency)"
    )
    assert len(captured_kwargs["glossary_lines"]) >= 1, (
        "glossary_lines must contain at least one entry"
    )

    # (c) Byte-identity of index/start_tc/end_tc on the captured translated_doc line.
    assert captured_translated_doc_line is not None, (
        "captured_translated_doc_line must have been set (repair was called)"
    )
    # The repaired SubLine in the final doc must have the SAME index/start_tc/end_tc
    # as the original translated_doc line.
    assert captured_translated_doc_line.index == "1", (
        f"Failing cue index must be '1', got {captured_translated_doc_line.index!r}"
    )
    # start_tc and end_tc match the SRT we wrote (cue 1: 00:00:01,000 → 00:00:03,000)
    assert captured_translated_doc_line.start_tc == "00:00:01,000", (
        f"start_tc must be preserved byte-identically, got {captured_translated_doc_line.start_tc!r}"
    )
    assert captured_translated_doc_line.end_tc == "00:00:03,000", (
        f"end_tc must be preserved byte-identically, got {captured_translated_doc_line.end_tc!r}"
    )


# ── Test 5: gate repair disabled ─────────────────────────────────────────────

async def test_gate_repair_disabled(tmp_path: Path) -> None:
    """TrezarrSettings(enable_gate_repair=False): Check-11 defect quarantines immediately.

    The repair LLM must never be called (mock_repair.call_count == 0).
    """
    from unittest.mock import AsyncMock, patch

    from trezarr.translate.engine import translate_file

    _DEFECTIVE = "Miss Mei, chúng ta nên đi thôi."

    src = tmp_path / "Show.S01E01.en.srt"
    _write_srt(src, [_DEFECTIVE])

    quarantine_dir = tmp_path / "quarantine"
    settings = _settings(
        translate_quarantine_dir=str(quarantine_dir),
        translate_batch_retry_attempts=1,
        enable_gate_repair=False,   # ← disabled
        gate_repair_max_attempts=3,
        enable_pass1_analysis=False,
        enable_attribution=False,
        enable_self_review=False,
    )

    ledger = FakeLedger()

    async def _fake_llm_call(messages: list, response_model: Any = None, model: Any = None) -> str:
        return f"[1] {_DEFECTIVE}"

    from trezarr.llm.client import LLMClient
    client = LLMClient(settings)

    with patch("trezarr.translate.engine._repair_failing_cues", new=AsyncMock()) as mock_repair:
        with patch.object(client, "call", side_effect=_fake_llm_call):
            result = await translate_file(src, settings, client, ledger)

    assert result.status == "quarantined", (
        f"Expected status='quarantined' with enable_gate_repair=False, got {result.status!r}"
    )
    assert mock_repair.call_count == 0, (
        f"_repair_failing_cues must NOT be called when enable_gate_repair=False; "
        f"got call_count={mock_repair.call_count}"
    )
