"""Pass 2: Per-cue speaker/addressee attribution (D-43, PRON-01).

Design decisions honoured:
  D-43  LineAttribution carries (line_index, speaker, addressee, confidence).
        Unmatched speaker/addressee names (not in bible.characters) resolve to
        speaker=None/addressee=None rather than crashing.
  D-47  Tier-3 (text-only) degradation returns all-LOW-confidence all-None
        attributions — never raises, never quarantines.
  D-50  enable_attribution toggle: False → same all-LOW-unknown path as Tier-3.
  PRON-01 Speaker/addressee attribution per cue with confidence enum.

Critical constraints:
  - No asyncio.Semaphore in this module.  LLMClient._semaphore is the sole gate (D-06, Pitfall A).
  - No SQLAlchemy import (D-39, Pitfall D).  Only trezarr.bible.dto is imported.
  - line_index is 1-based WITHIN a batch, not document-global (Pitfall E).
  - Returned list length == len(batch.cues) — missing LLM entries are filled LOW.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from trezarr.bible.dto import SeriesBibleDTO
    from trezarr.config import TrezarrSettings
    from trezarr.llm.client import LLMClient
    from trezarr.translate.batching import Batch

logger = logging.getLogger(__name__)


# ── Pydantic shapes (D-43, PRON-01) ───────────────────────────────────────────

class AttributionConfidence(str, Enum):
    """Confidence level for a speaker/addressee attribution."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LineAttribution(BaseModel):
    """Speaker/addressee attribution for a single subtitle cue.

    Attributes:
        line_index:  1-based index within the batch (Pitfall E — NOT document-global).
        speaker:     original_latin_name of the speaking character, or None if unknown.
        addressee:   original_latin_name of the addressed character, or None if unknown.
        confidence:  Confidence level of the attribution.
    """

    line_index: int                                   # 1-based within batch
    speaker: str | None = None                        # original_latin_name or None
    addressee: str | None = None                      # original_latin_name or None
    confidence: AttributionConfidence = AttributionConfidence.LOW


class BatchAttribution(BaseModel):
    """LLM structured-output container for a batch of cue attributions."""

    attributions: list[LineAttribution]


# ── Prompt construction ────────────────────────────────────────────────────────

def build_attribution_prompt(
    batch: "Batch",
    bible: "SeriesBibleDTO",
    attribute_context_lines_k: int,
) -> str:
    """Build the attribution prompt for a single batch.

    Wider context window than the translate pass (attribute_context_lines_k from D-50).
    Structure per RESEARCH.md Key Pattern 3:
      1. Series register/genre preamble
      2. Known characters list
      3. [CONTEXT - read only] — up to K lines before the batch
      4. [LINES TO ATTRIBUTE] — numbered 1..N
      5. [CONTEXT - read only] — up to K lines after the batch
      6. Attribution instruction

    Args:
        batch:                   The Batch whose cues need attribution.
        bible:                   Series Bible DTO with character roster.
        attribute_context_lines_k: Number of context lines before/after (wider than translate).

    Returns:
        Formatted prompt string for the LLM.
    """
    parts: list[str] = []

    # Preamble — series register
    register = getattr(bible, "register_value", None)
    register_desc = f" (register/tone: {register})" if register else ""
    parts.append(
        f"You are a subtitle analyst working on a Vietnamese-dubbed series{register_desc}. "
        "For each numbered subtitle line, identify who is speaking and who they are addressing. "
        "Use the character names exactly as listed below."
    )
    parts.append("")

    # Known characters list
    if bible.characters:
        parts.append("KNOWN CHARACTERS:")
        for char in bible.characters:
            gender_note = f" ({char.gender})" if char.gender else ""
            parts.append(f"  - {char.original_latin_name}{gender_note}")
    else:
        parts.append("KNOWN CHARACTERS: (none registered yet)")
    parts.append("")

    # Context before — read only, up to K lines
    # WR-05 (T-05-04-01 hardening): collapse internal newlines in context/cue text
    # so injected fake section headers cannot align with [CONTEXT]/[LINES TO ATTRIBUTE].
    context_before = batch.context_before[-attribute_context_lines_k:] if attribute_context_lines_k > 0 else []
    if context_before:
        parts.append("[CONTEXT - read only, lines before]")
        for line in context_before:
            parts.append(f"  {line.text.strip().replace(chr(10), ' ⏎ ')}")
        parts.append("")

    # Lines to attribute — numbered 1..N (1-based, batch-local per Pitfall E)
    parts.append("[LINES TO ATTRIBUTE]")
    for i, cue in enumerate(batch.cues, 1):
        safe_text = cue.text.strip().replace("\n", " ⏎ ")
        parts.append(f"[{i}] {safe_text}")
    parts.append("")

    # Context after — read only, up to K lines
    context_after = batch.context_after[:attribute_context_lines_k] if attribute_context_lines_k > 0 else []
    if context_after:
        parts.append("[CONTEXT - read only, lines after]")
        for line in context_after:
            parts.append(f"  {line.text.strip().replace(chr(10), ' ⏎ ')}")
        parts.append("")

    # Attribution instruction
    parts.append(
        "For each numbered line output a JSON object in this format:\n"
        '  {"line_index": N, "speaker": "<name or null>", "addressee": "<name or null>", '
        '"confidence": "<high|medium|low>"}\n'
        "Use null (not the string \"unknown\") when you cannot determine speaker or addressee. "
        "Only use names from the KNOWN CHARACTERS list. "
        "Wrap the full response as: "
        '{"attributions": [<list of line attribution objects>]}'
    )

    return "\n".join(parts)


