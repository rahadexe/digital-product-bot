from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.admin.catalog import _validate_custom_emoji
from app.api.admin.schemas import CategoryPayload, ProductPayload, ProductUpdatePayload
from app.bot.handlers.search import _product_button
from app.bot.handlers.shop import show_main_product_detail
from app.bot.icons import tg_icon
from app.bot.keyboards import (
    get_account_keyboard,
    get_categories_keyboard,
    get_categories_reply_keyboard,
    get_main_inline_keyboard,
    get_persistent_reply_keyboard,
    get_product_detail_keyboard,
    get_products_keyboard,
    get_quantity_selector_keyboard,
)


def test_persistent_reply_keyboard_compact_six_action_layout():
    cats = [
        {"id": 1, "name": "VPN", "icon": "🛡️"},
        {"id": 2, "name": "AI Tools", "icon": "🤖"},
    ]
    kb = get_persistent_reply_keyboard(pinned_categories=cats, is_admin=False, is_reseller=False, lang="bn")
    rows = kb.keyboard

    assert kb.is_persistent is False
    assert kb.resize_keyboard is True

    assert len(rows) == 3
    assert [[button.text for button in row] for row in rows] == [
        ["🛍 প্রোডাক্টস", "💰 ওয়ালেট"],
        ["📦 অর্ডারস", "🎁 রেফারেল"],
        ["👤 প্রোফাইল", "💬 হেল্প"],
    ]


def test_persistent_reply_keyboard_admin_and_reseller():
    cats = [
        {"id": 1, "name": "VPN", "icon": "🛡️"},
        {"id": 2, "name": "AI Tools", "icon": "🤖"},
    ]
    kb = get_persistent_reply_keyboard(pinned_categories=cats, is_admin=True, is_reseller=True, lang="en")
    rows = kb.keyboard

    # Three customer rows; operator tools stay role-restricted.
    assert len(rows) == 5
    assert "Reseller Panel" in rows[3][0].text
    assert "Admin Panel" in rows[4][0].text


def test_inline_keyboard_customer_first_bengali():
    cats = [
        {"id": 1, "name": "VPN", "icon": "🛡️"},
        {"id": 2, "name": "AI Tools", "icon": "🤖"},
    ]
    kb = get_main_inline_keyboard(pinned_categories=cats, is_admin=False, is_reseller=False, lang="bn")
    rows = kb.inline_keyboard

    assert len(rows) == 3
    assert [button.callback_data for button in rows[0]] == ["open_categories", "open_wallet"]
    assert [button.callback_data for button in rows[1]] == ["open_orders", "open_referral"]
    assert [button.callback_data for button in rows[2]] == ["open_account", "open_help"]
    assert [button.text for row in rows for button in row] == [
        "🛍 প্রোডাক্টস", "💰 ওয়ালেট", "📦 অর্ডারস", "🎁 রেফারেল", "👤 প্রোফাইল", "💬 হেল্প",
    ]


def test_six_button_grid_with_admin_and_reseller():
    cats = [
        {"id": 10, "name": "Streaming", "icon": "🎬"},
        {"id": 20, "name": "Facebook", "icon": "🌐"},
    ]
    kb = get_main_inline_keyboard(pinned_categories=cats, is_admin=True, is_reseller=True, lang="en")
    rows = kb.inline_keyboard

    assert len(rows) == 5
    assert [button.callback_data for button in rows[0]] == ["open_categories", "open_wallet"]
    assert [button.callback_data for button in rows[1]] == ["open_orders", "open_referral"]
    assert [button.callback_data for button in rows[2]] == ["open_account", "open_help"]
    assert rows[3][0].callback_data == "open_reseller_panel"
    assert rows[4][0].callback_data == "adm_dashboard"


