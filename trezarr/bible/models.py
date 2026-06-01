"""SQLAlchemy 2.0 typed declarative models for the Series Bible (D-31, D-32, D-33).

Design decisions honoured:
  D-31  A single Alembic baseline migration creates ALL 7 long-term Bible tables.
        This module defines the corresponding SQLAlchemy 2.0 typed models.
        Tables: series, character, term_dictionary, address_map,
                relationship_event, bible_event, processed_file.
  D-32  bible_event is an append-only audit log (series_id, episode_key,
        entity_type, entity_id, field, old_value, new_value, source, created_at).
        source ∈ {inference, lock, import, system}.
  D-33  series uses a surrogate id PK + UNIQUE(arr_kind, arr_instance, arr_series_id).
        tvdb_id/tmdb_id stored as denormalized nullable columns.
  D-34  Every entity table (series, character, term_dictionary) carries
        locked_fields: JSON (list of field names), default=list callable.
        Mutable default MUST be a callable (list), not a literal [] — SQLAlchemy
        needs a callable so each row instance gets its own fresh list.
  D-35  series.arr_metadata is a JSON column (Phase-3 snapshot); series.register
        starts NULL (Phase 5 sets it via merge_inferred).
  D-39  SQLAlchemy stays inside the bible/ package. Downstream consumers (Phase 5+)
        import Pydantic DTOs from bible/dto.py, never from this module.

address_map and relationship_event are created EMPTY in Phase 4:
  - address_map: Phase 5 populates (BIBLE-03, speaker/addressee attribution).
  - relationship_event: Phase 6 populates (BIBLE-07, relationship evolution).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trezarr.db.base import Base


class Series(Base):
    """Per-series Bible header row — one per (arr_kind, arr_instance, arr_series_id).

    Attributes:
        id:              Surrogate integer primary key.
        arr_kind:        Source *arr service: "sonarr" or "radarr" (D-33).
        arr_instance:    Instance name (default "default"; v2 multi-instance hook).
        arr_series_id:   Integer series ID as returned by pyarr (D-33).
        tvdb_id:         TVDB ID at series creation time (denormalized, nullable).
        tmdb_id:         TMDB ID at series creation time (denormalized, nullable).
        register:        Series tone/register string; NULL until Phase 5 sets it (D-35).
        arr_metadata:    JSON snapshot of Phase-3 MediaItem arr payload (D-35).
        locked_fields:   JSON list of field names locked by the user (D-34).
        characters:      Relationship to Character rows for this series.
        terms:           Relationship to TermDictionary rows for this series.
    """

    __tablename__ = "series"
    __table_args__ = (
        UniqueConstraint(
            "arr_kind", "arr_instance", "arr_series_id",
            name="uq_series_arr_identity",
        ),
        CheckConstraint(
            "arr_kind IN ('sonarr', 'radarr')",
            name="ck_series_arr_kind",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    arr_kind: Mapped[str] = mapped_column(String)                       # D-33: sonarr|radarr
    arr_instance: Mapped[str] = mapped_column(String, default="default") # D-33: multi-instance hook
    arr_series_id: Mapped[int] = mapped_column(Integer)                  # D-33: pyarr integer ID
    tvdb_id: Mapped[int | None] = mapped_column(Integer, default=None)   # D-33: denormalized
    tmdb_id: Mapped[int | None] = mapped_column(Integer, default=None)   # D-33: denormalized
    register: Mapped[str | None] = mapped_column(String, default=None)   # D-35: Phase 5 sets
    arr_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # D-35 snapshot
    locked_fields: Mapped[list[str]] = mapped_column(JSON, default=list)      # D-34 callable!

    characters: Mapped[list["Character"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    terms: Mapped[list["TermDictionary"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )
    address_maps: Mapped[list["AddressMap"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class Character(Base):
    """A named character in a series — BIBLE-02 column shape.

    Attributes:
        id:                  Surrogate integer primary key.
        series_id:           FK → series.id.
        original_latin_name: Character name in original-language Latin form.
        gender:              Optional gender string (free-form).
        rough_age:           Optional rough age descriptor (e.g. "adult", "teen").
        role:                Optional role descriptor (e.g. "detective", "villain").
        locked_fields:       JSON list of locked field names (D-34).
        series:              Back-relationship to the parent Series.
    """

    __tablename__ = "character"
    __table_args__ = (
        Index("ix_character_series_name", "series_id", "original_latin_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    original_latin_name: Mapped[str] = mapped_column(String, nullable=False)
    gender: Mapped[str | None] = mapped_column(String, default=None)
    rough_age: Mapped[str | None] = mapped_column(String, default=None)
    role: Mapped[str | None] = mapped_column(String, default=None)
    locked_fields: Mapped[list[str]] = mapped_column(JSON, default=list)  # D-34

    series: Mapped["Series"] = relationship(back_populates="characters")


class TermDictionary(Base):
    """A source-language term with its Vietnamese rendering — BIBLE-04 column shape.

    Attributes:
        id:                   Surrogate integer primary key.
        series_id:            FK → series.id.
        source_term:          Source-language term (proper noun, title, place, jargon).
        vietnamese_rendering: Canonical Vietnamese rendering of the term.
        category:             Optional category: proper_noun|title|place|jargon.
        locked_fields:        JSON list of locked field names (D-34).
        series:               Back-relationship to the parent Series.
    """

    __tablename__ = "term_dictionary"
    __table_args__ = (
        Index("ix_term_dictionary_series_term", "series_id", "source_term"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    source_term: Mapped[str] = mapped_column(String, nullable=False)
    vietnamese_rendering: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, default=None)
    locked_fields: Mapped[list[str]] = mapped_column(JSON, default=list)  # D-34

    series: Mapped["Series"] = relationship(back_populates="terms")


class AddressMap(Base):
    """Directed speaker→addressee pronoun-pair entry — EMPTY in Phase 4.

    Phase 5 populates this table (BIBLE-03, speaker/addressee attribution).
    The schema is locked here so Phase 5 only needs to INSERT rows.

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

    __tablename__ = "address_map"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    speaker_character_id: Mapped[int] = mapped_column(ForeignKey("character.id"), nullable=False)
    addressee_character_id: Mapped[int] = mapped_column(ForeignKey("character.id"), nullable=False)
    self_term: Mapped[str | None] = mapped_column(String, default=None)
    address_term: Mapped[str | None] = mapped_column(String, default=None)
    valid_from_episode: Mapped[str | None] = mapped_column(String, default=None)
    locked_fields: Mapped[list[str]] = mapped_column(JSON, default=list)  # D-34

    series: Mapped["Series"] = relationship(back_populates="address_maps")


