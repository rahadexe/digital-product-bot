"""Unit tests for interactive inline Balance History and Deposit Details."""

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User

from app.bot.handlers.profile import (
    show_deposit_history,
    show_order_history,
    view_deposit_detail,
    view_order_detail,
)


class BalanceHistoryUITests(unittest.IsolatedAsyncioTestCase):
    async def test_balance_history_renders_inline_buttons(self):
        services = MagicMock()
        services.deposits.count_for_user = AsyncMock(return_value=2)
        services.deposits.history = AsyncMock(return_value=[
            {
                "id": 101,
                "method_name": "bKash Personal",
                "amount": 100.0,
                "status": "approved",
                "transaction_id": "TRX101",
                "admin_note": None,
                "created_at": datetime(2026, 9, 22, 14, 0),
                "reviewed_at": datetime(2026, 9, 22, 14, 5),
            },
            {
                "id": 102,
                "method_name": "Nagad",
                "amount": 50.0,
                "status": "pending",
                "transaction_id": "TRX102",
                "admin_note": None,
                "created_at": datetime(2026, 9, 22, 14, 10),
                "reviewed_at": None,
            },
        ])
        services.settings.get = AsyncMock(return_value="৳")
        services.settings.number = AsyncMock(return_value=125.0)
        services.settings.flag = AsyncMock(return_value=True)
        services.users.get_language = AsyncMock(return_value="en")

        user = User(id=12345, is_bot=False, first_name="Test")
        query = MagicMock(spec=CallbackQuery)
        query.from_user = user
        query.data = "open_deposits"
        query.message = MagicMock(spec=Message)
        query.message.edit_text = AsyncMock()
        query.answer = AsyncMock()

        state = MagicMock(spec=FSMContext)
        state.clear = AsyncMock()

        await show_deposit_history(query, state, services)

        query.message.edit_text.assert_called_once()
        text_arg, kwargs = query.message.edit_text.call_args[0][0], query.message.edit_text.call_args[1]
        self.assertIn("Deposit History", text_arg)
        self.assertNotIn("TRX101", text_arg)
        self.assertNotIn("TRX102", text_arg)

        kb = kwargs["reply_markup"]
        self.assertIsInstance(kb, InlineKeyboardMarkup)

        all_texts = [btn.text for r in kb.inline_keyboard for btn in r]
        all_cbs = [btn.callback_data for r in kb.inline_keyboard for btn in r if btn.callback_data]
        self.assertIn("✅ bKash Personal · $0.80 · D101", all_texts)
        self.assertIn("⏳ Nagad · $0.40 · D102", all_texts)
        self.assertIn("vdep_101_1_0", all_cbs)
        self.assertIn("vdep_102_1_0", all_cbs)
        self.assertFalse(any("Add Balance" in t for t in all_texts))
        self.assertNotIn("open_deposit_from_history", all_cbs)

        # Refresh and Back present; Back button returns strictly to open_deposit (wallet)
        self.assertTrue(any("Refresh" in t or "🔄" in t for t in all_texts))
        self.assertTrue(any("Back" in t for t in all_texts))
        self.assertIn("open_deposit", all_cbs)
        self.assertNotIn("open_account", all_cbs)
        self.assertFalse(any("Close" in t for t in all_texts))

    async def test_view_deposit_detail(self):
        services = MagicMock()
        services.deposits.get_for_customer = AsyncMock(return_value={
            "id": 101,
            "method_name": "bKash Personal",
            "amount": 100.0,
            "status": "rejected",
            "transaction_id": "BLX998877",
            "admin_note": "Transaction could not be verified.",
            "created_at": datetime(2026, 9, 22, 14, 0),
            "reviewed_at": datetime(2026, 9, 22, 14, 5),
        })
        services.settings.get = AsyncMock(return_value="৳")
        services.settings.number = AsyncMock(return_value=125.0)
        services.settings.flag = AsyncMock(return_value=True)
        services.users.get_language = AsyncMock(return_value="en")

        user = User(id=12345, is_bot=False, first_name="Test")
        query = MagicMock(spec=CallbackQuery)
        query.from_user = user
        query.data = "vdep_101_2_0"
        query.message = MagicMock(spec=Message)
        query.message.edit_text = AsyncMock()
        query.answer = AsyncMock()

        state = MagicMock(spec=FSMContext)
        state.clear = AsyncMock()

        await view_deposit_detail(query, state, services)

        services.deposits.get_for_customer.assert_called_once_with(12345, 101)
        query.message.edit_text.assert_called_once()
        text_arg, kwargs = query.message.edit_text.call_args[0][0], query.message.edit_text.call_args[1]
        self.assertIn("<b>Top-up D101</b>", text_arg)
        self.assertIn("<b>Rejected</b> ❌", text_arg)
        self.assertIn("<i>Transaction could not be verified.</i>", text_arg)
        self.assertIn("bKash Personal", text_arg)
        self.assertIn("BLX998877", text_arg)
        self.assertNotIn("#101", text_arg)
        self.assertNotIn("✅", text_arg)
        self.assertNotIn("📝", text_arg)
        self.assertIn("Submitted:</b> 22 Sep 2026 · 14:00", text_arg)
        self.assertIn("Reviewed:</b> 22 Sep 2026 · 14:05", text_arg)

        kb = kwargs["reply_markup"]
        all_cbs = [btn.callback_data for r in kb.inline_keyboard for btn in r]
        # Back button returns to page 2 with wallet context preserved!
        self.assertIn("dep_page_2_w", all_cbs)
        self.assertEqual(all_cbs, ["dep_page_2_w"])
        self.assertNotIn("open_deposit_from_history", all_cbs)
        self.assertNotIn("close_menu", all_cbs)

    async def test_approved_deposit_detail_shows_check_after_status(self):
        services = MagicMock()
        services.deposits.get_for_customer = AsyncMock(return_value={
            "id": 102,
            "method_name": "Nagad",
            "amount": 50.0,
            "status": "approved",
            "transaction_id": "NG12345",
            "admin_note": None,
            "created_at": datetime(2026, 9, 22, 14, 0),
            "reviewed_at": datetime(2026, 9, 22, 14, 5),
        })
        services.settings.get = AsyncMock(return_value="৳")
        services.settings.number = AsyncMock(return_value=125.0)
        services.settings.flag = AsyncMock(return_value=True)
        services.users.get_language = AsyncMock(return_value="en")

        query = MagicMock(spec=CallbackQuery)
        query.from_user = User(id=12345, is_bot=False, first_name="Test")
        query.data = "vdep_102_1_0"
        query.message = MagicMock(spec=Message)
        query.message.edit_text = AsyncMock()
        query.answer = AsyncMock()

        state = MagicMock(spec=FSMContext)
        state.clear = AsyncMock()

        await view_deposit_detail(query, state, services)

        text_arg = query.message.edit_text.call_args.args[0]
        self.assertIn("<b>Approved</b> ✅", text_arg)
        self.assertNotIn("❌", text_arg)


