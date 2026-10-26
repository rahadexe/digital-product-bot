"""Tests for the compact More menu and English-only customer UI."""

from __future__ import annotations

import unittest

from app.bot.keyboards import get_more_inline_keyboard


class AccountRedesignTests(unittest.TestCase):
    def test_more_menu_keeps_only_api_and_reseller_tools(self):
        keyboard = get_more_inline_keyboard(is_reseller=True)
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(
            [button.callback_data for button in buttons],
            ["open_api_hub", "open_reseller_hub"],
        )
        self.assertEqual([button.text for button in buttons], ["⚡ API", "💼 Reseller Hub"])

    def test_deposit_history_keyboard_and_prompts(self):
        from app.bot.keyboards import get_deposit_methods_keyboard
        from app.core.i18n import t

        # English deposit methods use inline keyboard (no redundant Back button when back_target is back_to_main).
        kb_en = get_deposit_methods_keyboard([], lang="en", show_history=True)
        self.assertEqual(
            [[button.text for button in row] for row in kb_en.inline_keyboard],
            [["📜 Deposit History"]],
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
                ["Binance Pay", "Jinpay Checkout"],
                ["📜 Deposit History"],
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
            "💰 <b>Balance:</b> <code>$10.00</code>\n\nChoose a method to top up.",
        )

        prompt_legacy_language = t("deposit_choose_method", "bn", balance="$1.00")
        self.assertEqual(prompt_legacy_language, prompt_en.replace("$10.00", "$1.00"))

        # Check title and hint
        title_en = t("balance_history_title", "en", icon_stats="📊")
        self.assertEqual(title_en, "<b>Deposit History</b>")
        self.assertEqual(t("balance_history_hint", "en"), "")

        # Check btn_deposit
        # Check deposit_detail_title without #id
        self.assertEqual(t("deposit_detail_title", "en", id="D21"), "<b>Top-up D21</b>")
        self.assertEqual(t("deposit_detail_title", "bn", id="D21"), "<b>Top-up D21</b>")


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
    async def test_legacy_account_callback_redirects_to_wallet(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from app.bot.handlers.profile import open_wallet_from_legacy_account

        event = SimpleNamespace(from_user=SimpleNamespace(id=123))
        state = SimpleNamespace(clear=AsyncMock())
        services = SimpleNamespace()

        with patch("app.bot.handlers.deposit.show_deposit_methods", new_callable=AsyncMock) as show_wallet:
            await open_wallet_from_legacy_account(event, state, services)

        show_wallet.assert_awaited_once_with(event, state, services)
        state.clear.assert_awaited_once()

    async def test_more_menu_has_only_settings_and_role_tools(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from app.bot.handlers.profile import show_more_menu

        event = SimpleNamespace(from_user=SimpleNamespace(id=123))
        state = SimpleNamespace(clear=AsyncMock())
        services = SimpleNamespace(users=SimpleNamespace(
            get=AsyncMock(return_value={"rank": "reseller partner"}),
            get_language=AsyncMock(return_value="en"),
        ))
        with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as respond:
            await show_more_menu(event, state, services)

        text, keyboard = respond.await_args.args[1:]
        self.assertIn("<b>More</b>", text)
        self.assertNotIn("Balance:", text)
        self.assertNotIn("Profile", text)
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(callbacks, ["open_api_hub", "open_reseller_hub"])
        self.assertEqual([len(row) for row in keyboard.inline_keyboard], [2])

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
        self.assertIn("Successful invites: <code>4</code>", text)
        self.assertIn("Earned:", text)
        self.assertIn("Earn <b>$20</b> per new friend", text)
        self.assertIn("required channel check", text)
        self.assertIn("https://t.me/test_bot?start=999", text)

        button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
        self.assertEqual(button_texts, ["Copy Link", "Share"])
        self.assertTrue(all(btn.callback_data is None for row in kb.inline_keyboard for btn in row))

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

        self.assertIn("<b>Order:</b> <code>ORD-789</code>", text)
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
        services.users.get_language = AsyncMock(return_value="en")
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
