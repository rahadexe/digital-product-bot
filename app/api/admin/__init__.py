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
    reseller_applications,
    session,
    settings,
    suppliers,
    users,
)
from app.api.admin.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(session.router)

protected = APIRouter(dependencies=[Depends(require_admin)])
for module in (overview, catalog, inventory, orders, deposits, payments, users, reseller_applications, channels, broadcast, settings, emojis, suppliers):
    protected.include_router(module.router)

router.include_router(protected)
