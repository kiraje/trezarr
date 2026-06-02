"""Format dispatcher — read_subtitle / write_subtitle keyed on file extension (D-94).

Supported extensions:
  .srt  → read_srt  / write_srt
  .ass  → read_ass  / write_ass
  .ssa  → read_ass  / write_ass  (SSA v4 uses the same codec as ASS)
  .vtt  → read_vtt  / write_vtt

An unknown extension raises ValueError before any file I/O (T-09-05-A allowlist).

Design decisions honoured:
  D-93  The dispatcher is the ONLY change in the call chain — batching, reconcile,
        attribute, analyze, and the 3-pass engine flow are untouched.
  D-94  Single suffix-keyed dict lookup replaces the two hardcoded read_srt /
        write_srt call sites in engine.py and output/write.py.
"""
from __future__ import annotations

from pathlib import Path

from .model import SubDoc
from .srt import read_srt, write_srt
from .ass import read_ass, write_ass
from .vtt import read_vtt, write_vtt

# ---------------------------------------------------------------------------
# Allowlist-based dispatch tables (T-09-05-A: only known safe suffixes).
# Unknown suffixes raise ValueError — no arbitrary file I/O from an untrusted
# extension string.
# ---------------------------------------------------------------------------

_READERS: dict[str, object] = {
    ".srt": read_srt,
    ".ass": read_ass,
    ".ssa": read_ass,
    ".vtt": read_vtt,
}

_WRITERS: dict[str, object] = {
    ".srt": write_srt,
    ".ass": write_ass,
    ".ssa": write_ass,
    ".vtt": write_vtt,
}


def read_subtitle(path: str | Path) -> SubDoc:
    """Read a subtitle file into a :class:`~trezarr.subtitles.model.SubDoc`.

    Dispatches to the appropriate codec based on the file extension (case-insensitive):
    ``.srt`` → :func:`~trezarr.subtitles.srt.read_srt`,
    ``.ass`` / ``.ssa`` → :func:`~trezarr.subtitles.ass.read_ass`,
    ``.vtt`` → :func:`~trezarr.subtitles.vtt.read_vtt`.

    Args:
        path: Path to the subtitle file (str or :class:`pathlib.Path`).

    Returns:
        A :class:`~trezarr.subtitles.model.SubDoc` with an appropriate envelope
        for the write-back codec.

    Raises:
        ValueError: If the file extension is not in the supported allowlist
                    (``.srt``, ``.ass``, ``.ssa``, ``.vtt``).
    """
    path = Path(path)
    reader = _READERS.get(path.suffix.lower())
    if reader is None:
        raise ValueError(f"Unsupported subtitle format: {path.suffix}")
    return reader(path)  # type: ignore[operator]


def write_subtitle(doc: SubDoc, path: str | Path) -> None:
    """Write a :class:`~trezarr.subtitles.model.SubDoc` to a subtitle file.

    Dispatches to the appropriate codec based on the file extension (case-insensitive):
    ``.srt`` → :func:`~trezarr.subtitles.srt.write_srt`,
    ``.ass`` / ``.ssa`` → :func:`~trezarr.subtitles.ass.write_ass`,
    ``.vtt`` → :func:`~trezarr.subtitles.vtt.write_vtt`.

    Args:
        doc:  The subtitle document to serialise. Must have the appropriate
              ``envelope`` set for ASS/VTT formats.
        path: Destination path for the subtitle file (str or :class:`pathlib.Path`).

    Raises:
        ValueError: If the file extension is not in the supported allowlist.
    """
    path = Path(path)
    writer = _WRITERS.get(path.suffix.lower())
    if writer is None:
        raise ValueError(f"Unsupported subtitle format: {path.suffix}")
    writer(doc, path)  # type: ignore[operator]
