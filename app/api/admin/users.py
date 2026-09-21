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
    # users.get() returns the customer row itself. It was read as though it were
    # the {"user": ..., "order_count": ...} shape that users.stats() returns, so
    # every field fell out and the profile came back empty.
    stats = await services.users.stats(tg_user_id)
    if not stats:
        raise HTTPException(status_code=404, detail="User not found.")
    user_data = dict(stats["user"])
    user_data["order_count"] = stats["order_count"]
    user_data["total_spent"] = stats["total_spent"]

    reseller_key = await services.reseller.get_latest_key(tg_user_id)
    reseller_stats = await services.reseller.get_reseller_stats(tg_user_id)
    return {
        "user": user_data,
        "reseller_key": reseller_key,
        "reseller_stats": reseller_stats,
    }


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


@router.post("/users/{tg_user_id}/reseller-key/toggle", dependencies=WRITE)
async def toggle_reseller_key(tg_user_id: int, services: ServicesDep):
    key = await services.reseller.get_latest_key(tg_user_id)
    if not key:
        raise HTTPException(status_code=404, detail="No API key found for this user.")
    new_active = not bool(key.get("is_active"))
    await services.reseller.set_key_status_admin(tg_user_id, new_active)
    updated_key = await services.reseller.get_latest_key(tg_user_id)
    return {"success": True, "reseller_key": updated_key}


@router.post("/users/{tg_user_id}/reseller-key/generate", dependencies=WRITE)
async def generate_reseller_key(tg_user_id: int, services: ServicesDep):
    user = await services.users.get(tg_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    # Minting a key only works for a reseller, so this grants the rank. That is a
    # pricing change as well as an access one, so it is reported back rather than
    # done quietly.
    upgraded = (user.get("rank") or "").strip().lower() != "reseller"
    if upgraded:
        await services.users.set_rank(tg_user_id, "Reseller")
    raw_key, record = await services.reseller.generate_key(tg_user_id, name="Admin Key")
    return {"success": True, "raw_key": raw_key, "reseller_key": record, "rank_upgraded": upgraded}
