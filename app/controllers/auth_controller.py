"""
Auth controller — login & invitation acceptance.

These routes are PUBLIC (no permission dependency) because the user
hasn't authenticated yet.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas import (
    AcceptInvitationRequest,
    LoginRequest,
    TokenResponse,
    UserOut,
)
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password → receive JWT."""
    return await auth_service.authenticate_user(body.email, body.password, db)


@router.post("/accept-invitation", response_model=UserOut)
async def accept_invitation(
    body: AcceptInvitationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Accept a pending invitation, set password, activate account."""
    user = await auth_service.accept_invitation(
        token=body.token,
        password=body.password,
        full_name=body.full_name,
        db=db,
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
