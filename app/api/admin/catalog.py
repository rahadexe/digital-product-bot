from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.api.admin.auth import WRITE
from app.api.admin.schemas import CategoryPayload, ProductPayload, ProductUpdatePayload
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/categories")
async def list_categories(services: ServicesDep):
    return await services.catalog.categories(active_only=False)


@router.post("/categories", dependencies=WRITE)
async def create_category(payload: CategoryPayload, services: ServicesDep):
    category_id = await services.catalog.create_category(**payload.model_dump())
    return {"success": True, "id": category_id}



@router.put("/categories/{category_id}", dependencies=WRITE)
async def update_category(category_id: int, payload: CategoryPayload, services: ServicesDep):
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
    product_id = await services.catalog.create_product(**payload.model_dump())
    return {"success": True, "id": product_id}


@router.put("/products/{product_id}", dependencies=WRITE)
async def update_product(product_id: int, payload: ProductUpdatePayload, services: ServicesDep, background: BackgroundTasks):
    data = payload.model_dump(exclude_unset=True)
    old_price = await services.catalog.update_product(product_id, **data)
    if old_price is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    if "price" in data and data["price"] is not None and data["price"] < old_price:
        background.add_task(services.announcements.price_drop, product_id, old_price, data["price"])
    return {"success": True}


@router.delete("/products/{product_id}", dependencies=WRITE)
async def archive_product(product_id: int, services: ServicesDep):
    await services.catalog.archive_product(product_id)
    return {"success": True}


@router.post("/products/{product_id}/announce", dependencies=WRITE)
async def announce_product(product_id: int, services: ServicesDep):
    if not await services.announcements.promote(product_id):
        raise HTTPException(
            status_code=400,
            detail="Could not send announcement. Check channel username in Settings and verify bot is Admin there.",
        )
    return {"success": True}
