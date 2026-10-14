import base64
import hashlib
import unittest
from unittest.mock import AsyncMock, MagicMock

from cryptography.fernet import Fernet

from app.services.binance_credentials import BinanceCredentialsService
from app.services.binance import BinanceDepositService


class TestBinanceCredentials(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.secret_key = "a" * 32
        self.mock_db = MagicMock()
        self.service = BinanceCredentialsService(self.mock_db, self.secret_key)

    def test_cipher_valid(self):
        cipher = self.service._cipher()
        self.assertIsInstance(cipher, Fernet)
        msg = b"hello-binance-key"
        token = cipher.encrypt(msg)
        self.assertEqual(cipher.decrypt(token), msg)

    async def test_save_and_decrypt(self):
        saved_args = []

        class FakeConn:
            async def execute(self, query, *args):
                saved_args.extend(args)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        self.mock_db.connect.return_value = FakeConn()

        await self.service.save(42, "api_key_123", "api_secret_456")
        self.assertEqual(saved_args[0], 42)
        # Verify ciphertexts are not plaintext
        enc_key = saved_args[1]
        enc_secret = saved_args[2]
        self.assertNotEqual(enc_key, "api_key_123")
        self.assertNotEqual(enc_secret, "api_secret_456")

        # Now mock get
        class FakeGetConn:
            async def fetchrow(self, query, *args):
                return {
                    "api_key_encrypted": enc_key,
                    "api_secret_encrypted": enc_secret,
                }

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        self.mock_db.connect.return_value = FakeGetConn()
        creds = await self.service.get(42)
        self.assertIsNotNone(creds)
        self.assertEqual(creds["api_key"], "api_key_123")
        self.assertEqual(creds["api_secret"], "api_secret_456")

    async def test_credentials_isolation_for_methods(self):
        # Test BinanceDepositService resolving different credentials per method
        mock_cred_service = AsyncMock()
        mock_cred_service.get.side_effect = lambda m_id: {
            1: {"api_key": "KEY_1", "api_secret": "SEC_1"},
            2: {"api_key": "KEY_2", "api_secret": "SEC_2"},
        }.get(m_id)

        mock_settings = AsyncMock()
        mock_settings.get.return_value = ""

        binance_service = BinanceDepositService(
            db=MagicMock(),
            settings=mock_settings,
            deposits=MagicMock(),
            notifier=MagicMock(),
            config=MagicMock(binance_api_key="", binance_api_secret=""),
            binance_credentials=mock_cred_service,
        )

        key1, sec1 = await binance_service.get_credentials_for_method(1)
        key2, sec2 = await binance_service.get_credentials_for_method(2)
        key3, sec3 = await binance_service.get_credentials_for_method(3)

        self.assertEqual((key1, sec1), ("KEY_1", "SEC_1"))
        self.assertEqual((key2, sec2), ("KEY_2", "SEC_2"))
        self.assertEqual((key3, sec3), ("", ""))


if __name__ == "__main__":
    unittest.main()
