"""
Operator controller — warehouse-scoped views and inventory actions.

Every route enforces:
1. Permission (via `require_permission`)
2. Data scope (via `resolve_data_scope` — locks to operator's warehouse)
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.rbac.context_resolver import DataScope, resolve_data_scope
from app.rbac.dependencies import require_permission
from app.schemas import (
    LinkClientResponse,
    ProductCreateRequest,
    ProductLinkClientRequest,
    ProductOut,
    WarehouseOut,
)

from app.services import warehouse_service, product_service

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
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No warehouse assigned",
        )
    wh = await warehouse_service.get_warehouse_by_id(scope.warehouse_id, db, scope)
    return WarehouseOut.model_validate(wh)


# ── Product intake endpoints ─────────────────────────────────────────

@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreateRequest,
    user: User = Depends(require_permission("inventory.inward.create")),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 1 of intake: Operator enters product/pallet details.

    Auto-generates a SKU code in the format:
        {CATEGORY}-{WAREHOUSE_CODE}-{YYYYMMDD}-{SEQ}
    """
    scope = await resolve_data_scope(user, db)
    if scope.warehouse_id is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No warehouse assigned",
        )

    product = await product_service.create_product(
        name=body.name,
        description=body.description,
        category=body.category,
        unit=body.unit,
        quantity=body.quantity,
        lot_number=body.lot_number,
        temperature_requirement=body.temperature_requirement,
        warehouse_id=scope.warehouse_id,
        created_by=user.id,
        db=db,
    )
    return ProductOut.model_validate(product)


@router.post("/products/{product_id}/link-client", response_model=LinkClientResponse)
async def link_client_to_product(
    product_id: uuid.UUID,
    body: ProductLinkClientRequest,
    user: User = Depends(require_permission("inventory.inward.create")),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2 of intake: Operator provides the client's email.

    - If a CLIENT user with that email exists → product is linked immediately.
    - If no user found → a CLIENT invitation is created and emailed.
      When the client accepts, their client_id is back-filled on the product.
    """
    scope = await resolve_data_scope(user, db)
    if scope.warehouse_id is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No warehouse assigned",
        )

    result = await product_service.link_client_to_product(
        product_id=product_id,
        email=body.email,
        operator_id=user.id,
        db=db,
    )
    return LinkClientResponse(**result)


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


@router.post("/inventory/inward", response_model=ProductOut, status_code=201)
async def create_inward(
    body: ProductCreateRequest,
    user: User = Depends(require_permission("inventory.inward.create")),
    db: AsyncSession = Depends(get_db),
):
    """Create an inward entry — delegates to product creation."""
    scope = await resolve_data_scope(user, db)
    if scope.warehouse_id is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No warehouse assigned",
        )

    product = await product_service.create_product(
        name=body.name,
        description=body.description,
        category=body.category,
        unit=body.unit,
        quantity=body.quantity,
        lot_number=body.lot_number,
        temperature_requirement=body.temperature_requirement,
        warehouse_id=scope.warehouse_id,
        created_by=user.id,
        db=db,
    )
    return ProductOut.model_validate(product)
