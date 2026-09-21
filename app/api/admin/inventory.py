from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.admin.auth import WRITE
from app.api.admin.schemas import BulkStockPayload, StockItemPayload
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/inventory")
async def list_inventory(
    services: ServicesDep,
    product_id: Optional[int] = Query(None, gt=0),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    items, total, summary = await services.inventory.items(product_id=product_id, status=status, limit=limit, offset=offset)
    return {"items": items, "total": total, "summary": summary}


@router.post("/inventory/bulk", dependencies=WRITE)
async def bulk_add_stock(payload: BulkStockPayload, services: ServicesDep, background: BackgroundTasks):
    result = await services.inventory.add_stock(
        payload.product_id, payload.items_text.splitlines(), payload.max_uses, payload.expires_at
    )
    if result["added"]:
        background.add_task(services.announcements.restock, payload.product_id, result["added"] * payload.max_uses)
    return {"success": True, "added_count": result["added"], "skipped_count": result["skipped"]}


@router.put("/inventory/{item_id}", dependencies=WRITE)
async def edit_inventory_item(item_id: int, payload: StockItemPayload, services: ServicesDep):
    return {
        "success": True,
        "item": await services.inventory.update_item(
            item_id, payload.content, payload.max_uses, payload.expires_at
        ),
    }


@router.delete("/inventory/{item_id}", dependencies=WRITE)
async def delete_inventory_item(item_id: int, services: ServicesDep):
    return {"success": await services.inventory.remove_available(item_id)}
