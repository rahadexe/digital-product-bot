"""Search is started by its button and does not outlive it.

The complaint this guards: tap Search once, wander off to Deposit or a category, and
whatever you type later — an amount, a greeting — is still searched, as if search mode
never switched off.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
        python -m unittest tests.test_search_mode -v
"""

import datetime
import os
import re
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from app.bot.app import create_dispatcher
from app.bot.handlers import admin, deposit, help_guide, navigation, profile, reseller_apply, search, shop, start
from app.bot.storage import PostgresStorage
from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services

DSN = os.environ.get('TEST_DATABASE_URL', '')
CUSTOMER = 930000111


def plain(value):
    return re.sub(r'<[^>]+>', '', value or '')


def searched(text):
    return ' match' in text or 'Please try a different name' in text


@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class SearchMode(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.enterContext(patch.object(Message, 'delete', new_callable=AsyncMock))
        self.enterContext(patch.object(Bot, 'delete_message', new_callable=AsyncMock))
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise unittest.SkipTest('This suite only runs against a local database.')
        self.schema = 'searchmode_' + uuid.uuid4().hex[:12]
        config = Settings(_env_file=None, app_env='testing', database_url=DSN,
                          secret_key='search-mode-tests-' * 3, admin_password='local-test-password', bot_token='')
        self.db = Database(DSN, schema=self.schema, max_size=8)
        await migrate(self.db)
        self.s = build_services(config, db=self.db, use_telegram=False)
        for module in (navigation, admin, start, shop, deposit, profile, reseller_apply, help_guide, search):
            module.router._parent_router = None
        self.dp = create_dispatcher(self.s, storage=PostgresStorage(self.db))
        self.bot = Bot(token='111111:AAtestAAtestAAtestAAtestAAtestAAtest',
                       default=DefaultBotProperties(parse_mode='HTML'))
        await self.s.users.sync_profile(CUSTOMER, first_name='Rafi')
        await self.s.users.set_language(CUSTOMER, "en")
        await self.s.settings.update({'force_join_enabled': '0', 'zinipay_enabled': '0', 'binance_enabled': '0'})
        cat = await self.s.catalog.create_category('VPN')
        await self.s.catalog.create_product(cat, 'Nord VPN', price=160, delivery_type='manual')
        await self.s.catalog.create_product(cat, 'HMA VPN', price=120, delivery_type='manual')
        await self.s.deposits.create_method('bKash', '01790038892', min_deposit=10)
        self.screen, self.written, self.callbacks = {}, [], []

    async def asyncTearDown(self):
        await self.bot.session.close()
        await self.s.close()
        admin_db = Database(DSN)
        async with admin_db.connect() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await admin_db.close()

    async def tap(self, *, text=None, data=None):
        screen, written = self.screen, self.written

        def labels(kw):
            rows = getattr(kw.get('reply_markup'), 'inline_keyboard', None) or []
            self.callbacks = [b.callback_data for row in rows for b in row if b.callback_data] or self.callbacks
            return ' '.join(b.text for row in rows for b in row)

        async def answer(message, text=None, **kw):
            mid = 8000 + len(screen)
            screen[mid] = text
            written.append(f"{text} {labels(kw)}")
            return Message(message_id=mid, date=datetime.datetime.now(datetime.timezone.utc),
                           chat=message.chat, from_user=message.from_user, text='x')

        async def edit(message, text=None, **kw):
            if screen.get(message.message_id) == text:
                raise TelegramBadRequest(method=None, message='Bad Request: message is not modified')
            screen[message.message_id] = text
            written.append(f"{text} {labels(kw)}")
            return message

        async def quietly(*a, **kw):
            return None

        for mw in list(self.dp.message.outer_middleware) + list(self.dp.callback_query.outer_middleware):
            if getattr(mw, '_buckets', None) is not None:
                mw._buckets.clear()
            if getattr(mw, '_last_actions', None) is not None:
                mw._last_actions.clear()
        now = datetime.datetime.now(datetime.timezone.utc)
        user = User(id=CUSTOMER, is_bot=False, first_name='Rafi')
        message = Message(message_id=1, date=now, chat=Chat(id=CUSTOMER, type='private'), from_user=user,
                          text=text or 'x')
        update = (Update(update_id=1, callback_query=CallbackQuery(id='1', from_user=user, chat_instance='c',
                                                                   data=data, message=message))
                  if data else Update(update_id=1, message=message))
        self.written.clear()
        with patch.object(Message, 'answer', answer), patch.object(Message, 'edit_text', edit), \
             patch.object(Message, 'delete', quietly), patch.object(CallbackQuery, 'answer', quietly):
            await self.dp.feed_update(self.bot, update)
        return ' '.join(plain(w) for w in self.written)

    async def test_search_button_then_a_name_searches(self):
        await self.tap(text='Search')
        self.assertIn('Nord VPN', await self.tap(text='nord'))

    async def test_bengali_still_finds_it(self):
        await self.tap(text='Search')
        self.assertIn('HMA VPN', await self.tap(text='হামা'))

    async def test_text_without_the_button_gets_no_reply_at_all(self):
        self.assertEqual(await self.tap(text='nord'), '')
        self.assertEqual(await self.tap(text='asdkjh random'), '')

    def button(self, prefix):
        return next(c for c in self.callbacks if c.startswith(prefix))

    async def test_back_from_a_search_result_returns_to_the_results(self):
        await self.tap(text='Search')
        await self.tap(text='nord')
        await self.tap(data=self.button('sprod_'))
        back = self.button('sback_')
        reply = await self.tap(data=back)
        self.assertIn('match', reply)
        self.assertIn('Nord VPN', reply)

    async def test_back_still_returns_to_the_results_after_changing_quantity(self):
        await self.tap(text='Search')
        await self.tap(text='nord')
        await self.tap(data=self.button('sprod_'))
        plus = max((c for c in self.callbacks if c.startswith('qty_set_')),
                   key=lambda c: int(c.rsplit('_', 1)[1]))          # the + button
        self.assertIn('Quantity: 2', await self.tap(data=plus))
        self.assertTrue(any(c.startswith('sback_') for c in self.callbacks), self.callbacks)

    async def test_the_same_product_from_its_category_goes_back_to_the_category(self):
        await self.tap(text='Search')
        await self.tap(text='nord')
        product_id = self.button('sprod_').removeprefix('sprod_')
        await self.tap(data=f'prod_{product_id}')
        self.assertFalse(any(c.startswith('sback_') for c in self.callbacks), self.callbacks)

    async def test_one_search_per_tap(self):
        await self.tap(text='Search')
        await self.tap(text='nord')
        reply = await self.tap(text='hello there')
        self.assertFalse(searched(reply), reply)

    async def test_search_again_arms_the_next_one(self):
        await self.tap(text='Search')
        await self.tap(text='nord')
        await self.tap(data='search_again')
        self.assertIn('HMA VPN', await self.tap(text='hma'))

    async def test_an_inline_button_ends_it(self):
        await self.tap(text='Search')
        await self.tap(data='open_shop')
        reply = await self.tap(text='nord')
        self.assertFalse(searched(reply), reply)

    async def test_cancel_ends_it(self):
        await self.tap(text='Search')
        await self.tap(data='close_menu')
        reply = await self.tap(text='nord')
        self.assertFalse(searched(reply), reply)

    async def test_a_menu_button_ends_it(self):
        await self.tap(text='Search')
        await self.tap(text='VPN')            # a category from the keyboard menu
        reply = await self.tap(text='nord')
        self.assertFalse(searched(reply), reply)

    async def test_going_to_deposit_ends_it_and_the_amount_goes_to_the_deposit(self):
        await self.tap(text='Search')
        await self.tap(text='Add Balance')
        methods = await self.s.deposits.methods(active_only=True)
        await self.tap(data=f"dep_method_{methods[0]['id']}")
        await self.tap(data='dep_confirm_paid')
        reply = await self.tap(text='100')
        self.assertFalse(searched(reply), reply)
        self.assertIn('TrxID', reply, 'the amount belongs to the deposit, which now asks for the TrxID')

    async def test_search_from_inside_a_deposit_prompt(self):
        await self.tap(text='Add Balance')
        methods = await self.s.deposits.methods(active_only=True)
        await self.tap(data=f"dep_method_{methods[0]['id']}")
        await self.tap(data='dep_confirm_paid')
        await self.tap(text='Search')
        self.assertIn('Nord VPN', await self.tap(text='nord'))


if __name__ == '__main__':
    unittest.main()
