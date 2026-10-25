from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import CallbackQuery, User

from app.bot.handlers.deposit import confirm_deposit_callback, show_deposit_methods
from app.services.delivery import receipt, waiting_notice


@pytest.mark.asyncio
@pytest.mark.parametrize("pending", [None, {"id": 19}])
@pytest.mark.parametrize("show_usd", [True, False])
async def test_wallet_shows_balance_and_direct_deposit_options(pending, show_usd):
    query = CallbackQuery(id="wallet", from_user=User(id=123, is_bot=False, first_name="Test"), chat_instance="1", data="open_wallet")
    services = SimpleNamespace(
        deposits=SimpleNamespace(
            pending_for=AsyncMock(return_value=pending),
            methods=AsyncMock(return_value=[{"id": 1, "name": "bKash"}]),
        ),
        payments=SimpleNamespace(instant_options=AsyncMock(return_value=None)),
        users=SimpleNamespace(
            get=AsyncMock(return_value={"balance": 48.75}),
            get_language=AsyncMock(return_value="en"),
        ),
        settings=SimpleNamespace(
            get=AsyncMock(return_value="৳"),
            number=AsyncMock(return_value=125),
            flag=AsyncMock(return_value=show_usd),
            paused_message=AsyncMock(return_value=None),
        ),
    )
    state = SimpleNamespace(clear=AsyncMock())
    with patch("app.bot.handlers.deposit.respond", new_callable=AsyncMock) as respond:
        await show_deposit_methods(query, state, services)
    text, keyboard = respond.await_args.args[1:]
    assert "Balance:" in text
    assert ("$0.39" if show_usd else "48.75") in text
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    if pending:
        assert callbacks == ["open_deposits"]
        assert "Top-up D19 is being verified" in text
    else:
        assert callbacks == ["dep_method_1", "open_deposits"]
    state.clear.assert_awaited_once()


def test_delivery_receipt_keeps_reference_amount_and_escaped_credentials():
    text = receipt({"order_id": 42, "product_title": "A & B", "price": 180, "show_usd": False, "delivered_item": "email@example.com\np<a&ss"})
    assert "Delivered · #42" in text
    assert "Paid:" in text and "180" in text
    assert "A &amp; B" in text
    assert "<code>email@example.com</code>" in text
    assert "<code>p&lt;a&amp;ss</code>" in text


def test_waiting_notice_does_not_claim_delivery():
    text = waiting_notice({"order_id": 42, "product_title": "A & B"})
    assert "Preparing delivery · #42" in text
    assert "Payment received" in text
    assert "Delivered" not in text


@pytest.mark.asyncio
async def test_old_confirmation_cannot_clear_or_resubmit_a_deposit():
    query = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(get_state=AsyncMock(return_value=None), clear=AsyncMock())
    with patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit:
        await confirm_deposit_callback(query, state, SimpleNamespace())
    submit.assert_not_awaited()
    state.clear.assert_not_awaited()
    query.answer.assert_awaited_once()
