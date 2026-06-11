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

# D-90: Additive fill of KINSHIP_RECIPROCAL gaps (bác/cháu, chú/cháu, cô/cháu, thầy/em, tao/mày)
# Missing pairs verified C4 in harness review. Forward AND reverse keys added so round-trips work.
KINSHIP_RECIPROCAL.update(
    {
        ("bác", "cháu"): ("cháu", "bác"),  # uncle/aunt (older-than-parent) ↔ niece/nephew
        ("cháu", "bác"): ("bác", "cháu"),
        ("chú", "cháu"): ("cháu", "chú"),  # uncle (younger-than-parent) ↔ niece/nephew
        ("cháu", "chú"): ("chú", "cháu"),
        ("cô", "cháu"): ("cháu", "cô"),  # aunt (father's sister) ↔ niece/nephew
        ("cháu", "cô"): ("cô", "cháu"),
        ("thầy", "em"): ("em", "thầy"),  # teacher ↔ student
        ("em", "thầy"): ("thầy", "em"),
        ("tao", "mày"): ("mày", "tao"),  # intimate/rude peer
        ("mày", "tao"): ("tao", "mày"),
    }
)

# KNOWN_PRONOUN_TERMS — shared vocabulary for the Bible editor combo (D-86).
# Single source of truth: exposed via /api/pronouns; never duplicated in the frontend.
# Split into self_terms and address_terms for gender-aware picker hints.
KNOWN_PRONOUN_TERMS_SELF: list[str] = [
    "tôi",
    "con",
    "em",
    "anh",
    "chị",
    "cháu",
    "mày",
    "tao",
    "bạn",
    # WR-06: parental/elder self-terms that appear as speaker-side terms in KINSHIP_RECIPROCAL
    # (bố/mẹ/cha address "con"; ông/bà address "cháu"/"con"; bác/chú/cô/thầy address "cháu"/"em").
    # Absent from the dropdown forces the user to the "custom…" escape hatch, bypassing the D-86
    # typo guard for the most common parental pronouns.
    "bố",
    "mẹ",
    "cha",
    "ông",
    "bà",
    "bác",
    "chú",
    "cô",
    "thầy",
]
KNOWN_PRONOUN_TERMS_ADDRESS: list[str] = [
    "bạn",
    "anh",
    "chị",
    "em",
    "con",
    "cháu",
    "ông",
    "bà",
    "bố",
    "mẹ",
    "cha",
    "mày",
    "thầy",
    "dì",
    "cậu",
    "bác",
    "chú",
    "cô",
]

# ---------------------------------------------------------------------------
# Safe-default constants (D-45, RESEARCH.md Key Pattern 5)
# ---------------------------------------------------------------------------
SAFE_DEFAULT_SELF = "tôi"
SAFE_DEFAULT_ADDRESS_MALE = "anh"
SAFE_DEFAULT_ADDRESS_FEMALE = "chị"
SAFE_DEFAULT_ADDRESS_NEUTRAL = "bạn"

# H3/B4 fix: classical / historical / wuxia / xianxia / cultivation safe-default ladder.
# These are SAFE, non-presumptuous, respectful classical Sino-Vietnamese terms — the
# classical analogue of the modern tôi + anh/chị/bạn floor. They never risk an intimate
# or superior term (e.g. 'ngươi', which is presumptuous/superior, is deliberately NOT a
# default), and they lean non-gendered when the addressee gender is unknown.
#   self:    'tại hạ' (humble "this one")
#   address: male/unknown → 'các hạ' (respectful, non-gendered "you"); female →
#            'cô nương' (respectful "young lady"). Unknown leans non-gendered → 'các hạ'.
# [linguist: confirm final terms]
SAFE_DEFAULT_SELF_CLASSICAL = "tại hạ"
SAFE_DEFAULT_ADDRESS_CLASSICAL_MALE = "các hạ"
SAFE_DEFAULT_ADDRESS_CLASSICAL_FEMALE = "cô nương"
SAFE_DEFAULT_ADDRESS_CLASSICAL_NEUTRAL = "các hạ"

