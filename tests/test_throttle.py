import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.middlewares import Throttle


class ThrottleTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_message_is_dropped_within_cooldown(self):
        throttle = Throttle()
        handler = AsyncMock(return_value="ok")

        user = SimpleNamespace(id=12345)
        msg1 = SimpleNamespace(from_user=user, text="Buy VPN", data=None)

        # First tap passes
        res1 = await throttle(handler, msg1, {})
        self.assertEqual(res1, "ok")
        self.assertEqual(handler.call_count, 1)

        # Rapid duplicate tap of the exact same button is dropped immediately
        res2 = await throttle(handler, msg1, {})
        self.assertIsNone(res2)
        self.assertEqual(handler.call_count, 1)

    async def test_different_button_is_not_dropped(self):
        throttle = Throttle()
        handler = AsyncMock(return_value="ok")

        user = SimpleNamespace(id=12345)
        msg_vpn = SimpleNamespace(from_user=user, text="Buy VPN", data=None)
        msg_proxy = SimpleNamespace(from_user=user, text="Proxy Shop", data=None)

        # First tap on Buy VPN
        res1 = await throttle(handler, msg_vpn, {})
        self.assertEqual(res1, "ok")

        # Immediate tap on a DIFFERENT button (Proxy Shop) passes without waiting
        res2 = await throttle(handler, msg_proxy, {})
        self.assertEqual(res2, "ok")
        self.assertEqual(handler.call_count, 2)

    async def test_duplicate_tap_after_cooldown_is_allowed(self):
        throttle = Throttle()
        throttle.SAME_ACTION_COOLDOWN = 0.1  # Fast cooldown for test
        handler = AsyncMock(return_value="ok")

        user = SimpleNamespace(id=12345)
        msg = SimpleNamespace(from_user=user, text="Buy VPN", data=None)

        res1 = await throttle(handler, msg, {})
        self.assertEqual(res1, "ok")

        # Dropped before cooldown
        res2 = await throttle(handler, msg, {})
        self.assertIsNone(res2)

        # Wait for cooldown to expire
        await asyncio.sleep(0.12)

        # Allowed after cooldown
        res3 = await throttle(handler, msg, {})
        self.assertEqual(res3, "ok")
        self.assertEqual(handler.call_count, 2)

    async def test_duplicate_callback_query_answers_silently(self):
        throttle = Throttle()
        handler = AsyncMock(return_value="ok")

        user = SimpleNamespace(id=12345)
        cb_answer = AsyncMock()
        cb = SimpleNamespace(from_user=user, text=None, data="cat:vpn", answer=cb_answer)

        # First tap
        res1 = await throttle(handler, cb, {})
        self.assertEqual(res1, "ok")
        cb_answer.assert_not_called()

        # Rapid duplicate callback tap
        res2 = await throttle(handler, cb, {})
        self.assertIsNone(res2)
        # Verify callback was answered silently so Telegram client stops spinner
        cb_answer.assert_called_once()
        self.assertEqual(handler.call_count, 1)


if __name__ == "__main__":
    unittest.main()
