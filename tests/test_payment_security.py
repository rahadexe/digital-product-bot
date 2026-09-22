"""Adversarial tests for the paths that put money in a wallet.

Every test drives the real service against a disposable schema with the gateway
mocked, so what is asserted is the decision the shop makes about a payment, not
the shape of a helper.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
        python -m unittest tests.test_payment_security -v
"""

import asyncio
import datetime
import os
import re
import unittest
import uuid
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlsplit

import asyncpg
import httpx

from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services
from app.services import zinipay as zinipay_module
from app.services.binance import PAID_BEFORE_CLAIM_HOURS, BinanceDepositService
from app.services.deposits import DuplicateTransactionError
from app.services.errors import InvalidInputError
from app.services.zinipay import _matches_receipt

DSN = os.environ.get('TEST_DATABASE_URL', '')
CUSTOMER = 100200300
INTRUDER = 100200999


def plain_text(value):
    """The words of a message, without the markup."""
    return re.sub(r'<[^>]+>', '', value or '')
def gateway(body, status=200):
    """An httpx client that answers every call with one body."""
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)))


class ReceiptMatching(unittest.TestCase):
    """A receipt has to say what it paid. Silence is not agreement."""

    def test_states_amount_and_transaction(self):
        self.assertTrue(_matches_receipt({'amount': 50, 'trxID': 'ABC123'}, 50, 'ABC123'))
        self.assertTrue(_matches_receipt({'amount': 50, 'transactionId': 'abc123'}, 50, 'ABC123'))

    def test_contradiction_is_rejected(self):
        self.assertFalse(_matches_receipt({'amount': 5, 'trxID': 'ABC123'}, 50, 'ABC123'))
        self.assertFalse(_matches_receipt({'amount': 50, 'trxID': 'OTHER'}, 50, 'ABC123'))
        self.assertFalse(_matches_receipt({'amount': 50, 'trxID': 'ABC123', 'transactionId': 'OTHER'}, 50, 'ABC123'))

    def test_silence_is_rejected(self):
        # These all used to pass: the check only compared the fields that happened
        # to be present, so a body naming neither agreed with every payment.
        self.assertFalse(_matches_receipt({}, 50, 'ABC123'))
        self.assertFalse(_matches_receipt({'id': 9}, 50, 'ABC123'))
        self.assertFalse(_matches_receipt({'trxID': 'ABC123'}, 50, 'ABC123'))
        self.assertFalse(_matches_receipt({'amount': 50}, 50, 'ABC123'))
        self.assertFalse(_matches_receipt({'amount': None, 'trxID': 'ABC123'}, 50, 'ABC123'))
        self.assertFalse(_matches_receipt({'amount': 'NaN', 'trxID': 'ABC123'}, 50, 'ABC123'))



