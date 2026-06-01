"""Source-subtitle filesystem scan and eligible-item collection.

Design decisions honoured:
  D-25  Filesystem source-sub scan with source-language priority list, default ["en"].
  D-26  Gap detection (delegated to gap.is_eligible) — foreign vi sidecars are NEVER
        clobbered; D-26 semantics live in gap.py, not here.
  D-28  Self-output exclusion via ledger provenance (gap.is_eligible handles this).

Limitation (Phase 3, per 03-REVIEWS.md MEDIUM #11): only matches
`{media_stem}.{lang}.srt` where {lang} is a 2 or 3-letter ISO code. Suffixed
variants such as `Show.S01E01.forced.srt` or `Show.S01E01.default.en.srt`
are NOT detected — those are Phase 10 (Bazarr integration, INTG-02) scope.

Per 03-REVIEWS.md MEDIUM #12: find_source_sub iterates the source-sub glob
in `sorted()` order so same-language collisions resolve deterministically
(lexicographically-first wins). Without this, two `.en.srt` candidates in the
same directory could produce different choices across runs depending on
filesystem iteration order.

Per 03-REVIEWS.md HIGH #5 + MEDIUM #14: scan_for_eligible_items returns a
typed `(list[EligibleItem], ScanStats)` tuple instead of a bare list of tuples
so cli.py's end-of-run summary can include the pre-translate skip counters
(no_source, foreign_vi, already_done), not just the post-translate counts.
"""
from __future__ import annotations

import glob as _glob
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from trezarr.output.ledger import Ledger

logger = logging.getLogger(__name__)

# Module-level compiled regex — matches `{stem}.{lang}.srt` where {lang} is a
# 2- or 3-letter ISO-639 code (per 03-RESEARCH.md Open Question 3 — Bazarr
# regularly emits 3-letter codes like "eng", "jpn", "kor"). Case-insensitive
# to handle the (rare) `.EN.SRT` variants. The first capture group is the
# stem (everything before the language token); the second is the language
# token itself.
_LANG_SIDECAR_RE = re.compile(r'^(.+?)\.([a-z]{2,3})\.srt$', re.IGNORECASE)


@dataclass(frozen=True)
class EligibleItem:
    """A media item that gap-detection determined needs translation.

    Per 03-REVIEWS.md HIGH #5: typed dataclass instead of a bare tuple, so the
    downstream CLI (Plan 03-05) has a stable contract for what scan returns.

    Attributes:
        media_item:      The MediaItem this eligibility decision was made for.
                         Typed as ``Any`` to avoid hard-coupling scan.py to the
                         arr discovery layer's MediaItem shape (the cli layer
                         will adapt arr.sonarr.MediaItem into its own
                         MediaItem on the way in).
        source_sub_path: The discovered source sidecar path (absolute or
                         tmp_path-relative in tests).
        reason:          Free-form gap.is_eligible reason string ("new item",
                         "source subtitle changed", etc.). Used for log output;
                         not parsed for control flow.
        source_lang:     The matched 2- or 3-letter language code (lower-cased),
                         e.g. "en", "zh", "eng". Used for downstream ledger
                         record source_lang field.
    """

    media_item: Any
    source_sub_path: Path
    reason: str
    source_lang: str


@dataclass
class ScanStats:
    """Counts of items examined during scan, broken down by skip reason.

    Per 03-REVIEWS.md MEDIUM #14: cli.py's end-of-run summary should report the
    pre-translate skip counters (no_source, foreign_vi, already_done) as well
    as the post-translate counts (translated, quarantined, failed). Without
    this typed counter struct, the pre-translate skips would be silently lost.

    WR-03: a sixth `error` counter was added because ``gap.is_eligible`` Case
    0's second branch (``"source subtitle unreadable: ..."``) is a true
    transient I/O error, not a missing-source skip — counting it as no_source
    would conflate the two failure modes in the end-of-run summary. The
    classifier in ``scan_for_eligible_items`` matches reason strings
    explicitly so silent string-drift won't drop counts into the unclassified
    bucket as it did pre-WR-03.

    Mutable dataclass (NOT frozen) so the scan loop can `stats.scanned += 1`
    in-place.

    Attributes:
        scanned:      Total MediaItems passed to scan_for_eligible_items().
        no_source:    Count where find_source_sub() returned None OR
                      gap.is_eligible reported ``"no source subtitle at ..."``
                      (TOCTOU between find_source_sub and is_eligible).
        foreign_vi:   Count blocked by D-26 — a foreign .vi.srt is present
                      and not in the ledger; we never clobber it.
        already_done: Count of items where the ledger says status=done AND
                      the source content_hash matches — D-27 idempotency.
        error:        Count where the source-subtitle file existed at
                      find_source_sub time but failed an I/O read inside
                      gap.is_eligible (``"source subtitle unreadable: ..."``).
                      Distinct from no_source so the summary can flag
                      transient I/O issues vs missing files.
    """

    scanned: int = 0
    no_source: int = 0
    foreign_vi: int = 0
    already_done: int = 0
    error: int = 0


