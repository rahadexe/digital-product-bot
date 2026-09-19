from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.admin.auth import WRITE
from app.api.admin.schemas import BroadcastPayload
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/broadcast")
async def broadcast_info(services: ServicesDep):
    count = await services.delivery.recipient_count()
    recent = await services.delivery.recent_broadcasts()
    return {"recipient_count": count, "recent": recent}


@router.post("/broadcast", dependencies=WRITE)
async def broadcast_message(payload: BroadcastPayload, services: ServicesDep):
    if not services.notifier.bot:
        raise HTTPException(503, "Telegram bot is not configured.")
    return await services.delivery.enqueue_broadcast(payload.text)


@router.get("/broadcast/{job_id}")
async def broadcast_progress(job_id: int, services: ServicesDep):
    return await services.delivery.broadcast_status(job_id)
