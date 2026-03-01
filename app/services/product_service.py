"""Product service — logical product creation + inward completion."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.enums import MovementType
from app.models.inventory_ledger import InventoryLedger
from app.models.product import CATEGORY_PREFIX, Product, ProductCategory, StorageUnit
from app.models.rack import Rack
from app.models.rack_allocation import RackAllocation
from app.models.room import Room
from app.models.temperature_zone import TemperatureZone
from app.models.user import User
from app.models.warehouse import Warehouse
from app.rbac.context_resolver import DataScope
from app.services import audit_service, invitation_service
from app.services.audit_serializer import to_audit_dict


def _warehouse_code(warehouse: Warehouse) -> str:
    code = "".join(ch for ch in warehouse.name if ch.isalnum())[:4].upper()
    return code or "WH00"


async def _next_sequence(
    category: ProductCategory,
    warehouse_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    stmt = (
        select(func.count())
        .select_from(Product)
        .where(
            Product.category == category,
            Product.warehouse_id == warehouse_id,
            Product.created_at >= today_start,
        )
    )
    result = await db.execute(stmt)
    return (result.scalar() or 0) + 1


async def _generate_sku(
    category: ProductCategory,
    warehouse: Warehouse,
    db: AsyncSession,
) -> str:
    prefix = CATEGORY_PREFIX[category]
    wh_code = _warehouse_code(warehouse)
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = await _next_sequence(category, warehouse.id, db)
    return f"{prefix}-{wh_code}-{date_part}-{seq:04d}"


def _parse_category(category: str) -> ProductCategory:
    try:
        return ProductCategory(category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category '{category}'. Must be one of: {[c.value for c in ProductCategory]}",
        )


def _parse_unit(unit: str) -> StorageUnit:
    try:
        return StorageUnit(unit)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid unit '{unit}'. Must be one of: {[u.value for u in StorageUnit]}",
        )


async def create_product(
    *,
    name: str,
    description: str | None,
    category: str,
    unit: str,
    temperature_requirement: float | None,
    warehouse_id: uuid.UUID,
    created_by: uuid.UUID,
    db: AsyncSession,
) -> Product:
    """Create logical product only (no rack/quantity/lot/inward)."""
    cat = _parse_category(category)
    storage_unit = _parse_unit(unit)

    wh_result = await db.execute(select(Warehouse).where(Warehouse.id == warehouse_id))
    warehouse = wh_result.scalar_one_or_none()
    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found",
        )

    sku_code = await _generate_sku(cat, warehouse, db)
    product = Product(
        id=uuid.uuid4(),
        name=name,
        description=description,
        category=cat,
        unit=storage_unit,
        temperature_requirement=temperature_requirement,
        sku_code=sku_code,
        warehouse_id=warehouse_id,
        created_by=created_by,
    )
    db.add(product)
    await db.flush()

    await audit_service.log(
        db,
        entity_type="Product",
        entity_id=product.id,
        action="CREATE",
        performed_by=created_by,
        old_data=None,
        new_data=to_audit_dict(product),
        reason="Logical product created (pre-inward)",
    )

    return product


async def _load_client_for_email(email: str, db: AsyncSession) -> tuple[User | None, Client | None]:
    user_result = await db.execute(select(User).where(User.email == email))
    existing_user = user_result.scalar_one_or_none()
    if existing_user is None:
        return None, None

    role_names = {r.name for r in existing_user.roles}
    if "CLIENT" not in role_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{email}' exists but does not have CLIENT role",
        )

    client_result = await db.execute(select(Client).where(Client.user_id == existing_user.id))
    client = client_result.scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has CLIENT role but no client profile",
        )
    return existing_user, client


async def _bind_client_for_inward(
    *,
    product: Product,
    email: str,
    operator_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[bool, bool]:
    email_norm = email.strip().lower()
    current_email = (product.client_email or "").strip().lower()

    if product.client_id is not None:
        user, client = await _load_client_for_email(email_norm, db)
        if user is None or client is None or client.id != product.client_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Client mismatch: product already linked to a different client",
            )
        if current_email and current_email != email_norm:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Client email mismatch with immutable product owner",
            )
        if not product.client_email:
            product.client_email = email_norm
            await db.flush()
        return True, False

    if current_email and current_email != email_norm:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Client mismatch: product has a different pending client email",
        )

    user, client = await _load_client_for_email(email_norm, db)
    if user is not None and client is not None:
        old_data = {"client_id": str(product.client_id) if product.client_id else None}
        product.client_id = client.id
        product.client_email = email_norm
        await db.flush()
        await audit_service.log(
            db,
            entity_type="Product",
            entity_id=product.id,
            action="UPDATE",
            performed_by=operator_id,
            old_data=old_data,
            new_data={"client_id": str(client.id), "client_email": email_norm},
            reason="Client linked during inward",
        )
        return True, False

    invitation = await invitation_service.create_invitation(
        email=email_norm,
        role_assigned="CLIENT",
        invited_by=operator_id,
        db=db,
    )
    old_email = product.client_email
    product.client_email = email_norm
    await db.flush()
    await audit_service.log(
        db,
        entity_type="Product",
        entity_id=product.id,
        action="UPDATE",
        performed_by=operator_id,
        old_data={"client_email": old_email},
        new_data={"client_email": email_norm, "invitation_id": str(invitation.id)},
        reason="Client invitation created during inward",
    )
    return False, True


async def inward_product(
    *,
    product_id: uuid.UUID,
    client_email: str,
    rack_id: uuid.UUID,
    quantity: float,
    lot_number: str,
    operator_id: uuid.UUID,
    scope: DataScope,
    db: AsyncSession,
) -> dict[str, Any]:
    """Complete inward for a logical product in one atomic service call."""
    prod_result = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if not scope.is_admin:
        if scope.warehouse_id and product.warehouse_id != scope.warehouse_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this product")

    inward_exists_stmt = select(InventoryLedger.id).where(
        InventoryLedger.sku_id == product.id,
        InventoryLedger.movement_type == MovementType.INWARD,
    )
    inward_exists = (await db.execute(inward_exists_stmt)).scalar_one_or_none()
    if inward_exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product already has an inward entry",
        )

    lot_exists_stmt = select(InventoryLedger.id).where(InventoryLedger.lot_number == lot_number)
    lot_exists = (await db.execute(lot_exists_stmt)).scalar_one_or_none()
    if lot_exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lot number already exists",
        )

    rack_result = await db.execute(select(Rack).where(Rack.id == rack_id))
    rack = rack_result.scalar_one_or_none()
    if rack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rack not found")

    room_result = await db.execute(select(Room).where(Room.id == rack.room_id))
    room = room_result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    if room.warehouse_id != product.warehouse_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room does not belong to product warehouse",
        )
    if rack.is_occupied:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rack '{rack.label}' is already occupied",
        )

    if product.temperature_requirement is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product temperature requirement is required for inward",
        )

    zone_result = await db.execute(
        select(TemperatureZone).where(TemperatureZone.id == room.temperature_zone_id)
    )
    zone = zone_result.scalar_one_or_none()
    if zone is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room temperature zone is missing",
        )

    required_temp = Decimal(str(product.temperature_requirement))
    if required_temp < zone.min_temp or required_temp > zone.max_temp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Temperature mismatch: product requires {product.temperature_requirement}°C "
                f"but room zone '{zone.zone_name}' allows {zone.min_temp}°C to {zone.max_temp}°C"
            ),
        )

    if Decimal(str(quantity)) > rack.capacity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quantity {quantity} exceeds rack '{rack.label}' capacity of {rack.capacity}",
        )

    client_linked, invitation_sent = await _bind_client_for_inward(
        product=product,
        email=client_email,
        operator_id=operator_id,
        db=db,
    )

    now = datetime.now(timezone.utc)
    allocation = RackAllocation(
        id=uuid.uuid4(),
        rack_id=rack_id,
        sku_id=product.id,
        allocated_by=operator_id,
        allocated_at=now,
        released_at=None,
    )
    db.add(allocation)
    rack.is_occupied = True
    await db.flush()

    ledger_entry = InventoryLedger(
        id=uuid.uuid4(),
        sku_id=product.id,
        warehouse_id=product.warehouse_id,
        movement_type=MovementType.INWARD,
        lot_number=lot_number,
        quantity_delta=Decimal(str(quantity)),
        reference_type="RackAllocation",
        reference_id=allocation.id,
        performed_by=operator_id,
        reason=f"Inward to rack '{rack.label}'",
    )
    db.add(ledger_entry)
    await db.flush()

    await audit_service.log(
        db,
        entity_type="RackAllocation",
        entity_id=allocation.id,
        action="ALLOCATE",
        performed_by=operator_id,
        old_data=None,
        new_data=to_audit_dict(allocation),
        reason=f"Allocated SKU {product.sku_code} to rack '{rack.label}'",
    )
    await audit_service.log(
        db,
        entity_type="InventoryLedger",
        entity_id=ledger_entry.id,
        action="CREATE",
        performed_by=operator_id,
        old_data=None,
        new_data=to_audit_dict(ledger_entry),
    )
    await audit_service.log(
        db,
        entity_type="Inward",
        entity_id=ledger_entry.id,
        action="CREATE",
        performed_by=operator_id,
        old_data=None,
        new_data={
            "product_id": str(product.id),
            "warehouse_id": str(product.warehouse_id),
            "room_id": str(room.id),
            "rack_id": str(rack.id),
            "temperature_zone_id": str(zone.id),
            "lot_number": lot_number,
            "quantity": quantity,
            "unit": product.unit.value,
            "client_id": str(product.client_id) if product.client_id else None,
            "client_email": product.client_email,
        },
        reason="Inward completed",
    )

    return {
        "detail": "Inward completed successfully",
        "product_id": product.id,
        "ledger_id": ledger_entry.id,
        "rack_allocation_id": allocation.id,
        "client_linked": client_linked,
        "invitation_sent": invitation_sent,
    }


async def delete_product_if_uninwarded(
    *,
    product_id: uuid.UUID,
    performed_by: uuid.UUID,
    scope: DataScope,
    db: AsyncSession,
    reason: str,
) -> bool:
    prod_result = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_result.scalar_one_or_none()
    if product is None:
        return False

    if not scope.is_admin and scope.warehouse_id and product.warehouse_id != scope.warehouse_id:
        return False

    inward_stmt = select(InventoryLedger.id).where(
        InventoryLedger.sku_id == product.id,
        InventoryLedger.movement_type == MovementType.INWARD,
    )
    has_inward = (await db.execute(inward_stmt)).scalar_one_or_none() is not None
    if has_inward:
        return False

    allocation_stmt = select(RackAllocation.id).where(RackAllocation.sku_id == product.id)
    has_allocation = (await db.execute(allocation_stmt)).scalar_one_or_none() is not None
    if has_allocation:
        return False

    await audit_service.log(
        db,
        entity_type="Product",
        entity_id=product.id,
        action="DELETE",
        performed_by=performed_by,
        old_data=to_audit_dict(product),
        new_data=None,
        reason=reason,
    )
    await db.execute(delete(Product).where(Product.id == product.id))
    await db.flush()
    return True


async def inward_product_with_cleanup(
    *,
    product_id: uuid.UUID,
    client_email: str,
    rack_id: uuid.UUID,
    quantity: float,
    lot_number: str,
    operator_id: uuid.UUID,
    scope: DataScope,
    db: AsyncSession,
) -> dict[str, Any]:
    """Run inward; on failure delete uninwarded product and return error payload."""
    savepoint = await db.begin_nested()
    try:
        result = await inward_product(
            product_id=product_id,
            client_email=client_email,
            rack_id=rack_id,
            quantity=quantity,
            lot_number=lot_number,
            operator_id=operator_id,
            scope=scope,
            db=db,
        )
        await savepoint.commit()
        return {"success": True, **result}
    except HTTPException as exc:
        await savepoint.rollback()
        await delete_product_if_uninwarded(
            product_id=product_id,
            performed_by=operator_id,
            scope=scope,
            db=db,
            reason=f"Auto-delete draft after inward failure: {exc.detail}",
        )
        return {
            "success": False,
            "status_code": exc.status_code,
            "detail": exc.detail,
        }
    except Exception:
        await savepoint.rollback()
        await delete_product_if_uninwarded(
            product_id=product_id,
            performed_by=operator_id,
            scope=scope,
            db=db,
            reason="Auto-delete draft after inward failure (unexpected error)",
        )
        return {
            "success": False,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "detail": "Failed to complete inward",
        }


async def link_client_to_product(
    *,
    product_id: uuid.UUID,
    email: str,
    operator_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Legacy helper retained for compatibility; delegates to inward client binding rules."""
    prod_result = await db.execute(select(Product).where(Product.id == product_id))
    product = prod_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    client_linked, invitation_sent = await _bind_client_for_inward(
        product=product,
        email=email,
        operator_id=operator_id,
        db=db,
    )
    return {
        "detail": "Client linked" if client_linked else f"Invitation sent to '{email}'",
        "client_linked": client_linked,
        "invitation_sent": invitation_sent,
        "product_id": product.id,
        "client_email": email,
    }