# Register tokens (substring match, lowercased) that select the CLASSICAL ladder.
# Covers English genre labels and Vietnamese genre names a Pass-1 register inference may emit.
_CLASSICAL_REGISTER_TOKENS: frozenset[str] = frozenset(
    {
        "classical",
        "historical",
        "wuxia",
        "xianxia",
        "cultivation",
        "period",
        "ancient",
        "martial",
        "imperial",
        "dynasty",
        "cổ trang",
        "co trang",
        "tiên hiệp",
        "kiếm hiệp",
        "tu tiên",
        "võ hiệp",
    }
)


def _is_classical_register(register: str | None) -> bool:
    """True when ``register`` names a classical/historical/wuxia/xianxia/cultivation tone (H3/B4).

    Substring + case-insensitive so 'Xianxia / Cultivation', 'historical drama', or the
    Vietnamese 'cổ trang' all select the classical safe-default ladder. None/empty → False
    (modern ladder), preserving the existing behaviour on a register-less Bible.
    """
    if not register:
        return False
    low = register.lower()
    return any(tok in low for tok in _CLASSICAL_REGISTER_TOKENS)


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
    register: str | None = None,
) -> tuple[str, str]:
    """Return (self_term, address_term) for low-confidence attributions (D-45, H3/B4).

    Precedence:
      1. settings.pronoun_safe_default (user override) — returned verbatim, ALWAYS first.
      2. Genre/register-aware ladder (H3/B4): a classical/historical/wuxia/xianxia/
         cultivation register selects the CLASSICAL ladder (self 'tại hạ'; address
         'các hạ' for male/unknown, 'cô nương' for female). Otherwise the modern ladder
         (self 'tôi'; address 'anh'/'chị'/'bạn' by addressee gender).

    Both ladders stay SAFE — never an intimate ('em') or presumptuous/superior ('ngươi')
    term — and lean non-gendered when addressee_gender is unknown.

    Args:
        addressee_gender: Gender string of the addressee ("male"/"female"/None/other).
        settings:         TrezarrSettings instance (provides pronoun_safe_default).
        register:         Optional series register/tone (e.g. "xianxia"); thread it with
                          getattr(bible, "register_value", None). None → modern ladder
                          (unchanged default behaviour).

    Returns:
        (self_term, address_term) tuple for safe neutral/polite usage.
    """
    if settings.pronoun_safe_default is not None:
        return settings.pronoun_safe_default  # user override wins first

    # H3/B4 fix: classical register ladder. Lean non-gendered when gender is unknown
    # (the classical neutral address is safe for either gender). [linguist: confirm terms]
    if _is_classical_register(register):
        address = {
            "male": SAFE_DEFAULT_ADDRESS_CLASSICAL_MALE,
            "female": SAFE_DEFAULT_ADDRESS_CLASSICAL_FEMALE,
        }.get(addressee_gender or "", SAFE_DEFAULT_ADDRESS_CLASSICAL_NEUTRAL)
        return (SAFE_DEFAULT_SELF_CLASSICAL, address)

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
        if (event.character_a_id == spk_id and event.character_b_id == addr_id) or (
            event.character_a_id == addr_id and event.character_b_id == spk_id
        ):
            return event
    return None


