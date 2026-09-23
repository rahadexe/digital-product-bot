from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.admin.auth import WRITE
from app.api.deps import ServicesDep
from app.services.audit import record

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




@router.get('/failed-jobs')
async def failed_jobs(services: ServicesDep):
    async with services.db.connect() as conn:
        rows = await conn.fetch("SELECT 'telegram' AS kind,update_id AS id,attempts,error FROM telegram_inbox WHERE status='failed' UNION ALL SELECT 'notification',id,attempts,error FROM admin_notification_jobs WHERE status='failed' ORDER BY id DESC LIMIT 100")
    return [dict(row) for row in rows]

@router.post('/failed-jobs/{kind}/{job_id}/retry', dependencies=WRITE)
async def retry_job(kind: Literal['telegram','notification'], job_id: int, services: ServicesDep):
    table, column = ('telegram_inbox','update_id') if kind == 'telegram' else ('admin_notification_jobs','id')
    async with services.db.transaction() as conn:
        changed = await conn.fetchval(f"UPDATE {table} SET status='pending',attempts=0,error='',next_attempt=now(),lease_token=NULL WHERE {column}=$1 AND status='failed' RETURNING {column}",job_id)
        if changed is None:
            raise HTTPException(409, 'This job is no longer failed.')
        await record(conn, 'job_retry', f'{kind} job #{job_id}')
    return {'success': True}
