from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import ServicesDep

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(services: ServicesDep):
    try:
        async with services.db.connect() as conn:
            await conn.fetchval("SELECT COUNT(*) FROM schema_migrations")
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": False})
    runtime = services.runtime
    is_ready = runtime.bot in ("webhook", "disabled") and runtime.components_alive()
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "starting", "database": True, "bot": runtime.bot},
    )
