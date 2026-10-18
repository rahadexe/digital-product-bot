"""Customer-copy contracts and real-DB optional notification delivery checks."""

from __future__ import annotations

import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import asyncpg
import pytest

from app.bot.customer_copy import order_refunded, wallet_updated
from app.bot.handlers.deposit import _render_instant_invoice, confirm_cancel_instant_payment
from app.bot.handlers.help_guide import FAQ_ITEMS
from app.bot.handlers.profile import handle_notification_toggle, show_referral_info
from app.bot.keyboards import get_notification_settings_keyboard
from app.core.i18n import t


def test_wallet_confirmation_is_short_and_keeps_financial_reference():
    text = wallet_updated(500, 650, "৳", 42)
    assert text.splitlines()[0] == "<b>Wallet updated</b>"
    assert "500" in text and "650" in text and "D42" in text
    assert len(text.splitlines()) == 4


def test_refund_keeps_reference_and_escapes_product_title():
    text = order_refunded(9, "VPN <private> & pro", 150, "৳")
    assert "Refunded · O9" in text
    assert "&lt;private&gt; &amp;" in text
    assert "150" in text and "returned to your wallet" in text


def test_pending_does_not_claim_payment_received():
    text = t("status_pending_msg", "en").lower()
    assert "verification" in text and "do not pay again" in text
    assert "payment received" not in text


@pytest.mark.parametrize("enabled", [True, False])
def test_optional_toggle_is_the_only_customer_notification_switch(enabled):
    keyboard = get_notification_settings_keyboard({"notify_news": enabled})
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        "notif_toggle_notify_news", "open_account",
    ]
    assert buttons[0].text == f"News & Offers: {'On' if enabled else 'Off'}"


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["notify_orders", "notify_deposits", "unknown"])
async def test_old_or_forged_essential_toggle_does_not_change_preferences(key):
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=101),
        data=f"notif_toggle_{key}",
        answer=AsyncMock(),
    )
    services = SimpleNamespace(users=SimpleNamespace(toggle_notification_preference=AsyncMock()))
    await handle_notification_toggle(query, services)
    services.users.toggle_notification_preference.assert_not_awaited()
    assert "stay on" in query.answer.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,amount", [(True, 3), (False, 3), (True, 0)])
async def test_referral_copy_matches_reward_state_and_shares_one_encoded_link(enabled, amount):
    connection = SimpleNamespace(fetchrow=AsyncMock(return_value={
        "total_invited": 4, "total_earned": 12,
    }))
    context = AsyncMock()
    context.__aenter__.return_value = connection
    services = SimpleNamespace(
        users=SimpleNamespace(get=AsyncMock(), get_language=AsyncMock(return_value="en")),
        settings=SimpleNamespace(
            get=AsyncMock(side_effect=lambda key: "৳" if key == "currency_symbol" else "Shop & Co"),
            number=AsyncMock(side_effect=lambda key: amount if key == "referral_reward_amount" else 125),
            flag=AsyncMock(return_value=enabled),
        ),
        db=SimpleNamespace(connect=lambda: context),
        notifier=SimpleNamespace(bot_username=AsyncMock(return_value="sample_bot")),
    )
    event = SimpleNamespace(from_user=SimpleNamespace(id=101))
    with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as respond:
        await show_referral_info(event, SimpleNamespace(clear=AsyncMock()), services)
    text, keyboard = respond.await_args.args[1:]
    assert "Successful invites: <code>4</code>" in text
    assert ("currently paused" in text) == (not enabled or amount <= 0)
    if enabled and amount > 0:
        assert "required channel check" in text
    share_url = keyboard.inline_keyboard[0][1].url
    query = parse_qs(urlsplit(share_url).query)
    assert query["url"] == ["https://t.me/sample_bot?start=101"]
    assert query["text"] == ["Join Shop & Co"]


def test_referral_help_does_not_equate_link_clicks_with_rewards():
    text = FAQ_ITEMS["referral"]["answer"]["en"]
    assert "not for link clicks" in text
    assert "once per eligible friend" in text


@pytest.mark.asyncio
async def test_checkout_has_short_consistent_actions_without_instant_credit_promise():
    services = SimpleNamespace(settings=SimpleNamespace(get=AsyncMock(return_value="৳")))
    text, keyboard = await _render_instant_invoice(
        {"reference": "SM0123456789ABCDEF", "pay_amount": 500, "payment_url": "https://example.com/pay"},
        services,
    )
    assert "Awaiting payment" in text
    assert "after verification" in text
    assert "instantly" not in text
    assert [row[0].text for row in keyboard.inline_keyboard] == [
        "Pay ৳500.00", "Payment Done", "Cancel Payment",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "cancelled"])
