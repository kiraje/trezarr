"""Pass 1: Full-file Bible analysis — holistic LLM call + merge into Series Bible (D-41, ENG-04, BIBLE-03).

Design decisions honoured:
  D-41  analyze_file() builds a single holistic prompt from the full source_doc + existing
        Bible + arr_metadata, calls LLMClient.call(response_model=BibleAnalysis), and merges
        the result via upsert_character / upsert_term / upsert_address_pair / merge_inferred.
  D-47  Tier-3 (plain-text) endpoint degrades gracefully: returns empty BibleAnalysis, never
        quarantines. Only logic failures (malformed JSON that Pydantic rejects after Tier-2)
        raise BibleAnalysisError and trigger quarantine.
  ENG-04 Pass 1 is a BARRIER — analyze_file must complete before any Pass 2/3 calls. This is
        enforced by engine.py's await in Plan 06 (not in this module).
  BIBLE-03 merge_bible_analysis writes directed address-pair entries via upsert_address_pair.

# No asyncio.Semaphore in this module.  LLMClient._semaphore is the sole gate (D-06, Pitfall 1).
# No SQLAlchemy imports (D-39, Pitfall D) — only trezarr.bible.dto and trezarr.bible.store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trezarr.bible.store import (
    upsert_character,
    upsert_term,
    upsert_address_pair,
    merge_inferred,
    record_relationship_event,
    load_series_bible,
    apply_human_edit_term,
)

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
    from trezarr.llm.client import LLMClient
    from trezarr.bible.dto import SeriesBibleDTO, SeriesDTO
    from trezarr.subtitles.model import SubDoc

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exception class — raised on logic failure to signal quarantine
# ---------------------------------------------------------------------------


class BibleAnalysisError(Exception):
    """Raised on Pass-1 logic failure (e.g., BibleAnalysis Pydantic validation fails
    after Tier-2 JSON attempt). This signals the engine to quarantine the episode.

    NOT raised on openai.APIError — the SDK handles transport/API retries (Pitfall B).
    NOT raised on Tier-3 degradation — that path returns empty BibleAnalysis (D-47).
    """


# ---------------------------------------------------------------------------
# Pydantic inference shapes
# ---------------------------------------------------------------------------


class AddressMapInference(BaseModel):
    """Directed speaker→addressee pronoun pair inferred from dialogue by the LLM."""

    speaker_name: str
    addressee_name: str
    self_term: str
    address_term: str
    confidence: float = 0.0


class RelationshipEventInference(BaseModel):
    """A relationship transition detected by Pass-1 analysis (BIBLE-07, D-51)."""

    character_a_name: str
    character_b_name: str
    episode_marker: str  # set to the current episode_key
    description: str  # narrative description of the shift
    suggested_self_term: str | None = None  # new self_term for A→B (if LLM can suggest)
    suggested_address_term: str | None = None  # new address_term for A→B (if LLM can suggest)


class CharacterInference(BaseModel):
    """Character inferred from dialogue by the LLM."""

    original_latin_name: str
    gender: str | None = None
    rough_age: str | None = None
    role: str | None = None
    original_script_name: str | None = None  # CJK / non-Latin on-screen name (e.g. '樱')
    # H2 fix: Sino-Vietnamese (Hán-Việt) reading of the character's name (e.g. 'Han' → 'Hàn',
    # 'Feng Tianji' → 'Phong Thiên Cực'). Pydantic-only inference field — NOT persisted, so no
    # DB migration is needed; consumed by plan_character_name_terms to pin the canonical
    # rendering on a cold Bible whose source is English/pinyin (no original_script_name to key on).
    vietnamese_rendering: str | None = None


class TermInference(BaseModel):
    """Proper noun / title / place / jargon term inferred by the LLM."""

    source_term: str
    vietnamese_rendering: str
    category: str | None = None


class BibleAnalysis(BaseModel):
    """Structured LLM output for Pass 1 — holistic Bible analysis of a subtitle file.

    All fields have safe defaults so a partial LLM response is still usable.
    model_config uses extra="ignore" so unknown extra fields from the LLM are silently
    dropped (T-05-04-03 mitigation).

    CR-02 (following SeriesDTO convention): the Python attribute is named ``register_value``
    because a field literally named ``register`` shadows Pydantic v2's deprecated
    ``BaseModel.register`` classmethod, producing a UserWarning. The alias ``register``
    keeps the LLM JSON key and merge_bible_analysis register-update logic intact.
    populate_by_name=True allows construction by Python name OR alias.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    register_value: str | None = Field(default=None, alias="register")
    characters: list[CharacterInference] = []
    terms: list[TermInference] = []
    address_map: list[AddressMapInference] = []
    relationship_events: list[
        RelationshipEventInference
    ] = []  # [Phase 6 ADDITIVE — safe default []]


