"""Regressions for forged statements, stale wallets and currency preferences."""

import asyncio
from contextlib import asynccontextmanager
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.payments import router
from app.services.users import UserService
from app.services.deposits import DepositService
from app.services.errors import InvalidInputError


def statement_client(secret="statement-secret", fallback=""):
    services = SimpleNamespace(
        config=SimpleNamespace(webhook_secret=fallback),
        settings=SimpleNamespace(get=AsyncMock(return_value=secret)),
        deposits=SimpleNamespace(record_received_transaction=AsyncMock(return_value={"id": 1})),
        payments=SimpleNamespace(handle_webhook=AsyncMock()),
    )
    app = FastAPI()
    app.state.services = services
    app.include_router(router)
    return TestClient(app), services


@pytest.mark.parametrize("path", ["sms-webhook", "zinipay/webhook"])
@pytest.mark.parametrize("secret,provided", [("statement-secret", ""), ("statement-secret", "wrong"), ("", "anything")])
def test_forged_statements_never_reach_the_ledger(path, secret, provided):
    client, services = statement_client(secret)
    response = client.post(f"/api/payments/{path}", headers={"x-webhook-secret": provided},
                           json={"transaction_id": "ABC123456", "amount": 500})
    assert response.status_code == 401
    services.deposits.record_received_transaction.assert_not_awaited()


@pytest.mark.parametrize("path", ["sms-webhook", "zinipay/webhook"])
@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity", "-1", "0.00001", "1000000001"])
def test_invalid_statement_amount_is_a_client_error(path, amount):
    client, services = statement_client()
    response = client.post(f"/api/payments/{path}", headers={"x-webhook-secret": "statement-secret"},
                           json={"transaction_id": "ABC123456", "amount": amount})
    assert response.status_code == 400
    services.deposits.record_received_transaction.assert_not_awaited()


def test_unsigned_invoice_callback_only_requests_server_verification():
    client, services = statement_client()
    response = client.post("/api/payments/zinipay/webhook", json={
        "invoice_id": "invoice123", "transaction_id": "ABC123456", "amount": 500,
    })
    assert response.status_code == 200
    services.payments.handle_webhook.assert_awaited_once_with("invoice123", "")
    services.deposits.record_received_transaction.assert_not_awaited()


def test_sms_non_object_body_is_rejected():
    client, services = statement_client()
    response = client.post("/api/payments/sms-webhook", headers={"x-webhook-secret": "statement-secret"}, json=[])
    assert response.status_code == 400
    services.deposits.record_received_transaction.assert_not_awaited()


class WalletDatabase:
    def __init__(self):
        self.row = {"balance": 12.5, "currency": "BDT", "language": "en"}
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def connect(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        async with self.lock:
            yield self

    async def fetchrow(self, query, *args):
        return dict(self.row)

    async def execute(self, query, currency, language, user_id):
        self.row.update(currency=currency, language=language)


@pytest.mark.asyncio
async def test_wallet_reads_observe_external_credit_immediately():
    db = WalletDatabase()
    service = UserService(db, MagicMock(), MagicMock())
    assert (await service.get(123))["balance"] == 12.5
    db.row["balance"] = 20
    assert (await service.get(123))["balance"] == 20


@pytest.mark.asyncio
async def test_currency_toggle_uses_locked_preference_and_preserves_wallet():
    db = WalletDatabase()
    service = UserService(db, MagicMock(), MagicMock())
    service._user_cache[123] = (monotonic(), {"currency": "USD"})
    assert await service.toggle_currency(123) == "USD"
    assert await service.toggle_currency(123) == "BDT"
    assert db.row["balance"] == 12.5
    assert db.row["language"] == "en-BD"


@pytest.mark.asyncio
async def test_cold_locale_uses_explicit_currency_over_legacy_language():
    service = UserService(WalletDatabase(), MagicMock(), MagicMock())
    assert await service.get_language(123) == "en-BD"


@pytest.mark.asyncio
async def test_locale_reads_ignore_stale_cache():
    service = UserService(WalletDatabase(), MagicMock(), MagicMock())
    timestamp = monotonic() - 20
    service._lang_cache[123] = (timestamp, "en")
    assert await service.get_language(123) == "en-BD"
    assert service._lang_cache[123][0] == timestamp


@pytest.mark.asyncio
async def test_adjustment_notification_honors_bdt_preference():
    notifier = SimpleNamespace(send=AsyncMock())
    service = UserService(WalletDatabase(), SimpleNamespace(number=AsyncMock(return_value=125)), notifier)
    await service._notify_adjustment(123, 2, 12, "<bonus>")
    text = notifier.send.call_args.args[1]
    assert "250 ৳" in text and "1500 ৳" in text
    assert "&lt;bonus&gt;" in text


@pytest.mark.asyncio
async def test_binance_callback_credits_the_clicking_customer_not_message_author():
    from app.bot.handlers.deposit import claim_binance_payment

    message = SimpleNamespace(from_user=SimpleNamespace(id=999, is_bot=True))
    status = SimpleNamespace(edit_text=AsyncMock())
    services = SimpleNamespace(
        users=SimpleNamespace(get_language=AsyncMock(return_value="en")),
        binance=SimpleNamespace(claim=AsyncMock(side_effect=RuntimeError("gateway down"))),
    )
    state = SimpleNamespace(clear=AsyncMock())
    await claim_binance_payment(message, state, services, 1, "ABC123", status_msg=status, user_id=123)
    services.binance.claim.assert_awaited_once_with(123, 1, "ABC123", expected_usdt=None)
    assert "An error occurred" in status.edit_text.call_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("rate,credit", [(float("nan"), 4), (float("inf"), 4), (-125, 4), (0, 4), (125, 4.0001)])
async def test_deposit_rejects_invalid_rates_and_even_small_overcredits(rate, credit):
    conn = SimpleNamespace(fetchrow=AsyncMock(side_effect=[
        {"id": 1, "username": "customer", "is_banned": 0},
        {"id": 1, "name": "bKash", "auto_verify": "none"},
    ]))

    @asynccontextmanager
    async def transaction():
        yield conn

    service = DepositService.__new__(DepositService)
    service.db = SimpleNamespace(transaction=transaction)
    service.settings = SimpleNamespace(paused_message=AsyncMock(return_value=""),
                                       values=AsyncMock(return_value={"usd_rate": "125"}))
    with pytest.raises(InvalidInputError):
        await service.create_request(123, 1, credit, "ABC123456", pay_amount=500, quoted_rate=rate)
