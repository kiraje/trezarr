"""Pydantic DTOs at the trezarr.bible.store boundary (D-39).

SQLAlchemy models stay inside store.py; everything that crosses out is a DTO.
Field names mirror the SQLAlchemy column names 1:1 so model_validate(row,
from_attributes=True) is a no-op rename.

Design decisions honoured:
  D-39  No SQLAlchemy import is reachable through any public name in this module.
        Phase 5+ may safely import from trezarr.bible.dto without pulling in SQLA.
        Enforced by import-graph contract test in tests/bible/test_dto_boundary.py
        (uses inspect.getsource — not brittle dir() name inspection).
  D-33  tvdb_id/tmdb_id are nullable denormalized fields captured at series creation.
  D-34  locked_fields defaults to [] (empty list). Pydantic v2 copies mutable
        defaults per-instance, so list literals are safe here (unlike TrezarrSettings
        where pydantic-settings requires Field(default_factory=list) for env-var
        deserialization reasons).
  D-35  arr_metadata is a dict[str, Any] snapshot; register is str | None (NULL
        until Phase 5 sets it via merge_inferred).

Cross-AI review MEDIUM finding:
  BibleEventDTO.created_at is typed as `datetime | None` (NOT `Any`). Pydantic v2
  automatically coerces ISO-8601 strings to `datetime` objects when the field
  annotation is `datetime | None`, so this works correctly whether the value comes
  from SQLAlchemy (a datetime object) or from JSON deserialization (an ISO-8601
  string). Changed from `Any` per review.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SeriesDTO(BaseModel):
    """Per-series Bible header row DTO — one per (arr_kind, arr_instance, arr_series_id).

    Attributes:
        id:              Surrogate integer primary key.
        arr_kind:        Source *arr service: "sonarr" or "radarr" (D-33).
        arr_instance:    Instance name (default "default"; v2 multi-instance hook).
        arr_series_id:   Integer series ID as returned by pyarr (D-33).
        tvdb_id:         TVDB ID at series creation time (denormalized, nullable, D-33).
        tmdb_id:         TMDB ID at series creation time (denormalized, nullable, D-33).
        register_value:  Series tone/register string; None until Phase 5 sets it (D-35).
                         CR-02: the Python attribute is named ``register_value`` because
                         a field literally named ``register`` shadows Pydantic v2's
                         deprecated ``BaseModel.register`` classmethod, producing a
                         UserWarning at every class load that future Pydantic releases
                         may upgrade to a hard error. The alias keeps the serialized
                         JSON key and SQLA-bridge column name as ``register`` for
                         backward compatibility.
        arr_metadata:    JSON snapshot of Phase-3 discovery payload (D-35).
        locked_fields:   JSON list of field names locked by the user (D-34).
    """

    # CR-02: populate_by_name=True so model_validate(row, from_attributes=True)
    # can accept either the Python attribute name (``register_value``) OR the
    # alias (``register``) when loading from the SQLA row — whose attribute is
    # named ``register``.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    arr_kind: str
    arr_instance: str
    arr_series_id: int
    tvdb_id: int | None = None
    tmdb_id: int | None = None
    register_value: str | None = Field(default=None, alias="register")
    arr_metadata: dict[str, Any] = {}
    locked_fields: list[str] = []


class CharacterDTO(BaseModel):
    """Per-character Bible entry DTO (BIBLE-02).

    Attributes:
        id:                  Surrogate integer primary key.
        series_id:           FK → series.id.
        original_latin_name: Character name in original-language Latin form.
        gender:              Optional gender string (free-form).
        rough_age:           Optional rough age descriptor (e.g. "adult", "teen").
        role:                Optional role descriptor (e.g. "detective", "villain").
        locked_fields:       JSON list of locked field names (D-34).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    original_latin_name: str
    gender: str | None = None
    rough_age: str | None = None
    role: str | None = None
    locked_fields: list[str] = []


