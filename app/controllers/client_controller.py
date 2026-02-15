"""
Client controller — client-scoped views.

Every route enforces:
1. Permission (via `require_permission`)
2. Data scope (via `resolve_data_scope` — locks to client's own data)

Clients have a contractually fixed single login and can only see
their own inventory and invoices.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.rbac.context_resolver import resolve_data_scope
from app.rbac.dependencies import require_permission
from app.schemas import ClientOut

router = APIRouter(prefix="/api/client", tags=["Client"])


@router.get("/me", response_model=ClientOut)
async def get_my_profile(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
):
    """Return the client's own profile."""
    if user.client is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client profile not found",
        )
    return ClientOut.model_validate(user.client)


@router.get("/inventory")
async def list_my_inventory(
    user: User = Depends(require_permission("inventory.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List inventory belonging to this client.

    When the Inventory model is added, the service will filter:
        query.where(Inventory.client_id == scope.client_id)
    """
    scope = await resolve_data_scope(user, db)
    # TODO: replace with inventory_service.list_inventory(db, scope, skip, limit)
    return {
        "detail": "Client inventory listing (stub)",
        "client_id": str(scope.client_id),
    }


@router.get("/invoices")
async def list_my_invoices(
    user: User = Depends(require_permission("invoice.view")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List invoices for this client.

    When the Invoice model is added, the service will filter:
        query.where(Invoice.client_id == scope.client_id)
    """
    scope = await resolve_data_scope(user, db)
    # TODO: replace with billing_service.list_invoices(db, scope, skip, limit)
    return {
        "detail": "Client invoices listing (stub)",
        "client_id": str(scope.client_id),
    }
