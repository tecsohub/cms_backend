"""
Password-reset OTP model.

Stores time-limited, single-use numeric OTPs for the forgot-password
flow.  Key design decisions:

- OTP is hashed (SHA-256) before storage — prevents DB-leak abuse.
- ``is_used`` flag prevents replay.
- ``expires_at`` enforces the configurable TTL (default 60 min).
- Daily request count is enforced at the service layer by counting
  rows per email per calendar day (max 5/day/email).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_password_reset_otps_email_created", "email", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<PasswordResetOTP user={self.user_id} used={self.is_used}>"
