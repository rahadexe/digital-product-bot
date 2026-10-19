import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import CallbackQuery, Message, Chat, User
from app.bot.formatting import (
    respond,
    remember_menu_message,
    forget_menu_message,
    clean_previous_menu,
    _last_menu_messages,
)

@pytest.mark.asyncio
async def test_auto_clean_previous_message_on_new_command():
    # Setup chat and bot mocks
    chat = Chat(id=12345, type="private")
    bot = MagicMock()
    bot.delete_message = AsyncMock()

    # Message 1 (e.g. My Profile)
    sent_msg_1 = MagicMock(spec=Message)
    sent_msg_1.message_id = 101

    msg_1 = MagicMock(spec=Message)
    msg_1.chat = chat
    msg_1.bot = bot
    msg_1.message_id = 901
    msg_1.answer = AsyncMock(return_value=sent_msg_1)

    await respond(msg_1, "👤 My Profile")
    msg_1.answer.assert_called_once()

    import app.bot.formatting as fmt
    old_val = fmt.AUTO_DELETE_ENABLED
    fmt.AUTO_DELETE_ENABLED = True
    try:
        # clean_previous_menu handles explicit cleanups without jumping
        remember_menu_message(12345, 101)
        clean_previous_menu(bot, 12345, current_msg_id=102)
        await asyncio.sleep(0.01)
        bot.delete_message.assert_called_with(chat_id=12345, message_id=101)
    finally:
        fmt.AUTO_DELETE_ENABLED = old_val

@pytest.mark.asyncio
async def test_callback_query_edits_without_duplicate():
    chat = Chat(id=12345, type="private")
    bot = MagicMock()
    bot.delete_message = AsyncMock()

    inner_msg = MagicMock(spec=Message)
    inner_msg.chat = chat
    inner_msg.message_id = 102
    inner_msg.edit_text = AsyncMock()

    cb = MagicMock(spec=CallbackQuery)
    cb.message = inner_msg
    cb.answer = AsyncMock()

    await respond(cb, "📦 Order History")
    assert _last_menu_messages.get(12345) == 102
    inner_msg.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_render_main_dashboard_cleans_previous_and_deletes_trigger():
    chat = Chat(id=99999, type="private")
    bot = MagicMock()
    bot.delete_message = AsyncMock()

    # Pre-populate previous menu
    remember_menu_message(99999, 501)

    sent_msg = MagicMock(spec=Message)
    sent_msg.message_id = 502

    trigger_msg = MagicMock(spec=Message)
    trigger_msg.chat = chat
    trigger_msg.bot = bot
    trigger_msg.message_id = 777
    trigger_msg.text = "/start"
    trigger_msg.answer = AsyncMock(return_value=sent_msg)

    services = MagicMock()
    services.settings.values = AsyncMock(return_value={"store_name": "Store"})
    services.settings.paused_message = AsyncMock(return_value="")
    services.users.get = AsyncMock(return_value={"language": "en"})
    services.users.get_language = AsyncMock(return_value="en")
    services.catalog.pinned_categories = AsyncMock(return_value=[])
    services.catalog.categories = AsyncMock(return_value=[])
    services.catalog.unpinned_categories = AsyncMock(return_value=[])
    services.settings.admin_chat_ids = AsyncMock(return_value=set())

    import app.bot.formatting as fmt
    old_val = fmt.AUTO_DELETE_ENABLED
    fmt.AUTO_DELETE_ENABLED = True
    try:
        from app.bot.handlers.start import render_main_dashboard
        await render_main_dashboard(trigger_msg, services, 99999)

        assert _last_menu_messages.get(99999) == 502

        await asyncio.sleep(0.01)
        deleted_ids = [call.kwargs.get("message_id") for call in bot.delete_message.call_args_list]
        assert 501 in deleted_ids
        assert 777 in deleted_ids
    finally:
        fmt.AUTO_DELETE_ENABLED = old_val

