"""
Rack service — CRUD for racks inside rooms, plus query helpers.

Racks are the smallest allocatable storage unit.  Each rack can hold
one SKU at a time (exclusive).  The ``is_occupied`` flag is maintained
by the product service during allocation / release.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rack import Rack
from app.models.rack_allocation import RackAllocation
from app.models.room import Room
from app.rbac.context_resolver import DataScope
from app.services import audit_service
from app.services.audit_serializer import to_audit_dict


async def create_rack(
    *,
    label: str,
    room_id: uuid.UUID,
    capacity: float,
    temperature: float | None,
    created_by: uuid.UUID,
    db: AsyncSession,
) -> Rack:
    """
    Create a rack inside a room.

    Validates that the room exists before inserting.
    """
    room_result = await db.execute(
        select(Room).where(Room.id == room_id)
    )
    room = room_result.scalar_one_or_none()
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    rack = Rack(
        id=uuid.uuid4(),
        label=label,
        room_id=room_id,
        capacity=capacity,
        temperature=temperature,
        is_occupied=False,
    )
    db.add(rack)
    await db.flush()

    await audit_service.log(
        db,
        entity_type="Rack",
        entity_id=rack.id,
        action="CREATE",
        performed_by=created_by,
        old_data=None,
        new_data=to_audit_dict(rack),
    )

    return rack


async def list_racks(
    db: AsyncSession,
    scope: DataScope,
    room_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Rack]:
    """List racks scoped by caller's role, optionally filtered by room."""
    stmt = select(Rack).join(Room, Rack.room_id == Room.id)

    if room_id is not None:
        stmt = stmt.where(Rack.room_id == room_id)

    if scope.is_admin:
        pass
    elif scope.warehouse_id:
        stmt = stmt.where(Room.warehouse_id == scope.warehouse_id)
    else:
        return []

    stmt = stmt.order_by(Rack.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_rack_by_id(
    rack_id: uuid.UUID,
    db: AsyncSession,
    scope: DataScope,
) -> Rack:
    """Get a single rack, enforcing data scope."""
    stmt = select(Rack).where(Rack.id == rack_id)
    result = await db.execute(stmt)
    rack = result.scalar_one_or_none()

    if rack is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rack not found",
        )

    # Scope check via room → warehouse
    if not scope.is_admin:
        room_result = await db.execute(
            select(Room).where(Room.id == rack.room_id)
        )
        room = room_result.scalar_one_or_none()
        if room and scope.warehouse_id and room.warehouse_id != scope.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this rack",
            )

    return rack


async def list_available_racks(
    db: AsyncSession,
    warehouse_id: uuid.UUID,
    temperature: float | None = None,
) -> list[Rack]:
    """
    Return empty (unoccupied) racks in the given warehouse, optionally
    filtered by matching temperature.

    Useful for operators to pick a rack during inward.
    """
    stmt = (
        select(Rack)
        .join(Room, Rack.room_id == Room.id)
        .where(
            Room.warehouse_id == warehouse_id,
            Rack.is_occupied.is_(False),
        )
    )

    if temperature is not None:
        stmt = stmt.where(Rack.temperature == temperature)

    stmt = stmt.order_by(Rack.label)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_allocation_for_rack(
    rack_id: uuid.UUID,
    db: AsyncSession,
) -> RackAllocation | None:
    """Return the active (unreleased) allocation on a rack, if any."""
    stmt = select(RackAllocation).where(
        RackAllocation.rack_id == rack_id,
        RackAllocation.released_at.is_(None),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
