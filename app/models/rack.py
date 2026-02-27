from __future__ import annotations

"""
Rack model.

A Rack is the smallest allocatable storage unit inside a Room.
Each rack holds a single SKU at a time (exclusive).

Key fields:
- capacity   : maximum quantity (same unit as the product) this rack can hold
- temperature : the rack's temperature setting; must match the product's requirement
- is_occupied : denormalized flag set by the allocation service
"""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.rack_allocation import RackAllocation
    from app.models.room import Room


class Rack(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "racks"

    label: Mapped[str] = mapped_column(String(128), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
    )
    capacity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
        nullable=False,
        comment="Max storage quantity this rack can hold",
    )
    temperature: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment="Rack temperature setting (°C)",
    )
    is_occupied: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────────
    room: Mapped["Room"] = relationship(
        back_populates="racks",
        lazy="selectin",
    )
    allocations: Mapped[list["RackAllocation"]] = relationship(
        back_populates="rack",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Rack {self.label} room={self.room_id} occupied={self.is_occupied}>"