def find_source_sub(media_path: Path, lang_priority: Sequence[str]) -> tuple[Path, str] | None:
    """Find the highest-priority source-language sidecar next to a media file (D-25).

    Algorithm:
      1. Glob ``{media_stem}.*.srt`` in ``media_path.parent`` (deterministic via
         ``sorted()`` — per 03-REVIEWS.md MEDIUM #12).
      2. For each candidate, match against _LANG_SIDECAR_RE; record the
         lower-cased language token. On same-language collision, the
         lexicographically-first candidate (after sort) wins.
      3. Iterate ``lang_priority`` in order; return the first language that has
         at least one candidate, as ``(path, lang)``.
      4. Return None if no priority-language candidate exists.

    Phase-3 limitation (per 03-REVIEWS.md MEDIUM #11): the glob pattern only
    catches ``{stem}.{lang}.srt`` — NOT suffixed variants like
    ``{stem}.forced.srt`` or ``{stem}.default.en.srt``. Phase 10 (Bazarr
    integration) will widen this with a properly-typed source-selector.

    Args:
        media_path: The video file path (Sonarr/Radarr-discovered + path-mapped).
                    Used only as the directory + stem source — the file itself
                    does not need to exist for this function to operate.
        lang_priority: Ordered list of language codes to try (lower- or upper-
                    case; matching is case-insensitive). Default Phase-3 value
                    is ``["en"]`` (D-25).

    Returns:
        ``(source_sub_path, lang)`` tuple on match, where ``lang`` is the
        lower-cased matched language token. Returns ``None`` if no priority-
        language candidate exists.
    """
    media_dir = media_path.parent
    media_stem = media_path.stem

    # Group all matching candidates by language. dict insertion order does NOT
    # govern selection — lang_priority order does — but within a language we
    # rely on `sorted()` to make the choice deterministic (MEDIUM #12).
    found: dict[str, list[Path]] = {}
    # CR-02: Path.glob interprets `[`, `]`, `*`, `?` as glob meta-characters,
    # which silently mis-matches common *arr filenames like `Show [2024].S01E01.mkv`
    # — the `[2024]` becomes a character class matching one of {2,0,4}. Escape
    # the stem via glob.escape so the literal stem is matched on the filesystem.
    escaped_stem = _glob.escape(media_stem)
    try:
        candidates = sorted(media_dir.glob(f"{escaped_stem}.*.srt"))
    except OSError as exc:
        # Directory unreadable / permission denied — log and treat as "no source".
        logger.warning("source-sub glob failed for %s: %s", media_dir, exc)
        return None

    for candidate in candidates:
        match = _LANG_SIDECAR_RE.match(candidate.name)
        if match is None:
            continue
        cand_stem, cand_lang = match.group(1), match.group(2).lower()
        # Defensive: glob `{stem}.*.srt` should only return paths whose
        # filename starts with `{media_stem}.`, but the regex's lazy stem
        # capture could over-match for stems containing dots. Re-check.
        if cand_stem != media_stem:
            continue
        found.setdefault(cand_lang, []).append(candidate)

    for lang in lang_priority:
        lang_key = lang.lower()
        if lang_key in found:
            paths = found[lang_key]
            if len(paths) > 1:
                logger.info(
                    "multiple %s candidates for %s; selecting lexicographically-first: %s",
                    lang_key, media_stem, paths[0],
                )
            return (paths[0], lang_key)

    return None


