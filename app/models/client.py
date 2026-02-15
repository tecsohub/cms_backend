from __future__ import annotations

"""
Client model.

Each Client row maps 1-to-1 with a User.  It stores company-level
billing info so the User table remains role-neutral.
The `created_by_admin_id` captures who onboarded the client.
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Client(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "clients"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    billing_address: Mapped[str] = mapped_column(String(512), nullable=True)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ────────────────────────────────────────────────
    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="client",
        foreign_keys=[user_id],
        lazy="selectin",
    )
    created_by_admin: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_admin_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Client {self.company_name}>"
