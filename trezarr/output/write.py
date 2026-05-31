"""Atomic UTF-8 sidecar write with correct naming convention (D-19) and
PUID/PGID/UMASK permission application (D-29, INTG-04).

Design decisions honoured:
  D-19  Write to a NamedTemporaryFile in dest.parent (SAME filesystem as dest),
        then atomically rename via os.replace().  Crash before os.replace()
        leaves a .tmp file in dest.parent but never a partially-visible dest.
        Output is always UTF-8 regardless of the source SubDoc encoding.

  D-29  After write_vi_sidecar() returns, apply_permissions() applies PUID/PGID
        ownership and UMASK-derived file permissions in-process so the media
        server (Plex/Jellyfin/Bazarr) can read the sidecar even before the
        Phase-7 s6-overlay container init is in place. Constrain all writes to
        within configured media roots via paths.assert_within_media_roots()
        BEFORE calling apply_permissions (caller's responsibility — cli.py).

Asymmetry (per 03-REVIEWS.md MEDIUM #13):
  - chown PermissionError  → log warning + continue (process lacks CAP_CHOWN,
                              Phase-7 container init will fix this)
  - chmod OSError          → raise PermissionApplyError (item-level failure,
                              caller quarantines the item — chmod failure
                              directly threatens INTG-04 media-server
                              readability)

NEVER call the process-global umask syscall — that is unsafe in async code.
apply_permissions computes file_mode = 0o666 & ~umask per-call.

Sidecar naming:
  Input:  Show.S01E01.en.srt  →  Output:  Show.S01E01.vi.srt
  Input:  Show.S01E01.srt     →  Output:  Show.S01E01.vi.srt
  Rule: strip any 2-letter ISO-639 language-code suffix from the stem
  (e.g. ".en", ".ja", ".fr"), then append ".vi.srt".
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from trezarr.subtitles.model import SubDoc
from trezarr.subtitles.srt import write_srt

logger = logging.getLogger(__name__)


class PermissionApplyError(RuntimeError):
    """Raised when apply_permissions fails to apply chmod to a written sidecar.

    Per 03-REVIEWS.md MEDIUM #13: a chmod failure leaves the sidecar potentially
    unreadable to the media server, which directly violates INTG-04. The caller
    (cli.py) catches this and quarantines the item via n_quar++. Distinct from
    a chown failure, which is non-fatal (Phase-7 s6-overlay container init will
    correct ownership later).

    The asymmetry is intentional:
      - chown PermissionError = expected (Phase-3 has no CAP_CHOWN) → warn+continue.
      - chmod OSError         = breaks INTG-04 → escalate to PermissionApplyError.
    """

# Matches a 2-letter (case-insensitive) language code at the end of the stem,
# e.g. ".en", ".ja", ".fr", ".vi".  Used to strip the source language code
# before appending ".vi.srt" to form the sidecar name.
_LANG_CODE_RE = re.compile(r'\.[a-z]{2}$', re.IGNORECASE)


def derive_vi_sidecar_path(media_path: str | Path) -> Path:
    """Derive the Vietnamese sidecar path from a media (source SRT) path.

    Rules:
      - If the stem ends with a 2-letter language code (e.g. ".en"), strip it.
      - Append ".vi.srt" to form the sidecar name in the same directory.

    This is the single source of truth for sidecar naming — both write_vi_sidecar
    and translate_file must call this function so dest paths can never diverge.

    Args:
        media_path: Path to the source SRT file (str or Path).

    Returns:
        Path to the derived Vietnamese sidecar (e.g. Show.S01E01.vi.srt).
    """
    media_path = Path(media_path).resolve()
    stem = media_path.stem
    if _LANG_CODE_RE.search(stem):
        stem = stem.rsplit('.', 1)[0]
    return media_path.parent / (stem + '.vi.srt')


def write_vi_sidecar(doc: SubDoc, media_path: str | Path) -> Path:
    """Write a translated SubDoc as a Vietnamese sidecar SRT file atomically.

    The output file is always encoded as UTF-8 (D-19), regardless of the source
    SubDoc's encoding.  The write is atomic: a NamedTemporaryFile is written in
    the same directory as the destination (ensuring same filesystem for os.replace),
    then renamed to the final path in a single POSIX-atomic operation.  If any
    exception occurs before the rename, the temporary file is cleaned up and the
    destination is never created or overwritten.

    Args:
        doc:        The translated SubDoc to serialise.
        media_path: Path to the source SRT file (str or Path).  Used to derive
                    the output sidecar path (see module docstring for naming rules).

    Returns:
        Path to the written sidecar file (Show.S01E01.vi.srt).
    """
    dest = derive_vi_sidecar_path(media_path)

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix='.tmp',
            dir=dest.parent,    # MUST be same filesystem as dest (D-19, Pitfall 3)
            delete=False,
        ) as f:
            tmp_path = Path(f.name)

        # Force UTF-8 output regardless of source encoding (D-19)
        doc_out = SubDoc(
            lines=doc.lines,
            encoding='utf-8',
            line_ending=doc.line_ending,
            separators=doc.separators,
            leading=doc.leading,
            trailer=doc.trailer,
        )
        write_srt(doc_out, tmp_path)      # reuse Phase-1 serialiser
        os.replace(tmp_path, dest)        # POSIX-atomic rename
        tmp_path = None                   # prevent cleanup in finally
        return dest
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()             # cleanup on any failure before os.replace


def apply_permissions(path: Path, puid: int, pgid: int, umask: int) -> None:
    """Apply PUID/PGID ownership and UMASK-derived permissions to a written sidecar (D-29).

    Design decisions honoured:
      D-29  os.chown / os.chmod in-process; PermissionError on chown (EPERM)
            degrades to log-and-continue (Phase-7 s6-overlay container init
            will fix this). chmod failure raises PermissionApplyError because
            it directly threatens INTG-04 media-server readability (per
            03-REVIEWS.md MEDIUM #13).

    NEVER call the process-global umask syscall — it is unsafe in async code
    because it mutates global per-process state. file_mode is derived per-call
    as ``0o666 & ~umask`` (standard POSIX convention; with the default
    umask=0o022 the result is 0o644 rw-r--r--).

    PUID and PGID values of ``-1`` are POSIX no-ops for ``os.chown`` — they
    leave the existing ownership unchanged. This is the Phase-3 default when
    the operator has not configured PUID/PGID (the sidecar is owned by whatever
    user the daemon runs as, which is fine on macOS dev machines and gets
    fixed up by s6-overlay in Phase 7).

    Phase-3 caller invariant: ``paths.assert_within_media_roots`` MUST be
    called by cli.py on the resolved write target BEFORE apply_permissions
    fires. This module does NOT re-assert the guard; the path-traversal check
    lives at the orchestration boundary.

    Args:
        path: The path to the written sidecar (typically the return value of
              ``write_vi_sidecar``). Must already exist on disk.
        puid: POSIX user ID to chown to, or ``-1`` for "leave unchanged".
        pgid: POSIX group ID to chown to, or ``-1`` for "leave unchanged".
        umask: The umask value (int, e.g. ``0o022``). file_mode is computed
              as ``0o666 & ~umask`` and passed to ``os.chmod``.

    Raises:
        PermissionApplyError: when ``os.chmod`` fails. cli.py catches this and
            quarantines the item because the sidecar may not be readable to
            the media server, violating INTG-04.
    """
    try:
        os.chown(path, puid, pgid)
    except PermissionError:
        # Expected on Phase-3 macOS dev machines and any non-root deployment:
        # the process lacks CAP_CHOWN and cannot chown to an arbitrary UID.
        # The sidecar was written successfully; ownership will be corrected by
        # the Phase-7 s6-overlay container init at startup.
        logger.warning(
            "chown(%s, %d, %d) failed — process lacks CAP_CHOWN. "
            "File was written but ownership is not yet corrected. "
            "Phase 7 container init (s6-overlay) will fix this.",
            path, puid, pgid,
        )
    except OSError as exc:
        # Other chown errors (e.g. ENOENT — though path should exist by here)
        # are unexpected but still non-fatal for INTG-04 reach — log and move on.
        logger.warning("chown(%s) failed with unexpected error: %s", path, exc)

    file_mode = 0o666 & ~umask
    try:
        os.chmod(path, file_mode)
    except OSError as exc:
        # chmod failure → INTG-04 readability at risk. Raise PermissionApplyError
        # so the cli.py orchestration layer can quarantine the item rather than
        # silently leaving a potentially-unreadable sidecar in place.
        logger.error(
            "chmod(%s, %o) failed: %s — INTG-04 readability at risk; quarantining",
            path, file_mode, exc,
        )
        raise PermissionApplyError(
            f"chmod({path}, {file_mode:o}) failed: {exc}"
        ) from exc
