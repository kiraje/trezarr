"""Path-mapping layer: remote→local prefix substitution, startup probe, traversal guard.

Design decisions honoured:
  D-23  Path mapping = ordered remote→local find/replace pairs. Longest-prefix
        match (defensive choice, see 03-RESEARCH.md A2). Trailing slashes stripped
        on both remote prefix and incoming API path before comparison (Pitfall 3).
        Do NOT lowercase — Linux filesystems are case-sensitive.

  D-24  Fail-fast startup readability probe. Any unreadable (missing / non-dir /
        not R_OK|X_OK) configured local media root → sys.exit non-zero with a
        clear actionable error (03-REVIEWS.md MEDIUM #8). A readable-but-not-
        writable root is a WARNING only, not a fatal probe failure — PUID/PGID
        in Phase 7 may legitimately make host-side paths read-only at probe time.

  D-29  Path-traversal guard. assert_within_media_roots() must run on every
        resolved write target before any write. resolve(strict=False) so paths
        that do not yet exist (newly-written sidecars) resolve symbolically
        (03-REVIEWS.md MEDIUM #9). assert_media_roots_configured() refuses
        startup when path_mappings is empty AND any *arr discovery is enabled
        — otherwise the traversal guard silently degrades to a no-op
        (03-REVIEWS.md HIGH #2).

This module is stdlib-only (plus pydantic.BaseModel for PathMapping). It must
not import from trezarr.config so config.py can import PathMapping from here
without forming an import cycle (paths.py is the lower layer in the dep graph).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from pydantic import BaseModel

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

logger = logging.getLogger(__name__)


class PathMapping(BaseModel):
    """A remote→local path prefix substitution pair (D-23).

    Defined as a pydantic BaseModel (not a dataclass) so pydantic-settings can
    deserialize the JSON array env var `TREZARR_PATH_MAPPINGS` and YAML
    `path_mappings:` lists into a list[PathMapping] field on TrezarrSettings.

    Attributes:
        remote: Prefix as it appears in *arr API-returned paths (e.g. "/tv").
        local:  Corresponding local path in this container / host (e.g. "/data/tv").
    """

    remote: str
    local: str


def apply_path_mapping(api_path: str, mappings: Sequence[PathMapping]) -> Path:
    """Apply ordered remote→local path mappings to an API-returned path (D-23).

    Algorithm (per 03-RESEARCH.md Pattern 3 / Assumption A2):
      1. Strip a single trailing slash from both api_path and each mapping.remote
         before comparison (Pitfall 3 — *arr APIs are inconsistent about trailing
         slashes).
      2. Sort mappings by descending len(remote) so the LONGEST matching prefix
         wins. Without this, the user-ordered list could let a short prefix
         (e.g. "/tv") shadow a longer one (e.g. "/tv/anime").
      3. Return Path(local.rstrip("/") + suffix) on the first match.
      4. If no mapping matches, return Path(api_path) unchanged (passthrough).

    Do NOT lowercase — Linux filesystems are case-sensitive (Show.S01E01.mkv !=
    show.s01e01.mkv).

    Args:
        api_path: The path as returned by the *arr API (treated as untrusted
                  until path-mapped + validated via assert_within_media_roots).
        mappings: The configured list of remote→local prefix substitutions.

    Returns:
        Path object pointing at the local-side path, or passthrough Path(api_path)
        if no mapping matches.
    """
    normalized = api_path.rstrip("/")
    # Sort by descending remote length so the longest matching prefix wins
    # regardless of user-supplied ordering (defensive — see 03-RESEARCH.md A2).
    sorted_mappings = sorted(mappings, key=lambda m: len(m.remote.rstrip("/")), reverse=True)
    for mapping in sorted_mappings:
        remote = mapping.remote.rstrip("/")
        if normalized.startswith(remote):
            suffix = normalized[len(remote):]
            local_root = mapping.local.rstrip("/")
            return Path(local_root + suffix)
    return Path(api_path)


def assert_within_media_roots(resolved: Path, media_roots: Sequence[Path]) -> None:
    """Raise ValueError if resolved path escapes all configured media roots (D-29).

    This is the path-traversal guard — every write path must pass through this
    before any write or read. The set of allowed roots is the union of all
    `local` values from configured mappings (see build_media_roots).

    resolve(strict=False) is used so paths that do not yet exist (newly-written
    sidecar targets) resolve symbolically rather than raising FileNotFoundError
    (03-REVIEWS.md MEDIUM #9). This is critical because apply_permissions runs
    AFTER write_vi_sidecar writes the file, but assert_within_media_roots is
    called BEFORE the write completes in some code paths — the target file
    will not exist yet.

    Example:
        >>> from pathlib import Path
        >>> media_root = Path("/data/media")  # may not exist in this doctest
        >>> future_sidecar = media_root / "Show.S01E01.vi.srt"  # does NOT exist
        >>> # assert_within_media_roots(future_sidecar, [media_root])  # OK — no exception

    Args:
        resolved: The candidate path (typically the output of apply_path_mapping
                  followed by derive_vi_sidecar_path). May or may not exist yet.
        media_roots: The configured set of allowed write roots (typically the
                  deduplicated `local` values from settings.path_mappings).

    Raises:
        ValueError: when resolved is outside ALL of the configured media roots.
                    The message names the resolved path and the configured roots
                    so the misconfiguration is actionable.
    """
    resolved_abs = resolved.resolve(strict=False)
    for root in media_roots:
        try:
            resolved_abs.relative_to(root.resolve(strict=False))
            return  # inside this root — OK
        except ValueError:
            continue
    raise ValueError(
        f"Resolved path {resolved_abs} is outside all configured media roots "
        f"{[str(r) for r in media_roots]}. This may indicate a path-mapping "
        "misconfiguration or path-traversal attempt (D-29, Pitfall 4)."
    )


def build_media_roots(settings: "TrezarrSettings") -> list[Path]:
    """Build the deduplicated list of local media roots from configured path mappings.

    The result is what probe_media_roots() and assert_within_media_roots()
    consume. Currently the union is just the `local` side of every path mapping
    — there is no separate `media_roots` setting in Phase 3 (the planner kept
    the contract minimal; an explicit media_roots field can be added later if
    a passthrough-only deployment ever needs one).

    Args:
        settings: TrezarrSettings carrying the configured path_mappings.

    Returns:
        Deduplicated list of Path objects, order-preserved by first occurrence.
    """
    seen: set[str] = set()
    roots: list[Path] = []
    for mapping in settings.path_mappings:
        local = mapping.local.rstrip("/")
        if local not in seen:
            seen.add(local)
            roots.append(Path(local))
    return roots


def probe_media_roots(media_roots: Sequence[Path]) -> None:
    """Verify each configured media root is readable; sys.exit on hard failure (D-24).

    Mandatory checks (any failure → sys.exit):
      - root.exists()
      - root.is_dir()
      - os.access(root, os.R_OK | os.X_OK)   — needed to enter and list

    Soft check (failure → logger.warning, but probe still passes):
      - os.access(root, os.W_OK)             — sidecar writes will fail if absent,
                                                but PUID/PGID may legitimately make
                                                host-side paths read-only at probe
                                                time (Phase 7 container init lands
                                                later). Per 03-REVIEWS.md MEDIUM #8.

    Args:
        media_roots: The probe targets, typically the output of build_media_roots.

    Raises:
        SystemExit: when any root fails a mandatory check. The error message is
                    multi-line and names each bad root + a remediation hint
                    (verify your path_mappings and volume mounts match the
                    *arr stack).
    """
    errors: list[str] = []
    for root in media_roots:
        if not root.exists():
            errors.append(f"  {root}: does not exist")
            continue
        if not root.is_dir():
            errors.append(f"  {root}: not a directory")
            continue
        if not os.access(root, os.R_OK | os.X_OK):
            errors.append(f"  {root}: not readable+executable (check PUID/PGID or volume mount)")
            continue
        # Soft check — warn but do not fail
        if not os.access(root, os.W_OK):
            logger.warning(
                "media root %s is not writable; sidecar writes will fail until "
                "permissions are fixed (Phase 7 PUID/PGID may legitimately make "
                "this read-only at probe time)",
                root,
            )

    if errors:
        sys.exit(
            "ERROR: Trezarr cannot start — unreadable media root(s):\n"
            + "\n".join(errors)
            + "\nVerify your path_mappings and volume mounts match the *arr stack."
        )


def assert_media_roots_configured(settings: "TrezarrSettings") -> None:
    """Refuse startup when path_mappings is empty AND any *arr discovery is enabled (D-29).

    Per 03-REVIEWS.md HIGH #2: without any configured path_mappings, the set of
    allowed write roots (returned by build_media_roots) is EMPTY, which means
    assert_within_media_roots silently degrades to "no constraint" because the
    for-loop has nothing to iterate. That silently disables the D-29 traversal
    guard for a write-capable run. We must refuse startup in that case.

    Passes silently when:
      - path_mappings is non-empty (the guard is constrained — OK), OR
      - both sonarr_enabled and radarr_enabled are False (nothing will be
        discovered and nothing will be written — passthrough OK)

    cli.py (Plan 03-05) MUST call this BEFORE probe_media_roots so the empty-
    mappings case fails fast with an actionable message instead of silently
    becoming a no-op or surfacing as a downstream traversal failure.

    Args:
        settings: TrezarrSettings carrying path_mappings, sonarr_enabled, radarr_enabled.

    Raises:
        SystemExit: when path_mappings is empty AND at least one *arr is enabled.
    """
    arr_enabled = settings.sonarr_enabled or settings.radarr_enabled
    if not settings.path_mappings and arr_enabled:
        sys.exit(
            "ERROR: Trezarr cannot start — no path_mappings configured but at "
            "least one *arr discovery is enabled (sonarr_enabled or "
            "radarr_enabled). Per D-29, writes must be constrained to "
            "configured media roots; an empty media_roots set would silently "
            "disable the path-traversal guard. Configure TREZARR_PATH_MAPPINGS "
            "(JSON array env var) or path_mappings: in your config YAML, or "
            "disable sonarr_enabled/radarr_enabled."
        )
    if not settings.path_mappings and not arr_enabled:
        logger.info(
            "no media roots configured and no *arr discovery enabled — "
            "passthrough OK (nothing will be written)"
        )
