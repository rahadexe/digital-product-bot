from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.services.sms_parser import parse_mfs_sms


class TestSMSParser(unittest.TestCase):
    def test_parse_bkash_send_money(self):
        sms = "You have received Tk 500.00 from 01712345678. Ref . Fee Tk 0.00. Balance Tk 1,234.56. TrxID 9ABC123456 at 24/10/2026 18:30"
        parsed = parse_mfs_sms(sms, sender_hint="bKash")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["provider"], "bKash")
        self.assertEqual(parsed["transaction_id"], "9ABC123456")
        self.assertEqual(parsed["amount"], 500.0)
        self.assertEqual(parsed["sender_number"], "01712345678")

    def test_parse_bkash_deposit_variation(self):
        sms = "You have received deposit of Tk 1,500.00 from 01812345678. Fee Tk 0.00. Balance Tk 5,000.00. TrxID BAA123XYZ9 at 24/10/2026 19:00"
        parsed = parse_mfs_sms(sms)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["transaction_id"], "BAA123XYZ9")
        self.assertEqual(parsed["amount"], 1500.0)

    def test_parse_nagad_money_received(self):
        sms = "Money Received. Amount: Tk 300.00. Sender: 01812345678. TxnID: 7XYZ987654. Balance: Tk 2,500.00. 24/10/2026 18:32"
        parsed = parse_mfs_sms(sms, sender_hint="Nagad")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["provider"], "Nagad")
        self.assertEqual(parsed["transaction_id"], "7XYZ987654")
        self.assertEqual(parsed["amount"], 300.0)
        self.assertEqual(parsed["sender_number"], "01812345678")

    def test_parse_rocket(self):
        sms = "Tk 250.00 received from 01912345678. Balance Tk 500.00. TxnId: 1234567890"
        parsed = parse_mfs_sms(sms, sender_hint="16216")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["provider"], "Rocket")
        self.assertEqual(parsed["transaction_id"], "1234567890")
        self.assertEqual(parsed["amount"], 250.0)

    def test_parse_invalid(self):
        sms = "Dear customer, your internet pack has expired."
        self.assertIsNone(parse_mfs_sms(sms))


