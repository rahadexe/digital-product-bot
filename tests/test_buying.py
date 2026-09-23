"""Buying: several at once, and buying at a reseller's own price.

The bug this guards: the check that the price had not moved since the screen was drawn
compared the price on the button with the shop price, ignoring the reseller rate. A
reseller was told "Price changed" every single time and could never buy anything.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
        python -m unittest tests.test_buying -v
"""

import datetime
import os
import re
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.bot.app import create_dispatcher
from app.bot.handlers import admin, deposit, help_guide, profile, search, shop, start
from app.bot.storage import PostgresStorage
from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services

DSN = os.environ.get('TEST_DATABASE_URL', '')
BUYER, RESELLER = 970000001, 970000002


def plain(value):
    return re.sub(r'<[^>]+>', '', value or '')


@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class Buying(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise unittest.SkipTest('This suite only runs against a local database.')
        self.schema = 'buying_' + uuid.uuid4().hex[:12]
        config = Settings(_env_file=None, app_env='testing', database_url=DSN,
                          secret_key='buying-tests-here-' * 3, admin_password='local-test-password', bot_token='')
        self.db = Database(DSN, schema=self.schema, max_size=8)
        await migrate(self.db)
        self.s = build_services(config, db=self.db, use_telegram=False)
        for module in (admin, start, shop, deposit, profile, help_guide, search):
            module.router._parent_router = None
        self.dp = create_dispatcher(self.s, storage=PostgresStorage(self.db))
        self.bot = Bot(token='111111:AAtestAAtestAAtestAAtestAAtestAAtest',
                       default=DefaultBotProperties(parse_mode='HTML'))
        await self.s.settings.update({'force_join_enabled': '0', 'zinipay_enabled': '0', 'binance_enabled': '0'})
        for uid in (BUYER, RESELLER):
            await self.s.users.sync_profile(uid, first_name='Rafi')
            await self.s.users.adjust_balance(uid, 10_000, 'seed')
        async with self.db.connect() as conn:
            await conn.execute("UPDATE users SET rank='reseller' WHERE tg_user_id=$1", RESELLER)
        category = await self.s.catalog.create_category('VPN', is_pinned=1)
        self.plain_product = await self.s.catalog.create_product(category, 'Plain VPN', price=100,
                                                                 delivery_type='stock')
        self.deal = await self.s.catalog.create_product(category, 'Deal VPN', price=100, reseller_price=80,
                                                        delivery_type='stock')
        for pid in (self.plain_product, self.deal):
            await self.s.inventory.add_stock(pid, [f'key-{pid}-{i}' for i in range(20)])
        self.screen, self.written = {}, []

    async def asyncTearDown(self):
        await self.bot.session.close()
        await self.s.close()
        admin_db = Database(DSN)
        async with admin_db.connect() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await admin_db.close()

    async def tap(self, uid, *, data=None, text=None):
        screen, written, alerts = self.screen, self.written, []

        async def answer(message, text=None, **kw):
            mid = 12_000 + len(screen)
            screen[mid] = text
            written.append((plain(text), kw.get('reply_markup')))
            return Message(message_id=mid, date=datetime.datetime.now(datetime.timezone.utc),
                           chat=message.chat, from_user=message.from_user, text='x')

        async def edit(message, text=None, **kw):
            if screen.get(message.message_id) == text:
                raise TelegramBadRequest(method=None, message='Bad Request: message is not modified')
            screen[message.message_id] = text
            written.append((plain(text), kw.get('reply_markup')))
            return message

        async def acknowledge(query, text=None, **kw):
            if text:
                alerts.append(text)

        # A test taps faster than any thumb: the rate limit and the debounce are tested
        # where they belong, not here.
        for mw in list(self.dp.message.outer_middleware) + list(self.dp.callback_query.outer_middleware):
            if getattr(mw, '_buckets', None) is not None:
                mw._buckets.clear()
            if getattr(mw, '_last_actions', None) is not None:
                mw._last_actions.clear()
        now = datetime.datetime.now(datetime.timezone.utc)
        user = User(id=uid, is_bot=False, first_name='Rafi')
        message = Message(message_id=1, date=now, chat=Chat(id=uid, type='private'), from_user=user, text=text or 'x')
        update = (Update(update_id=1, callback_query=CallbackQuery(id='1', from_user=user, chat_instance='c',
                                                                   data=data, message=message))
                  if data else Update(update_id=1, message=message))
        self.written.clear()
        self.screen.clear()
        with patch.object(Message, 'answer', answer), patch.object(Message, 'edit_text', edit), \
             patch.object(CallbackQuery, 'answer', acknowledge):
            await self.dp.feed_update(self.bot, update)
        self.alerts = alerts
        return alerts

    def buttons(self):
        for _, markup in reversed(self.written):
            rows = getattr(markup, 'inline_keyboard', None) or []
            data = [b.callback_data for row in rows for b in row if b.callback_data]
            if data:
                return data
        return []

    def said(self):
        return self.written[-1][0] if self.written else ''

    async def balance(self, uid):
        user = await self.s.users.get(uid)
        return float(user['balance']) if user else 0.0

    async def add_one(self, uid):
        """Press + on the quantity selector."""
        plus = max((c for c in self.buttons() if c.startswith('qty_set_')),
                   key=lambda c: int(c.rsplit('_', 1)[1]))
        await self.tap(uid, data=plus)

    async def buy(self, uid, product_id, quantity=1):
        await self.tap(uid, data=f'prod_{product_id}')
        for _ in range(quantity - 1):
            await self.add_one(uid)
        button = next((c for c in self.buttons() if c.startswith('buy_qty_')), None)
        self.assertIsNotNone(button, f'no buy button on screen: {self.said()[:80]}')
        before = await self.balance(uid)
        await self.tap(uid, data=button)
        return round(before - await self.balance(uid), 2)

    # -- the tests -------------------------------------------------------------

    async def test_a_customer_buys_three_at_once(self):
        self.assertEqual(await self.buy(BUYER, self.plain_product, quantity=3), 300.0, self.said()[:100])

    async def test_a_reseller_pays_their_own_price(self):
        spent = await self.buy(RESELLER, self.deal)
        self.assertEqual(spent, 80.0, f'{self.said()[:60]} {self.alerts}')

    async def test_a_reseller_buys_two_at_their_own_price(self):
        self.assertEqual(await self.buy(RESELLER, self.deal, quantity=2), 160.0, f'{self.said()[:60]} {self.alerts}')

    async def test_a_normal_customer_pays_the_normal_price(self):
        self.assertEqual(await self.buy(BUYER, self.deal), 100.0, f'{self.said()[:60]} {self.alerts}')

    async def test_a_price_that_really_changed_still_stops_the_purchase(self):
        await self.tap(BUYER, data=f'prod_{self.plain_product}')
        button = next(c for c in self.buttons() if c.startswith('buy_qty_'))
        async with self.db.connect() as conn:
            await conn.execute('UPDATE products SET price = 150 WHERE id=$1', self.plain_product)
        self.s.catalog._products_cache.clear()
        before = await self.balance(BUYER)
        alerts = await self.tap(BUYER, data=button)
        self.assertEqual(await self.balance(BUYER), before, 'nothing may be charged at the old price')
        self.assertTrue(any('Price changed' in a for a in alerts), alerts)

    async def test_a_manual_order_is_confirmed_once(self):
        """The delivery queue sends the customer's confirmation; the screen must not repeat it."""
        category = await self.s.catalog.create_category('Manual', is_pinned=1)
        manual = await self.s.catalog.create_product(category, 'Netflix Private', price=63,
                                                     delivery_type='manual')
        spent = await self.buy(BUYER, manual)
        self.assertEqual(spent, 63.0)
        self.assertIn('Order Placed', self.said())
        for repeated in ('Payment successful', 'being prepared', 'delivered shortly'):
            self.assertNotIn(repeated, self.said(), self.said())

        async with self.db.connect() as conn:
            queued = await conn.fetch('SELECT text FROM outbox WHERE tg_user_id=$1', BUYER)
        waiting = [q for q in queued if 'Payment Received' in q['text']]
        self.assertEqual(len(waiting), 1, 'exactly one queued confirmation')

    async def test_an_instant_order_still_points_at_its_details(self):
        spent = await self.buy(BUYER, self.plain_product)
        self.assertEqual(spent, 100.0)
        self.assertIn('below', self.said(), self.said())


if __name__ == '__main__':
    unittest.main()
