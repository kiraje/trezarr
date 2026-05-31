"""Token-budget batch packer with scene-gap detection and context window (D-14, D-15).

Design decisions honoured:
  D-14  Batch subtitle cues by token budget at safe boundaries.  Never split a
        single cue across batches.  Prefer boundaries at scene/pause gaps
        (>= translate_scene_gap_ms); fall back to max-cue-count cap.  Token
        estimation uses a char/token heuristic — conservative and
        tokenizer-agnostic.
  D-15  Attach K read-only source lines before and after each batch as context
        for the LLM (translate_context_lines_k).  Context lines cross batch
        boundaries; cues do not.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from trezarr.subtitles.model import SubDoc, SubLine

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings

# Timecode pattern: HH:MM:SS,mmm or HH:MM:SS.mmm (comma or period separator;
# any number of millisecond digits).  Replicated locally from srt.py's _TC_RE
# pattern — _TC_RE is private; we do NOT import it directly.
_TC_PARSE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d+)"
)


def _tc_to_ms(tc: str) -> int:
    """Convert a verbatim timecode string (HH:MM:SS,mmm or HH:MM:SS.mmm) to milliseconds."""
    m = _TC_PARSE_RE.match(tc)
    if m is None:
        return 0  # malformed timecode — treat as 0ms (defensive; gate will catch bad docs)
    h, mi, s, ms_str = m.group(1), m.group(2), m.group(3), m.group(4)
    ms = int(ms_str.ljust(3, '0')[:3])
    return int(h) * 3600000 + int(mi) * 60000 + int(s) * 1000 + ms


def _gap_ms(prev: SubLine, cur: SubLine) -> int:
    """Return the gap in milliseconds between end of prev and start of cur."""
    return _tc_to_ms(cur.start_tc) - _tc_to_ms(prev.end_tc)


@dataclass
class Batch:
    """A group of subtitle cues to be translated together, with context neighbors.

    Attributes:
        cues:           The subtitle cues in this batch (to be translated).
        context_before: Up to K source cues immediately preceding this batch
                        (read-only context for the LLM; not translated).
        context_after:  Up to K source cues immediately following this batch
                        (read-only context for the LLM; not translated).
    """
    cues: list[SubLine] = field(default_factory=list)
    context_before: list[SubLine] = field(default_factory=list)
    context_after: list[SubLine] = field(default_factory=list)


def _compute_budget_chars(settings: "TrezarrSettings") -> int:
    """Compute the effective character budget for cue text per batch.

    Formula (Q1 from RESEARCH.md):
        input_budget_chars = (context_window * (1 - overhead_fraction))
                             / (1 + output_expansion)
                             * chars_per_token
    """
    return int(
        (settings.llm_context_window * (1 - settings.translate_overhead_fraction))
        / (1 + settings.translate_output_expansion)
        * settings.translate_chars_per_token
    )


def _make_batch(
    cues: list[SubLine],
    all_lines: list[SubLine],
    next_idx: int,
    settings: "TrezarrSettings",
) -> Batch:
    """Construct a Batch with context_before and context_after attached.

    Args:
        cues:     The cues that belong to this batch.
        all_lines: The full ordered list of cues in the SubDoc.
        next_idx: Index in all_lines of the first cue AFTER this batch
                  (i.e. the position where the next batch will start).
        settings: Settings supplying translate_context_lines_k.
    """
    k = settings.translate_context_lines_k

    # Find the position of the first cue in this batch within all_lines
    first_idx = next_idx - len(cues)

    # context_before: up to K lines immediately before this batch
    before_start = max(0, first_idx - k)
    context_before = all_lines[before_start:first_idx]

    # context_after: up to K lines immediately after this batch
    after_end = min(len(all_lines), next_idx + k)
    context_after = all_lines[next_idx:after_end]

    return Batch(cues=cues, context_before=context_before, context_after=context_after)


def batch_subdoc(doc: SubDoc, settings: "TrezarrSettings") -> list[Batch]:
    """Pack a SubDoc into LLM-sized batches respecting scene gaps and token budget.

    Greedy-walk algorithm (Q2 from RESEARCH.md):
    1. Compute char budget from settings.
    2. Walk cues in order, accumulating into the current batch while:
       - current_chars + len(cue.text) <= budget_chars, AND
       - current cue count < translate_max_cues_per_batch
    3. Before adding each cue, check for a scene gap >= translate_scene_gap_ms.
       If found, emit the current batch and start a new one (gap takes priority).
    4. A single cue that alone exceeds the budget is emitted as a one-cue batch
       with a UserWarning (never split or skipped).

    Args:
        doc:      The source subtitle document to batch.
        settings: Settings controlling batch size, gap threshold, and context K.

    Returns:
        List of Batch objects in document order.
    """
    budget_chars = _compute_budget_chars(settings)
    batches: list[Batch] = []
    current: list[SubLine] = []
    current_chars = 0

    for i, cue in enumerate(doc.lines):
        gap_ms = _gap_ms(doc.lines[i - 1], cue) if i > 0 else 0
        at_scene_gap = gap_ms >= settings.translate_scene_gap_ms

        would_overflow = (
            current_chars + len(cue.text) > budget_chars
            or len(current) >= settings.translate_max_cues_per_batch
        )

        if current and (at_scene_gap or would_overflow):
            batches.append(_make_batch(current, doc.lines, i, settings))
            current = []
            current_chars = 0

        # Warn if a single cue alone exceeds the budget (D-14 one-cue batch rule)
        if not current and len(cue.text) > budget_chars:
            warnings.warn(
                f"batch_subdoc: single cue at index {i} exceeds token budget — "
                f"treating as one-cue batch (configure a larger llm_context_window)",
                UserWarning,
                stacklevel=2,
            )

        current.append(cue)
        current_chars += len(cue.text)

    if current:
        batches.append(_make_batch(current, doc.lines, len(doc.lines), settings))

    return batches