class TestSMSWebhookEndpoint(unittest.IsolatedAsyncioTestCase):
    def _build_mock_services(self, secret: str = ""):
        mock_services = MagicMock()
        mock_services.config.secret_key = "test-secret-key"
        mock_services.config.admin_password = "test-admin-password"
        mock_services.config.webapp_url = "https://example.com"
        mock_services.config.bot_token = "123:ABC"
        mock_services.config.webhook_secret = "test-webhook-secret"
        mock_services.config.allowed_hosts = "*"
        mock_services.rate_limits.consume = AsyncMock(return_value=0)
        mock_services.settings.get = AsyncMock(return_value=secret)
        return mock_services

    async def test_sms_webhook_records_transaction(self):
        mock_services = self._build_mock_services()
        mock_services.deposits.record_received_transaction = AsyncMock(return_value={"id": 1, "transaction_id": "9ABC123456"})

        app = create_app(mock_services)
        client = TestClient(app, base_url="http://localhost")

        # 1. Post raw SMS text
        res = client.post(
            "/api/payments/sms-webhook",
            headers={"x-webhook-secret": "test-webhook-secret"},
            json={
                "from": "bKash",
                "message": "You have received Tk 500.00 from 01712345678. TrxID 9ABC123456 at 24/10/2026",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("transaction_id"), "9ABC123456")
        self.assertEqual(data.get("amount"), 500.0)
        mock_services.deposits.record_received_transaction.assert_awaited_once_with(
            transaction_id="9ABC123456",
            amount=500.0,
            provider="bKash",
            sender_number="01712345678",
            raw_message="You have received Tk 500.00 from 01712345678. TrxID 9ABC123456 at 24/10/2026",
        )

    async def test_sms_webhook_authorization(self):
        # Configure a secret
        mock_services = self._build_mock_services(secret="super-secret-token")
        app = create_app(mock_services)
        client = TestClient(app, base_url="http://localhost")

        # Unauthorized request
        res = client.post(
            "/api/payments/sms-webhook",
            json={
                "trx_id": "9ABC123456",
                "amount": 500.0,
            },
        )
        self.assertEqual(res.status_code, 401)

        # Authorized with header
        mock_services.deposits.record_received_transaction = AsyncMock(return_value={"id": 1, "transaction_id": "9ABC123456"})
        res = client.post(
            "/api/payments/sms-webhook",
            headers={"x-webhook-secret": "super-secret-token"},
            json={
                "trx_id": "9ABC123456",
                "amount": 500.0,
                "provider": "bKash",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("ok"))

    async def test_zinipay_sms_webhook_event(self):
        mock_services = self._build_mock_services()
        mock_services.deposits.record_received_transaction = AsyncMock(return_value={"id": 2, "transaction_id": "DFR5QMLP41"})

        app = create_app(mock_services)
        client = TestClient(app, base_url="http://localhost")

        res = client.post(
            "/api/payments/zinipay/webhook",
            headers={"x-webhook-secret": "test-webhook-secret"},
            json={
                "event": "billing.payment_received",
                "amount": 750,
                "provider": "bKash",
                "transactionId": "DFR5QMLP41",
                "senderNumber": "01877778917",
                "message": "You have received Tk 750.00 from 01877778917. TrxID DFR5QMLP41",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("transaction_id"), "DFR5QMLP41")
        mock_services.deposits.record_received_transaction.assert_awaited_once_with(
            transaction_id="DFR5QMLP41",
            amount=750.0,
            provider="bKash",
            sender_number="01877778917",
            raw_message="You have received Tk 750.00 from 01877778917. TrxID DFR5QMLP41",
        )


class TestBotDepositWithStatementSync(unittest.IsolatedAsyncioTestCase):
    async def test_instant_trxid_deposit_when_statement_exists(self):
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.types import Chat, Message, User
        from app.bot.handlers.deposit import DepositStates, process_deposit_txid

        services = MagicMock()
        services.settings.number = AsyncMock(return_value=125)
        services.users.get_language = AsyncMock(return_value="en")
        services.users.get = AsyncMock(return_value={"id": 1, "balance": 901.0})
        services.deposits.get_method = AsyncMock(return_value={"id": 1, "name": "bKash", "is_active": 1, "auto_verify": "none", "min_deposit": 50})
        services.deposits.find_by_transaction = AsyncMock(return_value=None)
        services.deposits.pending_for = AsyncMock(return_value=None)
        services.deposits.verification_failures = AsyncMock(return_value=[])
        services.deposits.clear_verification_failures = AsyncMock()
        services.deposits.create_request = AsyncMock(return_value=123)
        services.deposits.approve = AsyncMock(return_value=(True, "", {"amount": 500.0, "new_balance": 901.0}))
        services.deposits.claim_received_transaction = AsyncMock(return_value=True)

        # Unused statement of 500 Tk exists for TrxID '9ABC123456'
        services.deposits.get_unused_received_transaction = AsyncMock(
            return_value={"id": 1, "transaction_id": "9ABC123456", "amount": 500.0, "provider": "bKash", "status": "unused"}
        )

        message = MagicMock(spec=Message)
        message.message_id = 999
        message.chat = Chat(id=6775546602, type="private")
        message.from_user = User(id=6775546602, is_bot=False, first_name="RAHAD", username="rahadhasanrafi")
        message.text = "9ABC123456"
        message.answer = AsyncMock()

        storage = MemoryStorage()
        state = FSMContext(storage=storage, key=MagicMock(user_id=6775546602, chat_id=6775546602))
        await state.set_state(DepositStates.waiting_for_txid)
        await state.update_data(method_id=1, method_name="bKash", reference_first=True)

        await process_deposit_txid(message, state, services)

        # Verified BDT 500 is converted to the canonical USD credit without asking for amount
        services.deposits.create_request.assert_awaited_once_with(
            tg_user_id=6775546602,
            method_id=1,
            amount=4.0,
            transaction_id="9ABC123456",
            pay_amount=500.0,
            quoted_rate=125.0,
            admin_note="Auto-verified via Instant Statement Sync",
            notify_admin=True,
        )
        services.deposits.approve.assert_awaited_once_with(
            123,
            admin_note="Auto-verified via Instant Statement Sync",
            notify_customer=False,
        )
        services.deposits.claim_received_transaction.assert_awaited_once_with(
            "9ABC123456", 6775546602, 123
        )
        # State cleared
        self.assertIsNone(await state.get_state())

    async def test_trxid_deposit_falls_back_to_asking_amount_when_no_statement(self):
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.types import Chat, Message, User
        from app.bot.handlers.deposit import DepositStates, process_deposit_txid

        services = MagicMock()
        services.users.get_language = AsyncMock(return_value="en")
        # No statement in DB yet
        services.deposits.get_unused_received_transaction = AsyncMock(return_value=None)

        message = MagicMock(spec=Message)
        message.message_id = 999
        message.chat = Chat(id=6775546602, type="private")
        message.from_user = User(id=6775546602, is_bot=False, first_name="RAHAD", username="rahadhasanrafi")
        message.text = "TXN999999"
        message.answer = AsyncMock()

        storage = MemoryStorage()
        state = FSMContext(storage=storage, key=MagicMock(user_id=6775546602, chat_id=6775546602))
        await state.set_state(DepositStates.waiting_for_txid)
        await state.update_data(method_id=1, method_name="bKash", reference_first=True, min_deposit=50)

        await process_deposit_txid(message, state, services)

        # State transitioned to waiting_for_amount
        self.assertEqual(await state.get_state(), DepositStates.waiting_for_amount.state)
        data = await state.get_data()
        self.assertEqual(data.get("manual_txid"), "TXN999999")

