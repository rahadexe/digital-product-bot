from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.admin.auth import WRITE
from app.api.admin.schemas import GateChannelPayload, UpdateChannelPayload
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/gate-channels")
async def list_gate_channels(services: ServicesDep):
    return await services.gate.channels(active_only=False)


@router.post("/gate-channels", dependencies=WRITE)
async def add_gate_channel(payload: GateChannelPayload, services: ServicesDep):
    channel_id = await services.gate.add(**payload.model_dump())
    return {"success": True, "id": channel_id}


@router.put("/gate-channels/{channel_id}", dependencies=WRITE)
async def update_gate_channel(channel_id: int, payload: GateChannelPayload, services: ServicesDep):
    if not await services.gate.update(channel_id, **payload.model_dump()):
        raise HTTPException(status_code=404, detail="Gate channel not found.")
    return {"success": True}


@router.delete("/gate-channels/{channel_id}", dependencies=WRITE)
async def remove_gate_channel(channel_id: int, services: ServicesDep):
    await services.gate.remove(channel_id)
    return {"success": True}


@router.get("/update-channels")
async def list_update_channels(services: ServicesDep):
    return await services.update_channels.channels(active_only=False)


@router.post("/update-channels", dependencies=WRITE)
async def add_update_channel(payload: UpdateChannelPayload, services: ServicesDep):
    channel_id = await services.update_channels.add(**payload.model_dump())
    return {"success": True, "id": channel_id}


@router.put("/update-channels/{channel_id}", dependencies=WRITE)
async def update_update_channel(channel_id: int, payload: UpdateChannelPayload, services: ServicesDep):
    if not await services.update_channels.update(channel_id, **payload.model_dump()):
        raise HTTPException(status_code=404, detail="Channel not found.")
    return {"success": True}


@router.delete("/update-channels/{channel_id}", dependencies=WRITE)
async def remove_update_channel(channel_id: int, services: ServicesDep):
    await services.update_channels.remove(channel_id)
    return {"success": True}
