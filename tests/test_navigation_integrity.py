from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, User

from app.bot.handlers.deposit import show_deposit_methods
from app.bot.handlers.profile import show_order_history, view_order_detail
from app.bot.handlers.shop import (
    adjust_quantity,
    handle_keypad_action,
    show_order_buy_again,
    show_product_detail_paginated,
)
from app.bot.keyboards import get_products_keyboard


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
        data="prod_bo_15_1001_2_1",
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
    # Returns back to the order detail on page 2 originating from account
    assert back_buttons[0].callback_data == "vord_1001_2_1"


@pytest.mark.asyncio
async def test_order_detail_from_account_page_2_back_target():
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        data="vord_1001_2_1",
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
    assert back_buttons[0].callback_data == "orders_acc_page_2"


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

    assert PAGE_SIZE == 12

    mock_products = [
        {"id": i, "title": f"Product {i}", "price": 10.0 + i, "is_active": True, "category_id": 1, "stock": 5}
        for i in range(1, 16)
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
    # Product buttons on page 1 should be exactly 12
    prod_buttons = [btn for row in kb.inline_keyboard for btn in row if btn.callback_data.startswith("prod_p_")]
    assert len(prod_buttons) == 12

    # Test page 2 has remaining 3 products
    query.data = "shop_p_1_2"
    await paginate_products(query, state, services)
    kb_page_2 = query.message.edit_text.call_args.kwargs["reply_markup"]
    prod_buttons_2 = [btn for row in kb_page_2.inline_keyboard for btn in row if btn.callback_data.startswith("prod_p_")]
    assert len(prod_buttons_2) == 3

