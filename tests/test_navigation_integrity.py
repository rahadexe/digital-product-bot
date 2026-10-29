from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery

from app.bot.handlers.deposit import show_deposit_methods
from app.bot.handlers.profile import view_order_detail
from app.bot.handlers.shop import (
    adjust_quantity,
    show_order_buy_again,
    show_product_detail_paginated,
)


@pytest.mark.asyncio
async def test_paginated_product_click_preserves_category_page_on_back():
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        data="prod_p_15_2_1",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )
    state = SimpleNamespace(
        clear=AsyncMock(),
        update_data=AsyncMock(),
        get_data=AsyncMock(return_value={}),
    )
    services = SimpleNamespace(
        catalog=SimpleNamespace(
            category=AsyncMock(return_value={"id": 1, "name": "VPN", "is_pinned": True, "has_validity_filter": 0}),
            product=AsyncMock(return_value={
                "id": 15,
                "title": "NordVPN 1 Month",
                "price": 100.0,
                "stock": 5,
                "is_active": True,
                "category_id": 1,
            }),
        ),
        users=SimpleNamespace(
            get=AsyncMock(return_value={"balance": 500.0, "rank": "Member"}),
            get_language=AsyncMock(return_value="en"),
        ),
        settings=SimpleNamespace(
            get=AsyncMock(return_value="৳"),
            number=AsyncMock(return_value=125.0),
            flag=AsyncMock(return_value=False),
        ),
        notifier=SimpleNamespace(bot_username=AsyncMock(return_value="sample_bot")),
    )

    with patch("app.bot.handlers.shop.respond", new_callable=AsyncMock) as mock_respond:
        await show_product_detail_paginated(query, state, services)

    assert mock_respond.called
    kb = mock_respond.call_args.args[2]
    # Check that Back button callback_data is shop_p_1_2 (Page 2 of Category 1)
    back_buttons = [btn for row in kb.inline_keyboard for btn in row if "Back" in btn.text]
    assert len(back_buttons) >= 1
    assert back_buttons[0].callback_data == "shop_p_1_2"


@pytest.mark.asyncio
async def test_quantity_adjustment_preserves_page_back_target():
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        data="qty_set_15_2",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )
    state = SimpleNamespace(
        clear=AsyncMock(),
        update_data=AsyncMock(),
        get_data=AsyncMock(return_value={"back_target_15": "shop_p_1_2"}),
    )
    services = SimpleNamespace(
        catalog=SimpleNamespace(
            product=AsyncMock(return_value={
                "id": 15,
                "title": "NordVPN 1 Month",
                "price": 100.0,
                "stock": 5,
                "is_active": True,
                "category_id": 1,
            }),
        ),
        users=SimpleNamespace(
            get=AsyncMock(return_value={"balance": 500.0, "rank": "Member"}),
            get_language=AsyncMock(return_value="en"),
        ),
        settings=SimpleNamespace(
            get=AsyncMock(return_value="৳"),
            number=AsyncMock(return_value=125.0),
            flag=AsyncMock(return_value=False),
        ),
        notifier=SimpleNamespace(bot_username=AsyncMock(return_value="sample_bot")),
    )

    await adjust_quantity(query, state, services)

    assert query.message.edit_text.called
    kb = query.message.edit_text.call_args.kwargs["reply_markup"]
    back_buttons = [btn for row in kb.inline_keyboard for btn in row if "Back" in btn.text]
    assert len(back_buttons) >= 1
    assert back_buttons[0].callback_data == "shop_p_1_2"


