from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.api.admin.auth import WRITE
from app.api.admin.schemas import ManualDeliveryPayload
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/orders")
async def list_orders(
    services: ServicesDep,
    search: str = Query("", max_length=100),
    waiting: bool = Query(False),
    customer: int | None = Query(None, gt=0),
    days: int | None = Query(None, ge=1),
    date_from: str | None = Query(None, max_length=30),
    date_to: str | None = Query(None, max_length=30),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    orders, total, summary = await services.purchases.all_orders(
        search=search,
        limit=limit,
        offset=offset,
        waiting_only=waiting,
        tg_user_id=customer,
        days=days,
        date_from=date_from,
        date_to=date_to,
    )
    return {
        "orders": orders,
        "total": total,
        "waiting": await services.purchases.waiting_count(),
        "summary": summary,
    }


@router.get("/orders/{order_id}")
async def order_detail(order_id: int, services: ServicesDep):
    return await services.purchases.order_detail(order_id)


@router.post("/orders/{order_id}/deliver", dependencies=WRITE)
async def deliver_by_hand(order_id: int, payload: ManualDeliveryPayload, services: ServicesDep):
    await services.purchases.fulfill_manually(order_id, payload.content)
    return {"success": True}




@router.post("/orders/{order_id}/refund", dependencies=WRITE)
async def refund_order(order_id: int, services: ServicesDep):
    success, message = await services.purchases.refund(order_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/orders/{order_id}/retry-delivery", dependencies=WRITE)
async def retry_delivery(order_id: int, services: ServicesDep):
    await services.delivery.retry_order(order_id)
    return {"success": True}


@router.post("/orders/{order_id}/retry-supplier", dependencies=WRITE)
async def retry_supplier_fulfillment(order_id: int, services: ServicesDep):
    success, message, data = await services.purchases.retry_supplier_fulfillment(order_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message, "order": data}
