"""Payment currency is fixed by the method; wallet display follows the customer."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, User

from app.bot.customer_copy import order_refunded, payment_summary, wallet_updated
from app.bot.formatting import format_dual_price
from app.bot.handlers.deposit import _render_instant_invoice, process_deposit_amount
from app.services.delivery import DeliveryService


@pytest.mark.parametrize("currency,is_binance,payment,expected", [
    ("BDT", False, 500, "Send: <code>500 ৳</code>"),
    ("USD", False, 500, "Send: <code>500 ৳</code>\nAdds to balance: <code>$4</code>"),
    ("BDT", True, 4, "Send: <code>4 USDT</code>\nAdds to balance: <code>500 ৳</code>"),
    ("USD", True, 4, "Send: <code>4 USDT</code>\nAdds to balance: <code>$4</code>"),
])
def test_payment_display_matrix(currency, is_binance, payment, expected):
    assert payment_summary(4, payment, currency=currency, is_binance=is_binance, usd_rate=125) == expected


@pytest.mark.parametrize("currency,is_binance", [(c, b) for c in ("BDT", "USD") for b in (False, True)])
@pytest.mark.asyncio
async def test_amount_entry_keeps_accounting_usd_and_shows_selected_currency(currency, is_binance):
    incoming = MagicMock(spec=Message)
    incoming.from_user = User(id=123, is_bot=False, first_name="Customer")
    incoming.text = "4" if is_binance else "500"
    incoming.chat = SimpleNamespace(id=123, type="group")
    incoming.bot = None
    incoming.answer = AsyncMock(return_value=None)
    state = SimpleNamespace(
        get_data=AsyncMock(return_value={
            "method_id": 1, "method_name": "Binance" if is_binance else "bKash",
            "is_binance": is_binance, "min_deposit": 1, "rate": 1 if is_binance else 125,
        }), update_data=AsyncMock(), set_state=AsyncMock(),
    )
    services = SimpleNamespace(
        users=SimpleNamespace(get_currency=AsyncMock(return_value=currency),
                              get_language=AsyncMock(return_value="en-BD" if currency == "BDT" else "en")),
        settings=SimpleNamespace(number=AsyncMock(side_effect=lambda key: 125 if key == "usd_rate" else 1000)),
    )
    await process_deposit_amount(incoming, state, services)
    saved = state.update_data.await_args_list[0].kwargs
    assert saved["manual_amount"] == 4
    assert saved["pay_amount"] == (4 if is_binance else 500)
    text = incoming.answer.await_args.args[0]
    assert "equivalent" not in text and "→" not in text
    if is_binance:
        assert ("$4" in text) == (currency == "USD")
        assert "4 USDT" in text
    else:
        if currency == "USD":
            assert "$4" in text
            assert "$1 = 125৳" in text
        else:
            assert "$" not in text
        assert "500 ৳" in text


@pytest.mark.parametrize("currency,credit", [("BDT", "500 ৳"), ("USD", "$4")])
def test_notifications_and_refunds_use_preference(currency, credit):
    text = wallet_updated(4, 8, "$", currency=currency, usd_rate=125)
    assert credit in text
    assert ("$" in text) == (currency == "USD")
    refund = order_refunded(1, "Subscription", 4, "$", currency=currency, usd_rate=125)
    assert credit in refund
    assert ("$" in refund) == (currency == "USD")


@pytest.mark.asyncio
@pytest.mark.parametrize("currency", ["BDT", "USD"])
async def test_checkout_reopens_in_current_preference(currency):
    services = SimpleNamespace(
        users=SimpleNamespace(get_currency=AsyncMock(return_value=currency)),
        settings=SimpleNamespace(number=AsyncMock(return_value=125)),
    )
    text, keyboard = await _render_instant_invoice(
        {"reference": "ABC123", "credit_amount": 4, "pay_amount": 500}, services, 123,
    )
    assert "500 ৳" in text
    assert ("$4" in text) == (currency == "USD")
    assert "USD" not in text and "equivalent" not in text


@pytest.mark.asyncio
async def test_delivery_receipt_reads_customer_preference():
    connection = SimpleNamespace(
        fetchrow=AsyncMock(return_value={"currency": "BDT", "language": "en"}), execute=AsyncMock(),
    )
    service = DeliveryService(None)
    await service.enqueue_order(123, {"order_id": 1, "price": 4, "usd_rate": 125}, conn=connection)
    text = connection.execute.await_args.args[2]
    assert "500 ৳" in text and "$" not in text


def test_bdt_profile_formatter_has_no_implicit_second_currency():
    for locale in ("bn", "en-BD"):
        assert format_dual_price(4, usd_rate=125, lang=locale) == "500 ৳"
    assert format_dual_price(4, usd_rate=125, currency="BDT", show_usd=True) == "500 ৳ (≈$4)"


def test_usd_balance_preserves_wallet_precision():
    assert format_dual_price(4.0001, currency="USD") == "$4.0001"
    assert format_dual_price(4, currency="USD") == "$4"


def test_quantity_selector_price_matches_card_unit_price():
    from app.bot.keyboards import get_quantity_selector_keyboard

    # Product price is 0.792 (99 BDT at 125 rate).
    # Previous bug: total_price = round(unit_price * 1, 2) produced 0.79 -> 0.79 * 125 = 98.75 BDT!
    # Card showed 'Price: 99 BDT' while button showed 'Buy · 98.75 BDT'.
    unit_price = 0.792
    usd_rate = 125.0

    kb = get_quantity_selector_keyboard(
        product_id=10,
        quantity=1,
        unit_price=unit_price,
        max_stock=10,
        user_balance=2000.0,
        usd_rate=usd_rate,
        currency='BDT',
    )
    # The buy button must show 99 ৳, matching card text Price: 99 ৳
    buy_btn = next(btn for row in kb.inline_keyboard for btn in row if 'Buy' in btn.text)
    assert buy_btn.text == 'Buy · 99 ৳'
    assert '98.75' not in buy_btn.text