def test_featured_products_do_not_expand_compact_main_menu():
    prods = [
        {"id": 101, "title": "ExpressVPN", "duration_label": "1 Month", "price": 60.0, "icon": "⚡"},
        {"id": 102, "title": "ChatGPT Plus", "duration_label": "", "price": 350.0, "icon": "🤖"},
    ]

    pinned = [{"id": 7, "name": "VPN", "icon": "🛡️"}]
    kb_bn = get_main_inline_keyboard(pinned_categories=pinned, featured_products=prods, is_admin=False, lang="bn")
    rows = kb_bn.inline_keyboard

    assert len(rows) == 3
    assert [button.callback_data for button in rows[0]] == ["open_categories", "open_wallet"]
    assert [button.callback_data for button in rows[1]] == ["open_orders", "open_referral"]
    assert [button.callback_data for button in rows[2]] == ["open_account", "open_help"]


def test_product_list_separates_validity_from_legacy_title():
    keyboard = get_products_keyboard(
        products=[
            {
                "id": 1,
                "title": "Netflix 30 Days",
                "duration_label": "30 Days",
                "warranty_label": "Full Warranty",
                "price": 250,
                "stock": 2,
            }
        ],
        currency_symbol="৳",
        show_usd=False,
        lang="bn",
    )

    assert keyboard.inline_keyboard[0][0].text == "Netflix · 30d (Full Warranty) · 250 ৳"


def test_product_list_extracts_legacy_validity_when_field_is_empty():
    keyboard = get_products_keyboard(
        products=[
            {"id": 2, "title": "YouTube Premium (1 Month)", "duration_label": "", "price": 320, "stock": 1}
        ],
        currency_symbol="৳",
        show_usd=False,
        lang="bn",
    )

    assert keyboard.inline_keyboard[0][0].text == "YouTube Premium · 1mo · 320 ৳"


def test_product_list_separates_legacy_warranty_from_product_name():
    keyboard = get_products_keyboard(
        products=[
            {
                "id": 3,
                "title": "ChatGPT Plus 30 Days (FW)",
                "duration_label": "30 Days",
                "price": 450,
                "stock": 1,
            }
        ],
        currency_symbol="৳",
        show_usd=False,
        lang="bn",
    )

    assert keyboard.inline_keyboard[0][0].text == "ChatGPT Plus · 30d (FW) · 450 ৳"


def test_product_warranty_is_optional_in_admin_payloads():
    created = ProductPayload(title="ChatGPT Plus", price=450, warranty_label="Full Warranty")
    updated = ProductUpdatePayload(warranty_label="7 Days Warranty")

    assert created.warranty_label == "Full Warranty"
    assert updated.warranty_label == "7 Days Warranty"


def test_catalog_payloads_require_exactly_one_icon_source():
    with pytest.raises(ValueError):
        CategoryPayload(name="VPN", icon="🌐", custom_emoji_id="5796345694969140339")
    with pytest.raises(ValueError):
        ProductPayload(title="VPN", price=60, icon="🌐", custom_emoji_id="5796345694969140339")
    with pytest.raises(ValueError):
        ProductUpdatePayload(icon="🌐", custom_emoji_id="5796345694969140339")
    with pytest.raises(ValueError):
        ProductPayload(title="VPN", price=60, custom_emoji_id="not-an-id")
    with pytest.raises(ValueError):
        CategoryPayload(name="VPN", icon="not an emoji")
    with pytest.raises(ValueError):
        ProductPayload(title="VPN", price=60, icon="\u200d")

    assert CategoryPayload(name="Empty").icon == ""
    assert ProductPayload(title="No icon", price=50).icon == ""


@pytest.mark.asyncio
async def test_premium_icon_id_is_verified_with_telegram_before_save():
    bot = SimpleNamespace(
        get_custom_emoji_stickers=AsyncMock(
            return_value=[SimpleNamespace(custom_emoji_id="5796345694969140339")]
        )
    )
    services = SimpleNamespace(notifier=SimpleNamespace(bot=bot))
    await _validate_custom_emoji(services, "5796345694969140339")
    bot.get_custom_emoji_stickers.assert_awaited_once_with(["5796345694969140339"])

    bot.get_custom_emoji_stickers.return_value = []
    with pytest.raises(HTTPException) as error:
        await _validate_custom_emoji(services, "1111111111111111111")
    assert error.value.status_code == 422


