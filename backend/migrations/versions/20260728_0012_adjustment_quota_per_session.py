"""Scope the three adjustment requests to each patient session."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260728_0012"
down_revision: str | None = "20260728_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_adjustment_case_sequence",
        "adjustment_requests",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_adjustment_session_sequence",
        "adjustment_requests",
        ["session_id", "sequence_no"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_adjustment_session_sequence",
        "adjustment_requests",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_adjustment_case_sequence",
        "adjustment_requests",
        ["case_id", "sequence_no"],
    )
