"""Tests for Phase 3 path-mapping layer (INTG-03 / D-23, D-24, D-29).

All imports from trezarr.paths and trezarr.config are deferred inside each test
function body to preserve the pytest.importorskip pattern used elsewhere in the
suite (collection succeeds even if a downstream wave hasn't landed yet).

Plan 03-02 removed all @pytest.mark.xfail(strict=False) markers from this file
after the trezarr/paths.py implementation landed (per 03-REVIEWS.md HIGH #3
xfail-removal policy).

Covers:
  INTG-03  apply_path_mapping():  prefix replace, no-match passthrough,
           trailing-slash normalization, longest-prefix wins
  D-29     assert_within_media_roots(): inside-root OK, outside-root raises,
           handles not-yet-existing sidecar paths (03-REVIEWS.md MEDIUM #9)
  D-24     probe_media_roots(): unreadable root → SystemExit, readable OK,
           non-writable root → WARNING but no exit (03-REVIEWS.md MEDIUM #8)
  D-29     assert_media_roots_configured(): empty path_mappings + *arr enabled
           → SystemExit at startup (03-REVIEWS.md HIGH #2)
  D-23     PathMapping / source_lang_priority defaults are NOT shared mutable
           state across TrezarrSettings() instances (03-REVIEWS.md HIGH #1)
"""
from __future__ import annotations

import os

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# apply_path_mapping — pure prefix substitution (D-23)
# ──────────────────────────────────────────────────────────────────────────────


def test_path_mapping_replaces_prefix():
    """apply_path_mapping replaces the remote prefix with the local prefix (D-23)."""
    paths_mod = pytest.importorskip("trezarr.paths")
    apply_path_mapping = paths_mod.apply_path_mapping
    PathMapping = paths_mod.PathMapping

    mappings = [PathMapping(remote="/tv", local="/data/media/tv")]
    result = apply_path_mapping("/tv/Show/S1/ep.mkv", mappings)
    assert str(result) == "/data/media/tv/Show/S1/ep.mkv", (
        f"Expected /data/media/tv/Show/S1/ep.mkv, got {result}"
    )


def test_path_mapping_no_match_passthrough():
    """When no mapping matches, apply_path_mapping returns the input path unchanged (D-23)."""
    paths_mod = pytest.importorskip("trezarr.paths")
    apply_path_mapping = paths_mod.apply_path_mapping
    PathMapping = paths_mod.PathMapping

    mappings = [PathMapping(remote="/tv", local="/data/media/tv")]
    result = apply_path_mapping("/movies/Film.mkv", mappings)
    assert str(result) == "/movies/Film.mkv", (
        f"Expected passthrough /movies/Film.mkv, got {result}"
    )


def test_path_mapping_strips_trailing_slash():
    """Trailing slashes on the remote prefix are stripped before comparison (Pitfall 3)."""
    paths_mod = pytest.importorskip("trezarr.paths")
    apply_path_mapping = paths_mod.apply_path_mapping
    PathMapping = paths_mod.PathMapping

    mappings = [PathMapping(remote="/tv/", local="/data/media/tv")]
    result = apply_path_mapping("/tv/Show/ep.mkv", mappings)
    assert str(result) == "/data/media/tv/Show/ep.mkv", (
        f"Expected /data/media/tv/Show/ep.mkv (trailing slash normalized), got {result}"
    )


def test_longest_prefix_wins():
    """When multiple remote prefixes match, the longest one wins (D-23 defensive choice).

    Without sorting, '/tv' shadows '/tv/anime' if listed first. apply_path_mapping
    must apply longest-prefix semantics regardless of input order.
    """
    paths_mod = pytest.importorskip("trezarr.paths")
    apply_path_mapping = paths_mod.apply_path_mapping
    PathMapping = paths_mod.PathMapping

    mappings = [
        PathMapping(remote="/tv", local="/data/tv"),
        PathMapping(remote="/tv/anime", local="/data/anime"),
    ]
    # '/tv/anime/Show/ep.mkv' should map via the longer prefix
    result = apply_path_mapping("/tv/anime/Show/ep.mkv", mappings)
    assert str(result) == "/data/anime/Show/ep.mkv", (
        f"Expected longest-prefix /data/anime/Show/ep.mkv to win, got {result}"
    )


