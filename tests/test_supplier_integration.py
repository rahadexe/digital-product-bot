"""Supplier contracts, import safety and cache isolation. No live API credentials."""

import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.services.suppliers import DigitalMartClient, SafwanTigerClient, SupplierError, SupplierManager
from app.services.upstream_reseller import UpstreamResellerService
from app.workers.upstream import UpstreamWorker
from tests.test_bulk_and_suppliers import create_test_client


def provider(code, settings=None, db=None):
    config = Settings(_env_file=None, bot_token="", upstream_reseller_key="")
    client = (SafwanTigerClient(db, settings) if code == "safwan_tiger"
              else UpstreamResellerService(db, config, settings) if code == "legacy"
              else DigitalMartClient(db, config, settings))
    client.api_key = "synthetic-only"
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger", "legacy"])
@pytest.mark.parametrize("status,body", [
    (401, {"detail": "private upstream response"}),
    (403, {"error": "private upstream response"}),
    (404, {"error": "not_found"}),
    (429, {"error": "rate_limited"}),
    (502, {"detail": "private upstream response"}),
    (200, {"success": False, "products": []}),
    (200, {"products": "invalid"}),
    (200, {"products": [{"id": 1, "title": "Invalid", "price": "NaN"}]}),
    (200, {"products": [{"id": 1, "title": "Invalid", "price": -1}]}),
    (200, {"products": [{"id": True, "title": "Invalid"}]}),
    (200, {"products": [{"id": 1, "title": "Duplicate"}, {"id": 1, "title": "Duplicate"}]}),
])
async def test_catalog_errors_are_not_successful_empty_catalogs(code, status, body):
    client = provider(code)
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    http = httpx.AsyncClient(transport=transport)
    try:
        with patch("app.services.suppliers.httpx.AsyncClient", return_value=http):
            with pytest.raises(SupplierError) as error:
                await client.get_products()
    finally:
        await http.aclose()
    assert "private upstream response" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger"])
async def test_empty_successful_catalog_is_valid(code):
    client = provider(code)
    http = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"success": True, "products": []})
    ))
    try:
        with patch("app.services.suppliers.httpx.AsyncClient", return_value=http):
            assert await client.get_products() == []
    finally:
        await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger", "legacy"])
async def test_cached_balance_does_not_survive_removed_key(code):
    settings = SimpleNamespace(get=AsyncMock(return_value=""))
    client = provider(code, settings)
    client._balance_cache = (time.monotonic(), {"ok": True, "balance": 987})
    assert await client.get_balance() is None
    assert client._balance_cache is None
    assert not client.is_configured


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger"])
@pytest.mark.parametrize("body", [{}, {"success": True}, {"balance": "NaN"}, {"user": {"balance": "NaN"}}])
async def test_invalid_account_is_not_connected_with_fake_zero_balance(code, body):
    client = provider(code)
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body)))
    try:
        with patch("app.services.suppliers.httpx.AsyncClient", return_value=http):
            assert await client.get_balance(force=True) is None
    finally:
        await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger", "legacy"])
@pytest.mark.parametrize("credentials,status", [
    ({}, "waiting"),
    ({"credentials": "synthetic delivered content"}, "delivered"),
    ({"credentials": "  "}, "waiting"),
    ({"credentials": "synthetic", "fulfillment": "waiting"}, "waiting"),
])
async def test_purchase_message_is_never_delivered_as_credentials(code, credentials, status):
    client = provider(code)
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={
            "success": True, "ok": True, "order_id": 15,
            "message": "Order accepted. Please wait.", **credentials,
        })

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        with patch("app.services.suppliers.httpx.AsyncClient", return_value=http):
            result = await client.purchase(41, custom_id="stable-reference")
    finally:
        await http.aclose()
    assert result["success"]
    assert result["fulfillment"] == status
    assert result["credentials"] != "Order accepted. Please wait."
    assert "stable-reference" in seen[0].content.decode()
    assert seen[0].url.path.endswith("/order" if code == "safwan_tiger" else "/orders")


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger", "legacy"])
async def test_purchase_body_and_exception_details_are_not_leaked(code, caplog):
    client = provider(code)
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
        500, json={"detail": "private-upstream-content"}
    )))
    try:
        with patch("app.services.suppliers.httpx.AsyncClient", return_value=http):
            result = await client.purchase(41, custom_id="stable-reference")
    finally:
        await http.aclose()
    assert not result["success"] and result["outcome_unknown"]
    assert "private-upstream-content" not in str(result) + caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger"])
