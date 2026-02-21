"""
Tests for the to_audit_dict() serialization helper.

Covers:
- UUID → str conversion
- datetime → ISO format conversion
- Decimal → str conversion
- Enum → value conversion
- Secret columns are excluded
- Relationships are excluded (only scalar columns)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.user import User, UserStatus
from app.models.warehouse import Warehouse
from app.models.invitation import Invitation, InvitationStatus
from app.services.audit_serializer import to_audit_dict


def test_uuid_serialised_as_string():
    """UUID fields must appear as plain strings in the audit dict."""
    uid = uuid.uuid4()
    user = User(
        id=uid,
        email="serial@test.com",
        full_name="Serial Test",
        password_hash="secret",
        status=UserStatus.ACTIVE,
    )
    result = to_audit_dict(user)
    assert result["id"] == str(uid)
    assert isinstance(result["id"], str)


def test_datetime_serialised_as_iso():
    """datetime fields must appear in ISO 8601 format."""
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        email="dt@test.com",
        full_name="DT Test",
        status=UserStatus.ACTIVE,
    )
    user.created_at = now
    result = to_audit_dict(user)
    assert result["created_at"] == now.isoformat()


def test_enum_serialised_as_value():
    """Enum fields must appear as their string value, not the enum instance."""
    user = User(
        id=uuid.uuid4(),
        email="enum@test.com",
        full_name="Enum Test",
        status=UserStatus.DISABLED,
    )
    result = to_audit_dict(user)
    assert result["status"] == "DISABLED"


def test_secrets_excluded():
    """password_hash and token must never appear in audit output."""
    user = User(
        id=uuid.uuid4(),
        email="safe@test.com",
        full_name="Safe User",
        password_hash="$2b$12$supersecret",
        status=UserStatus.ACTIVE,
    )
    result = to_audit_dict(user)
    assert "password_hash" not in result

    invite = Invitation(
        id=uuid.uuid4(),
        email="inv@test.com",
        invited_by=uuid.uuid4(),
        role_assigned="OPERATOR",
        token="secret-token-value",
        expires_at=datetime.now(timezone.utc),
        status=InvitationStatus.PENDING,
    )
    inv_result = to_audit_dict(invite)
    assert "token" not in inv_result


def test_relationships_excluded():
    """
    to_audit_dict must only return column attributes.
    User.roles is a relationship and must NOT appear.
    """
    user = User(
        id=uuid.uuid4(),
        email="rel@test.com",
        full_name="Rel Test",
        status=UserStatus.ACTIVE,
    )
    result = to_audit_dict(user)
    assert "roles" not in result
    assert "operator_profile" not in result
    assert "client" not in result


def test_warehouse_serialisation():
    """Warehouse columns should be fully serialised, including nullable capacity."""
    wid = uuid.uuid4()
    admin_id = uuid.uuid4()
    wh = Warehouse(
        id=wid,
        name="Frost Unit",
        address="10 Ice Road",
        capacity=500,
        created_by_admin_id=admin_id,
    )
    result = to_audit_dict(wh)
    assert result["id"] == str(wid)
    assert result["name"] == "Frost Unit"
    assert result["capacity"] == 500
    assert result["created_by_admin_id"] == str(admin_id)


def test_nullable_fields_serialised_as_none():
    """Nullable columns that are None must appear as None, not be omitted."""
    user = User(
        id=uuid.uuid4(),
        email="null@test.com",
        full_name="Null Test",
        status=UserStatus.ACTIVE,
        phone=None,
        address=None,
    )
    result = to_audit_dict(user)
    assert "phone" in result
    assert result["phone"] is None
    assert "address" in result
    assert result["address"] is None
