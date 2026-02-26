# Copilot Instructions — CMS Backend

## Architecture Overview

This is a **cold-storage warehouse management system** backend built with FastAPI + async SQLAlchemy + PostgreSQL. It follows a strict **Controller → Service → Model** layered architecture:

- **Controllers** (`app/controllers/`) are thin — validate input via Pydantic schemas, call a service, return a schema. No business logic here.
- **Services** (`app/services/`) hold all business logic. They receive an `AsyncSession` from the controller and **must not commit** — the `get_db` dependency auto-commits/rollbacks.
- **Models** (`app/models/`) use SQLAlchemy 2.0 `Mapped[]` style. Every model inherits `Base`, `UUIDPrimaryKeyMixin`, and `TimestampMixin` from `app/models/base.py`.

## RBAC & Data Scoping (Critical Path)

Every protected route uses a two-layer enforcement pattern:

1. **Permission check** — `Depends(require_permission("inventory.inward.create"))` in the route signature. This is a callable class in `app/rbac/dependencies.py` that decodes the JWT, loads User→Roles→Permissions, and returns the `User` object.
2. **Data scope** — inside the service, call `resolve_data_scope(user, db)` from `app/rbac/context_resolver.py`. It returns a `DataScope` dataclass with `is_admin`, `warehouse_id`, or `client_id`. **Every warehouse/client-bound query must filter on scope**.

Roles follow a **governance separation rule** defined in `app/rbac/permission_seed.py`: operators never get billing approval, billing managers never get inventory mutation. Only ADMIN has all permissions.

## Authentication — Hybrid Stateful JWT

JWTs are validated against a **server-side session registry** on every request (`get_current_user_token` in `app/core/security.py`). The token carries `user_id`, `session_id`, `device_id`, and contextual IDs (`warehouse_id`/`client_id`). Session inactivity timeout and device-binding are enforced server-side. Operators are limited to one active device at a time.

## Key Conventions

- **Database sessions**: Never call `db.commit()` in services — `get_db()` handles commit/rollback. Services call `db.flush()` when they need IDs before commit.
- **Schemas**: All Pydantic schemas live in `app/schemas.py` (single file). They use `model_config = {"from_attributes": True}` for ORM compatibility.
- **Audit logging**: Every mutation must call `audit_service.log(db, ...)` in the same transaction. Use `to_audit_dict(entity)` from `app/services/audit_serializer.py` for JSONB snapshots — it auto-excludes secrets (`password_hash`, `token`).
- **Append-only tables**: `AuditLog` and `InventoryLedger` are immutable — no UPDATE/DELETE. Inventory quantity is derived via `SUM(quantity_delta)`.
- **Enums**: Shared enums (`MovementType`, `AuditAction`) live in `app/models/enums.py` to avoid circular imports.
- **Model registration**: All models must be imported in `app/models/__init__.py` so Alembic sees them.

## Database & Migrations

- **Alembic manages all schema changes** — never use `Base.metadata.create_all` in production.
- Migration files are in `alembic/versions/`. The async engine uses `asyncpg`; Alembic env.py overrides the URL to use it directly.
- Generate migrations: `alembic revision --autogenerate -m "description"`
- Apply migrations: `alembic upgrade head`

## Developer Commands

```bash
# Run the dev server
uv run uvicorn main:app --reload

# Seed permissions and roles (idempotent)
uv run python -m app.rbac.permission_seed

# Create the first admin user (one-time bootstrap)
uv run python -m app.scripts.create_admin

# Run tests (uses in-memory SQLite, no Postgres needed)
uv run pytest

# Generate a new Alembic migration
uv run alembic revision --autogenerate -m "description"
```

## Testing Patterns

Tests use **in-memory SQLite with aiosqlite** (`tests/audit/conftest.py`). Each test runs inside a SAVEPOINT that auto-rollbacks. Seed helpers (`seed_user`, `seed_warehouse`) create minimal fixtures. JSONB columns fall back to plain JSON on SQLite. Mark all async tests with `@pytest.mark.asyncio`.

## Adding a New Feature Checklist

1. **Model**: Create in `app/models/`, inherit `Base + UUIDPrimaryKeyMixin + TimestampMixin`, add import to `app/models/__init__.py`.
2. **Migration**: `alembic revision --autogenerate -m "add_feature_table"`.
3. **Schema**: Add Pydantic request/response classes to `app/schemas.py`.
4. **Service**: Create in `app/services/`, accept `AsyncSession`, use `resolve_data_scope` for scoped queries, call `audit_service.log` for mutations.
5. **Controller**: Add routes in `app/controllers/`, use `Depends(require_permission(...))`, keep logic minimal.
6. **Permissions**: If new permissions are needed, add to `PERMISSIONS` list and `ROLE_PERMISSIONS` map in `app/rbac/permission_seed.py`, then re-run the seed.
