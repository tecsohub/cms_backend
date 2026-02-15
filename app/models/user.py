from __future__ import annotations

"""
User model.

Design decisions:
- NO role-specific columns here (operator shift, client company, etc.)
  Those live in OperatorProfile / Client — referenced via one-to-one.
- Status is an ENUM (INVITED → ACTIVE → DISABLED).
- Roles are attached via a many-to-many so new roles can be added
  without schema changes.
"""

import enum
import uuid

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from typing import TYPE_CHECKING

from app.models.role import user_roles  # association table

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.operator_profile import OperatorProfile
    from app.models.role import Role


class UserStatus(str, enum.Enum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(256), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=True)  # null while INVITED
    full_name: Mapped[str] = mapped_column(String(256), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        default=UserStatus.INVITED,
        nullable=False,
    )

    # ── Relationships ────────────────────────────────────────────────
    roles: Mapped[list["Role"]] = relationship(  # noqa: F821
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )
    operator_profile: Mapped["OperatorProfile | None"] = relationship(  # noqa: F821
        back_populates="user",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    client: Mapped["Client | None"] = relationship(  # noqa: F821
        back_populates="user",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
        foreign_keys="[Client.user_id]",
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
