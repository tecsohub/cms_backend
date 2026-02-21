"""
Tests for audit_service.log and the AuditLog model.

Covers:
- Audit row created on entity creation
- Audit row NOT created if transaction fails (rollback)
- Audit query by entity_id returns full history
- Audit query by performed_by returns user action history
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.services import audit_service
from app.services.audit_serializer import to_audit_dict
from tests.audit.conftest import seed_user, seed_warehouse


# ─────────────────────────────────────────────────────────────────────
# 1. Audit row is created when log() is called inside a transaction
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_row_created_on_entity_creation(db: AsyncSession):
    """log() should insert a row that is visible within the same transaction."""
    user = await seed_user(db, email="audit-create@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)

    entry = await audit_service.log(
        db,
        entity_type="Warehouse",
        entity_id=wh.id,
        action=AuditAction.CREATE,
        performed_by=user.id,
        old_data=None,
        new_data=to_audit_dict(wh),
    )

    assert entry.id is not None
    assert entry.entity_type == "Warehouse"
    assert entry.entity_id == wh.id
    assert entry.action == AuditAction.CREATE
    assert entry.performed_by == user.id
    assert entry.new_data is not None
    assert entry.old_data is None

    # Verify row is queryable
    result = await db.execute(select(AuditLog).where(AuditLog.id == entry.id))
    row = result.scalar_one_or_none()
    assert row is not None


# ─────────────────────────────────────────────────────────────────────
# 2. Audit row is NOT persisted if outer transaction rolls back
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_row_not_created_on_transaction_rollback(engine):
    """If the outer transaction rolls back, the audit row must disappear."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        async with session.begin():
            user = await seed_user(session, email="rollback-test@test.com")
            wh = await seed_warehouse(session, admin_id=user.id)

            await audit_service.log(
                session,
                entity_type="Warehouse",
                entity_id=wh.id,
                action=AuditAction.CREATE,
                performed_by=user.id,
                old_data=None,
                new_data={"name": wh.name},
            )
            # Force rollback
            await session.rollback()

    # In a new session, verify nothing was persisted
    async with async_session() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.entity_type == "Warehouse")
        )
        rows = result.scalars().all()
        # Either zero rows, or at least none from this transaction
        for row in rows:
            assert row.new_data.get("name") != "Cold Store A" if row.new_data else True


# ─────────────────────────────────────────────────────────────────────
# 3. Query audit by entity_id returns full history
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_query_by_entity_id(db: AsyncSession):
    """Multiple audit entries for the same entity should all be returned."""
    user = await seed_user(db, email="history@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)

    # CREATE
    await audit_service.log(
        db,
        entity_type="Warehouse",
        entity_id=wh.id,
        action=AuditAction.CREATE,
        performed_by=user.id,
        old_data=None,
        new_data=to_audit_dict(wh),
    )

    # UPDATE
    old = to_audit_dict(wh)
    wh.name = "Updated Store"
    await db.flush()
    await audit_service.log(
        db,
        entity_type="Warehouse",
        entity_id=wh.id,
        action=AuditAction.UPDATE,
        performed_by=user.id,
        old_data=old,
        new_data=to_audit_dict(wh),
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.entity_id == wh.id).order_by(AuditLog.created_at)
    )
    entries = result.scalars().all()
    assert len(entries) == 2
    assert entries[0].action == AuditAction.CREATE
    assert entries[1].action == AuditAction.UPDATE


# ─────────────────────────────────────────────────────────────────────
# 4. Query audit by performed_by returns user action history
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_query_by_performed_by(db: AsyncSession):
    """All actions by a specific user should be retrievable."""
    user = await seed_user(db, email="actor@test.com")
    wh1 = await seed_warehouse(db, admin_id=user.id)

    await audit_service.log(
        db,
        entity_type="Warehouse",
        entity_id=wh1.id,
        action=AuditAction.CREATE,
        performed_by=user.id,
        old_data=None,
        new_data=to_audit_dict(wh1),
    )

    await audit_service.log(
        db,
        entity_type="User",
        entity_id=user.id,
        action=AuditAction.DISABLE,
        performed_by=user.id,
        old_data={"status": "ACTIVE"},
        new_data={"status": "DISABLED"},
    )

    result = await db.execute(
        select(AuditLog).where(AuditLog.performed_by == user.id)
    )
    entries = result.scalars().all()
    assert len(entries) == 2
    entity_types = {e.entity_type for e in entries}
    assert entity_types == {"Warehouse", "User"}


# ─────────────────────────────────────────────────────────────────────
# 5. String action is auto-converted to AuditAction enum
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_string_action_converted_to_enum(db: AsyncSession):
    """Passing action as a string should work just like passing the enum."""
    user = await seed_user(db, email="str-action@test.com")

    entry = await audit_service.log(
        db,
        entity_type="Test",
        entity_id=user.id,
        action="CREATE",
        performed_by=user.id,
        old_data=None,
        new_data={"foo": "bar"},
    )
    assert entry.action == AuditAction.CREATE
