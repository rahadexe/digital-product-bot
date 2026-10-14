from __future__ import annotations

import asyncio

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.admin.auth import WRITE
from app.api.deps import ServicesDep

router = APIRouter(prefix="/suppliers")


class SupplierConfigPayload(BaseModel):
    supplier_code: str = Field(default="digital_mart", max_length=64)
    base_url: str = Field(default="https://dmb.bmdigital.bd/api/v1/reseller", max_length=255)
    api_key: str = Field(default="", max_length=255)
    markup_percent: float | None = Field(default=None, ge=0, le=500)
    auto_sync: int | None = Field(default=None, ge=0, le=1)
    low_balance_alert: float | None = Field(default=None, ge=0, le=100000)


class ImportSupplierProductsPayload(BaseModel):
    supplier_code: str = Field(default="digital_mart", max_length=64)
    product_ids: list[int] = Field(..., min_length=1, max_length=500)
    activate: bool = Field(default=False)
    target_category_id: int | None = Field(default=None)



@router.get("/status")
async def get_supplier_status(services: ServicesDep):
    dm_sup = services.suppliers.get("digital_mart") if services.suppliers else services.upstream_reseller
    st_sup = services.suppliers.get("safwan_tiger") if services.suppliers else None

    async def balance(client):
        return await client.get_balance() if client else None

    dm_bal, st_bal = await asyncio.gather(balance(dm_sup), balance(st_sup))

    async with services.db.connect() as conn:
        counts = {
            r["supplier_code"] or "digital_mart": r["c"]
            for r in await conn.fetch(
                "SELECT COALESCE(supplier_code, 'digital_mart') AS supplier_code, COUNT(*) AS c "
                "FROM products WHERE upstream_product_id IS NOT NULL GROUP BY supplier_code"
            )
        }
        total_products = await conn.fetchval("SELECT COUNT(*) FROM products")
        upstream_orders = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE source IN ('upstream_reseller', 'supplier_pending')"
        )

    dm_markup = float(await services.settings.get("upstream_markup_percent") or 15.0)
    dm_auto_sync = int(await services.settings.get("upstream_auto_sync") or 1)
    dm_low_alert = float(await services.settings.get("upstream_low_balance_alert") or 50.0)

    st_markup = float(await services.settings.get("safwan_tiger_markup_percent") or 15.0)
    st_auto_sync = int(await services.settings.get("safwan_tiger_auto_sync") or 0)
    st_low_alert = float(await services.settings.get("safwan_tiger_low_balance_alert") or 5.0)

    def mask(k: str) -> str:
        return f"{k[:8]}...{k[-4:]}" if len(k) > 12 else ("****" if k else "")

    providers = [
        {
            "code": "digital_mart",
            "name": "Digital Mart",
            "currency": "BDT",
            "currency_symbol": "৳",
            "is_configured": bool(dm_sup and dm_sup.is_configured),
            "base_url": getattr(dm_sup, "base_url", ""),
            "api_key_masked": mask(getattr(dm_sup, "api_key", "")),
            "balance": dm_bal.get("balance", 0.0) if dm_bal else 0.0,
            "connected": bool(dm_bal and dm_bal.get("ok")),
            "markup_percent": dm_markup,
            "auto_sync": dm_auto_sync,
            "low_balance_alert": dm_low_alert,
            "products_count": counts.get("digital_mart", 0),
        },
        {
            "code": "safwan_tiger",
            "name": "Safwan Tiger Shop",
            "currency": "USDT",
            "currency_symbol": "$",
            "is_configured": bool(st_sup and st_sup.is_configured),
            "base_url": getattr(st_sup, "base_url", ""),
            "api_key_masked": mask(getattr(st_sup, "api_key", "")),
            "balance": st_bal.get("balance", 0.0) if st_bal else 0.0,
            "connected": bool(st_bal and st_bal.get("ok")),
            "markup_percent": st_markup,
            "auto_sync": st_auto_sync,
            "low_balance_alert": st_low_alert,
            "products_count": counts.get("safwan_tiger", 0),
        },
    ]

    total_upstream_count = sum(counts.values())

    return {
        "providers": providers,
        # Legacy fields for backward compatibility
        "is_configured": bool(dm_sup and dm_sup.is_configured),
        "base_url": getattr(dm_sup, "base_url", ""),
        "api_key_masked": mask(getattr(dm_sup, "api_key", "")),
        "account": {"balance": dm_bal.get("balance", 0.0), "currency_symbol": "৳", "name": "Digital Mart"} if dm_bal else None,
        "upstream_products_count": total_upstream_count,
        "total_products": total_products or 0,
        "upstream_orders_count": upstream_orders or 0,
        "markup_percent": dm_markup,
        "auto_sync": dm_auto_sync,
        "low_balance_alert": dm_low_alert,
    }


@router.post("/sync", dependencies=WRITE)
async def sync_supplier_catalog(services: ServicesDep, supplier: str = Query("all")):
    if not services.suppliers:
        raise HTTPException(400, "Suppliers manager is not initialized.")

    if supplier == "all":
        results = await services.suppliers.sync_all()
        total_cats = sum(c for c, _ in results.values())
        total_prods = sum(p for _, p in results.values())
        return {
            "success": True,
            "categories_synced": total_cats,
            "products_synced": total_prods,
            "details": results,
            "message": f"Successfully synced {total_prods} products across all suppliers!",
        }

    client = services.suppliers.get(supplier)
    if not client or not client.is_configured:
        raise HTTPException(400, f"Supplier '{supplier}' is not configured.")

    cats, prods = await client.sync_catalog()
    return {
        "success": True,
        "categories_synced": cats,
        "products_synced": prods,
        "message": f"Successfully synced {prods} products and {cats} categories from {client.name}!",
    }