class TermDTO(BaseModel):
    """Term Dictionary entry DTO (BIBLE-04).

    Attributes:
        id:                   Surrogate integer primary key.
        series_id:            FK → series.id.
        source_term:          Source-language term (proper noun, title, place, jargon).
        vietnamese_rendering: Canonical Vietnamese rendering of the term.
        category:             Optional category: proper_noun|title|place|jargon.
        locked_fields:        JSON list of locked field names (D-34).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    source_term: str
    vietnamese_rendering: str
    category: str | None = None
    locked_fields: list[str] = []


class AddressMapDTO(BaseModel):
    """Directed speaker→addressee pronoun-pair entry DTO (BIBLE-03).

    model_config mirrors CharacterDTO: from_attributes=True only (no populate_by_name
    needed — no alias required, column names match Python field names 1:1).

    Attributes:
        id:                    Surrogate integer primary key.
        series_id:             FK → series.id.
        speaker_character_id:  FK → character.id (the one speaking).
        addressee_character_id: FK → character.id (the one being addressed).
        self_term:             Vietnamese self-reference term used by speaker.
        address_term:          Vietnamese address term for the addressee.
        valid_from_episode:    Optional episode key from which this mapping applies.
        locked_fields:         JSON list of locked field names (D-34).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    speaker_character_id: int
    addressee_character_id: int
    self_term: str | None = None
    address_term: str | None = None
    valid_from_episode: str | None = None
    locked_fields: list[str] = []   # D-34: mutable default safe in Pydantic v2 (see dto.py:14)


class RelationshipEventDTO(BaseModel):
    """Relationship transition entry DTO (BIBLE-07).

    model_config mirrors AddressMapDTO: from_attributes=True only — no aliases needed,
    column names match Python field names 1:1.

    Note: suggested_self_term / suggested_address_term are NOT persisted to DB
    (the relationship_event schema is locked from Phase 4, D-31). They are
    populated from RelationshipEventInference in-memory and carried through
    reconciliation only.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    character_a_id: int
    character_b_id: int
    episode_marker: str
    description: str | None = None
    created_at: datetime | None = None  # datetime | None — Pydantic v2 coerces ISO-8601
    # In-memory only (from inference, not stored in DB):
    suggested_self_term: str | None = None
    suggested_address_term: str | None = None


class BibleEventDTO(BaseModel):
    """Append-only audit log entry DTO — D-32 provenance schema.

    Attributes:
        id:          Surrogate integer primary key.
        series_id:   FK → series.id.
        episode_key: Optional episode where the inference was made.
        entity_type: Entity being updated: "character"|"term_dictionary"|"series".
        entity_id:   ID of the entity row being updated.
        field:       Name of the field that changed.
        old_value:   Prior value (None if new row).
        new_value:   Incoming value.
        source:      Provenance: "inference"|"lock"|"import"|"system" (D-32).
        created_at:  UTC timestamp. Typed as datetime | None (NOT Any) so Pydantic v2
                     coerces ISO-8601 strings automatically (cross-AI review MEDIUM finding).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    episode_key: str | None = None
    entity_type: str
    entity_id: int
    field: str
    old_value: Any = None
    new_value: Any = None
    source: str
    created_at: datetime | None = None   # datetime | None, NOT Any — Pydantic v2 coerces ISO-8601


class SeriesBibleDTO(BaseModel):
    """Aggregate Series Bible DTO returned by load_series_bible() (D-39).

    This is the primary read-side contract for Phase 5+ callers. It carries the
    register (None until Phase 5 sets it), the arr_metadata snapshot for LLM
    grounding, and the eagerly-loaded characters and terms lists.

    Attributes:
        id:              Surrogate integer primary key of the series row.
        arr_kind:        Source *arr service: "sonarr" or "radarr".
        arr_instance:    Instance name (default "default").
        arr_series_id:   Integer series ID as returned by pyarr.
        register_value:  Series tone/register; None until Phase 5 sets via merge_inferred.
                         CR-02: see SeriesDTO.register_value — same shadowing fix
                         applies here; alias ``register`` keeps JSON / SQLA bridge
                         backward compatible.
        arr_metadata:    JSON snapshot of Phase-3 discovery payload (D-35).
        characters:      List of CharacterDTOs for this series (eagerly loaded).
        terms:           List of TermDTOs for this series (eagerly loaded).
        locked_fields:   JSON list of field names locked by the user (D-34).
    """

    # CR-02: populate_by_name=True so explicit-keyword construction
    # ``SeriesBibleDTO(register_value=..., ...)`` works alongside the alias.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    arr_kind: str
    arr_instance: str
    arr_series_id: int
    register_value: str | None = Field(default=None, alias="register")
    arr_metadata: dict[str, Any] = {}
    characters: list[CharacterDTO] = []
    terms: list[TermDTO] = []
    address_map: list[AddressMapDTO] = []   # Eagerly loaded by load_series_bible Phase 5+
    relationship_events: list[RelationshipEventDTO] = []  # [Phase 6 ADDITIVE — safe default []]
    locked_fields: list[str] = []
