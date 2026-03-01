"""Product model — logical SKU entity.

This table stores stable product metadata (name/category/unit/etc.) only.
Physical stock details such as quantity and lot number are captured in the
append-only ``inventory_ledger`` during inward.
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
    temperature_requirement: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Required storage temperature in °C",
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
        return f"<Product {self.sku_code} - {self.name}>"
