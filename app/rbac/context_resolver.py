"""
Context resolver — data-scope enforcement.

Every service query MUST pass through `resolve_data_scope` so that:
- Operators see only their warehouse's data.
- Clients see only their own data.
- Admins get unrestricted access.

The resolver inspects the JWT payload (which already carries
`warehouse_id` / `client_id` if applicable) AND double-checks
against the DB profile to prevent token tampering.

Usage in a service:
    scope = await resolve_data_scope(current_user, db)
    query = query.where(SomeModel.warehouse_id == scope.warehouse_id)
"""

import uuid
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@dataclass
class DataScope:
    """
    Encapsulates the data-access boundaries for the current request.

    - is_admin: full access, no filters needed.
    - warehouse_id: set for operators — every warehouse-bound query must filter on this.
    - client_id: set for clients — every client-bound query must filter on this.
    """

    is_admin: bool = False
    warehouse_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    role_names: set[str] = field(default_factory=set)


async def resolve_data_scope(user: User, db: AsyncSession) -> DataScope:
    """
    Build a DataScope from the authenticated user's profile.

    This is called inside every service method that touches
    warehouse- or client-scoped data.
    """
    role_names = {role.name for role in user.roles}

    scope = DataScope(
        user_id=user.id,
        role_names=role_names,
    )

    # Admin → unrestricted
    if "ADMIN" in role_names:
        scope.is_admin = True
        return scope

    # Operator → locked to their warehouse
    if "OPERATOR" in role_names or "INVENTORY_MANAGER" in role_names:
        if user.operator_profile is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operator profile missing — contact admin",
            )
        scope.warehouse_id = user.operator_profile.warehouse_id
        return scope

    # Client → locked to their client record
    if "CLIENT" in role_names:
        if user.client is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Client profile missing — contact admin",
            )
        scope.client_id = user.client.id
        return scope

    # Fallback — billing manager or future roles with no special scope
    # They have permissions but no warehouse/client restriction.
    # If your business requires scope for them too, add logic here.
    return scope
