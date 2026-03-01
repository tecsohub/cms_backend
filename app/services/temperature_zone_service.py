"""Temperature zone service — global CRUD."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.room import Room
from app.models.temperature_zone import TemperatureZone
from app.services import audit_service
from app.services.audit_serializer import to_audit_dict


def _validate_range(min_temp: float, max_temp: float) -> tuple[Decimal, Decimal]:
    min_dec = Decimal(str(min_temp))
    max_dec = Decimal(str(max_temp))
    if min_dec > max_dec:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_temp cannot be greater than max_temp",
        )
    return min_dec, max_dec


async def create_temperature_zone(
    *,
    zone_name: str,
    min_temp: float,
    max_temp: float,
    created_by: uuid.UUID,
    db: AsyncSession,
) -> TemperatureZone:
    min_dec, max_dec = _validate_range(min_temp, max_temp)
    trimmed = zone_name.strip()

    existing = (
        await db.execute(
            select(TemperatureZone).where(TemperatureZone.zone_name == trimmed)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Temperature zone name already exists",
        )

    zone = TemperatureZone(
        id=uuid.uuid4(),
        zone_name=trimmed,
        min_temp=min_dec,
        max_temp=max_dec,
    )
    db.add(zone)
    await db.flush()

    await audit_service.log(
        db,
        entity_type="TemperatureZone",
        entity_id=zone.id,
        action="CREATE",
        performed_by=created_by,
        old_data=None,
        new_data=to_audit_dict(zone),
    )
    return zone


async def list_temperature_zones(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 50,
) -> list[TemperatureZone]:
    stmt = select(TemperatureZone).order_by(TemperatureZone.zone_name.asc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_temperature_zone_by_id(
    zone_id: uuid.UUID,
    db: AsyncSession,
) -> TemperatureZone:
    zone = (
        await db.execute(select(TemperatureZone).where(TemperatureZone.id == zone_id))
    ).scalar_one_or_none()
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Temperature zone not found")
    return zone


async def update_temperature_zone(
    *,
    zone_id: uuid.UUID,
    zone_name: str | None,
    min_temp: float | None,
    max_temp: float | None,
    updated_by: uuid.UUID,
    db: AsyncSession,
) -> TemperatureZone:
    zone = await get_temperature_zone_by_id(zone_id, db)
    old_data = to_audit_dict(zone)

    if zone_name is not None:
        trimmed = zone_name.strip()
        existing = (
            await db.execute(
                select(TemperatureZone).where(
                    TemperatureZone.zone_name == trimmed,
                    TemperatureZone.id != zone_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Temperature zone name already exists",
            )
        zone.zone_name = trimmed

    next_min = float(zone.min_temp) if min_temp is None else min_temp
    next_max = float(zone.max_temp) if max_temp is None else max_temp
    min_dec, max_dec = _validate_range(next_min, next_max)
    zone.min_temp = min_dec
    zone.max_temp = max_dec

    await db.flush()

    await audit_service.log(
        db,
        entity_type="TemperatureZone",
        entity_id=zone.id,
        action="UPDATE",
        performed_by=updated_by,
        old_data=old_data,
        new_data=to_audit_dict(zone),
    )
    return zone


async def delete_temperature_zone(
    *,
    zone_id: uuid.UUID,
    deleted_by: uuid.UUID,
    db: AsyncSession,
) -> None:
    zone = await get_temperature_zone_by_id(zone_id, db)

    linked_room = (
        await db.execute(select(Room.id).where(Room.temperature_zone_id == zone.id).limit(1))
    ).scalar_one_or_none()
    if linked_room is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Temperature zone is used by one or more rooms",
        )

    old_data = to_audit_dict(zone)
    await db.delete(zone)
    await db.flush()

    await audit_service.log(
        db,
        entity_type="TemperatureZone",
        entity_id=zone.id,
        action="DELETE",
        performed_by=deleted_by,
        old_data=old_data,
        new_data=None,
    )
