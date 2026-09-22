from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from contextlib import suppress

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.start import gate_text
from app.bot.keyboards import get_gate_keyboard
from app.services import Services

OPEN_COMMANDS = {"/start", "/menu"}

SLOW_DOWN_TEXT = "⏳ Too many requests. Please wait a few seconds and try again."


class Throttle(BaseMiddleware):
    """Drops a customer's updates beyond what a person can tap, before they cost any database or Telegram work.

    Each customer has a bucket of BURST taps that refills at RATE per second. While it is empty, updates are
    ignored and the customer is told to slow down at most once every NOTICE_SECONDS, so a flood cannot make
    the bot flood Telegram with replies either. Buckets live in memory, which suits the single bot process.
    """

    RATE = 2.0
    BURST = 8
    NOTICE_SECONDS = 10.0
    TRACKED_USERS = 20000

    def __init__(self) -> None:
        # user id -> (tokens, refilled_at, last_notice_at)
        self._buckets: OrderedDict[int, tuple[float, float, float]] = OrderedDict()

    def _take(self, user_id: int, now: float) -> tuple[bool, bool]:
        """Whether this update may run, and whether the customer should be told to slow down."""
        tokens, refilled_at, noticed_at = self._buckets.get(user_id, (float(self.BURST), now, 0.0))
        tokens = min(float(self.BURST), tokens + (now - refilled_at) * self.RATE)
        allowed = tokens >= 1.0
        notify = False
        if allowed:
            tokens -= 1.0
        elif now - noticed_at >= self.NOTICE_SECONDS:
            notify, noticed_at = True, now
        self._buckets[user_id] = (tokens, now, noticed_at)
        self._buckets.move_to_end(user_id)
        while len(self._buckets) > self.TRACKED_USERS:
            self._buckets.popitem(last=False)
        return allowed, notify

    async def __call__(self, handler, event, data):
        user = event.from_user
        if not user:
            return await handler(event, data)
        allowed, notify = self._take(user.id, time.monotonic())
        if allowed:
            return await handler(event, data)
        # Working through a queue of deposits or orders is two taps each, so an owner
        # clearing a backlog empties the bucket in seconds. A dropped tap is silent, which
        # makes Approve look broken. The administrator list is a handful of trusted
        # accounts and comes from the settings cache, so let them through.
        services: Services | None = data.get("services")
        if services and user.id in await services.settings.admin_chat_ids():
            return await handler(event, data)
        if notify:
            with suppress(TelegramAPIError):
                if isinstance(event, CallbackQuery):
                    await event.answer(SLOW_DOWN_TEXT, show_alert=True)
                elif isinstance(event, Message) and event.chat.type == "private":
                    await event.answer(SLOW_DOWN_TEXT)
        return None


class StoreAccess(BaseMiddleware):
    """Private chats only; banned customers are stopped; force-join applies to everything except /start."""

    async def __call__(self, handler, event, data):
        services: Services = data["services"]
        user = event.from_user
        if not user:
            return None
        message = event.message if isinstance(event, CallbackQuery) else event
        # Wallet details and delivered credentials must never appear in group chats.
        if not message or message.chat.type != "private":
            if isinstance(event, CallbackQuery):
                await event.answer("Open a private chat with the bot to continue.", show_alert=True)
            return None

        # Admins always have unhindered access to bot commands
        admin_ids = await services.settings.admin_chat_ids()
        if user.id in admin_ids:
            return await handler(event, data)

        opens_store = (isinstance(event, Message) and event.text and event.text.split()[0].split("@")[0] in OPEN_COMMANDS) or (
            isinstance(event, CallbackQuery) and event.data == "gate_verify"
        )
        # Both checks run on every update, so they run concurrently. /start presents the gate itself.
        if opens_store:
            record = await services.users.get(user.id)
            passed, missing = True, []
        else:
            record, (passed, missing) = await asyncio.gather(services.users.get(user.id), services.gate.check(user.id))

        if record and record["is_banned"]:
            if isinstance(event, CallbackQuery):
                await event.answer("Your account is suspended.", show_alert=True)
            else:
                await event.answer("Your account is suspended.")
            return None
        if not passed:
            if isinstance(event, CallbackQuery):
                await event.answer("Please join the required channels first.", show_alert=True)
            await message.answer(
                gate_text(missing), reply_markup=get_gate_keyboard(missing)
            )
            return None
        return await handler(event, data)
