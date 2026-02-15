from __future__ import annotations

"""
Permission model.

Permissions are *immutable codes* that map to a single action in the
system (e.g. `inventory.inward.create`).  They are seeded at deploy
time and referenced by role ↔ permission associations — never checked
by role name in endpoint logic.
"""

import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.role import Role


class Permission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=True)

    # ── Relationships ────────────────────────────────────────────────
    roles: Mapped[list["Role"]] = relationship(  # noqa: F821
        secondary="role_permissions",
        back_populates="permissions",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"
