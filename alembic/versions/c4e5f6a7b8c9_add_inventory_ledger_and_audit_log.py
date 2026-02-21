"""add inventory_ledger and audit_log tables

Revision ID: c4e5f6a7b8c9
Revises: b3d4e5f6a7b8
Create Date: 2026-02-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "b3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create inventory_ledger and audit_log tables with ENUMs and indexes."""

    # ── ENUM types ───────────────────────────────────────────────────
    movement_type_enum = sa.Enum(
        "INWARD",
        "ALLOCATION",
        "INTERNAL_TRANSFER",
        "OUTWARD",
        "ADJUSTMENT",
        "WASTE",
        name="movement_type",
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
    )
    audit_action_enum.create(op.get_bind(), checkfirst=True)

    # ── inventory_ledger table ───────────────────────────────────────
    op.create_table(
        "inventory_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column(
            "movement_type",
            movement_type_enum,
            nullable=False,
        ),
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
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["sku_id"], ["skus.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"], ["users.id"], ondelete="RESTRICT",
        ),
    )

    # Single-column indexes
    op.create_index("ix_inventory_ledger_sku_id", "inventory_ledger", ["sku_id"])
    op.create_index("ix_inventory_ledger_warehouse_id", "inventory_ledger", ["warehouse_id"])
    op.create_index("ix_inventory_ledger_created_at", "inventory_ledger", ["created_at"])
    op.create_index("ix_inventory_ledger_performed_by", "inventory_ledger", ["performed_by"])
    op.create_index("ix_inventory_ledger_reference_type", "inventory_ledger", ["reference_type"])
    # Composite index
    op.create_index(
        "ix_inventory_ledger_sku_created",
        "inventory_ledger",
        ["sku_id", "created_at"],
    )

    # ── audit_log table ──────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "action",
            audit_action_enum,
            nullable=False,
        ),
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
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["performed_by"], ["users.id"], ondelete="RESTRICT",
        ),
    )

    # Single-column indexes
    op.create_index("ix_audit_log_entity_type", "audit_log", ["entity_type"])
    op.create_index("ix_audit_log_entity_id", "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_performed_by", "audit_log", ["performed_by"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    # Composite index
    op.create_index(
        "ix_audit_log_entity",
        "audit_log",
        ["entity_type", "entity_id"],
    )


def downgrade() -> None:
    """Drop audit_log and inventory_ledger tables and their ENUM types."""
    # audit_log
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_performed_by", table_name="audit_log")
    op.drop_index("ix_audit_log_entity_id", table_name="audit_log")
    op.drop_index("ix_audit_log_entity_type", table_name="audit_log")
    op.drop_table("audit_log")

    # inventory_ledger
    op.drop_index("ix_inventory_ledger_sku_created", table_name="inventory_ledger")
    op.drop_index("ix_inventory_ledger_reference_type", table_name="inventory_ledger")
    op.drop_index("ix_inventory_ledger_performed_by", table_name="inventory_ledger")
    op.drop_index("ix_inventory_ledger_created_at", table_name="inventory_ledger")
    op.drop_index("ix_inventory_ledger_warehouse_id", table_name="inventory_ledger")
    op.drop_index("ix_inventory_ledger_sku_id", table_name="inventory_ledger")
    op.drop_table("inventory_ledger")

    # ENUM types
    sa.Enum(name="audit_action").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="movement_type").drop(op.get_bind(), checkfirst=True)
