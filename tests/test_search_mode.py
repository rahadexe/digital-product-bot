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
CUSTOMER = 930000111


def plain(value):
    return re.sub(r'<[^>]+>', '', value or '')


def searched(text):
    return ' match' in text or 'Please try a different name' in text


@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class SearchMode(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise unittest.SkipTest('This suite only runs against a local database.')
        self.schema = 'searchmode_' + uuid.uuid4().hex[:12]
        config = Settings(_env_file=None, app_env='testing', database_url=DSN,
                          secret_key='search-mode-tests-' * 3, admin_password='local-test-password', bot_token='')
        self.db = Database(DSN, schema=self.schema, max_size=8)
        await migrate(self.db)
        self.s = build_services(config, db=self.db, use_telegram=False)
        for module in (admin, start, shop, deposit, profile, help_guide, search):
            module.router._parent_router = None
        self.dp = create_dispatcher(self.s, storage=PostgresStorage(self.db))
        self.bot = Bot(token='111111:AAtestAAtestAAtestAAtestAAtestAAtest',
                       default=DefaultBotProperties(parse_mode='HTML'))
        await self.s.users.sync_profile(CUSTOMER, first_name='Rafi')
        await self.s.settings.update({'force_join_enabled': '0', 'zinipay_enabled': '0', 'binance_enabled': '0'})
        cat = await self.s.catalog.create_category('VPN')
        await self.s.catalog.create_product(cat, 'Nord VPN', price=160, delivery_type='manual')
        await self.s.catalog.create_product(cat, 'HMA VPN', price=120, delivery_type='manual')
        await self.s.deposits.create_method('bKash', '01790038892', min_deposit=10)
        self.screen, self.written = {}, []

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

    async def test_text_without_the_button_is_not_searched(self):
        reply = await self.tap(text='nord')
        self.assertFalse(searched(reply), reply)
        self.assertIn('Search', reply, 'but it points the way instead of staying silent')

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
