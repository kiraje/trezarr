"""Add 'auto-retry' to ck_job_trigger CHECK constraint (P0 campaign, 260612-dmh).

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-12

_execute_job re-enqueues jobs with trigger='auto-retry' when a TRANSIENT
BatchValidationError parse-contract quarantine fires (Empty/whitespace-only,
Missing line, Parsed N lines mismatch). The ck_job_trigger constraint in
migration 0004 only allowed {poll, webhook, manual, manual-retry, startup-reconcile}.
Any INSERT with trigger='auto-retry' would raise IntegrityError.

Fix: expand the allowed trigger set to include 'auto-retry'.

SQLite cannot ALTER a CHECK constraint in place, so we use batch_alter_table
with recreate="always" (move-and-copy) to drop the old constraint and recreate
the table with the corrected constraint. All existing rows and columns are
preserved by SQLAlchemy's batch reflection.

Constraint values before:  {poll, webhook, manual, manual-retry, startup-reconcile}
Constraint values after:   {poll, webhook, manual, manual-retry, startup-reconcile, auto-retry}
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Recreate the job table with 'auto-retry' added to ck_job_trigger."""
    with op.batch_alter_table("job", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_job_trigger", type_="check")
        batch_op.create_check_constraint(
            "ck_job_trigger",
            "trigger IN ('poll','webhook','manual','manual-retry','startup-reconcile','auto-retry')",
        )


def downgrade() -> None:
    """Restore ck_job_trigger to the 5-value set from migration 0004 (removes 'auto-retry')."""
    with op.batch_alter_table("job", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_job_trigger", type_="check")
        batch_op.create_check_constraint(
            "ck_job_trigger",
            "trigger IN ('poll','webhook','manual','manual-retry','startup-reconcile')",
        )
