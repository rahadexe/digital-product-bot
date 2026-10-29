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
    assert [len(row) for row in keyboard.inline_keyboard] == [2, 2, 2]
    assert [[button.callback_data for button in row] for row in keyboard.inline_keyboard] == [
        ["adm_queue_dep", "adm_queue_ord"],
        ["adm_start_stock", "adm_start_settings"],
        ["adm_start_broadcast", "adm_toggle_pause"],
    ]
    assert keyboard.inline_keyboard[0][0].text == "💳 Deposits (1)"
    assert keyboard.inline_keyboard[0][1].text == "📦 Orders (2)"
    assert keyboard.inline_keyboard[1][0].text == "📋 Stock"
    assert keyboard.inline_keyboard[1][1].text == "⚙️ Settings"


@pytest.mark.asyncio
async def test_admin_set_banner_and_welcome_tagline():
    services = SimpleNamespace(
        settings=SimpleNamespace(
            admin_chat_ids=AsyncMock(return_value=[1]),
            update=AsyncMock(),
            get=AsyncMock(return_value=""),
        )
    )

    # 1. /setbanner with photo
    photo_obj = SimpleNamespace(file_id="AgACAgIAAxkBAAI...")
    msg_with_photo = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        text="/setbanner",
        caption=None,
        photo=[photo_obj],
        reply_to_message=None,
        reply=AsyncMock(),
    )
    await admin.adm_set_banner(msg_with_photo, services)
    services.settings.update.assert_awaited_with({"welcome_banner_file_id": "AgACAgIAAxkBAAI..."})
    assert "saved" in msg_with_photo.reply.call_args[0][0].lower()

    # 2. /setbanner clear
    msg_clear = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        text="/setbanner clear",
        caption=None,
        photo=None,
        reply_to_message=None,
        reply=AsyncMock(),
    )
    await admin.adm_set_banner(msg_clear, services)
    services.settings.update.assert_awaited_with({"welcome_banner_file_id": ""})

    # 3. Interactive photo upload via FSM state
    state = SimpleNamespace(clear=AsyncMock())
    msg_photo_upload = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        photo=[photo_obj],
        reply=AsyncMock(),
    )
    await admin.adm_receive_banner_photo(msg_photo_upload, state, services)
    services.settings.update.assert_awaited_with({"welcome_banner_file_id": "AgACAgIAAxkBAAI..."})
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_views_have_no_close_buttons_and_proper_back_navigation():
    """Verify that the admin panel contains NO 'Close' options and provides proper Back navigation."""
    services = SimpleNamespace(
        settings=SimpleNamespace(
            flag=AsyncMock(return_value=False),
            get=AsyncMock(return_value="৳"),
            values=AsyncMock(return_value={
                "store_name": "Test Store",
                "currency_symbol": "৳",
                "support_username": "testadmin",
                "store_paused": "0",
                "welcome_banner_file_id": "",
            }),
            number=AsyncMock(return_value=3),
        ),
        dashboard=SimpleNamespace(
            stats=AsyncMock(return_value={"stock_summary": [], "total_orders": 0, "total_revenue": 0, "total_users": 0}),
        ),
        delivery=SimpleNamespace(
            recent_broadcasts=AsyncMock(return_value=[]),
        ),
        db=SimpleNamespace(
            connect=lambda: _MockConn(),
        ),
        catalog=SimpleNamespace(
            products=AsyncMock(return_value=[]),
        ),
    )

    class _MockConn:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def fetchval(self, *args, **kwargs):
            return 0
        async def fetchrow(self, *args, **kwargs):
            return {"orders": 0, "revenue": 0}
        async def fetch(self, *args, **kwargs):
            return []

    # 1. Store Status View
    _, status_kb = await admin.build_store_status_view(services)
    status_cbs = [btn.callback_data for row in status_kb.inline_keyboard for btn in row]
    status_texts = [btn.text.lower() for row in status_kb.inline_keyboard for btn in row]
    assert "close_menu" not in status_cbs
    assert not any("close" in t for t in status_texts)
    assert "adm_dashboard" in status_cbs

    # 2. BC Status View
    _, bc_kb = await admin.build_bcstatus_view(services)
    bc_cbs = [btn.callback_data for row in bc_kb.inline_keyboard for btn in row]
    bc_texts = [btn.text.lower() for row in bc_kb.inline_keyboard for btn in row]
    assert "close_menu" not in bc_cbs
    assert not any("close" in t for t in bc_texts)
    assert "adm_dashboard" in bc_cbs

    # 3. Settings View
    _, set_kb = await admin.build_admin_settings_view(services)
    set_cbs = [btn.callback_data for row in set_kb.inline_keyboard for btn in row]
    set_texts = [btn.text.lower() for row in set_kb.inline_keyboard for btn in row]
    assert "close_menu" not in set_cbs
    assert not any("close" in t for t in set_texts)
    assert "adm_dashboard" in set_cbs

    # 4. Stock Overview View
    _, stock_kb = await admin.build_stock_overview_view(services, page=0)
    stock_cbs = [btn.callback_data for row in stock_kb.inline_keyboard for btn in row]
    stock_texts = [btn.text.lower() for row in stock_kb.inline_keyboard for btn in row]
    assert "close_menu" not in stock_cbs
    assert not any("close" in t for t in stock_texts)
    assert "adm_dashboard" in stock_cbs

    # 5. Queue Views
    for kind in ("deposits", "orders", "all"):
        _, q_kb = await admin.build_queue_view(services, kind=kind, page=0)
        q_cbs = [btn.callback_data for row in q_kb.inline_keyboard for btn in row]
        q_texts = [btn.text.lower() for row in q_kb.inline_keyboard for btn in row]
        assert "close_menu" not in q_cbs
        assert not any("close" in t for t in q_texts)
        assert "adm_dashboard" in q_cbs

