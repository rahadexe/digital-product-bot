"""Bounded, durable Telegram processing with per-customer ordering across replicas."""

import asyncio
import json
import logging
import uuid

from aiogram.types import Update

logger = logging.getLogger(__name__)


class TelegramInboxWorker:
    def __init__(self, services):
        self.services = services

    async def claim(self):
        async with self.services.db.connect() as conn:
            return await conn.fetchrow(
                "UPDATE telegram_inbox SET status='processing',attempts=attempts+1, "
                "next_attempt=now()+interval '120 seconds',lease_token=$1 WHERE update_id=("
                "SELECT i.update_id FROM telegram_inbox i WHERE i.status IN ('pending','processing') "
                "AND i.next_attempt<=now() AND NOT EXISTS (SELECT 1 FROM telegram_inbox earlier "
                "WHERE earlier.customer_id=i.customer_id AND earlier.update_id<>i.update_id "
                "AND (earlier.status='processing' OR (i.status='pending' AND earlier.update_id<i.update_id AND earlier.status='pending'))) "
                "ORDER BY i.update_id LIMIT 1 FOR UPDATE OF i SKIP LOCKED) RETURNING *", uuid.uuid4().hex,
            )

    async def step(self) -> bool:
        row = await self.claim()
        if not row:
            return False
        status, error, delay = 'done', '', 0
        try:
            update = Update.model_validate(json.loads(row['payload']), context={'bot': self.services.notifier.bot})
            async with asyncio.timeout(90):
                await self.services.runtime.dispatcher.feed_update(self.services.notifier.bot, update)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Telegram update %s failed", row['update_id'])
            status = 'failed' if row['attempts'] >= 5 else 'pending'
            error, delay = type(exc).__name__, min(60, 2 ** row['attempts'])
        async with self.services.db.connect() as conn:
            await conn.execute(
                "UPDATE telegram_inbox SET status=$3,error=$4,next_attempt=now()+$5*interval '1 second', "
                "payload=CASE WHEN $3='done' THEN '{}'::jsonb ELSE payload END "
                "WHERE update_id=$1 AND lease_token=$2", row['update_id'], row['lease_token'], status, error, delay,
            )
        return True

    async def consume(self) -> None:
        while True:
            try:
                if await self.step():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram inbox temporarily unavailable")
            try:
                await asyncio.wait_for(self.services.runtime.inbox_wake.wait(), timeout=1)
            except TimeoutError:
                pass
            self.services.runtime.inbox_wake.clear()

    async def run(self) -> None:
        workers = max(1, min(4, self.services.config.db_pool_size // 3))
        async with asyncio.TaskGroup() as group:
            for _ in range(workers):
                group.create_task(self.consume())
