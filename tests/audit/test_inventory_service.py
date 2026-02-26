"""
Tests for inventory_service.list_inventory.

Verifies that the service correctly scopes results by client_id,
handles pagination, and returns an empty list for an unscoped context.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductCategory, StorageUnit
from app.rbac.context_resolver import DataScope
from app.services import inventory_service
from tests.audit.conftest import seed_user, seed_warehouse, seed_client


# ── Seed helper ──────────────────────────────────────────────────────

async def _seed_product(
    db: AsyncSession,
    *,
    warehouse_id: uuid.UUID,
    created_by: uuid.UUID,
    client_id: uuid.UUID | None = None,
    sku_suffix: str = "0001",
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        name="Frozen Salmon",
        category=ProductCategory.FROZEN,
        unit=StorageUnit.KG,
        quantity=100.0,
        lot_number="LOT-001",
        sku_code=f"FRZ-TEST-20260226-{sku_suffix}",
        warehouse_id=warehouse_id,
        created_by=created_by,
        client_id=client_id,
    )
    db.add(product)
    await db.flush()
    return product


# ── Tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_inventory_client_scope(db: AsyncSession):
    """Client scope returns only products assigned to that client."""
    user = await seed_user(db, email="inv-client@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    client_user = await seed_user(db, email="inv-client-user@test.com")
    client = await seed_client(db, user_id=client_user.id)

    # Product owned by the client
    p1 = await _seed_product(
        db, warehouse_id=wh.id, created_by=user.id, client_id=client.id, sku_suffix="0001",
    )
    # Product NOT owned by the client
    await _seed_product(
        db, warehouse_id=wh.id, created_by=user.id, client_id=None, sku_suffix="0002",
    )

    scope = DataScope(is_admin=False, warehouse_id=None, client_id=client.id)
    results = await inventory_service.list_inventory(db, scope)

    assert len(results) == 1
    assert results[0].id == p1.id


@pytest.mark.asyncio
async def test_list_inventory_no_scope_returns_empty(db: AsyncSession):
    """A scope with no client_id, warehouse_id, or admin flag returns empty."""
    scope = DataScope(is_admin=False, warehouse_id=None, client_id=None)
    results = await inventory_service.list_inventory(db, scope)
    assert results == []


@pytest.mark.asyncio
async def test_list_inventory_pagination(db: AsyncSession):
    """skip and limit are applied correctly."""
    user = await seed_user(db, email="inv-page@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    client_user = await seed_user(db, email="inv-page-user@test.com")
    client = await seed_client(db, user_id=client_user.id)

    for i in range(5):
        await _seed_product(
            db,
            warehouse_id=wh.id,
            created_by=user.id,
            client_id=client.id,
            sku_suffix=f"{i:04d}",
        )

    scope = DataScope(is_admin=False, warehouse_id=None, client_id=client.id)
    page1 = await inventory_service.list_inventory(db, scope, skip=0, limit=3)
    page2 = await inventory_service.list_inventory(db, scope, skip=3, limit=3)

    assert len(page1) == 3
    assert len(page2) == 2
    # No overlap
    ids1 = {p.id for p in page1}
    ids2 = {p.id for p in page2}
    assert ids1.isdisjoint(ids2)
