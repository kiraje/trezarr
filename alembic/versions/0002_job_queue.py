"""Add job queue tables: job + job_log (D-69, Phase 7).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-02

This migration adds the job queue persistence layer on top of the Phase-4
baseline. It does NOT alter any of the 7 tables from 0001 — the frozen D-20
LedgerEntry↔ProcessedFile column contract is left completely untouched.

Tables created:
  job      — queued/running/completed translation jobs
  job_log  — per-job append-only log records (SVC-03 log view)

CheckConstraints:
  ck_job_status  — status IN (queued, running, done, failed, quarantined)
  ck_job_trigger — trigger IN (poll, webhook, manual-retry, startup-reconcile)

Indexes (created AFTER tables per 0001 convention):
  ix_job_source_path   — job.source_path (dedup guard lookups)
  ix_job_log_job_id    — job_log.job_id (per-job log queries)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create job and job_log tables with constraints and indexes."""

    # 1 — job (root entity; no FK dependencies among new tables)
    op.create_table(
        "job",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_path", sa.String, nullable=False),
        sa.Column("series_id", sa.Integer, nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("trigger", sa.String, nullable=False),
        sa.Column("error_reason", sa.Text, nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "enqueued_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','running','done','failed','quarantined')",
            name="ck_job_status",
        ),
        sa.CheckConstraint(
            "trigger IN ('poll','webhook','manual-retry','startup-reconcile')",
            name="ck_job_trigger",
        ),
    )

    # 2 — job_log (FK → job; append-only audit log)
    op.create_table(
        "job_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("job.id"), nullable=False),
        sa.Column("level", sa.String, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
    )

    # Indexes (created AFTER tables per FK-safe order, mirroring 0001 convention)
    op.create_index("ix_job_source_path", "job", ["source_path"])
    op.create_index("ix_job_log_job_id", "job_log", ["job_id"])


def downgrade() -> None:
    """Drop job_log and job tables in FK-safe reverse order."""

    # Drop indexes first
    op.drop_index("ix_job_log_job_id", table_name="job_log")
    op.drop_index("ix_job_source_path", table_name="job")

    # Drop tables in reverse FK-safe order
    op.drop_table("job_log")
    op.drop_table("job")
