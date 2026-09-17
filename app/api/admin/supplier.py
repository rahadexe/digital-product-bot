from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.api.admin.auth import WRITE
from app.api.admin.schemas import SupplierAttemptReview, SupplierItemPricePayload, SupplierSyncPayload
from app.api.deps import ServicesDep

router = APIRouter(prefix="/supplier")


@router.get("/status")
async def supplier_status(services: ServicesDep):
    return await services.supplier.status()


@router.get("/products")
async def supplier_products(services: ServicesDep):
    return await services.supplier.catalog()


@router.put("/products/{supplier_product_id}/price", dependencies=WRITE)
async def set_supplier_product_price(supplier_product_id: int, payload: SupplierItemPricePayload, services: ServicesDep):
    await services.supplier.set_retail_price(supplier_product_id, payload.price)
    return {"success": True, "supplier_product_id": supplier_product_id, "new_price": payload.price}


@router.post("/sync", dependencies=WRITE)
async def sync_supplier_products(services: ServicesDep, payload: SupplierSyncPayload = Body(default_factory=SupplierSyncPayload)):
    return await services.supplier.sync(payload.markup_percent, payload.fixed_markup, payload.overwrite_prices)


@router.get("/purchase-attempts")
async def supplier_purchase_attempts(services: ServicesDep):
    return await services.supplier.unresolved_attempts()


@router.post("/purchase-attempts/{attempt_id}/release", dependencies=WRITE)
async def release_supplier_attempt(attempt_id: int, payload: SupplierAttemptReview, services: ServicesDep):
    if not payload.verified_no_charge:
        raise HTTPException(
            422, "Verify with the supplier that no order was fulfilled and no charge was made before releasing a retry."
        )
    await services.supplier.release_attempt(attempt_id, payload.reason)
    return {"success": True}