async def scan_for_eligible_items(
    items: Sequence[Any],
    ledger: "Ledger",
    lang_priority: Sequence[str],
) -> tuple[list[EligibleItem], ScanStats]:
    """Scan a list of MediaItems for translation eligibility (D-25, D-26, D-28).

    Per 03-REVIEWS.md HIGH #5 + MEDIUM #14: returns a typed
    ``(list[EligibleItem], ScanStats)`` tuple rather than a bare list of
    tuples — the typed dataclasses give the cli layer a stable shape and
    widen the end-of-run summary to include pre-translate skip counters.

    The signature uses keyword-friendly positional args ``items, ledger,
    lang_priority`` (matching the Wave-0 test contract — see
    tests/discover/test_scan.py::test_scan_returns_eligible_item_and_scan_stats).
    The plan's `<action>` block originally took a TrezarrSettings parameter;
    the contract was changed at the test-stub level to be more granular (one
    setting, not the whole settings object), which is the canonical Phase-3
    shape.

    Per-item flow:
      1. stats.scanned += 1.
      2. Use ``find_source_sub(item.local_path, lang_priority)`` to locate the
         best source sidecar. None ⇒ stats.no_source += 1; continue.
      3. Delegate to ``gap.is_eligible(source_sub_path, ledger)``. The import
         is done inside the function to avoid a module-load-order cycle (gap
         imports from output.write, which is fine; scan does NOT need to
         import gap at module load).
      4. If not eligible, classify the reason for stats:
           - "foreign" in reason ⇒ stats.foreign_vi += 1
           - "already translated" in reason ⇒ stats.already_done += 1
           - other False reasons (e.g. "no source") are counted as no_source
             via the find_source_sub None branch already; they should not
             surface from is_eligible in normal flow.
      5. Otherwise append an EligibleItem to the result list.

    Args:
        items:         Iterable of MediaItem-shaped objects with ``.local_path:
                       Path``. The MediaItem type is intentionally untyped here
                       (``Any``) so scan.py is decoupled from the arr discovery
                       layer's MediaItem shape (the cli layer adapts between
                       arr.sonarr.MediaItem and its own MediaItem on the way in).
        ledger:        The ``Ledger`` instance used by ``gap.is_eligible`` to
                       resolve D-27 idempotency (source-hash compare) and D-28
                       self-output exclusion (provenance-based skip).
        lang_priority: Ordered list of source-language codes, e.g. ``["en"]``
                       (D-25 default). Passed through to find_source_sub.

    Returns:
        ``(list[EligibleItem], ScanStats)`` — the eligible items the caller
        should translate, and a typed counter struct of skip reasons for the
        end-of-run summary.
    """
    # Lazy import to keep module-load-time dependency graph minimal — gap
    # imports from output.write and output.ledger; scan does not need to
    # carry that surface at import time.
    from trezarr.discover.gap import is_eligible

    eligible: list[EligibleItem] = []
    stats = ScanStats()

    for item in items:
        stats.scanned += 1

        src = find_source_sub(item.local_path, lang_priority)
        if src is None:
            stats.no_source += 1
            logger.info(
                "no source sub found for %s (lang_priority=%s)",
                item.local_path, list(lang_priority),
            )
            continue

        source_sub_path, source_lang = src
        ok, reason = await is_eligible(source_sub_path, ledger)

        if not ok:
            # WR-03: explicitly classify each is_eligible False reason so a
            # silent reason-string drift cannot drop counts into the
            # unclassified bucket. Pre-WR-03, "no source subtitle at ..." and
            # "source subtitle unreadable: ..." both fell through to the
            # default INFO log and were NOT counted in any ScanStats field;
            # the summary line silently under-counted skipped items.
            reason_lower = reason.lower()
            if "foreign" in reason_lower:
                stats.foreign_vi += 1
            elif "already translated" in reason_lower:
                stats.already_done += 1
            elif "no source" in reason_lower:
                # Case 0a — TOCTOU between find_source_sub and is_eligible
                # (the source file vanished between glob and read). Counted
                # as no_source for summary parity with the find_source_sub
                # None branch above.
                stats.no_source += 1
            elif "unreadable" in reason_lower:
                # Case 0b — source file present but read failed (permission /
                # I/O). This is a transient error, not a missing-source skip.
                stats.error += 1
                logger.warning(
                    "source-sub unreadable for %s: %s",
                    source_sub_path, reason,
                )
            else:
                # Unrecognised non-eligible reason — log but do not crash.
                # If we reach this branch, gap.is_eligible has grown a new
                # reason string that scan_for_eligible_items doesn't classify
                # yet; the count is intentionally dropped (loud at INFO) so
                # the next review surfaces the drift.
                logger.info(
                    "scan skip for %s — unclassified reason: %s",
                    source_sub_path, reason,
                )
            continue

        eligible.append(
            EligibleItem(
                media_item=item,
                source_sub_path=source_sub_path,
                reason=reason,
                source_lang=source_lang,
            )
        )

    return eligible, stats
