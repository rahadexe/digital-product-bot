"""Run with TEST_DATABASE_URL pointing at a disposable LOCAL PostgreSQL instance.

Every test owns a random schema. No application .env or real gateway is used.
"""

import asyncio
import os
import shutil
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

import asyncpg
import httpx
from aiogram.fsm.storage.base import StorageKey

from app.api.app import create_app
from app.bot.storage import PostgresStorage
from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services
from app.services.deposits import PendingDepositError
from app.services.errors import InvalidInputError
from app.workers.delivery import DeliveryWorker
from app.workers.telegram import TelegramInboxWorker

DSN = os.environ.get('TEST_DATABASE_URL', '')


@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('Integration tests refuse non-local databases')
        self.schema = 'test_' + uuid.uuid4().hex
        self.db = Database(DSN, schema=self.schema, max_size=10)
        await migrate(self.db)
        self.config = Settings(_env_file=None, app_env='testing', database_url=DSN,
                               bot_token='', admin_password='test-only-password', secret_key='t' * 48)
        self.s = build_services(self.config, db=self.db, use_telegram=False)
        await self.s.users.sync_profile(100, first_name='Test')
        await self.s.users.adjust_balance(100, 1000)
        self.product = await self.s.catalog.create_product(None, 'Test stock', price=10)
        self.method = await self.s.deposits.create_method('bKash', 'test-account')

    async def asyncTearDown(self):
        await self.s.close()
        conn = await asyncpg.connect(DSN)
        try:
            await conn.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        finally:
            await conn.close()

    async def scalar(self, sql, *args):
        async with self.db.connect() as conn:
            return await conn.fetchval(sql, *args)

    async def execute(self, sql, *args):
        async with self.db.connect() as conn:
            return await conn.execute(sql, *args)

    async def enable_zini(self):
        await self.s.settings.update({'zinipay_enabled': '1', 'zinipay_api_key': 'test-key'})
        # verify() hands back the gateway's receipt as 'raw'; it names the wallet.
        self.s.zinipay.verify = AsyncMock(return_value={'ok': True, 'id': 42, 'raw': {'provider': 'bKash'}})
        self.s.zinipay.confirm = AsyncMock(return_value={'ok': True, 'provider': 'bKash'})

    async def test_migrations_repeat_and_cleanup(self):
        self.assertEqual(await migrate(self.db), [])
        self.assertTrue(await self.scalar(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=$1 AND table_name='inventory_items' AND column_name='expires_at')",
            self.schema,
        ))
        for name in ('media_assets', 'home_banners', 'bot_welcome_banners', 'supplier_purchase_attempts'):
            self.assertIsNone(await self.scalar('SELECT to_regclass($1)', f'{self.schema}.{name}'))
        self.assertIsNone(await self.scalar('SELECT to_regclass($1)', f'{self.schema}.idx_orders_inventory_user'))
        self.assertTrue(await self.scalar("SELECT bool_and(checksum IS NOT NULL) FROM schema_migrations"))
        values = await self.s.settings.values()
        for name in ('supplier_api_url', 'supplier_api_key', 'notice_banner', 'referral_bonus_percent', 'custom_emojis'):
            self.assertNotIn(name, values)
        for changes in ({'currency': 'USD'}, {'zinipay_rate': '2'}):
            with self.assertRaises(InvalidInputError):
                await self.s.settings.update(changes)

    async def test_shared_stock_quantity_and_idempotency(self):
        await self.s.inventory.add_stock(self.product, ['shared-secret'], max_uses=7)
        result = await self.s.purchases.purchase(100, self.product, quantity=3, request_id='same-request')
        self.assertTrue(result[0], result)
        second = await self.s.purchases.purchase(100, self.product, quantity=3, request_id='same-request')
        self.assertEqual(result[2]['order_id'], second[2]['order_id'])
        self.assertEqual(await self.scalar('SELECT uses FROM inventory_items'), 3)
        self.assertEqual(await self.scalar('SELECT allocated_units FROM order_inventory_allocations'), 3)
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 970)
        mismatch = await self.s.purchases.purchase(100, self.product, quantity=2, request_id='same-request')
        self.assertFalse(mismatch[0])

    async def test_concurrent_purchase_never_oversells(self):
        await self.s.inventory.add_stock(self.product, ['one-key'])
        await self.s.users.sync_profile(200)
        await self.s.users.adjust_balance(200, 100)
        results = await asyncio.gather(
            self.s.purchases.purchase(100, self.product, request_id='first'),
            self.s.purchases.purchase(200, self.product, request_id='second'),
        )
        self.assertEqual(sum(result[0] for result in results), 1)
        self.assertEqual(await self.scalar('SELECT uses FROM inventory_items'), 1)
        self.assertEqual(await self.scalar('SELECT count(*) FROM orders'), 1)

    async def test_concurrent_upload_deduplicates(self):
        results = await asyncio.gather(*(self.s.inventory.add_stock(self.product, ['same-content']) for _ in range(5)))
        self.assertEqual(sum(row['added'] for row in results), 1)
        self.assertEqual(await self.scalar('SELECT count(*) FROM inventory_items'), 1)
        with self.assertRaises(asyncpg.UniqueViolationError):
            await self.execute("INSERT INTO inventory_items(product_id,content) VALUES($1,'same-content')", self.product)

    async def test_manual_delivery_and_refund_preserved(self):
        manual = await self.s.catalog.create_product(None, 'Manual subscription', price=25, delivery_type='manual')
        result = await self.s.purchases.purchase(100, manual, quantity=2, request_id='manual')
        self.assertTrue(result[0])
        self.assertEqual(result[2]['fulfillment'], 'waiting')
        await self.s.purchases.fulfill_manually(result[2]['order_id'], 'manual-credentials')
        self.assertEqual(await self.scalar('SELECT fulfillment FROM orders'), 'delivered')
        self.assertEqual(await self.scalar('SELECT count(*) FROM outbox'), 2)
        self.assertTrue((await self.s.purchases.refund(result[2]['order_id']))[0])
        self.assertFalse((await self.s.purchases.refund(result[2]['order_id']))[0])
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 1000)

    async def test_multi_item_history_survives_product_delete(self):
        await self.s.inventory.add_stock(self.product, ['a', 'b'])
        self.assertTrue((await self.s.purchases.purchase(100, self.product, quantity=2, request_id='multi'))[0])
        await self.s.catalog.delete_product(self.product)
        self.assertEqual(await self.scalar('SELECT count(*) FROM order_inventory_allocations'), 2)
        self.assertEqual(await self.scalar('SELECT count(*) FROM inventory_items WHERE product_id IS NULL'), 2)
        self.assertIsNone(await self.scalar('SELECT product_id FROM orders'))

    async def test_zini_toggle_is_respected(self):
        await self.s.settings.update({'zinipay_enabled': '0', 'zinipay_api_key': 'present-key'})
        self.assertFalse(await self.s.zinipay.is_enabled())

    async def test_zini_reserves_before_consuming_provider(self):
        await self.enable_zini()
        await self.s.deposits.create_request(100, self.method, 10, 'EXISTING1')
        with self.assertRaises(PendingDepositError):
            await self.s.zinipay.claim(100, self.method, 100, 'NEWPAY001')
        self.s.zinipay.confirm.assert_not_awaited()

    async def test_zini_failed_approval_never_reports_credit(self):
        await self.enable_zini()
        real_approve = self.s.deposits.approve
        self.s.deposits.approve = AsyncMock(return_value=(False, 'Not approved', None))
        result = await self.s.zinipay.claim(100, self.method, 100, 'NEWPAY002')
        self.assertFalse(result.get('credited', False))
        self.assertEqual(await self.scalar('SELECT status FROM payment_verification_attempts'), 'confirmed')
        self.s.deposits.approve = real_approve
        await self.s.zinipay.recover()
        await self.s.zinipay.recover()
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 1100)
        self.assertEqual(await self.scalar('SELECT status FROM payment_verification_attempts'), 'completed')

    async def test_zini_uncertain_confirm_leaves_review_record(self):
        await self.enable_zini()
        self.s.zinipay.confirm = AsyncMock(return_value={'ok': False, 'message': 'Timeout'})
        result = await self.s.zinipay.claim(100, self.method, 100, 'NEWPAY003')
        self.assertTrue(result['fallback_manual'])
        self.assertEqual(await self.scalar('SELECT status FROM payment_verification_attempts'), 'review')
        self.assertEqual(await self.scalar('SELECT status FROM deposits'), 'pending')
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 1000)

    async def test_binance_quote_units_and_singleton(self):
        await self.s.settings.update({'binance_enabled': '1'})
        methods = await asyncio.gather(*(self.s.deposits.get_or_create_binance_method() for _ in range(5)))
        self.assertEqual(len({row['id'] for row in methods}), 1)
        quote = await self.s.deposits.quote(methods[0]['id'], 250)
        self.assertEqual(quote['pay_amount'], 2)
        self.assertEqual(quote['paid_currency'], 'USDT')

    async def test_binance_uid_does_not_auto_credit(self):
        now = datetime.now(timezone.utc)
        client = SimpleNamespace(pay_transactions=AsyncMock(return_value=[{
            'orderType': 'C2C', 'amount': '2', 'currency': 'USDT', 'transactionTime': int(now.timestamp()*1000),
            'payerInfo': {'binanceId': '12345678'}, 'transactionId': 'txn123', 'orderId': 'order123',
        }]))
        self.s.binance._credit = AsyncMock()
        result = await self.s.binance._match_pay({'transaction_id': '12345678', 'created_at': now, 'id': 1}, client, 'USDT')
        self.assertFalse(result['credited'])
        self.s.binance._credit.assert_not_awaited()

    async def test_concurrent_approval_credits_once_and_ledger_reconciles(self):
        dep = await self.s.deposits.create_request(100, self.method, 25, 'CONCURRENT')
        results = await asyncio.gather(*(self.s.deposits.approve(dep) for _ in range(6)))
        self.assertEqual(sum(row[0] for row in results), 1)
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 1025)
        self.assertEqual(await self.scalar('SELECT sum(delta) FROM wallet_ledger WHERE tg_user_id=100'), 1025)
        with self.assertRaises(asyncpg.RaiseError):
            await self.execute('DELETE FROM wallet_ledger')

    async def test_broadcast_retention_preserves_pending_jobs(self):
        first = await self.s.delivery.enqueue_broadcast('first')
        for i in range(31):
            await self.s.delivery.enqueue_broadcast(f'message {i}')
        self.assertEqual(await self.scalar('SELECT count(*) FROM broadcasts'), 32)
        await self.execute("UPDATE outbox SET status='sent' WHERE broadcast_id=$1", first['id'])
        await self.s.delivery.enqueue_broadcast('latest')
        self.assertIsNone(await self.scalar('SELECT id FROM broadcasts WHERE id=$1', first['id']))
        self.assertEqual(await self.scalar("SELECT count(*) FROM outbox WHERE status='pending'"), 32)

    async def test_expired_stock_dashboard(self):
        await self.s.inventory.add_stock(self.product, ['expired'], expires_at=datetime.now(timezone.utc)-timedelta(days=1))
        self.assertEqual((await self.s.dashboard.stats())['available_stock'], 0)
        self.assertFalse((await self.s.purchases.purchase(100, self.product, request_id='expired'))[0])

    async def test_long_credentials_sent_without_invalid_copy_button(self):
        await self.s.inventory.add_stock(self.product, ['x'*300])
        await self.s.purchases.purchase(100, self.product, request_id='long')
        bot = SimpleNamespace(send_message=AsyncMock(), send_document=AsyncMock())
        await DeliveryWorker(self.s.delivery, bot).step()
        markup = bot.send_message.call_args.kwargs['reply_markup']
        self.assertTrue(all(button.copy_text is None for row in markup.inline_keyboard for button in row))
        self.assertEqual(await self.scalar('SELECT delivery_status FROM orders'), 'sent')

    async def test_durable_fsm_and_atomic_updates(self):
        storage = PostgresStorage(self.db)
        key = StorageKey(bot_id=1, chat_id=100, user_id=100)
        await storage.set_state(key, 'waiting_for_payment')
        await asyncio.gather(*(storage.update_data(key, {str(i): i}) for i in range(5)))
        restarted = PostgresStorage(self.db)
        self.assertEqual(await restarted.get_state(key), 'waiting_for_payment')
        self.assertEqual(len(await restarted.get_data(key)), 5)

    async def test_inbox_per_user_ordering_and_retry(self):
        for update_id, user in ((10, 100), (11, 100), (12, 200)):
            await self.execute("INSERT INTO telegram_inbox(update_id,customer_id,payload) VALUES($1,$2,'{}')", update_id, user)
        worker = TelegramInboxWorker(self.s)
        claims = await asyncio.gather(*(worker.claim() for _ in range(3)))
        self.assertEqual({row['update_id'] for row in claims if row}, {10, 12})
        await self.execute("INSERT INTO telegram_inbox(update_id,customer_id,payload) VALUES(9,100,'{}')")
        self.assertIsNone(await worker.claim())
        await self.execute("UPDATE telegram_inbox SET next_attempt=now()-interval '1 second' WHERE update_id=10")
        # A lower queued ID cannot steal an actively processed user's lease.
        reclaimed = await worker.claim()
        self.assertEqual(reclaimed['update_id'], 10)

    async def test_conversation_reads_follow_another_replica(self):
        one, two = PostgresStorage(self.db), PostgresStorage(self.db)
        key = StorageKey(bot_id=1, chat_id=100, user_id=100)
        self.assertIsNone(await one.get_state(key))
        self.assertEqual(await one.get_data(key), {})
        await two.set_state(key, 'waiting')
        await two.set_data(key, {'product': 77})
        self.assertEqual(await one.get_state(key), 'waiting')
        self.assertEqual(await one.get_data(key), {'product': 77})
        await one.set_state(key, None)
        await one.set_data(key, {})
        self.assertIsNone(await two.get_state(key))
        self.assertEqual(await two.get_data(key), {})

    async def test_membership_webhook_queues_by_affected_customer(self):
        self.s.notifier.bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()))
        self.s.runtime.dispatcher = SimpleNamespace(feed_update=AsyncMock())
        user = {'id': 100, 'is_bot': False, 'first_name': 'Customer'}
        payload = {'update_id': 2000, 'chat_member': {
            'chat': {'id': -100123, 'type': 'channel', 'title': 'Required'},
            'from': {'id': 900, 'is_bot': False, 'first_name': 'Admin'}, 'date': 1700000000,
            'old_chat_member': {'status': 'member', 'user': user},
            'new_chat_member': {'status': 'left', 'user': user},
        }}
        headers = {'X-Telegram-Bot-Api-Secret-Token': self.config.webhook_secret}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)), base_url='http://localhost') as client:
            self.assertEqual((await client.post('/telegram/webhook', json=payload, headers=headers)).status_code, 200)
        self.assertEqual(await self.scalar('SELECT customer_id FROM telegram_inbox'), 100)

    async def test_login_limit_atomic_under_concurrency(self):
        allowed = await asyncio.gather(*(self.s.admin_access.login_allowed('test-ip') for _ in range(12)))
        self.assertEqual(sum(allowed), 5)

    async def test_failure_budget_shared_between_service_instances(self):
        await asyncio.gather(*(self.s.deposits.verification_failures(100, record_failure=True) for _ in range(3)))
        self.assertEqual(len(await self.s.deposits.verification_failures(100)), 3)

    async def test_interrupted_confirmation_is_reviewable_and_blocks_early_admin_credit(self):
        dep = await self.s.deposits.create_request(100, self.method, 50, 'INTERRUPT1', verification_id='42')
        self.assertFalse((await self.s.deposits.approve(dep))[0])
        self.assertFalse((await self.s.deposits.reject(dep))[0])
        await self.execute("UPDATE payment_verification_attempts SET updated_at=now()-interval '3 minutes'")
        await self.s.zinipay.recover()
        self.assertEqual(await self.scalar('SELECT status FROM payment_verification_attempts'), 'review')
        self.assertTrue((await self.s.deposits.approve(dep))[0])

    async def test_created_invoice_recovered_and_credit_idempotent(self):
        await self.s.settings.update({'zinipay_api_key': 'test'})
        user_id = await self.scalar('SELECT id FROM users WHERE tg_user_id=100')
        await self.execute(
            "INSERT INTO payment_invoices(reference,provider,user_id,tg_user_id,credit_amount,pay_amount,rate) "
            "VALUES('RECOVERY','zinipay',$1,100,50,50,1)", user_id,
        )
        client = SimpleNamespace(verify=AsyncMock(return_value={
            'status': 'COMPLETED', 'val_id': 'RECOVERY', 'amount': '50', 'transaction_id': 'RECOVERYTX',
        }))
        self.s.payments.client = lambda key: client
        await self.s.payments.refresh('RECOVERY')
        await self.s.payments.refresh('RECOVERY')
        self.assertEqual(await self.scalar('SELECT status FROM payment_invoices'), 'completed')
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 1050)

    async def test_binance_pending_checks_do_not_starve_old_claims(self):
        await self.s.settings.update({'binance_enabled': '1'})
        method = await self.s.deposits.get_or_create_binance_method()
        for i in range(21):
            user = await self.s.users.sync_profile(200+i)
            await self.execute(
                "INSERT INTO deposits(user_id,tg_user_id,method_id,method_name,amount,transaction_id) "
                "VALUES($1,$2,$3,'Binance',125,$4)", user['id'],200+i,method['id'],f'FAIR{i:06}',
            )
        self.s.binance.get_credentials_for_method = AsyncMock(return_value=('dummy','dummy'))
        self.s.binance._match = AsyncMock(return_value={'credited': False})
        self.assertEqual(await self.s.binance.recheck_pending(), 20)
        self.assertEqual(await self.s.binance.recheck_pending(), 1)
        ids = [call.args[0]['id'] for call in self.s.binance._match.call_args_list]
        self.assertEqual(len(set(ids)), 21)

    async def test_legacy_referral_refund_keeps_wallet_nonnegative(self):
        await self.s.users.sync_profile(200)
        manual = await self.s.catalog.create_product(None, 'Historical manual', price=25, delivery_type='manual')
        result = await self.s.purchases.purchase(100, manual, request_id='legacy')
        await self.execute('UPDATE orders SET referral_user_id=200,referral_bonus=5 WHERE id=$1', result[2]['order_id'])
        self.assertTrue((await self.s.purchases.refund(result[2]['order_id']))[0])
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=200'), 0)
        self.assertEqual(await self.scalar('SELECT outstanding FROM referral_recoveries'), 5)

    async def test_webhook_durable_deduplication_and_restart_processing(self):
        self.s.notifier.bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()))
        self.s.runtime.dispatcher = SimpleNamespace(feed_update=AsyncMock())
        payload = {'update_id': 1000, 'message': {'message_id': 1, 'date': 1700000000,
                   'chat': {'id': 100, 'type': 'private'}, 'from': {'id': 100, 'is_bot': False, 'first_name': 'Test'}, 'text': '/start'}}
        headers = {'X-Telegram-Bot-Api-Secret-Token': self.config.webhook_secret}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)), base_url='http://localhost') as client:
            self.assertEqual((await client.post('/telegram/webhook',json=payload)).status_code,403)
            for _ in range(2):
                self.assertEqual((await client.post('/telegram/webhook',json=payload,headers=headers)).status_code,200)
        self.assertEqual(await self.scalar('SELECT count(*) FROM telegram_inbox'),1)
        self.s.runtime.dispatcher.feed_update.assert_not_awaited()
        await TelegramInboxWorker(self.s).step()
        self.s.runtime.dispatcher.feed_update.assert_awaited_once()
        self.assertEqual(await self.scalar('SELECT status FROM telegram_inbox'),'done')

    async def test_reseller_rotation_and_revocation(self):
        await self.execute("UPDATE users SET rank='Reseller' WHERE tg_user_id=100")
        keys = await asyncio.gather(*(self.s.reseller.generate_key(100) for _ in range(4)))
        self.assertEqual(await self.scalar('SELECT count(*) FROM reseller_api_keys WHERE is_active=1'), 1)
        valid = [key for key, _ in keys if await self.s.reseller.authenticate_key(key)]
        self.assertEqual(len(valid), 1)
        await self.s.reseller.revoke_key(100)
        self.assertIsNone(await self.s.reseller.authenticate_key(valid[0]))

    async def test_reseller_retry_identity_and_role(self):
        await self.execute("UPDATE users SET rank='Reseller' WHERE tg_user_id=100")
        key, _ = await self.s.reseller.generate_key(100)
        await self.s.inventory.add_stock(self.product, ['reseller-secret'], max_uses=3)
        headers = {'X-API-Key': key}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)), base_url='http://localhost') as client:
            payload = {'product_id': self.product, 'quantity': 2}
            self.assertEqual((await client.post('/api/v1/reseller/orders', json=payload, headers=headers)).status_code, 422)
            headers['Idempotency-Key'] = 'merchant-order-1'
            first = await client.post('/api/v1/reseller/orders', json=payload, headers=headers)
            second = await client.post('/api/v1/reseller/orders', json=payload, headers=headers)
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json()['order_id'], second.json()['order_id'])
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 980)
        stats = await self.s.reseller.get_reseller_stats(100)
        self.assertEqual(stats['total_orders'], 1)
        self.assertEqual(stats['total_spent'], 20)
        self.assertIsNone(await self.s.reseller.get_reseller_order(200, first.json()['order_id']))
        await self.execute("UPDATE users SET rank='Member' WHERE tg_user_id=100")
        self.assertIsNotNone(await self.s.reseller.authenticate_key(key))
        result = await self.s.purchases.purchase(100, self.product, request_id='late-request', require_reseller=True)
        self.assertFalse(result[0])

    async def test_invoice_conflicting_identity_and_nonfinite_amount_rejected(self):
        user_id = await self.scalar('SELECT id FROM users WHERE tg_user_id=100')
        # 'wrong' here is another invoice of ours: an answer naming it is mixed up. An id we
        # simply do not know is the gateway's own and is no longer treated as a conflict,
        # because live ZiniPay answers with its own UUID beside the val_id it was given.
        await self.scalar(
            "INSERT INTO payment_invoices(reference,provider,user_id,tg_user_id,credit_amount,pay_amount,rate) "
            "VALUES('wrong','zinipay',$1,100,50,50,1) RETURNING id", user_id)
        for i, extra in enumerate(({'invoice_id': 'wrong'}, {'amount': 'NaN'}, {'amount': 'Infinity'})):
            reference = f'INVALID{i}'
            invoice_id = await self.scalar(
                "INSERT INTO payment_invoices(reference,provider,user_id,tg_user_id,credit_amount,pay_amount,rate) "
                "VALUES($1,'zinipay',$2,100,50,50,1) RETURNING id", reference,user_id,
            )
            row = await self.s.payments._apply(invoice_id, {'status': 'COMPLETED', 'val_id': reference, 'amount': '50', **extra})
            self.assertEqual(row['status'], 'failed')
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'), 1000)

    async def test_zini_rejects_malformed_or_conflicting_receipts(self):
        await self.s.settings.update({'zinipay_enabled': '1', 'zinipay_api_key': 'test-key'})
        await self.s.zinipay.http.aclose()
        for body in ([], {'success': True, 'data': []},
                     {'success': True, 'data': {'amount': 'NaN'}},
                     {'success': True, 'data': {'amount': 5}},
                     {'success': True, 'data': {'amount': 50, 'transactionId': 'WRONG'}}):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request, body=body: httpx.Response(200, json=body))) as client:
                self.s.zinipay.http = client
                self.assertFalse((await self.s.zinipay.verify(50, 'RIGHT'))['ok'])
                self.assertFalse((await self.s.zinipay.confirm(50, 'RIGHT', 1))['ok'])

    async def test_migration_checksum_drift_rejected(self):
        await self.execute("UPDATE schema_migrations SET checksum='changed' WHERE version=(SELECT min(version) FROM schema_migrations)")
        with self.assertRaisesRegex(RuntimeError, 'Applied migration changed'):
            await migrate(self.db)

    async def test_upgrade_preserves_historical_orders_wallet_and_supplier_audit(self):
        schema = 'test_upgrade_' + uuid.uuid4().hex
        old = Database(DSN, schema=schema)
        try:
            with tempfile.TemporaryDirectory() as directory:
                for path in Path('app/db/migrations').glob('*.sql'):
                    if path.name[:4] <= '0021':
                        shutil.copyfile(path, Path(directory) / path.name)
                with patch('app.db.migrations.MIGRATIONS_DIR', Path(directory)):
                    await migrate(old)
            async with old.transaction() as conn:
                user = await conn.fetchval("INSERT INTO users(tg_user_id,balance) VALUES(999,123.4567) RETURNING id")
                product = await conn.fetchval("INSERT INTO products(title,price,supplier_product_id) VALUES('Legacy',10,77) RETURNING id")
                order = await conn.fetchval(
                    "INSERT INTO orders(user_id,tg_user_id,product_id,product_title,price,delivered_item,source) "
                    "VALUES($1,999,$2,'Legacy',10,'old-secret','supplier') RETURNING id", user,product,
                )
                await conn.execute(
                    "INSERT INTO supplier_purchase_attempts(tg_user_id,product_id,request_id,provider_request_id,status,order_id) "
                    "VALUES(999,$1,'legacy','provider-legacy','completed',$2)", product,order,
                )
                await conn.execute("INSERT INTO bot_welcome_banners(content_type,data,width,height) VALUES('image/png',decode('00','hex'),1,1)")
                # Simulate migration history written before checksums were introduced.
                await conn.execute('UPDATE schema_migrations SET checksum=NULL')
            await migrate(old)
            self.assertEqual(await migrate(old), [])
            async with old.connect() as conn:
                self.assertEqual(await conn.fetchval('SELECT balance FROM users'), 123.4567)
                self.assertEqual(await conn.fetchval('SELECT balance_after FROM wallet_ledger'), 123.4567)
                self.assertEqual(await conn.fetchval('SELECT delivered_item FROM orders'), 'old-secret')
                self.assertEqual(await conn.fetchval("SELECT count(*) FROM audit_logs WHERE action='supplier_history_archived'"), 1)
                self.assertIsNone(await conn.fetchval("SELECT to_regclass('bot_welcome_banners')"))
        finally:
            await old.close()
            conn = await asyncpg.connect(DSN)
            try:
                await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            finally:
                await conn.close()

    async def test_payment_return_and_removed_routes(self):
        app = create_app(self.s)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
            page = await client.get('/api/payments/return?reference=unknown')
            self.assertEqual(page.status_code, 200)
            self.assertIn('Return to bot', page.text)
            legacy = await client.get('/app/?payment=example%26cancelled%3D1')
            self.assertEqual(legacy.status_code, 302)
            self.assertEqual(legacy.headers['location'], '/api/payments/return?reference=example%26cancelled%3D1')
        self.assertNotIn('supplier', self.s.__dataclass_fields__)

    async def test_shared_rate_budget_atomic_and_expires(self):
        from app.services.rate_limits import RateLimits
        other = RateLimits(self.db)
        results = await asyncio.gather(*((self.s.rate_limits if i % 2 else other).consume('test', 'identity', 5) for i in range(20)))
        self.assertEqual(results.count(0), 5)
        self.assertTrue(all(1 <= value <= 60 for value in results if value))
        await self.execute("UPDATE request_limits SET expires_at=now()-interval '1 second'")
        self.assertEqual(await other.consume('test', 'identity', 5), 0)

    async def test_ip_limits_shared_between_apps(self):
        with patch('app.api.middleware.RATE_LIMIT_PER_MINUTE', 3):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)),base_url='http://localhost') as a:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)),base_url='http://localhost') as b:
                    for client in (a,b,a):
                        self.assertEqual((await client.get('/api/admin/session')).status_code, 200)
                    response = await b.get('/api/admin/session')
                    self.assertEqual(response.status_code, 429)
                    self.assertIn('retry-after',response.headers)
                    self.assertEqual((await b.get('/health/live')).status_code, 200)

    async def test_reseller_rate_limit_survives_key_rotation(self):
        await self.execute("UPDATE users SET rank='Reseller' WHERE tg_user_id=100")
        await self.s.reseller.generate_key(100)
        for _ in range(30):
            await self.s.rate_limits.consume('reseller-write', '100', 30)
        key, _ = await self.s.reseller.generate_key(100)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)),base_url='http://localhost') as client:
            response = await client.post('/api/v1/reseller/orders',headers={'X-API-Key':key},
                                         json={'product_id':self.product,'custom_id':'limited'})
            self.assertEqual(response.status_code,429)
        self.assertEqual(await self.scalar('SELECT count(*) FROM orders'),0)

    async def test_admin_cookie_only_csrf_logout_and_absolute_expiry(self):
        from app.api.admin.auth import SESSION_COOKIE_NAME, SESSION_SECONDS
        app = create_app(self.s)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as client:
            self.assertEqual((await client.get('/api/admin/settings')).status_code,401)
            login = await client.post('/api/admin/login',json={'password':'test-only-password'})
            self.assertEqual(login.status_code,200)
            self.assertNotIn('token',login.json())
            self.assertIn('httponly',login.headers['set-cookie'].lower())
            token = client.cookies.get(SESSION_COOKIE_NAME)
            self.assertLessEqual(app.state.admin_auth.expiry(token)-int(datetime.now(timezone.utc).timestamp()),SESSION_SECONDS)
            session = await client.get('/api/admin/session')
            self.assertNotIn('token',session.json())
            self.assertNotIn('set-cookie',session.headers)
            self.assertEqual((await client.post('/api/admin/logout')).status_code,403)
            self.assertEqual((await client.post('/api/admin/logout',headers={'x-csrf-token':login.json()['csrf']})).status_code,200)
            client.cookies.set(SESSION_COOKIE_NAME,token)
            self.assertFalse((await client.get('/api/admin/session')).json()['signed_in'])

    async def test_body_timeout_is_total_not_per_chunk(self):
        from app.api.middleware import SecurityBoundary
        called = AsyncMock()
        middleware = SecurityBoundary(called,self.config,SimpleNamespace(consume=AsyncMock(return_value=0)))
        async def receive():
            await asyncio.sleep(0.02)
            return {'type':'http.request','body':b'a','more_body':True}
        sent = []
        async def send(message):
            sent.append(message)
        with patch('app.api.middleware.BODY_TIMEOUT_SECONDS',0.03):
            await middleware({'type':'http','path':'/api/test','method':'POST','scheme':'http',
                              'headers':[(b'host',b'localhost')],'client':('127.0.0.1',123)},receive,send)
        called.assert_not_awaited()
        self.assertEqual(sent[0]['status'],408)

    async def test_unsigned_callbacks_coalesce_gateway_checks(self):
        user = await self.scalar('SELECT id FROM users WHERE tg_user_id=100')
        await self.execute("INSERT INTO payment_invoices(reference,provider,user_id,tg_user_id,credit_amount,pay_amount,rate) "
                           "VALUES('CALLBACK','zinipay',$1,100,50,50,1)",user)
        self.s.payments.refresh = AsyncMock()
        await asyncio.gather(*(self.s.payments.handle_webhook('', 'CALLBACK') for _ in range(10)))
        self.s.payments.refresh.assert_awaited_once_with('CALLBACK')

    async def test_readiness_rejects_missing_migration(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)),base_url='http://localhost') as client:
            self.assertEqual((await client.get('/health/ready')).status_code,200)
            await self.execute("DELETE FROM schema_migrations WHERE version='0027_request_limits'")
            self.assertEqual((await client.get('/health/ready')).status_code,503)

    async def test_reseller_cannot_set_price_owner_or_access_admin(self):
        await self.execute("UPDATE users SET rank='Reseller' WHERE tg_user_id=100")
        key, _ = await self.s.reseller.generate_key(100)
        await self.s.users.sync_profile(200)
        await self.execute("UPDATE users SET rank='Reseller' WHERE tg_user_id=200")
        other_key, _ = await self.s.reseller.generate_key(200)
        await self.s.inventory.add_stock(self.product,['private-credential'])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)),base_url='http://localhost') as client:
            headers = {'Authorization':f'Bearer {key}'}
            payload = {'product_id':self.product,'custom_id':'private-order'}
            for extra in ({'price':0},{'user_id':200},{'tg_user_id':200},{'balance':1000000},{'quantity':True},{'quantity':-1}):
                self.assertEqual((await client.post('/api/v1/reseller/orders',headers=headers,json={**payload,**extra})).status_code,422)
            self.assertEqual((await client.post('/api/v1/reseller/orders',headers={**headers,'Idempotency-Key':'different'},json=payload)).status_code,422)
            for path in ('/api/admin/users/200/adjust-balance','/api/admin/deposits/1/approve','/api/admin/orders/1/refund'):
                self.assertEqual((await client.post(path,headers=headers,json={'amount':500,'delta':500})).status_code,401)
            order = await client.post('/api/v1/reseller/orders',headers=headers,json=payload)
            self.assertEqual(order.status_code,200,order.text)
            other = {'X-API-Key':other_key}
            response = await client.get(f"/api/v1/reseller/orders/{order.json()['order_id']}",headers=other)
            self.assertEqual(response.status_code,404)
            self.assertNotIn('private-credential',response.text)
            self.assertEqual((await client.get('/api/v1/reseller/orders',headers=other)).json()['orders'],[])
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'),990)
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=200'),0)

    async def test_reseller_concurrent_retry_charges_exact_server_price_once(self):
        await self.execute("UPDATE users SET rank='Reseller' WHERE tg_user_id=100")
        await self.execute('UPDATE products SET reseller_price=9.9999 WHERE id=$1',self.product)
        key, _ = await self.s.reseller.generate_key(100)
        await self.s.inventory.add_stock(self.product,['shared-exact'],max_uses=3)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(self.s)),base_url='http://localhost') as client:
            results = await asyncio.gather(*(client.post('/api/v1/reseller/orders',headers={'X-API-Key':key},
                         json={'product_id':self.product,'quantity':3,'custom_id':'concurrent'}) for _ in range(8)))
        self.assertTrue(all(result.status_code==200 for result in results),[r.text for r in results])
        self.assertEqual(len({r.json()['order_id'] for r in results}),1)
        self.assertTrue(await self.scalar('SELECT balance=970.0003 FROM users WHERE tg_user_id=100'))
        self.assertTrue(await self.scalar('SELECT price=29.9997 FROM orders'))
        self.assertEqual(await self.scalar('SELECT sum(allocated_units) FROM order_inventory_allocations'),3)
        self.assertEqual(await self.scalar('SELECT count(*) FROM outbox'),1)

    async def test_key_revoked_after_authentication_cannot_charge(self):
        await self.execute("UPDATE users SET rank='Reseller' WHERE tg_user_id=100")
        key, _ = await self.s.reseller.generate_key(100)
        authenticated = await self.s.reseller.authenticate_key(key)
        await self.s.inventory.add_stock(self.product,['revoked-stock'])
        await self.s.reseller.revoke_key(100)
        result = await self.s.purchases.purchase(100,self.product,request_id='stale-auth',require_reseller=True,
                                                  reseller_key_id=authenticated['key_id'])
        self.assertFalse(result[0])
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'),1000)
        self.assertEqual(await self.scalar('SELECT count(*) FROM orders'),0)

    async def test_reseller_delivery_queue_failure_rolls_back_charge_and_stock(self):
        await self.execute("UPDATE users SET rank='Reseller' WHERE tg_user_id=100")
        _, key = await self.s.reseller.generate_key(100)
        await self.s.inventory.add_stock(self.product,['rollback-stock'])
        with patch.object(self.s.delivery,'enqueue_order',AsyncMock(side_effect=RuntimeError('simulated queue failure'))):
            result = await self.s.purchases.purchase(100,self.product,request_id='rollback',require_reseller=True,reseller_key_id=key['id'])
        self.assertFalse(result[0])
        self.assertEqual(await self.scalar('SELECT balance FROM users WHERE tg_user_id=100'),1000)
        self.assertEqual(await self.scalar('SELECT count(*) FROM orders'),0)
        self.assertEqual(await self.scalar('SELECT sum(uses) FROM inventory_items'),0)
        self.assertEqual(await self.scalar('SELECT count(*) FROM outbox'),0)

    async def test_purchase_waits_for_current_price_and_delete_keeps_history(self):
        await self.s.inventory.add_stock(self.product, ['locked-price-stock'])
        async with self.db.transaction() as conn:
            await conn.execute('UPDATE products SET price=20 WHERE id=$1',self.product)
            pending = asyncio.create_task(self.s.purchases.purchase(100,self.product,request_id='price-update'))
            await asyncio.sleep(0.1)
            self.assertFalse(pending.done())
        purchase = await asyncio.wait_for(pending,5)
        self.assertTrue(purchase[0],purchase)
        self.assertEqual(purchase[2]['price'],20)
        await self.s.catalog.delete_product(self.product)
        self.assertEqual(await self.scalar('SELECT delivered_item FROM orders'),'locked-price-stock')


