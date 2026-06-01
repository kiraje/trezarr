"""Deterministic pronoun-pair reconciliation for Phase 5 Three-Pass Engine (D-44, D-45).

Design decisions honoured:
  D-44  Deterministic reconciliation — one (self_term, address_term) per ordered pair
        per episode; first high-confidence witness wins the gate; existing Address Map
        entry supplies the actual terms; reciprocal coherence check against
        KINSHIP_RECIPROCAL; persist to Address Map.
  D-45  Below confidence threshold → safe neutral/polite default pair; never risk intimate
        pronoun. Configurable pronoun_confidence_threshold ("high"|"medium"|"low").
  D-39  No SQLAlchemy import at module level — TYPE_CHECKING only (Pitfall D).

# No asyncio.Semaphore in this module.  LLMClient._semaphore is the sole gate (D-06, Pitfall 1).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from trezarr.bible.store import upsert_address_pair

if TYPE_CHECKING:
    from trezarr.config import TrezarrSettings
    from trezarr.bible.dto import SeriesBibleDTO, AddressMapDTO, RelationshipEventDTO
    from trezarr.translate.attribute import LineAttribution
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vietnamese kinship pronoun reciprocal pairs (D-44, RESEARCH.md Key Pattern 5)
# ---------------------------------------------------------------------------
# Standard Vietnamese kinship pronoun reciprocal pairs — extend as needed for niche terms.
# (self_term, address_term) → expected reciprocal (self_term, address_term) for B→A
KINSHIP_RECIPROCAL: dict[tuple[str, str], tuple[str, str]] = {
    ("anh", "em"): ("em", "anh"),
    ("em", "anh"): ("anh", "em"),
    ("chị", "em"): ("em", "chị"),
    ("em", "chị"): ("chị", "em"),
    ("anh", "anh"): ("anh", "anh"),
    ("chị", "chị"): ("chị", "chị"),
    ("ông", "cháu"): ("cháu", "ông"),
    ("bà", "cháu"): ("cháu", "bà"),
    ("ông", "con"): ("con", "ông"),
    ("bà", "con"): ("con", "bà"),
    ("bố", "con"): ("con", "bố"),
    ("mẹ", "con"): ("con", "mẹ"),
    ("cha", "con"): ("con", "cha"),
    ("tôi", "bạn"): ("bạn", "tôi"),
    ("tôi", "anh"): ("anh", "tôi"),
    ("tôi", "chị"): ("chị", "tôi"),
    ("tôi", "ông"): ("ông", "tôi"),
    ("tôi", "bà"): ("bà", "tôi"),
}

# ---------------------------------------------------------------------------
# Safe-default constants (D-45, RESEARCH.md Key Pattern 5)
# ---------------------------------------------------------------------------
SAFE_DEFAULT_SELF = "tôi"
SAFE_DEFAULT_ADDRESS_MALE = "anh"
SAFE_DEFAULT_ADDRESS_FEMALE = "chị"
SAFE_DEFAULT_ADDRESS_NEUTRAL = "bạn"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _threshold_value(threshold_str: str) -> int:
    """Map threshold string to a numeric tier (higher = stricter).

    Returns:
        3 for "high", 2 for "medium", 1 for "low".  Unknown strings default to 2.
    """
    return {"high": 3, "medium": 2, "low": 1}.get(threshold_str.lower(), 2)


def _confidence_value(confidence: object) -> int:
    """Map AttributionConfidence enum (or its string value) to numeric tier.

    AttributionConfidence is a str Enum: HIGH="high", MEDIUM="medium", LOW="low".
    Accepts the enum instance or a plain string.
    """
    # str(enum_instance) → "AttributionConfidence.high" in some Python versions;
    # .value gives the raw string.  Handle both.
    raw = getattr(confidence, "value", str(confidence)).lower()
    # Strip "attributionconfidence." prefix if present (str(Enum) representation)
    if "." in raw:
        raw = raw.split(".")[-1]
    return {"high": 3, "medium": 2, "low": 1}.get(raw, 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_safe_default(
    addressee_gender: str | None,
    settings: "TrezarrSettings",
) -> tuple[str, str]:
    """Return (self_term, address_term) for low-confidence attributions (D-45).

    If settings.pronoun_safe_default is set, that user override is returned
    directly.  Otherwise, selects the address term by addressee_gender:
      "male"   → SAFE_DEFAULT_ADDRESS_MALE   ("anh")
      "female" → SAFE_DEFAULT_ADDRESS_FEMALE ("chị")
      other    → SAFE_DEFAULT_ADDRESS_NEUTRAL ("bạn")

    Args:
        addressee_gender: Gender string of the addressee ("male"/"female"/None/other).
        settings:         TrezarrSettings instance (provides pronoun_safe_default).

    Returns:
        (self_term, address_term) tuple for safe neutral/polite usage.
    """
    if settings.pronoun_safe_default is not None:
        return settings.pronoun_safe_default  # user override

    address = {
        "male": SAFE_DEFAULT_ADDRESS_MALE,
        "female": SAFE_DEFAULT_ADDRESS_FEMALE,
    }.get(addressee_gender or "", SAFE_DEFAULT_ADDRESS_NEUTRAL)
    return (SAFE_DEFAULT_SELF, address)


def _find_transition_for_pair(
    relationship_events: "list[RelationshipEventDTO]",
    spk_id: int,
    addr_id: int,
    episode_key: str,
) -> "RelationshipEventDTO | None":
    """Find a logged relationship_event for the ordered pair at this episode.

    Events are undirected (character_a_id, character_b_id) — match EITHER direction.
    Filter to current episode only (Pitfall 6: never apply future-episode transitions).
    """
    for event in relationship_events:
        if event.episode_marker != episode_key:
            continue  # Pitfall 6: only current episode's event authorizes a change
        if (event.character_a_id == spk_id and event.character_b_id == addr_id) or \
           (event.character_a_id == addr_id and event.character_b_id == spk_id):
            return event
    return None


def _derive_transition_terms(
    transition: "RelationshipEventDTO",
    resolved_map: dict,
    addr_id: int,
    id_to_gender: dict,
    settings: "TrezarrSettings",
) -> tuple[str, str]:
    """Derive (self_term, address_term) for a transition (D-54 preferred order):
      1. LLM-suggested terms from transition (suggested_self_term / suggested_address_term)
      2. get_safe_default fallback
    """
    if transition.suggested_self_term and transition.suggested_address_term:
        return (transition.suggested_self_term, transition.suggested_address_term)
    # Fallback: use get_safe_default
    addr_gender = id_to_gender.get(addr_id)
    return get_safe_default(addr_gender, settings)


async def reconcile_attributions(
    flat_attributions: "list[LineAttribution]",
    bible: "SeriesBibleDTO",
    session_factory: "async_sessionmaker",
    series_id: int,
    episode_key: str,
    settings: "TrezarrSettings",
) -> dict[tuple[int, int], tuple[str, str]]:
    """Produce the in-memory (speaker_id, addressee_id) → (self_term, address_term) map.

    This is the Pass-3 lookup table — no DB read in the hot path.

    Algorithm (D-44):
      a) Build name→char_id index from bible.characters.
      b) For each attribution where speaker+addressee can be matched to IDs,
         collect attributions by (speaker_id, addressee_id).
      c) Apply confidence threshold gate per observed pair:
         - Filter to attributions with confidence >= pronoun_confidence_threshold.
         - If any survive the filter: the pair is "confirmed" — use the existing
           Address Map entry's terms if present; otherwise fall through to
           get_safe_default.
         - If NONE survive the filter (all below threshold):
             • Honour a LOCKED Address Map entry if present.
             • Otherwise SKIP an unlocked Address Map entry and fall through to
               get_safe_default.  (Success #4 invariant: below-threshold always
               yields safe default regardless of unlocked prior-episode entries.)
      d) Call upsert_address_pair for each resolved pair.
      e) Reciprocal coherence: for each resolved (A→B, self_t, addr_t), look up
         KINSHIP_RECIPROCAL.get((self_t, addr_t)); if found and (B→A) not yet resolved,
         call upsert_address_pair with source="inference" for the reciprocal.
      f) Return resolved_map dict.

    Args:
        flat_attributions:  All LineAttribution objects for this episode (batch-local
                            line_index values — reconciliation groups by pair, not index).
        bible:              SeriesBibleDTO with characters and address_map eagerly loaded.
        session_factory:    async_sessionmaker for DB writes.
        series_id:          Series PK.
        episode_key:        Episode key for provenance (e.g. "S01E01").
        settings:           TrezarrSettings (pronoun_confidence_threshold, pronoun_safe_default).

    Returns:
        dict mapping (speaker_char_id, addressee_char_id) to (self_term, address_term).
    """
    # (a) Build case- and whitespace-insensitive name→char_id index (CR-01)
    name_to_id: dict[str, int] = {
        c.original_latin_name.strip().lower(): c.id for c in bible.characters
    }
    # Build char_id→gender for get_safe_default fallback
    id_to_gender: dict[int, str | None] = {c.id: c.gender for c in bible.characters}

    # Build existing Address Map index: (spk_id, addr_id) → AddressMapDTO
    existing_map: dict[tuple[int, int], "AddressMapDTO"] = {
        (a.speaker_character_id, a.addressee_character_id): a for a in bible.address_map
    }

    # (b) Collect attributions per ordered pair (only matched pairs)
    pair_attributions: dict[tuple[int, int], list["LineAttribution"]] = {}
    for attr in flat_attributions:
        if attr.speaker is None or attr.addressee is None:
            continue
        spk_id = name_to_id.get(attr.speaker.strip().lower())
        addr_id = name_to_id.get(attr.addressee.strip().lower())
        if spk_id is None or addr_id is None:
            # Unmatched names → safe default per D-43
            continue
        key = (spk_id, addr_id)
        pair_attributions.setdefault(key, []).append(attr)

    threshold_val = _threshold_value(settings.pronoun_confidence_threshold)
    resolved_map: dict[tuple[int, int], tuple[str, str]] = {}

    # Determine all pairs to process: observed pairs + existing address-map pairs
    all_pairs = set(pair_attributions.keys()) | set(existing_map.keys())

    for pair in all_pairs:
        spk_id, addr_id = pair
        attributions = pair_attributions.get(pair, [])

        # LOCK CHECK — lock always wins (D-34, D-54).
        # Must be FIRST — before transition check and confidence gate.
        existing = existing_map.get(pair)
        if existing is not None:
            locked = set(existing.locked_fields or [])
            if "self_term" in locked or "address_term" in locked:
                st = existing.self_term
                at = existing.address_term
                if st is not None and at is not None:
                    resolved_map[pair] = (st, at)
                    continue  # lock wins — skip transition + confidence gate

        # [Phase 6] TRANSITION CHECK — logged event authorizes term change (D-54).
        # Precedence: human lock > logged transition (this episode) > carried-forward > safe-default.
        if getattr(settings, "enable_relationship_events", True):
            transition = _find_transition_for_pair(
                getattr(bible, "relationship_events", []),
                spk_id, addr_id, episode_key,
            )
            if transition is not None:
                new_self, new_addr = _derive_transition_terms(
                    transition, resolved_map, addr_id, id_to_gender, settings
                )
                resolved_map[pair] = (new_self, new_addr)
                await upsert_address_pair(
                    session_factory,
                    series_id=series_id,
                    speaker_character_id=spk_id,
                    addressee_character_id=addr_id,
                    self_term=new_self,
                    address_term=new_addr,
                    valid_from_episode=episode_key,  # D-53: bump version marker
                    episode_key=episode_key,
                    source="inference",
                )
                logger.debug(
                    "reconcile: transition-authorized change for %d→%d: (%s/%s) at %s",
                    spk_id, addr_id, new_self, new_addr, episode_key,
                )
                continue  # transition handled — skip confidence gate

        # (c) Apply threshold gate
        survivors = [a for a in attributions if _confidence_value(a.confidence) >= threshold_val]

        if survivors:
            # Pair is "confirmed" — use existing Address Map entry if available;
            # the entry supplies the actual (self_term, address_term).
            if (
                existing is not None
                and existing.self_term is not None
                and existing.address_term is not None
            ):
                self_term = existing.self_term
                address_term = existing.address_term
            else:
                # No pre-existing entry: fall back to safe default for now;
                # upsert will create a new row with safe-default terms.
                addr_gender = id_to_gender.get(addr_id)
                self_term, address_term = get_safe_default(addr_gender, settings)

            resolved_map[pair] = (self_term, address_term)
            await upsert_address_pair(
                session_factory,
                series_id=series_id,
                speaker_character_id=spk_id,
                addressee_character_id=addr_id,
                self_term=self_term,
                address_term=address_term,
                episode_key=episode_key,
                source="inference",
            )

        else:
            # No survivors — all attributions below threshold (or no attributions).
            # Lock check already handled above — if we're here, pair is either unlocked or no lock.
            # Unlocked entry — SKIP it, fall through to safe default
            # (Success #4 invariant: below-threshold → safe default regardless of
            # what unlocked prior-episode Address Map rows say)
            addr_gender = id_to_gender.get(addr_id)
            st, at = get_safe_default(addr_gender, settings)
            resolved_map[pair] = (st, at)

    # (e) Reciprocal coherence check and write
    reciprocal_additions: list[tuple[tuple[int, int], tuple[str, str]]] = []
    for (spk_id, addr_id), (self_t, addr_t) in list(resolved_map.items()):
        recip_pair = KINSHIP_RECIPROCAL.get((self_t, addr_t))
        if recip_pair is not None:
            rev_key = (addr_id, spk_id)
            if rev_key not in resolved_map:
                reciprocal_additions.append((rev_key, recip_pair))

    for rev_key, (r_self, r_addr) in reciprocal_additions:
        rev_spk, rev_addr = rev_key
        resolved_map[rev_key] = (r_self, r_addr)
        await upsert_address_pair(
            session_factory,
            series_id=series_id,
            speaker_character_id=rev_spk,
            addressee_character_id=rev_addr,
            self_term=r_self,
            address_term=r_addr,
            episode_key=episode_key,
            source="inference",
        )
        logger.debug(
            "reconcile: inferred reciprocal %d→%d as (%s/%s)",
            rev_spk,
            rev_addr,
            r_self,
            r_addr,
        )

    return resolved_map