@dataclass(frozen=True)
class NameTermSpec:
    """A character-name Term Dictionary entry to create-and-lock (on-screen name → canonical)."""

    source_term: str
    vietnamese_rendering: str


def plan_character_name_terms(
    characters: "list[CharacterInference]",
    existing_terms: list,
) -> "list[NameTermSpec]":
    """Plan LOCKED name terms so every character's on-screen name pins to a canonical rendering.

    260604-ikq follow-up (consistency moat): the protagonist had no Term Dictionary row, so her
    name was consistent-by-prompt only. For each character, the source form to pin is its
    ``original_script_name`` (the on-screen, often non-Latin name, e.g. '雏菊') when present, else
    its ``original_latin_name``. The canonical rendering is the existing Term Dictionary rendering
    for that character's Latin name when one exists (e.g. 'Sakura' → 'Anh Đào'), else the Latin
    name itself (e.g. 'Daisy'). A source form already present in ``existing_terms`` is skipped —
    idempotent, and it never clobbers an existing or human-edited term.

    Pure function. ``existing_terms`` is duck-typed on ``.source_term`` / ``.vietnamese_rendering``
    (works for both TermDTO and TermInference).
    """
    rendering_by_latin: dict[str, str] = {}
    existing_sources: set[str] = set()
    for t in existing_terms or []:
        src = (getattr(t, "source_term", "") or "").strip()
        if not src:
            continue
        existing_sources.add(src.lower())
        ren = (getattr(t, "vietnamese_rendering", "") or "").strip()
        if ren:
            rendering_by_latin[src.lower()] = ren

    specs: "list[NameTermSpec]" = []
    seen: set[str] = set()
    for ch in characters or []:
        latin = (getattr(ch, "original_latin_name", "") or "").strip()
        if not latin:
            continue
        script = (getattr(ch, "original_script_name", "") or "").strip()
        # H2 fix: prefer (1) an existing Term Dictionary rendering for this Latin name, then
        # (2) this character's inferred Hán-Việt vietnamese_rendering (stripped), then (3) the
        # raw Latin name. On a cold Bible whose source is English/pinyin, (2) is what stops
        # 'Han' being pinned as 'Han'; (1) still wins so a human-edited rendering is never clobbered.
        ch_rendering = (getattr(ch, "vietnamese_rendering", "") or "").strip()
        canonical = rendering_by_latin.get(latin.lower()) or ch_rendering or latin
        source = script or latin
        key = source.lower()
        if key in existing_sources or key in seen:
            continue
        specs.append(NameTermSpec(source_term=source, vietnamese_rendering=canonical))
        seen.add(key)
    return specs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_analysis_prompt(
    cue_texts: list[str],
    bible: "SeriesBibleDTO",
    arr_metadata: dict,
    episode_key: str = "",  # [Phase 6 NEW — for relationship_events episode_marker]
) -> str:
    """Build the Pass-1 holistic analysis prompt.

    Prompt structure (RESEARCH.md Key Pattern 1):
      1. EXISTING BIBLE CONTEXT — ground the LLM with what is already known.
      2. SERIES METADATA — title, genres, overview, year from arr_metadata.
      3. DIALOGUE SAMPLE — numbered cue texts for analysis.
      4. INSTRUCTIONS — what to infer and output.

    Security (T-05-04-01): cue texts are included as numbered data items under
    a clear [DIALOGUE SAMPLE] heading, not as instructions. Suspiciously long
    individual cue texts (>500 chars) are logged as a warning.

    Security (T-05-04-02): only known arr_metadata fields are extracted (title,
    genres, overview, year, network) — never a raw metadata dump.
    """
    parts: list[str] = []

    # ── EXISTING BIBLE CONTEXT ────────────────────────────────────────────
    parts.append("[EXISTING BIBLE CONTEXT]")
    if bible.register_value:
        parts.append(f"Register/tone: {bible.register_value}")
    if bible.characters:
        char_lines = []
        for c in bible.characters:
            desc = c.original_latin_name
            if c.gender:
                desc += f" ({c.gender})"
            if c.role:
                desc += f" — {c.role}"
            char_lines.append(f"  - {desc}")
        parts.append("Known characters:\n" + "\n".join(char_lines))
    else:
        parts.append("Known characters: none yet")

    # Include locked address map entries as grounding
    locked_pairs = [
        a
        for a in bible.address_map
        if "self_term" in (a.locked_fields or []) or "address_term" in (a.locked_fields or [])
    ]
    if locked_pairs:
        pair_lines = []
        for pair in locked_pairs:
            pair_lines.append(
                f"  - speaker_id={pair.speaker_character_id} → "
                f"addressee_id={pair.addressee_character_id}: "
                f"self_term={pair.self_term!r}, address_term={pair.address_term!r} [LOCKED]"
            )
        parts.append("Locked address pairs:\n" + "\n".join(pair_lines))

    # ── SERIES METADATA ───────────────────────────────────────────────────
    parts.append("\n[SERIES METADATA]")
    title = arr_metadata.get("title", "Unknown")
    genres = arr_metadata.get("genres", [])
    overview = arr_metadata.get("overview", "")
    year = arr_metadata.get("year", "")
    network = arr_metadata.get("network", "")

    parts.append(f"Title: {title}")
    if genres:
        genre_str = ", ".join(genres) if isinstance(genres, list) else str(genres)
        parts.append(f"Genres: {genre_str}")
    if year:
        parts.append(f"Year: {year}")
    if network:
        parts.append(f"Network: {network}")
    if overview:
        parts.append(f"Overview: {overview[:500]}")  # T-05-04-02: cap overview length

    # ── DIALOGUE SAMPLE ───────────────────────────────────────────────────
    parts.append("\n[DIALOGUE SAMPLE]")
    for i, text in enumerate(cue_texts, 1):
        if len(text) > 500:
            logger.warning(
                "Pass 1: cue %d has suspiciously long text (%d chars) — possible injection (T-05-04-01)",
                i,
                len(text),
            )
        # WR-05 (T-05-04-01 hardening): collapse internal newlines so injected fake
        # section headers cannot column-align with real [DIALOGUE SAMPLE] / [INSTRUCTIONS].
        safe_text = text.strip().replace("\n", " ⏎ ")
        parts.append(f"[{i}] {safe_text}")

    # ── INSTRUCTIONS ──────────────────────────────────────────────────────
    # H2 + B3 + B4 fix: require Hán-Việt readings (vietnamese_rendering) with concrete
    # examples + kinship-as-address mapping (H2); demand a genre-aware register so H1/H3
    # get a real signal (H1/H3); strengthen cold-Bible seeding so characters AND
    # confidence-bearing address_map dyads are emitted even with no prior Bible (B3); and
    # reinforce gender-/register-aware pronoun pairs (B4). The [DIALOGUE SAMPLE] framing and
    # WR-05 newline collapse above are untouched, so the T-05-04-01 security posture holds.
    parts.append(
        "\n[INSTRUCTIONS]\n"
        "Analyze the dialogue sample above. Even if no prior Bible context is given, infer "
        "a COMPLETE first-pass Bible and return a JSON object with:\n"
        "  - register: overall tone/register of the series. Be specific about genre register "
        "when applicable (e.g. 'xianxia', 'wuxia', 'cultivation', 'historical', 'classical', "
        "'cổ trang', 'tiên hiệp', 'kiếm hiệp'), otherwise 'formal' / 'casual' / 'romantic'. "
        "A classical/historical/cultivation register signals the translator and pronoun engine "
        "to use classical Sino-Vietnamese vocabulary and pronouns, so do not under-label it as "
        "merely 'casual'.\n"
        "  - characters: list of character objects with original_latin_name, gender (if determinable), "
        "rough_age (if determinable), role (if determinable), "
        "original_script_name (the original-script form of the name if non-Latin, "
        "e.g. '樱' for a Chinese character named Sakura; omit for Latin-named characters), "
        "vietnamese_rendering (REQUIRED: the Sino-Vietnamese / Hán-Việt reading of the name, "
        "NOT a phonetic transliteration and NOT the raw romanized/pinyin form — e.g. "
        "'Han' → 'Hàn', 'Feng Tianji' → 'Phong Thiên Cực', 'Elder Zhou' → 'Châu trưởng lão', "
        "'Miss Mei' → 'Mai cô nương'). A kinship word or rank used as a form of address "
        "('Brother', 'Elder', 'Senior', 'Young Master') maps to a Vietnamese kinship/honorific "
        "('huynh' / 'huynh trưởng' / 'trưởng lão' / 'tiền bối' / 'thiếu gia'), never a literal "
        "transliterated name. [linguist: confirm Hán-Việt examples]\n"
        "  - terms: list of proper nouns, titles, places, jargon with source_term and vietnamese_rendering\n"
        "  - address_map: list of directed pronoun pairs with speaker_name, addressee_name, self_term "
        "(how speaker refers to themselves), address_term (how speaker addresses the other), confidence (0.0-1.0). "
        "Emit a dyad for EVERY pair of characters who speak to each other in the sample, even on a "
        "fresh Bible, so downstream passes have an anchor. "
        "Use the EXACT name string from the characters list (either original_latin_name or original_script_name). "
        "Do NOT reference a character with a name form that was not listed in the characters list.\n"
        "  - relationship_events: list of relationship transitions detected in this episode\n"
        "    (ONLY emit when a relationship has CHANGED relative to the existing Bible context above).\n"
        f"    Each entry: character_a_name, character_b_name (use the EXACT name string from the characters list), "
        f'episode_marker (use "{episode_key}"),\n'
        "    description (narrative description, e.g. 'They become lovers in this episode'),\n"
        "    suggested_self_term (optional: new Vietnamese self-reference term for A→B),\n"
        "    suggested_address_term (optional: new Vietnamese address term for A→B).\n"
        "    IMPORTANT: Do NOT emit entries for stable, unchanged relationships.\n"
        "Focus on Vietnamese pronoun accuracy. The most important output is the address_map — "
        "identify which Vietnamese pronoun pairs (anh/em, chị/em, ông/bà, ta/ngươi, etc.) are appropriate "
        "for each speaker→addressee relationship. When the register is classical/historical/"
        "cultivation, prefer the classical pronoun set (ta / tại hạ / huynh / muội / ngươi / "
        "các hạ / tiền bối / trưởng lão) over the flat modern set. Never assign a female-"
        "gendered address term to a male addressee (or vice versa)."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def analyze_file(
    source_doc: "SubDoc",
    bible: "SeriesBibleDTO",
    arr_metadata: dict,
    llm_client: "LLMClient",
    settings: "TrezarrSettings",
    episode_key: str,
) -> BibleAnalysis:
    """Pass 1: Holistic Bible analysis of a subtitle file.

    Builds a structured prompt from the full source_doc + existing Bible + arr_metadata,
    calls the LLM, and returns a BibleAnalysis instance for merging.

    Tier-1 path (json_schema): result is a BibleAnalysis instance — return it directly.
    Tier-2 path (json_object): result is a JSON string — validate via model_validate_json();
        on ValidationError raise BibleAnalysisError (logic failure → quarantine).
    Tier-3 path (plain text, _mode == "text"): degrade gracefully — log warning, return
        empty BibleAnalysis (D-47). Do NOT raise BibleAnalysisError. Do NOT quarantine.

    Args:
        source_doc:   Parsed subtitle document to analyze.
        bible:        Current Series Bible state (for grounding).
        arr_metadata: *arr metadata snapshot (title, genres, overview, year, network).
        llm_client:   LLMClient instance — concurrency gate is inside LLMClient._semaphore.
        settings:     TrezarrSettings (for enable_pass1_analysis, pass1_max_cues_per_chunk).
        episode_key:  Episode identifier for logging.

    Returns:
        BibleAnalysis instance (possibly empty on Tier-3 or when disabled).

    Raises:
        BibleAnalysisError: On Tier-2 JSON that fails Pydantic validation (not on API errors).
    """
    # D-50: toggle for staged rollout/tests
    if not settings.enable_pass1_analysis:
        logger.debug("Pass 1 disabled via enable_pass1_analysis=False (episode: %s)", episode_key)
        return BibleAnalysis()

    # D-47: Tier-3 degradation — detect text-only endpoint before making the call
    if getattr(llm_client, "_mode", None) == "text":
        logger.warning(
            "Pass 1 skipped: endpoint is Tier-3 text-only (D-47). "
            "Bible will not be updated for episode: %s",
            episode_key,
        )
        return BibleAnalysis()

    # M2 fix: real Pass-1 chunk loop. Split into chunks of pass1_max_cues_per_chunk and merge
    # the per-chunk results, so a >chunk-size episode no longer silently drops its tail (the old
    # all_cue_texts[:max_cues] truncation). The enable_pass1_analysis and Tier-3 (_mode=='text')
    # early-returns above are unchanged, so the disabled-toggle + Tier-3 behavior is identical.
    all_cue_texts = [line.text for line in source_doc.lines if line.text.strip()]
    max_cues = settings.pass1_max_cues_per_chunk
    if max_cues and max_cues > 0:
        chunks = [
            all_cue_texts[i : i + max_cues] for i in range(0, len(all_cue_texts), max_cues)
        ] or [[]]
    else:
        chunks = [all_cue_texts]
    if len(chunks) > 1:
        logger.debug(
            "Pass 1 chunking: %d cues total -> %d chunks of <=%d (episode: %s)",
            len(all_cue_texts),
            len(chunks),
            max_cues,
            episode_key,
        )

    async def _analyze_one_chunk(chunk_texts: list[str]) -> BibleAnalysis:
        """Run + parse one chunk. Mirrors the Tier-1/Tier-2 contract; raises on parse failure.

        Tier-1 (json_schema): a BibleAnalysis instance — returned directly.
        Tier-2 (json_object): a JSON string — validated via model_validate_json().
        Any unexpected type is coerced through model_validate_json(str(result)).
        A ValidationError propagates so the caller can tolerate this single chunk (M2).
        """
        prompt = _build_analysis_prompt(chunk_texts, bible, arr_metadata, episode_key=episode_key)
        # Sole concurrency gate is inside LLMClient._semaphore (D-06, Pitfall A).
        # NEVER add asyncio.Semaphore here. response_model triggers the Tier-1/2 path (D-47).
        # FIX-B (260607-dbe): pass thinking= from settings.enable_reasoning_analysis so Pass-1
        # analysis always gets reasoning horsepower when the flag is set (captured from the
        # enclosing analyze_file() scope via closure).
        result = await llm_client.call(
            messages=[{"role": "user", "content": prompt}],
            response_model=BibleAnalysis,
            thinking=settings.enable_reasoning_analysis,
        )
        if isinstance(result, BibleAnalysis):
            return result
        if isinstance(result, str):
            return BibleAnalysis.model_validate_json(result)
        return BibleAnalysis.model_validate_json(str(result))

    # Merge per-chunk results: union de-duplicated by character name / source_term /
    # (speaker, addressee) / (a, b, description); keep the FIRST non-empty register_value.
    merged = BibleAnalysis()
    seen_chars: set[str] = set()
    char_by_key: dict[str, CharacterInference] = {}  # LOW-2: for cross-chunk field-fill
    seen_terms: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    seen_events: set[tuple[str, str, str]] = set()
    chunk_fail_count = 0
    for chunk_texts in chunks:
        if not chunk_texts:
            continue
        try:
            part = await _analyze_one_chunk(chunk_texts)
        except ValidationError as exc:
            # Stay tolerant: one bad chunk must not lose the others (M2).
            chunk_fail_count += 1
            logger.warning(
                "Pass 1: chunk parse failed for episode %s — skipping this chunk: %s",
                episode_key,
                exc,
            )
            continue
        # Keep the FIRST non-empty register_value across chunks.
        if not (merged.register_value or "").strip() and (part.register_value or "").strip():
            merged.register_value = part.register_value
        for c in part.characters:
            key = (c.original_latin_name or "").strip().lower()
            if not key:
                continue
            if key not in seen_chars:
                seen_chars.add(key)
                merged.characters.append(c)
                char_by_key[key] = c
            else:
                # LOW-2 fix: first-wins dedup must not drop a field a LATER chunk supplies —
                # especially the H2 vietnamese_rendering (else plan_character_name_terms pins the
                # raw Latin name). Fill any field the kept character left empty, field-by-field.
                kept = char_by_key[key]
                for _f in (
                    "vietnamese_rendering",
                    "gender",
                    "rough_age",
                    "role",
                    "original_script_name",
                ):
                    if not (getattr(kept, _f, None) or "") and (getattr(c, _f, None) or ""):
                        setattr(kept, _f, getattr(c, _f))
        for t in part.terms:
            key = (t.source_term or "").strip().lower()
            if key and key not in seen_terms:
                seen_terms.add(key)
                merged.terms.append(t)
        for p in part.address_map:
            pkey = (
                (p.speaker_name or "").strip().lower(),
                (p.addressee_name or "").strip().lower(),
            )
            if pkey not in seen_pairs:
                seen_pairs.add(pkey)
                merged.address_map.append(p)
        for e in part.relationship_events:
            ekey = (
                (e.character_a_name or "").strip().lower(),
                (e.character_b_name or "").strip().lower(),
                (e.description or "").strip().lower(),
            )
            if ekey not in seen_events:
                seen_events.add(ekey)
                merged.relationship_events.append(e)

    # Only quarantine when EVERY non-empty chunk failed to parse (systemic logic failure → D-47).
    non_empty_chunks = sum(1 for c in chunks if c)
    if non_empty_chunks > 0 and chunk_fail_count == non_empty_chunks:
        raise BibleAnalysisError(
            f"BibleAnalysis parse failed for ALL {chunk_fail_count} chunk(s) of episode "
            f"{episode_key!r} — logic failure (quarantine)."
        )

    logger.debug(
        "Pass 1 merged %d chunk(s) for episode %s (%d failed)",
        non_empty_chunks,
        episode_key,
        chunk_fail_count,
    )
    return merged


async def merge_bible_analysis(
    session_factory: object,
    series_dto: "SeriesDTO | None" = None,
    analysis: BibleAnalysis | None = None,
    episode_key: str = "",
    *,
    series_id: int | None = None,
    settings: object = None,
) -> None:
    """Merge a BibleAnalysis result into the Series Bible via store functions.

    Order of operations (D-41):
      1. If analysis.register is set → merge_inferred(series register field).
      2. For each character → upsert_character (builds name→id map for address_map step).
      3. For each term → upsert_term.
      4. For each address_map entry → resolve speaker+addressee IDs from the name map,
         then upsert_address_pair. Unresolvable names are warned and skipped (never crash).
      5. For each relationship_event → resolve character IDs case-insensitively (CR-01),
         then record_relationship_event. Advisory only — no total-failure raise (WR-06).

    WR-06: Per-row store failures are caught so one bad character/term/pair does not
    abort the merge.  However, if ALL rows fail (likely a systemic DB issue), a
    BibleAnalysisError is raised so the episode is quarantined rather than silently
    proceeding to Pass 2/3 with an empty Bible.

    Args:
        session_factory: Async session factory (passed through to store functions).
        series_dto:      SeriesDTO for the current series (carries id). If None, series_id must be set.
        analysis:        BibleAnalysis from analyze_file().
        episode_key:     Episode identifier for bible_event provenance.
        series_id:       Series surrogate PK — alternative to series_dto.id (Phase-6 callers).
        settings:        TrezarrSettings — used for enable_relationship_events toggle.
    """
    # Resolve series_id from either series_dto or explicit series_id kwarg
    if series_dto is not None:
        _series_id = series_dto.id
    elif series_id is not None:
        _series_id = series_id
    else:
        raise ValueError("merge_bible_analysis requires either series_dto or series_id")
    series_id = _series_id  # type: ignore[assignment]

    # analysis defaults to empty BibleAnalysis if called with None (backward compat)
    if analysis is None:
        analysis = BibleAnalysis()

    # Step 1: Update series register if inferred
    # WR-07: guard against empty/whitespace register_value — "" is not None but must
    # not overwrite a good prior register with an empty string.
    reg = (analysis.register_value or "").strip()
    if reg and series_dto is not None:
        try:
            await merge_inferred(
                session_factory,
                series_dto,
                {"register": reg},
                episode_key,
                source="inference",
            )
            logger.debug("Pass 1: merged register=%r for series %d", reg, series_id)
        except Exception as exc:
            logger.warning("Pass 1: failed to merge register for series %d: %s", series_id, exc)

    # Step 2: Upsert characters — build name→id map for address_map resolution
    # WR-06: count failures; raise BibleAnalysisError on total failure (systemic DB fault).
    # Pre-seed name_to_id with existing DB characters (case-insensitive, CR-01) so that
    # relationship_event resolution works even when the character is not in analysis.characters.
    # MEDIUM-1 fix (C6 aliases): resolve honorific-prefixed dyad/event names ("Elder Han") to
    # the seeded character row ("Han") via the shared helper — mirrors reconcile.py / engine.py
    # so the cold-Bible address-map anchor is actually written even if the LLM references the
    # dyad by an honorific form. name_to_id stays EXACT-keyed; the alias is a lookup fallback.
    from trezarr.translate.engine import _normalize_name

    name_to_id: dict[str, int] = {}
    existing_pair_keys: set[tuple[int, int]] = set()
    try:
        existing_bible = await load_series_bible(session_factory, series_id=series_id)
        for c in existing_bible.characters:
            name_to_id[c.original_latin_name.strip().lower()] = c.id
        # Build existing pair keys for create-or-affirm mode in Step 4 (scy):
        # any pair already in the Bible must NOT have its terms overwritten by bare
        # Pass-1 inference absent a relationship_event — Pass-1 Step 4 is create-only
        # for existing pairs; new pairs are created with inferred terms as before.
        existing_pair_keys = {
            (a.speaker_character_id, a.addressee_character_id) for a in existing_bible.address_map
        }
    except Exception as exc:
        existing_pair_keys = set()  # safe degrade: create-with-terms path applies
        logger.warning(
            "Pass 1: could not pre-load existing characters for series %d (name resolution may miss some): %s",
            series_id,
            exc,
        )
    char_fail_count = 0
    for char in analysis.characters:
        try:
            char_dto, _ = await upsert_character(
                session_factory,
                series_id=series_id,
                original_latin_name=char.original_latin_name,
                gender=char.gender,
                rough_age=char.rough_age,
                role=char.role,
                episode_key=episode_key,
                source="inference",
            )
            name_to_id[char.original_latin_name.strip().lower()] = char_dto.id
            # CJK fix: also index the original-script name so address_map / relationship_events
            # that reference the on-screen name (e.g. '樱') resolve to the character ID (CR-01).
            if char.original_script_name and char.original_script_name.strip():
                name_to_id[char.original_script_name.strip().lower()] = char_dto.id
            logger.debug(
                "Pass 1: upserted character %r (id=%d) for series %d",
                char.original_latin_name,
                char_dto.id,
                series_id,
            )
        except Exception as exc:
            char_fail_count += 1
            logger.warning(
                "Pass 1: failed to upsert character %r for series %d: %s",
                char.original_latin_name,
                series_id,
                exc,
            )

    if analysis.characters and char_fail_count == len(analysis.characters):
        raise BibleAnalysisError(
            f"Pass 1 merge: ALL {char_fail_count} character upserts failed for series {series_id} "
            f"episode {episode_key!r} — likely a systemic DB failure (WR-06)"
        )

    # Step 3: Upsert terms
    term_fail_count = 0
    for term in analysis.terms:
        try:
            await upsert_term(
                session_factory,
                series_id=series_id,
                source_term=term.source_term,
                vietnamese_rendering=term.vietnamese_rendering,
                category=term.category,
                episode_key=episode_key,
                source="inference",
            )
            logger.debug("Pass 1: upserted term %r for series %d", term.source_term, series_id)
        except Exception as exc:
            term_fail_count += 1
            logger.warning(
                "Pass 1: failed to upsert term %r for series %d: %s",
                term.source_term,
                series_id,
                exc,
            )

    if analysis.terms and term_fail_count == len(analysis.terms):
        raise BibleAnalysisError(
            f"Pass 1 merge: ALL {term_fail_count} term upserts failed for series {series_id} "
            f"episode {episode_key!r} — likely a systemic DB failure (WR-06)"
        )

    # Step 3.5: Lock each character's on-screen name → canonical rendering (260604-ikq).
    # Makes name consistency contract-protected (a LOCKED Term Dictionary row injected into the
    # translate-prompt glossary, safe from future inference drift) rather than prompt-only — the
    # protagonist 雏菊 previously had no term row. Idempotent + respects existing/human-edited
    # terms (plan_character_name_terms skips source forms already present). Best-effort: a failure
    # here must never abort the merge or quarantine the episode.
    # PROVENANCE NOTE (bible-consistency audit LOW nit): apply_human_edit_term stamps the audit
    # event source="lock" + episode_key=None, so these system auto-locks are not distinguishable
    # from human UI locks in bible_event. Accepted for now; the preferred fix (a source="system"
    # kwarg on apply_human_edit_term) is recorded as a follow-up.
    try:
        existing_terms = (await load_series_bible(session_factory, series_id=series_id)).terms
    except Exception as exc:
        existing_terms = []
        logger.warning(
            "Pass 1 Step 3.5: could not load terms for name-lock (series %d): %s", series_id, exc
        )
    for spec in plan_character_name_terms(analysis.characters, existing_terms):
        try:
            await apply_human_edit_term(
                session_factory,
                series_id=series_id,
                source_term=spec.source_term,
                field="vietnamese_rendering",
                new_value=spec.vietnamese_rendering,
                lock=True,
            )
            logger.debug(
                "Pass 1 Step 3.5: locked name term %r → %r for series %d",
                spec.source_term,
                spec.vietnamese_rendering,
                series_id,
            )
        except Exception as exc:
            logger.warning(
                "Pass 1 Step 3.5: failed to lock name term %r for series %d: %s",
                spec.source_term,
                series_id,
                exc,
            )

    # Step 4: Upsert address pairs — resolve names to character IDs
    # Use same case-insensitive normalisation as reconcile.py / engine.py (CR-01)
    pair_fail_count = 0
    pair_attempt_count = 0
    for pair in analysis.address_map:
        spk_id = name_to_id.get((pair.speaker_name or "").strip().lower()) or name_to_id.get(
            _normalize_name(pair.speaker_name or "")
        )
        addr_id = name_to_id.get((pair.addressee_name or "").strip().lower()) or name_to_id.get(
            _normalize_name(pair.addressee_name or "")
        )

        if spk_id is None:
            logger.warning(
                "Pass 1: could not resolve speaker name %r to a character ID for series %d — "
                "skipping address pair (%r → %r)",
                pair.speaker_name,
                series_id,
                pair.speaker_name,
                pair.addressee_name,
            )
            continue

        if addr_id is None:
            logger.warning(
                "Pass 1: could not resolve addressee name %r to a character ID for series %d — "
                "skipping address pair (%r → %r)",
                pair.addressee_name,
                series_id,
                pair.speaker_name,
                pair.addressee_name,
            )
            continue

        pair_attempt_count += 1
        try:
            # CREATE-OR-AFFIRM (scy — Vector 1 fix): an existing unlocked pair's terms must
            # NOT be overwritten by bare Pass-1 inference absent a relationship_event. Pass
            # self_term=None/address_term=None for an existing pair so store.py's
            # `if new_val is None: continue` guard leaves the established terms untouched.
            # A brand-new pair (not in existing_pair_keys) is created with inferred terms.
            pair_already_exists = (spk_id, addr_id) in existing_pair_keys
            if pair_already_exists:
                logger.debug(
                    "Pass 1: existing pair %r→%r — skipping term update (create-or-affirm mode); terms unchanged.",
                    pair.speaker_name,
                    pair.addressee_name,
                )
            await upsert_address_pair(
                session_factory,
                series_id=series_id,
                speaker_character_id=spk_id,
                addressee_character_id=addr_id,
                self_term=None if pair_already_exists else pair.self_term,
                address_term=None if pair_already_exists else pair.address_term,
                # FIX (260608-scy harness LOW): for an EXISTING pair, pass None so
                # store.py's None-guard leaves the original valid_from_episode intact.
                # A brand-new pair correctly carries the current episode_key as its
                # first-seen marker (symmetric with the None/term guards above).
                valid_from_episode=None if pair_already_exists else episode_key,
                episode_key=episode_key,
                source="inference",
            )
            logger.debug(
                "Pass 1: upserted address pair %r→%r (self=%r, address=%r) for series %d",
                pair.speaker_name,
                pair.addressee_name,
                pair.self_term,
                pair.address_term,
                series_id,
            )
        except Exception as exc:
            pair_fail_count += 1
            logger.warning(
                "Pass 1: failed to upsert address pair %r→%r for series %d: %s",
                pair.speaker_name,
                pair.addressee_name,
                series_id,
                exc,
            )

    if pair_attempt_count > 0 and pair_fail_count == pair_attempt_count:
        raise BibleAnalysisError(
            f"Pass 1 merge: ALL {pair_fail_count} address-pair upserts failed for series {series_id} "
            f"episode {episode_key!r} — likely a systemic DB failure (WR-06)"
        )

    # Step 5: Record relationship events (D-51, D-52, BIBLE-07)
    # Uses the SAME name_to_id map built in Step 2 (case-insensitive, CR-01).
    # Pitfall 4: resolve via .strip().lower() — same as address_map Step 4.
    # D-60 toggle: skip if enable_relationship_events is False.
    enable_rel_events = getattr(settings, "enable_relationship_events", True)
    if enable_rel_events:
        event_fail_count = 0
        for event in analysis.relationship_events:
            char_a_id = name_to_id.get(
                (event.character_a_name or "").strip().lower()
            ) or name_to_id.get(_normalize_name(event.character_a_name or ""))
            char_b_id = name_to_id.get(
                (event.character_b_name or "").strip().lower()
            ) or name_to_id.get(_normalize_name(event.character_b_name or ""))

            if char_a_id is None:
                logger.warning(
                    "Pass 1: could not resolve character_a_name %r to ID for series %d — "
                    "skipping relationship_event (%r ↔ %r)",
                    event.character_a_name,
                    series_id,
                    event.character_a_name,
                    event.character_b_name,
                )
                continue
            if char_b_id is None:
                logger.warning(
                    "Pass 1: could not resolve character_b_name %r to ID for series %d — "
                    "skipping relationship_event (%r ↔ %r)",
                    event.character_b_name,
                    series_id,
                    event.character_a_name,
                    event.character_b_name,
                )
                continue

            try:
                await record_relationship_event(
                    session_factory,
                    series_id=series_id,
                    character_a_id=char_a_id,
                    character_b_id=char_b_id,
                    episode_marker=episode_key,
                    description=event.description,
                )
                logger.debug(
                    "Pass 1: recorded relationship_event %r ↔ %r at %r for series %d",
                    event.character_a_name,
                    event.character_b_name,
                    episode_key,
                    series_id,
                )
            except Exception as exc:
                event_fail_count += 1
                logger.warning(
                    "Pass 1: failed to record relationship_event %r ↔ %r for series %d: %s",
                    event.character_a_name,
                    event.character_b_name,
                    series_id,
                    exc,
                )
        # WR-06 pattern: total failure check is omitted for relationship_events —
        # events are advisory, not required for a successful translation (unlike address pairs).