def test_path_mapping_prefix_is_path_boundary():
    """A configured remote prefix MUST match on a path boundary — '/tv' does not match '/tvshow' (CR-01).

    Real *arr deployments (TRaSH-Guides setups) commonly have neighbouring roots
    like /tv and /tvshow-anime, or /data/movies and /data/movies-4k. A naked
    str.startswith would silently route a /tvshow path through the /tv mapping,
    landing the write target in the wrong directory. The path-boundary check
    (normalized == remote OR normalized starts with remote + "/") makes shadowed
    prefixes a passthrough instead.
    """
    paths_mod = pytest.importorskip("trezarr.paths")
    apply_path_mapping = paths_mod.apply_path_mapping
    PathMapping = paths_mod.PathMapping

    mappings = [PathMapping(remote="/tv", local="/data/tv")]
    # /tvshow must NOT match /tv — must passthrough unchanged
    result = apply_path_mapping("/tvshow/Foo.mkv", mappings)
    assert str(result) == "/tvshow/Foo.mkv", (
        f"Expected passthrough /tvshow/Foo.mkv (no path-boundary match), got {result}"
    )
    # Also assert that the exact-equality case still maps (boundary OR equality).
    result_exact = apply_path_mapping("/tv", mappings)
    assert str(result_exact) == "/data/tv", (
        f"Exact match must still map, got {result_exact}"
    )
    # And /tv/... still maps as before.
    result_child = apply_path_mapping("/tv/Show/ep.mkv", mappings)
    assert str(result_child) == "/data/tv/Show/ep.mkv", (
        f"Child path must still map under boundary semantics, got {result_child}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# assert_within_media_roots — path-traversal guard (D-29)
# ──────────────────────────────────────────────────────────────────────────────


def test_traversal_guard_raises_outside_roots(tmp_path):
    """Path outside all configured media roots raises ValueError (D-29, Pitfall 4)."""
    paths_mod = pytest.importorskip("trezarr.paths")
    assert_within_media_roots = paths_mod.assert_within_media_roots

    media_root = tmp_path / "media"
    media_root.mkdir()
    outside = tmp_path / "etc" / "passwd"
    outside.parent.mkdir()
    outside.write_text("not-a-sidecar", encoding="utf-8")

    with pytest.raises(ValueError, match="outside"):
        assert_within_media_roots(outside, [media_root])


def test_traversal_guard_allows_inside(tmp_path):
    """Path inside a configured media root does NOT raise (D-29)."""
    paths_mod = pytest.importorskip("trezarr.paths")
    assert_within_media_roots = paths_mod.assert_within_media_roots

    media_root = tmp_path / "media"
    media_root.mkdir()
    inside = media_root / "Show.S01E01.vi.srt"
    inside.write_text("1\n00:00:01,000 --> 00:00:03,000\nXin chào\n", encoding="utf-8")

    # Must not raise — path is inside media_root
    assert_within_media_roots(inside, [media_root])


def test_traversal_guard_handles_nonexistent_sidecar(tmp_path):
    """Traversal guard works for sidecar paths that don't exist yet (write target).

    The vi.srt sidecar is being written for the first time; Path.resolve() may
    behave differently on non-existent paths. Implementation should resolve()
    the parent directory and verify containment from there.
    """
    paths_mod = pytest.importorskip("trezarr.paths")
    assert_within_media_roots = paths_mod.assert_within_media_roots

    media_root = tmp_path / "media"
    media_root.mkdir()
    # File does NOT exist yet — but its parent does
    future_sidecar = media_root / "Show.S01E01.vi.srt"
    assert not future_sidecar.exists(), "precondition: sidecar does not exist yet"

    # Must not raise — the future write target is inside media_root
    assert_within_media_roots(future_sidecar, [media_root])


# ──────────────────────────────────────────────────────────────────────────────
# probe_media_roots — startup readability probe (D-24)
# ──────────────────────────────────────────────────────────────────────────────


def test_probe_unreadable_root_exits(tmp_path):
    """probe_media_roots exits non-zero on unreadable / missing root (D-24)."""
    paths_mod = pytest.importorskip("trezarr.paths")
    probe_media_roots = paths_mod.probe_media_roots

    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(SystemExit):
        probe_media_roots([nonexistent])


def test_probe_readable_root_passes(tmp_path):
    """probe_media_roots returns normally when every root is readable (D-24)."""
    paths_mod = pytest.importorskip("trezarr.paths")
    probe_media_roots = paths_mod.probe_media_roots

    media_root = tmp_path / "media"
    media_root.mkdir()

    # Must not raise — root exists, is a dir, is readable
    probe_media_roots([media_root])


def test_probe_warns_on_non_writable_root(tmp_path, caplog):
    """A readable but non-writable root logs a WARNING but the probe does not exit (INTG-04).

    INTG-04 requires sidecar writes; a non-writable media root is a soft-fail
    config issue worth warning about, but read-only mounts are sometimes
    intentional (e.g. mounting a remote NFS view-only for discovery). The probe
    distinguishes 'fatal: unreadable' from 'soft-fail: not writable'.
    """
    import logging

    paths_mod = pytest.importorskip("trezarr.paths")
    probe_media_roots = paths_mod.probe_media_roots

    ro_root = tmp_path / "ro_media"
    ro_root.mkdir()
    # Make the directory read-only (no write bit)
    original_mode = ro_root.stat().st_mode
    os.chmod(ro_root, 0o500)
    try:
        with caplog.at_level(logging.WARNING):
            # Must not raise — non-writable is a warning, not a fatal probe failure
            probe_media_roots([ro_root])
    finally:
        os.chmod(ro_root, original_mode)   # cleanup so tmp_path can be removed

    assert any("not writable" in rec.message.lower() for rec in caplog.records), (
        "Expected a WARNING log mentioning 'not writable' on a read-only media root"
    )


# ──────────────────────────────────────────────────────────────────────────────
# assert_media_roots_configured — refuse empty media roots when *arr enabled
# (03-REVIEWS.md HIGH #2 — empty media_roots silently disables D-29 traversal guard)
# ──────────────────────────────────────────────────────────────────────────────


def test_assert_media_roots_configured_refuses_when_empty_and_arr_enabled():
    """Empty path_mappings + sonarr/radarr_enabled → SystemExit at startup (D-29).

    Without any configured media roots, the traversal guard silently degrades
    to a no-op — D-29 is silently disabled. The startup helper must refuse to
    run when an *arr service is enabled but no media roots / path mappings are
    configured.
    """
    paths_mod = pytest.importorskip("trezarr.paths")
    assert_media_roots_configured = paths_mod.assert_media_roots_configured

    from trezarr.config import TrezarrSettings

    settings = TrezarrSettings(
        sonarr_enabled=True,
        sonarr_host="192.168.1.10",
        sonarr_api_key="dummy-key",
        path_mappings=[],   # empty — the failure condition
    )

    with pytest.raises(SystemExit):
        assert_media_roots_configured(settings)


# ──────────────────────────────────────────────────────────────────────────────
# Mutable-default isolation — Pydantic Field(default_factory=...) regression
# (03-REVIEWS.md HIGH #1)
# ──────────────────────────────────────────────────────────────────────────────


def test_path_mappings_no_shared_default_identity():
    """Two TrezarrSettings() instances must NOT share the same list object (D-23).

    A bare `path_mappings: list[PathMapping] = []` default is a classic mutable-
    default footgun in Pydantic v2: depending on copy semantics, two instances
    can end up referencing the same list. Use Field(default_factory=list).
    """
    from trezarr.config import TrezarrSettings

    s1 = TrezarrSettings()
    s2 = TrezarrSettings()
    assert s1.path_mappings is not s2.path_mappings, (
        "Two TrezarrSettings instances share the same path_mappings list — "
        "use Field(default_factory=list) instead of `= []`"
    )


def test_source_lang_priority_no_shared_default_identity():
    """source_lang_priority defaults must be per-instance, not a shared list (D-25)."""
    from trezarr.config import TrezarrSettings

    s1 = TrezarrSettings()
    s2 = TrezarrSettings()
    assert s1.source_lang_priority is not s2.source_lang_priority, (
        "Two TrezarrSettings instances share the same source_lang_priority list — "
        "use Field(default_factory=lambda: ['en']) instead of `= ['en']`"
    )