class BinanceClaimWindow(unittest.TestCase):
    """How old a Binance transfer may be and still be credited without a human."""

    @staticmethod
    def _claimed_now(hours_before):
        now = datetime.datetime.now(datetime.timezone.utc)
        paid = now - datetime.timedelta(hours=hours_before)
        return BinanceDepositService._arrived_in_time({'created_at': now}, int(paid.timestamp() * 1000))

    def test_a_payment_made_just_now_is_in_time(self):
        self.assertTrue(self._claimed_now(0))

    def test_a_payment_from_yesterday_is_still_in_time(self):
        # One day used to be the whole allowance, so paying at night and claiming the
        # next evening became a manual ticket.
        self.assertTrue(self._claimed_now(30))
        self.assertTrue(self._claimed_now(PAID_BEFORE_CLAIM_HOURS - 1))

    def test_old_history_is_left_for_a_human(self):
        self.assertFalse(self._claimed_now(PAID_BEFORE_CLAIM_HOURS + 1))
        self.assertFalse(self._claimed_now(24 * 14))

    def test_a_transfer_binance_gives_no_time_for_is_allowed(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        self.assertTrue(BinanceDepositService._arrived_in_time({'created_at': now}, 0))
        self.assertFalse(BinanceDepositService._arrived_in_time({'created_at': now}, 'nonsense'))

@unittest.skipUnless(DSN, 'Set TEST_DATABASE_URL to a disposable local PostgreSQL instance')
class PaymentSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise unittest.SkipTest('This suite only runs against a local database.')
        self.schema = 'paysec_' + uuid.uuid4().hex[:12]
        self.config = Settings(
            _env_file=None, app_env='testing', database_url=DSN,
            secret_key='payment-security-' * 4, admin_password='local-test-password', bot_token='',
        )
        self.db = Database(DSN, schema=self.schema, max_size=6)
        await migrate(self.db)
        self.s = build_services(self.config, db=self.db, use_telegram=False)
        await self.s.settings.update({'zinipay_enabled': '1', 'zinipay_api_key': 'test-key',
                                      'zinipay_web_gateway_enabled': '1', 'zinipay_brand_url': 'https://shop.example'})
        await self.s.users.sync_profile(CUSTOMER, first_name='Customer')
        await self.s.users.sync_profile(INTRUDER, first_name='Intruder')
        self.method = await self.s.deposits.create_method('bKash', '01700000000')

    async def asyncTearDown(self):
        self.s.notifier.bot = None   # a stand-in bot has no session to close
        await self.s.close()
        admin = Database(DSN)
        async with admin.connect() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await admin.close()

    async def balance(self, tg_user_id=CUSTOMER):
        async with self.db.connect() as conn:
            return float(await conn.fetchval('SELECT balance FROM users WHERE tg_user_id=$1', tg_user_id) or 0)

    # ---- in-bot transaction verification -------------------------------------

    async def _claim(self, body, amount=500, trx='TRX0000001'):
        await self.s.zinipay.http.aclose()
        async with gateway(body) as client:
            self.s.zinipay.http = client
            return await self.s.zinipay.claim(CUSTOMER, self.method, amount, trx, quoted_rate=1.0)

    async def test_receipt_that_names_nothing_does_not_credit(self):
        """The gateway says yes but names no amount and no transaction."""
        result = await self._claim({'success': True, 'data': {'id': 77}})
        self.assertFalse(result.get('auto_verified'))
        self.assertEqual(await self.balance(), 0.0)
        async with self.db.connect() as conn:
            status = await conn.fetchval('SELECT status FROM deposits WHERE id=$1', result['deposit_id'])
        self.assertEqual(status, 'pending', 'an unproven payment must wait for a human')

    async def test_receipt_for_a_different_amount_does_not_credit(self):
        result = await self._claim({'success': True, 'data': {'id': 77, 'amount': 5, 'trxID': 'TRX0000001', 'provider': 'bKash'}})
        self.assertFalse(result.get('auto_verified'))
        self.assertEqual(await self.balance(), 0.0)

    async def test_receipt_for_a_different_transaction_does_not_credit(self):
        result = await self._claim({'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'SOMEONE-ELSE', 'provider': 'bKash'}})
        self.assertFalse(result.get('auto_verified'))
        self.assertEqual(await self.balance(), 0.0)

    async def test_matching_receipt_credits_once(self):
        body = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'bKash'}}
        result = await self._claim(body)
        self.assertTrue(result.get('auto_verified'), result)
        self.assertEqual(await self.balance(), 500.0)

        # The same transaction id a second time must not pay twice.
        with self.assertRaises(DuplicateTransactionError):
            await self._claim(body)
        self.assertEqual(await self.balance(), 500.0)

    async def test_transaction_already_used_by_another_customer(self):
        await self._claim({'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'bKash'}})
        self.assertEqual(await self.balance(), 500.0)
        await self.s.zinipay.http.aclose()
        async with gateway({'success': True, 'data': {'id': 78, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'bKash'}}) as client:
            self.s.zinipay.http = client
            with self.assertRaises(DuplicateTransactionError):
                await self.s.zinipay.claim(INTRUDER, self.method, 500, 'TRX0000001', quoted_rate=1.0)
        self.assertEqual(await self.balance(INTRUDER), 0.0)

    # ---- what the gateway says when it refuses --------------------------------

    async def _verify(self, body, status):
        await self.s.zinipay.http.aclose()
        async with gateway(body, status) as client:
            self.s.zinipay.http = client
            return await self.s.zinipay.verify(500, 'TRX0000001')

    async def test_a_refusal_is_read_not_discarded(self):
        """ZiniPay answers every refusal with "data": null.

        Insisting that "data" be an object turned all of these into one useless
        "Malformed gateway response", so the caller could not tell a receipt that has
        not synced yet from a wrong amount, and never retried.
        """
        cases = {
            'not_found': ({'success': False, 'code': 'REQUEST_FAILED',
                           'message': 'Transaction not found', 'data': None}, 404),
            'amount_mismatch': ({'success': False,
                                 'message': 'Amount must be equal to the receipt', 'data': None}, 400),
            'already_used': ({'success': False,
                              'message': 'This transaction is already used', 'data': None}, 400),
            'credits_error': ({'success': False, 'code': 'INSUFFICIENT_CREDITS',
                               'message': '', 'data': None}, 402),
        }
        for expected, (body, status) in cases.items():
            with self.subTest(expected):
                result = await self._verify(body, status)
                self.assertFalse(result['ok'])
                self.assertEqual(result['reason'], expected)

    async def test_a_body_that_cannot_be_read_is_still_refused(self):
        self.assertEqual((await self._verify({'success': False, 'data': ['not', 'an', 'object']}, 400))['reason'], 'error')
        self.assertEqual((await self._verify(['not an object at all'], 400))['reason'], 'error')

    async def test_a_receipt_that_has_not_synced_yet_is_waited_for(self):
        """The bank SMS reaches the gateway seconds after the customer pays."""
        body = {'success': False, 'code': 'REQUEST_FAILED', 'message': 'Transaction not found', 'data': None}
        waits = []

        async def on_wait(waited, total):
            waits.append((waited, total))

        with patch.object(zinipay_module, 'SMS_SYNC_RETRY_DELAYS', (0.01, 0.01, 0.01)):
            await self.s.zinipay.http.aclose()
            async with gateway(body, 404) as client:
                self.s.zinipay.http = client
                result = await self.s.zinipay.claim(CUSTOMER, self.method, 500, 'TRX0000001',
                                                    quoted_rate=1.0, on_sync_wait=on_wait)

        self.assertEqual(len(waits), 3, 'the customer should be told we are still checking')
        self.assertTrue(result.get('pending_sync'), result)
        self.assertFalse(result.get('fallback_manual'), 'a missing receipt is not an admin job yet')
        self.assertEqual(await self.balance(), 0.0, 'nothing is credited until the receipt is seen')

    # ---- a receipt that arrives after the customer does -----------------------

    async def _awaiting(self, amount=500, trx='TRX0000001'):
        """Submit a TrxID the gateway has not seen yet."""
        missing = {'success': False, 'code': 'REQUEST_FAILED', 'message': 'Transaction not found', 'data': None}
        with patch.object(zinipay_module, 'SMS_SYNC_RETRY_DELAYS', (0.01,)):
            await self.s.zinipay.http.aclose()
            async with gateway(missing, 404) as client:
                self.s.zinipay.http = client
                return await self.s.zinipay.claim(CUSTOMER, self.method, amount, trx, quoted_rate=1.0)

    async def _due_now(self, deposit_id):
        async with self.db.connect() as conn:
            await conn.execute("UPDATE deposits SET next_check_at=now()-interval '1 minute' WHERE id=$1", deposit_id)

    async def test_a_receipt_still_in_transit_is_filed_not_refused(self):
        """The bank SMS reaches the gateway after the customer submits the TrxID.

        Telling them it does not exist, and spending one of three attempts on it, was
        wrong about the most ordinary case there is.
        """
        result = await self._awaiting()
        self.assertTrue(result.get('pending_sync'), result)
        self.assertIsNone(result.get('error'), 'this is not the customer getting something wrong')
        self.assertEqual(await self.balance(), 0.0, 'nothing is credited on no evidence')

        pending = await self.s.deposits.pending_for(CUSTOMER)
        self.assertIsNotNone(pending, 'the payment is on record so it cannot be lost')
        async with self.db.connect() as conn:
            state = await conn.fetchval('SELECT status FROM payment_verification_attempts WHERE deposit_id=$1',
                                        result['deposit_id'])
        self.assertEqual(state, 'awaiting_sms')

    async def test_the_wallet_is_credited_once_the_receipt_lands(self):
        result = await self._awaiting()
        await self._due_now(result['deposit_id'])

        arrived = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'bKash'}}
        await self.s.zinipay.http.aclose()
        async with gateway(arrived) as client:
            self.s.zinipay.http = client
            await self.s.zinipay.recover()

        self.assertEqual(await self.balance(), 500.0, 'nobody had to touch this')
        async with self.db.connect() as conn:
            row = await conn.fetchrow('SELECT d.status, a.status AS attempt FROM deposits d '
                                      'JOIN payment_verification_attempts a ON a.deposit_id=d.id WHERE d.id=$1',
                                      result['deposit_id'])
        self.assertEqual(row['status'], 'approved')
        self.assertEqual(row['attempt'], 'completed')

    async def test_a_receipt_that_never_arrives_goes_to_a_person(self):
        result = await self._awaiting()
        async with self.db.connect() as conn:
            await conn.execute("UPDATE deposits SET next_check_at=now()-interval '1 minute' WHERE id=$1",
                               result['deposit_id'])
            await conn.execute("UPDATE payment_verification_attempts SET created_at=now()-interval '1 hour' "
                               'WHERE deposit_id=$1', result['deposit_id'])

        missing = {'success': False, 'code': 'REQUEST_FAILED', 'message': 'Transaction not found', 'data': None}
        await self.s.zinipay.http.aclose()
        async with gateway(missing, 404) as client:
            self.s.zinipay.http = client
            await self.s.zinipay.recover()

        self.assertEqual(await self.balance(), 0.0)
        async with self.db.connect() as conn:
            row = await conn.fetchrow('SELECT d.status, d.admin_note, a.status AS attempt FROM deposits d '
                                      'JOIN payment_verification_attempts a ON a.deposit_id=d.id WHERE d.id=$1',
                                      result['deposit_id'])
        self.assertEqual(row['status'], 'pending', 'still the customer money, waiting on a human')
        self.assertEqual(row['attempt'], 'review')
        self.assertIn('mistyped', row['admin_note'])

    async def test_a_customer_can_take_back_a_mistyped_transaction_id(self):
        result = await self._awaiting(trx='TRX0000OOPS')
        self.assertTrue(await self.s.deposits.cancel_awaiting_sms(result['deposit_id'], CUSTOMER))
        self.assertIsNone(await self.s.deposits.pending_for(CUSTOMER), 'they are free to submit the right one')

        arrived = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'bKash'}}
        await self.s.zinipay.http.aclose()
        async with gateway(arrived) as client:
            self.s.zinipay.http = client
            second = await self.s.zinipay.claim(CUSTOMER, self.method, 500, 'TRX0000001', quoted_rate=1.0)
        self.assertTrue(second.get('auto_verified'), second)
        self.assertEqual(await self.balance(), 500.0)

    async def test_nobody_else_can_cancel_your_deposit(self):
        result = await self._awaiting()
        self.assertFalse(await self.s.deposits.cancel_awaiting_sms(result['deposit_id'], INTRUDER))
        self.assertIsNotNone(await self.s.deposits.pending_for(CUSTOMER))

    async def test_an_approved_deposit_cannot_be_cancelled_from_the_button(self):
        result = await self._awaiting()
        await self._due_now(result['deposit_id'])
        arrived = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'bKash'}}
        await self.s.zinipay.http.aclose()
        async with gateway(arrived) as client:
            self.s.zinipay.http = client
            await self.s.zinipay.recover()
        self.assertFalse(await self.s.deposits.cancel_awaiting_sms(result['deposit_id'], CUSTOMER))
        self.assertEqual(await self.balance(), 500.0)

    # ---- how often an owner is interrupted ------------------------------------

    def _watch_admin(self):
        """Collect the admin alerts a flow sends."""
        seen = []

        async def spy(text, event='general', keyboard=None):
            seen.append(plain_text(text).splitlines()[0][:60])
            return True

        self.s.notifier.send_admin = spy
        # in_background drops its work when there is no bot, and the alert on a
        # brand-new request goes out that way.
        self.s.notifier.bot = self.s.notifier.bot or object()
        return seen

    async def test_an_auto_verified_deposit_does_not_page_the_owner(self):
        """It was approved before they could read it, so asking them to approve it is noise."""
        alerts = self._watch_admin()
        result = await self._claim({'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'bKash'}})
        self.assertTrue(result.get('auto_verified'), result)
        await asyncio.sleep(0.2)   # the alert would go out in the background
        self.assertEqual(alerts, [], 'nothing needed a person')

    async def test_a_payment_waiting_for_its_receipt_does_not_page_the_owner_yet(self):
        alerts = self._watch_admin()
        await self._awaiting()
        await asyncio.sleep(0.2)
        self.assertEqual(alerts, [], 'it will most likely credit itself')

    async def test_giving_up_on_a_receipt_pages_the_owner_once(self):
        result = await self._awaiting()
        async with self.db.connect() as conn:
            await conn.execute("UPDATE deposits SET next_check_at=now()-interval '1 minute' WHERE id=$1",
                               result['deposit_id'])
            await conn.execute("UPDATE payment_verification_attempts SET created_at=now()-interval '1 hour' "
                               'WHERE deposit_id=$1', result['deposit_id'])
        alerts = self._watch_admin()
        missing = {'success': False, 'code': 'REQUEST_FAILED', 'message': 'Transaction not found', 'data': None}
        await self.s.zinipay.http.aclose()
        async with gateway(missing, 404) as client:
            self.s.zinipay.http = client
            await self.s.zinipay.recover()
        await asyncio.sleep(0.2)
        self.assertEqual(len(alerts), 1, alerts)
        self.assertIn('Deposit Request', alerts[0])

    async def test_a_gateway_that_cannot_answer_still_pages_the_owner(self):
        """Nothing automatic can happen here, so the deposit needs a person straight away."""
        alerts = self._watch_admin()
        broken = {'success': False, 'code': 'INSUFFICIENT_CREDITS', 'message': 'Out of credits', 'data': None}
        result = await self._claim(broken)
        self.assertTrue(result.get('fallback_manual'), result)
        await asyncio.sleep(0.2)
        self.assertEqual(len(alerts), 1, alerts)

    # ---- a bKash deposit is paid by a bKash transaction ----------------------

    async def _claim_recording(self, body, amount=500, trx='TRX0000001', status=200):
        """Claim, and report which gateway endpoints were called."""
        calls = []

        def answer(request):
            calls.append(request.url.path.rsplit('/', 1)[-1])
            return httpx.Response(status, json=body)

        await self.s.zinipay.http.aclose()
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
            self.s.zinipay.http = client
            result = await self.s.zinipay.claim(CUSTOMER, self.method, amount, trx, quoted_rate=1.0)
        return result, calls

    async def test_a_nagad_transaction_cannot_pay_a_bkash_deposit(self):
        """ZiniPay searches every wallet; the shop checks the receipt names the one chosen."""
        nagad = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'Nagad'}}
        result, calls = await self._claim_recording(nagad)
        self.assertEqual(result.get('error'), 'wrong_method', result)
        self.assertEqual(result.get('paid_with'), 'Nagad')
        self.assertEqual(await self.balance(), 0.0)
        self.assertNotIn('confirm', calls, 'the transaction must not be consumed, so it can pay the right method')
        self.assertIsNone(await self.s.deposits.pending_for(CUSTOMER))

    async def test_the_wallet_name_is_compared_loosely(self):
        from app.services.zinipay import _wallet
        self.assertEqual({_wallet(p) for p in ('bKash', 'BKASH', 'bkash personal', 'b-Kash')}, {'bkash'})
        self.assertEqual(_wallet('Nagad'), 'nagad')
        self.assertEqual(_wallet('Mobile Banking'), '', 'a method that names no wallet is not checked')
        shouting = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'BKASH'}}
        result, _ = await self._claim_recording(shouting)
        self.assertTrue(result.get('auto_verified'), result)

    async def test_a_receipt_that_names_no_wallet_goes_to_a_person(self):
        silent = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001'}}
        result, calls = await self._claim_recording(silent)
        self.assertTrue(result.get('fallback_manual'), result)
        self.assertNotIn('confirm', calls)
        self.assertEqual(await self.balance(), 0.0)

    async def test_a_transaction_id_the_shop_has_seen_is_refused_at_once(self):
        """Even a rejected one: no gateway call, so no receipt wait."""
        await self.s.users.sync_profile(INTRUDER, first_name='Intruder')
        earlier = await self.s.deposits.create_request(INTRUDER, self.method, 300, 'TRXSEEN0001')
        await self.s.deposits.reject(earlier, 'Payment not received')
        calls = []

        def answer(request):
            calls.append(request.url.path)
            return httpx.Response(404, json={'success': False, 'message': 'Transaction not found', 'data': None})

        await self.s.zinipay.http.aclose()
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
            self.s.zinipay.http = client
            with self.assertRaises(DuplicateTransactionError):
                await self.s.zinipay.claim(CUSTOMER, self.method, 500, 'TRXSEEN0001', quoted_rate=1.0)
        self.assertEqual(calls, [], 'the gateway was asked about a transaction id the shop already knew')

    async def test_a_transaction_id_is_used_once_even_by_the_same_customer(self):
        """deposit_transaction_unique: once, whatever became of the deposit that used it."""
        waiting = await self._awaiting(trx='TRXMINE0001')
        self.assertTrue(await self.s.deposits.cancel_awaiting_sms(waiting['deposit_id'], CUSTOMER))
        body = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRXMINE0001', 'provider': 'bKash'}}
        with self.assertRaises(DuplicateTransactionError):
            await self._claim_recording(body, trx='TRXMINE0001')
        self.assertEqual(await self.balance(), 0.0)

    async def test_a_late_receipt_from_the_wrong_wallet_is_not_credited(self):
        result = await self._awaiting()
        await self._due_now(result['deposit_id'])
        alerts = self._watch_admin()
        nagad = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001', 'provider': 'Nagad'}}
        await self.s.zinipay.http.aclose()
        async with gateway(nagad) as client:
            self.s.zinipay.http = client
            await self.s.zinipay.recover()
            await self._due_now(result['deposit_id'])
            await self.s.zinipay.recover()           # a second pass must not alert again
        self.assertEqual(await self.balance(), 0.0)
        self.assertEqual(len(alerts), 1, alerts)
        async with self.db.connect() as conn:
            note = await conn.fetchval('SELECT admin_note FROM deposits WHERE id=$1', result['deposit_id'])
        self.assertIn('Nagad', note)

    # ---- hosted invoices ------------------------------------------------------

    async def _invoice(self, amount=500):
        await self.s.payments.http.aclose()
        created = {'success': True, 'invoice_id': 'INV-1',
                   'payment_url': 'https://secure.zinipay.com/payment/INV-1'}
        async with gateway(created) as client:
            self.s.payments.http = client
            return await self.s.payments.create_invoice(CUSTOMER, amount)

    async def _refresh(self, reference, verify_body):
        await self.s.payments.http.aclose()
        async with gateway(verify_body) as client:
            self.s.payments.http = client
            return await self.s.payments.refresh(reference)

    async def test_forged_callback_cannot_credit(self):
        """The callback carries no signature, so it may only prompt a check."""
        invoice = await self._invoice()
        await self.s.payments.http.aclose()
        # The gateway is asked directly and says the invoice is still unpaid.
        async with gateway({'status': 'PENDING', 'val_id': invoice['reference']}) as client:
            self.s.payments.http = client
            await self.s.payments.handle_webhook('INV-1', invoice['reference'])
        self.assertEqual(await self.balance(), 0.0)

    async def test_completed_for_a_different_invoice_is_refused(self):
        invoice = await self._invoice()
        await self._refresh(invoice['reference'],
                            {'status': 'COMPLETED', 'val_id': 'SM-SOMEONE-ELSE', 'amount': 500})
        self.assertEqual(await self.balance(), 0.0)
        async with self.db.connect() as conn:
            status = await conn.fetchval('SELECT status FROM payment_invoices WHERE reference=$1', invoice['reference'])
        self.assertEqual(status, 'failed')

    async def test_completed_for_the_wrong_amount_is_refused(self):
        invoice = await self._invoice()
        await self._refresh(invoice['reference'],
                            {'status': 'COMPLETED', 'val_id': invoice['reference'], 'amount': 5})
        self.assertEqual(await self.balance(), 0.0)

    async def test_completed_naming_no_invoice_is_refused(self):
        invoice = await self._invoice()
        await self._refresh(invoice['reference'], {'status': 'COMPLETED', 'amount': 500})
        self.assertEqual(await self.balance(), 0.0)

    async def test_matching_completion_credits_once_however_often_it_is_checked(self):
        invoice = await self._invoice()
        body = {'status': 'COMPLETED', 'val_id': invoice['reference'], 'invoice_id': 'INV-1',
                'amount': float(invoice['pay_amount']), 'transaction_id': 'GW-TXN-1'}
        for _ in range(3):
            await self._refresh(invoice['reference'], body)
        self.assertEqual(await self.balance(), 500.0, 'repeated checks must credit exactly once')
        async with self.db.connect() as conn:
            deposits = await conn.fetchval('SELECT count(*) FROM deposits WHERE tg_user_id=$1', CUSTOMER)
        self.assertEqual(deposits, 1)

    async def test_another_customer_cannot_refresh_your_invoice(self):
        invoice = await self._invoice()
        seen = await self.s.payments.refresh(invoice['reference'], tg_user_id=INTRUDER)
        self.assertIsNone(seen, 'an invoice must only be readable by the customer it belongs to')

    async def test_payment_url_from_another_domain_is_refused(self):
        await self.s.payments.http.aclose()
        async with gateway({'success': True, 'invoice_id': 'INV-2',
                            'payment_url': 'https://zinipay.attacker.example/payment/INV-2'}) as client:
            self.s.payments.http = client
            with self.assertRaises(InvalidInputError):
                await self.s.payments.create_invoice(CUSTOMER, 500)
        self.assertEqual(await self.balance(), 0.0)

    # ---- wallet integrity -----------------------------------------------------

    async def test_every_credit_is_recorded_in_the_ledger(self):
        invoice = await self._invoice()
        await self._refresh(invoice['reference'],
                            {'status': 'COMPLETED', 'val_id': invoice['reference'],
                             'amount': float(invoice['pay_amount']), 'transaction_id': 'GW-TXN-9'})
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                'SELECT delta, reason FROM wallet_ledger WHERE tg_user_id=$1 AND delta <> 0 ORDER BY id', CUSTOMER)
        self.assertTrue(any(Decimal(str(r['delta'])) == Decimal('500') for r in rows), rows)

    async def test_ledger_rows_cannot_be_edited_away(self):
        await self.s.users.adjust_balance(CUSTOMER, 100, 'test top-up')
        async with self.db.connect() as conn:
            with self.assertRaises(asyncpg.PostgresError):
                await conn.execute('UPDATE wallet_ledger SET delta = 0 WHERE tg_user_id=$1', CUSTOMER)
            with self.assertRaises(asyncpg.PostgresError):
                await conn.execute('DELETE FROM wallet_ledger WHERE tg_user_id=$1', CUSTOMER)


if __name__ == '__main__':
    unittest.main()