async def test_missing_selected_product_fails_before_any_database_write(code):
    db = SimpleNamespace(transaction=MagicMock())
    client = provider(code, db=db)
    client.get_products = AsyncMock(return_value=[{"id": 41, "title": "Available"}])
    with pytest.raises(SupplierError, match="no longer available"):
        await client.sync_catalog(filter_ids=[41, 42])
    db.transaction.assert_not_called()


@pytest.mark.asyncio
async def test_worker_uses_each_suppliers_own_auto_sync_flag_and_continues_after_failure():
    dm = SimpleNamespace(code="digital_mart", is_configured=True, _ensure_config=AsyncMock(),
                         check_low_balance=AsyncMock(side_effect=SupplierError("Offline")),
                         sync_catalog=AsyncMock(return_value=(0, 2)))
    tiger = SimpleNamespace(code="safwan_tiger", is_configured=True, _ensure_config=AsyncMock(),
                            check_low_balance=AsyncMock(), sync_catalog=AsyncMock(return_value=(0, 3)))
    services = SimpleNamespace(
        suppliers=SimpleNamespace(list_all=lambda: [dm, tiger]),
        settings=SimpleNamespace(flag=AsyncMock(side_effect=lambda key: key == "safwan_tiger_auto_sync")),
        notifier=None,
    )
    await UpstreamWorker(services).check_once()
    dm.sync_catalog.assert_not_awaited()
    tiger.sync_catalog.assert_awaited_once()
    tiger.check_low_balance.assert_awaited_once()


@pytest.mark.asyncio
async def test_manager_no_longer_reports_failed_sync_as_zero_products_success():
    manager = SupplierManager(None, Settings(_env_file=None, bot_token=""))
    dm = manager.get("digital_mart")
    dm.api_key = "synthetic-only"
    dm.sync_catalog = AsyncMock(side_effect=SupplierError("Connection failed"))
    with pytest.raises(SupplierError):
        await manager.sync_all()


def test_import_rejects_missing_category_before_calling_supplier():
    client, services = create_test_client()
    supplier = SimpleNamespace(name="Digital Mart", is_configured=True, sync_catalog=AsyncMock())
    services.suppliers.get.return_value = supplier
    connection = AsyncMock()
    connection.fetchval.return_value = None
    cm = MagicMock()
    cm.__aenter__.return_value = connection
    cm.__aexit__.return_value = False
    services.db.connect.return_value = cm
    response = client.post("/api/admin/suppliers/import-products", json={
        "product_ids": [41], "target_category_id": 999,
    })
    assert response.status_code == 422
    supplier.sync_catalog.assert_not_awaited()


@pytest.mark.parametrize("ids", [[], [0], [-1], [True], [1.5], [1.0]])
def test_import_rejects_invalid_product_ids(ids):
    client, services = create_test_client()
    response = client.post("/api/admin/suppliers/import-products", json={"product_ids": ids})
    assert response.status_code == 422
    services.suppliers.get.assert_not_called()


def test_import_deduplicates_ids_and_does_not_claim_success_for_zero_products():
    client, services = create_test_client()
    supplier = SimpleNamespace(name="Digital Mart", is_configured=True, sync_catalog=AsyncMock(return_value=(0, 0)))
    services.suppliers.get.return_value = supplier
    response = client.post("/api/admin/suppliers/import-products", json={"product_ids": [41, 41]})
    assert response.status_code == 409
    supplier.sync_catalog.assert_awaited_once_with(filter_ids=[41], force_active=False)


def test_remote_api_failure_is_actionable_502_not_empty_products():
    client, services = create_test_client()
    supplier = SimpleNamespace(name="Digital Mart", is_configured=True,
                               get_products=AsyncMock(side_effect=SupplierError("Check the API key.")))
    services.suppliers.get.return_value = supplier
    response = client.get("/api/admin/suppliers/remote-products")
    assert response.status_code == 502
    assert response.json()["detail"] == "Check the API key."


