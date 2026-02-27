from __future__ import annotations

"""
Rack Allocation model.

Tracks which SKU (product) is physically stored in which rack.
This is the STATEFUL location truth — one active allocation per rack.

- allocated_at : when the pallet was placed
- released_at  : set when the pallet is moved out (NULL while active)
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.rack import Rack
    from app.models.user import User


class RackAllocation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rack_allocations"

    rack_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("racks.id", ondelete="CASCADE"),
        nullable=False,
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skus.id", ondelete="CASCADE"),
        nullable=False,
    )
    allocated_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relationships ────────────────────────────────────────────────
    rack: Mapped["Rack"] = relationship(
        back_populates="allocations",
        lazy="selectin",
    )
    product: Mapped["Product"] = relationship(
        foreign_keys=[sku_id],
        lazy="selectin",
    )
    allocated_by_user: Mapped["User | None"] = relationship(
        foreign_keys=[allocated_by],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<RackAllocation rack={self.rack_id} sku={self.sku_id} "
            f"released={self.released_at is not None}>"
        )
