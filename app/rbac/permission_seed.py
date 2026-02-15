"""
Permission & Role seeding script.

Run this once against a live database to populate the default
permissions and roles.  It is IDEMPOTENT — safe to re-run.

Governance rule enforced here:
    • OPERATOR / INVENTORY_MANAGER get inventory.* but NEVER billing.invoice.approve
    • BILLING_MANAGER gets billing.* but NEVER inventory mutation permissions
    • Only ADMIN holds every permission

Usage:
    python -m app.rbac.permission_seed
"""

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.base import Base
from app.models.permission import Permission
from app.models.role import Role

# ────────────────────────────────────────────────────────────────────
# 1.  CANONICAL PERMISSION LIST
# ────────────────────────────────────────────────────────────────────
PERMISSIONS: list[dict[str, str]] = [
    # Inventory
    {"code": "inventory.inward.create", "description": "Create inward inventory entries"},
    {"code": "inventory.zone.allocate", "description": "Allocate inventory to a zone"},
    {"code": "inventory.move.internal", "description": "Move inventory between zones"},
    {"code": "inventory.dispatch.execute", "description": "Execute dispatch of inventory"},
    {"code": "inventory.view", "description": "View inventory data"},
    # Billing
    {"code": "billing.invoice.create", "description": "Create invoices"},
    {"code": "billing.invoice.approve", "description": "Approve invoices (governance-separated)"},
    {"code": "invoice.view", "description": "View invoices"},
    # User management
    {"code": "user.invite.operator", "description": "Invite an operator"},
    {"code": "user.invite.client", "description": "Invite a client"},
    # Warehouse
    {"code": "warehouse.create", "description": "Create a warehouse"},
    {"code": "warehouse.update", "description": "Update warehouse details"},
]

# ────────────────────────────────────────────────────────────────────
# 2.  ROLE → PERMISSION MAPPING
#
#     Governance: inventory mutation and billing approval are
#     NEVER combined in the same non-admin role.
# ────────────────────────────────────────────────────────────────────
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "ADMIN": [p["code"] for p in PERMISSIONS],  # full access
    "OPERATOR": [
        "inventory.inward.create",
        "inventory.zone.allocate",
        "inventory.move.internal",
        "inventory.dispatch.execute",
        "inventory.view",
    ],
    "INVENTORY_MANAGER": [
        "inventory.inward.create",
        "inventory.zone.allocate",
        "inventory.move.internal",
        "inventory.dispatch.execute",
        "inventory.view",
        # NOTE: No billing.invoice.approve here — governance rule
    ],
    "BILLING_MANAGER": [
        "billing.invoice.create",
        "billing.invoice.approve",
        "invoice.view",
        # NOTE: No inventory mutation permissions — governance rule
    ],
    "CLIENT": [
        "inventory.view",
        "invoice.view",
    ],
}


# ────────────────────────────────────────────────────────────────────
# 3.  SEED FUNCTION (idempotent)
# ────────────────────────────────────────────────────────────────────
async def seed(session: AsyncSession) -> None:
    """Create permissions & roles if they don't already exist."""

    # ── Permissions ──────────────────────────────────────────────────
    existing_perms = (await session.execute(select(Permission))).scalars().all()
    existing_codes = {p.code for p in existing_perms}
    code_to_perm: dict[str, Permission] = {p.code: p for p in existing_perms}

    for pdata in PERMISSIONS:
        if pdata["code"] not in existing_codes:
            perm = Permission(id=uuid.uuid4(), **pdata)
            session.add(perm)
            code_to_perm[pdata["code"]] = perm

    await session.flush()  # ensure IDs are available

    # ── Roles ────────────────────────────────────────────────────────
    existing_roles = (await session.execute(select(Role))).scalars().all()
    existing_role_names = {r.name for r in existing_roles}

    for role_name, perm_codes in ROLE_PERMISSIONS.items():
        if role_name in existing_role_names:
            continue
        role = Role(
            id=uuid.uuid4(),
            name=role_name,
            description=f"Default {role_name} role",
        )
        for code in perm_codes:
            perm_obj = code_to_perm.get(code)
            if perm_obj:
                role.permissions.append(perm_obj)
        session.add(role)

    await session.commit()
    print("✔  Permissions and roles seeded successfully.")


# ────────────────────────────────────────────────────────────────────
# 4.  CLI entrypoint:  python -m app.rbac.permission_seed
# ────────────────────────────────────────────────────────────────────
async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
