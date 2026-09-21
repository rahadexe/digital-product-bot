"""Injection, access-control and production-configuration tests.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
        python -m unittest tests.test_access_security -v
"""

import os
import unittest
import uuid
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services

DSN = os.environ.get('TEST_DATABASE_URL', '')
CUSTOMER = 100200300
INTRUDER = 100200999
HOSTILE = "'; DROP TABLE users; --"


@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class InjectionTests(unittest.IsolatedAsyncioTestCase):
    """Some SQL is built as text. These prove the text comes from an allowlist
    and everything from a request is bound as a parameter."""

    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise unittest.SkipTest('This suite only runs against a local database.')
        self.schema = 'inj_' + uuid.uuid4().hex[:12]
        config = Settings(_env_file=None, app_env='testing', database_url=DSN,
                          secret_key='injection-tests-' * 4, admin_password='local-test-password', bot_token='')
        self.db = Database(DSN, schema=self.schema, max_size=6)
        await migrate(self.db)
        self.s = build_services(config, db=self.db, use_telegram=False)
        await self.s.users.sync_profile(CUSTOMER, first_name='Customer', username='victim')
        self.category = await self.s.catalog.create_category('Subs')
        self.product = await self.s.catalog.create_product(self.category, 'A product', price=100)

    async def asyncTearDown(self):
        await self.s.close()
        admin = Database(DSN)
        async with admin.connect() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await admin.close()

    async def tables(self):
        async with self.db.connect() as conn:
            return {r['table_name'] for r in await conn.fetch(
                'SELECT table_name FROM information_schema.tables WHERE table_schema=$1', self.schema)}

    async def test_search_terms_cannot_change_the_query(self):
        before = await self.tables()
        users, _, _ = await self.s.users.list(search=HOSTILE)
        orders, _, _ = await self.s.purchases.all_orders(search=HOSTILE)
        entries = await self.s.audit.search(search=HOSTILE, action=HOSTILE)
        items, _, _ = await self.s.inventory.items(status=HOSTILE)
        self.assertEqual(users, [])
        self.assertEqual(orders, [])
        self.assertEqual(entries['entries'], [])
        self.assertEqual(items, [])
        self.assertEqual(await self.tables(), before, 'the schema must be untouched')

    async def test_a_field_name_outside_the_allowlist_is_dropped(self):
        """The SET clause is built from dict keys, so the allowlist is the defence."""
        before = await self.tables()
        smuggled = 'title = title, is_active = 0 WHERE 1=1; DROP TABLE orders; --'
        await self.s.catalog.update_product(self.product, **{smuggled: 'x', 'price': 250.0})
        async with self.db.connect() as conn:
            row = await conn.fetchrow('SELECT price, is_active FROM products WHERE id=$1', self.product)
        self.assertEqual(float(row['price']), 250.0, 'the allowlisted field still applies')
        self.assertEqual(row['is_active'], 1, 'the smuggled clause must not have run')
        self.assertEqual(await self.tables(), before)

    def test_every_text_built_update_filters_its_keys(self):
        """A writable field has to be a plain identifier, because it is written
        into the statement verbatim."""
        from app.services.catalog import PRODUCT_FIELDS
        from app.services.deposits import METHOD_FIELDS
        from app.services.gate import CHANNEL_FIELDS as GATE_FIELDS
        from app.services.update_channels import CHANNEL_FIELDS as UPDATE_FIELDS
        for allowlist in (PRODUCT_FIELDS, METHOD_FIELDS, GATE_FIELDS, UPDATE_FIELDS):
            self.assertTrue(allowlist)
            for name in allowlist:
                self.assertRegex(name, r'^[a-z][a-z0-9_]*$',
                                 f'{name!r} would be interpolated into SQL as written')

    async def test_an_unknown_setting_is_refused(self):
        from app.services.errors import InvalidInputError
        with self.assertRaises(InvalidInputError):
            await self.s.settings.update({'store_name; DROP TABLE users': 'x'})