@router.get("/remote-products")
async def get_supplier_remote_products(services: ServicesDep, supplier: str = Query("digital_mart"), search: str = Query("")):
    if not services.suppliers:
        raise HTTPException(400, "Suppliers manager is not initialized.")

    sup_code = supplier.lower().strip()
    client = services.suppliers.get(sup_code)
    if not client or not client.is_configured:
        raise HTTPException(400, f"Supplier '{supplier}' is not configured.")

    try:
        raw_products = await client.get_products()
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch live products from {client.name}: {exc}") from exc

    # Cross-reference with store products
    async with services.db.connect() as conn:
        local_rows = await conn.fetch(
            """
            SELECT id, upstream_product_id, is_active, price, reseller_price, title
            FROM products
            WHERE (supplier_code = $1 OR (supplier_code IS NULL AND $1 = 'digital_mart'))
              AND upstream_product_id IS NOT NULL
            """,
            sup_code,
        )
        local_map = {int(r["upstream_product_id"]): dict(r) for r in local_rows if r["upstream_product_id"] is not None}

    clean_search = search.strip().lower()
    annotated: list[dict[str, Any]] = []
    categories_set: set[str] = set()

    for p in raw_products:
        pid = int(p.get("id") or 0)
        title = (p.get("title") or p.get("name") or "").strip()
        cat_name = (p.get("category_name") or "General").strip()
        categories_set.add(cat_name)

        if clean_search and clean_search not in title.lower() and clean_search not in cat_name.lower():
            continue

        local = local_map.get(pid)
        reseller_rate = float(p.get("reseller_price") or p.get("price") or 0.0)
        regular_price = float(p.get("regular_price") or 0.0)

        annotated.append({
            "id": pid,
            "title": title,
            "category_name": cat_name,
            "duration": (p.get("duration") or p.get("duration_label") or "").strip(),
            "reseller_price": reseller_rate,
            "regular_price": regular_price,
            "currency": client.currency,
            "currency_symbol": "৳" if client.currency == "BDT" else "$",
            "icon": (p.get("icon") or "").strip(),
            "description": (p.get("description") or "").strip(),
            "warranty": (p.get("warranty") or "").strip(),
            "in_store": local is not None,
            "local_id": local["id"] if local else None,
            "local_is_active": bool(local["is_active"]) if local else False,
            "local_price": float(local["price"]) if local else None,
        })

    return {
        "supplier": sup_code,
        "supplier_name": client.name,
        "currency": client.currency,
        "total": len(raw_products),
        "filtered_total": len(annotated),
        "categories": sorted(list(categories_set)),
        "products": annotated,
    }


@router.post("/import-products", dependencies=WRITE)
async def import_supplier_products(services: ServicesDep, payload: ImportSupplierProductsPayload = Body(...)):
    if not services.suppliers:
        raise HTTPException(400, "Suppliers manager is not initialized.")

    sup_code = payload.supplier_code.lower().strip()
    client = services.suppliers.get(sup_code)
    if not client or not client.is_configured:
        raise HTTPException(400, f"Supplier '{payload.supplier_code}' is not configured.")

    if payload.target_category_id is not None:
        cats, prods = await client.sync_catalog(
            filter_ids=payload.product_ids,
            force_active=payload.activate,
            target_category_id=payload.target_category_id,
        )
    else:
        cats, prods = await client.sync_catalog(
            filter_ids=payload.product_ids,
            force_active=payload.activate,
        )
    return {
        "success": True,
        "products_synced": prods,
        "categories_synced": cats,
        "message": f"Successfully imported {prods} product(s) from {client.name}!",
    }



@router.post("/config", dependencies=WRITE)
async def update_supplier_config(services: ServicesDep, payload: SupplierConfigPayload = Body(...)):
    url = payload.base_url.strip().rstrip("/")
    key = payload.api_key.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(422, "Base URL must start with http:// or https://")

    sup_code = (payload.supplier_code or "digital_mart").lower().strip()
    if sup_code not in {"digital_mart", "safwan_tiger"}:
        raise HTTPException(422, "Unknown supplier.")
    prefix = "safwan_tiger" if sup_code == "safwan_tiger" else "upstream"
    url_key = f"{prefix}_url" if prefix == "safwan_tiger" else "upstream_reseller_url"
    key_key = f"{prefix}_key" if prefix == "safwan_tiger" else "upstream_reseller_key"
    markup_key = f"{prefix}_markup_percent"
    sync_key = f"{prefix}_auto_sync"
    alert_key = f"{prefix}_low_balance_alert"

    updates = {url_key: url}
    if key and key != "keep_existing":
        updates[key_key] = key
    if payload.markup_percent is not None:
        updates[markup_key] = f"{payload.markup_percent:.2f}"
    if payload.auto_sync is not None:
        updates[sync_key] = str(int(payload.auto_sync))
    if payload.low_balance_alert is not None:
        updates[alert_key] = f"{payload.low_balance_alert:.2f}"

    await services.settings.update(updates)

    client = services.suppliers.get(sup_code) if services.suppliers else None
    if client:
        client.base_url = url
        if key and key != "keep_existing":
            client.api_key = key

    bal = await client.get_balance() if client and client.is_configured else None
    connected = bool(bal and bal.get("ok"))

    return {
        "success": True,
        "connected": connected,
        "message": f"{client.name if client else sup_code} configuration saved!" if connected else "Saved, but connection check failed. Verify API key and URL.",
        "balance": bal.get("balance", 0.0) if bal else None,
    }
