import unittest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from app.services.zinipay import _wallet_mismatch, _matches_receipt, ZiniPayVerificationService


class TestZiniPayHardening(unittest.IsolatedAsyncioTestCase):
    def test_wallet_mismatch_does_not_reject_missing_provider(self):
        # When gateway verifies payment but does not include provider key, do not treat as mismatch
        receipt_no_provider = {"id": 123, "amount": 500, "trxID": "BL123456"}
        self.assertIsNone(_wallet_mismatch("bKash Personal", receipt_no_provider))
        self.assertIsNone(_wallet_mismatch("Nagad", receipt_no_provider))

        # Real mismatch must still be detected
        receipt_nagad = {"id": 123, "amount": 500, "trxID": "BL123456", "provider": "Nagad"}
        self.assertEqual(_wallet_mismatch("bKash Personal", receipt_nagad), "nagad")

        # Same wallet must match
        receipt_bkash = {"id": 123, "amount": 500, "trxID": "BL123456", "provider": "bKash"}
        self.assertIsNone(_wallet_mismatch("bKash Personal", receipt_bkash))
        self.assertIsNone(_wallet_mismatch("বিকাশ (পার্সোনাল)", receipt_bkash))

        # Bengali method name mismatch
        self.assertEqual(_wallet_mismatch("নগদ (পার্সোনাল)", receipt_bkash), "bkash")

    def test_matches_receipt_trx_variations(self):
        self.assertTrue(_matches_receipt({"amount": 500, "trxId": "BL123456"}, 500.0, "bl123456"))
        self.assertTrue(_matches_receipt({"amount": 500, "trx_id": "BL123456"}, 500.0, "BL123456"))
        self.assertTrue(_matches_receipt({"amount": 500, "transaction_id": "BL123456"}, 500.0, "BL123456"))
        self.assertTrue(_matches_receipt({"data": {"amount": 500, "trxID": "BL123456"}}, 500.0, "BL123456"))
        self.assertFalse(_matches_receipt({"amount": 400, "trxID": "BL123456"}, 500.0, "BL123456"))
        # When amount is None (single TrxID verify probe)
        self.assertTrue(_matches_receipt({"amount": 500, "trxID": "BL123456"}, None, "BL123456"))
        self.assertFalse(_matches_receipt({"trxID": "BL123456"}, None, "BL123456"))

    async def test_env_api_key_enables_zinipay(self):
        db = MagicMock()
        db.connect = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)
        db.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        db.connect.return_value.__aexit__ = AsyncMock(return_value=None)
        settings = MagicMock()
        settings.get = AsyncMock(return_value="")
        settings.flag = AsyncMock(return_value=False)
        deposits = MagicMock()
        notifier = MagicMock()
        config = MagicMock()
        config.zinipay_api_key = "test_env_key"

        service = ZiniPayVerificationService(db, settings, deposits, notifier, config)
        self.assertTrue(await service.is_enabled())

    def test_format_deposit_status_card_accepts_error_note(self):
        from app.bot.handlers.deposit import format_deposit_status_card
        card = format_deposit_status_card(
            dep_id=99,
            method_name="bKash",
            amount_str="100 ৳",
            txid="BL123456",
            status="pending",
            lang="bn",
            error_note="ZiniPay gateway error details",
        )
        self.assertIn("ZiniPay gateway error details", card)
        self.assertIn("BL123456", card)

    async def test_execute_deposit_submission_no_unbound_local_status_msg(self):
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
        from aiogram.types import Message, User, Chat
        from app.bot.handlers.deposit import execute_deposit_submission, DepositStates

        storage = MemoryStorage()
        key = StorageKey(bot_id=1, chat_id=100, user_id=200)
        state = FSMContext(storage=storage, key=key)
        await state.set_state(DepositStates.waiting_for_amount)
        await state.set_data({
            "method_id": 1,
            "method_name": "bKash",
            "manual_amount": 0.8,
            "pay_amount": 100.0,
            "manual_txid": "BL123456",
            "rate": 125.0,
            "card_msg_id": 50,
            "card_chat_id": 100,
        })

        mock_services = MagicMock()
        mock_services.settings.number = AsyncMock(return_value=125)
        mock_services.users.get_language = AsyncMock(return_value="bn")
        mock_services.users.get = AsyncMock(return_value={"id": 1, "balance": 50.0})
        # Mock active pending deposit with matching TrxID
        mock_services.deposits.pending_for = AsyncMock(return_value={
            "id": 88,
            "transaction_id": "BL123456",
            "amount": 0.8,
            "status": "pending",
        })
        mock_services.deposits.clear_verification_failures = AsyncMock()
        mock_services.zinipay.is_enabled = AsyncMock(return_value=True)
        # _finish_awaiting returns True (successfully credited)
        mock_services.zinipay._finish_awaiting = AsyncMock(return_value=True)

        user = User(id=200, is_bot=False, first_name="Rahad")
        chat = Chat(id=100, type="private")
        msg = MagicMock(spec=Message)
        msg.from_user = user
        msg.chat = chat
        msg.message_id = 999
        msg.answer = AsyncMock()
        bot = MagicMock()
        bot.edit_message_text = AsyncMock()
        bot.delete_message = AsyncMock()
        msg.bot = bot

        # Must execute cleanly without UnboundLocalError
        await execute_deposit_submission(msg, state, mock_services)
        self.assertTrue(mock_services.zinipay._finish_awaiting.called)

