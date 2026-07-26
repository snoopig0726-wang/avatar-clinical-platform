"""Store encrypted clinician rejection reasons for adjustment requests."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0010"
down_revision: str | None = "20260724_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "adjustment_requests",
        sa.Column("rejection_reason_encrypted", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("adjustment_requests", "rejection_reason_encrypted")
