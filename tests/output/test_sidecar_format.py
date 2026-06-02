"""Sidecar naming tests for derive_vi_sidecar_path — ASS/SSA/VTT generalization (D-95).

The SRT regression guard (test_sidecar_naming_srt_unchanged) is concrete and must
pass GREEN immediately — derive_vi_sidecar_path already handles .srt.

ASS/SSA/VTT cases are marked xfail(strict=False) because the generalization lands
in Wave 3 (D-95: mirror source extension instead of hardcoding .vi.srt).

Covers:
  D-95 — derive_vi_sidecar_path(.ass) → .vi.ass (not .vi.srt)
  D-95 — derive_vi_sidecar_path(.ssa) → .vi.ssa (not .vi.srt)
  D-95 — derive_vi_sidecar_path(.vtt) → .vi.vtt (not .vi.srt)
  D-95 — derive_vi_sidecar_path(.srt) → .vi.srt (SRT regression guard)
"""
import pytest


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="derive_vi_sidecar_path .ass generalization (D-95) not yet implemented (Wave 3)",
)
def test_sidecar_naming_ass(tmp_path):
    """derive_vi_sidecar_path returns .vi.ass for an .ass source (D-95)."""
    write_mod = pytest.importorskip("trezarr.output.write")
    derive_vi_sidecar_path = write_mod.derive_vi_sidecar_path

    src = tmp_path / "Show.S01E01.en.ass"
    src.write_bytes(b"")  # content irrelevant for naming

    result = derive_vi_sidecar_path(src)

    assert result.suffix == ".ass", (
        f"Expected .ass suffix for ASS sidecar, got {result.suffix!r}"
    )
    assert result.name == "Show.S01E01.vi.ass", (
        f"Expected 'Show.S01E01.vi.ass', got {result.name!r}"
    )


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="derive_vi_sidecar_path .ssa generalization (D-95) not yet implemented (Wave 3)",
)
def test_sidecar_naming_ssa(tmp_path):
    """derive_vi_sidecar_path returns .vi.ssa for an .ssa source (D-95)."""
    write_mod = pytest.importorskip("trezarr.output.write")
    derive_vi_sidecar_path = write_mod.derive_vi_sidecar_path

    src = tmp_path / "Show.S01E01.ssa"
    src.write_bytes(b"")

    result = derive_vi_sidecar_path(src)

    assert result.suffix == ".ssa", (
        f"Expected .ssa suffix for SSA sidecar, got {result.suffix!r}"
    )
    assert result.name == "Show.S01E01.vi.ssa", (
        f"Expected 'Show.S01E01.vi.ssa', got {result.name!r}"
    )


@pytest.mark.xfail(
    raises=(ImportError, AssertionError, TypeError),
    strict=False,
    reason="derive_vi_sidecar_path .vtt generalization (D-95) not yet implemented (Wave 3)",
)
def test_sidecar_naming_vtt(tmp_path):
    """derive_vi_sidecar_path returns .vi.vtt for a .vtt source (D-95)."""
    write_mod = pytest.importorskip("trezarr.output.write")
    derive_vi_sidecar_path = write_mod.derive_vi_sidecar_path

    src = tmp_path / "Episode.S02E03.vtt"
    src.write_bytes(b"")

    result = derive_vi_sidecar_path(src)

    assert result.suffix == ".vtt", (
        f"Expected .vtt suffix for VTT sidecar, got {result.suffix!r}"
    )
    assert result.name == "Episode.S02E03.vi.vtt", (
        f"Expected 'Episode.S02E03.vi.vtt', got {result.name!r}"
    )


def test_sidecar_naming_srt_unchanged(tmp_path):
    """derive_vi_sidecar_path still returns .vi.srt for .srt source — SRT regression guard (D-95)."""
    write_mod = pytest.importorskip("trezarr.output.write")
    derive_vi_sidecar_path = write_mod.derive_vi_sidecar_path

    src = tmp_path / "Show.S01E01.en.srt"
    src.write_bytes(b"")

    result = derive_vi_sidecar_path(src)

    assert result.suffix == ".srt", (
        f"Expected .srt suffix for SRT sidecar (regression guard), got {result.suffix!r}"
    )
    assert result.name == "Show.S01E01.vi.srt", (
        f"Expected 'Show.S01E01.vi.srt' (regression guard), got {result.name!r}"
    )
