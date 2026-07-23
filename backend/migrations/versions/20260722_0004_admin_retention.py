"""Add retention jobs for permanent case deletion."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0004"
down_revision: str | None = "20260721_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retention_jobs",
        sa.Column("retention_job_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid()),
        sa.Column("case_reference_hash", sa.LargeBinary(), nullable=False),
        sa.Column("retention_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "SCHEDULED",
                "RUNNING",
                "RETRYING",
                "COMPLETED",
                "FAILED",
                name="retention_status_enum",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_categories_json", sa.JSON()),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.case_id"],
            name="fk_retention_jobs_case_id_cases",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("retention_job_id", name="pk_retention_jobs"),
        sa.UniqueConstraint("case_id", name="uq_retention_jobs_case_id"),
        sa.UniqueConstraint("case_reference_hash", name="uq_retention_jobs_case_reference_hash"),
    )
    op.create_index(
        "ix_retention_jobs_due_status",
        "retention_jobs",
        ["retention_due_at", "status"],
    )


def downgrade() -> None:
    op.drop_table("retention_jobs")
