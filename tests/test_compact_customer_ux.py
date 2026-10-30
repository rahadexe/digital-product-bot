"""Compact menu and Telegram ForceReply contracts, without live Telegram calls."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ForceReply, InlineKeyboardMarkup

from app.bot.handlers.deposit import (
    DepositStates,
    begin_payment_reference,
    process_deposit_amount,
    process_deposit_txid,
)
from app.bot.handlers.navigation import NAVIGATION_TEXTS
from app.bot.keyboards import get_main_inline_keyboard, get_persistent_reply_keyboard


def context():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=2))


def customer():
    return SimpleNamespace(
        from_user=SimpleNamespace(id=2),
        answer=AsyncMock(return_value=SimpleNamespace(message_id=9)),
        edit_text=AsyncMock(),
        chat=None,
        text="BK123456",
    )


def services():
    return SimpleNamespace(
        users=SimpleNamespace(get_language=AsyncMock(return_value="en")),
        settings=SimpleNamespace(number=AsyncMock(return_value=1000)),
        deposits=SimpleNamespace(
            pending_for=AsyncMock(return_value=None),
            get_method=AsyncMock(return_value={"id": 3, "is_active": True}),
        ),
    )


def test_five_primary_buttons_are_short_and_routable():
    reply = get_persistent_reply_keyboard()
    inline = get_main_inline_keyboard()
    labels = [[b.text for b in row] for row in reply.keyboard]
    assert labels == [
        ["🛍 Shop", "💰 Balance"],
        ["💬 Help", "👤 Account"],
    ]
    assert [[b.text for b in row] for row in inline.inline_keyboard] == [
        ["💱 Currency: ৳ BDT", "🎁 Referral"],
    ]
    assert [NAVIGATION_TEXTS[b.text] for row in reply.keyboard for b in row] == [
        "other_products", "deposit", "help", "account",
    ]
    assert all(len(b.text) <= 12 for row in reply.keyboard for b in row)


def test_admin_panel_is_a_separate_admin_only_home_row():
    customer_reply = get_persistent_reply_keyboard()
    customer_inline = get_main_inline_keyboard()
    assert len(customer_reply.keyboard) == 2
    assert len(customer_inline.inline_keyboard) == 1

    admin_reply = get_persistent_reply_keyboard(is_admin=True)
    admin_inline = get_main_inline_keyboard(is_admin=True)
    assert admin_reply.keyboard[-1][0].text == "⚙️ Admin Panel"
    assert len(admin_reply.keyboard) == 3
    assert len(admin_inline.inline_keyboard) == 1


def test_products_keyboard_renders_category_chips_on_top():
    from app.bot.keyboards import get_products_keyboard
    products = [
        {"id": 1, "title": "Canva Pro", "duration_label": "1 Month", "price": 100, "stock": 5},
    ]
    categories = [
        {"id": 10, "name": "Streaming", "icon": "🎬"},
        {"id": 20, "name": "VPN", "icon": "🛡️"},
    ]
    # All products active
    kb = get_products_keyboard(products=products, categories=categories, category_id=None, lang="en")
    chip_row = kb.inline_keyboard[0]
    assert [btn.text for btn in chip_row] == ["✅ All", "🎬 Streaming", "🛡️ VPN"]
    assert [btn.callback_data for btn in chip_row] == ["shop_p_all_1", "cat_10", "cat_20"]
    assert kb.inline_keyboard[1][0].text.startswith("Canva Pro")

    # Specific category active (VPN)
    kb_cat = get_products_keyboard(products=products, categories=categories, category_id=20, lang="en")
    chip_row_cat = kb_cat.inline_keyboard[0]
    assert [btn.text for btn in chip_row_cat] == ["All", "🎬 Streaming", "✅ VPN"]


@pytest.mark.asyncio
async def test_payment_done_edits_card_in_place_without_force_reply():
    state = context()
    await state.set_state(DepositStates.method_selected)
    await state.set_data({"method_id": 3, "method_name": "bKash", "card_msg_id": 1, "account_info": "01700000000"})
    message = customer()
    query = SimpleNamespace(data="dep_paid_3", message=message, from_user=message.from_user, answer=AsyncMock())
    await begin_payment_reference(query, state, services())
    message.edit_text.assert_awaited_once()
    edit_args, edit_kwargs = message.edit_text.await_args
    assert "bKash" in edit_args[0]
    assert "01700000000" in edit_args[0]
    assert "Transaction ID" in edit_args[0]
    assert await state.get_state() == DepositStates.waiting_for_txid.state
    # A second tap must not reset the state or edit again.
    await begin_payment_reference(query, state, services())
    assert message.edit_text.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("selected,active_state,available,pending", [
    (4, DepositStates.method_selected, True, None),
    (3, None, True, None),
    (3, DepositStates.waiting_for_amount, True, None),
    (3, DepositStates.method_selected, False, None),
    (3, DepositStates.method_selected, True, {"id": 19}),
])
async def test_stale_payment_buttons_never_start_or_reset_a_payment(selected, active_state, available, pending):
    state = context()
    await state.set_state(active_state)
    await state.set_data({"method_id": selected, "method_name": "bKash", "manual_txid": "KEEP_THIS"})
    before = await state.get_data()
    message = customer()
    query = SimpleNamespace(data="dep_paid_3", message=message, from_user=message.from_user, answer=AsyncMock())
    svc = services()
    svc.deposits.get_method.return_value = {"id": 3, "is_active": available}
    svc.deposits.pending_for.return_value = pending
    await begin_payment_reference(query, state, svc)
    message.answer.assert_not_awaited()
    assert await state.get_data() == before
    query.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_reference_is_retained_for_the_required_amount_then_submitted_once():
    state = context()
    await state.set_state(DepositStates.waiting_for_txid)
    await state.set_data({
        "method_id": 3, "method_name": "bKash", "reference_first": True,
        "min_deposit": 50, "rate": 125, "manual_amount": None,
    })
    message = customer()
    svc = services()
    with patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit:
        await process_deposit_txid(message, state, svc)
        submit.assert_not_awaited()
        assert (await state.get_data())["manual_txid"] == "BK123456"
        assert await state.get_state() == DepositStates.waiting_for_amount.state
        assert "Enter the amount you sent in BDT, e.g. 50." in message.answer.await_args.args[0]
        assert isinstance(message.answer.await_args.kwargs["reply_markup"], InlineKeyboardMarkup)
        message.text = "100.50"
        await process_deposit_amount(message, state, svc)
        submit.assert_awaited_once_with(message, state, svc)
        data = await state.get_data()
        assert data["manual_txid"] == "BK123456"
        assert data["pay_amount"] == 100.50
        assert message.answer.await_count == 1  # No second TrxID or confirmation prompt.


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", ["-100", "1e3", "12.345", "0", "49", "125001", "9" * 400])
async def test_reference_first_flow_keeps_amount_validation_and_limits(amount):
    state = context()
    await state.set_state(DepositStates.waiting_for_amount)
    await state.set_data({
        "method_id": 3, "method_name": "bKash", "reference_first": True,
        "manual_txid": "BK123456", "min_deposit": 50, "rate": 125,
    })
    message = customer()
    message.text = amount
    with patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit:
        await process_deposit_amount(message, state, services())
        submit.assert_not_awaited()
    assert (await state.get_data())["manual_txid"] == "BK123456"
    assert await state.get_state() == DepositStates.waiting_for_amount.state
    assert isinstance(message.answer.await_args.kwargs["reply_markup"], InlineKeyboardMarkup)
