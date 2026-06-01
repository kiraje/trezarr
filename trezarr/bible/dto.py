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

from pydantic import BaseModel, ConfigDict


class SeriesDTO(BaseModel):
    """Per-series Bible header row DTO — one per (arr_kind, arr_instance, arr_series_id).

    Attributes:
        id:              Surrogate integer primary key.
        arr_kind:        Source *arr service: "sonarr" or "radarr" (D-33).
        arr_instance:    Instance name (default "default"; v2 multi-instance hook).
        arr_series_id:   Integer series ID as returned by pyarr (D-33).
        tvdb_id:         TVDB ID at series creation time (denormalized, nullable, D-33).
        tmdb_id:         TMDB ID at series creation time (denormalized, nullable, D-33).
        register:        Series tone/register string; None until Phase 5 sets it (D-35).
        arr_metadata:    JSON snapshot of Phase-3 discovery payload (D-35).
        locked_fields:   JSON list of field names locked by the user (D-34).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    arr_kind: str
    arr_instance: str
    arr_series_id: int
    tvdb_id: int | None = None
    tmdb_id: int | None = None
    register: str | None = None
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
        register:        Series tone/register; None until Phase 5 sets via merge_inferred.
        arr_metadata:    JSON snapshot of Phase-3 discovery payload (D-35).
        characters:      List of CharacterDTOs for this series (eagerly loaded).
        terms:           List of TermDTOs for this series (eagerly loaded).
        locked_fields:   JSON list of field names locked by the user (D-34).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    arr_kind: str
    arr_instance: str
    arr_series_id: int
    register: str | None = None
    arr_metadata: dict[str, Any] = {}
    characters: list[CharacterDTO] = []
    terms: list[TermDTO] = []
    locked_fields: list[str] = []
