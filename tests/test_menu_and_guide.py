"""Every menu button and every guide entry point, driven through the real dispatcher.

These two modules had no test at all, and that is where the worst bug of the day lived:
navigate() read five handlers that no longer existed, and because Python evaluates every
value in a dict literal, the lookup raised before it could reach the one being asked for.
From inside any prompt that waits on typed input, every menu button did nothing — and no
linter could see it, because the names are resolved on another module at call time.

So these tests do not check wiring in the abstract. They press every button the keyboard
can show, from a state where a prompt is waiting, and insist something comes back.

    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
    python -m pytest tests/test_menu_and_guide.py
"""

from __future__ import annotations

import asyncio
import datetime
import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import CallbackQuery, Chat, Message, Update, User

DSN = os.environ.get("TEST_DATABASE_URL", "")

ADMIN = 900100300
CUSTOMER = 900100777


@unittest.skipUnless(DSN, "Set TEST_DATABASE_URL to a disposable local PostgreSQL instance")
class MenuAndGuideTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.enterContext(patch.object(Message, 'delete', new_callable=AsyncMock))
        self.enterContext(patch.object(Bot, 'delete_message', new_callable=AsyncMock))
        from app.bot.app import create_dispatcher
        from app.bot.storage import PostgresStorage
        from app.core.config import Settings
        from app.db import Database
        from app.db.migrations import migrate
        from app.services import build_services

        self.schema = "menu_" + uuid.uuid4().hex[:10]
        config = Settings(
            _env_file=None, app_env="testing", database_url=DSN,
            secret_key="menu-and-guide-tests" * 3, admin_password="local-test-password",
            bot_token="",
        )
        # The routers are module-level singletons, so a second dispatcher in the same
        # process refuses to adopt them. Each test builds its own, against its own
        # schema, so release them from the previous one first.
        from app.bot.handlers import admin, deposit, help_guide, navigation, profile, reseller_apply, search, shop, start
        for module in (navigation, admin, start, shop, deposit, profile, reseller_apply, help_guide, search):
            module.router._parent_router = None

        self.db = Database(DSN, schema=self.schema, max_size=8)
        await migrate(self.db)
        self.services = build_services(config, db=self.db, use_telegram=False)
        self.dp = create_dispatcher(self.services, storage=PostgresStorage(self.db))
        self.bot = Bot(
            token="111111:AAtestAAtestAAtestAAtestAAtestAAtest",
            default=DefaultBotProperties(parse_mode="HTML"),
        )
        self.sent: list[dict] = []

        await self.services.users.sync_profile(ADMIN, first_name="Owner")
        await self.services.users.sync_profile(CUSTOMER, first_name="Rafi", username="rafi")
        await self.services.users.set_language(CUSTOMER, "en")
        await self.services.settings.update({
            "admin_tg_ids": str(ADMIN),
            "force_join_enabled": "0",
            "support_username": "@shopsupport",
        })
        category = await self.services.catalog.create_category("Buy VPN")
        product = await self.services.catalog.create_product(
            category, "Fast VPN 30d", price=100, delivery_type="instant")
        await self.services.inventory.add_stock(product, ["key-1", "key-2"])
        await self.services.deposits.create_method("bKash", "01700000000")

    async def asyncTearDown(self) -> None:
        from app.db import Database

        await self.bot.session.close()
        await self.services.close()
        admin_db = Database(DSN)
        async with admin_db.connect() as conn:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        await admin_db.close()

    # ---- driving the dispatcher -------------------------------------------------

    def _clear_throttle(self) -> None:
        """A real customer taps at human speed; a test fires instantly."""
        for middleware in (list(self.dp.message.outer_middleware)
                           + list(self.dp.callback_query.outer_middleware)):
            buckets = getattr(middleware, "_buckets", None)
            if buckets is not None:
                buckets.clear()
            actions = getattr(middleware, "_last_actions", None)
            if actions is not None:
                actions.clear()

    async def _feed(self, *, text: str | None = None, data: str | None = None,
                    user_id: int = CUSTOMER) -> list[dict]:
        async def capture(inner, body=None, **kwargs):
            self.sent.append({"text": body if body is not None else kwargs.get("text"), "reply_markup": kwargs.get("reply_markup")})
            return inner

        async def capture_alert(inner, body=None, **kwargs):
            self.sent.append({"alert": body})

        self._clear_throttle()
        self.sent.clear()
        now = datetime.datetime.now(datetime.timezone.utc)
        user = User(id=user_id, is_bot=False, first_name="Rafi", username="rafi")
        message = Message(message_id=1, date=now, chat=Chat(id=user_id, type="private"),
                          from_user=user, text=text or "x")
        if data is not None:
            update = Update(update_id=1, callback_query=CallbackQuery(
                id="1", from_user=user, chat_instance="c", data=data, message=message))
        else:
            update = Update(update_id=1, message=message)
        with patch.object(Message, "answer", capture), \
             patch.object(Message, "edit_text", capture), \
             patch.object(CallbackQuery, "answer", capture_alert):
            await self.dp.feed_update(self.bot, update)
        return list(self.sent)

    async def _strand_in_a_prompt(self) -> None:
        """Leave the customer where the bot is waiting for them to type something."""
        from app.bot.handlers.deposit import DepositStates

        context = self.dp.fsm.get_context(self.bot, chat_id=CUSTOMER, user_id=CUSTOMER)
        await context.set_state(DepositStates.waiting_for_amount)
        await context.update_data(method_id=1, method_name="bKash", min_deposit=1.0)

    # ---- the tests --------------------------------------------------------------

    async def test_every_menu_button_answers_from_inside_a_prompt(self):
        """The bug that started this: a dict of handlers built from names that had moved.

        Every value in that dict is evaluated before any of them is chosen, so one stale
        name silenced every button at once. Pressing them one at a time from a waiting
        prompt is the only thing that would have caught it.
        """
        from app.bot.handlers.navigation import NAVIGATION_TEXTS

        buttons = sorted({label for label, action in NAVIGATION_TEXTS.items()
                          if action not in {"cancel", "admin"} and not label.startswith("/")})
        self.assertGreater(len(buttons), 5, "the menu should have several buttons to press")

        silent, crashed = [], []
        for label in buttons:
            await self._strand_in_a_prompt()
            try:
                replies = await self._feed(text=label)
            except Exception as exc:  # noqa: BLE001 - the failure is the finding
                crashed.append(f"{label}: {type(exc).__name__}: {exc}")
                continue
            if not any(reply.get("text") or reply.get("alert") for reply in replies):
                silent.append(label)

        self.assertEqual(crashed, [], "menu buttons raised instead of answering")
        self.assertEqual(silent, [], "menu buttons answered with nothing at all")

    async def test_four_compact_buttons_exit_the_transaction_reply_step(self):
        from app.bot.handlers.deposit import DepositStates
        from app.bot.keyboards import get_persistent_reply_keyboard

        context = self.dp.fsm.get_context(self.bot, chat_id=CUSTOMER, user_id=CUSTOMER)
        for row in get_persistent_reply_keyboard().keyboard:
            for button in row:
                with self.subTest(button=button.text):
                    await context.set_state(DepositStates.waiting_for_txid)
                    await context.set_data({"method_id": 1, "reference_first": True})
                    replies = await self._feed(text=button.text)
                    self.assertTrue(any(reply.get("text") for reply in replies))
                    self.assertIsNone(await context.get_state(), button.text)

    async def test_every_navigation_target_still_exists(self):
        """A renamed handler must not be discoverable only by a customer pressing it."""
        import inspect
        import re

        from app.bot.handlers import deposit, help_guide, navigation, profile, search, shop, start

        modules = {"shop": shop, "profile": profile, "deposit": deposit,
                   "help_guide": help_guide, "start": start, "search": search}
        source = inspect.getsource(navigation.navigate)
        targets = re.findall(r'"((?:' + "|".join(modules) + r')\.\w+)"', source)
        self.assertTrue(targets, "navigate() should route by name")

        missing = [t for t in targets
                   if not hasattr(modules[t.split(".")[0]], t.split(".")[1])]
        self.assertEqual(missing, [], "navigate() points at handlers that no longer exist")

    async def test_a_menu_button_leaves_the_prompt_behind(self):
        """Tapping a menu button means leaving, not answering the question."""
        await self._strand_in_a_prompt()
        await self._feed(text="👤 Profile")
        context = self.dp.fsm.get_context(self.bot, chat_id=CUSTOMER, user_id=CUSTOMER)
        self.assertIsNone(await context.get_state(),
                          "the deposit prompt should have been dropped")

    async def test_cancel_returns_to_wallet_and_clears(self):
        await self._strand_in_a_prompt()
        replies = await self._feed(text="Cancel")
        self.assertTrue(any("balance:" in (r.get("text") or "").lower() for r in replies), replies)
        context = self.dp.fsm.get_context(self.bot, chat_id=CUSTOMER, user_id=CUSTOMER)
        self.assertIsNone(await context.get_state())

    async def test_profile_and_legacy_account_buttons_open_the_same_clean_screen(self):
        for label in ("👤 Profile", "Profile", "/profile", "👤 Account", "Account", "/account"):
            with self.subTest(label=label):
                replies = await self._feed(text=label)
                texts = [reply.get("text") or "" for reply in replies]
                self.assertTrue(any(("<b>Profile</b>" in text or "More" in text or "আরও" in text or "User:" in text or "ইউজার:" in text) for text in texts), replies)
                profile_text = next(text for text in texts if ("<b>Profile</b>" in text or "More" in text or "আরও" in text or "User:" in text or "ইউজার:" in text))
                for duplicate in ("Orders", "Spent"):
                    self.assertNotIn(duplicate, profile_text)

    async def test_legacy_balance_entries_open_wallet_instead_of_profile(self):
        for label in ("/balance", "Balance", "My Balance", "💰 My Balance"):
            with self.subTest(label=label):
                replies = await self._feed(text=label)
                texts = [reply.get("text") or "" for reply in replies]
                self.assertTrue(any("balance:" in text.lower() for text in texts), replies)
                self.assertFalse(any("<b>Profile</b>" in text for text in texts), replies)

    async def test_amount_input_is_not_captured_by_a_matching_payment_method_label(self):
        from app.bot.handlers.deposit import DepositStates

        await self.services.deposits.create_method("Rocket 500", "01700000000")
        context = self.dp.fsm.get_context(self.bot, chat_id=CUSTOMER, user_id=CUSTOMER)
        await context.set_state(DepositStates.waiting_for_amount)
        await context.set_data({
            "method_id": 1, "method_name": "bKash", "reference_first": True,
            "manual_txid": "BK12345678", "min_deposit": 50, "rate": 125,
        })
        with patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit:
            await self._feed(text="500")
        submit.assert_awaited_once()
        self.assertEqual((await context.get_data())["manual_txid"], "BK12345678")
        self.assertEqual((await context.get_data())["pay_amount"], 500)

    async def test_reference_input_is_not_captured_by_payment_brand_detection(self):
        from app.bot.handlers.deposit import DepositStates

        context = self.dp.fsm.get_context(self.bot, chat_id=CUSTOMER, user_id=CUSTOMER)
        await context.set_state(DepositStates.waiting_for_txid)
        await context.set_data({
            "method_id": 1, "method_name": "bKash", "reference_first": True,
            "min_deposit": 50, "rate": 125,
        })
        await self._feed(text="bKash123456")
        self.assertEqual(await context.get_state(), DepositStates.waiting_for_amount.state)
        self.assertEqual((await context.get_data())["manual_txid"], "bKash123456")

    async def test_hosted_checkout_label_cannot_steal_a_manual_payment_amount(self):
        from app.bot.handlers.deposit import DepositStates

        context = self.dp.fsm.get_context(self.bot, chat_id=CUSTOMER, user_id=CUSTOMER)
        await context.set_state(DepositStates.waiting_for_amount)
        await context.set_data({
            "method_id": 1, "method_name": "bKash", "reference_first": True,
            "manual_txid": "BK12345678", "min_deposit": 50, "rate": 125,
        })
        with (
            patch.object(self.services.payments, "instant_options", new_callable=AsyncMock) as instant,
            patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit,
        ):
            instant.return_value = {"label": "Checkout 500", "min_amount": 50}
            await self._feed(text="500")
        submit.assert_awaited_once()
        self.assertEqual((await context.get_data())["pay_amount"], 500)

    async def test_an_unknown_button_falls_back_to_the_dashboard(self):
        """A label with no action must not leave the customer with nothing."""
        from app.bot.handlers import navigation

        context = self.dp.fsm.get_context(self.bot, chat_id=CUSTOMER, user_id=CUSTOMER)
        message_holder: list[str] = []

        async def capture(inner, body=None, **kwargs):
            message_holder.append(body or "")
            return inner

        with patch.object(Message, "answer", capture):
            now = datetime.datetime.now(datetime.timezone.utc)
            user = User(id=CUSTOMER, is_bot=False, first_name="Rafi")
            message = Message(message_id=1, date=now, chat=Chat(id=CUSTOMER, type="private"),
                              from_user=user, text="Buy VPN")
            await navigation.navigate("a label nobody registered", message, context, self.services)
        self.assertTrue(message_holder, "an unknown action should still answer")

    async def test_guide_stays_in_english(self):
        replies_en = await self._feed(data="guide_lang_en")
        replies_bn = await self._feed(data="guide_lang_bn")
        self.assertTrue(any("How to use the bot" in (r.get("text") or "") for r in replies_en),
                        "English guide did not render")
        self.assertTrue(any("How to use the bot" in (r.get("text") or "") for r in replies_bn),
                        "Legacy Bengali guide callback should fall back to English")

    async def test_user_can_switch_language_and_localize_the_bot(self):
        selector = await self._feed(data="open_language_menu")
        selector_markup = next((r.get("reply_markup") for r in selector if r.get("reply_markup")), None)
        self.assertIsNotNone(selector_markup)
        self.assertEqual(
            [row[0].callback_data for row in selector_markup.inline_keyboard],
            ["set_lang_en", "set_lang_bn", "open_more"],
        )

        replies_bn = await self._feed(data="set_lang_bn")
        self.assertEqual(await self.services.users.get_language(CUSTOMER), "bn")
        reply_keyboard_bn = next(
            (r.get("reply_markup") for r in replies_bn if getattr(r.get("reply_markup"), "keyboard", None)),
            None,
        )
        self.assertIsNotNone(reply_keyboard_bn)
        labels_bn = [button.text for row in reply_keyboard_bn.keyboard for button in row]
        self.assertIn("🛍 প্রোডাক্টস", labels_bn)
        guide_bn = await self._feed(data="open_guide")
        self.assertTrue(any("বট ব্যবহার" in (r.get("text") or "") for r in guide_bn))

        replies_en = await self._feed(data="set_lang_en")
        self.assertEqual(await self.services.users.get_language(CUSTOMER), "en")
        reply_keyboard_en = next(
            (r.get("reply_markup") for r in replies_en if getattr(r.get("reply_markup"), "keyboard", None)),
            None,
        )
        self.assertIsNotNone(reply_keyboard_en)
        labels_en = [button.text for row in reply_keyboard_en.keyboard for button in row]
        self.assertIn("🛍 Products", labels_en)

    async def test_support_and_channels_answer(self):
        for label in ("Support", "Channel"):
            replies = await self._feed(text=label)
            self.assertTrue(any(r.get("text") or r.get("alert") for r in replies),
                            f"{label!r} answered with nothing")

    async def test_only_an_admin_gets_an_emoji_id_back(self):
        """The emoji helper reads a message's entities; it is an admin convenience."""
        from aiogram.types import MessageEntity

        async def capture(inner, body=None, **kwargs):
            self.sent.append({"text": body})
            return inner

        for user_id, expected in ((ADMIN, True), (CUSTOMER, False)):
            self._clear_throttle()
            self.sent.clear()
            now = datetime.datetime.now(datetime.timezone.utc)
            user = User(id=user_id, is_bot=False, first_name="X")
            message = Message(
                message_id=1, date=now, chat=Chat(id=user_id, type="private"), from_user=user,
                text="\U0001F680",
                entities=[MessageEntity(type="custom_emoji", offset=0, length=2,
                                        custom_emoji_id="5431234567890")])
            with patch.object(Message, "reply", capture), patch.object(Message, "answer", capture):
                await self.dp.feed_update(self.bot, Update(update_id=1, message=message))
            got = any("5431234567890" in (r.get("text") or "") for r in self.sent)
            self.assertEqual(got, expected,
                             f"emoji id disclosure for {'admin' if expected else 'customer'} was wrong")


if __name__ == "__main__":
    asyncio.run(unittest.main())
