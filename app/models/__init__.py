"""
Models package — import every model so SQLAlchemy's Base.metadata
knows about all tables (critical for `create_all` / Alembic).
"""

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.user import User, UserStatus
from app.models.role import Role, user_roles, role_permissions
from app.models.permission import Permission
from app.models.warehouse import Warehouse
from app.models.operator_profile import OperatorProfile
from app.models.client import Client
from app.models.invitation import Invitation, InvitationStatus

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserStatus",
    "Role",
    "user_roles",
    "role_permissions",
    "Permission",
    "Warehouse",
    "OperatorProfile",
    "Client",
    "Invitation",
    "InvitationStatus",
]
