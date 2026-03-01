"""
Inventory Ledger model — domain-level mutation tracking.

This table is **append-only** and **immutable**.
Current inventory for any SKU is derived as:

    SUM(quantity_delta) WHERE sku_id = ? [GROUP BY warehouse_id]

Rules:
- No UPDATE operations allowed.
- No DELETE operations allowed.
- Only INSERT allowed.
- This ledger is the source of truth for quantity history.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.enums import MovementType


class InventoryLedger(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "inventory_ledger"

    # ── Domain columns ───────────────────────────────────────────────
    sku_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skus.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    movement_type: Mapped[MovementType] = mapped_column(
        Enum(MovementType, name="movement_type", create_constraint=True),
        nullable=False,
    )
    lot_number: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )
    quantity_delta: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        nullable=False,
    )
    reference_type: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    reference_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    performed_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── Composite indexes ────────────────────────────────────────────
    __table_args__ = (
        Index("ix_inventory_ledger_sku_created", "sku_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<InventoryLedger {self.movement_type.value} "
            f"sku={self.sku_id} Δ={self.quantity_delta}>"
        )