async def test_cancellation_reply_never_calls_completed_payment_cancelled(status):
    reference = "SM0123456789ABCDEF"
    query = SimpleNamespace(
        data=f"inst_cancfm_{reference}", from_user=SimpleNamespace(id=101),
        answer=AsyncMock(), message=SimpleNamespace(edit_text=AsyncMock()),
    )
    services = SimpleNamespace(
        payments=SimpleNamespace(cancel_invoice=AsyncMock(return_value={
            "status": status, "credit_amount": 100,
        })),
        settings=SimpleNamespace(get=AsyncMock(return_value="৳"), number=AsyncMock(return_value=125)),
        users=SimpleNamespace(get=AsyncMock(return_value={"balance": 100})),
    )
    await confirm_cancel_instant_payment(query, SimpleNamespace(), services)
    if status == "completed":
        assert query.answer.await_args.args[0] == "Payment already verified."
        assert "cancelled" not in query.message.edit_text.await_args.args[0].lower()
    else:
        assert "contact Support before paying again" in query.message.edit_text.await_args.args[0]


DSN = os.environ.get("TEST_DATABASE_URL", "")


@unittest.skipUnless(DSN, "Set TEST_DATABASE_URL to a disposable local PostgreSQL instance")
class NotificationDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        if urlsplit(DSN).hostname not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError("Tests refuse non-local databases")
        from app.core.config import Settings
        from app.db import Database
        from app.db.migrations import migrate
        from app.services import build_services

        self.schema = "copy_" + uuid.uuid4().hex[:12]
        self.db = Database(DSN, schema=self.schema, max_size=8)
        await migrate(self.db)
        self.services = build_services(
            Settings(
                _env_file=None, app_env="testing", database_url=DSN, bot_token="",
                admin_password="local-test-only", secret_key="copy-tests" * 6,
            ),
            db=self.db, use_telegram=False,
        )
        for user_id in (101, 102):
            await self.services.users.sync_profile(user_id, first_name="Test")

    async def asyncTearDown(self):
        await self.services.close()
        connection = await asyncpg.connect(DSN)
        try:
            await connection.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        finally:
            await connection.close()

    async def test_legacy_false_flags_cannot_disable_essential_updates(self):
        async with self.db.connect() as conn:
            await conn.execute(
                "INSERT INTO user_notification_preferences "
                "(tg_user_id,notify_orders,notify_deposits,notify_news) VALUES(101,FALSE,FALSE,FALSE)"
            )
        prefs = await self.services.users.get_notification_preferences(101)
        self.assertEqual(prefs, {"notify_orders": True, "notify_deposits": True, "notify_news": False})
        for key in ("notify_orders", "notify_deposits", "not_a_column"):
            self.assertEqual(await self.services.users.toggle_notification_preference(101, key), prefs)

    async def test_broadcast_recipient_count_and_queue_honor_news_opt_out(self):
        await self.services.users.toggle_notification_preference(101, "notify_news")
        self.assertEqual(await self.services.delivery.recipient_count(), 1)
        job = await self.services.delivery.enqueue_broadcast("New offers")
        self.assertEqual(job["total"], 1)
        message = await self.services.delivery.claim_next()
        self.assertEqual(message["tg_user_id"], 102)
        self.assertEqual(message["broadcast_id"], job["id"])

    async def test_opt_out_after_queue_cancels_news_but_not_essential_message(self):
        await self.services.delivery.enqueue_broadcast("News")
        await self.services.users.toggle_notification_preference(101, "notify_news")
        async with self.db.connect() as conn:
            essential_id = await conn.fetchval(
                "INSERT INTO outbox(tg_user_id,text) VALUES(101,'Wallet updated') RETURNING id"
            )
        messages = [await self.services.delivery.claim_next(), await self.services.delivery.claim_next()]
        self.assertIn(essential_id, [message["id"] for message in messages])
        async with self.db.connect() as conn:
            status = await conn.fetchval(
                "SELECT status FROM outbox WHERE tg_user_id=101 AND broadcast_id IS NOT NULL"
            )
        self.assertEqual(status, "cancelled")

    async def test_worker_rechecks_opt_out_after_claim(self):
        from app.workers.delivery import DeliveryWorker

        await self.services.delivery.enqueue_broadcast("News")
        message = await self.services.delivery.claim_next()
        await self.services.users.toggle_notification_preference(message["tg_user_id"], "notify_news")
        bot = SimpleNamespace(send_message=AsyncMock())
        with patch.object(self.services.delivery, "claim_next", AsyncMock(return_value=message)):
            self.assertTrue(await DeliveryWorker(self.services.delivery, bot).step())
        bot.send_message.assert_not_awaited()
        async with self.db.connect() as conn:
            self.assertEqual(await conn.fetchval("SELECT status FROM outbox WHERE id=$1", message["id"]), "cancelled")

    async def test_reenable_news_applies_to_future_broadcasts(self):
        await self.services.users.toggle_notification_preference(101, "notify_news")
        await self.services.users.toggle_notification_preference(101, "notify_news")
        job = await self.services.delivery.enqueue_broadcast("News")
        self.assertEqual(job["total"], 2)

    async def test_restock_obeys_preferences_and_escapes_title(self):
        product = await self.services.catalog.create_product(None, "VPN <private>", price=10)
        await self.services.users.toggle_notification_preference(101, "notify_news")
        async with self.db.connect() as conn:
            await conn.executemany(
                "INSERT INTO restock_notifications(tg_user_id,product_id) VALUES($1,$2)",
                [(101, product), (102, product)],
            )
        with patch.object(self.services.notifier, "bot", SimpleNamespace()), \
                patch.object(self.services.notifier, "send", new_callable=AsyncMock) as send:
            await self.services.inventory.add_stock(product, ["private-test-item"])
            await self.services.notifier.drain()
        self.assertEqual(send.await_count, 1)
        self.assertEqual(send.await_args.args[0], 102)
        self.assertIn("VPN &lt;private&gt;", send.await_args.args[1])

    async def test_delivery_and_waiting_notice_ignore_old_saved_bangla_language(self):
        async with self.db.connect() as conn:
            await conn.execute("UPDATE users SET language='bn' WHERE tg_user_id=101")
            await conn.execute(
                "INSERT INTO user_notification_preferences "
                "(tg_user_id,notify_orders,notify_deposits,notify_news) VALUES(101,FALSE,FALSE,FALSE)"
            )
        await self.services.users.adjust_balance(101, 100)
        for delivery_type in ("instant", "manual"):
            product = await self.services.catalog.create_product(
                None, f"English {delivery_type}", price=10, delivery_type=delivery_type
            )
            if delivery_type == "instant":
                await self.services.inventory.add_stock(product, ["credentials-test"])
            ok, reason, order = await self.services.purchases.purchase(101, product)
            self.assertTrue(ok, reason)
            async with self.db.connect() as conn:
                text = await conn.fetchval(
                    "SELECT text FROM outbox WHERE order_id=$1 OR about_order_id=$1", order["order_id"]
                )
            self.assertFalse(any("\u0980" <= char <= "\u09ff" and char != "\u09f3" for char in text), text)
            if delivery_type == "instant":
                self.assertEqual(text.count("Delivered"), 1)
                self.assertIn("credentials-test", text)
            else:
                self.assertIn("Preparing delivery", text)

    async def test_manual_topup_confirmation_is_kept_even_when_news_is_off(self):
        await self.services.users.toggle_notification_preference(101, "notify_news")
        method = await self.services.deposits.create_method("bKash", "test-account")
        deposit_id = await self.services.deposits.create_request(101, method, 100, "COPYCONFIRM1")
        with patch.object(self.services.notifier, "bot", SimpleNamespace()), \
                patch.object(self.services.notifier, "send", new_callable=AsyncMock) as send:
            approved, reason, _ = await self.services.deposits.approve(deposit_id)
            self.assertTrue(approved, reason)
            await self.services.notifier.drain()
        self.assertEqual(send.await_count, 1)
        self.assertIn("Wallet updated", send.await_args.args[1])
        self.assertIn(f"D{deposit_id}", send.await_args.args[1])
        self.assertNotIn("clears_after", send.await_args.kwargs)

    async def test_all_restock_opt_outs_remain_silent(self):
        product = await self.services.catalog.create_product(None, "VPN", price=10)
        await self.services.users.toggle_notification_preference(101, "notify_news")
        async with self.db.connect() as conn:
            await conn.execute(
                "INSERT INTO restock_notifications(tg_user_id,product_id) VALUES(101,$1)",
                product,
            )
        with patch.object(self.services.notifier, "bot", SimpleNamespace()), \
                patch.object(self.services.notifier, "send", new_callable=AsyncMock) as send:
            await self.services.inventory.add_stock(product, ["test-stock"])
            await self.services.notifier.drain()
        send.assert_not_awaited()
