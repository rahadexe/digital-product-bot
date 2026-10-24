"""The Admin Panel button: on the owner's keyboard, absent from everyone else's.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
        python -m unittest tests.test_admin_keyboard -v
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
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, Update, User

from app.bot.app import create_dispatcher
from app.bot.handlers import admin, deposit, help_guide, navigation, profile, reseller_apply, search, shop, start
from app.bot.keyboards import ADMIN_PANEL_TEXT
from app.bot.storage import PostgresStorage
from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services

DSN = os.environ.get('TEST_DATABASE_URL', '')
OWNER, CUSTOMER = 940000001, 940000777


def plain(value):
    return re.sub(r'<[^>]+>', '', value or '')


@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class AdminKeyboard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise unittest.SkipTest('This suite only runs against a local database.')
        self.schema = 'adminkb_' + uuid.uuid4().hex[:12]
        config = Settings(_env_file=None, app_env='testing', database_url=DSN,
                          secret_key='admin-keyboard-tests-' * 3, admin_password='local-test-password', bot_token='')
        self.db = Database(DSN, schema=self.schema, max_size=8)
        await migrate(self.db)
        self.s = build_services(config, db=self.db, use_telegram=False)
        for module in (navigation, admin, start, shop, deposit, profile, reseller_apply, help_guide, search):
            module.router._parent_router = None
        self.dp = create_dispatcher(self.s, storage=PostgresStorage(self.db))
        self.bot = Bot(token='111111:AAtestAAtestAAtestAAtestAAtestAAtest',
                       default=DefaultBotProperties(parse_mode='HTML'))
        await self.s.users.sync_profile(OWNER, first_name='Owner')
        await self.s.users.set_language(OWNER, "en")
        await self.s.users.sync_profile(CUSTOMER, first_name='Rafi')
        await self.s.users.set_language(CUSTOMER, "en")
        await self.s.settings.update({'force_join_enabled': '0', 'admin_tg_ids': str(OWNER),
                                      'zinipay_enabled': '0', 'binance_enabled': '0'})
        await self.s.deposits.create_method('bKash', '01790038892', min_deposit=10)
        self.sent = []

    async def asyncTearDown(self):
        await self.bot.session.close()
        await self.s.close()
        admin_db = Database(DSN)
        async with admin_db.connect() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await admin_db.close()

    async def tap(self, uid, *, text=None, data=None):
        sent = self.sent

        async def answer(message, text=None, **kw):
            sent.append({'text': plain(text), 'markup': kw.get('reply_markup')})
            return Message(message_id=5000 + len(sent), date=datetime.datetime.now(datetime.timezone.utc),
                           chat=message.chat, from_user=message.from_user, text='x')

        async def quietly(*a, **kw):
            return None

        async def edit(message, text=None, **kw):
            sent.append({'text': plain(text), 'markup': kw.get('reply_markup')})
            return message

        now = datetime.datetime.now(datetime.timezone.utc)
        user = User(id=uid, is_bot=False, first_name='X')
        message = Message(message_id=1, date=now, chat=Chat(id=uid, type='private'), from_user=user, text=text or 'x')
        update = (Update(update_id=1, callback_query=CallbackQuery(id='1', from_user=user, chat_instance='c',
                                                                   data=data, message=message))
                  if data else Update(update_id=1, message=message))
        sent.clear()
        with patch.object(Message, 'answer', answer), patch.object(Message, 'edit_text', edit), \
             patch.object(Message, 'delete', quietly), patch.object(CallbackQuery, 'answer', quietly), \
             patch.object(Bot, 'delete_message', quietly):
            await self.dp.feed_update(self.bot, update)
        return list(sent)

    @staticmethod
    def reply_buttons(sent):
        for item in sent:
            if isinstance(item['markup'], ReplyKeyboardMarkup):
                return [b.text for row in item['markup'].keyboard for b in row]
        return []

    async def test_admin_action_is_fifth_home_button_and_not_in_more(self):
        sent = await self.tap(OWNER, text='/start')
        markup = next(i['markup'] for i in sent if isinstance(i['markup'], ReplyKeyboardMarkup))
        self.assertEqual([[b.text for b in row] for row in markup.keyboard], [
            ["🛍 Products", "💰 Wallet", "📦 Orders"], ["💬 Support", "🎁 Referral", "✨ More"], ["🛡 Admin Panel"],
        ])
        more = await self.tap(OWNER, text="✨ More")
        more_markup = next(i['markup'] for i in more if isinstance(i['markup'], InlineKeyboardMarkup))
        callbacks = [b.callback_data for row in more_markup.inline_keyboard for b in row]
        self.assertNotIn("adm_dashboard", callbacks)

    async def test_a_customer_never_sees_it(self):
        buttons = self.reply_buttons(await self.tap(CUSTOMER, text='/start'))
        self.assertFalse(any("Admin Panel" in button for button in buttons), buttons)

    async def test_it_opens_the_panel(self):
        sent = await self.tap(OWNER, text="🛡 Admin Panel")
        self.assertTrue(any('Admin Panel' in i['text'] for i in sent), sent)

    async def test_a_customer_typing_the_words_gets_nothing(self):
        sent = await self.tap(CUSTOMER, text=ADMIN_PANEL_TEXT)
        self.assertFalse(any('Admin' in i['text'] for i in sent), sent)

    async def test_it_works_from_the_middle_of_a_deposit(self):
        await self.tap(OWNER, text='Add Balance')
        methods = await self.s.deposits.methods(active_only=True)
        await self.tap(OWNER, data=f"dep_method_{methods[0]['id']}")
        await self.tap(OWNER, data='dep_confirm_paid')
        sent = await self.tap(OWNER, text=ADMIN_PANEL_TEXT)
        self.assertTrue(any('Admin Panel' in i['text'] for i in sent), sent)
        # and the deposit is no longer waiting for an amount
        after = await self.tap(OWNER, text='100')
        self.assertFalse(any('TrxID' in i['text'] for i in after), after)


if __name__ == '__main__':
    unittest.main()
