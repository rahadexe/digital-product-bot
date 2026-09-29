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
    assert _last_menu_messages.get(12345) == 101

    # Allow background delete task to run
    await asyncio.sleep(0.01)
    # The user's incoming message 901 was deleted
    bot.delete_message.assert_called_with(chat_id=12345, message_id=901)

    # Message 2 (e.g. Refer & Earn)
    sent_msg_2 = MagicMock(spec=Message)
    sent_msg_2.message_id = 102

    msg_2 = MagicMock(spec=Message)
    msg_2.chat = chat
    msg_2.bot = bot
    msg_2.message_id = 902
    msg_2.answer = AsyncMock(return_value=sent_msg_2)

    await respond(msg_2, "🎁 Refer & Earn")
    assert _last_menu_messages.get(12345) == 102

    await asyncio.sleep(0.01)
    # Both old menu message (101) and incoming trigger (902) were deleted
    deleted_ids = [call.kwargs.get("message_id") for call in bot.delete_message.call_args_list]
    assert 101 in deleted_ids
    assert 902 in deleted_ids

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
