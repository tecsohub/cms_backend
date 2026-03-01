"""split product and inward fields

Revision ID: 1a2b3c4d5e6f
Revises: 9c1d2e3f4a5b
Create Date: 2026-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, Sequence[str], None] = "9c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Move lot_number to ledger and remove mutable inventory fields from skus."""
    # Add lot_number to ledger first, nullable for backfill.
    op.add_column(
        "inventory_ledger",
        sa.Column("lot_number", sa.String(length=128), nullable=True),
    )

    # Backfill from existing skus rows.
    op.execute(
        sa.text(
            """
            UPDATE inventory_ledger AS il
            SET lot_number = s.lot_number
            FROM skus AS s
            WHERE il.sku_id = s.id
            """
        )
    )

    # Ensure no NULL lot values remain.
    op.execute(
        sa.text(
            """
            UPDATE inventory_ledger
            SET lot_number = 'MIG-' || id::text
            WHERE lot_number IS NULL
            """
        )
    )

    op.alter_column("inventory_ledger", "lot_number", nullable=False)
    op.create_index(
        "ix_inventory_ledger_lot_number",
        "inventory_ledger",
        ["lot_number"],
        unique=True,
    )

    # Product is now logical SKU only.
    op.drop_index("ix_skus_lot_number", table_name="skus")
    op.drop_column("skus", "lot_number")
    op.drop_column("skus", "quantity")


def downgrade() -> None:
    """Restore quantity/lot_number on skus and remove lot_number from ledger."""
    op.add_column("skus", sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=True))
    op.add_column("skus", sa.Column("lot_number", sa.String(length=128), nullable=True))

    # Backfill from inward ledger rows.
    op.execute(
        sa.text(
            """
            UPDATE skus AS s
            SET
                lot_number = il.lot_number,
                quantity = il.quantity_delta
            FROM inventory_ledger AS il
            WHERE il.sku_id = s.id
              AND il.movement_type = 'INWARD'
            """
        )
    )

    # Ensure non-null for restored schema.
    op.execute(
        sa.text(
            """
            UPDATE skus
            SET lot_number = 'MIG-' || id::text
            WHERE lot_number IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE skus
            SET quantity = 0
            WHERE quantity IS NULL
            """
        )
    )

    op.alter_column("skus", "lot_number", nullable=False)
    op.alter_column("skus", "quantity", nullable=False)
    op.create_index("ix_skus_lot_number", "skus", ["lot_number"], unique=False)

    op.drop_index("ix_inventory_ledger_lot_number", table_name="inventory_ledger")
    op.drop_column("inventory_ledger", "lot_number")
