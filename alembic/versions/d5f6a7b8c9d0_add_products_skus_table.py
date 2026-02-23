"""add products (skus) table

Revision ID: d5f6a7b8c9d0
Revises: c4e5f6a7b8c9
Create Date: 2026-02-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "c4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the skus (products) table with ENUM types and indexes."""

    # ── ENUM types ───────────────────────────────────────────────────
    product_category_enum = sa.Enum(
        "FROZEN",
        "CHILLED",
        "DRY",
        "PHARMA",
        "OTHER",
        name="product_category",
    )
    product_category_enum.create(op.get_bind(), checkfirst=True)

    storage_unit_enum = sa.Enum(
        "KG",
        "TON",
        "BOX",
        "PALLET",
        "LITRE",
        "UNIT",
        name="storage_unit",
    )
    storage_unit_enum.create(op.get_bind(), checkfirst=True)

    # ── skus table ───────────────────────────────────────────────────
    op.create_table(
        "skus",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category",
            product_category_enum,
            nullable=False,
        ),
        sa.Column(
            "unit",
            storage_unit_enum,
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column(
            "temperature_requirement",
            sa.Numeric(5, 2),
            nullable=True,
            comment="Required storage temperature in °C",
        ),
        sa.Column(
            "lot_number",
            sa.String(128),
            nullable=False,
            comment="Lot/batch number — all items on the pallet share this",
        ),
        sa.Column("sku_code", sa.String(64), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=True),
        sa.Column(
            "client_email",
            sa.String(256),
            nullable=True,
            comment="Email provided at intake — used to link or invite the client",
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # ── Constraints ──────────────────────────────────────────────
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku_code"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["clients.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
    )

    # ── Indexes ──────────────────────────────────────────────────────
    op.create_index("ix_skus_sku_code", "skus", ["sku_code"], unique=True)
    op.create_index("ix_skus_warehouse_id", "skus", ["warehouse_id"])
    op.create_index("ix_skus_client_id", "skus", ["client_id"])
    op.create_index("ix_skus_client_email", "skus", ["client_email"])
    op.create_index("ix_skus_lot_number", "skus", ["lot_number"])


def downgrade() -> None:
    """Drop the skus table and its ENUM types."""
    op.drop_index("ix_skus_lot_number", table_name="skus")
    op.drop_index("ix_skus_client_email", table_name="skus")
    op.drop_index("ix_skus_client_id", table_name="skus")
    op.drop_index("ix_skus_warehouse_id", table_name="skus")
    op.drop_index("ix_skus_sku_code", table_name="skus")
    op.drop_table("skus")

    sa.Enum(name="storage_unit").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="product_category").drop(op.get_bind(), checkfirst=True)
