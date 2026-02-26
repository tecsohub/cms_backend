"""
Inventory service — client-facing inventory queries.

In the current implementation, physical inventory items are represented
by the ``Product`` model (table ``skus``).  Queries here filter that
table by the caller's ``DataScope``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.rbac.context_resolver import DataScope


async def list_inventory(
    db: AsyncSession,
    scope: DataScope,
    skip: int = 0,
    limit: int = 50,
) -> list[Product]:
    """
    List inventory items scoped to the caller's context.

    - Client scope    → filters by client_id
    - Warehouse scope → filters by warehouse_id
    - Admin scope     → no filter (returns all)
    - No scope        → returns empty list
    """
    stmt = select(Product)

    if scope.is_admin:
        pass  # no filter
    elif scope.client_id:
        stmt = stmt.where(Product.client_id == scope.client_id)
    elif scope.warehouse_id:
        stmt = stmt.where(Product.warehouse_id == scope.warehouse_id)
    else:
        return []

    stmt = stmt.order_by(Product.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
