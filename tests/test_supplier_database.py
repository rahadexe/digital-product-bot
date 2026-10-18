"""Supplier imports and fulfillment against a disposable local database."""

import asyncio
import os
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest

from tests import test_product_admin_regressions

admin_client = test_product_admin_regressions.admin_client

DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DSN or urlsplit(DSN).hostname not in ("localhost", "127.0.0.1", "::1"),
    reason="Requires a disposable local PostgreSQL database.",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger"])
@pytest.mark.parametrize("markup", [0, 15])
async def test_concurrent_import_is_idempotent_and_preserves_customizations(admin_client, code, markup):
    api, services = admin_client
    supplier = services.suppliers.get(code)
    await services.settings.update({
        "upstream_reseller_key" if code == "digital_mart" else "safwan_tiger_key": "synthetic-only",
        "upstream_markup_percent" if code == "digital_mart" else "safwan_tiger_markup_percent": str(markup),
    })
    await supplier._ensure_config()
    supplier.get_products = AsyncMock(return_value=[{
        "id": 41, "title": "Remote original", "name": "Remote original", "category_name": "Remote category",
        "reseller_price": 200, "regular_price": 200, "price": 2, "duration": "7 days", "warranty": "7 days",
    }])
    # Warm caches before import; the customer should see the imported item immediately.
    await services.catalog.categories()
    await services.catalog.products()
    responses = await asyncio.gather(*[
        api.post("/api/admin/suppliers/import-products", json={
            "supplier_code": code, "product_ids": [41], "activate": True,
        }) for _ in range(2)
    ])
    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    async with services.db.connect() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM products WHERE supplier_code = $1", code) == 1
        row = await conn.fetchrow("SELECT * FROM products WHERE supplier_code = $1", code)
        assert await conn.fetchval("SELECT COUNT(*) FROM categories") == 1
    assert len(await services.catalog.products()) == 1
    assert len(await services.catalog.categories()) == 1
    wholesale = 200 if code == "digital_mart" else 250
    assert float(row["price"]) == round(wholesale * (1 + markup / 100), 2)
    assert row["duration_label"] == "7 days"
    if code == "safwan_tiger":
        assert row["warranty_label"] == "7 days"
    custom_category = await services.catalog.create_category(name="Custom category")
    await services.catalog.update_product(row["id"], title="Admin title", price=999,
                                          category_id=custom_category, is_active=0)
    result = await api.post(f"/api/admin/suppliers/sync?supplier={code}")
    assert result.status_code == 200, result.text
    product = await services.catalog.product(row["id"])
    assert product["title"] == "Admin title"
    assert product["category_id"] == custom_category
    assert product["price"] == 999
    assert not product["is_active"]
    async with services.db.connect() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM categories") == 2


@pytest.mark.asyncio
async def test_partial_missing_selection_never_imports_a_subset(admin_client):
    api, services = admin_client
    await services.settings.update({"upstream_reseller_key": "synthetic-only"})
    supplier = services.suppliers.get("digital_mart")
    await supplier._ensure_config()
    supplier.get_products = AsyncMock(return_value=[{
        "id": 41, "title": "Available", "reseller_price": 100, "regular_price": 150,
    }])
    response = await api.post("/api/admin/suppliers/import-products", json={"product_ids": [41, 42]})
    assert response.status_code == 502
    async with services.db.connect() as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM products") == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM categories") == 0


@pytest.mark.asyncio
async def test_status_has_no_key_fragments_and_handles_unreachable_supplier(admin_client):
    api, services = admin_client
    await services.settings.update({
        "upstream_reseller_key": "synthetic-private-value-not-for-output",
        "upstream_auto_sync": "0", "upstream_markup_percent": "0", "upstream_low_balance_alert": "0",
    })
    supplier = services.suppliers.get("digital_mart")
    await supplier._ensure_config()
    supplier.get_balance = AsyncMock(return_value=None)
    response = await api.get("/api/admin/suppliers/status")
    assert response.status_code == 200
    data = response.json()
    dm = data["providers"][0]
    assert not dm["connected"] and dm["is_configured"]
    assert dm["api_key_masked"] == "Configured"
    assert dm["auto_sync"] == dm["markup_percent"] == dm["low_balance_alert"] == 0
    assert "synthetic-private" not in response.text


@pytest.mark.asyncio
async def test_shared_supplier_quantity_guard_never_calls_paid_api(admin_client):
    _, services = admin_client
    await services.users.sync_profile(551122, first_name="Synthetic")
    await services.users.adjust_balance(551122, 1000)
    await services.settings.update({"upstream_reseller_key": "synthetic-only"})
    product = await services.catalog.create_product(
        None, "Shared supplier", price=100, upstream_product_id=41, supplier_code="digital_mart", upstream_devices=2,
    )
    supplier = services.suppliers.get("digital_mart")
    supplier.purchase = AsyncMock()
    success, message, _ = await services.purchases.purchase(551122, product, quantity=3, request_id="capacity")
    assert not success and "up to 2" in message
    supplier.purchase.assert_not_awaited()
    assert (await services.users.get(551122))["balance"] == 1000


@pytest.mark.asyncio
async def test_retry_records_shared_seat_allocations_not_only_inventory_uses(admin_client):
    _, services = admin_client
    await services.users.sync_profile(551122, first_name="Synthetic")
    await services.users.adjust_balance(551122, 1000)
    await services.settings.update({"upstream_reseller_key": "synthetic-only", "supplier_fallback_to_waiting": "1"})
    product = await services.catalog.create_product(
        None, "Shared supplier", price=100, upstream_product_id=41, supplier_code="digital_mart", upstream_devices=2,
    )
    supplier = services.suppliers.get("digital_mart")
    supplier.purchase = AsyncMock(side_effect=[
        {"success": False, "detail": "Supplier balance is low.", "insufficient_balance": True},
        {"success": True, "credentials": "synthetic-item", "order_id": 91, "fulfillment": "delivered"},
    ])
    supplier.check_low_balance = AsyncMock()
    success, _, receipt = await services.purchases.purchase(551122, product, quantity=2, request_id="shared-retry")
    assert success and receipt["fulfillment"] == "waiting"
    success, message, _ = await services.purchases.retry_supplier_fulfillment(receipt["order_id"])
    assert success, message
    async with services.db.connect() as conn:
        item = await conn.fetchrow("SELECT * FROM inventory_items WHERE product_id = $1", product)
        allocated = await conn.fetchval(
            "SELECT allocated_units FROM order_inventory_allocations WHERE order_id = $1", receipt["order_id"],
        )
    assert item["uses"] == allocated == 2
    assert item["status"] == "sold"
    assert (await services.users.get(551122))["balance"] == 800
