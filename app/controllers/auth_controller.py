"""
Auth controller — login, logout, token refresh & invitation acceptance.

Login and invitation routes are PUBLIC (no permission dependency).
Logout requires a valid session.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_token
from app.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationRequestOperator,
    InvitationOut,
    InvitationOutOperator,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth_service, session_service

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password + device_id → receive JWT pair."""
    return await auth_service.authenticate_user(
        body.email, body.password, body.device_id, db,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access + refresh pair."""
    return await auth_service.refresh_access_token(body.refresh_token, db)


@router.delete("/logout", response_model=MessageResponse)
async def logout(
    token_payload: dict[str, Any] = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate the current session (server-side logout)."""
    session_id = token_payload["session_id"]
    await session_service.deactivate_session(uuid.UUID(session_id), db)
    return MessageResponse(detail="Logged out successfully")


@router.post("/accept-invitation", response_model=UserOut)
async def accept_invitation(
    body: AcceptInvitationRequest | AcceptInvitationRequestOperator,
    db: AsyncSession = Depends(get_db),
):
    """Accept a pending invitation, set password, activate account."""
    user = await auth_service.accept_invitation(
        warehouse_id=body.warehouse_id,
        token=body.token,
        password=body.password,
        full_name=body.full_name,
        db=db,
        shift_start=getattr(body, "shift_start", None),
        shift_end=getattr(body, "shift_end", None),
    )
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        address=user.address,
        status=user.status.value,
        roles=[r.name for r in user.roles],
        created_at=user.created_at,
    )

@router.get("/accept-invitation", response_model=InvitationOutOperator)
async def get_invitation(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> InvitationOutOperator:
    """Fetch invitation details for a given token (used by frontend to validate token before showing form)."""
    invite = await auth_service.get_invitation_by_token(token, db)
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found or already accepted")

    warehouses = await auth_service.get_all_warehouses(db)
    return InvitationOutOperator(
        id=invite.id,
        email=invite.email,
        role_assigned=invite.role_assigned,
        token=invite.token,
        status=invite.status.value,
        warehouses=warehouses,
        expires_at=invite.expires_at,
        created_at=invite.created_at
    )