# ── Core attribution function ──────────────────────────────────────────────────

def _all_low_unknown(batch: "Batch") -> list[LineAttribution]:
    """Return all-LOW-confidence, all-None attributions for every cue in the batch.

    Used for Tier-3 degradation, enable_attribution=False, and any parse failure
    (D-47: graceful degrade — never crash, never quarantine on attribution failure).
    """
    return [
        LineAttribution(line_index=i, confidence=AttributionConfidence.LOW)
        for i in range(1, len(batch.cues) + 1)
    ]


def _apply_name_matching(
    attributions: list[LineAttribution],
    bible: "SeriesBibleDTO",
) -> list[LineAttribution]:
    """Validate speaker/addressee names against bible.characters.

    Any name not found in the known character roster (case-insensitive) is set to
    None with confidence=LOW (D-43 name-matching rule, T-05-05-02 mitigation).

    Args:
        attributions: List of LineAttribution objects to validate.
        bible:        Series Bible DTO with character roster.

    Returns:
        Updated list with unmatched names replaced by None/LOW.
    """
    known_names = {
        c.original_latin_name.strip().lower()
        for c in bible.characters
    }

    result: list[LineAttribution] = []
    for attr in attributions:
        speaker = attr.speaker
        addressee = attr.addressee
        confidence = attr.confidence

        if speaker is not None and speaker.strip().lower() not in known_names:
            logger.debug(
                "attribution: speaker %r not in bible.characters — setting to None (D-43)",
                speaker,
            )
            speaker = None
            confidence = AttributionConfidence.LOW

        if addressee is not None and addressee.strip().lower() not in known_names:
            logger.debug(
                "attribution: addressee %r not in bible.characters — setting to None (D-43)",
                addressee,
            )
            addressee = None
            confidence = AttributionConfidence.LOW

        result.append(
            LineAttribution(
                line_index=attr.line_index,
                speaker=speaker,
                addressee=addressee,
                confidence=confidence,
            )
        )

    return result


