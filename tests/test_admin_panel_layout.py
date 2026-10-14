from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

import pytest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove

from app.bot.handlers import admin


@pytest.mark.asyncio
async def test_admin_command_replaces_reply_keyboard_with_one_inline_panel():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Store Status", callback_data="adm_view_status")]]
    )
    panel_message = SimpleNamespace(message_id=42, edit_text=AsyncMock())
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        chat=SimpleNamespace(id=1),
        answer=AsyncMock(return_value=panel_message),
    )
    services = SimpleNamespace()

    with (
        patch.object(admin, "_is_admin", AsyncMock(return_value=True)),
        patch.object(admin, "build_admin_dashboard", AsyncMock(return_value=("Admin Panel", keyboard))),
    ):
        await admin.cmd_admin_help(message, state=None, services=services)

    message.answer.assert_awaited_once_with("Admin Panel", reply_markup=keyboard)
    assert admin._last_admin_panels[1] == 42
    admin._last_admin_panels.pop(1, None)


@pytest.mark.asyncio
async def test_admin_dashboard_groups_existing_controls_into_consistent_rows():
    services = SimpleNamespace(
        settings=SimpleNamespace(flag=AsyncMock(return_value=False)),
        dashboard=SimpleNamespace(
            stats=AsyncMock(return_value={"waiting_orders": 2, "pending_deposits": 1})
        ),
        reseller_applications=SimpleNamespace(count_applications=AsyncMock(return_value=3)),
    )

    text, keyboard = await admin.build_admin_dashboard(services)

    assert "Admin Panel" in text
    assert [len(row) for row in keyboard.inline_keyboard] == [2, 2, 2, 2, 1, 2]
    assert [[button.callback_data for button in row] for row in keyboard.inline_keyboard] == [
        ["adm_view_status", "adm_start_broadcast"],
        ["adm_queue_dep", "adm_queue_ord"],
        ["adm_start_stock", "adm_queue_reseller"],
        ["adm_start_find", "adm_start_settings"],
        ["adm_toggle_pause"],
        ["back_to_main", "close_menu"],
    ]
    assert keyboard.inline_keyboard[1][0].text == "Deposits (1)"
    assert keyboard.inline_keyboard[1][1].text == "Orders (2)"
    assert keyboard.inline_keyboard[2][1].text == "Reseller Apps (3)"
