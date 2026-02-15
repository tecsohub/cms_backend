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
from app.schemas import WarehouseOut

from app.services import warehouse_service

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


# ── Example: inventory-scoped endpoints ──────────────────────────────
# These are stubs — the actual inventory model will be added later.
# They demonstrate how permission + scope work together.

@router.get("/inventory")
async def list_inventory(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List inventory for the operator's warehouse.

    When the Inventory model is added, the service will filter:
        query.where(Inventory.warehouse_id == scope.warehouse_id)
    """
    scope = await resolve_data_scope(user, db)
    # TODO: replace with inventory_service.list_inventory(db, scope, skip, limit)
    return {
        "detail": "Inventory listing (stub)",
        "warehouse_id": str(scope.warehouse_id),
    }


@router.post("/inventory/inward")
async def create_inward(
    user: User = Depends(require_permission("inventory.inward.create")),
    db: AsyncSession = Depends(get_db),
):
    """Create an inward entry — operator must have inventory.inward.create."""
    scope = await resolve_data_scope(user, db)
    # TODO: replace with inventory_service.create_inward(data, db, scope)
    return {
        "detail": "Inward created (stub)",
        "warehouse_id": str(scope.warehouse_id),
    }
