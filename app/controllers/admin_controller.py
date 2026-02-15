"""
Admin controller — warehouse management, user management, invitations.

Every route uses `Depends(require_permission(...))` for enforcement.
Controllers are THIN — they delegate to services and return schemas.

Architecture note:
    We inject `user: User` from `require_permission` so the controller
    has access to the authenticated admin's identity without a second
    DB call.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.rbac.context_resolver import DataScope, resolve_data_scope
from app.rbac.dependencies import require_permission
from app.schemas import (
    CreateInvitationRequest,
    CreateWarehouseRequest,
    InvitationOut,
    MessageResponse,
    UpdateWarehouseRequest,
    UserOut,
    WarehouseOut,
)
from app.services import invitation_service, user_service, warehouse_service

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ── Warehouses ───────────────────────────────────────────────────────
@router.post("/warehouses", response_model=WarehouseOut, status_code=201)
async def create_warehouse(
    body: CreateWarehouseRequest,
    user: User = Depends(require_permission("warehouse.create")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new cold-storage warehouse."""
    wh = await warehouse_service.create_warehouse(
        name=body.name,
        address=body.address,
        capacity=body.capacity,
        admin_id=user.id,
        db=db,
    )
    return WarehouseOut.model_validate(wh)


@router.get("/warehouses", response_model=list[WarehouseOut])
async def list_warehouses(
    user: User = Depends(require_permission("warehouse.create")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    scope = await resolve_data_scope(user, db)
    warehouses = await warehouse_service.list_warehouses(db, scope, skip, limit)
    return [WarehouseOut.model_validate(w) for w in warehouses]


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseOut)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    body: UpdateWarehouseRequest,
    user: User = Depends(require_permission("warehouse.update")),
    db: AsyncSession = Depends(get_db),
):
    scope = await resolve_data_scope(user, db)
    wh = await warehouse_service.update_warehouse(
        warehouse_id=warehouse_id,
        db=db,
        scope=scope,
        name=body.name,
        address=body.address,
        capacity=body.capacity,
    )
    return WarehouseOut.model_validate(wh)


# ── Users ────────────────────────────────────────────────────────────
@router.get("/users", response_model=list[UserOut])
async def list_users(
    user: User = Depends(require_permission("user.invite.operator")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    scope = await resolve_data_scope(user, db)
    users = await user_service.list_users(db, scope, skip, limit)
    return [
        UserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            phone=u.phone,
            address=u.address,
            status=u.status.value,
            roles=[r.name for r in u.roles],
            created_at=u.created_at,
        )
        for u in users
    ]


@router.post("/users/{user_id}/disable", response_model=MessageResponse)
async def disable_user(
    user_id: uuid.UUID,
    user: User = Depends(require_permission("user.invite.operator")),
    db: AsyncSession = Depends(get_db),
):
    await user_service.disable_user(user_id, db)
    return MessageResponse(detail="User disabled successfully")


# ── Invitations ──────────────────────────────────────────────────────
@router.post("/invitations", response_model=InvitationOut, status_code=201)
async def create_invitation(
    body: CreateInvitationRequest,
    user: User = Depends(require_permission("user.invite.operator")),
    db: AsyncSession = Depends(get_db),
):
    """
    Invite a new operator or client.

    Permission check is broad here (user.invite.operator).  For finer
    control (e.g. separate permission for inviting clients), add
    an additional check inside the service or use a different route.
    """
    invite = await invitation_service.create_invitation(
        email=body.email,
        role_assigned=body.role_assigned,
        invited_by=user.id,
        db=db,
    )
    return InvitationOut.model_validate(invite)


@router.get("/invitations", response_model=list[InvitationOut])
async def list_invitations(
    user: User = Depends(require_permission("user.invite.operator")),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    invites = await invitation_service.list_invitations(db, skip, limit)
    return [InvitationOut.model_validate(inv) for inv in invites]