class RelationshipEvent(Base):
    """A recorded character relationship transition — EMPTY in Phase 4.

    Phase 6 populates this table (BIBLE-07, relationship evolution). The schema
    is locked here so Phase 6 only needs to INSERT rows.

    Attributes:
        id:             Surrogate integer primary key.
        series_id:      FK → series.id.
        character_a_id: FK → character.id (first party in the relationship).
        character_b_id: FK → character.id (second party in the relationship).
        episode_marker: Episode key string where the transition occurs.
        description:    Optional narrative description of the transition.
        created_at:     UTC timestamp, set by DB server default.
    """

    __tablename__ = "relationship_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    character_a_id: Mapped[int] = mapped_column(ForeignKey("character.id"), nullable=False)
    character_b_id: Mapped[int] = mapped_column(ForeignKey("character.id"), nullable=False)
    episode_marker: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class BibleEvent(Base):
    """Append-only audit log of every Bible mutation — D-32 provenance schema.

    Every call to merge_inferred() that changes a field writes one BibleEvent
    inside the SAME transaction as the current-row UPDATE. This table is the
    foundation for Phase 6 self-review audits and Phase 8 lock-provenance UI.

    Attributes:
        id:          Surrogate integer primary key.
        series_id:   FK → series.id.
        episode_key: Optional episode where the inference was made.
        entity_type: Entity being updated: "character"|"term_dictionary"|"series".
        entity_id:   ID of the entity row being updated.
        field:       Name of the field that changed.
        old_value:   JSON-encoded prior value (None if new row).
        new_value:   JSON-encoded incoming value.
        source:      Provenance: "inference"|"lock"|"import"|"system" (D-32).
        created_at:  UTC timestamp, set by DB server default.
    """

    __tablename__ = "bible_event"
    __table_args__ = (
        CheckConstraint(
            "source IN ('inference', 'lock', 'import', 'system')",
            name="ck_bible_event_source",
        ),
        Index(
            "ix_bible_event_series_entity_time",
            "series_id", "entity_type", "entity_id", "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    episode_key: Mapped[str | None] = mapped_column(String, default=None)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[Any | None] = mapped_column(JSON, default=None)  # JSON for structured fields
    new_value: Mapped[Any | None] = mapped_column(JSON, default=None)  # JSON for structured fields
    source: Mapped[str] = mapped_column(String, nullable=False)        # D-32 enum
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )


class ProcessedFile(Base):
    """Idempotency ledger — JSON-ledger swap target (D-37, D-20 schema compat).

    Column names MUST match trezarr.output.ledger.LedgerEntry field names 1:1
    (D-20 wrote those names with this exact swap in mind). The surrogate id PK
    is added per RESEARCH A2 to avoid the compound-PK fragility of source_path
    as PK on a string column.

    Attributes:
        id:              Surrogate integer primary key.
        source_path:     Absolute path to the source subtitle (UNIQUE constraint).
        output_path:     Absolute path to the translated .vi.srt sidecar, or None.
        status:          Processing status: "done"|"quarantined"|"in_progress".
        content_hash:    SHA-256[:16] of the source file bytes (skip/regenerate key).
        series_id:       Optional series identifier (string — matches LedgerEntry).
        source_lang:     Optional ISO-639 source language code.
        episode_key:     Optional episode identifier string.
        translated_at:   ISO-8601 UTC timestamp of last successful translation.
        quarantine_path: Absolute path to the quarantine JSON artifact, or None.
    """

    __tablename__ = "processed_file"
    __table_args__ = (
        CheckConstraint(
            "status IN ('done', 'quarantined', 'in_progress')",
            name="ck_processed_file_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    output_path: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, nullable=False)           # D-20 enum
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    series_id: Mapped[str | None] = mapped_column(String, default=None)   # string per LedgerEntry
    source_lang: Mapped[str | None] = mapped_column(String, default=None)
    episode_key: Mapped[str | None] = mapped_column(String, default=None)
    translated_at: Mapped[str | None] = mapped_column(String, default=None)
    quarantine_path: Mapped[str | None] = mapped_column(String, default=None)
