"""
Tests for physical storage hierarchy and mandatory rack allocation.

Covers:
1. Successful allocation — product + rack allocation + INWARD ledger created
2. Allocation failure rollback — occupied rack rejects the operation
3. Temperature mismatch — blocks allocation when temps don't match
4. Capacity exceeded — blocks allocation when quantity > rack capacity
5. Rack exclusivity — two products can't be allocated to the same rack
6. Room & rack CRUD basics
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_ledger import InventoryLedger
from app.models.product import Product
from app.models.rack import Rack
from app.models.rack_allocation import RackAllocation
from app.models.room import Room
from app.services import product_service, room_service, rack_service

# Re-use shared fixtures from conftest
from tests.audit.conftest import seed_user, seed_warehouse


# ── Helpers ──────────────────────────────────────────────────────────

async def seed_room(
    db: AsyncSession,
    warehouse_id: uuid.UUID,
    *,
    name: str = "Room A",
    temperature_zone: float | None = -18.0,
) -> Room:
    """Insert a minimal Room and return it."""
    room = Room(
        id=uuid.uuid4(),
        name=name,
        warehouse_id=warehouse_id,
        temperature_zone=temperature_zone,
    )
    db.add(room)
    await db.flush()
    return room


async def seed_rack(
    db: AsyncSession,
    room_id: uuid.UUID,
    *,
    label: str = "R-001",
    capacity: float = 500.0,
    temperature: float | None = -18.0,
    is_occupied: bool = False,
) -> Rack:
    """Insert a minimal Rack and return it."""
    rack = Rack(
        id=uuid.uuid4(),
        label=label,
        room_id=room_id,
        capacity=Decimal(str(capacity)),
        temperature=Decimal(str(temperature)) if temperature is not None else None,
        is_occupied=is_occupied,
    )
    db.add(rack)
    await db.flush()
    return rack


# ── Tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_allocation(db: AsyncSession):
    """Product creation + rack allocation + INWARD ledger — all in one."""
    user = await seed_user(db, email="op@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    room = await seed_room(db, wh.id)
    rack = await seed_rack(db, room.id)

    product = await product_service.create_product(
        name="Frozen Shrimp",
        description="500kg pallet",
        category="FROZEN",
        unit="KG",
        quantity=200.0,
        lot_number="LOT-001",
        temperature_requirement=-18.0,
        warehouse_id=wh.id,
        rack_id=rack.id,
        created_by=user.id,
        db=db,
    )

    assert product.id is not None
    assert product.sku_code.startswith("FRZ-")

    # Rack must now be occupied
    await db.refresh(rack)
    assert rack.is_occupied is True

    # Allocation row must exist
    alloc_result = await db.execute(
        select(RackAllocation).where(RackAllocation.sku_id == product.id)
    )
    alloc = alloc_result.scalar_one()
    assert alloc.rack_id == rack.id
    assert alloc.released_at is None

    # INWARD ledger entry must exist
    ledger_result = await db.execute(
        select(InventoryLedger).where(InventoryLedger.sku_id == product.id)
    )
    ledger = ledger_result.scalar_one()
    assert ledger.movement_type == "INWARD"
    assert float(ledger.quantity_delta) == 200.0
    assert ledger.reference_type == "RackAllocation"
    assert ledger.reference_id == alloc.id


@pytest.mark.asyncio
async def test_occupied_rack_rejects_allocation(db: AsyncSession):
    """An already-occupied rack must reject a new product."""
    user = await seed_user(db, email="op2@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    room = await seed_room(db, wh.id)
    rack = await seed_rack(db, room.id, is_occupied=True)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await product_service.create_product(
            name="Frozen Peas",
            description=None,
            category="FROZEN",
            unit="KG",
            quantity=100.0,
            lot_number="LOT-002",
            temperature_requirement=-18.0,
            warehouse_id=wh.id,
            rack_id=rack.id,
            created_by=user.id,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert "already occupied" in exc_info.value.detail

    # No product should have been created
    prod_result = await db.execute(
        select(Product).where(Product.lot_number == "LOT-002")
    )
    assert prod_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_temperature_mismatch_blocks_allocation(db: AsyncSession):
    """Product temp != rack temp → 400 error."""
    user = await seed_user(db, email="op3@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    room = await seed_room(db, wh.id, temperature_zone=-18.0)
    rack = await seed_rack(db, room.id, temperature=-18.0)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await product_service.create_product(
            name="Chilled Milk",
            description=None,
            category="CHILLED",
            unit="LITRE",
            quantity=50.0,
            lot_number="LOT-003",
            temperature_requirement=4.0,  # doesn't match rack's -18.0
            warehouse_id=wh.id,
            rack_id=rack.id,
            created_by=user.id,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert "Temperature mismatch" in exc_info.value.detail


@pytest.mark.asyncio
async def test_capacity_exceeded_blocks_allocation(db: AsyncSession):
    """Quantity > rack capacity → 400 error."""
    user = await seed_user(db, email="op4@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    room = await seed_room(db, wh.id)
    rack = await seed_rack(db, room.id, capacity=100.0)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await product_service.create_product(
            name="Frozen Meat",
            description=None,
            category="FROZEN",
            unit="KG",
            quantity=200.0,  # exceeds rack capacity of 100
            lot_number="LOT-004",
            temperature_requirement=-18.0,
            warehouse_id=wh.id,
            rack_id=rack.id,
            created_by=user.id,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert "exceeds" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rack_exclusivity(db: AsyncSession):
    """After one product is allocated, the same rack rejects a second."""
    user = await seed_user(db, email="op5@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    room = await seed_room(db, wh.id)
    rack = await seed_rack(db, room.id, capacity=500.0)

    # First allocation succeeds
    await product_service.create_product(
        name="Frozen Fish",
        description=None,
        category="FROZEN",
        unit="KG",
        quantity=100.0,
        lot_number="LOT-005A",
        temperature_requirement=-18.0,
        warehouse_id=wh.id,
        rack_id=rack.id,
        created_by=user.id,
        db=db,
    )

    # Second allocation to same rack must fail
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await product_service.create_product(
            name="Frozen Lobster",
            description=None,
            category="FROZEN",
            unit="KG",
            quantity=50.0,
            lot_number="LOT-005B",
            temperature_requirement=-18.0,
            warehouse_id=wh.id,
            rack_id=rack.id,
            created_by=user.id,
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert "already occupied" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rack_wrong_warehouse_rejected(db: AsyncSession):
    """Rack in warehouse B cannot be used for warehouse A inward."""
    user = await seed_user(db, email="op6@test.com")
    wh_a = await seed_warehouse(db, admin_id=user.id)
    wh_b = await seed_warehouse(db, admin_id=user.id)

    room_b = await seed_room(db, wh_b.id, name="Room in WH-B")
    rack_b = await seed_rack(db, room_b.id, label="R-B-001")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await product_service.create_product(
            name="Frozen Goods",
            description=None,
            category="FROZEN",
            unit="KG",
            quantity=50.0,
            lot_number="LOT-006",
            temperature_requirement=-18.0,
            warehouse_id=wh_a.id,     # operating in warehouse A
            rack_id=rack_b.id,        # but rack is in warehouse B
            created_by=user.id,
            db=db,
        )

    assert exc_info.value.status_code == 400
    assert "does not belong" in exc_info.value.detail


@pytest.mark.asyncio
async def test_allocation_with_no_temperature_requirement(db: AsyncSession):
    """Product with no temp requirement can go into any rack."""
    user = await seed_user(db, email="op7@test.com")
    wh = await seed_warehouse(db, admin_id=user.id)
    room = await seed_room(db, wh.id)
    rack = await seed_rack(db, room.id, temperature=-18.0)

    product = await product_service.create_product(
        name="Dry Goods",
        description=None,
        category="DRY",
        unit="BOX",
        quantity=10.0,
        lot_number="LOT-007",
        temperature_requirement=None,  # no constraint
        warehouse_id=wh.id,
        rack_id=rack.id,
        created_by=user.id,
        db=db,
    )

    assert product.id is not None
    await db.refresh(rack)
    assert rack.is_occupied is True
