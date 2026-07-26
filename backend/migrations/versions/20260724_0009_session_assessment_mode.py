"""Persist whether a patient session reuses or repeats the voice assessment."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0009"
down_revision: str | None = "20260723_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patient_sessions",
        sa.Column(
            "assessment_mode",
            sa.String(32),
            nullable=False,
            server_default="new_assessment",
        ),
    )
    op.alter_column("patient_sessions", "assessment_mode", server_default=None)


def downgrade() -> None:
    op.drop_column("patient_sessions", "assessment_mode")
