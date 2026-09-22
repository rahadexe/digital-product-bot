from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from contextlib import suppress
from typing import Any

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

    1. Same-action debounce: If the exact same button or command is pressed repeatedly in rapid succession
       (within SAME_ACTION_COOLDOWN seconds), duplicate updates are dropped immediately without processing.
       This prevents accidental double-taps or rapid key spamming from creating duplicate messages or duplicate actions.
    2. Rate-limit burst bucket: Each customer has a bucket of BURST taps that refills at RATE per second.
       While empty, updates are dropped and the user is warned at most once per NOTICE_SECONDS.
    """

    RATE = 2.0
    BURST = 8
    NOTICE_SECONDS = 10.0
    SAME_ACTION_COOLDOWN = 2.0
    TRACKED_USERS = 20000
    TRACKED_ACTIONS = 50000

    def __init__(self) -> None:
        # user id -> (tokens, refilled_at, last_notice_at)
        self._buckets: OrderedDict[int, tuple[float, float, float]] = OrderedDict()
        # (user_id, action_key) -> last_tap_time
        self._last_actions: OrderedDict[tuple[int, str], float] = OrderedDict()

    def _extract_action(self, event: Any) -> str | None:
        text = getattr(event, "text", None)
        if text:
            return f"msg:{text.strip()}"
        data = getattr(event, "data", None)
        if data:
            return f"cb:{data.strip()}"
        return None

    def _is_duplicate_tap(self, user_id: int, action: str, now: float) -> bool:
        key = (user_id, action)
        last_tap = self._last_actions.get(key)
        self._last_actions[key] = now
        self._last_actions.move_to_end(key)
        while len(self._last_actions) > self.TRACKED_ACTIONS:
            self._last_actions.popitem(last=False)
        return last_tap is not None and (now - last_tap) < self.SAME_ACTION_COOLDOWN

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

        action = self._extract_action(event)
        now = time.monotonic()
        if action and self._is_duplicate_tap(user.id, action, now):
            if isinstance(event, CallbackQuery) or (hasattr(event, "data") and not getattr(event, "text", None) and hasattr(event, "answer")):
                with suppress(Exception):
                    await event.answer()
            return None

        allowed, notify = self._take(user.id, now)
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
