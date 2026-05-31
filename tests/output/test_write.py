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


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3 RED stubs — apply_permissions() (INTG-04, D-29)
#
# apply_permissions(path, puid, pgid, umask) wraps os.chown + os.chmod after
# write_vi_sidecar() returns. Per 03-REVIEWS.md MEDIUM #13, a chmod failure
# escalates to PermissionApplyError (item-level failure), while a chown
# PermissionError logs a warning and continues (process lacks CAP_CHOWN is the
# expected Phase-3 case; Phase-7 s6-overlay fixes ownership later).
# ──────────────────────────────────────────────────────────────────────────────
from unittest.mock import patch  # noqa: E402  (deliberately after the legacy tests)


@pytest.mark.xfail(strict=False, reason="Plan 03-04: apply_permissions not yet implemented")
def test_apply_permissions_calls_chown_chmod(tmp_path):
    """apply_permissions(path, puid, pgid, umask) calls os.chown and os.chmod (D-29, INTG-04).

    Verifies the basic happy path: both syscalls fire with the expected arguments;
    chmod mode is computed as `0o666 & ~umask` (POSIX convention).
    """
    write_mod = pytest.importorskip("trezarr.output.write")
    apply_permissions = write_mod.apply_permissions

    sidecar = tmp_path / "Show.S01E01.vi.srt"
    sidecar.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    with patch("os.chown") as mock_chown, patch("os.chmod") as mock_chmod:
        apply_permissions(sidecar, puid=1000, pgid=1000, umask=0o022)

    assert mock_chown.called, "Expected os.chown to be called"
    chown_args = mock_chown.call_args[0]
    assert chown_args[1] == 1000 and chown_args[2] == 1000, (
        f"Expected chown(path, 1000, 1000), got {chown_args!r}"
    )

    assert mock_chmod.called, "Expected os.chmod to be called"
    chmod_args = mock_chmod.call_args[0]
    expected_mode = 0o666 & ~0o022   # 0o644
    assert chmod_args[1] == expected_mode, (
        f"Expected chmod mode {expected_mode:o}, got {chmod_args[1]:o}"
    )


@pytest.mark.xfail(strict=False, reason="Plan 03-04: apply_permissions not yet implemented")
def test_apply_permissions_chown_permission_error_continues(tmp_path):
    """os.chown raising PermissionError (no CAP_CHOWN) is logged and swallowed (D-29).

    Phase 3 runs without container init; non-root processes cannot chown to an
    arbitrary UID. The write succeeds; Phase-7 s6-overlay corrects ownership.
    apply_permissions MUST NOT raise on this expected condition.
    """
    write_mod = pytest.importorskip("trezarr.output.write")
    apply_permissions = write_mod.apply_permissions

    sidecar = tmp_path / "Show.S01E02.vi.srt"
    sidecar.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    with patch("os.chown", side_effect=PermissionError("EPERM")), patch("os.chmod") as mock_chmod:
        # Must not raise — chown failure is logged-and-continued
        apply_permissions(sidecar, puid=1000, pgid=1000, umask=0o022)

    # chmod must still be attempted after chown swallowed
    assert mock_chmod.called, "Expected os.chmod to be called even when chown fails"


@pytest.mark.xfail(
    strict=False,
    reason="Plan 03-04: PermissionApplyError + chmod-failure-escalates not yet implemented (03-REVIEWS.md MEDIUM #13)",
)
def test_apply_permissions_raises_PermissionApplyError_on_chmod_failure(tmp_path):
    """An os.chmod failure escalates to PermissionApplyError (item-level failure, INTG-04).

    Per 03-REVIEWS.md MEDIUM #13: a failed chmod can leave the sidecar unreadable
    by the media server, directly violating INTG-04 "media server can read them".
    Treat it as an item failure (quarantine in cli.py), not just a warning.
    """
    write_mod = pytest.importorskip("trezarr.output.write")
    apply_permissions = write_mod.apply_permissions
    PermissionApplyError = write_mod.PermissionApplyError

    sidecar = tmp_path / "Show.S01E03.vi.srt"
    sidecar.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    with patch("os.chmod", side_effect=OSError("read-only filesystem")):
        with pytest.raises(PermissionApplyError):
            apply_permissions(sidecar, puid=-1, pgid=-1, umask=0o022)
