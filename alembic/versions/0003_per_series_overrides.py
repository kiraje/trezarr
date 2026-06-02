"""Add per-series override columns: source_lang_override, model_override (D-111, Phase 10).

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-02

Adds two nullable columns to the `series` table for per-series source-language and
model overrides (SVC-05). NULL = inherit global config (D-112).

Columns added:
  source_lang_override  — JSON (nullable): ordered list of ISO-639-1 language codes.
                          NULL means use global source_lang_priority.
  model_override        — String (nullable): LLM model identifier for this series.
                          NULL means use global llm_model.

No indexes needed — per-series lookup is always by series.id (PK).
Reversible: downgrade() removes both columns (D-69, D-37).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add source_lang_override and model_override columns to series table."""
    op.add_column(
        "series",
        sa.Column("source_lang_override", sa.JSON, nullable=True, server_default=sa.text("NULL")),
    )
    op.add_column(
        "series",
        sa.Column("model_override", sa.String, nullable=True, server_default=sa.text("NULL")),
    )


def downgrade() -> None:
    """Remove override columns in reverse order (FK-safe — no FK dependencies)."""
    op.drop_column("series", "model_override")
    op.drop_column("series", "source_lang_override")
