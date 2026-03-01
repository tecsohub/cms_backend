from __future__ import annotations

"""Room model."""

import uuid
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.rack import Rack
    from app.models.temperature_zone import TemperatureZone
    from app.models.warehouse import Warehouse


class Room(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rooms"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )
    temperature_zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("temperature_zones.id", ondelete="RESTRICT"),
        nullable=False,
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
    temperature_zone: Mapped["TemperatureZone"] = relationship(
        back_populates="rooms",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Room {self.name} in warehouse={self.warehouse_id}>"