class SecurityUnitTests(unittest.TestCase):
    def test_payment_redirect_rejects_lookalikes_and_userinfo(self):
        from app.services.payments import _is_zinipay_url
        self.assertTrue(_is_zinipay_url('https://secure.zinipay.com/payment/example'))
        for url in ('https://zinipay.xyz/pay','https://zinipay.com.evil.test/pay',
                    'https://evil.test@secure.zinipay.com/pay','http://secure.zinipay.com/pay',
                    'https://secure.zinipay.com:8443/pay','https://[invalid'):
            self.assertFalse(_is_zinipay_url(url),url)


class SecurityClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_documented_invoice_url_only_response_and_untrusted_redirect(self):
        from app.services.payments import PaymentProviderError, ZiniPayClient
        for url, valid in (('https://secure.zinipay.com/payment/INVOICE_ID',True),
                           ('https://zinipay.xyz/payment/INVOICE_ID',False),
                           ('https://secure.zinipay.com/unexpected/INVOICE_ID',False)):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request, url=url: httpx.Response(200,json={'status':True,'payment_url':url}))) as http:
                client = ZiniPayClient('test',http)
                if valid:
                    self.assertEqual((await client.create_invoice({'amount':50}))['invoice_id'],'INVOICE_ID')
                else:
                    with self.assertRaises(PaymentProviderError):
                        await client.create_invoice({'amount':50})


if __name__ == '__main__':
    unittest.main()
