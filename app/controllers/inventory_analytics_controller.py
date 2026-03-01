"""Inventory analytics controller — dedicated real-time read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.rbac.context_resolver import resolve_data_scope
from app.rbac.dependencies import require_permission
from app.schemas import InventoryAgingOut, InventoryDashboardOut, InventoryLotStockOut
from app.services import inventory_read_service

router = APIRouter(prefix="/api/inventory", tags=["Inventory Analytics"])


@router.get("/dashboard", response_model=list[InventoryDashboardOut])
async def inventory_dashboard(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    scope = await resolve_data_scope(user, db)
    rows = await inventory_read_service.get_inventory_dashboard(
        db=db,
        scope=scope,
        skip=skip,
        limit=limit,
    )
    return [InventoryDashboardOut.model_validate(row) for row in rows]


@router.get("/lot-stock", response_model=list[InventoryLotStockOut])
async def inventory_lot_stock(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    scope = await resolve_data_scope(user, db)
    rows = await inventory_read_service.get_inventory_lot_stock(
        db=db,
        scope=scope,
        skip=skip,
        limit=limit,
    )
    return [InventoryLotStockOut.model_validate(row) for row in rows]


@router.get("/aging", response_model=list[InventoryAgingOut])
async def inventory_aging(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    scope = await resolve_data_scope(user, db)
    rows = await inventory_read_service.get_inventory_aging(
        db=db,
        scope=scope,
        skip=skip,
        limit=limit,
    )
    return [InventoryAgingOut.model_validate(row) for row in rows]
