"""reconcile missing inventory/audit/product tables for stamped databases

Revision ID: a7b9c1d3e5f7
Revises: ee5fe9ae0bf8
Create Date: 2026-03-01 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7b9c1d3e5f7"
down_revision: Union[str, Sequence[str], None] = "ee5fe9ae0bf8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in set(inspector.get_table_names(schema="public"))


def upgrade() -> None:
    """Backfill c4/d5 schema objects when DB was stamped ahead."""

    # ENUMs are shared across multiple tables; create with checkfirst.
    movement_type_enum = sa.Enum(
        "INWARD",
        "ALLOCATION",
        "INTERNAL_TRANSFER",
        "OUTWARD",
        "ADJUSTMENT",
        "WASTE",
        name="movement_type",
        create_type=False,
    )
    movement_type_enum.create(op.get_bind(), checkfirst=True)

    audit_action_enum = sa.Enum(
        "CREATE",
        "UPDATE",
        "DELETE",
        "DISABLE",
        "APPROVE",
        "REJECT",
        "ALLOCATE",
        "CLOSE",
        name="audit_action",
        create_type=False,
    )
    audit_action_enum.create(op.get_bind(), checkfirst=True)

    product_category_enum = sa.Enum(
        "FROZEN",
        "CHILLED",
        "DRY",
        "PHARMA",
        "OTHER",
        name="product_category",
        create_type=False,
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
        create_type=False,
    )
    storage_unit_enum.create(op.get_bind(), checkfirst=True)

    movement_type_col_type = postgresql.ENUM(name="movement_type", create_type=False)
    audit_action_col_type = postgresql.ENUM(name="audit_action", create_type=False)
    product_category_col_type = postgresql.ENUM(name="product_category", create_type=False)
    storage_unit_col_type = postgresql.ENUM(name="storage_unit", create_type=False)

    if not _table_exists("skus"):
        op.create_table(
            "skus",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(256), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", product_category_col_type, nullable=False),
            sa.Column("unit", storage_unit_col_type, nullable=False),
            sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("temperature_requirement", sa.Numeric(5, 2), nullable=True),
            sa.Column("lot_number", sa.String(128), nullable=False),
            sa.Column("sku_code", sa.String(64), nullable=False),
            sa.Column("warehouse_id", sa.Uuid(), nullable=False),
            sa.Column("client_id", sa.Uuid(), nullable=True),
            sa.Column("client_email", sa.String(256), nullable=True),
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
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sku_code"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        )
        op.create_index("ix_skus_sku_code", "skus", ["sku_code"], unique=True)
        op.create_index("ix_skus_warehouse_id", "skus", ["warehouse_id"])
        op.create_index("ix_skus_client_id", "skus", ["client_id"])
        op.create_index("ix_skus_client_email", "skus", ["client_email"])
        op.create_index("ix_skus_lot_number", "skus", ["lot_number"])

    if not _table_exists("inventory_ledger"):
        op.create_table(
            "inventory_ledger",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("sku_id", sa.Uuid(), nullable=False),
            sa.Column("warehouse_id", sa.Uuid(), nullable=False),
            sa.Column("movement_type", movement_type_col_type, nullable=False),
            sa.Column("quantity_delta", sa.Numeric(precision=14, scale=3), nullable=False),
            sa.Column("reference_type", sa.String(length=128), nullable=False),
            sa.Column("reference_id", sa.Uuid(), nullable=False),
            sa.Column("performed_by", sa.Uuid(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["performed_by"], ["users.id"], ondelete="RESTRICT"),
        )
        op.create_index("ix_inventory_ledger_sku_id", "inventory_ledger", ["sku_id"])
        op.create_index("ix_inventory_ledger_warehouse_id", "inventory_ledger", ["warehouse_id"])
        op.create_index("ix_inventory_ledger_created_at", "inventory_ledger", ["created_at"])
        op.create_index("ix_inventory_ledger_performed_by", "inventory_ledger", ["performed_by"])
        op.create_index("ix_inventory_ledger_reference_type", "inventory_ledger", ["reference_type"])
        op.create_index("ix_inventory_ledger_sku_created", "inventory_ledger", ["sku_id", "created_at"])

    if not _table_exists("audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("entity_type", sa.String(length=128), nullable=False),
            sa.Column("entity_id", sa.Uuid(), nullable=False),
            sa.Column("action", audit_action_col_type, nullable=False),
            sa.Column("performed_by", sa.Uuid(), nullable=False),
            sa.Column("old_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("new_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["performed_by"], ["users.id"], ondelete="RESTRICT"),
        )
        op.create_index("ix_audit_log_entity_type", "audit_log", ["entity_type"])
        op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
        op.create_index("ix_audit_log_performed_by", "audit_log", ["performed_by"])
        op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
        op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])


def downgrade() -> None:
    """No-op: this is a forward-only reconciliation migration."""
    pass
