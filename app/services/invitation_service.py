"""
Invitation service.

Handles the creation and management of user invitations.
Only users with the appropriate `user.invite.*` permissions can
create invitations (enforced at the controller layer via RBAC).
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation, InvitationStatus
from app.models.user import User
from app.services.email_service import send_invitation_email


def _generate_invite_token() -> str:
    """Cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(48)


async def create_invitation(
    email: str,
    role_assigned: str,
    invited_by: uuid.UUID,
    db: AsyncSession,
    expires_in_hours: int = 72,
) -> Invitation:
    """
    Create a new invitation.

    Business rules enforced:
    - Cannot invite an email that already has an ACTIVE user account.
    - Cannot create duplicate PENDING invitations for the same email.
    """
    # Check for existing active user
    existing_user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    if existing_user and existing_user.status.value == "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    # Check for pending invitation
    pending = (
        await db.execute(
            select(Invitation).where(
                Invitation.email == email,
                Invitation.status == InvitationStatus.PENDING,
            )
        )
    ).scalar_one_or_none()

    if pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation already exists for this email",
        )

    invitation = Invitation(
        id=uuid.uuid4(),
        email=email,
        invited_by=invited_by,
        role_assigned=role_assigned,
        token=_generate_invite_token(),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
        status=InvitationStatus.PENDING,
    )
    db.add(invitation)
    await db.flush()

    # Send invitation email
    await send_invitation_email(
        to_email=email,
        invitation_token=invitation.token,
        role_assigned=role_assigned,
    )

    return invitation


async def list_invitations(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[Invitation]:
    """List all invitations (admin only — enforced at controller)."""
    stmt = select(Invitation).order_by(Invitation.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_invitation_by_token(token: str, db: AsyncSession) -> Invitation:
    stmt = select(Invitation).where(Invitation.token == token)
    result = await db.execute(stmt)
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )
    return invite
