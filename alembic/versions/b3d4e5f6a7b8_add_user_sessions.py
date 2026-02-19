"""add user_sessions table

Revision ID: b3d4e5f6a7b8
Revises: 7142304e8e20
Create Date: 2026-02-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "7142304e8e20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_sessions table for device-bound session enforcement."""
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_device_id", "user_sessions", ["device_id"])
    op.create_index("ix_user_sessions_is_active", "user_sessions", ["is_active"])
    op.create_index(
        "ix_user_sessions_user_active",
        "user_sessions",
        ["user_id", "is_active"],
    )


def downgrade() -> None:
    """Drop user_sessions table."""
    op.drop_index("ix_user_sessions_user_active", table_name="user_sessions")
    op.drop_index("ix_user_sessions_is_active", table_name="user_sessions")
    op.drop_index("ix_user_sessions_device_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
