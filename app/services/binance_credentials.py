from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.db import Database

logger = logging.getLogger("app.services.binance_credentials")


class BinanceCredentialsService:
    def __init__(self, db: Database, secret_key: str):
        self.db = db
        self.secret_key = secret_key

    def _cipher(self) -> Fernet:
        raw = self.secret_key or "default-stable-secret-key-digital-products-bot-32chars"
        key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        return Fernet(key)

    def validate_encryption_key(self) -> None:
        self._cipher()

    async def save(self, method_id: int, api_key: str, api_secret: str) -> None:
        if not api_key or not api_secret:
            raise ValueError("Both Binance API Key and Secret are required.")
        cipher = self._cipher()
        enc_key = cipher.encrypt(api_key.strip().encode()).decode()
        enc_secret = cipher.encrypt(api_secret.strip().encode()).decode()
        async with self.db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO binance_method_credentials
                    (method_id, api_key_encrypted, api_secret_encrypted, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (method_id) DO UPDATE SET
                    api_key_encrypted = EXCLUDED.api_key_encrypted,
                    api_secret_encrypted = EXCLUDED.api_secret_encrypted,
                    updated_at = NOW()
                """,
                method_id,
                enc_key,
                enc_secret,
            )

    async def get(self, method_id: int) -> dict[str, str] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                SELECT api_key_encrypted, api_secret_encrypted
                FROM binance_method_credentials WHERE method_id = $1
                """,
                method_id,
            )
        if not row:
            return None
        cipher = self._cipher()
        try:
            return {
                "api_key": cipher.decrypt(row["api_key_encrypted"].encode()).decode(),
                "api_secret": cipher.decrypt(row["api_secret_encrypted"].encode()).decode(),
            }
        except InvalidToken:
            logger.error("Failed to decrypt Binance credentials for method_id=%s: InvalidToken", method_id)
            return None

    async def delete(self, method_id: int) -> None:
        async with self.db.connect() as conn:
            await conn.execute("DELETE FROM binance_method_credentials WHERE method_id = $1", method_id)

    async def has_credentials(self, method_id: int) -> bool:
        async with self.db.connect() as conn:
            return bool(
                await conn.fetchval(
                    "SELECT 1 FROM binance_method_credentials WHERE method_id = $1 LIMIT 1",
                    method_id,
                )
            )
