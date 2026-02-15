"""
Convenience decorators (optional syntactic sugar on top of dependencies).

These are thin wrappers that make route declarations more readable.

Example:
    @router.get("/warehouses")
    @permission_required("warehouse.create")
    async def create_warehouse(...): ...

NOTE: In FastAPI, using `Depends(require_permission(...))` is the
idiomatic pattern.  These decorators are provided for teams that prefer
the decorator style — both approaches resolve to the same underlying
check.
"""

import functools
from typing import Any, Callable

from fastapi import Depends

from app.rbac.dependencies import require_permission


def permission_required(*codes: str) -> Callable:
    """
    Decorator that adds a permission dependency to a route handler.

    Usage:
        @router.post("/items")
        @permission_required("inventory.inward.create")
        async def create_item(user = Depends(require_permission("inventory.inward.create")), ...):
            ...

    For dependency-injection style (recommended in FastAPI), simply
    use `Depends(require_permission("code"))` directly in the route
    signature instead.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # The actual enforcement happens via the dependency injection
            # system.  This wrapper is a no-op — the magic is in the
            # `dependencies` list appended below.
            return await func(*args, **kwargs)

        # Append the permission dependency so FastAPI picks it up
        if not hasattr(wrapper, "__dependencies__"):
            wrapper.__dependencies__ = []
        wrapper.__dependencies__.append(Depends(require_permission(*codes)))
        return wrapper

    return decorator
