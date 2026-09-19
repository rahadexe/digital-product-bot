from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.admin.auth import WRITE
from app.api.admin.schemas import BalanceAdjustPayload, BanPayload, UserRankPayload
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/users")
async def list_users(
    services: ServicesDep,
    search: str = Query("", max_length=100),
    filter: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    users, total, summary = await services.users.list(search=search, filter_type=filter, limit=limit, offset=offset)
    return {"users": users, "total": total, "summary": summary}


@router.get("/users/{tg_user_id}")
async def get_user(tg_user_id: int, services: ServicesDep):
    user = await services.users.get(tg_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user": user}


@router.post("/users/{tg_user_id}/adjust-balance", dependencies=WRITE)
async def adjust_balance(tg_user_id: int, payload: BalanceAdjustPayload, services: ServicesDep):
    user = await services.users.adjust_balance(tg_user_id, payload.delta, payload.reason, notify=True)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"success": True, "user": user}


@router.post("/users/{tg_user_id}/ban", dependencies=WRITE)
async def set_ban(tg_user_id: int, services: ServicesDep, payload: Optional[BanPayload] = None):
    banned = await services.users.set_banned(tg_user_id, payload.banned if payload else None)
    return {"success": True, "is_banned": banned}


@router.post("/users/{tg_user_id}/rank", dependencies=WRITE)
async def set_user_rank(tg_user_id: int, payload: UserRankPayload, services: ServicesDep):
    rank = await services.users.set_rank(tg_user_id, payload.rank)
    return {"success": True, "rank": rank}