def test_category_buttons_render_only_the_selected_icon_type():
    keyboard = get_categories_keyboard(
        categories=[
            {"id": 1, "name": "Streaming", "icon": "🎬"},
            {"id": 2, "name": "AI Tools", "icon": "🌐", "custom_emoji_id": "5796345694969140339"},
            {"id": 3, "name": "Other", "icon": ""},
        ],
        show_all_option=False,
        back_target=None,
    )

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert buttons[0].text == "🎬 Streaming"
    assert buttons[0].icon_custom_emoji_id is None
    assert buttons[1].text == "AI Tools"
    assert buttons[1].icon_custom_emoji_id == "5796345694969140339"
    assert buttons[2].text == "Other"
    assert buttons[2].icon_custom_emoji_id is None


def test_category_reply_buttons_use_one_icon_and_leave_empty_icons_blank():
    keyboard = get_categories_reply_keyboard(
        categories=[
            {"id": 1, "name": "Streaming", "icon": "🎬"},
            {"id": 2, "name": "AI Tools", "custom_emoji_id": "5796345694969140339"},
            {"id": 3, "name": "Other", "icon": ""},
        ]
    )
    buttons = [button for row in keyboard.keyboard[:-1] for button in row]

    assert buttons[0].text == "🎬 Streaming"
    assert buttons[0].icon_custom_emoji_id is None
    assert buttons[1].text == "AI Tools"
    assert buttons[1].icon_custom_emoji_id == "5796345694969140339"
    assert buttons[2].text == "Other"
    assert buttons[2].icon_custom_emoji_id is None


def test_missing_catalog_icon_has_no_fallback_and_custom_ids_emit_no_text_glyph():
    assert tg_icon(None, "") == ""
    assert tg_icon(None, "🌐") == "🌐"
    assert tg_icon("5796345694969140339", "") == ""
    assert tg_icon("5796345694969140339", "🌐") == ""


def test_product_buttons_render_basic_or_custom_icon_without_duplicate_title_emoji():
    keyboard = get_products_keyboard(
        products=[
            {"id": 1, "title": "🌐 Netflix", "icon": "🌐", "price": 250, "stock": 1},
            {
                "id": 2,
                "title": "🤖 ChatGPT Plus",
                "icon": "🤖",
                "custom_emoji_id": "5796345694969140339",
                "price": 450,
                "stock": 1,
            },
            {"id": 3, "title": "Prime", "icon": "", "price": 100, "stock": 1},
        ],
        currency_symbol="৳",
        show_usd=False,
        lang="bn",
    )
    buttons = [row[0] for row in keyboard.inline_keyboard[:3]]

    assert buttons[0].text == "🌐 Netflix · 250 ৳"
    assert buttons[0].icon_custom_emoji_id is None
    assert buttons[1].text == "ChatGPT Plus · 450 ৳"
    assert buttons[1].icon_custom_emoji_id == "5796345694969140339"
    assert buttons[2].text == "Prime · 100 ৳"
    assert buttons[2].icon_custom_emoji_id is None


def test_search_product_button_does_not_add_fallback_and_preserves_custom_icon():
    missing_icon = _product_button(
        {"id": 3, "title": "Prime", "icon": "", "price": 100},
        "৳",
        None,
        False,
    )
    custom_icon = _product_button(
        {
            "id": 4,
            "title": "🤖 ChatGPT Plus",
            "icon": "",
            "custom_emoji_id": "5796345694969140339",
            "price": 200,
        },
        "৳",
        None,
        False,
    )

    assert missing_icon.text == "Prime · 100 ৳"
    assert missing_icon.icon_custom_emoji_id is None
    assert custom_icon.text == "ChatGPT Plus · 200 ৳"
    assert custom_icon.icon_custom_emoji_id == "5796345694969140339"

    detail_keyboard = get_quantity_selector_keyboard(
        product_id=4,
        quantity=1,
        unit_price=200,
        max_stock=1,
        user_balance=500,
        product_icon_custom_emoji_id="5796345694969140339",
    )
    buy_button = next(
        button
        for row in detail_keyboard.inline_keyboard
        for button in row
        if button.callback_data and button.callback_data.startswith("buy_qty_")
    )
    assert buy_button.icon_custom_emoji_id == "5796345694969140339"

    fallback_keyboard = get_product_detail_keyboard(
        product_id=4,
        category_id=1,
        has_stock=True,
        user_has_enough_balance=True,
        price=200,
        product_icon_custom_emoji_id="5796345694969140339",
    )
    fallback_buy_button = next(
        button
        for row in fallback_keyboard.inline_keyboard
        for button in row
        if button.callback_data and button.callback_data.startswith("buy_qty_")
    )
    assert fallback_buy_button.icon_custom_emoji_id == "5796345694969140339"