@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise unittest.SkipTest('This suite only runs against a local database.')
        self.schema = 'acc_' + uuid.uuid4().hex[:12]
        config = Settings(_env_file=None, app_env='testing', database_url=DSN,
                          secret_key='access-tests-key-' * 3, admin_password='local-test-password', bot_token='')
        self.db = Database(DSN, schema=self.schema, max_size=6)
        await migrate(self.db)
        self.s = build_services(config, db=self.db, use_telegram=False)
        await self.s.users.sync_profile(CUSTOMER, first_name='Customer')
        await self.s.users.sync_profile(INTRUDER, first_name='Intruder')
        self.category = await self.s.catalog.create_category('Subs')
        self.product = await self.s.catalog.create_product(self.category, 'A product', price=100)
        await self.s.inventory.add_stock(self.product, ['credential-1', 'credential-2'])

    async def asyncTearDown(self):
        await self.s.close()
        admin = Database(DSN)
        async with admin.connect() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await admin.close()

    async def test_a_customer_cannot_read_another_customers_order(self):
        await self.s.users.adjust_balance(CUSTOMER, 1000, 'test')
        ok, _, order = await self.s.purchases.purchase(CUSTOMER, self.product, request_id='sec-1')
        self.assertTrue(ok)
        self.assertIsNone(await self.s.purchases.order_for_customer(INTRUDER, order['order_id']),
                          'delivered credentials must not be readable by anyone else')
        self.assertIsNotNone(await self.s.purchases.order_for_customer(CUSTOMER, order['order_id']))

    async def test_a_reseller_order_belongs_to_its_reseller(self):
        await self.s.users.set_rank(CUSTOMER, 'Reseller')
        await self.s.users.adjust_balance(CUSTOMER, 1000, 'test')
        ok, _, order = await self.s.purchases.purchase(CUSTOMER, self.product, request_id='sec-2')
        self.assertTrue(ok)
        self.assertIsNone(await self.s.reseller.get_reseller_order(INTRUDER, order['order_id']))
        self.assertIsNotNone(await self.s.reseller.get_reseller_order(CUSTOMER, order['order_id']))

    async def test_a_revoked_reseller_key_stops_working(self):
        await self.s.users.set_rank(CUSTOMER, 'Reseller')
        raw, _ = await self.s.reseller.generate_key(CUSTOMER)
        self.assertIsNotNone(await self.s.reseller.authenticate_key(raw))
        await self.s.reseller.revoke_key(CUSTOMER)
        self.assertIsNone(await self.s.reseller.authenticate_key(raw))

    async def test_losing_the_reseller_rank_stops_the_key(self):
        await self.s.users.set_rank(CUSTOMER, 'Reseller')
        raw, _ = await self.s.reseller.generate_key(CUSTOMER)
        await self.s.users.set_rank(CUSTOMER, 'Standard')
        self.assertIsNone(await self.s.reseller.authenticate_key(raw))

    async def test_a_banned_reseller_cannot_use_their_key(self):
        await self.s.users.set_rank(CUSTOMER, 'Reseller')
        raw, _ = await self.s.reseller.generate_key(CUSTOMER)
        await self.s.users.set_banned(CUSTOMER, True)
        self.assertIsNone(await self.s.reseller.authenticate_key(raw))

    async def test_rotating_a_key_retires_the_previous_one(self):
        await self.s.users.set_rank(CUSTOMER, 'Reseller')
        first, _ = await self.s.reseller.generate_key(CUSTOMER)
        second, _ = await self.s.reseller.generate_key(CUSTOMER)
        self.assertIsNone(await self.s.reseller.authenticate_key(first))
        self.assertIsNotNone(await self.s.reseller.authenticate_key(second))

    async def test_a_non_reseller_cannot_mint_a_key(self):
        from app.services.errors import PermissionDeniedError
        with self.assertRaises(PermissionDeniedError):
            await self.s.reseller.generate_key(INTRUDER)

    async def test_secret_settings_are_never_read_back(self):
        await self.s.settings.update({'zinipay_api_key': 'super-secret-key-value',
                                      'binance_api_secret': 'another-secret-value'})
        public = await self.s.settings.public()
        self.assertNotIn('super-secret-key-value', str(public))
        self.assertNotIn('another-secret-value', str(public))
        # Saving the form back with its masked placeholders must not erase the key.
        await self.s.settings.update(public)
        self.assertEqual(await self.s.settings.get('zinipay_api_key'), 'super-secret-key-value')

    async def test_a_banned_customer_cannot_buy(self):
        await self.s.users.adjust_balance(CUSTOMER, 1000, 'test')
        await self.s.users.set_banned(CUSTOMER, True)
        ok, message, _ = await self.s.purchases.purchase(CUSTOMER, self.product, request_id='sec-3')
        self.assertFalse(ok)
        self.assertIn('banned', message.lower())

    async def test_a_paused_store_refuses_every_purchase(self):
        await self.s.users.adjust_balance(CUSTOMER, 1000, 'test')
        await self.s.settings.update({'store_paused': '1'})
        ok, _, _ = await self.s.purchases.purchase(CUSTOMER, self.product, request_id='sec-4')
        self.assertFalse(ok)

    async def test_a_purchase_cannot_spend_money_that_is_not_there(self):
        await self.s.users.adjust_balance(CUSTOMER, 50, 'test')
        ok, message, _ = await self.s.purchases.purchase(CUSTOMER, self.product, request_id='sec-5')
        self.assertFalse(ok)
        self.assertIn('balance', message.lower())
        async with self.db.connect() as conn:
            balance = float(await conn.fetchval('SELECT balance FROM users WHERE tg_user_id=$1', CUSTOMER))
        self.assertEqual(balance, 50.0, 'a refused purchase must not move money')