def _derive_transition_terms(
    transition: "RelationshipEventDTO",
    survivors: "list",
    existing: "AddressMapDTO | None",
    addr_id: int,
    id_to_gender: dict,
    settings: "TrezarrSettings",
    register: str | None = None,
) -> tuple[str, str]:
    """Derive (self_term, address_term) for a transition (D-54 three-step order, CR-02+WR-03):

    1. LLM-suggested terms from transition (suggested_self_term / suggested_address_term),
       if BOTH are present — in-memory same-pass suggestion from RelationshipEventInference.
    2. ELSE if this episode produced high-confidence survivors AND the existing AddressMapDTO
       has non-None self_term/address_term: use the existing entry's terms — this episode's
       Pass-1-refreshed confident inference for the ordered pair.
    3. ELSE get_safe_default — safe fallback when no confident attribution exists.

    Note: WR-03 directional concern is resolved because terms come from the per-(spk_id,
    addr_id) directional resolution (existing entry or survivors for THIS ordered pair),
    not from the unordered event's stored suggested terms alone.

    Args:
        transition:  The RelationshipEventDTO that authorized this change.
        survivors:   High-confidence LineAttribution objects for this (spk_id, addr_id) pair.
        existing:    The current AddressMapDTO for this pair (None if no prior entry).
        addr_id:     Addressee character ID (for gender-based safe default).
        id_to_gender: char_id → gender lookup.
        settings:    TrezarrSettings (pronoun_safe_default).
        register:    Optional series register/tone (H3/B4) — threaded into the Step-3
                     safe-default so a classical series uses the classical ladder.
    """
    # Step 1: LLM-suggested terms from transition (in-memory, same-pass)
    if transition.suggested_self_term and transition.suggested_address_term:
        return (transition.suggested_self_term, transition.suggested_address_term)
    # Step 2: This episode's confident attribution for the ordered pair
    if survivors and existing is not None and existing.self_term and existing.address_term:
        return (existing.self_term, existing.address_term)
    # Step 3: Carry forward the established pair (scy precedence: carried > safe-default).
    # D-01: lock > genuine evolution (event WITH usable terms) > carried Bible pair > safe-default.
    # A term-less event on an ESTABLISHED dyad must not flatten the existing pronoun pair
    # to a stranger safe-default — only truly-new dyads (no prior entry) use get_safe_default.
    # Audit 260611-ru6 R1: Leg B Steven→Khonshu (tôi/ông→tôi/anh) and Leg A Mei→Han
    # (muội/huynh→tại hạ/các hạ) were both caused by this Step 3 fall-through.
    if existing is not None and existing.self_term and existing.address_term:
        return (existing.self_term, existing.address_term)
    # Step 4: Truly-new dyad (no prior entry or entry with None terms) → safe default.
    # Success #4 invariant: never invent an intimate pronoun for a brand-new relationship.
    addr_gender = id_to_gender.get(addr_id)
    return get_safe_default(addr_gender, settings, register=register)


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
    # B3/C6: reuse the single shared in-memory aliases helper (honorific stripping) so
    # 'Elder Zhou' / 'Mr. Han' resolve to the seeded 'Zhou' / 'Han' row. _resolve_char_id
    # tries the EXACT name first and the honorific-stripped alias only as a fallback, so two
    # distinct characters differing only by an honorific never collide. Function-local import
    # keeps this module free of heavy/SQLAlchemy imports (Pitfall D / D-39) + avoids a cycle.
    from trezarr.translate.engine import _resolve_char_id

    # H3/B4 fix: capture the series register once so every safe-default in this episode uses
    # the genre-aware ladder. getattr-with-default keeps SimpleNamespace test bibles (no
    # register_value field) → None (modern ladder, unchanged behaviour).
    register = getattr(bible, "register_value", None)

    # (a) Build EXACT-keyed name→char_id index (CR-01); _resolve_char_id adds the honorific
    # fallback at lookup (B3) without aliasing two distinct characters onto one id.
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
        spk_id = _resolve_char_id(name_to_id, attr.speaker)
        addr_id = _resolve_char_id(name_to_id, attr.addressee)
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

        # (c) Compute survivors BEFORE transition check so the transition branch can use them.
        # CR-02/WR-03: _derive_transition_terms (step 2 fallback) needs survivors to determine
        # whether this episode produced confident attributions for the ordered pair.
        survivors = [a for a in attributions if _confidence_value(a.confidence) >= threshold_val]

        # [Phase 6] TRANSITION CHECK — logged event authorizes term change (D-54).
        # Precedence: human lock > logged transition (this episode) > carried-forward > safe-default.
        # R2 fix (260611-ru6): skip the transition branch entirely when episode_key == "S00E00".
        # S00E00 is the cold-Bible fallback key produced when the subtitle stem cannot be parsed
        # (e.g. a Plex "NxNN" stem before the NxNN regex fix lands). All 12 Leg A series-1
        # relationship_events are stamped S00E00, so without this guard every run of ANY Plex
        # episode triggers all events and re-fires the cold-Bible safe-default flatten. The guard
        # is AFTER the lock check (lock always wins, even on S00E00 keys) and BEFORE the
        # transition check. An S00E00 episode proceeds to the survivors/carry-forward path.
        if getattr(settings, "enable_relationship_events", True) and episode_key != "S00E00":
            transition = _find_transition_for_pair(
                getattr(bible, "relationship_events", []),
                spk_id,
                addr_id,
                episode_key,
            )
            if transition is not None:
                new_self, new_addr = _derive_transition_terms(
                    transition,
                    survivors,
                    existing,
                    addr_id,
                    id_to_gender,
                    settings,
                    register=register,
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
                    spk_id,
                    addr_id,
                    new_self,
                    new_addr,
                    episode_key,
                )
                continue  # transition handled — skip confidence gate

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
                self_term, address_term = get_safe_default(addr_gender, settings, register=register)

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
            #
            # B3 within-episode consistency: `all_pairs` is a SET, so each ordered (spk_id,
            # addr_id) dyad is processed exactly once and resolved_map holds exactly ONE
            # (self_term, address_term) per dyad per episode. Pass-3 then looks the dyad up in
            # resolved_map for EVERY line attributed to it, so low-confidence lines of a dyad
            # already get the dyad's single resolved pair — there is no per-line re-guessing to
            # override here (Success #3: no mid-episode flip is structurally guaranteed).
            #
            # CARRY-FORWARD (scy — moat-core fix for cross-episode pronoun drift):
            # Precedence ladder: human lock > genuine evolution (transition) > carried Bible pair
            # > current-episode safe-default (truly-new dyad only).
            # Lock and transition branches already `continue`d above, so any pair reaching here
            # is either unlocked-with-prior-entry or has no prior entry at all.
            # If a prior unlocked entry exists with non-None terms, CARRY it forward into
            # resolved_map — do NOT drop an established (anh/em) to a fresh safe-default
            # with no narrative cause. Only truly-new dyads (no prior entry, or prior entry with
            # None terms) fall through to get_safe_default.
            # NOTE: carry-forward does NOT call upsert_address_pair — the resolved_map entry is
            # sufficient for Pass-3 hints (engine.py 1785); valid_from_episode stays as-is in the
            # DB (lower-risk minimal fix; the survivors-branch upsert already handles the update
            # when there IS a confident witness this episode).
            if (
                existing is not None
                and existing.self_term is not None
                and existing.address_term is not None
            ):
                resolved_map[pair] = (existing.self_term, existing.address_term)
                logger.debug(
                    "reconcile: carried prior pair for %d→%d: (%s/%s) at %s",
                    spk_id,
                    addr_id,
                    existing.self_term,
                    existing.address_term,
                    episode_key,
                )
                continue

            # Truly-new dyad (no prior entry, or prior entry has None terms) → safe default.
            # Success #4 invariant: we never invent an intimate pronoun from thin air on a
            # genuinely-new or term-less relationship.
            # H3/B4: register-aware safe default (classical ladder on a xianxia/historical series).
            addr_gender = id_to_gender.get(addr_id)
            st, at = get_safe_default(addr_gender, settings, register=register)
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
