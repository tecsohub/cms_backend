from __future__ import annotations

"""
OperatorProfile model.

One-to-one with User — uses `user_id` as its PK (no separate UUID).
Contains operator-specific data so the User table stays role-agnostic.
"""

import uuid
from datetime import time

from sqlalchemy import ForeignKey, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.warehouse import Warehouse


class OperatorProfile(Base, TimestampMixin):
    __tablename__ = "operator_profiles"

    # PK = FK → users.id  (true one-to-one)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    warehouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_start: Mapped[time] = mapped_column(Time, nullable=True)
    shift_end: Mapped[time] = mapped_column(Time, nullable=True)

    # ── Relationships ────────────────────────────────────────────────
    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="operator_profile",
        lazy="selectin",
    )
    warehouse: Mapped["Warehouse"] = relationship(  # noqa: F821
        back_populates="operator_profiles",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<OperatorProfile user_id={self.user_id}>"
