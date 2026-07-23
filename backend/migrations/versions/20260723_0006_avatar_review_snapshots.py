"""Separate review and authorization and preserve immutable Avatar inputs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0006"
down_revision: str | None = "20260722_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("avatar_versions", sa.Column("voice_features_snapshot_json", sa.JSON()))
    op.add_column("avatar_versions", sa.Column("visual_features_snapshot_json", sa.JSON()))
    op.add_column("avatar_versions", sa.Column("doctor_reviewed_by", sa.Uuid()))
    op.add_column(
        "avatar_versions", sa.Column("doctor_reviewed_at", sa.DateTime(timezone=True))
    )
    op.create_foreign_key(
        "fk_avatar_versions_doctor_reviewed_by_users",
        "avatar_versions",
        "users",
        ["doctor_reviewed_by"],
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_avatar_versions_doctor_reviewed_by_users",
        "avatar_versions",
        type_="foreignkey",
    )
    op.drop_column("avatar_versions", "doctor_reviewed_at")
    op.drop_column("avatar_versions", "doctor_reviewed_by")
    op.drop_column("avatar_versions", "visual_features_snapshot_json")
    op.drop_column("avatar_versions", "voice_features_snapshot_json")
