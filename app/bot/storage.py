"""Durable conversation state when Redis is not configured."""

import json
from collections.abc import Mapping
from typing import Any

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, DefaultKeyBuilder, StorageKey

from app.db import Database


class PostgresStorage(BaseStorage):
    def __init__(self, db: Database):
        self.db = db
        self.keys = DefaultKeyBuilder(with_bot_id=True, with_business_connection_id=True, with_destiny=True)

    async def set_state(self, key: StorageKey, state=None) -> None:
        value = state.state if isinstance(state, State) else state
        async with self.db.connect() as conn:
            await conn.execute(
                "INSERT INTO bot_conversations(key,state) VALUES($1,$2) ON CONFLICT(key) "
                "DO UPDATE SET state=EXCLUDED.state,updated_at=now()", self.keys.build(key), value,
            )

    async def get_state(self, key: StorageKey) -> str | None:
        async with self.db.connect() as conn:
            return await conn.fetchval("SELECT state FROM bot_conversations WHERE key=$1", self.keys.build(key))

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        async with self.db.connect() as conn:
            await conn.execute(
                "INSERT INTO bot_conversations(key,data) VALUES($1,$2::jsonb) ON CONFLICT(key) "
                "DO UPDATE SET data=EXCLUDED.data,updated_at=now()", self.keys.build(key), json.dumps(dict(data)),
            )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self.db.connect() as conn:
            raw = await conn.fetchval("SELECT data FROM bot_conversations WHERE key=$1", self.keys.build(key))
        return json.loads(raw) if raw else {}

    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        async with self.db.connect() as conn:
            raw = await conn.fetchval(
                "INSERT INTO bot_conversations(key,data) VALUES($1,$2::jsonb) ON CONFLICT(key) "
                "DO UPDATE SET data=bot_conversations.data || EXCLUDED.data,updated_at=now() RETURNING data",
                self.keys.build(key), json.dumps(dict(data)),
            )
        return json.loads(raw)

    async def close(self) -> None:
        pass  # The application owns the shared database pool.