# ── Back-fill helper (called from auth_service on invitation accept) ─

async def backfill_client_on_products(
    client_id: uuid.UUID,
    client_email: str,
    performed_by: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    After a CLIENT accepts their invitation, find all products
    tagged with their email and set client_id.

    Returns the number of products updated.
    """
    stmt = select(Product).where(
        Product.client_email == client_email,
        Product.client_id.is_(None),
    )
    result = await db.execute(stmt)
    products = list(result.scalars().all())

    for product in products:
        product.client_id = client_id
        await audit_service.log(
            db,
            entity_type="Product",
            entity_id=product.id,
            action="UPDATE",
            performed_by=performed_by,
            old_data={"client_id": None},
            new_data={"client_id": str(client_id)},
            reason=f"Client back-filled after invitation acceptance ({client_email})",
        )

    if products:
        await db.flush()

    return len(products)


# ── Listing ──────────────────────────────────────────────────────────

async def list_products(
    db: AsyncSession,
    scope: DataScope,
    skip: int = 0,
    limit: int = 50,
) -> list[Product]:
    """List products scoped by the caller's role."""
    stmt = select(Product)

    if scope.is_admin:
        pass  # no filter
    elif scope.warehouse_id:
        stmt = stmt.where(Product.warehouse_id == scope.warehouse_id)
    elif scope.client_id:
        stmt = stmt.where(Product.client_id == scope.client_id)
    else:
        return []

    stmt = stmt.order_by(Product.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_product_by_id(
    product_id: uuid.UUID,
    db: AsyncSession,
    scope: DataScope,
) -> Product:
    """Get a single product — enforcing data scope."""
    stmt = select(Product).where(Product.id == product_id)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Scope check
    if not scope.is_admin:
        if scope.warehouse_id and product.warehouse_id != scope.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this product",
            )
        if scope.client_id and product.client_id != scope.client_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this product",
            )

    return product