def test_long_warranty_label_does_not_hide_price_or_exceed_telegram_limit():
    keyboard = get_products_keyboard(
        products=[
            {
                "id": 4,
                "title": "Premium",
                "duration_label": "30 Days",
                "warranty_label": "A very long warranty description that should be shortened",
                "price": 450,
                "stock": 1,
            }
        ],
        currency_symbol="৳",
        show_usd=False,
        lang="bn",
    )

    label = keyboard.inline_keyboard[0][0].text
    assert label.startswith("Premium")
    assert label.endswith("450 ৳")
    assert len(label) <= 64


def test_top_products_dock_bengali_and_admin():
    prods = [
        {"id": 201, "title": "NordVPN", "duration_label": "1 Month", "price": 80.0, "icon": "🛡️"},
    ]

    pinned = [{"id": 8, "name": "Streaming", "icon": "🎬"}]
    kb = get_main_inline_keyboard(pinned_categories=pinned, featured_products=prods, is_admin=True, is_reseller=True, lang="bn")
    rows = kb.inline_keyboard

    assert len(rows) == 5
    assert [button.callback_data for button in rows[0]] == ["open_categories", "open_wallet"]
    assert [button.callback_data for button in rows[1]] == ["open_orders", "open_referral"]
    assert [button.callback_data for button in rows[2]] == ["open_account", "open_help"]
    assert rows[3][0].callback_data == "open_reseller_panel"
    assert rows[4][0].callback_data == "adm_dashboard"


def test_account_keyboard_clean_grid():
    kb = get_account_keyboard(lang="en")
    all_callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    assert "open_orders_acc" not in all_callbacks
    assert "open_referral" not in all_callbacks
    assert "open_api_hub" in all_callbacks
    assert "open_language_menu" not in all_callbacks
    assert "open_notifications_hub" in all_callbacks
    assert "back_to_main" in all_callbacks
    assert "open_deposits" not in all_callbacks
    assert "open_reseller" in all_callbacks
    assert len(kb.inline_keyboard) == 3


@pytest.mark.asyncio
async def test_main_product_click_sets_back_to_main():
    query = MagicMock()
    query.data = "prod_m_55"
    mock_user = MagicMock()
    mock_user.id = 12345
    query.from_user = mock_user
    query.answer = AsyncMock()

    state = AsyncMock()
    services = MagicMock()
    mock_prod = {
        "id": 55,
        "title": "Netflix Premium",
        "price": 120.0,
        "is_active": 1,
        "stock": 5,
        "category_id": 2,
    }
    services.catalog.product = AsyncMock(return_value=mock_prod)
    services.users.get = AsyncMock(return_value={"balance": 500.0, "language": "en"})
    services.settings.get = AsyncMock(return_value="৳")
    services.settings.number = AsyncMock(return_value=125.0)
    services.settings.flag = AsyncMock(return_value=False)
    services.notifier.bot_username = AsyncMock(return_value="testbot")

    with patch("app.bot.handlers.shop.respond", new_callable=AsyncMock) as mock_respond:
        await show_main_product_detail(query, state, services)
        assert mock_respond.called
        kb = mock_respond.call_args[0][2]
        # Back button in keyboard must navigate back to main menu
        back_btn = next((btn for row in kb.inline_keyboard for btn in row if btn.callback_data == "back_to_main"), None)
        assert back_btn is not None
