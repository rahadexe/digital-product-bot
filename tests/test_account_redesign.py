"""Tests for Account actions, language selection, and notification settings."""

from __future__ import annotations

import unittest

from app.bot.keyboards import (
    get_account_keyboard,
    get_language_selection_keyboard,
    get_notification_settings_keyboard,
)


class AccountRedesignTests(unittest.TestCase):
    def test_account_keyboard_structure_english(self):
        kb = get_account_keyboard(lang="en", is_reseller=False)
        rows = kb.inline_keyboard

        self.assertEqual(len(rows), 3)
        self.assertEqual([button.text for button in rows[0]], ["Orders", "Referral"])
        self.assertEqual(
            [button.callback_data for button in rows[0]],
            ["open_orders_acc", "open_referral"],
        )
        self.assertEqual([button.text for button in rows[1]], ["API", "Language"])
        self.assertEqual(
            [button.callback_data for button in rows[1]],
            ["open_api_hub", "open_language_menu"],
        )
        self.assertEqual([button.text for button in rows[2]], ["Reseller"])
        self.assertEqual(
            [button.callback_data for button in rows[2]],
            ["open_reseller"],
        )

    def test_account_keyboard_reseller_tier(self):
        kb = get_account_keyboard(lang="en", is_reseller=True)
        rows = kb.inline_keyboard
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2][0].text, "Reseller")
        self.assertEqual(rows[2][0].callback_data, "open_reseller_hub")

    def test_account_keyboard_structure_bengali(self):
        kb = get_account_keyboard(lang="bn", is_reseller=False)
        rows = kb.inline_keyboard

        self.assertEqual(len(rows), 3)
        self.assertEqual([button.text for button in rows[0]], ["অর্ডার", "রেফারেল"])
        self.assertEqual([button.text for button in rows[1]], ["এপিআই", "ভাষা"])
        self.assertEqual([button.text for button in rows[2]], ["রিসেলার"])

    def test_language_keyboard_marks_bangla_as_coming_soon(self):
        kb = get_language_selection_keyboard()
        rows = kb.inline_keyboard

        self.assertEqual(rows[0][0].text, "🇬🇧 English (Active)")
        self.assertEqual(rows[0][0].callback_data, "set_lang_en")
        self.assertEqual(rows[1][0].text, "🇧🇩 Bangla (Coming Soon)")
        self.assertEqual(rows[1][0].callback_data, "language_coming_soon")
        self.assertEqual(rows[2][0].callback_data, "open_account")
        self.assertEqual(rows[2][0].text, "Back")

    def test_notification_settings_keyboard(self):
        prefs = {"notify_orders": True, "notify_deposits": False, "notify_news": True}
        kb = get_notification_settings_keyboard(prefs, lang="en")
        rows = kb.inline_keyboard

        self.assertEqual(len(rows), 4)
        self.assertIn("On ✅", rows[0][0].text)
        self.assertEqual(rows[0][0].callback_data, "notif_toggle_notify_orders")

        self.assertIn("Off ❌", rows[1][0].text)
        self.assertEqual(rows[1][0].callback_data, "notif_toggle_notify_deposits")

        self.assertIn("On ✅", rows[2][0].text)
        self.assertEqual(rows[2][0].callback_data, "notif_toggle_notify_news")

        # Back returns to open_account
        self.assertEqual(rows[3][0].callback_data, "open_account")
        self.assertEqual(rows[3][0].text, "🔙 Back")

    def test_deposit_history_keyboard_and_prompts(self):
        from app.bot.keyboards import get_deposit_methods_keyboard
        from app.core.i18n import t

        # English deposit methods use inline keyboard (no redundant Back button when back_target is back_to_main).
        kb_en = get_deposit_methods_keyboard([], lang="en", show_history=True)
        self.assertEqual(
            [[button.text for button in row] for row in kb_en.inline_keyboard],
            [["📊 Deposit History"]],
        )

        # Bengali labels are localized.
        kb_bn = get_deposit_methods_keyboard([], lang="bn", show_history=True)
        self.assertEqual(
            [[button.text for button in row] for row in kb_bn.inline_keyboard],
            [["📊 ডিপোজিট হিস্ট্রি"]],
        )

        # Configured methods and hosted checkout stay selectable as buttons.
        methods_kb = get_deposit_methods_keyboard(
            [
                {"id": 1, "name": "bKash"},
                {"id": 2, "name": "Nagad"},
                {
                    "id": 3,
                    "name": "Binance Pay",
                    "auto_verify": "binance_pay",
                    "custom_emoji_id": "5796345694969140339",
                },
            ],
            instant_label="Jinpay Checkout",
            lang="en",
        )
        self.assertEqual(
            [[button.text for button in row] for row in methods_kb.inline_keyboard],
            [
                ["bKash", "Nagad"],
                ["Binance Pay"],
                ["Jinpay Checkout"],
                ["📊 Deposit History"],
            ],
        )
        self.assertEqual(
            methods_kb.inline_keyboard[1][0].icon_custom_emoji_id,
            "5796345694969140339",
        )

        # The picker keeps its message to balance and the next action.
        prompt_en = t("deposit_choose_method", "en", balance="$10.00")
        self.assertEqual(
            prompt_en,
            "💰 <b>Balance:</b> <code>$10.00</code>\n\n<b>Select Payment Method</b>",
        )

        prompt_bn = t("deposit_choose_method", "bn", balance="৳১০০")
        self.assertEqual(
            prompt_bn,
            "💰 <b>ব্যালেন্স:</b> <code>৳১০০</code>\n\n"
            "<b>পেমেন্ট মেথড সিলেক্ট করুন</b>",
        )

        # Check title and hint
        title_en = t("balance_history_title", "en", icon_stats="📊")
        self.assertEqual(title_en, "📊 <b>Deposit History</b>")
        self.assertEqual(t("balance_history_hint", "en"), "")

        # Check btn_deposit
        # Check deposit_detail_title without #id
        self.assertEqual(t("deposit_detail_title", "en", id="D21"), "<b>Deposit D21</b>")
        self.assertEqual(t("deposit_detail_title", "bn", id="D21"), "<b>ডিপোজিট D21</b>")


class DepositPickerRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_instant_checkout_reply_button_matches_configured_label(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from app.bot.handlers.deposit import InstantPaymentTextFilter

        instant = {"label": "Jinpay Checkout", "min_amount": 10}
        services = SimpleNamespace(
            payments=SimpleNamespace(instant_options=AsyncMock(return_value=instant))
        )

        result = await InstantPaymentTextFilter()(
            SimpleNamespace(text="⚡ Jinpay Checkout"),
            services,
        )

        self.assertEqual(result, {"instant": instant})


class AccountScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_entry_uses_inline_keyboard_and_short_profile(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.bot.handlers.profile import show_user_profile

        db_connection = MagicMock()
        db_connection.fetchrow = AsyncMock(
            return_value={"total_invited": 3, "total_earned": 12.5}
        )
        db_context = MagicMock()
        db_context.__aenter__ = AsyncMock(return_value=db_connection)
        db_context.__aexit__ = AsyncMock(return_value=False)
        user = SimpleNamespace(
            id=123,
            full_name="Test Customer",
            first_name="Test",
            username="test_user",
        )
        event = SimpleNamespace(from_user=user)
        state = SimpleNamespace(clear=AsyncMock())
        services = SimpleNamespace(
            users=SimpleNamespace(
                get=AsyncMock(return_value={"rank": "Standard", "balance": 25}),
                get_language=AsyncMock(return_value="en"),
                stats=AsyncMock(return_value={"order_count": 2, "total_spent": 50}),
            ),
            settings=SimpleNamespace(
                get=AsyncMock(return_value="৳"),
                number=AsyncMock(return_value=125),
                flag=AsyncMock(return_value=False),
            ),
            db=SimpleNamespace(connect=MagicMock(return_value=db_context)),
            notifier=SimpleNamespace(bot_username=AsyncMock(return_value="sample_bot")),
        )

        with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as respond:
            await show_user_profile(event, state, services)

        text = respond.await_args.args[1]
        keyboard = respond.await_args.args[2]
        self.assertNotIn("<b>My Account</b>", text)
        self.assertIn("<b>Name:</b> Test Customer", text)
        self.assertIn("<b>User ID:</b> <code>123</code>", text)
        self.assertIn("<b>Status:</b> Member", text)
        self.assertIn("<b>Orders:</b> 2", text)
        self.assertIn("<b>Referrals:</b> 3", text)
        self.assertIn("start=123", text)
        self.assertEqual([button.text for button in keyboard.inline_keyboard[0]], ["Orders (2)", "Referral"])

    async def test_reseller_account_shows_reseller_status(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.bot.handlers.profile import show_user_profile

        db_connection = MagicMock()
        db_connection.fetchrow = AsyncMock(
            return_value={"total_invited": 0, "total_earned": 0}
        )
        db_context = MagicMock()
        db_context.__aenter__ = AsyncMock(return_value=db_connection)
        db_context.__aexit__ = AsyncMock(return_value=False)
        event = SimpleNamespace(
            from_user=SimpleNamespace(id=123, full_name="Reseller User", first_name="Reseller")
        )
        state = SimpleNamespace(clear=AsyncMock())
        services = SimpleNamespace(
            users=SimpleNamespace(
                get=AsyncMock(return_value={"rank": "reseller partner", "balance": 25}),
                get_language=AsyncMock(return_value="en"),
                stats=AsyncMock(return_value={"order_count": 5, "total_spent": 50}),
            ),
            settings=SimpleNamespace(
                get=AsyncMock(return_value="৳"),
                number=AsyncMock(return_value=125),
                flag=AsyncMock(return_value=False),
            ),
            db=SimpleNamespace(connect=MagicMock(return_value=db_context)),
            notifier=SimpleNamespace(bot_username=AsyncMock(return_value="sample_bot")),
        )

        with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as respond:
            await show_user_profile(event, state, services)

        text = respond.await_args.args[1]
        keyboard = respond.await_args.args[2]
        self.assertIn("<b>Status:</b> Reseller", text)
        self.assertIn("<b>Referrals:</b> 0", text)
        self.assertEqual(keyboard.inline_keyboard[2][0].text, "Reseller")
        self.assertEqual(keyboard.inline_keyboard[2][0].callback_data, "open_reseller_hub")

    async def test_language_menu_marks_bangla_coming_soon(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from app.bot.handlers.profile import show_language_menu

        event = SimpleNamespace(from_user=SimpleNamespace(id=123))
        state = SimpleNamespace(clear=AsyncMock())

        with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as respond:
            await show_language_menu(event, state, SimpleNamespace())

        text, keyboard = respond.await_args.args[1:]
        self.assertNotIn("Current:", text)
        self.assertEqual("Choose your preferred language:", text)
        self.assertEqual(keyboard.inline_keyboard[1][0].callback_data, "language_coming_soon")

    async def test_bangla_coming_soon_button_explains_availability(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from app.bot.handlers.profile import notify_language_coming_soon

        event = SimpleNamespace(answer=AsyncMock())
        await notify_language_coming_soon(event)

        event.answer.assert_awaited_once_with("বাংলা ভাষা শীঘ্রই যুক্ত করা হচ্ছে! / Bangla language coming soon!", show_alert=True)

    async def test_english_selection_persists_and_returns_to_account(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from app.bot.handlers.profile import select_english_language

        user = SimpleNamespace(id=123)
        event = SimpleNamespace(from_user=user)
        state = SimpleNamespace(clear=AsyncMock())
        set_language = AsyncMock()
        services = SimpleNamespace(users=SimpleNamespace(set_language=set_language))

        with patch("app.bot.handlers.profile.show_user_profile", new_callable=AsyncMock) as show_profile:
            await select_english_language(event, state, services)

        set_language.assert_awaited_once_with(123, "en")
        show_profile.assert_awaited_once_with(event, state, services)

    async def test_reseller_openapi_spec_structure(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from app.api.reseller import reseller_openapi_spec

        request = SimpleNamespace(base_url="https://api.example.com/")
        services = SimpleNamespace(
            settings=SimpleNamespace(values=AsyncMock(return_value={"store_name": "Test Store"}))
        )

        spec = await reseller_openapi_spec(request, services)
        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertIn("Test Store", spec["info"]["title"])
        self.assertEqual(spec["servers"][0]["url"], "https://api.example.com/api/v1/reseller")
        self.assertIn("/me", spec["paths"])
        self.assertIn("/products", spec["paths"])
        self.assertIn("/orders", spec["paths"])
        self.assertIn("ApiKeyAuth", spec["components"]["securitySchemes"])

    async def test_reseller_documentation_page_renders_agent_ready_portal(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from app.api.reseller import reseller_documentation_page

        request = SimpleNamespace(base_url="https://api.example.com/")
        services = SimpleNamespace(
            settings=SimpleNamespace(
                values=AsyncMock(return_value={"store_name": "Test Store", "currency": "BDT", "currency_symbol": "৳"})
            ),
            notifier=SimpleNamespace(bot_username=AsyncMock(return_value="test_bot")),
        )

        response = await reseller_documentation_page(request, services)
        html = response if isinstance(response, str) else response.body.decode("utf-8")
        self.assertIn("AI Agent Ready", html)
        self.assertIn("https://api.example.com/api/v1/reseller/openapi.json", html)
        self.assertIn("X-API-Key: rkliveYOUR_API_KEY_HERE", html)
        self.assertIn("rklive", html)
        self.assertIn("copySnippet", html)

    async def test_referral_screen_clean_layout_and_no_emojis(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.bot.handlers.profile import show_referral_info

        db_conn = MagicMock()
        db_conn.fetchrow = AsyncMock(return_value={"total_invited": 4, "total_earned": 80.0})
        db_ctx = MagicMock()
        db_ctx.__aenter__ = AsyncMock(return_value=db_conn)
        db_ctx.__aexit__ = AsyncMock(return_value=False)

        services = SimpleNamespace(
            users=SimpleNamespace(
                get=AsyncMock(return_value={"balance": 100}),
                get_language=AsyncMock(return_value="en"),
            ),
            settings=SimpleNamespace(
                get=AsyncMock(side_effect=lambda k: "৳" if k == "currency_symbol" else "StoreName"),
                number=AsyncMock(side_effect=lambda k: 20.0 if k == "referral_reward_amount" else 125.0),
                flag=AsyncMock(side_effect=lambda k: True if k == "referral_enabled" else False),
            ),
            db=SimpleNamespace(connect=MagicMock(return_value=db_ctx)),
            notifier=SimpleNamespace(bot_username=AsyncMock(return_value="test_bot")),
        )

        event = SimpleNamespace(from_user=SimpleNamespace(id=999))
        state = SimpleNamespace(clear=AsyncMock())

        with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as respond:
            await show_referral_info(event, state, services)

        text = respond.await_args.args[1]
        kb = respond.await_args.args[2]

        self.assertNotIn("<b>Referral</b>", text)
        self.assertIn("Invited: <code>4</code>", text)
        self.assertIn("Earned:", text)
        self.assertIn("Reward: <code>", text)
        self.assertIn("per friend", text)
        self.assertIn("https://t.me/test_bot?start=999", text)

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        self.assertEqual(button_texts, ["Copy Link", "Share", "Back"])

    async def test_orders_history_clean_header_and_no_order_id_in_buttons(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from app.bot.handlers.profile import show_order_history

        services = SimpleNamespace(
            purchases=SimpleNamespace(
                customer_orders=AsyncMock(return_value=([
                    {
                        "id": 1024,
                        "product_title": "Proton VPN Plus",
                        "price": 150.0,
                        "status": "completed",
                        "fulfillment": "delivered",
                    }
                ], 1))
            ),
            settings=SimpleNamespace(
                get=AsyncMock(return_value="৳"),
                number=AsyncMock(return_value=125.0),
                flag=AsyncMock(return_value=False),
            ),
            users=SimpleNamespace(get_language=AsyncMock(return_value="en")),
        )

        event = SimpleNamespace(from_user=SimpleNamespace(id=123), data="open_orders")
        state = SimpleNamespace(clear=AsyncMock())

        with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as respond:
            await show_order_history(event, state, services)

        text = respond.await_args.args[1]
        kb = respond.await_args.args[2]

        self.assertIn("<b>Orders (1)</b>", text)
        row0 = kb.inline_keyboard[0][0]
        self.assertNotIn("#1024", row0.text)
        self.assertIn("Proton VPN Plus", row0.text)
        self.assertIn("✅", row0.text)

    async def test_order_detail_clean_header_and_action_buttons(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from datetime import datetime
        from app.bot.handlers.profile import view_order_detail

        services = SimpleNamespace(
            purchases=SimpleNamespace(
                order_for_customer=AsyncMock(return_value={
                    "id": 789,
                    "product_title": "Telegram Premium 3 Months",
                    "price": 350.0,
                    "status": "completed",
                    "fulfillment": "delivered",
                    "delivered_item": "user:pass",
                    "created_at": datetime(2026, 10, 14, 12, 0),
                    "product_id": 42,
                })
            ),
            settings=SimpleNamespace(
                get=AsyncMock(return_value="৳"),
                number=AsyncMock(return_value=125.0),
                flag=AsyncMock(return_value=False),
            ),
            users=SimpleNamespace(get_language=AsyncMock(return_value="en")),
        )

        query = SimpleNamespace(
            from_user=SimpleNamespace(id=123),
            data="vord_789_1",
            answer=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        state = SimpleNamespace(clear=AsyncMock())

        await view_order_detail(query, state, services)

        text = query.message.edit_text.call_args[0][0]
        kb = query.message.edit_text.call_args[1]["reply_markup"]

        self.assertIn("<b>Order:</b> <code>O789</code>", text)
        self.assertIn("Status: Delivered ✅", text)
        self.assertIn("Telegram Premium 3 Months", text)
        self.assertIn("<code>user:pass</code>", text)

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        self.assertIn("Copy Credentials", button_texts)
        self.assertIn("Report Issue", button_texts)
        self.assertIn("Buy Again", button_texts)
        self.assertIn("Back", button_texts)

    async def test_order_detail_back_navigation_preserves_account_origin(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from datetime import datetime
        from app.bot.handlers.profile import view_order_detail, handle_claim_warranty

        services = SimpleNamespace(
            purchases=SimpleNamespace(
                order_for_customer=AsyncMock(return_value={
                    "id": 1005,
                    "product_title": "NordVPN",
                    "price": 120.0,
                    "status": "completed",
                    "fulfillment": "delivered",
                    "delivered_item": "user:pass",
                    "created_at": datetime(2026, 10, 14, 12, 0),
                    "product_id": 1,
                })
            ),
            settings=SimpleNamespace(
                get=AsyncMock(return_value="৳"),
                number=AsyncMock(return_value=125.0),
                flag=AsyncMock(return_value=False),
            ),
            users=SimpleNamespace(get_language=AsyncMock(return_value="en")),
        )

        # 1. From account (from_acc=1): vord_1005_1_1
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=123),
            data="vord_1005_1_1",
            answer=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        state = SimpleNamespace(clear=AsyncMock())
        await view_order_detail(query, state, services)

        kb = query.message.edit_text.call_args[1]["reply_markup"]
        report_btn = [btn for row in kb.inline_keyboard for btn in row if "Report Issue" in btn.text][0]
        buy_again_btn = [btn for row in kb.inline_keyboard for btn in row if "Buy Again" in btn.text][0]
        back_btn = [btn for row in kb.inline_keyboard for btn in row if "Back" in btn.text][0]
        self.assertEqual(report_btn.callback_data, "claim_warranty_1005_1_1")
        self.assertEqual(buy_again_btn.callback_data, "prod_bo_1_1005_1_1")
        self.assertEqual(back_btn.callback_data, "open_orders_acc")

        # 2. When clicking Buy Again: prod_bo_1_1005_1_1
        from app.bot.handlers.shop import show_order_buy_again
        services.catalog = SimpleNamespace(
            product=AsyncMock(return_value={
                "id": 1,
                "title": "NordVPN",
                "price": 120.0,
                "is_active": True,
                "category_id": 1,
                "stock": 5,
            })
        )
        services.notifier = SimpleNamespace(bot_username=AsyncMock(return_value="TestBot"))
        services.users.get = AsyncMock(return_value={"id": 123, "rank": "member", "balance": 500.0})
        from unittest.mock import MagicMock
        from aiogram.types import CallbackQuery, Message, User
        query_buy = MagicMock(spec=CallbackQuery)
        query_buy.from_user = User(id=123, is_bot=False, first_name="Test")
        query_buy.data = "prod_bo_1_1005_1_1"
        query_buy.answer = AsyncMock()
        query_buy.message = MagicMock(spec=Message)
        query_buy.message.edit_text = AsyncMock()
        state_data = {}
        state.update_data = AsyncMock(side_effect=lambda **kw: state_data.update(kw))
        state.get_data = AsyncMock(return_value=state_data)
        await show_order_buy_again(query_buy, state, services)
        prod_kb = query_buy.message.edit_text.call_args[1]["reply_markup"]
        prod_back_btn = [btn for row in prod_kb.inline_keyboard for btn in row if "Back" in btn.text][0]
        # Back button on product page returns directly to the order detail!
        self.assertEqual(prod_back_btn.callback_data, "vord_1005_1_1")

        # 3. When clicking Report Issue: claim_warranty_1005_1_1
        query_claim = SimpleNamespace(
            from_user=SimpleNamespace(id=123),
            data="claim_warranty_1005_1_1",
            answer=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        await handle_claim_warranty(query_claim, state, services)
        claim_kb = query_claim.message.edit_text.call_args[1]["reply_markup"]
        claim_back_btn = [btn for row in claim_kb.inline_keyboard for btn in row if "Back" in btn.text][0]
        self.assertEqual(claim_back_btn.callback_data, "vord_1005_1_1")
