"""Unit tests for product bulk operations and supplier remote products endpoints."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_services
from app.api.admin.auth import require_admin, require_write
from app.api.admin.catalog import router as catalog_router
from app.api.admin.suppliers import router as suppliers_router


def create_test_client():
    services = SimpleNamespace(
        catalog=SimpleNamespace(
            bulk_update_status=AsyncMock(return_value=5),
            bulk_delete_products=AsyncMock(return_value=3),
        ),
        suppliers=SimpleNamespace(
            get=MagicMock(),
            sync_all=AsyncMock(return_value={}),
        ),
        db=SimpleNamespace(
            connect=MagicMock(),
        ),
    )
    app = FastAPI()
    app.include_router(catalog_router, prefix="/api/admin")
    app.include_router(suppliers_router, prefix="/api/admin")
    app.dependency_overrides[get_services] = lambda: services
    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[require_write] = lambda: None
    return TestClient(app), services


def test_bulk_activate_products():
    client, services = create_test_client()
    resp = client.post("/api/admin/products/bulk", json={"action": "activate", "product_ids": [1, 2, 3]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 5
    services.catalog.bulk_update_status.assert_awaited_once_with([1, 2, 3], 1)


def test_unknown_supplier_cannot_overwrite_default_supplier_settings():
    client, services = create_test_client()
    services.settings = SimpleNamespace(update=AsyncMock())
    response = client.post('/api/admin/suppliers/config', json={
        'supplier_code': 'unknown', 'base_url': 'https://example.test/api', 'api_key': 'unused',
    })
    assert response.status_code == 422
    services.settings.update.assert_not_awaited()


def test_bulk_hide_products():
    client, services = create_test_client()
    resp = client.post("/api/admin/products/bulk", json={"action": "hide", "product_ids": [10, 20]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    services.catalog.bulk_update_status.assert_awaited_once_with([10, 20], 0)


def test_bulk_delete_products():
    client, services = create_test_client()
    resp = client.post("/api/admin/products/bulk", json={"action": "delete", "product_ids": [5, 6]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] == 3
    services.catalog.bulk_delete_products.assert_awaited_once_with([5, 6])


def test_bulk_invalid_action():
    client, _ = create_test_client()
    resp = client.post("/api/admin/products/bulk", json={"action": "invalid_action", "product_ids": [1]})
    assert resp.status_code == 422  # validation error from pydantic pattern


def test_remote_products_fetch():
    client, services = create_test_client()

    # Mock supplier client
    mock_supplier = SimpleNamespace(
        name="Digital Mart",
        currency="BDT",
        is_configured=True,
        get_products=AsyncMock(return_value=[
            {"id": 41, "title": "VPN Pro", "category_name": "VPN", "reseller_price": 200.0, "icon": "⚡"},
            {"id": 42, "title": "Netflix Premium", "category_name": "Streaming", "reseller_price": 350.0, "icon": "🎬"},
        ]),
    )
    services.suppliers.get.return_value = mock_supplier

    # Mock DB connection context manager
    conn_mock = AsyncMock()
    conn_mock.fetch.return_value = [
        {"id": 101, "upstream_product_id": 41, "is_active": 1, "price": 250.0, "reseller_price": 200.0, "title": "VPN Pro"}
    ]
    cm_mock = MagicMock()
    cm_mock.__aenter__.return_value = conn_mock
    cm_mock.__aexit__.return_value = False
    services.db.connect.return_value = cm_mock

    resp = client.get("/api/admin/suppliers/remote-products?supplier=digital_mart&search=vpn")
    assert resp.status_code == 200
    data = resp.json()
    assert data["supplier"] == "digital_mart"
    assert data["total"] == 2
    assert data["filtered_total"] == 1
    item = data["products"][0]
    assert item["id"] == 41
    assert item["in_store"] is True
    assert item["local_is_active"] is True
    assert item["local_id"] == 101


def test_import_supplier_products():
    client, services = create_test_client()
    mock_supplier = SimpleNamespace(
        name="Digital Mart",
        is_configured=True,
        sync_catalog=AsyncMock(return_value=(1, 2)),
    )
    services.suppliers.get.return_value = mock_supplier

    resp = client.post(
        "/api/admin/suppliers/import-products",
        json={"supplier_code": "digital_mart", "product_ids": [41, 42], "activate": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["products_synced"] == 2
    mock_supplier.sync_catalog.assert_awaited_once_with(filter_ids=[41, 42], force_active=True)
