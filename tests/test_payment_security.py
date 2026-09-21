"""Adversarial tests for the paths that put money in a wallet.

Every test drives the real service against a disposable schema with the gateway
mocked, so what is asserted is the decision the shop makes about a payment, not
the shape of a helper.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
        python -m unittest tests.test_payment_security -v
"""

import os
import unittest
import uuid
from decimal import Decimal
from urllib.parse import urlsplit

import asyncpg
import httpx

from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services
from app.services.deposits import DuplicateTransactionError
from app.services.errors import InvalidInputError
from app.services.zinipay import _matches_receipt

DSN = os.environ.get('TEST_DATABASE_URL', '')
CUSTOMER = 100200300
INTRUDER = 100200999


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
        result = await self._claim({'success': True, 'data': {'id': 77, 'amount': 5, 'trxID': 'TRX0000001'}})
        self.assertFalse(result.get('auto_verified'))
        self.assertEqual(await self.balance(), 0.0)

    async def test_receipt_for_a_different_transaction_does_not_credit(self):
        result = await self._claim({'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'SOMEONE-ELSE'}})
        self.assertFalse(result.get('auto_verified'))
        self.assertEqual(await self.balance(), 0.0)

    async def test_matching_receipt_credits_once(self):
        body = {'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001'}}
        result = await self._claim(body)
        self.assertTrue(result.get('auto_verified'), result)
        self.assertEqual(await self.balance(), 500.0)

        # The same transaction id a second time must not pay twice.
        with self.assertRaises(DuplicateTransactionError):
            await self._claim(body)
        self.assertEqual(await self.balance(), 500.0)

    async def test_transaction_already_used_by_another_customer(self):
        await self._claim({'success': True, 'data': {'id': 77, 'amount': 500, 'trxID': 'TRX0000001'}})
        self.assertEqual(await self.balance(), 500.0)
        await self.s.zinipay.http.aclose()
        async with gateway({'success': True, 'data': {'id': 78, 'amount': 500, 'trxID': 'TRX0000001'}}) as client:
            self.s.zinipay.http = client
            with self.assertRaises(DuplicateTransactionError):
                await self.s.zinipay.claim(INTRUDER, self.method, 500, 'TRX0000001', quoted_rate=1.0)
        self.assertEqual(await self.balance(INTRUDER), 0.0)

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
