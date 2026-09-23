import json
import os
import unittest
import uuid
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import asyncpg
import httpx

from app.api.app import create_app
from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services
from app.services.admin_jobs import enqueue
from app.workers.admin_notifications import AdminNotificationWorker

DSN = os.environ.get('TEST_DATABASE_URL', '')


@unittest.skipUnless(DSN, 'Requires disposable local PostgreSQL')
class AuditFixes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('localhost', '127.0.0.1', '::1'):
            raise RuntimeError('Local DB only')
        self.schema = 'audit_test_' + uuid.uuid4().hex
        self.db = Database(DSN, schema=self.schema, max_size=5)
        await migrate(self.db)
        self.s = build_services(
            Settings(_env_file=None, app_env='testing', database_url=DSN, admin_password='test-password', secret_key='x' * 48),
            db=self.db,
            use_telegram=False,
        )
        await self.s.users.sync_profile(100, first_name='Test')
        await self.s.users.adjust_balance(100, 100)

    async def asyncTearDown(self):
        await self.s.close()
        c = await asyncpg.connect(DSN)
        await c.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        await c.close()

    async def scalar(self, sql, *args):
        async with self.db.connect() as c:
            return await c.fetchval(sql, *args)

    async def test_purchase_job_atomic_idempotent_and_private(self):
        pid = await self.s.catalog.create_product(None, 'Manual', price=10, delivery_type='manual')
        for _ in range(2):
            ok, _, order = await self.s.purchases.purchase(100, pid, request_id='same')
            self.assertTrue(ok)
        self.assertEqual(await self.scalar('SELECT count(*) FROM admin_notification_jobs'), 1)
        payload = json.loads(await self.scalar('SELECT payload FROM admin_notification_jobs'))
        self.assertNotIn('delivered_item', payload['order'])
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 90)
        self.s.purchases._notify_admin = AsyncMock(side_effect=RuntimeError('offline'))
        worker = AdminNotificationWorker(self.s)
        await worker.step()
        self.assertEqual(await self.scalar('SELECT status FROM admin_notification_jobs'), 'pending')
        async with self.db.connect() as c:
            await c.execute("UPDATE admin_notification_jobs SET next_attempt=now()")
        self.s.purchases._notify_admin = AsyncMock()
        await worker.step()
        self.assertEqual(await self.scalar('SELECT status FROM admin_notification_jobs'), 'done')

    async def test_queue_rolls_back_with_transaction(self):
        with self.assertRaises(RuntimeError):
            async with self.db.transaction() as c:
                await enqueue(c, 'order', 1, {'dummy': True})
                raise RuntimeError('rollback')
        self.assertEqual(await self.scalar('SELECT count(*) FROM admin_notification_jobs'), 0)

    async def test_deposit_partial_delivery_retries_only_failed_recipient(self):
        await self.s.settings.update({'admin_tg_ids': '123456, 234567'})
        method = await self.s.deposits.create_method('Test', 'account')
        await self.s.deposits.create_request(100, method, 10, 'AUDIT123')
        self.s.notifier.bot = AsyncMock()
        self.s.notifier.send = AsyncMock(side_effect=[True, False])
        worker = AdminNotificationWorker(self.s)
        await worker.step()
        self.assertEqual(await self.scalar('SELECT count(*) FROM admin_notification_deliveries'), 1)
        async with self.db.connect() as c:
            await c.execute('UPDATE admin_notification_jobs SET next_attempt=now()')
        self.s.notifier.send = AsyncMock(return_value=True)
        await worker.step()
        self.s.notifier.send.assert_awaited_once()
        self.assertEqual(await self.scalar('SELECT status FROM admin_notification_jobs'), 'done')

    async def test_job_retry_requires_admin_and_csrf(self):
        async with self.db.connect() as c:
            await enqueue(c, 'order', 1, {})
            await c.execute("UPDATE admin_notification_jobs SET status='failed'")
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)), base_url='http://test') as client:
            self.assertEqual((await client.get('/api/admin/failed-jobs')).status_code, 401)
            login = await client.post('/api/admin/login', json={'password': 'test-password'})
            self.assertEqual(login.status_code, 200)
            self.assertEqual((await client.post('/api/admin/failed-jobs/notification/1/retry')).status_code, 403)
            response = await client.post(
                '/api/admin/failed-jobs/notification/1/retry', headers={'X-CSRF-Token': login.json()['csrf']}
            )
            self.assertEqual(response.status_code, 200)
            audit_actor = await self.scalar("SELECT actor FROM audit_logs WHERE action='job_retry' ORDER BY id DESC LIMIT 1")
            self.assertTrue(audit_actor.startswith('admin-session:'))
            self.assertEqual(
                (
                    await client.post(
                        '/api/admin/failed-jobs/notification/1/retry', headers={'X-CSRF-Token': login.json()['csrf']}
                    )
                ).status_code,
                409,
            )

    async def test_force_join_outage_is_distinct_and_does_not_poison_cache(self):
        from app.bot.handlers.start import gate_text

        self.s.gate.settings.flag = AsyncMock(return_value=True)
        channels = [{'channel_username': '@test', 'title': 'Test'}]
        self.s.gate.channels = AsyncMock(return_value=channels)
        self.s.notifier.is_member = AsyncMock(side_effect=RuntimeError('unavailable'))
        ok, missing = await self.s.gate.check(100)
        self.assertFalse(ok)
        self.assertIn('temporarily unavailable', gate_text(missing))
        self.assertNotIn('verification_unavailable', channels[0])

    async def test_automatic_deposit_has_delayed_restart_fallback(self):
        method = await self.s.deposits.create_method('Test', 'account')
        deposit = await self.s.deposits.create_request(100, method, 10, 'DELAY123', notify_admin=False)
        self.assertTrue(await self.scalar('SELECT next_attempt > now() FROM admin_notification_jobs'))
        await self.s.deposits.alert_admin_needs_review(deposit, 'Review needed')
        self.assertTrue(await self.scalar('SELECT next_attempt <= now() FROM admin_notification_jobs'))
        self.assertEqual(await self.scalar("SELECT payload->>'admin_note' FROM admin_notification_jobs"), 'Review needed')

    async def test_wallet_retry_is_idempotent(self):
        import asyncio

        await asyncio.gather(
            *(self.s.users.adjust_balance(100, 10, 'retry', operation_id='same-operation-123') for _ in range(5))
        )
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 110)
        from app.services.errors import InvalidInputError

        with self.assertRaises(InvalidInputError):
            await self.s.users.adjust_balance(100, 20, 'retry', operation_id='same-operation-123')

    async def test_stale_outbox_claim_cannot_overwrite_success(self):
        async with self.db.connect() as c:
            await c.execute("INSERT INTO outbox(tg_user_id,text) VALUES(100,'test')")
        first = await self.s.delivery.claim_next()
        async with self.db.connect() as c:
            await c.execute('UPDATE outbox SET next_attempt=0')
        second = await self.s.delivery.claim_next()
        await self.s.delivery.finish(second, 'sent', 0, '')
        await self.s.delivery.finish(first, 'pending', 10, 'stale')
        await self.s.delivery.cancel(first)
        self.assertEqual(await self.scalar('SELECT status FROM outbox'), 'sent')

    async def test_admin_retry_after_survives_long_cooldown(self):
        from aiogram.exceptions import TelegramRetryAfter
        from aiogram.methods import SendMessage

        pid = await self.s.catalog.create_product(None, 'Manual', price=10, delivery_type='manual')
        await self.s.purchases.purchase(100, pid, request_id='rate-limit')
        self.s.purchases._notify_admin = AsyncMock(
            side_effect=TelegramRetryAfter(method=SendMessage(chat_id=100, text='test'), message='wait', retry_after=300)
        )
        await AdminNotificationWorker(self.s).step()
        self.assertEqual(await self.scalar('SELECT status FROM admin_notification_jobs'), 'pending')
        self.assertEqual(await self.scalar('SELECT attempts FROM admin_notification_jobs'), 0)
        self.assertTrue(await self.scalar("SELECT next_attempt > now()+interval '290 seconds' FROM admin_notification_jobs"))
