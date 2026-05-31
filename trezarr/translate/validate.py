"""7-check pre-write validation gate for translated SubDocs (D-16, D-17).

Design decisions honoured:
  D-16  Gate every write on all 7 structural checks (fail-fast).
  D-17  Untranslated-line detection is cheap, layered, and low-false-reject:
        per-line allowlist (punctuation/digits/symbols) + per-file Vietnamese
        diacritic ratio threshold.  No heavy NLP dependency.
  D-18  Failure raises GateError so the engine can quarantine; gate never
        silently swallows a structural error.

The gate deliberately does NOT check Vietnamese quality (pronoun choices,
semantic correctness) — that is the responsibility of Phases 4–6.  It checks
structural integrity only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from trezarr.subtitles.model import SubDoc

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

# Vietnamese diacritic detection — two Unicode ranges combined:
#   U+1E00–U+1EFF: Latin Extended Additional (ổ, ợ, ẫ, ộ, ề, ể, ạ, ặ …)
#   U+01A0/U+01A1: Ơ/ơ ("o horn") — uniquely Vietnamese, not in French/Spanish
#   U+01AF/U+01B0: Ư/ư ("u horn") — uniquely Vietnamese, not in French/Spanish
# French/Spanish use only U+00C0–U+00FF (e.g. é, à, ü) which do NOT overlap.
VN_DIACRITIC_RE = re.compile(r'[Ḁ-ỿƠơƯư]')

# Lines matching this pattern are "legitimately unchanged" — all punctuation,
# digits, whitespace, or common musical/symbolic characters.  Excluded from
# the Vietnamese diacritic ratio denominator (D-17).
ALLOWLIST_RE = re.compile(r'^[\W\d\s♪♫…\.]+$')

# Backstop check for orphan sentinel tokens that were not reinserted (D-12/D-16 check 6)
SENTINEL_RE = re.compile(r'<<T\d+>>')

# Timecode parse pattern for check 5 (monotonic timestamps).  Same format as
# batching.py — replicated locally to avoid importing private symbols.
_TC_PARSE_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)")


@dataclass
class GateFailure:
    """Structured description of a validation gate failure.

    Attributes:
        check:           Check number (1–7) that failed.
        reason:          Human-readable failure description.
        failing_indices: Optional list of SubLine indices involved in the failure.
    """
    check: int
    reason: str
    failing_indices: list[int] | None = field(default=None)


class GateError(Exception):
    """Raised by validate_subdoc() when any of the 7 gate checks fails.

    Attributes:
        failure: The GateFailure instance describing the failed check.
    """

    def __init__(self, failure: GateFailure) -> None:
        self.failure = failure
        super().__init__(failure.reason)


def _tc_to_ms(tc: str) -> int:
    """Convert HH:MM:SS,mmm or HH:MM:SS.mmm to milliseconds."""
    m = _TC_PARSE_RE.match(tc)
    if m is None:
        return 0
    h, mi, s, ms_str = m.group(1), m.group(2), m.group(3), m.group(4)
    ms = int(ms_str.ljust(3, '0')[:3])
    return int(h) * 3600000 + int(mi) * 60000 + int(s) * 1000 + ms


def _check_untranslated(
    translated: SubDoc,
    source: SubDoc,
    settings: "TrezarrSettings",
) -> None:
    """Check 3: No untranslated lines (D-17).

    Raises GateError(GateFailure(3, ...)) if the ratio of translatable lines
    containing Vietnamese diacritics falls below settings.translate_vi_diacritic_ratio.

    A line is "translatable" if it is not on the allowlist (i.e. not all-punctuation/
    digits/symbols).  Allowlisted lines are excluded from both numerator and denominator.
    """
    translatable_indices = []
    vi_count = 0

    for i, (trn_line, src_line) in enumerate(zip(translated.lines, source.lines)):
        text = trn_line.text.strip()
        if not text:
            continue  # caught by check 2 before this; defensive skip
        if ALLOWLIST_RE.match(text):
            continue  # legitimately unchanged — excluded from ratio
        translatable_indices.append(i)
        if VN_DIACRITIC_RE.search(text):
            vi_count += 1

    if not translatable_indices:
        # All lines are allowlist-exempt — ratio defaults to 1.0 (pass)
        return

    ratio = vi_count / len(translatable_indices)
    if ratio < settings.translate_vi_diacritic_ratio:
        failing = [i for i in translatable_indices if not VN_DIACRITIC_RE.search(translated.lines[i].text.strip())]
        raise GateError(GateFailure(
            3,
            f"Vietnamese diacritic ratio {ratio:.2f} < threshold {settings.translate_vi_diacritic_ratio:.2f} "
            f"({vi_count}/{len(translatable_indices)} translatable lines have VI diacritics)",
            failing_indices=failing,
        ))


def _check_monotonic(doc: SubDoc) -> None:
    """Check 5: Monotonic, non-overlapping timestamps.

    Raises GateError(GateFailure(5, ...)) if:
    - Any cue's start_ms >= end_ms (zero-duration or reversed cue), OR
    - Any adjacent pair where start_ms[i] < end_ms[i-1] AND start_ms[i] is
      strictly greater than start_ms[i-1] (true overlap — simultaneous/duplicate-
      start cues that appear concurrently are accepted as common real-world SRT usage).
    """
    prev_end_ms: int | None = None
    prev_start_ms: int | None = None

    for i, sl in enumerate(doc.lines):
        start_ms = _tc_to_ms(sl.start_tc)
        end_ms = _tc_to_ms(sl.end_tc)

        if start_ms >= end_ms:
            raise GateError(GateFailure(
                5,
                f"Cue {i} has non-positive duration: start={start_ms}ms >= end={end_ms}ms",
                failing_indices=[i],
            ))

        # Monotonic-start check: flag backward jumps (cue starts before previous cue started).
        # This is distinct from the overlap check: a cue at [3000ms, 4000ms] after a cue at
        # [5000ms, 10000ms] has start_ms < prev_start_ms but does NOT satisfy the overlap
        # condition below — the backward jump would pass silently without this guard.
        if prev_start_ms is not None and start_ms < prev_start_ms:
            raise GateError(GateFailure(
                5,
                f"Cue {i} starts before previous cue: start={start_ms}ms < prev_start={prev_start_ms}ms",
                failing_indices=[i],
            ))

        # Overlap check: only flag when this cue starts after the previous cue started
        # (simultaneous/duplicate-start cues are accepted as concurrent display lines).
        if (
            prev_end_ms is not None
            and prev_start_ms is not None
            and start_ms > prev_start_ms
            and start_ms < prev_end_ms
        ):
            raise GateError(GateFailure(
                5,
                f"Cue {i} overlaps previous: start={start_ms}ms < prev_end={prev_end_ms}ms",
                failing_indices=[i],
            ))

        prev_start_ms = start_ms
        prev_end_ms = end_ms


def validate_subdoc(
    translated: SubDoc,
    source: SubDoc,
    settings: "TrezarrSettings",
) -> None:
    """Run all 7 gate checks on a translated SubDoc.  Raises GateError on first failure.

    Checks (fail-fast — stops at first failure):
      1. Cue count equals source
      2. No empty/whitespace-only translated lines
      3. No untranslated lines (per-line allowlist + VI diacritic ratio)
      4. Timecodes/indices byte-identical to source
      5. Monotonic, non-overlapping timestamps
      6. No orphan sentinel tokens (<<TN>>)
      7. All cue texts encode as valid UTF-8

    Args:
        translated: The translated SubDoc produced by the engine.
        source:     The original source SubDoc (for comparison).
        settings:   Settings supplying translate_vi_diacritic_ratio.

    Returns:
        None if all checks pass.

    Raises:
        GateError: On the first check that fails, with failure.check set to the
                   check number (1–7).
    """
    # Check 1: cue count equals source
    if len(translated.lines) != len(source.lines):
        raise GateError(GateFailure(
            1,
            f"Cue count mismatch: translated has {len(translated.lines)} lines, "
            f"source has {len(source.lines)} lines",
        ))

    # Check 2: no empty/whitespace-only translated lines
    for i, sl in enumerate(translated.lines):
        if not sl.text.strip():
            raise GateError(GateFailure(
                2,
                f"Empty translated cue at index {i}",
                failing_indices=[i],
            ))

    # Check 3: untranslated-line detection (two-tier: per-line allowlist + VI ratio)
    _check_untranslated(translated, source, settings)

    # Check 4: timecodes/indices byte-identical to source
    for i, (src, trn) in enumerate(zip(source.lines, translated.lines)):
        if src.index != trn.index or src.start_tc != trn.start_tc or src.end_tc != trn.end_tc:
            raise GateError(GateFailure(
                4,
                f"Timecode/index mutation at cue {i}: "
                f"source=({src.index!r}, {src.start_tc!r}, {src.end_tc!r}) "
                f"translated=({trn.index!r}, {trn.start_tc!r}, {trn.end_tc!r})",
                failing_indices=[i],
            ))

    # Check 5: monotonic, non-overlapping timestamps
    _check_monotonic(translated)

    # Check 6: no orphan sentinel tokens
    for i, sl in enumerate(translated.lines):
        if SENTINEL_RE.search(sl.text):
            raise GateError(GateFailure(
                6,
                f"Orphan sentinel token found in cue {i}: {sl.text!r}",
                failing_indices=[i],
            ))

    # Check 7: all cue texts encode as valid UTF-8
    for i, sl in enumerate(translated.lines):
        try:
            sl.text.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise GateError(GateFailure(
                7,
                f"UTF-8 encode error at cue {i}: {exc}",
                failing_indices=[i],
            )) from exc