class OrderHistoryUITests(unittest.IsolatedAsyncioTestCase):
    async def test_order_history_renders_consistent_layout(self):
        services = MagicMock()
        services.purchases.customer_orders = AsyncMock(return_value=([
            {
                "id": 501,
                "product_title": "Discord Nitro",
                "price": 420.0,
                "status": "completed",
                "fulfillment": "delivered",
                "delivered_item": "nitro-token-xyz",
                "created_at": datetime(2026, 9, 25, 12, 0),
            },
        ], 1))
        services.settings.get = AsyncMock(return_value="৳")
        services.settings.number = AsyncMock(return_value=125.0)
        services.settings.flag = AsyncMock(return_value=True)
        services.users.get_language = AsyncMock(return_value="en")

        user = User(id=12345, is_bot=False, first_name="Test")
        query = MagicMock(spec=CallbackQuery)
        query.from_user = user
        query.data = "open_orders"
        query.message = MagicMock(spec=Message)
        query.message.edit_text = AsyncMock()
        query.answer = AsyncMock()

        state = MagicMock(spec=FSMContext)
        state.clear = AsyncMock()

        await show_order_history(query, state, services)

        query.message.edit_text.assert_called_once()
        text_arg, kwargs = query.message.edit_text.call_args[0][0], query.message.edit_text.call_args[1]
        self.assertIn("Orders", text_arg)
        kb = kwargs["reply_markup"]
        self.assertIsInstance(kb, InlineKeyboardMarkup)

        row0 = kb.inline_keyboard[0]
        self.assertIn("Discord Nitro", row0[0].text)
        self.assertNotIn("#501", row0[0].text)
        self.assertTrue("✅" in row0[0].text or bool(row0[0].icon_custom_emoji_id))
        self.assertEqual(row0[0].callback_data, "vord_501_1")

        self.assertNotIn("•", text_arg)
        all_texts = [btn.text for r in kb.inline_keyboard for btn in r]
        self.assertTrue(any("Refresh" in t or "🔄" in t for t in all_texts))
        self.assertTrue(any("Back" in t for t in all_texts))
        self.assertFalse(any("Close" in t for t in all_texts))

    async def test_view_order_detail_preserves_page_and_shows_status(self):
        services = MagicMock()
        services.purchases.order_for_customer = AsyncMock(return_value={
            "id": 501,
            "product_title": "Discord Nitro",
            "price": 420.0,
            "status": "completed",
            "fulfillment": "delivered",
            "delivered_item": "nitro-token-xyz",
            "created_at": datetime(2026, 9, 25, 12, 0),
        })
        services.settings.get = AsyncMock(return_value="৳")
        services.settings.number = AsyncMock(return_value=125.0)
        services.settings.flag = AsyncMock(return_value=True)
        services.users.get_language = AsyncMock(return_value="en")

        user = User(id=12345, is_bot=False, first_name="Test")
        query = MagicMock(spec=CallbackQuery)
        query.from_user = user
        query.data = "vord_501_3"
        query.message = MagicMock(spec=Message)
        query.message.edit_text = AsyncMock()
        query.answer = AsyncMock()

        state = MagicMock(spec=FSMContext)
        state.clear = AsyncMock()

        await view_order_detail(query, state, services)

        services.purchases.order_for_customer.assert_called_once_with(12345, 501)
        query.message.edit_text.assert_called_once()
        text_arg, kwargs = query.message.edit_text.call_args[0][0], query.message.edit_text.call_args[1]
        self.assertIn("O501", text_arg)
        self.assertNotIn("#501", text_arg)
        self.assertIn("Delivered", text_arg)
        self.assertIn("nitro-token-xyz", text_arg)

        kb = kwargs["reply_markup"]
        all_cbs = [btn.callback_data for r in kb.inline_keyboard for btn in r]
        # Back button returns to page 3!
        self.assertIn("orders_page_3", all_cbs)
        self.assertNotIn("close_menu", all_cbs)
