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
    # Phase 10 additions:
    source_upgraded: bool = False  # True when Case 1.5 fires (richer source available)


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
    source_upgraded: int = 0  # Phase 10: Case 1.5 re-translation from richer source


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
            elif "richer source" in reason_lower:
                # Case 1.5: richer source available — eligible, not skipped.
                # This branch should NOT be reached in the `not ok` path because
                # Case 1.5 returns eligible=True. Included defensively in case a
                # future variant produces False with this reason string.
                stats.source_upgraded += 1
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

        # Phase 10: track Case 1.5 source-upgrade items (D-110).
        is_source_upgrade = "richer source" in reason.lower()
        if is_source_upgrade:
            stats.source_upgraded += 1
        eligible.append(
            EligibleItem(
                media_item=item,
                source_sub_path=source_sub_path,
                reason=reason,
                source_lang=source_lang,
                source_upgraded=is_source_upgrade,
            )
        )

    return eligible, stats


def select_source_for_item(
    media_item: Any,
    settings: Any,
    bazarr_inventory: "list | None" = None,
    per_series_source_override: "list[str] | None" = None,
) -> "str | None":
    """Select the best available source language for a media item (D-109).

    Implements the D-109 fallback chain:
      1. per_series_source_override — if provided and any entry exists in available sources
      2. rank_sources over Bazarr inventory ∪ filesystem-detected langs, biased by
         media_item.original_language
      3. global settings.source_lang_priority
      4. first available source of any language

    Path safety (D-105, T-10-03):
      For each SubtitleEntry in bazarr_inventory:
        - apply_path_mapping(entry.path, settings.path_mappings)
        - assert_within_media_roots(mapped_path, media_roots)  [INTG-03 traversal guard]
        - Path(mapped_path).exists()
      Only entries that pass all three checks contribute code2 to the available-language set.
      Entries that fail (path outside media roots, or mapped path not on disk) are discarded
      silently. This prevents Bazarr-reported paths from causing traversal exploits.

    Bazarr soft-dependency (D-104):
      If bazarr_inventory is None or settings.bazarr_use_inventory is False, skip Bazarr
      step entirely and fall through to filesystem glob (find_source_sub).

    Args:
        media_item:               MediaItem-shaped object with .local_path (Path) and
                                  optionally .original_language (str | None).
        settings:                 TrezarrSettings-shaped object with .source_lang_priority,
                                  .path_mappings, .bazarr_use_inventory, .media_roots (optional).
        bazarr_inventory:         Optional list of BazarrInventoryItem or SubtitleEntry objects
                                  from BazarrClient.fetch_episodes/fetch_movies. None = degrade
                                  to filesystem glob (D-104).
        per_series_source_override: Optional per-series source language priority list (D-111).
                                  If provided, entries are checked against available sources first.

    Returns:
        2-letter source language code (e.g. "ko", "en") of the best available source,
        or None if no source found.
    """
    # Lazy imports to avoid circular imports at module load time.
    from trezarr.paths import apply_path_mapping, assert_within_media_roots, build_media_roots  # noqa: PLC0415
    from trezarr.source_selection.rank import normalize_original_language, rank_sources  # noqa: PLC0415

    # ── Step 1: Collect available source languages ─────────────────────────────
    available_langs: set[str] = set()

    # Build media roots for the traversal guard (D-29/INTG-03).
    try:
        media_roots = build_media_roots(settings)
    except Exception:  # noqa: BLE001
        media_roots = []

    # Bazarr inventory path (D-104 soft-dependency check).
    use_bazarr = (
        bazarr_inventory is not None
        and getattr(settings, "bazarr_use_inventory", True)
    )
    if use_bazarr and bazarr_inventory:
        for entry in bazarr_inventory:
            # SubtitleEntry has .code2 and .path; BazarrInventoryItem has .subtitles.
            # Handle both types.
            entries_to_check = []
            if hasattr(entry, "subtitles"):
                # BazarrInventoryItem
                entries_to_check = entry.subtitles
            elif hasattr(entry, "code2"):
                # SubtitleEntry directly
                entries_to_check = [entry]

            for sub in entries_to_check:
                raw_path = getattr(sub, "path", "")
                code2 = getattr(sub, "code2", "")
                if not raw_path or not code2:
                    continue
                # D-105: apply path mapping before any filesystem use.
                try:
                    mapped_path = apply_path_mapping(raw_path, getattr(settings, "path_mappings", []))
                except Exception:  # noqa: BLE001
                    continue
                # INTG-03: traversal guard — discard paths outside media roots (T-10-03).
                if media_roots:
                    try:
                        assert_within_media_roots(mapped_path, media_roots)
                    except ValueError:
                        # Path outside configured media roots — discard this entry.
                        logger.debug(
                            "Bazarr subtitle path %s failed traversal guard — discarding",
                            raw_path,
                        )
                        continue
                # Existence check — only count sources that are actually accessible.
                from pathlib import Path as _Path  # noqa: PLC0415
                if not _Path(mapped_path).exists():
                    continue
                available_langs.add(code2.lower())

    # Filesystem fallback / complement: scan for ALL source sidecar files (D-104, CR-01).
    # Do NOT use find_source_sub here — it returns only the first priority-matching
    # file, so available_langs would have at most 1 language code and rank_sources
    # would be a no-op for filesystem sources. Instead, glob directly for all
    # {stem}.{lang}.srt files and collect every language code present on disk.
    media_path = getattr(media_item, "local_path", None)
    if media_path is not None:
        try:
            escaped_stem = _glob.escape(media_path.stem)
            fs_candidates = sorted(media_path.parent.glob(f"{escaped_stem}.*.srt"))
        except OSError:
            fs_candidates = []
        for candidate in fs_candidates:
            m = _LANG_SIDECAR_RE.match(candidate.name)
            if m and m.group(1) == media_path.stem:
                available_langs.add(m.group(2).lower())

    if not available_langs:
        return None

    # ── Step 2: Select the best language ────────────────────────────────────────
    # Normalize original_language from the MediaItem.
    orig_lang_name: str | None = getattr(media_item, "original_language", None)
    original_language_code = normalize_original_language(orig_lang_name)

    available_list = list(available_langs)

    # Per-series override (D-111 / D-109 step 1): if provided, use override order,
    # filtered to what's actually available.
    if per_series_source_override:
        for override_lang in per_series_source_override:
            if override_lang.lower() in available_langs:
                return override_lang.lower()
        # No override lang available — fall through to ranking.

    # SRC-02 richness ranking over available sources biased by original_language (D-109 step 2).
    ranked = rank_sources(available_list, original_language_code)
    if ranked:
        return ranked[0]

    # Global source_lang_priority (D-109 step 3).
    global_priority = getattr(settings, "source_lang_priority", ["en"])
    for lang in global_priority:
        if lang.lower() in available_langs:
            return lang.lower()

    # First available (D-109 step 4).
    return next(iter(available_langs))
