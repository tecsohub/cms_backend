from __future__ import annotations

"""
Invitation model.

Admin sends an invite → creates an Invitation row with a unique token.
The invited user clicks the link, sets a password, and their status
transitions from INVITED → ACTIVE.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from typing import TYPE_CHECKING

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class InvitationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"


class Invitation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "invitations"

    email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    invited_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    role_assigned: Mapped[str] = mapped_column(String(64), nullable=False)
    token: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, name="invitation_status"),
        default=InvitationStatus.PENDING,
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────────
    inviter: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[invited_by],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Invitation {self.email} [{self.status}]>"
