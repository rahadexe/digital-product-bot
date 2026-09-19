"""Admin console API under /api/admin. Everything except login and session requires an admin session."""

from fastapi import APIRouter, Depends

from app.api.admin import (
    broadcast,
    catalog,
    channels,
    deposits,
    emojis,
    inventory,
    orders,
    overview,
    payments,
    session,
    settings,
    supplier,
    users,
)
from app.api.admin.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(session.router)

protected = APIRouter(dependencies=[Depends(require_admin)])
for module in (overview, catalog, inventory, orders, deposits, payments, users, channels, broadcast, settings, supplier, emojis):
    protected.include_router(module.router)
router.include_router(protected)
