"""SQLAlchemy 2.0 typed declarative models for the job queue persistence layer (D-69).

Design decisions honoured:
  D-69  New job + job_log tables via Alembic 0002 migration. Keeps the frozen
        D-20 LedgerEntry↔ProcessedFile-column contract untouched. job.status
        ∈ {queued, running, done, failed, quarantined}. job.trigger ∈
        {poll, webhook, manual, manual-retry, startup-reconcile}.
  D-68  Per-series asyncio.Lock serializes translation; job.series_id is the
        serialization key. No second asyncio.Semaphore (Pitfall C).
  D-75  job_log rows capture per-job logging output so the UI can render a
        specific job's log trail (SVC-03).

Pattern mirrors trezarr/bible/models.py — Mapped[T] = mapped_column(),
CheckConstraint for enum columns, server_default=func.current_timestamp()
for audit timestamps.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from trezarr.db.base import Base


class Job(Base):
    """One queued/running/completed translation job.

    Keyed to source_path (the subtitle file to translate). References the
    processed_file idempotency ledger conceptually but does NOT foreign-key
    to it — the two tables serve different concerns (D-69).

    status ∈ {queued, running, done, failed, quarantined}
    trigger ∈ {poll, webhook, manual, manual-retry, startup-reconcile}
    """

    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','failed','quarantined')",
            name="ck_job_status",
        ),
        CheckConstraint(
            "trigger IN ('poll','webhook','manual','manual-retry','startup-reconcile','auto-retry')",
            name="ck_job_trigger",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(String, nullable=False, index=True)
    series_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Snapshot of the discovery MediaItem fields needed for Bible-aware translation (CR-01).
    # Serialised at enqueue time by enqueue_job; reconstructed at execution time by
    # _execute_job so translate_file can take the Bible-aware path (Phase-5 pipeline).
    # None when the job was enqueued without discovery context (e.g. ARM-2 reconcile
    # from a bare ProcessedFile row) — in that case _execute_job falls back to the
    # mechanical (non-Bible-aware) path.
    media_item_json: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


class JobLog(Base):
    """Append-only per-job log record (D-75).

    Captures logging output from each job execution so the UI can render the
    full log trail for a specific job (SVC-03 per-job logs view).
    """

    __tablename__ = "job_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job.id"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(String, nullable=False)  # DEBUG/INFO/WARNING/ERROR
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
