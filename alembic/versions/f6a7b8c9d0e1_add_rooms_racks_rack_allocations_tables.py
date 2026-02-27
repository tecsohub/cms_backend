"""add_rooms_racks_rack_allocations_tables

Revision ID: f6a7b8c9d0e1
Revises: ee5fe9ae0bf8
Create Date: 2026-02-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'ee5fe9ae0bf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create rooms, racks, and rack_allocations tables."""

    # ── Rooms ────────────────────────────────────────────────────────
    op.create_table(
        'rooms',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('warehouse_id', sa.Uuid(), nullable=False),
        sa.Column('temperature_zone', sa.Numeric(precision=5, scale=2), nullable=True,
                  comment='Target temperature (°C) for this room'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rooms_warehouse_id', 'rooms', ['warehouse_id'])

    # ── Racks ────────────────────────────────────────────────────────
    op.create_table(
        'racks',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('label', sa.String(length=128), nullable=False),
        sa.Column('room_id', sa.Uuid(), nullable=False),
        sa.Column('capacity', sa.Numeric(precision=14, scale=3), nullable=False,
                  comment='Max storage quantity this rack can hold'),
        sa.Column('temperature', sa.Numeric(precision=5, scale=2), nullable=True,
                  comment='Rack temperature setting (°C)'),
        sa.Column('is_occupied', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_racks_room_id', 'racks', ['room_id'])
    op.create_index('ix_racks_is_occupied', 'racks', ['is_occupied'])

    # ── Rack allocations ─────────────────────────────────────────────
    op.create_table(
        'rack_allocations',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('rack_id', sa.Uuid(), nullable=False),
        sa.Column('sku_id', sa.Uuid(), nullable=False),
        sa.Column('allocated_by', sa.Uuid(), nullable=True),
        sa.Column('allocated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['rack_id'], ['racks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sku_id'], ['skus.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['allocated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rack_allocations_rack_id', 'rack_allocations', ['rack_id'])
    op.create_index('ix_rack_allocations_sku_id', 'rack_allocations', ['sku_id'])
    op.create_index('ix_rack_allocations_released_at', 'rack_allocations', ['released_at'])


def downgrade() -> None:
    """Drop tables in reverse dependency order."""
    op.drop_table('rack_allocations')
    op.drop_table('racks')
    op.drop_table('rooms')