def _fill_missing_indices(
    attributions: list[LineAttribution],
    batch_size: int,
) -> list[LineAttribution]:
    """Ensure the returned list has exactly batch_size entries, 1..batch_size.

    If the LLM returned too few or too many entries (Pitfall E), fill missing
    indices with all-LOW-unknown and drop extras beyond batch_size.

    Args:
        attributions: Parsed attributions from LLM.
        batch_size:   Expected number of cues in this batch.

    Returns:
        List of exactly batch_size LineAttribution entries, line_index 1..N.
    """
    # Build a lookup by line_index
    by_index: dict[int, LineAttribution] = {a.line_index: a for a in attributions}

    result: list[LineAttribution] = []
    for i in range(1, batch_size + 1):
        if i in by_index:
            result.append(by_index[i])
        else:
            logger.debug(
                "attribution: LLM missing entry for line_index=%d — inserting LOW default",
                i,
            )
            result.append(LineAttribution(line_index=i, confidence=AttributionConfidence.LOW))

    return result


async def attribute_batch(
    batch: "Batch",
    bible: "SeriesBibleDTO",
    llm_client: "LLMClient",
    settings: "TrezarrSettings",
) -> list[LineAttribution]:
    """Infer speaker/addressee for each cue in the batch.

    Calls LLMClient.call(response_model=BatchAttribution) and handles Tier-2/3
    degradation.  No asyncio.Semaphore here — LLMClient._semaphore is the sole
    concurrency gate (D-06, Pitfall A).  No DB access (D-39, Pitfall D).

    Args:
        batch:      The Batch whose cues need attribution.
        bible:      Series Bible DTO with character roster for name validation.
        llm_client: The LLM client (concurrency-gated internally).
        settings:   TrezarrSettings with enable_attribution, attribute_context_lines_k.

    Returns:
        List of LineAttribution with line_index 1..N (batch-local, Pitfall E).
        Length is always == len(batch.cues).  Never raises on LLM/parse failure.
    """
    batch_size = len(batch.cues)

    # Fast-path: attribution disabled → all-LOW-unknown (no LLM call)
    if not settings.enable_attribution:
        logger.debug("attribution: enable_attribution=False — returning all-LOW defaults")
        return _all_low_unknown(batch)

    # Tier-3 check: LLMClient is in plain-text mode → degrade gracefully (D-47)
    if getattr(llm_client, "_mode", None) == "text":
        logger.warning(
            "attribution: LLMClient is in text mode (Tier 3) — "
            "returning all-LOW-unknown attributions (D-47)"
        )
        return _all_low_unknown(batch)

    # Build the attribution prompt with the wider context window (D-50)
    prompt = build_attribution_prompt(batch, bible, settings.attribute_context_lines_k)

    # Call LLMClient — sole concurrency gate is inside LLMClient._semaphore (D-06, Pitfall A).
    # NEVER add asyncio.Semaphore here. response_model triggers Tier-1/2 path (D-47).
    raw = await llm_client.call(
        messages=[{"role": "user", "content": prompt}],
        response_model=BatchAttribution,
    )

    # Tier 1: raw is a BatchAttribution instance (json_schema mode succeeded)
    if isinstance(raw, BatchAttribution):
        attributions = raw.attributions

    # Tier 2: raw is a JSON string — attempt to parse
    elif isinstance(raw, str):
        try:
            parsed = BatchAttribution.model_validate_json(raw)
            attributions = parsed.attributions
        except (ValidationError, ValueError) as exc:
            logger.warning(
                "attribution: Tier-2 JSON parse failed (%s) — returning all-LOW defaults (D-47)",
                exc,
            )
            return _all_low_unknown(batch)

    else:
        # Unexpected return type — degrade gracefully
        logger.warning(
            "attribution: unexpected LLM return type %s — returning all-LOW defaults (D-47)",
            type(raw).__name__,
        )
        return _all_low_unknown(batch)

    # Apply name-matching gate (T-05-05-02, D-43)
    attributions = _apply_name_matching(attributions, bible)

    # Ensure length == batch_size, line_index 1..N (Pitfall E)
    attributions = _fill_missing_indices(attributions, batch_size)

    return attributions
