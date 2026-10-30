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
    search: Optional[str] = Query(None),
):
    deposits, total, summary = await services.deposits.list(status=status, limit=limit, offset=offset, search=search)
    return {"deposits": deposits, "total": total, "summary": summary}


@router.post("/deposits/{deposit_id}/approve", dependencies=WRITE)
async def approve_deposit(deposit_id: int, payload: DepositReviewPayload, services: ServicesDep):
    success, message, _ = await services.deposits.approve(deposit_id, payload.admin_note)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/deposits/{deposit_id}/reject", dependencies=WRITE)
async def reject_deposit(deposit_id: int, payload: DepositReviewPayload, services: ServicesDep):
    success, message, _ = await services.deposits.reject(deposit_id, payload.admin_note or "Verification Failed")
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.get("/deposit-methods")
async def list_deposit_methods(services: ServicesDep):
    all_methods = await services.deposits.methods(active_only=False)
    for m in all_methods:
        is_binance = (
            m.get("auto_verify") == "binance_pay"
            or m.get("account_type") == "crypto"
            or "binance" in m.get("name", "").lower()
        )
        if is_binance:
            m["account_type"] = "crypto"
    return all_methods


@router.post("/deposit-methods", dependencies=WRITE)
async def create_deposit_method(payload: DepositMethodPayload, services: ServicesDep):
    name = (payload.name or "").strip()
    is_binance = payload.account_type == "crypto" or "binance" in name.lower()
    auto_verify = payload.auto_verify
    account_type = "crypto" if is_binance else payload.account_type
    custom_emoji = payload.custom_emoji_id

    api_key = (payload.api_key or "").strip()
    api_secret = (payload.api_secret or "").strip()

    if bool(api_key) != bool(api_secret):
        raise HTTPException(status_code=422, detail="Both Binance API Key and Secret are required.")

    if (api_key or api_secret) and not is_binance:
        raise HTTPException(status_code=422, detail="Binance credentials only apply to Binance methods.")

    if is_binance:
        name = name or "Binance"
        custom_emoji = custom_emoji or None
        if api_key and api_secret:
            services.binance_credentials.validate_encryption_key()
            auto_verify = "binance_pay"
        else:
            auto_verify = "none"

    method_id = await services.deposits.create_method(
        name=name,
        account_info=payload.account_info.strip(),
        instructions=payload.instructions.strip(),
        min_deposit=payload.min_deposit,
        rate=payload.rate_to_currency,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        auto_verify=auto_verify,
        auto_verify_network="Binance ID" if is_binance else payload.auto_verify_network,
        custom_emoji_id=custom_emoji,
        account_type=account_type,
    )

    if is_binance and api_key and api_secret:
        await services.binance_credentials.save(method_id, api_key, api_secret)

    return {"success": True, "id": method_id}


@router.put("/deposit-methods/{method_id}", dependencies=WRITE)
async def update_deposit_method(method_id: int, payload: DepositMethodPayload, services: ServicesDep):
    name = (payload.name or "").strip()
    is_binance = payload.account_type == "crypto" or "binance" in name.lower()
    api_key = (payload.api_key or "").strip()
    api_secret = (payload.api_secret or "").strip()

    if bool(api_key) != bool(api_secret):
        raise HTTPException(status_code=422, detail="Both Binance API Key and Secret are required.")

    if (api_key or api_secret) and not is_binance:
        raise HTTPException(status_code=422, detail="Binance credentials only apply to Binance methods.")

    existing = await services.deposits.get_method(method_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Method not found.")

    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("api_key", None)
    update_data.pop("api_secret", None)
    clear_creds = update_data.pop("clear_api_credentials", False)

    if is_binance:
        update_data["name"] = name or "Binance"
        update_data["account_type"] = "crypto"
        update_data["auto_verify_network"] = "Binance ID"
        if clear_creds:
            await services.binance_credentials.delete(method_id)
            update_data["auto_verify"] = "none"
        elif api_key and api_secret:
            services.binance_credentials.validate_encryption_key()
            await services.binance_credentials.save(method_id, api_key, api_secret)
            update_data["auto_verify"] = "binance_pay"
        else:
            if existing.get("has_api_credentials"):
                update_data["auto_verify"] = "binance_pay"
            else:
                update_data["auto_verify"] = "none"

    if not await services.deposits.update_method(method_id, **update_data):
        raise HTTPException(status_code=404, detail="Method not found.")
    return {"success": True}


@router.post("/deposit-methods/{method_id}/toggle", dependencies=WRITE)
async def toggle_deposit_method(method_id: int, services: ServicesDep):
    all_methods = await services.deposits.methods(active_only=False)
    target = next((m for m in all_methods if m["id"] == method_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Method not found.")
    new_active = 0 if target["is_active"] == 1 else 1
    await services.deposits.update_method(method_id, is_active=new_active)
    return {"success": True, "is_active": new_active}


@router.delete("/deposit-methods/{method_id}", dependencies=WRITE)
async def delete_deposit_method(method_id: int, services: ServicesDep):
    if not await services.deposits.delete_method(method_id):
        raise HTTPException(status_code=404, detail="Method not found.")
    return {"success": True}
