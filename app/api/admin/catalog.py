from __future__ import annotations

import re
from typing import Optional

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.admin.auth import WRITE
from app.api.admin.schemas import CategoryPayload, ProductPayload, ProductUpdatePayload
from app.api.deps import ServicesDep
from app.services import Services

router = APIRouter()


async def _validate_custom_emoji(services: Services, emoji_id: str | None) -> None:
    value = (emoji_id or "").strip()
    if not value:
        return
    if not re.fullmatch(r"\d{1,64}", value):
        raise HTTPException(status_code=422, detail="Telegram custom emoji ID must contain only digits.")
    bot = services.notifier.bot
    if bot is None:
        raise HTTPException(
            status_code=503,
            detail="Telegram is unavailable, so this custom emoji ID cannot be verified right now.",
        )
    try:
        stickers = await bot.get_custom_emoji_stickers([value])
    except TelegramBadRequest as exc:
        raise HTTPException(status_code=422, detail="Telegram rejected this custom emoji ID.") from exc
    except TelegramAPIError as exc:
        raise HTTPException(
            status_code=503,
            detail="Telegram could not verify this custom emoji ID. Please try again.",
        ) from exc
    if not any(sticker.custom_emoji_id == value for sticker in stickers):
        raise HTTPException(status_code=422, detail="Telegram did not find a custom emoji with this ID.")


class BulkProductsPayload(BaseModel):
    action: str = Field(..., pattern="^(activate|hide|delete)$")
    product_ids: list[int] = Field(..., min_length=1, max_length=500)



@router.get("/categories")
async def list_categories(services: ServicesDep):
    return await services.catalog.categories(active_only=False)


@router.post("/categories", dependencies=WRITE)
async def create_category(payload: CategoryPayload, services: ServicesDep):
    await _validate_custom_emoji(services, payload.custom_emoji_id)
    category_id = await services.catalog.create_category(**payload.model_dump())
    return {"success": True, "id": category_id}



@router.put("/categories/{category_id}", dependencies=WRITE)
async def update_category(category_id: int, payload: CategoryPayload, services: ServicesDep):
    await _validate_custom_emoji(services, payload.custom_emoji_id)
    if not await services.catalog.update_category(category_id, **payload.model_dump()):
        raise HTTPException(status_code=404, detail="Category not found.")
    return {"success": True}


@router.delete("/categories/{category_id}", dependencies=WRITE)
async def delete_category(category_id: int, services: ServicesDep):
    await services.catalog.delete_category(category_id)
    return {"success": True}


@router.get("/products")
async def list_products(services: ServicesDep, category_id: Optional[int] = Query(None)):
    return await services.catalog.products(category_id=category_id, active_only=False, limit=500)


@router.post("/products", dependencies=WRITE)
async def create_product(payload: ProductPayload, services: ServicesDep):
    await _validate_custom_emoji(services, payload.custom_emoji_id)
    product_id = await services.catalog.create_product(**payload.model_dump())
    return {"success": True, "id": product_id}


@router.put("/products/{product_id}", dependencies=WRITE)
async def update_product(product_id: int, payload: ProductUpdatePayload, services: ServicesDep, background: BackgroundTasks):
    data = payload.model_dump(exclude_unset=True)
    if "custom_emoji_id" in data:
        await _validate_custom_emoji(services, data["custom_emoji_id"])
    old_price = await services.catalog.update_product(product_id, **data)
    if old_price is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    if "price" in data and data["price"] is not None and data["price"] != old_price:
        background.add_task(services.announcements.price_change, product_id, old_price, data["price"])
    return {"success": True}


@router.delete("/products/{product_id}", dependencies=WRITE)
async def delete_product(product_id: int, services: ServicesDep):
    await services.catalog.delete_product(product_id)
    return {"success": True}


@router.post("/products/{product_id}/pin", dependencies=WRITE)
async def toggle_product_pinned(product_id: int, services: ServicesDep):
    prod = await services.catalog.product(product_id)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found.")
    next_pinned = 0 if prod.get("is_pinned") else 1
    await services.catalog.update_product(product_id, is_pinned=next_pinned)
    return {"success": True, "is_pinned": next_pinned}


@router.post("/products/bulk", dependencies=WRITE)
async def bulk_products_action(payload: BulkProductsPayload, services: ServicesDep):
    if payload.action == "activate":
        count = await services.catalog.bulk_update_status(payload.product_ids, 1)
        return {"success": True, "count": count, "message": f"{count} product(s) activated successfully."}
    elif payload.action == "hide":
        count = await services.catalog.bulk_update_status(payload.product_ids, 0)
        return {"success": True, "count": count, "message": f"{count} product(s) hidden successfully."}
    elif payload.action == "delete":
        count = await services.catalog.bulk_delete_products(payload.product_ids)
        return {"success": True, "count": count, "message": f"{count} product(s) deleted successfully."}
    raise HTTPException(status_code=400, detail="Unsupported bulk action.")



@router.post("/products/{product_id}/announce", dependencies=WRITE)
async def announce_product(product_id: int, services: ServicesDep):
    if not await services.announcements.promote(product_id):
        raise HTTPException(
            status_code=400,
            detail="Could not send announcement. Check channel username or admin configuration in Settings.",
        )
    return {"success": True}