@pytest.mark.asyncio
async def test_order_buy_again_back_returns_to_exact_order():
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        data="prod_bo_15_1001_2",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )
    state = SimpleNamespace(
        clear=AsyncMock(),
        update_data=AsyncMock(),
        get_data=AsyncMock(return_value={}),
    )
    services = SimpleNamespace(
        catalog=SimpleNamespace(
            product=AsyncMock(return_value={
                "id": 15,
                "title": "NordVPN 1 Month",
                "price": 100.0,
                "stock": 5,
                "is_active": True,
                "category_id": 1,
            }),
        ),
        users=SimpleNamespace(
            get=AsyncMock(return_value={"balance": 500.0, "rank": "Member"}),
            get_language=AsyncMock(return_value="en"),
        ),
        settings=SimpleNamespace(
            get=AsyncMock(return_value="৳"),
            number=AsyncMock(return_value=125.0),
            flag=AsyncMock(return_value=False),
        ),
        notifier=SimpleNamespace(bot_username=AsyncMock(return_value="sample_bot")),
    )

    with patch("app.bot.handlers.shop.respond", new_callable=AsyncMock) as mock_respond:
        await show_order_buy_again(query, state, services)

    assert mock_respond.called
    kb = mock_respond.call_args.args[2]
    back_buttons = [btn for row in kb.inline_keyboard for btn in row if "Back" in btn.text]
    assert len(back_buttons) >= 1
    # Returns to the order detail on page 2 from Orders
    assert back_buttons[0].callback_data == "vord_1001_2"


@pytest.mark.asyncio
async def test_order_detail_page_2_back_target():
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        data="vord_1001_2",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )
    state = SimpleNamespace(clear=AsyncMock())
    services = SimpleNamespace(
        purchases=SimpleNamespace(
            order_for_customer=AsyncMock(return_value={
                "id": 1001,
                "product_title": "NordVPN",
                "price": 100.0,
                "status": "completed",
                "fulfillment": "delivered",
                "delivered_item": "user:pass",
                "created_at": datetime(2026, 10, 14, 12, 0),
                "product_id": 15,
            })
        ),
        users=SimpleNamespace(get_language=AsyncMock(return_value="en")),
        settings=SimpleNamespace(
            get=AsyncMock(return_value="৳"),
            number=AsyncMock(return_value=125.0),
            flag=AsyncMock(return_value=False),
        ),
    )

    await view_order_detail(query, state, services)

    assert query.message.edit_text.called
    kb = query.message.edit_text.call_args.kwargs["reply_markup"]
    back_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.text == "Back"]
    assert len(back_buttons) >= 1
    assert back_buttons[0].callback_data == "orders_page_2"


@pytest.mark.asyncio
async def test_product_shortfall_deposit_back_returns_to_product():
    query = MagicMock(spec=CallbackQuery)
    query.from_user = SimpleNamespace(id=123)
    query.data = "open_deposit_prod_42"
    query.answer = AsyncMock()
    query.message = SimpleNamespace(edit_text=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())
    services = SimpleNamespace(
        deposits=SimpleNamespace(
            pending_for=AsyncMock(return_value=None),
            methods=AsyncMock(return_value=[{"id": 1, "name": "bKash"}]),
        ),
        payments=SimpleNamespace(instant_options=AsyncMock(return_value=None)),
        users=SimpleNamespace(
            get=AsyncMock(return_value={"balance": 10.0}),
            get_language=AsyncMock(return_value="en"),
        ),
        settings=SimpleNamespace(
            get=AsyncMock(return_value="৳"),
            number=AsyncMock(return_value=125.0),
            flag=AsyncMock(return_value=False),
            paused_message=AsyncMock(return_value=None),
        ),
    )

    with patch("app.bot.handlers.deposit.respond", new_callable=AsyncMock) as mock_respond:
        await show_deposit_methods(query, state, services)

    assert mock_respond.called
    kb = mock_respond.call_args.args[2]
    back_buttons = [btn for row in kb.inline_keyboard for btn in row if "Back" in btn.text]
    assert len(back_buttons) >= 1
    assert back_buttons[0].callback_data == "prod_42"


