import time
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Chat, Message, User
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bot.middlewares import StoreAccess
from app.api.telegram import router
from app.services.settings import SPECS
from app.services.suppliers import SafwanTigerClient, SupplierManager
from app.core.config import Settings
from app.services.notifications import Notifier
from app.bot import formatting
import httpx
from app.services.suppliers import DigitalMartClient
from app.services.upstream_reseller import UpstreamResellerService


@pytest.mark.asyncio
async def test_channel_cache_does_not_allow_a_newly_banned_user():
    middleware = StoreAccess()
    services = SimpleNamespace(
        users=SimpleNamespace(get=AsyncMock(return_value={'is_banned': 1})),
        settings=SimpleNamespace(admin_chat_ids=AsyncMock(return_value=[])),
    )
    message = Message(message_id=1, date=datetime.now(timezone.utc),
                      chat=Chat(id=123, type='private'),
                      from_user=User(id=123, is_bot=False, first_name='Test'), text='Balance')
    handler = AsyncMock()
    with patch.object(Message, 'answer', new_callable=AsyncMock) as answer:
        await middleware(handler, message, {'services': services})
        answer.assert_awaited_once_with('Your account is suspended.')
    handler.assert_not_awaited()


def test_non_ascii_webhook_secret_is_rejected_without_a_server_error():
    app = FastAPI()
    app.include_router(router)
    app.state.services = SimpleNamespace(
        notifier=SimpleNamespace(bot=object()), runtime=SimpleNamespace(dispatcher=object()),
        config=SimpleNamespace(webhook_secret='a' * 40),
    )
    response = TestClient(app).post('/telegram/webhook', headers=[
        (b'x-telegram-bot-api-secret-token', b'\xff'),
    ], content=b'{}')
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_supplier_credentials_start_empty_and_load_from_settings():
    assert SPECS['safwan_tiger_key'].default == ''
    assert not SafwanTigerClient(None).is_configured
    async def get(key):
        return {'safwan_tiger_key': 'test-only-supplier-key'}.get(key, '')
    manager = SupplierManager(None, Settings(_env_file=None, bot_token=''), SimpleNamespace(get=get))
    await manager.load_config()
    assert manager.get('safwan_tiger').is_configured


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['digital_mart', 'safwan_tiger', 'legacy'])
async def test_removing_saved_supplier_key_does_not_retain_it_in_memory(provider):
    settings = SimpleNamespace(get=AsyncMock(return_value=''))
    config = Settings(_env_file=None, bot_token='', upstream_reseller_key='')
    supplier = (SafwanTigerClient(None, settings) if provider == 'safwan_tiger' else
                DigitalMartClient(None, config, settings) if provider == 'digital_mart' else
                UpstreamResellerService(None, config, settings))
    supplier.api_key = 'removed-test-key'
    await supplier._ensure_config()
    assert not supplier.is_configured


@pytest.mark.asyncio
async def test_shutdown_cancels_delayed_notifications_before_clients_close():
    notifier = Notifier(object(), None)
    notifier.in_background(asyncio.sleep(3600))
    tasks = set(notifier._pending)
    await notifier.drain(timeout=0)
    assert all(task.cancelled() for task in tasks)


def test_menu_tracking_has_bounded_memory():
    with patch.object(formatting, '_last_menu_messages', {}), patch.object(formatting, '_chat_active_messages', {}), \
         patch.object(formatting, 'MAX_TRACKED_MENU_CHATS', 3), patch.object(formatting, 'MAX_TRACKED_MENU_MESSAGES', 2):
        for chat in range(10):
            for message in range(5):
                formatting.remember_menu_message(chat, message)
        assert len(formatting._last_menu_messages) == 3
        assert len(formatting._chat_active_messages) == 3
        assert all(len(messages) == 2 for messages in formatting._chat_active_messages.values())


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['digital_mart', 'safwan_tiger', 'legacy'])
@pytest.mark.parametrize('response_status', [None, 502, 408, 202, 402])
async def test_supplier_timeout_and_server_errors_require_reconciliation(provider, response_status):
    supplier = (DigitalMartClient(None, Settings(_env_file=None, bot_token=''))
                if provider == 'digital_mart' else SafwanTigerClient(None))
    if provider == 'legacy':
        supplier = UpstreamResellerService(None, Settings(_env_file=None, bot_token=''))
    supplier.api_key = 'test-only'
    def respond(request):
        if response_status is None:
            raise httpx.ReadTimeout('Timed out after sending purchase', request=request)
        return httpx.Response(response_status, json={'detail': 'balance unavailable'})
    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    with patch('app.services.suppliers.httpx.AsyncClient', return_value=client):
        result = await supplier.purchase(77, custom_id='stable-test-id')
    assert not result['success']
    assert result.get('outcome_unknown', False) == (response_status != 402)
