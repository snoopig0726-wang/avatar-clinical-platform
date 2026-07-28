"""Persist patient satisfaction with the currently authorized avatar."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0011"
down_revision: str | None = "20260725_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patient_sessions",
        sa.Column("patient_satisfied_version_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "patient_sessions",
        sa.Column("patient_satisfied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_patient_sessions_satisfied_version",
        "patient_sessions",
        "avatar_versions",
        ["patient_satisfied_version_id"],
        ["version_id"],
    )
    op.create_index(
        "ix_patient_sessions_satisfied_version",
        "patient_sessions",
        ["patient_satisfied_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_patient_sessions_satisfied_version",
        table_name="patient_sessions",
    )
    op.drop_constraint(
        "fk_patient_sessions_satisfied_version",
        "patient_sessions",
        type_="foreignkey",
    )
    op.drop_column("patient_sessions", "patient_satisfied_at")
    op.drop_column("patient_sessions", "patient_satisfied_version_id")
