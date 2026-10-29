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

    def test_matches_receipt_trx_variations(self):
        self.assertTrue(_matches_receipt({"amount": 500, "trxId": "BL123456"}, 500.0, "bl123456"))
        self.assertTrue(_matches_receipt({"amount": 500, "trx_id": "BL123456"}, 500.0, "BL123456"))
        self.assertTrue(_matches_receipt({"amount": 500, "transaction_id": "BL123456"}, 500.0, "BL123456"))
        self.assertFalse(_matches_receipt({"amount": 400, "trxID": "BL123456"}, 500.0, "BL123456"))

    async def test_env_api_key_enables_zinipay(self):
        db = MagicMock()
        settings = MagicMock()
        settings.get = AsyncMock(return_value="")
        settings.flag = AsyncMock(return_value=False)
        deposits = MagicMock()
        notifier = MagicMock()
        config = MagicMock()
        config.zinipay_api_key = "test_env_key"

        service = ZiniPayVerificationService(db, settings, deposits, notifier, config)
        self.assertTrue(await service.is_enabled())
