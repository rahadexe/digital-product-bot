from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/overview")
async def overview(services: ServicesDep):
    return await services.dashboard.stats()


@router.get("/audit-logs")
async def audit_logs(
    services: ServicesDep,
    search: str = Query("", max_length=100),
    action: str = Query("", max_length=64),
    security: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    return await services.audit.search(search=search, action=action, security_only=security, limit=limit, offset=offset)
