from __future__ import annotations

"""Global temperature zone model."""

from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.room import Room


class TemperatureZone(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "temperature_zones"

    zone_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    min_temp: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    max_temp: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    rooms: Mapped[list["Room"]] = relationship(back_populates="temperature_zone", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TemperatureZone {self.zone_name} [{self.min_temp}, {self.max_temp}]>"
