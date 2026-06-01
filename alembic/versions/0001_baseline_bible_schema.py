"""Baseline migration: create all 7 long-term Series Bible tables (D-31, D-32, D-33).

Revision ID: 0001
Revises: None
Create Date: 2026-06-01

This is a hand-authored migration (NOT autogenerate) to avoid drift risk on
the foundational schema. All 7 tables are created in FK-safe order:
  series → character → term_dictionary → address_map → relationship_event
  → bible_event → processed_file

DB-level constraints (per cross-AI review MEDIUM finding):
  - series.arr_kind CHECK IN ('sonarr', 'radarr')
  - bible_event.source CHECK IN ('inference', 'lock', 'import', 'system')
  - processed_file.status CHECK IN ('done', 'quarantined', 'in_progress')

DB-level indexes (per cross-AI review MEDIUM finding):
  - ix_character_series_name (character.series_id, character.original_latin_name)
  - ix_term_dictionary_series_term (term_dictionary.series_id, term_dictionary.source_term)
  - ix_bible_event_series_entity_time (bible_event.series_id, entity_type, entity_id, created_at)
  - processed_file.source_path: covered by the UNIQUE constraint on the column

JSON column server_defaults:
  - locked_fields columns: server_default='[]'
  - arr_metadata column:   server_default='{}'
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all 7 Series Bible tables with constraints and indexes."""

    # 1 — series (root entity; no FK dependencies)
    op.create_table(
        "series",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("arr_kind", sa.String, nullable=False),
        sa.Column("arr_instance", sa.String, nullable=False, server_default="default"),
        sa.Column("arr_series_id", sa.Integer, nullable=False),
        sa.Column("tvdb_id", sa.Integer, nullable=True),
        sa.Column("tmdb_id", sa.Integer, nullable=True),
        sa.Column("register", sa.String, nullable=True),
        sa.Column("arr_metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("locked_fields", sa.JSON, nullable=False, server_default="[]"),
        sa.UniqueConstraint(
            "arr_kind", "arr_instance", "arr_series_id",
            name="uq_series_arr_identity",
        ),
        sa.CheckConstraint(
            "arr_kind IN ('sonarr', 'radarr')",
            name="ck_series_arr_kind",
        ),
    )

    # 2 — character (FK → series)
    op.create_table(
        "character",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id"), nullable=False),
        sa.Column("original_latin_name", sa.String, nullable=False),
        sa.Column("gender", sa.String, nullable=True),
        sa.Column("rough_age", sa.String, nullable=True),
        sa.Column("role", sa.String, nullable=True),
        sa.Column("locked_fields", sa.JSON, nullable=False, server_default="[]"),
    )

    # 3 — term_dictionary (FK → series)
    op.create_table(
        "term_dictionary",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id"), nullable=False),
        sa.Column("source_term", sa.String, nullable=False),
        sa.Column("vietnamese_rendering", sa.String, nullable=False),
        sa.Column("category", sa.String, nullable=True),
        sa.Column("locked_fields", sa.JSON, nullable=False, server_default="[]"),
    )

    # 4 — address_map (FK → series + character×2; EMPTY in Phase 4 — Phase 5 populates)
    op.create_table(
        "address_map",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id"), nullable=False),
        sa.Column(
            "speaker_character_id",
            sa.Integer,
            sa.ForeignKey("character.id"),
            nullable=False,
        ),
        sa.Column(
            "addressee_character_id",
            sa.Integer,
            sa.ForeignKey("character.id"),
            nullable=False,
        ),
        sa.Column("self_term", sa.String, nullable=True),
        sa.Column("address_term", sa.String, nullable=True),
        sa.Column("valid_from_episode", sa.String, nullable=True),
        sa.Column("locked_fields", sa.JSON, nullable=False, server_default="[]"),
    )

    # 5 — relationship_event (FK → series + character×2; EMPTY in Phase 4 — Phase 6 populates)
    op.create_table(
        "relationship_event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id"), nullable=False),
        sa.Column(
            "character_a_id",
            sa.Integer,
            sa.ForeignKey("character.id"),
            nullable=False,
        ),
        sa.Column(
            "character_b_id",
            sa.Integer,
            sa.ForeignKey("character.id"),
            nullable=False,
        ),
        sa.Column("episode_marker", sa.String, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
    )

    # 6 — bible_event (FK → series; append-only audit log D-32)
    op.create_table(
        "bible_event",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("series_id", sa.Integer, sa.ForeignKey("series.id"), nullable=False),
        sa.Column("episode_key", sa.String, nullable=True),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=False),
        sa.Column("field", sa.String, nullable=False),
        sa.Column("old_value", sa.JSON, nullable=True),
        sa.Column("new_value", sa.JSON, nullable=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.CheckConstraint(
            "source IN ('inference', 'lock', 'import', 'system')",
            name="ck_bible_event_source",
        ),
    )

    # 7 — processed_file (D-37 JSON-ledger swap target; D-20 schema compat)
    op.create_table(
        "processed_file",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_path", sa.String, nullable=False, unique=True),
        sa.Column("output_path", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("series_id", sa.String, nullable=True),       # string per LedgerEntry D-20
        sa.Column("source_lang", sa.String, nullable=True),
        sa.Column("episode_key", sa.String, nullable=True),
        sa.Column("translated_at", sa.String, nullable=True),
        sa.Column("quarantine_path", sa.String, nullable=True),
        sa.CheckConstraint(
            "status IN ('done', 'quarantined', 'in_progress')",
            name="ck_processed_file_status",
        ),
    )

    # Indexes (created AFTER tables per FK-safe order)
    op.create_index(
        "ix_character_series_name",
        "character",
        ["series_id", "original_latin_name"],
    )
    op.create_index(
        "ix_term_dictionary_series_term",
        "term_dictionary",
        ["series_id", "source_term"],
    )
    op.create_index(
        "ix_bible_event_series_entity_time",
        "bible_event",
        ["series_id", "entity_type", "entity_id", "created_at"],
    )
    # NOTE: processed_file.source_path UNIQUE index is created inline above via
    # unique=True on the column — no separate op.create_index() needed.


def downgrade() -> None:
    """Drop all 7 Series Bible tables in REVERSE creation order."""

    # Drop indexes first
    op.drop_index("ix_bible_event_series_entity_time", table_name="bible_event")
    op.drop_index("ix_term_dictionary_series_term", table_name="term_dictionary")
    op.drop_index("ix_character_series_name", table_name="character")

    # Drop tables in reverse FK-safe order
    op.drop_table("processed_file")
    op.drop_table("bible_event")
    op.drop_table("relationship_event")
    op.drop_table("address_map")
    op.drop_table("term_dictionary")
    op.drop_table("character")
    op.drop_table("series")
