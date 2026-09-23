from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from contextlib import suppress

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

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


class Debounce(BaseMiddleware):
    """Drops rapid duplicate clicks from the same user on the same button/action within COOLDOWN seconds."""

    COOLDOWN = 1.0  # seconds

    def __init__(self, cooldown: float = 1.0) -> None:
        self.cooldown = cooldown
        self._last_actions: OrderedDict[tuple[int, str], float] = OrderedDict()
        self._locks: dict[int, asyncio.Lock] = {}

    def _get_lock(self, user_id: int) -> asyncio.Lock:
        lock = self._locks.get(user_id)
        if lock is None:
            if len(self._locks) > 5000:
                self._locks = {uid: lock for uid, lock in self._locks.items() if lock.locked()}
            lock = asyncio.Lock()
            self._locks[user_id] = lock
        return lock

    async def __call__(self, handler, event, data):
        user = event.from_user
        if not user:
            return await handler(event, data)

        action_key = ""
        if isinstance(event, CallbackQuery):
            action_key = f"cb:{event.data or ''}"
        elif isinstance(event, Message):
            text = (event.text or event.caption or "").strip()
            if text:
                action_key = f"msg:{text.lower()}"

        if not action_key:
            return await handler(event, data)

        now = time.monotonic()
        key = (user.id, action_key)

        lock = self._get_lock(user.id)
        async with lock:
            last_time = self._last_actions.get(key, 0.0)
            if now - last_time < self.cooldown:
                # Duplicate rapid click within cooldown window
                if isinstance(event, CallbackQuery):
                    with suppress(Exception):
                        await event.answer()
                elif isinstance(event, Message):
                    with suppress(Exception):
                        await event.delete()
                return None

            self._last_actions[key] = now
            self._last_actions.move_to_end(key)
            while len(self._last_actions) > 10000:
                self._last_actions.popitem(last=False)

        return await handler(event, data)


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
                alert_msg = "Please join our channel first!" if len(missing) == 1 else "Please join the channels first!"
                await event.answer(
                    "Verification is temporarily unavailable. Please retry shortly."
                    if any(c.get("verification_unavailable") for c in missing)
                    else f"⚠️ {alert_msg}",
                    show_alert=True,
                )
            services = data.get("services")
            store_name = await services.settings.get("store_name") if services else "Digital Mart"
            await message.answer(
                gate_text(missing, store_name),
                reply_markup=get_gate_keyboard(missing),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            return None
        return await handler(event, data)


class AuditActor(BaseMiddleware):
    async def __call__(self, handler, event, data):
        from app.services.audit import actor
        user = getattr(event, 'from_user', None)
        context = actor.set(f'telegram:{user.id}' if user else 'telegram:unknown')
        try:
            return await handler(event, data)
        finally:
            actor.reset(context)
