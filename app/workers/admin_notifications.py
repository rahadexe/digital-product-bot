"""Restart-safe admin alerts. Partial sends can repeat; financial actions never replay."""
import asyncio
import json
import logging
import uuid

from aiogram.exceptions import TelegramRetryAfter

from app.services.admin_jobs import require_admin_delivery

logger = logging.getLogger(__name__)

class AdminNotificationWorker:
    def __init__(self, services):
        self.services = services

    async def step(self):
        async with self.services.db.connect() as conn:
            row = await conn.fetchrow(
                "UPDATE admin_notification_jobs SET status='processing',attempts=attempts+1,lease_token=$1,next_attempt=now()+interval '120 seconds' "
                "WHERE id=(SELECT id FROM admin_notification_jobs WHERE status IN ('pending','processing') AND next_attempt<=now() ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *", uuid.uuid4().hex)
        if not row:
            return False
        status, error = 'done', ''
        delay = min(300, 2 ** min(row['attempts'], 8))
        throttled = False
        token = require_admin_delivery.set(row['id'])
        try:
            data = json.loads(row['payload'])
            async with asyncio.timeout(90):
                if row['kind'] == 'order':
                    async with self.services.db.connect() as conn:
                        active = await conn.fetchval("SELECT 1 FROM orders WHERE id=$1 AND status='completed' AND (NOT $2::boolean OR fulfillment='waiting')", data['order']['order_id'], bool(data['reason']))
                    if not active:
                        data = None
                    if data:
                        await self.services.purchases._notify_admin(data['user'], data['order'], data['reason'])
                else:
                    async with self.services.db.connect() as conn:
                        pending = await conn.fetchval("SELECT 1 FROM deposits WHERE id=$1 AND status='pending'", data['deposit_id'])
                    if pending:
                        await self.services.deposits._notify_new_request(**data)
        except TelegramRetryAfter as exc:
            status, error, delay, throttled = 'pending', 'Telegram rate limit', exc.retry_after + 1, True
        except Exception as exc:
            status = 'failed' if row['attempts'] >= 5 else 'pending'
            error = type(exc).__name__
            logger.warning('Admin notification job %s failed: %s', row['id'], error)
        finally:
            require_admin_delivery.reset(token)
        async with self.services.db.connect() as conn:
            await conn.execute(
                "UPDATE admin_notification_jobs SET status=$3,error=$4,attempts=attempts-$6,next_attempt=now()+$5*interval '1 second',payload=CASE WHEN $3='done' THEN '{}'::jsonb ELSE payload END WHERE id=$1 AND lease_token=$2",
                row['id'], row['lease_token'], status, error, delay, int(throttled))
        return True

    async def run(self):
        while True:
            try:
                if await self.step():
                    continue
            except Exception:
                logger.exception('Admin notification queue unavailable')
            await asyncio.sleep(1)
