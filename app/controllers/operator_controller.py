"""
Operator controller — warehouse-scoped views and inventory actions.

Every route enforces:
1. Permission (via `require_permission`)
2. Data scope (via `resolve_data_scope` — locks to operator's warehouse)
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.rbac.context_resolver import resolve_data_scope
from app.rbac.dependencies import require_permission
from app.schemas import (
    InwardRequest,
    InwardResponse,
    MessageResponse,
    ProductCreateRequest,
    ProductOut,
    TemperatureZoneCreateRequest,
    TemperatureZoneOut,
    TemperatureZoneUpdateRequest,
    WarehouseOut,
)

from app.services import warehouse_service, product_service, temperature_zone_service

router = APIRouter(prefix="/api/operator", tags=["Operator"])


@router.get("/my-warehouse", response_model=WarehouseOut)
async def get_my_warehouse(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the warehouse this operator is assigned to.

    The data scope ensures the operator can ONLY see their own warehouse.
    """
    scope = await resolve_data_scope(user, db)
    if scope.warehouse_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No warehouse assigned",
        )
    wh = await warehouse_service.get_warehouse_by_id(scope.warehouse_id, db, scope)
    return WarehouseOut.model_validate(wh)


# ── Product + inward endpoints ───────────────────────────────────────

@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreateRequest,
    user: User = Depends(require_permission("inventory.inward.create")),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 1: Create logical product (draft SKU entity).
    """
    scope = await resolve_data_scope(user, db)
    if scope.warehouse_id:
        body.warehouse_id = scope.warehouse_id  # enforce warehouse assignment for operators


    product = await product_service.create_product(
        name=body.name,
        description=body.description,
        category=body.category,
        unit=body.unit,
        temperature_requirement=body.temperature_requirement,
        warehouse_id=body.warehouse_id,
        created_by=user.id,
        db=db,
    )
    return ProductOut.model_validate(product)


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List products/pallets for the operator's warehouse."""
    scope = await resolve_data_scope(user, db)
    products = await product_service.list_products(db, scope, skip, limit)
    return [ProductOut.model_validate(p) for p in products]


@router.get("/products/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: uuid.UUID,
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
):
    """Get a single product by ID."""
    scope = await resolve_data_scope(user, db)
    product = await product_service.get_product_by_id(product_id, db, scope)
    return ProductOut.model_validate(product)


# ── Legacy stubs (kept for backward compat, delegate to new logic) ───

@router.get("/inventory")
async def list_inventory(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List inventory for the operator's warehouse.
    """
    scope = await resolve_data_scope(user, db)
    products = await product_service.list_products(db, scope, skip, limit)
    return [ProductOut.model_validate(p) for p in products]


@router.post("/inventory/inward", response_model=InwardResponse, status_code=201)
async def create_inward(
    body: InwardRequest,
    user: User = Depends(require_permission("inventory.inward.create")),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2: complete inward for an existing product draft.

    On inward failure, draft product is auto-deleted.
    """
    scope = await resolve_data_scope(user, db)
    # if scope.warehouse_id is None:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="No warehouse assigned",
    #     )

    result = await product_service.inward_product_with_cleanup(
        product_id=body.product_id,
        client_email=body.client_email,
        rack_id=body.rack_id,
        quantity=body.quantity,
        lot_number=body.lot_number,
        operator_id=user.id,
        scope=scope,
        db=db,
    )
    if not result["success"]:
        raise HTTPException(
            status_code=result["status_code"],
            detail=result["detail"],
        )

    return InwardResponse(
        detail=result["detail"],
        product_id=result["product_id"],
        ledger_id=result["ledger_id"],
        rack_allocation_id=result["rack_allocation_id"],
        client_linked=result["client_linked"],
        invitation_sent=result["invitation_sent"],
    )


@router.post("/temperature-zones", response_model=TemperatureZoneOut, status_code=201)
async def create_temperature_zone(
    body: TemperatureZoneCreateRequest,
    user: User = Depends(require_permission("temperature.zone.create")),
    db: AsyncSession = Depends(get_db),
):
    zone = await temperature_zone_service.create_temperature_zone(
        zone_name=body.zone_name,
        min_temp=body.min_temp,
        max_temp=body.max_temp,
        created_by=user.id,
        db=db,
    )
    return TemperatureZoneOut.model_validate(zone)


@router.get("/temperature-zones", response_model=list[TemperatureZoneOut])
async def list_temperature_zones(
    user: User = Depends(require_permission("temperature.zone.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    zones = await temperature_zone_service.list_temperature_zones(db, skip=skip, limit=limit)
    return [TemperatureZoneOut.model_validate(z) for z in zones]


@router.patch("/temperature-zones/{zone_id}", response_model=TemperatureZoneOut)
async def update_temperature_zone(
    zone_id: uuid.UUID,
    body: TemperatureZoneUpdateRequest,
    user: User = Depends(require_permission("temperature.zone.update")),
    db: AsyncSession = Depends(get_db),
):
    zone = await temperature_zone_service.update_temperature_zone(
        zone_id=zone_id,
        zone_name=body.zone_name,
        min_temp=body.min_temp,
        max_temp=body.max_temp,
        updated_by=user.id,
        db=db,
    )
    return TemperatureZoneOut.model_validate(zone)


@router.delete("/temperature-zones/{zone_id}", response_model=MessageResponse)
async def delete_temperature_zone(
    zone_id: uuid.UUID,
    user: User = Depends(require_permission("temperature.zone.delete")),
    db: AsyncSession = Depends(get_db),
):
    await temperature_zone_service.delete_temperature_zone(
        zone_id=zone_id,
        deleted_by=user.id,
        db=db,
    )
    return MessageResponse(detail="Temperature zone deleted")
