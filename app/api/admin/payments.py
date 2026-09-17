from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Path, Query

from app.api.admin.auth import WRITE
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/payments/binance/status")
async def binance_status(services: ServicesDep):
    return await services.binance.status()


@router.post("/payments/binance/test", dependencies=WRITE)
async def test_binance(services: ServicesDep):
    return await services.binance.test_connection()


@router.post("/deposits/{deposit_id}/check", dependencies=WRITE)
async def check_deposit_on_binance(deposit_id: int, services: ServicesDep):
    return await services.binance.check(deposit_id)


@router.post("/payments/binance/check-pending", dependencies=WRITE)
async def recheck_binance_deposits(services: ServicesDep):
    return {"checked": await services.binance.recheck_pending()}


@router.get("/payments/status")
async def payments_status(services: ServicesDep):
    return await services.payments.status()


@router.post("/payments/test-invoice", dependencies=WRITE)
async def test_payment_page(services: ServicesDep):
    return await services.payments.test_invoice()


@router.post("/payments/test", dependencies=WRITE)
async def test_payments(services: ServicesDep):
    return await services.payments.test_connection()


@router.post("/payments/check-pending", dependencies=WRITE)
async def check_pending_payments(services: ServicesDep):
    return {"checked": await services.payments.recheck_pending()}


@router.get("/payments")
async def list_payments(
    services: ServicesDep,
    status: Optional[Literal["created", "pending", "completed", "failed", "expired"]] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    invoices, total = await services.payments.list(status=status, limit=limit, offset=offset)
    return {"invoices": invoices, "total": total}


@router.post("/payments/{reference}/check", dependencies=WRITE)
async def check_payment(services: ServicesDep, reference: str = Path(..., pattern=r"^SM[0-9A-F]{16}$")):
    invoice = await services.payments.refresh(reference)
    if invoice is None:
        raise HTTPException(404, "Payment not found.")
    return {"success": True, "status": invoice["status"]}
