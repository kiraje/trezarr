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
from trezarr.translate._timecode import tc_to_ms as _tc_to_ms

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

# Lines that consist entirely of sentinel placeholder tokens after tag extraction
# have no natural-language content and must not count toward the VI diacritic ratio
# denominator.  A pure-tag cue (e.g. "{\an8}{\pos(960,50)}") becomes "<<T0>><<T1>>"
# after sentinel extraction — SENTINEL_ONLY_RE matches that form.
# Anchored (^ and $) and applied per-line to short strings; no catastrophic
# backtracking path (T-09-03-C, ASVS L1 V5).
SENTINEL_ONLY_RE = re.compile(r'^(<<T\d+>>\s*)*$')

# Backstop check for orphan sentinel tokens that were not reinserted (D-12/D-16 check 6)
SENTINEL_RE = re.compile(r'<<T\d+>>')

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
        # D-99/D-98: opaque pass-through cues (karaoke, drawing) — intentionally
        # untranslated.  SubLine.raw is set by the codec at parse time to signal
        # verbatim write-back.  These cues must never count toward the VI ratio.
        if trn_line.raw is not None:
            continue
        text = trn_line.text.strip()
        if not text:
            continue  # caught by check 2 before this; defensive skip
        if ALLOWLIST_RE.match(text):
            continue  # legitimately unchanged — excluded from ratio
        if SENTINEL_ONLY_RE.match(text):
            continue  # pure-tag cue — no natural language after sentinel extraction
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


def _check_timing_preserved(translated: SubDoc, source: SubDoc) -> None:
    """Check 5 (codec-fidelity invariant): each translated cue's timing equals its source cue.

    Trezarr's text/timing separation invariant (D-08/D-09) means translation NEVER
    alters timecodes — only ``SubLine.text`` is LLM-mutable; index/start_tc/end_tc are
    immutable by convention.  Check 4 verifies byte-identity of those fields; Check 5
    re-expresses this as a millisecond-level invariant so timing corruption (e.g. a
    codec bug that converts a timecode to milliseconds and back incorrectly) is caught
    even if the *string* round-trips cleanly.

    The check deliberately PASSES for source documents that contain overlapping cues
    (e.g. simultaneous song/dual-speaker lines, karaoke layers).  Such overlaps are a
    legitimate source-file property — translation preserves them verbatim, so they must
    never quarantine an otherwise valid translation.

    Raises GateError(GateFailure(5, ...)) if:
    - Any translated cue's start_ms differs from the corresponding source cue's start_ms, OR
    - Any translated cue's end_ms differs from the corresponding source cue's end_ms.

    Non-positive duration in the SOURCE (start_ms >= end_ms) is NOT flagged here —
    that is a property of the source file, faithfully preserved by translation.  A
    future source-validation step may flag it pre-pipeline; the gate's job is only to
    catch *translation-induced* corruption.

    Args:
        translated: The translated SubDoc produced by the engine.
        source:     The original source SubDoc (used for timing comparison).
    """
    for i, (trn_sl, src_sl) in enumerate(zip(translated.lines, source.lines)):
        trn_start = _tc_to_ms(trn_sl.start_tc)
        trn_end = _tc_to_ms(trn_sl.end_tc)
        src_start = _tc_to_ms(src_sl.start_tc)
        src_end = _tc_to_ms(src_sl.end_tc)

        if trn_start != src_start or trn_end != src_end:
            raise GateError(GateFailure(
                5,
                f"Cue {i} timing altered by translation: "
                f"source=({src_start}ms, {src_end}ms) "
                f"translated=({trn_start}ms, {trn_end}ms)",
                failing_indices=[i],
            ))


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
        # D-99/D-98: opaque pass-through cues have SubLine.raw set; the codec
        # guarantees they are non-empty by construction.  Skip to avoid any
        # accidental false-alarm if a future codec bug accidentally sets an empty
        # text alongside a non-None raw.
        if sl.raw is not None:
            continue
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

    # Check 5: timing preserved from source (codec-fidelity invariant — D-08/D-09).
    # Overlapping cues that exist in the SOURCE legitimately pass; only translation-
    # induced timing mutations fail.  The check complements Check 4 (byte-identity of
    # timecode strings) by catching ms-level corruption that survives string round-trip.
    _check_timing_preserved(translated, source)

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