@pytest.mark.parametrize("url", [
    "not-a-url", "http://example.test/api", "https://user:password@example.test/api",
    "https://example.test/api?key=synthetic", "https://example.test/api#fragment",
])
def test_config_rejects_insecure_or_credential_bearing_urls(url):
    client, services = create_test_client()
    services.settings = SimpleNamespace(update=AsyncMock())
    assert client.post("/api/admin/suppliers/config", json={"base_url": url}).status_code == 422
    services.settings.update.assert_not_awaited()


def test_save_and_connect_forces_fresh_balance_and_keeps_saved_key():
    client, services = create_test_client()
    services.settings = SimpleNamespace(update=AsyncMock())
    supplier = SimpleNamespace(name="Digital Mart", is_configured=True, api_key="synthetic-only",
                               _balance_cache=(time.monotonic(), {"ok": True, "balance": 25}),
                               get_balance=AsyncMock(return_value=None))
    services.suppliers.get.return_value = supplier
    response = client.post("/api/admin/suppliers/config", json={
        "base_url": "https://example.test/api/", "api_key": "", "auto_sync": 0, "markup_percent": 0,
    })
    assert response.status_code == 200 and response.json()["connected"] is False
    supplier.get_balance.assert_awaited_once_with(force=True)
    assert supplier._balance_cache is None
    assert supplier.api_key == "synthetic-only"
    updates = services.settings.update.await_args.args[0]
    assert "upstream_reseller_key" not in updates
    assert updates["upstream_auto_sync"] == "0"
    assert updates["upstream_markup_percent"] == "0.00"


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger"])
async def test_general_sync_does_not_create_categories_or_import_unselected_products(code):
    conn = AsyncMock()
    conn.fetchrow.return_value = None

    @asynccontextmanager
    async def transaction():
        yield conn

    client = provider(code, db=SimpleNamespace(transaction=transaction))
    client.get_products = AsyncMock(return_value=[{"id": 41, "title": "Product", "name": "Product", "price": 2}])
    assert await client.sync_catalog() == (0, 0)
    conn.fetchval.assert_not_awaited()
    assert conn.execute.await_count == 1  # transaction lock, no inserts


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger"])
async def test_supplier_balance_notice_is_short_english_without_decorative_symbols(code):
    settings = SimpleNamespace(get=AsyncMock(return_value="10"), admin_chat_ids=AsyncMock(return_value=[123]))
    client = provider(code, settings=settings)
    client.get_balance = AsyncMock(return_value={"ok": True, "balance": 2})
    notifier = SimpleNamespace(send=AsyncMock())

    def schedule(coroutine):
        coroutine.close()

    notifier.in_background = schedule
    assert await client.check_low_balance(notifier)
    # The async send is normally scheduled by Notifier; inspect its queued arguments here.
    text = notifier.send.call_args.args[1]
    assert len(text.splitlines()) == 3
    assert "Top up" in text and "balance is low" in text
    assert not any(symbol in text for symbol in ("•", "⚠", "—", "ব্যা"))
    # The message carries an inline button to mute alerts directly
    kb = notifier.send.call_args.kwargs.get("keyboard")
    assert kb is not None
    assert "Turn Off Alert" in kb.inline_keyboard[0][0].text
    assert kb.inline_keyboard[0][0].callback_data == f"mute_sup_{code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["digital_mart", "safwan_tiger"])
async def test_supplier_balance_notice_disabled_when_flag_off_or_zero_threshold(code):
    # Test flag off
    settings = SimpleNamespace(
        get=AsyncMock(return_value="10"),
        flag=AsyncMock(return_value=False),
        admin_chat_ids=AsyncMock(return_value=[123]),
    )
    client = provider(code, settings=settings)
    client.get_balance = AsyncMock(return_value={"ok": True, "balance": 2})
    notifier = SimpleNamespace(send=AsyncMock())
    assert not await client.check_low_balance(notifier)

    # Test threshold zero
    settings_zero = SimpleNamespace(
        get=AsyncMock(return_value="0"),
        flag=AsyncMock(return_value=True),
        admin_chat_ids=AsyncMock(return_value=[123]),
    )
    client_zero = provider(code, settings=settings_zero)
    client_zero.get_balance = AsyncMock(return_value={"ok": True, "balance": 0})
    assert not await client_zero.check_low_balance(notifier)
