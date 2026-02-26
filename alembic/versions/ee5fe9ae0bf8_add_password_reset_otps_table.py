"""add_password_reset_otps_table

Revision ID: ee5fe9ae0bf8
Revises: d5f6a7b8c9d0
Create Date: 2026-02-26 02:05:00.143040

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ee5fe9ae0bf8'
down_revision: Union[str, Sequence[str], None] = 'd5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('password_reset_otps',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=256), nullable=False),
    sa.Column('otp_hash', sa.String(length=128), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_used', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_password_reset_otps_email'), 'password_reset_otps', ['email'], unique=False)
    op.create_index('ix_password_reset_otps_email_created', 'password_reset_otps', ['email', 'created_at'], unique=False)
    op.create_index(op.f('ix_password_reset_otps_user_id'), 'password_reset_otps', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_password_reset_otps_user_id'), table_name='password_reset_otps')
    op.drop_index('ix_password_reset_otps_email_created', table_name='password_reset_otps')
    op.drop_index(op.f('ix_password_reset_otps_email'), table_name='password_reset_otps')
    op.drop_table('password_reset_otps')
