"""Unit tests for interactive inline Balance History and Deposit Details."""

import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User

from app.bot.handlers.profile import show_deposit_history, view_deposit_detail


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
        self.assertIn("Balance History", text_arg)
        kb = kwargs["reply_markup"]
        self.assertIsInstance(kb, InlineKeyboardMarkup)

        # First row is deposit #101 (approved)
        row0 = kb.inline_keyboard[0]
        self.assertEqual(len(row0), 1)
        self.assertIn("#101", row0[0].text)
        self.assertEqual(row0[0].callback_data, "vdep_101_1_0")

        # Second row is deposit #102 (pending)
        row1 = kb.inline_keyboard[1]
        self.assertEqual(len(row1), 1)
        self.assertIn("#102", row1[0].text)
        self.assertEqual(row1[0].callback_data, "vdep_102_1_0")

        # Refresh button present
        all_texts = [btn.text for r in kb.inline_keyboard for btn in r]
        self.assertIn("Refresh", all_texts)
        self.assertIn("Add Balance", all_texts)
        self.assertIn("Back", all_texts)
        self.assertIn("Close", all_texts)

    async def test_view_deposit_detail(self):
        services = MagicMock()
        services.deposits.get_for_customer = AsyncMock(return_value={
            "id": 101,
            "method_name": "bKash Personal",
            "amount": 100.0,
            "status": "approved",
            "transaction_id": "BLX998877",
            "admin_note": None,
            "created_at": datetime(2026, 9, 22, 14, 0),
            "reviewed_at": datetime(2026, 9, 22, 14, 5),
        })
        services.settings.get = AsyncMock(return_value="৳")
        services.settings.number = AsyncMock(return_value=125.0)
        services.settings.flag = AsyncMock(return_value=True)

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
        self.assertIn("Deposit #101 Details", text_arg)
        self.assertIn("APPROVED", text_arg)
        self.assertIn("bKash Personal", text_arg)
        self.assertIn("BLX998877", text_arg)

        kb = kwargs["reply_markup"]
        all_cbs = [btn.callback_data for r in kb.inline_keyboard for btn in r]
        # Back button returns to page 2!
        self.assertIn("dep_page_2", all_cbs)
        self.assertIn("close_menu", all_cbs)
