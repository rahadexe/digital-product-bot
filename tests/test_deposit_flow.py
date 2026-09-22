"""The deposit screens a customer actually walks through, driven by the real dispatcher.

These exist because the interesting failures are not in the services: they are in what
the conversation remembers between two taps. A deposit that cleared the conversation
state looked fine in every service test and still lost the customer their money, because
the corrected transaction id arrived in an expired session.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
        python -m unittest tests.test_deposit_flow -v
"""

import datetime
import os
import re
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import urlsplit

import httpx
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
from app.services import zinipay as zinipay_module

DSN = os.environ.get('TEST_DATABASE_URL', '')
CUSTOMER = 910000111

MISSING = ({'success': False, 'code': 'REQUEST_FAILED', 'message': 'Transaction not found', 'data': None}, 404)


def receipt(amount, trx):
    return ({'success': True, 'data': {'id': 77, 'amount': amount, 'trxID': trx}}, 200)


def plain(value):
    return re.sub(r'<[^>]+>', '', value or '')


@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class DepositConversation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise unittest.SkipTest('This suite only runs against a local database.')
        self.schema = 'depflow_' + uuid.uuid4().hex[:12]
        config = Settings(_env_file=None, app_env='testing', database_url=DSN,
                          secret_key='deposit-conversation-' * 3, admin_password='local-test-password',
                          bot_token='')
        self.db = Database(DSN, schema=self.schema, max_size=8)
        await migrate(self.db)
        self.s = build_services(config, db=self.db, use_telegram=False)
        # Routers are module-level singletons: a second dispatcher in the same process
        # refuses to adopt one that is still attached to the first.
        for module in (admin, start, shop, deposit, profile, help_guide, search):
            module.router._parent_router = None
        self.dp = create_dispatcher(self.s, storage=PostgresStorage(self.db))
        self.bot = Bot(token='111111:AAtestAAtestAAtestAAtestAAtestAAtest',
                       default=DefaultBotProperties(parse_mode='HTML'))
        await self.s.users.sync_profile(CUSTOMER, first_name='Rafi')
        await self.s.settings.update({'force_join_enabled': '0', 'zinipay_enabled': '1',
                                      'zinipay_api_key': 'test-key', 'binance_enabled': '0'})
        self.method = await self.s.deposits.create_method('bKash', '01790038892', min_deposit=10)
        self.screen, self.written, self.posted = {}, [], []

    async def asyncTearDown(self):
        await self.bot.session.close()
        await self.s.close()
        admin_db = Database(DSN)   # not the handler module of the same name
        async with admin_db.connect() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await admin_db.close()

    # -- driving the conversation ---------------------------------------------

    def _patches(self):
        screen, written, posted = self.screen, self.written, self.posted

        async def answer(message, text=None, **kw):
            mid = 7000 + len(posted)
            posted.append(text)
            screen[mid] = text
            written.append(text)
            return Message(message_id=mid, date=datetime.datetime.now(datetime.timezone.utc),
                           chat=message.chat, from_user=message.from_user, text='x')

        async def edit(message, text=None, **kw):
            # Telegram refuses an edit that would change nothing.
            if screen.get(message.message_id) == text:
                raise TelegramBadRequest(method=None, message='Bad Request: message is not modified')
            screen[message.message_id] = text
            written.append(text)
            return message

        async def acknowledge(query, text=None, **kw):
            if text:
                written.append('ALERT: ' + text)

        return (patch.object(Message, 'answer', answer),
                patch.object(Message, 'edit_text', edit),
                patch.object(CallbackQuery, 'answer', acknowledge))

    async def tap(self, *, text=None, data=None):
        now = datetime.datetime.now(datetime.timezone.utc)
        user = User(id=CUSTOMER, is_bot=False, first_name='Rafi')
        message = Message(message_id=1, date=now, chat=Chat(id=CUSTOMER, type='private'),
                          from_user=user, text=text or 'x')
        update = (Update(update_id=1, callback_query=CallbackQuery(id='1', from_user=user,
                                                                   chat_instance='c', data=data, message=message))
                  if data else Update(update_id=1, message=message))
        a, b, c = self._patches()
        with a, b, c:
            await self.dp.feed_update(self.bot, update)

    def last(self):
        return plain(self.written[-1]) if self.written else ''

    def gateway(self, body_status):
        body, status = body_status
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body)))

    async def submit(self, amount, trx, body_status, retries=(0.01,)):
        await self.tap(text='Add Balance')
        await self.tap(data=f'dep_method_{self.method}')
        await self.tap(data='dep_confirm_paid')
        await self.tap(text=str(amount))
        self.written.clear()
        self.posted.clear()
        await self.s.zinipay.http.aclose()
        with patch.object(zinipay_module, 'SMS_SYNC_RETRY_DELAYS', retries):
            async with self.gateway(body_status) as client:
                self.s.zinipay.http = client
                await self.tap(text=trx)

    async def balance(self):
        user = await self.s.users.get(CUSTOMER)
        return float(user['balance']) if user else 0.0

    # -- the tests -------------------------------------------------------------

    async def test_a_receipt_still_in_transit_leaves_one_card_on_screen(self):
        await self.submit(250, 'BK00000001', MISSING, retries=(0.01, 0.01, 0.01))
        self.assertEqual(len(self.posted), 1, f'one card, not one per retry: {len(self.posted)}')
        self.assertNotIn('1/3', self.last(), 'the customer did nothing wrong')
        self.assertIsNotNone(await self.s.deposits.pending_for(CUSTOMER), 'the payment is on record')
        self.assertFalse(await self.s.deposits.verification_failures(CUSTOMER),
                         'a slow receipt must not cost an attempt')

    async def test_correcting_a_mistyped_transaction_id_still_credits(self):
        """The Fix button has to land back on the same deposit, method and amount.

        Clearing the whole conversation here — rather than just the step — dropped the
        method and the amount, and the corrected transaction id arrived in an expired
        session with nothing credited.
        """
        await self.submit(120, 'BKTYPO0001', MISSING)
        stuck = await self.s.deposits.pending_for(CUSTOMER)
        self.assertIsNotNone(stuck)

        await self.tap(data=f"dep_fix_trx_{stuck['id']}")
        self.assertIsNone(await self.s.deposits.pending_for(CUSTOMER), 'the wait is called off')

        await self.s.zinipay.http.aclose()
        async with self.gateway(receipt(120, 'BKGOOD0001')) as client:
            self.s.zinipay.http = client
            self.written.clear()
            await self.tap(text='BKGOOD0001')

        self.assertEqual(await self.balance(), 120.0, self.last())

    async def test_the_fix_button_only_works_on_your_own_waiting_deposit(self):
        await self.submit(120, 'BKTYPO0002', MISSING)
        stuck = await self.s.deposits.pending_for(CUSTOMER)
        self.assertFalse(await self.s.deposits.cancel_awaiting_sms(stuck['id'], CUSTOMER + 1))
        self.assertIsNotNone(await self.s.deposits.pending_for(CUSTOMER))


if __name__ == '__main__':
    unittest.main()