class ProductionConfigTests(unittest.TestCase):
    """Production refuses to start on a configuration that cannot be safe."""

    BASE = dict(_env_file=None, app_env='production', database_url='postgresql://u:p@h/db',
                webhook_base_url='https://shop.example', bot_token='real:token')

    def settings(self, **overrides):
        return Settings(**{**self.BASE, 'admin_password': 'a-strong-password',
                           'secret_key': 'k' * 48, **overrides})

    def test_a_valid_production_configuration_starts(self):
        self.assertTrue(self.settings().cookie_secure, 'the session cookie must be marked secure')

    def test_a_short_admin_password_is_refused(self):
        with self.assertRaises(ValidationError):
            self.settings(admin_password='short')

    def test_the_documented_default_password_is_refused(self):
        with self.assertRaises(ValidationError):
            self.settings(admin_password='admin123456')

    def test_a_weak_secret_key_is_refused(self):
        with self.assertRaises(ValidationError):
            self.settings(secret_key='change_me')

    def test_an_absent_secret_key_is_refused(self):
        with self.assertRaises(ValidationError):
            Settings(**{**self.BASE, 'admin_password': 'a-strong-password'})

    def test_a_missing_database_is_refused(self):
        with self.assertRaises(ValidationError):
            self.settings(database_url='')

    def test_a_plain_http_webhook_is_refused(self):
        with self.assertRaises(ValidationError):
            self.settings(webhook_base_url='http://shop.example')

    def test_trusted_proxies_never_default_to_everything(self):
        self.assertNotIn('*', self.settings().trusted_proxy_ips)

    def test_the_webhook_secret_is_derived_when_absent(self):
        config = self.settings()
        self.assertGreaterEqual(len(config.webhook_secret), 32)
        self.assertEqual(config.webhook_secret, self.settings().webhook_secret,
                         'it must be stable across restarts, or every replica disagrees')


if __name__ == '__main__':
    unittest.main()
