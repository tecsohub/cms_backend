"""
Room service — CRUD for rooms inside warehouses.

Rooms represent physical sections within a warehouse, each potentially
having a temperature zone. Only admins can create rooms.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import Room
from app.models.warehouse import Warehouse
from app.rbac.context_resolver import DataScope
from app.services import audit_service
from app.services.audit_serializer import to_audit_dict


async def create_room(
    *,
    name: str,
    warehouse_id: uuid.UUID,
    temperature_zone: float | None,
    created_by: uuid.UUID,
    db: AsyncSession,
) -> Room:
    """
    Create a room in a warehouse.

    Validates that the warehouse exists before inserting.
    """
    # Verify warehouse exists
    wh_result = await db.execute(
        select(Warehouse).where(Warehouse.id == warehouse_id)
    )
    warehouse = wh_result.scalar_one_or_none()
    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        )

    room = Room(
        id=uuid.uuid4(),
        name=name,
        warehouse_id=warehouse_id,
        temperature_zone=temperature_zone,
    )
    db.add(room)
    await db.flush()

    await audit_service.log(
        db,
        entity_type="Room",
        entity_id=room.id,
        action="CREATE",
        performed_by=created_by,
        old_data=None,
        new_data=to_audit_dict(room),
    )

    return room


async def list_rooms(
    db: AsyncSession,
    scope: DataScope,
    warehouse_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Room]:
    """List rooms, scoped by caller's role."""
    stmt = select(Room)

    # If a specific warehouse is requested, filter by it
    if warehouse_id is not None:
        stmt = stmt.where(Room.warehouse_id == warehouse_id)

    # Apply data scope
    if scope.is_admin:
        pass  # no extra filter
    elif scope.warehouse_id:
        stmt = stmt.where(Room.warehouse_id == scope.warehouse_id)
    else:
        return []

    stmt = stmt.order_by(Room.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_room_by_id(
    room_id: uuid.UUID,
    db: AsyncSession,
    scope: DataScope,
) -> Room:
    """Get a single room, enforcing data scope."""
    stmt = select(Room).where(Room.id == room_id)
    result = await db.execute(stmt)
    room = result.scalar_one_or_none()

    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    if not scope.is_admin:
        if scope.warehouse_id and room.warehouse_id != scope.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this room",
            )

    return room
