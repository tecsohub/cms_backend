"""
Product service — handles product intake, SKU generation, and client linking.

Flow:
1. Operator enters product details → `create_product` generates the SKU
   and inserts the product row.
2. Operator enters client email → `link_client_to_product`:
   a) If a user with CLIENT role exists → links immediately.
   b) If no user found → creates an invitation with role_assigned="CLIENT"
      using the existing InvitationService.

When the client later accepts the invitation, `auth_service.accept_invitation`
calls `backfill_client_on_products` to set `client_id` on every product
that was tagged with that email.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.product import CATEGORY_PREFIX, Product, ProductCategory, StorageUnit
from app.models.user import User
from app.models.warehouse import Warehouse
from app.rbac.context_resolver import DataScope
from app.services import audit_service
from app.services.audit_serializer import to_audit_dict
from app.services import invitation_service


# ── SKU generation ───────────────────────────────────────────────────

def _warehouse_code(warehouse: Warehouse) -> str:
    """
    Derive a short warehouse code from the name.
    Takes first 4 alpha-numeric chars, uppercased.
    e.g. "Cold Hub 1" → "COLD"
    """
    code = "".join(ch for ch in warehouse.name if ch.isalnum())[:4].upper()
    return code or "WH00"


async def _next_sequence(
    category: ProductCategory,
    warehouse_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """
    Get the next daily sequence number for SKU generation.
    Counts how many products of the same category were created today
    in this warehouse and returns count + 1.
    """
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
    count = result.scalar() or 0
    return count + 1


async def _generate_sku(
    category: ProductCategory,
    warehouse: Warehouse,
    db: AsyncSession,
) -> str:
    """
    Generate SKU in the format:
        {CATEGORY_PREFIX}-{WAREHOUSE_CODE}-{YYYYMMDD}-{SEQ:04d}
    e.g.  FRZ-COLD-20260223-0001
    """
    prefix = CATEGORY_PREFIX[category]
    wh_code = _warehouse_code(warehouse)
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = await _next_sequence(category, warehouse.id, db)
    return f"{prefix}-{wh_code}-{date_part}-{seq:04d}"


# ── Product creation ─────────────────────────────────────────────────

async def create_product(
    *,
    name: str,
    description: str | None,
    category: str,
    unit: str,
    quantity: float,
    lot_number: str,
    temperature_requirement: float | None,
    warehouse_id: uuid.UUID,
    created_by: uuid.UUID,
    db: AsyncSession,
) -> Product:
    """
    Create a product record and auto-generate the SKU code.

    Called by the operator controller after permission + scope checks.
    """
    # Validate enums
    try:
        cat = ProductCategory(category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category '{category}'. "
                   f"Must be one of: {[c.value for c in ProductCategory]}",
        )
    try:
        storage_unit = StorageUnit(unit)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid unit '{unit}'. "
                   f"Must be one of: {[u.value for u in StorageUnit]}",
        )

    # Load warehouse for SKU code
    wh_result = await db.execute(
        select(Warehouse).where(Warehouse.id == warehouse_id)
    )
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
        quantity=quantity,
        lot_number=lot_number,
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
    )

    return product


# ── Client linking / invitation ──────────────────────────────────────

async def link_client_to_product(
    *,
    product_id: uuid.UUID,
    email: str,
    operator_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Link a client to a product by email.

    - If a user with CLIENT role exists → set product.client_id immediately.
    - If no user found → send a CLIENT invitation via the existing
      InvitationService (same `invitations` table, role = "CLIENT").

    Returns a dict describing the outcome.
    """
    # Load the product
    prod_result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = prod_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Store the email on the product regardless of outcome
    product.client_email = email
    await db.flush()

    # Check if a user with this email exists
    user_result = await db.execute(
        select(User).where(User.email == email)
    )
    existing_user = user_result.scalar_one_or_none()

    if existing_user is not None:
        # Check if they have a CLIENT role
        role_names = {r.name for r in existing_user.roles}
        if "CLIENT" not in role_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email '{email}' exists but does not have "
                       f"the CLIENT role (current roles: {role_names})",
            )

        # Find client profile
        client_result = await db.execute(
            select(Client).where(Client.user_id == existing_user.id)
        )
        client = client_result.scalar_one_or_none()
        if client is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User has CLIENT role but no client profile — contact admin",
            )

        product.client_id = client.id
        await db.flush()

        await audit_service.log(
            db,
            entity_type="Product",
            entity_id=product.id,
            action="UPDATE",
            performed_by=operator_id,
            old_data={"client_id": None},
            new_data={"client_id": str(client.id)},
            reason=f"Client linked via email '{email}'",
        )

        return {
            "detail": f"Client '{existing_user.full_name}' linked to product",
            "client_linked": True,
            "invitation_sent": False,
            "product_id": product.id,
            "client_email": email,
        }

    # No user found → create a CLIENT invitation
    invitation = await invitation_service.create_invitation(
        email=email,
        role_assigned="CLIENT",
        invited_by=operator_id,
        db=db,
    )

    await audit_service.log(
        db,
        entity_type="Product",
        entity_id=product.id,
        action="UPDATE",
        performed_by=operator_id,
        old_data=None,
        new_data={"client_email": email, "invitation_id": str(invitation.id)},
        reason=f"Client invitation sent to '{email}'",
    )

    return {
        "detail": f"Invitation sent to '{email}' with CLIENT role",
        "client_linked": False,
        "invitation_sent": True,
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
