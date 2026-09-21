from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import ServicesDep
from app.db.migrations import MIGRATIONS_DIR

EXPECTED_MIGRATIONS = frozenset(path.stem for path in MIGRATIONS_DIR.glob('*.sql'))

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live():
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(services: ServicesDep):
    try:
        async with services.db.connect() as conn:
            applied = {row['version'] for row in await conn.fetch('SELECT version FROM schema_migrations')}
            if not EXPECTED_MIGRATIONS.issubset(applied):
                return JSONResponse(status_code=503, content={'status':'migration_required','database':True})
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": False})
    runtime = services.runtime
    is_ready = runtime.bot in ("webhook", "polling", "disabled") and runtime.components_alive()
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "starting", "database": True, "bot": runtime.bot},
    )
