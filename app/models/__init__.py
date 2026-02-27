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
from app.models.session import UserSession
from app.models.enums import MovementType, AuditAction
from app.models.product import Product, ProductCategory, StorageUnit
from app.models.inventory_ledger import InventoryLedger
from app.models.audit_log import AuditLog
from app.models.password_reset_otp import PasswordResetOTP
from app.models.room import Room
from app.models.rack import Rack
from app.models.rack_allocation import RackAllocation

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
    "UserSession",
    "MovementType",
    "AuditAction",
    "Product",
    "ProductCategory",
    "StorageUnit",
    "InventoryLedger",
    "AuditLog",
    "PasswordResetOTP",
    "Room",
    "Rack",
    "RackAllocation",
]
