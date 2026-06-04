"""Add 'manual' to ck_job_trigger CHECK constraint (bug fix).

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-04

POST /api/translate enqueues jobs with trigger='manual' (user-initiated translate),
but the original ck_job_trigger CHECK constraint in migration 0002 only listed
{poll, webhook, manual-retry, startup-reconcile}. Any INSERT with trigger='manual'
raised sqlalchemy.exc.IntegrityError: CHECK constraint failed: ck_job_trigger.

Fix: expand the allowed trigger set to include 'manual'.

SQLite cannot ALTER a CHECK constraint in place, so we use batch_alter_table
with recreate="always" (move-and-copy) to drop the old constraint and recreate
the table with the corrected constraint. All existing rows and columns are
preserved by SQLAlchemy's batch reflection.

Constraint values before:  {poll, webhook, manual-retry, startup-reconcile}
Constraint values after:   {poll, webhook, manual, manual-retry, startup-reconcile}
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Recreate the job table with 'manual' added to ck_job_trigger."""
    with op.batch_alter_table("job", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_job_trigger", type_="check")
        batch_op.create_check_constraint(
            "ck_job_trigger",
            "trigger IN ('poll','webhook','manual','manual-retry','startup-reconcile')",
        )


def downgrade() -> None:
    """Restore ck_job_trigger to the original 4-value set (removes 'manual')."""
    with op.batch_alter_table("job", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_job_trigger", type_="check")
        batch_op.create_check_constraint(
            "ck_job_trigger",
            "trigger IN ('poll','webhook','manual-retry','startup-reconcile')",
        )
