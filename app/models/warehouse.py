from __future__ import annotations

"""
Warehouse model.

Each warehouse is created by an Admin.  Operators are assigned to
exactly one warehouse via their OperatorProfile.
"""

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.operator_profile import OperatorProfile
    from app.models.user import User


class Warehouse(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "warehouses"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    address: Mapped[str] = mapped_column(String(512), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=True)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ────────────────────────────────────────────────
    created_by_admin: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_admin_id],
        lazy="selectin",
    )
    operator_profiles: Mapped[list["OperatorProfile"]] = relationship(  # noqa: F821
        back_populates="warehouse",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Warehouse {self.name}>"
