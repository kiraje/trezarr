"""Test-only MediaItem factory previously hosted in ``trezarr.cli`` (WR-06).

Production ``_run_once`` constructs ``trezarr.arr.sonarr.MediaItem`` via
``discover_sonarr_items`` / ``discover_radarr_items`` — it never constructs the
cli-layer dataclass directly. Pre-WR-06 the cli-layer dataclass lived in
``trezarr.cli`` purely for the convenience of test stubs and was therefore
dead code in the production import graph: a maintainability hazard documented
in 03-REVIEW.md WR-06.

Moving the dataclass to a `_helpers` module makes the boundary explicit. The
``source_sub_path`` field stays here because some tests need a MediaItem-shaped
object that ALREADY carries a resolved source-subtitle path (i.e. constructed
by hand rather than the scan layer) — the production translate loop reads
``EligibleItem.source_sub_path``, not ``media_item.source_sub_path``, so this
field is exercised only by the test scaffolding.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class MediaItem:
    """A test-only MediaItem-shaped DTO used to drive ``_run_once`` and ``scan_for_eligible_items``.

    Production code constructs ``trezarr.arr.sonarr.MediaItem`` instead — the
    cli flow never instantiates this class. Keeping it under ``tests/_helpers``
    (rather than ``trezarr.cli``) makes that boundary obvious to the next
    contributor.

    Attributes:
        local_path: Resolved local filesystem path to the video file.
        source_sub_path: Resolved source-subtitle path; ``None`` if not yet
                         discovered (some tests fill this in by hand, others
                         leave it None and let scan_for_eligible_items
                         find it via the priority list).
        title: Display title for logging (series title or movie title).
        source_lang: ISO language code of the source sub, or None pre-scan.
    """

    local_path: Path
    source_sub_path: Path | None
    title: str
    source_lang: str | None
