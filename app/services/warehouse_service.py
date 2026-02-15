"""
Warehouse service.

All queries are scope-filtered:
- Admin sees everything.
- Operator sees only their assigned warehouse.
- Client sees nothing (no warehouse permission expected).
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.warehouse import Warehouse
from app.rbac.context_resolver import DataScope


async def create_warehouse(
    name: str,
    address: str,
    capacity: int | None,
    admin_id: uuid.UUID,
    db: AsyncSession,
) -> Warehouse:
    """Create a new warehouse (admin only — enforced at controller)."""
    warehouse = Warehouse(
        id=uuid.uuid4(),
        name=name,
        address=address,
        capacity=capacity,
        created_by_admin_id=admin_id,
    )
    db.add(warehouse)
    await db.flush()
    return warehouse


async def list_warehouses(
    db: AsyncSession,
    scope: DataScope,
    skip: int = 0,
    limit: int = 50,
) -> list[Warehouse]:
    """List warehouses — scoped by the caller's role."""
    stmt = select(Warehouse)

    if scope.is_admin:
        pass  # no filter
    elif scope.warehouse_id:
        # Operator sees only their own warehouse
        stmt = stmt.where(Warehouse.id == scope.warehouse_id)
    else:
        # Other roles: return empty or raise
        return []

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_warehouse_by_id(
    warehouse_id: uuid.UUID,
    db: AsyncSession,
    scope: DataScope,
) -> Warehouse:
    """Get a single warehouse — enforcing data scope."""
    stmt = select(Warehouse).where(Warehouse.id == warehouse_id)

    if not scope.is_admin and scope.warehouse_id:
        if scope.warehouse_id != warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this warehouse",
            )

    result = await db.execute(stmt)
    wh = result.scalar_one_or_none()
    if wh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    return wh


async def update_warehouse(
    warehouse_id: uuid.UUID,
    db: AsyncSession,
    scope: DataScope,
    name: str | None = None,
    address: str | None = None,
    capacity: int | None = None,
) -> Warehouse:
    """Update warehouse details (admin only — enforced at controller)."""
    wh = await get_warehouse_by_id(warehouse_id, db, scope)
    if name is not None:
        wh.name = name
    if address is not None:
        wh.address = address
    if capacity is not None:
        wh.capacity = capacity
    await db.flush()
    return wh
