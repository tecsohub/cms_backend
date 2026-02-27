from __future__ import annotations

"""
Room model.

A Room is a physical section inside a Warehouse.
Rooms carry a temperature zone so that racks within them inherit
compatible temperature ranges.
"""

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.rack import Rack
    from app.models.warehouse import Warehouse


class Room(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rooms"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )
    temperature_zone: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Target temperature (°C) for this room",
    )

    # ── Relationships ────────────────────────────────────────────────
    warehouse: Mapped["Warehouse"] = relationship(
        foreign_keys=[warehouse_id],
        lazy="selectin",
    )
    racks: Mapped[list["Rack"]] = relationship(
        back_populates="room",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Room {self.name} in warehouse={self.warehouse_id}>"
