"""RED test stubs for FMT-05: sidecar naming and atomic write in trezarr.output.write.

All imports from trezarr.output.write are deferred inside each test function body
so pytest collection succeeds even when the implementation module does not yet exist.
Tests skip cleanly via pytest.importorskip when the module is absent (Wave 0 / Wave 1).

Synchronous tests (file I/O, no async needed). Uses tmp_path pytest fixture.

Covers:
  FMT-05 — Sidecar naming: Show.S01E01.en.srt → Show.S01E01.vi.srt
  FMT-05 — Sidecar naming without lang code: Show.S01E01.srt → Show.S01E01.vi.srt
  FMT-05 — Atomic write: no .tmp file remains after completion
  FMT-05 — Output file bytes decode as valid UTF-8
"""
import pytest


def _make_minimal_doc(text: str = "Xin chào", encoding: str = "utf-8") -> object:
    """Helper: construct a minimal SubDoc with one line."""
    from trezarr.subtitles.model import SubDoc, SubLine
    line = SubLine(
        index="1",
        start_tc="00:00:01,000",
        end_tc="00:00:03,000",
        text=text,
    )
    return SubDoc(
        lines=[line],
        encoding=encoding,
        line_ending="\n",
        separators=[],
        leading="",
        trailer="\n",
    )


def test_sidecar_naming(tmp_path):
    """write_vi_sidecar derives Show.S01E01.vi.srt from Show.S01E01.en.srt (FMT-05)."""
    write_mod = pytest.importorskip("trezarr.output.write")
    write_vi_sidecar = write_mod.write_vi_sidecar

    src = tmp_path / "Show.S01E01.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    doc = _make_minimal_doc()
    dest = write_vi_sidecar(doc, src)

    assert dest == tmp_path / "Show.S01E01.vi.srt", (
        f"Expected dest = 'Show.S01E01.vi.srt', got {dest.name!r}"
    )
    assert dest.exists(), f"Expected output file to exist at {dest}"


def test_sidecar_naming_no_lang_code(tmp_path):
    """write_vi_sidecar derives Show.S01E01.vi.srt from Show.S01E01.srt (FMT-05).

    Source has no language code in stem — just strip .srt and append .vi.srt.
    """
    write_mod = pytest.importorskip("trezarr.output.write")
    write_vi_sidecar = write_mod.write_vi_sidecar

    src = tmp_path / "Show.S01E01.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    doc = _make_minimal_doc()
    dest = write_vi_sidecar(doc, src)

    assert dest == tmp_path / "Show.S01E01.vi.srt", (
        f"Expected dest = 'Show.S01E01.vi.srt' (no lang code in source), got {dest.name!r}"
    )
    assert dest.exists()


def test_atomic_write_crash_safety(tmp_path):
    """write_vi_sidecar creates the destination file; no .tmp file remains after completion (FMT-05)."""
    write_mod = pytest.importorskip("trezarr.output.write")
    write_vi_sidecar = write_mod.write_vi_sidecar

    src = tmp_path / "Episode.S02E03.en.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    doc = _make_minimal_doc()
    dest = write_vi_sidecar(doc, src)

    assert dest.exists(), f"Expected destination file to exist at {dest}"

    # No .tmp files should remain after successful write
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], (
        f"Expected no .tmp files after successful write, found: {[f.name for f in tmp_files]}"
    )


def test_utf8_output(tmp_path):
    """Output file bytes decode as valid UTF-8 even when source SubDoc encoding is latin-1 (FMT-05)."""
    write_mod = pytest.importorskip("trezarr.output.write")
    write_vi_sidecar = write_mod.write_vi_sidecar

    src = tmp_path / "Movie.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n", encoding="utf-8")

    # Source doc uses latin-1 encoding, but output must be UTF-8
    doc = _make_minimal_doc(text="Tôi yêu tiếng Việt", encoding="latin-1")
    dest = write_vi_sidecar(doc, src)

    assert dest.exists()
    raw_bytes = dest.read_bytes()

    # Must decode as valid UTF-8 without error
    try:
        decoded = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        pytest.fail(f"Output file is not valid UTF-8: {e}")

    assert "Tôi yêu tiếng Việt" in decoded, (
        f"Expected Vietnamese text in output, got {decoded!r}"
    )
