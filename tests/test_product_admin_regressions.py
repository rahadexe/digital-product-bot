"""Exercise the same product payloads sent by the operator console."""

import os
import uuid
from urllib.parse import urlsplit

import httpx
import pytest
import pytest_asyncio

from app.api.app import create_app
from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services

DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DSN or urlsplit(DSN).hostname not in ("localhost", "127.0.0.1", "::1"),
    reason="Requires a disposable local PostgreSQL database.",
)


@pytest_asyncio.fixture
async def admin_client():
    schema = "product_admin_" + uuid.uuid4().hex
    db = Database(DSN, schema=schema)
    await migrate(db)
    services = build_services(
        Settings(_env_file=None, database_url=DSN, bot_token="", admin_password="test-password-only"),
        db=db,
        use_telegram=False,
    )
    app = create_app(services)
    token = app.state.admin_auth.create_session_token()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://localhost",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, services
    finally:
        await services.close()
        cleanup = Database(DSN)
        async with cleanup.connect() as conn:
            await conn.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await cleanup.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("delivery_type", ["stock", "manual"])
async def test_console_can_create_product(admin_client, delivery_type):
    client, services = admin_client
    response = await client.post("/api/admin/products", json={
        "title": "New subscription", "price": 150,
        "delivery_type": delivery_type, "upstream_product_id": None,
        "supplier_code": None, "requires_customer_input": 1,
        "customer_input_prompt": "Enter your email",
    })
    assert response.status_code == 200, response.text
    product = await services.catalog.product(response.json()["id"])
    assert product["delivery_type"] == delivery_type
    assert product["requires_customer_input"] is True
    assert product["customer_input_prompt"] == "Enter your email"
    assert product["upstream_product_id"] is None


@pytest.mark.asyncio
async def test_supplier_routing_survives_product_creation(admin_client):
    client, services = admin_client
    response = await client.post("/api/admin/products", json={
        "title": "Supplier subscription", "price": 200,
        "upstream_product_id": 42, "supplier_code": "digital_mart",
        "upstream_devices": 3, "upstream_share_hours": 48,
    })
    assert response.status_code == 200, response.text
    product = await services.catalog.product(response.json()["id"])
    assert product["upstream_product_id"] == 42
    assert product["supplier_code"] == "digital_mart"
    assert product["upstream_devices"] == 3
    assert product["upstream_share_hours"] == 48


@pytest.mark.asyncio
async def test_console_can_toggle_customer_input_and_clear_category(admin_client):
    client, services = admin_client
    category = await services.catalog.create_category(name="Subscriptions")
    product_id = await services.catalog.create_product(category, "Existing subscription", price=150)
    response = await client.put(f"/api/admin/products/{product_id}", json={
        "category_id": None, "requires_customer_input": 1,
        "customer_input_prompt": "Enter your email",
    })
    assert response.status_code == 200, response.text
    product = await services.catalog.product(product_id)
    assert product["category_id"] is None
    assert product["requires_customer_input"] is True
    response = await client.put(f"/api/admin/products/{product_id}", json={
        "requires_customer_input": 0, "customer_input_prompt": "",
    })
    assert response.status_code == 200, response.text
    assert (await services.catalog.product(product_id))["requires_customer_input"] is False
