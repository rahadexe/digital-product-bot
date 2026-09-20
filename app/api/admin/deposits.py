from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from app.api.admin.auth import WRITE
from app.api.admin.schemas import DepositMethodPayload, DepositReviewPayload
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/deposits")
async def list_deposits(
    services: ServicesDep,
    status: Optional[Literal["pending", "approved", "rejected"]] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    deposits, total, summary = await services.deposits.list(status=status, limit=limit, offset=offset)
    return {"deposits": deposits, "total": total, "summary": summary}


@router.post("/deposits/{deposit_id}/approve", dependencies=WRITE)
async def approve_deposit(deposit_id: int, payload: DepositReviewPayload, services: ServicesDep):
    success, message, _ = await services.deposits.approve(deposit_id, payload.admin_note)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/deposits/{deposit_id}/reject", dependencies=WRITE)
async def reject_deposit(deposit_id: int, payload: DepositReviewPayload, services: ServicesDep):
    success, message, _ = await services.deposits.reject(deposit_id, payload.admin_note or "Transaction could not be verified.")
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.get("/deposit-methods")
async def list_deposit_methods(services: ServicesDep):
    return await services.deposits.methods(active_only=False)


@router.post("/deposit-methods", dependencies=WRITE)
async def create_deposit_method(payload: DepositMethodPayload, services: ServicesDep):
    method_id = await services.deposits.create_method(
        name=payload.name,
        account_info=payload.account_info,
        instructions=payload.instructions,
        min_deposit=payload.min_deposit,
        rate=payload.rate_to_currency,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        custom_emoji_id=payload.custom_emoji_id,
        account_type=payload.account_type,
    )
    return {"success": True, "id": method_id}


@router.put("/deposit-methods/{method_id}", dependencies=WRITE)
async def update_deposit_method(method_id: int, payload: DepositMethodPayload, services: ServicesDep):
    if not await services.deposits.update_method(method_id, **payload.model_dump()):
        raise HTTPException(status_code=404, detail="Method not found.")
    return {"success": True}


@router.delete("/deposit-methods/{method_id}", dependencies=WRITE)
async def delete_deposit_method(method_id: int, services: ServicesDep):
    if not await services.deposits.delete_method(method_id):
        raise HTTPException(status_code=404, detail="Method not found.")
    return {"success": True}
