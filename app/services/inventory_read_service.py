"""Inventory read service — real-time, ledger-derived query views."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.models.inventory_ledger import InventoryLedger
from app.models.product import Product
from app.rbac.context_resolver import DataScope


def _ensure_inventory_read_access(scope: DataScope) -> None:
    """Allow inventory read analytics only for admin/operator scopes."""
    if scope.client_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clients are not allowed to access inventory analytics",
        )


def _to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


async def get_inventory_dashboard(
    *,
    db: AsyncSession,
    scope: DataScope,
    skip: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Return real-time inventory summary per product.

    Derived only from ``inventory_ledger`` using SUM(quantity_delta), grouped
    by product and warehouse. Includes only positive current stock.
    """
    _ensure_inventory_read_access(scope)

    total_quantity = func.sum(InventoryLedger.quantity_delta)
    lot_count = func.count(func.distinct(InventoryLedger.lot_number))

    stmt = (
        select(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.unit.label("unit"),
            InventoryLedger.warehouse_id.label("warehouse_id"),
            total_quantity.label("total_quantity"),
            lot_count.label("lot_count"),
        )
        .join(Product, Product.id == InventoryLedger.sku_id)
        .group_by(
            Product.id,
            Product.name,
            Product.unit,
            InventoryLedger.warehouse_id,
        )
        .having(total_quantity > 0)
        .order_by(Product.name.asc())
        .offset(skip)
        .limit(limit)
    )

    if scope.warehouse_id is not None:
        stmt = stmt.where(InventoryLedger.warehouse_id == scope.warehouse_id)

    result = await db.execute(stmt)
    rows = result.all()

    output: list[dict[str, Any]] = []
    for row in rows:
        unit_value = row.unit.value if hasattr(row.unit, "value") else str(row.unit)
        output.append(
            {
                "product_id": row.product_id,
                "product_name": row.product_name,
                "unit": unit_value,
                "total_quantity": _to_float(row.total_quantity),
                "warehouse_id": row.warehouse_id,
                "has_lot_breakdown": bool((row.lot_count or 0) > 0),
            }
        )
    return output


async def get_inventory_lot_stock(
    *,
    db: AsyncSession,
    scope: DataScope,
    skip: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Return live stock grouped by Product × Lot.

    - current_quantity = SUM(quantity_delta)
    - inward_date = MIN(created_at where movement_type == INWARD)
    - only groups with current_quantity > 0
    """
    _ensure_inventory_read_access(scope)

    inward_date_expr = func.min(
        case(
            (InventoryLedger.movement_type == MovementType.INWARD, InventoryLedger.created_at),
            else_=None,
        )
    )
    current_quantity = func.sum(InventoryLedger.quantity_delta)

    stmt = (
        select(
            Product.id.label("product_id"),
            InventoryLedger.lot_number.label("lot_number"),
            inward_date_expr.label("inward_date"),
            current_quantity.label("current_quantity"),
            Product.unit.label("unit"),
            InventoryLedger.warehouse_id.label("warehouse_id"),
        )
        .join(Product, Product.id == InventoryLedger.sku_id)
        .group_by(
            Product.id,
            InventoryLedger.lot_number,
            Product.unit,
            InventoryLedger.warehouse_id,
        )
        .having(current_quantity > 0)
        .order_by(Product.id.asc(), InventoryLedger.lot_number.asc())
        .offset(skip)
        .limit(limit)
    )

    if scope.warehouse_id is not None:
        stmt = stmt.where(InventoryLedger.warehouse_id == scope.warehouse_id)

    result = await db.execute(stmt)
    rows = result.all()

    output: list[dict[str, Any]] = []
    for row in rows:
        # Defensive guard: a valid lot should always have an inward entry.
        if row.inward_date is None:
            continue

        unit_value = row.unit.value if hasattr(row.unit, "value") else str(row.unit)
        output.append(
            {
                "product_id": row.product_id,
                "lot_number": row.lot_number,
                "inward_date": row.inward_date,
                "current_quantity": _to_float(row.current_quantity),
                "unit": unit_value,
                "warehouse_id": row.warehouse_id,
            }
        )
    return output


async def get_inventory_aging(
    *,
    db: AsyncSession,
    scope: DataScope,
    skip: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Return inventory aging per Product × Lot.

    aging_days = (today_utc_date - inward_date_utc_date).days
    Includes only positive-current-stock groups.
    """
    lot_rows = await get_inventory_lot_stock(
        db=db,
        scope=scope,
        skip=skip,
        limit=limit,
    )

    today = datetime.now(timezone.utc).date()
    output: list[dict[str, Any]] = []

    for row in lot_rows:
        inward_date = row["inward_date"]
        inward_date_utc = (
            inward_date if inward_date.tzinfo is not None else inward_date.replace(tzinfo=timezone.utc)
        )
        aging_days = (today - inward_date_utc.date()).days

        output.append(
            {
                "product_id": row["product_id"],
                "lot_number": row["lot_number"],
                "inward_date": inward_date,
                "aging_days": aging_days,
                "current_quantity": row["current_quantity"],
                "unit": row["unit"],
            }
        )

    return output
