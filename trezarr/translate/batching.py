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

import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from trezarr.subtitles.model import SubDoc, SubLine
from trezarr.translate._timecode import tc_to_ms as _tc_to_ms

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings


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
        dominant_pair:  Optional (speaker_id, addressee_id) pair that is most
                        prevalent in this batch — used by Pass 4 self-review to
                        identify which pronoun pair the reviewer should check (D-56).
                        None when speaker attribution is not available.
    """
    cues: list[SubLine] = field(default_factory=list)
    context_before: list[SubLine] = field(default_factory=list)
    context_after: list[SubLine] = field(default_factory=list)
    dominant_pair: "tuple[int, int] | None" = None


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
    context_lines_k: int | None = None,
) -> Batch:
    """Construct a Batch with context_before and context_after attached.

    Args:
        cues:     The cues that belong to this batch.
        all_lines: The full ordered list of cues in the SubDoc.
        next_idx: Index in all_lines of the first cue AFTER this batch
                  (i.e. the position where the next batch will start).
        settings: Settings supplying translate_context_lines_k.
        context_lines_k: Override the context window size K.  When None (default),
                  falls back to settings.translate_context_lines_k so that existing
                  callers (Pass 3 translation) are unaffected.  Pass 2 attribution
                  uses settings.attribute_context_lines_k to widen context (D-50/WR-01).
    """
    k = context_lines_k if context_lines_k is not None else settings.translate_context_lines_k

    # Find the position of the first cue in this batch within all_lines
    first_idx = next_idx - len(cues)

    # context_before: up to K lines immediately before this batch
    before_start = max(0, first_idx - k)
    context_before = all_lines[before_start:first_idx]

    # context_after: up to K lines immediately after this batch
    after_end = min(len(all_lines), next_idx + k)
    context_after = all_lines[next_idx:after_end]

    return Batch(cues=cues, context_before=context_before, context_after=context_after)


def batch_subdoc(
    doc: SubDoc,
    settings: "TrezarrSettings",
    context_lines_k: int | None = None,
    max_cues_per_batch: int | None = None,
) -> list[Batch]:
    """Pack a SubDoc into LLM-sized batches respecting scene gaps and token budget.

    Greedy-walk algorithm (Q2 from RESEARCH.md):
    1. Compute char budget from settings.
    2. Walk cues in order, accumulating into the current batch while:
       - current_chars + len(cue.text) <= budget_chars, AND
       - current cue count < effective max cues per batch
    3. Before adding each cue, check for a scene gap >= translate_scene_gap_ms.
       If found, emit the current batch and start a new one (gap takes priority).
    4. A single cue that alone exceeds the budget is emitted as a one-cue batch
       with a UserWarning (never split or skipped).

    Args:
        doc:      The source subtitle document to batch.
        settings: Settings controlling batch size, gap threshold, and context K.
        context_lines_k: Override the context window size K for the Batch objects.
                  When None (default), uses settings.translate_context_lines_k (existing
                  behaviour preserved for all callers).  Pass this as
                  settings.attribute_context_lines_k when building attribution batches
                  to honour the D-50 "wider context than translate" design (WR-01).
        max_cues_per_batch: Override the maximum cue count per batch.  When None
                  (default), uses settings.translate_max_cues_per_batch.  Pass this as
                  settings.attribute_max_cues_per_batch when building attribution batches
                  to honour the D-50 "smaller attribution batches" design (WR-03).

    Returns:
        List of Batch objects in document order.
    """
    budget_chars = _compute_budget_chars(settings)
    effective_max_cues = max_cues_per_batch if max_cues_per_batch is not None else settings.translate_max_cues_per_batch
    batches: list[Batch] = []
    current: list[SubLine] = []
    current_chars = 0

    for i, cue in enumerate(doc.lines):
        # D-98/D-99: skip opaque pass-through cues (karaoke, drawing) — they are
        # never sent to the LLM.  Setting SubLine.raw marks the cue as verbatim.
        if cue.raw is not None:
            continue

        gap_ms = _gap_ms(doc.lines[i - 1], cue) if i > 0 else 0
        at_scene_gap = gap_ms >= settings.translate_scene_gap_ms

        would_overflow = (
            current_chars + len(cue.text) > budget_chars
            or len(current) >= effective_max_cues
        )

        if current and (at_scene_gap or would_overflow):
            batches.append(_make_batch(current, doc.lines, i, settings, context_lines_k))
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
        batches.append(_make_batch(current, doc.lines, len(doc.lines), settings, context_lines_k))

    return batches
