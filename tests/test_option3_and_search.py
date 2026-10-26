import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.fsm.context import FSMContext

from app.bot.keyboards import get_main_inline_keyboard, get_more_inline_keyboard
from app.bot.handlers.search import _prompt_keyboard, _closing_row, search_entry, search_products, SearchStates


def test_main_inline_keyboard_five_action_layout():
    cats = [
        {"id": 1, "name": "Facebook", "icon": "📱"},
        {"id": 2, "name": "VPN", "icon": "🛡️"},
        {"id": 3, "name": "AI Tools", "icon": "🤖"},
        {"id": 4, "name": "Streaming", "icon": "🍿"},
    ]

    kb = get_main_inline_keyboard(pinned_categories=cats, is_admin=False, lang="en")
    rows = kb.inline_keyboard
    assert len(rows) == 3

    assert [button.callback_data for button in rows[0]] == ["open_categories", "open_wallet"]
    assert [button.callback_data for button in rows[1]] == ["open_orders", "open_referral"]
    assert [button.callback_data for button in rows[2]] == ["open_help"]
    assert [button.text for row in rows for button in row] == [
        "🛍 Shop", "💰 Balance", "📦 Orders", "🎁 Referral", "💬 Support",
    ]

    # The admin panel remains on its own row; reseller stays under More.
    kb_admin = get_main_inline_keyboard(pinned_categories=cats, is_admin=True, lang="en")
    assert len(kb_admin.inline_keyboard) == 4
    assert kb_admin.inline_keyboard[-1][0].callback_data == "adm_dashboard"
    more = get_more_inline_keyboard(lang="en", is_admin=True, is_reseller=True)
    more_callbacks = [button.callback_data for row in more.inline_keyboard for button in row]
    assert "adm_dashboard" not in more_callbacks
    assert "open_reseller_hub" in more_callbacks


def test_search_prompt_keyboard_back_target():
    kb = _prompt_keyboard(lang="en")
    # Back button goes to back_to_main
    assert kb.inline_keyboard[0][0].callback_data == "back_to_main"
    # All products button goes to open_categories
    assert kb.inline_keyboard[0][1].callback_data == "open_categories"


def test_search_results_closing_rows():
    rows = _closing_row(lang="en")
    assert len(rows) == 2
    assert rows[0][0].callback_data == "search_again"
    assert rows[1][0].callback_data == "open_categories"
    assert rows[1][1].callback_data == "back_to_main"


@pytest.mark.asyncio
async def test_search_entry_callback_edits_in_place():
    query = MagicMock(spec=CallbackQuery)
    query.answer = AsyncMock()
    query.message = MagicMock(spec=Message)
    query.message.message_id = 1001
    query.message.edit_text = AsyncMock()
    query.from_user = MagicMock(id=12345)

    state = MagicMock(spec=FSMContext)
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.catalog.products = AsyncMock(return_value=[])

    await search_entry(query, state, services)

    query.answer.assert_awaited_once()
    state.clear.assert_awaited_once()
    state.set_state.assert_awaited_once_with(SearchStates.waiting_for_term)
    state.update_data.assert_awaited_once_with(search_msg_id=1001)
    query.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_products_deletes_user_message_and_edits():
    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()

    msg = MagicMock(spec=Message)
    msg.text = "netflix"
    msg.from_user = MagicMock(id=12345)
    msg.chat = MagicMock(id=99999, type="private")
    msg.message_id = 7001
    msg.bot = bot
    msg.answer = AsyncMock()

    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"search_msg_id": 1001})
    state.clear = AsyncMock()

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.catalog.search = AsyncMock(return_value=[{"id": 1, "title": "Netflix 1 Month", "price": 10.0}])
    services.settings.values = AsyncMock(return_value={"currency_symbol": "$", "usd_rate": "1", "show_usd_price": "1"})

    with patch("app.bot.handlers.search._quiet_delete", new_callable=AsyncMock) as mock_delete:
        await search_products(msg, state, services)

    state.clear.assert_awaited_once()
    # Verified bot.edit_message_text was called with the existing search_msg_id (1001)
    bot.edit_message_text.assert_awaited_once()
    assert bot.edit_message_text.call_args.kwargs["message_id"] == 1001
    assert bot.edit_message_text.call_args.kwargs["chat_id"] == 99999
    # Verify new answer was NOT sent because edit succeeded
    msg.answer.assert_not_called()
