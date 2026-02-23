"""
Product model — represents a pallet of goods entering a cold-storage warehouse.

Each record captures the product details entered by an operator during the
inward/intake process.  A pallet groups items with the same **lot/batch
number**.  A unique SKU code is auto-generated from product attributes:

    {CATEGORY_PREFIX}-{WAREHOUSE_CODE}-{YYYYMMDD}-{SEQ}
    e.g.  FRZ-WH01-20260223-0001

The `client_id` is nullable because the client may not yet exist at
intake time — the operator provides an email, and the system either
links an existing client or sends an invitation.  Once the client
accepts, `client_id` is back-filled by querying on `client_email`.

The inventory_ledger.sku_id FK already points at a table named "skus",
so we use that as __tablename__ to keep the FK consistent.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.user import User
    from app.models.warehouse import Warehouse


class ProductCategory(str, enum.Enum):
    """Broad cold-storage product categories — prefix used in SKU."""

    FROZEN = "FROZEN"       # FRZ
    CHILLED = "CHILLED"     # CHL
    DRY = "DRY"             # DRY
    PHARMA = "PHARMA"       # PHR
    OTHER = "OTHER"         # OTH


# Mapping used by SKU generator
CATEGORY_PREFIX: dict[ProductCategory, str] = {
    ProductCategory.FROZEN: "FRZ",
    ProductCategory.CHILLED: "CHL",
    ProductCategory.DRY: "DRY",
    ProductCategory.PHARMA: "PHR",
    ProductCategory.OTHER: "OTH",
}


class StorageUnit(str, enum.Enum):
    """Unit of measure for stored goods."""

    KG = "KG"
    TON = "TON"
    BOX = "BOX"
    PALLET = "PALLET"
    LITRE = "LITRE"
    UNIT = "UNIT"


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "skus"  # matches existing FK in inventory_ledger

    # ── Core product details ─────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[ProductCategory] = mapped_column(
        Enum(ProductCategory, name="product_category", create_constraint=True),
        nullable=False,
    )
    unit: Mapped[StorageUnit] = mapped_column(
        Enum(StorageUnit, name="storage_unit", create_constraint=True),
        nullable=False,
    )
    quantity: Mapped[float] = mapped_column(
        Numeric(14, 3),
        nullable=False,
    )
    temperature_requirement: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Required storage temperature in °C",
    )

    # ── Pallet / batch tracking ──────────────────────────────────────
    lot_number: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="Lot/batch number — all items on the pallet share this",
    )

    # ── Auto-generated SKU ───────────────────────────────────────────
    sku_code: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
    )

    # ── Ownership & location ─────────────────────────────────────────
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    client_email: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        index=True,
        comment="Email provided at intake - used to link or invite the client",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────────
    warehouse: Mapped["Warehouse"] = relationship(
        foreign_keys=[warehouse_id],
        lazy="selectin",
    )
    client: Mapped["Client | None"] = relationship(
        foreign_keys=[client_id],
        lazy="selectin",
    )
    created_by_user: Mapped["User"] = relationship(
        foreign_keys=[created_by],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Product {self.sku_code} - {self.name} lot={self.lot_number}>"
