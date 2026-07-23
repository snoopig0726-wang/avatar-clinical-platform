"""Record independent semantic image safety results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0008"
down_revision: str | None = "20260723_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "avatar_versions",
        sa.Column("semantic_safety_provider", sa.String(50)),
    )
    op.add_column(
        "avatar_versions",
        sa.Column("semantic_safety_model", sa.String(100)),
    )
    op.add_column(
        "avatar_versions",
        sa.Column("semantic_safety_request_id", sa.String(200)),
    )
    op.add_column(
        "avatar_versions",
        sa.Column("semantic_safety_categories_json", sa.JSON()),
    )


def downgrade() -> None:
    op.drop_column("avatar_versions", "semantic_safety_categories_json")
    op.drop_column("avatar_versions", "semantic_safety_request_id")
    op.drop_column("avatar_versions", "semantic_safety_model")
    op.drop_column("avatar_versions", "semantic_safety_provider")
