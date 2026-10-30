import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.announcements import AnnouncementService, format_customer_short_name


class TestProofAnnouncements(unittest.IsolatedAsyncioTestCase):
    def test_format_customer_short_name(self):
        self.assertEqual(format_customer_short_name("Rahad", "Hasan"), "Rahad H.")
        self.assertEqual(format_customer_short_name("Rahad", ""), "Rahad")
        self.assertEqual(format_customer_short_name("", "Hasan"), "Hasan")
        self.assertEqual(format_customer_short_name("", "", "rahad123"), "@ra***3")
        self.assertEqual(format_customer_short_name("", "", "amy"), "@amy")
        self.assertEqual(format_customer_short_name("", "", ""), "Verified Buyer")
        self.assertEqual(format_customer_short_name(None, None, None), "Verified Buyer")

    async def test_broadcast_order_proof(self):
        settings = MagicMock()
        settings.values = AsyncMock(return_value={"announcement_channel": "-1001234567890"})
        catalog = MagicMock()
        notifier = MagicMock()
        notifier.bot_username = AsyncMock(return_value="testbot")
        notifier.send = AsyncMock(return_value=True)

        service = AnnouncementService(settings, catalog, notifier)

        # Single item
        res = await service.broadcast_order_proof(
            product_id=42,
            product_title="Netflix Premium (1 Month)",
            price_str="250 ৳",
            quantity=1,
            first_name="Rahad",
            last_name="Hasan",
        )
        self.assertTrue(res)
        notifier.send.assert_called_once()
        call_args = notifier.send.call_args
        target_chat = call_args[0][0]
        text = call_args[0][1]
        kb = call_args[1].get("keyboard")

        self.assertEqual(target_chat, "-1001234567890")
        self.assertIn("New Order Delivered!", text)
        self.assertIn("Netflix Premium (1 Month)", text)
        self.assertNotIn("(x1)", text)
        self.assertIn("Rahad H.", text)
        self.assertIn("250 ৳", text)
        self.assertIn("Status: Delivered ✅", text)

        # Check buttons: 3 buttons total
        self.assertEqual(len(kb.inline_keyboard), 2)
        self.assertEqual(kb.inline_keyboard[0][0].text, "🛒 Buy This Item")
        self.assertIn("prod_42", kb.inline_keyboard[0][0].url)
        self.assertEqual(kb.inline_keyboard[1][0].text, "🛍️ Open Store")
        self.assertEqual(kb.inline_keyboard[1][1].text, "💳 Add Balance")

    async def test_broadcast_order_proof_multiple_quantity(self):
        settings = MagicMock()
        settings.values = AsyncMock(return_value={"announcement_channel": "@proof_channel"})
        catalog = MagicMock()
        notifier = MagicMock()
        notifier.bot_username = AsyncMock(return_value="testbot")
        notifier.send = AsyncMock(return_value=True)

        service = AnnouncementService(settings, catalog, notifier)

        res = await service.broadcast_order_proof(
            product_id=10,
            product_title="Spotify 3 Months",
            price_str="600 ৳",
            quantity=3,
            first_name="Alice",
            last_name=None,
        )
        self.assertTrue(res)
        text = notifier.send.call_args[0][1]
        self.assertIn("Spotify 3 Months (x3)", text)
        self.assertIn("Alice", text)
        self.assertIn("Status: Delivered ✅", text)

    async def test_broadcast_deposit_proof(self):
        settings = MagicMock()
        settings.values = AsyncMock(return_value={"announcement_channel": "-1009876543210"})
        catalog = MagicMock()
        notifier = MagicMock()
        notifier.bot_username = AsyncMock(return_value="testbot")
        notifier.send = AsyncMock(return_value=True)

        service = AnnouncementService(settings, catalog, notifier)

        res = await service.broadcast_deposit_proof(
            method_name="bKash Manual",
            amount_str="1200.00 ৳",
            first_name="Tanvir",
            last_name="Karim",
        )
        self.assertTrue(res)
        text = notifier.send.call_args[0][1]
        kb = notifier.send.call_args[1].get("keyboard")

        self.assertIn("Wallet Deposit Confirmed!", text)
        self.assertIn("Tanvir K.", text)
        self.assertIn("bKash Manual", text)
        self.assertIn("1200.00 ৳", text)
        self.assertIn("Status: Balance Added ✅", text)

        self.assertEqual(kb.inline_keyboard[0][0].text, "💳 Add Balance")
        self.assertIn("wallet", kb.inline_keyboard[0][0].url)
        self.assertEqual(kb.inline_keyboard[1][0].text, "🛍️ Open Store")

    async def test_broadcast_referral_proof(self):
        settings = MagicMock()
        settings.values = AsyncMock(return_value={"announcement_channel": "-1009876543210"})
        catalog = MagicMock()
        notifier = MagicMock()
        notifier.bot_username = AsyncMock(return_value="testbot")
        notifier.send = AsyncMock(return_value=True)

        service = AnnouncementService(settings, catalog, notifier)

        res = await service.broadcast_referral_proof(
            reward_str="20 ৳",
            first_name="Shohag",
            last_name="Rana",
        )
        self.assertTrue(res)
        text = notifier.send.call_args[0][1]
        kb = notifier.send.call_args[1].get("keyboard")

        self.assertIn("Referral Bonus Credited!", text)
        self.assertIn("Shohag R.", text)
        self.assertIn("+20 ৳", text)
        self.assertIn("Status: Added to Wallet ✅", text)

        self.assertEqual(kb.inline_keyboard[0][0].text, "👥 Invite & Earn")
        self.assertIn("ref", kb.inline_keyboard[0][0].url)

    async def test_broadcast_reseller_proof(self):
        settings = MagicMock()
        settings.values = AsyncMock(return_value={"announcement_channel": "-1009876543210"})
        catalog = MagicMock()
        notifier = MagicMock()
        notifier.bot_username = AsyncMock(return_value="testbot")
        notifier.send = AsyncMock(return_value=True)

        service = AnnouncementService(settings, catalog, notifier)

        res = await service.broadcast_reseller_proof(
            first_name="Hasan",
            last_name="Mahmud",
        )
        self.assertTrue(res)
        text = notifier.send.call_args[0][1]
        kb = notifier.send.call_args[1].get("keyboard")

        self.assertIn("New Reseller Partner Joined!", text)
        self.assertIn("Hasan M.", text)
        self.assertIn("Wholesale API Activated ⚡", text)

        self.assertEqual(kb.inline_keyboard[0][0].text, "💎 Reseller Program")
        self.assertIn("reseller", kb.inline_keyboard[0][0].url)
