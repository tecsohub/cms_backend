"""
Tests for the InventoryLedger model.

Covers:
- Ledger entries are immutable (append-only)
- Inventory quantity can be correctly derived from SUM(quantity_delta)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.models.inventory_ledger import InventoryLedger
from tests.audit.conftest import seed_user, seed_warehouse, seed_sku


# ─────────────────────────────────────────────────────────────────────
# Helper — insert a ledger entry (no SKU table exists yet, so we
# skip the FK and use a raw UUID for sku_id in these unit tests).
# The FK to `skus` is defined on the model but SQLite won't enforce
# it unless the referenced table exists, so we can safely test logic.
# ─────────────────────────────────────────────────────────────────────


async def _insert_ledger_entry(
    db: AsyncSession,
    *,
    sku_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    performed_by: uuid.UUID,
    movement_type: MovementType,
    quantity_delta: Decimal,
    reference_type: str = "test",
    reference_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> InventoryLedger:
    entry = InventoryLedger(
        id=uuid.uuid4(),
        sku_id=sku_id,
        warehouse_id=warehouse_id,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        reference_type=reference_type,
        reference_id=reference_id or uuid.uuid4(),
        performed_by=performed_by,
        reason=reason,
    )
    db.add(entry)
    await db.flush()
    return entry


# ─────────────────────────────────────────────────────────────────────
# 1. Ledger entries are immutable — INSERT only
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ledger_entry_creation(db: AsyncSession):
    """A ledger row can be inserted and read back."""
    user = await seed_user(db, email="ledger-insert@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    sku_id = await seed_sku(db, warehouse_id=wh.id, created_by=user.id)

    entry = await _insert_ledger_entry(
        db,
        sku_id=sku_id,
        warehouse_id=wh.id,
        performed_by=user.id,
        movement_type=MovementType.INWARD,
        quantity_delta=Decimal("100.500"),
    )

    result = await db.execute(
        select(InventoryLedger).where(InventoryLedger.id == entry.id)
    )
    row = result.scalar_one()
    assert row.sku_id == sku_id
    assert row.movement_type == MovementType.INWARD
    assert row.quantity_delta == Decimal("100.500")


@pytest.mark.asyncio
async def test_ledger_immutability_principle(db: AsyncSession):
    """
    Ledger design: new mutations must be tracked as new rows,
    not updates to existing ones.  We verify that inserting two
    entries for the same SKU produces two distinct rows.
    """
    user = await seed_user(db, email="ledger-immut@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    sku_id = await seed_sku(db, warehouse_id=wh.id, created_by=user.id)

    await _insert_ledger_entry(
        db,
        sku_id=sku_id,
        warehouse_id=wh.id,
        performed_by=user.id,
        movement_type=MovementType.INWARD,
        quantity_delta=Decimal("50.000"),
    )
    await _insert_ledger_entry(
        db,
        sku_id=sku_id,
        warehouse_id=wh.id,
        performed_by=user.id,
        movement_type=MovementType.OUTWARD,
        quantity_delta=Decimal("-20.000"),
    )

    result = await db.execute(
        select(InventoryLedger).where(InventoryLedger.sku_id == sku_id)
    )
    rows = result.scalars().all()
    assert len(rows) == 2


# ─────────────────────────────────────────────────────────────────────
# 2. Inventory can be derived from SUM(quantity_delta)
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inventory_derived_from_ledger_sum(db: AsyncSession):
    """
    Current inventory = SUM(quantity_delta) grouped by sku_id.
    After +100, -30, +10 the available quantity must be 80.
    """
    user = await seed_user(db, email="ledger-sum@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    sku_id = await seed_sku(db, warehouse_id=wh.id, created_by=user.id)

    for mt, delta in [
        (MovementType.INWARD, Decimal("100.000")),
        (MovementType.OUTWARD, Decimal("-30.000")),
        (MovementType.ADJUSTMENT, Decimal("10.000")),
    ]:
        await _insert_ledger_entry(
            db,
            sku_id=sku_id,
            warehouse_id=wh.id,
            performed_by=user.id,
            movement_type=mt,
            quantity_delta=delta,
        )

    result = await db.execute(
        select(func.sum(InventoryLedger.quantity_delta)).where(
            InventoryLedger.sku_id == sku_id
        )
    )
    total = result.scalar()
    assert total == Decimal("80.000")


@pytest.mark.asyncio
async def test_inventory_derived_per_warehouse(db: AsyncSession):
    """SUM should partition correctly when entries span multiple warehouses."""
    user = await seed_user(db, email="ledger-wh@test.com")
    wh_a = await seed_warehouse(db, admin_id=user.id)

    # Create a second warehouse manually
    from app.models.warehouse import Warehouse

    wh_b = Warehouse(
        id=uuid.uuid4(),
        name="Store B",
        address="456 Ice Blvd",
        capacity=500,
        created_by_admin_id=user.id,
    )
    db.add(wh_b)
    await db.flush()

    sku_id = await seed_sku(db, warehouse_id=wh_a.id, created_by=user.id)

    await _insert_ledger_entry(
        db,
        sku_id=sku_id,
        warehouse_id=wh_a.id,
        performed_by=user.id,
        movement_type=MovementType.INWARD,
        quantity_delta=Decimal("200.000"),
    )
    await _insert_ledger_entry(
        db,
        sku_id=sku_id,
        warehouse_id=wh_b.id,
        performed_by=user.id,
        movement_type=MovementType.INWARD,
        quantity_delta=Decimal("50.000"),
    )

    result = await db.execute(
        select(
            InventoryLedger.warehouse_id,
            func.sum(InventoryLedger.quantity_delta),
        )
        .where(InventoryLedger.sku_id == sku_id)
        .group_by(InventoryLedger.warehouse_id)
    )
    rows = {r[0]: r[1] for r in result.all()}
    assert rows[wh_a.id] == Decimal("200.000")
    assert rows[wh_b.id] == Decimal("50.000")