@pytest.mark.asyncio
async def test_category_products_pagination_page_size_7():
    from app.bot.handlers.shop import PAGE_SIZE, paginate_products, show_products_list

    assert PAGE_SIZE == 16

    mock_products = [
        {"id": i, "title": f"Product {i}", "price": 10.0 + i, "is_active": True, "category_id": 1, "stock": 5}
        for i in range(1, 21)
    ]
    query = MagicMock(spec=CallbackQuery)
    query.from_user = SimpleNamespace(id=123)
    query.data = "shop_p_1_1"
    query.answer = AsyncMock()
    query.message = SimpleNamespace(edit_text=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())
    services = SimpleNamespace(
        catalog=SimpleNamespace(
            products=AsyncMock(return_value=mock_products),
            category=AsyncMock(return_value={"id": 1, "name": "VPN", "is_pinned": True, "has_validity_filter": 0}),
        ),
        users=SimpleNamespace(
            get=AsyncMock(return_value={"balance": 10.0}),
            get_language=AsyncMock(return_value="en"),
        ),
        settings=SimpleNamespace(
            get=AsyncMock(return_value="৳"),
            number=AsyncMock(return_value=125.0),
            flag=AsyncMock(return_value=False),
        ),
    )

    await paginate_products(query, state, services)

    assert query.message.edit_text.called
    kb = query.message.edit_text.call_args.kwargs["reply_markup"]
    # Product buttons on page 1 should be exactly 16
    prod_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.callback_data.startswith("prod_p_")]
    assert len(prod_buttons) == 16

    # Test page 2 has remaining 4 products
    query.data = "shop_p_1_2"
    await paginate_products(query, state, services)
    kb_page_2 = query.message.edit_text.call_args.kwargs["reply_markup"]
    prod_buttons_2 = [btn for row in kb_page_2.inline_keyboard for btn in row if btn.callback_data.startswith("prod_p_")]
    assert len(prod_buttons_2) == 4


def test_smart_credential_formatting_isolates_values_for_tap_to_copy():
    from app.services.delivery import format_credential_lines

    raw = "Email: buyer@example.com\nPassword: Secret#123\nPIN: 4455\nRAW-VOUCHER-CODE-999"
    formatted = format_credential_lines(raw)
    lines = formatted.splitlines()
    assert lines[0] == "Email: <code>buyer@example.com</code>"
    assert lines[1] == "Password: <code>Secret#123</code>"
    assert lines[2] == "PIN: <code>4455</code>"
    assert lines[3] == "<code>RAW-VOUCHER-CODE-999</code>"


def test_quantity_selector_and_category_overflow_and_gate_deeplink():
    from app.bot.keyboards import (
        get_gate_keyboard,
        get_products_keyboard,
        get_quantity_selector_keyboard,
    )

    qty_kb = get_quantity_selector_keyboard(
        product_id=77, quantity=2, max_stock=10, unit_price=5.0, user_balance=100.0
    )
    center_btn = qty_kb.inline_keyboard[0][1]
    assert center_btn.callback_data == "qty_custom_77"

    cats = [{"id": i, "name": f"Cat {i}"} for i in range(1, 8)]
    prods = [{"id": 1, "title": "Item 1", "price": 2.0, "stock": 3}]
    prod_kb = get_products_keyboard(prods, category_id=1, page=1, total_pages=1, categories=cats)
    chip_callbacks = [btn.callback_data for row in prod_kb.inline_keyboard for btn in row]
    assert "catpage_1" in chip_callbacks

    gate_kb = get_gate_keyboard([{"name": "News", "url": "https://t.me/test"}], product_id=42)
    verify_btn = gate_kb.inline_keyboard[-1][0]
    assert verify_btn.callback_data == "gate_verify_prod_42"


@pytest.mark.asyncio
async def test_shortfall_deposit_shows_bdt_needed_on_method_card():
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import Chat, Message, User
    from app.bot.handlers.deposit import render_method_details

    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=10, user_id=20))
    await state.update_data(target_prod_id=42)

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=20, is_bot=False, first_name="Buyer")
    msg.chat = Chat(id=10, type="private")
    msg.answer = AsyncMock()

    services = SimpleNamespace(
        deposits=SimpleNamespace(pending_for=AsyncMock(return_value=None)),
        users=SimpleNamespace(
            get_language=AsyncMock(return_value="en"),
            get=AsyncMock(return_value={"balance": 1.0}),
        ),
        settings=SimpleNamespace(
            get=AsyncMock(return_value="৳"),
            number=AsyncMock(return_value=125.0),
        ),
        catalog=SimpleNamespace(
            get_product=AsyncMock(return_value={"id": 42, "title": "Netflix", "price": 3.0}),
        ),
    )
    method = {
        "id": 1,
        "name": "bKash",
        "account_type": "personal",
        "account_info": "01700000000",
        "min_deposit": 50.0,
        "rate_to_currency": 125.0,
        "auto_verify": "none",
        "instructions": "",
    }

    await render_method_details(msg, state, services, method)
    rendered = msg.answer.call_args.args[0]
    assert "Amount needed: <b>250 ৳</b> ($2.00)" in rendered


