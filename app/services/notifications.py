"""Telegram messages outside the durable outbox: customer and admin alerts, channel posts, membership checks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import BotCommand, InlineKeyboardMarkup, MenuButtonCommands

from app.services.admin_jobs import require_admin_delivery

if TYPE_CHECKING:
    from app.services.settings import SettingsService

logger = logging.getLogger("app.services.notifications")

FALLBACK_USERNAME = "PremiumHaven24Bot"

# Telegram shows this menu to everyone, so only customer commands belong here.
# The admin ones are listed by /admin and work whether or not they are listed.
COMMANDS = [
    BotCommand(command="start", description="Start"),
    BotCommand(command="api", description="API"),
    BotCommand(command="reseller", description="Reseller"),
]


class Notifier:
    def __init__(self, bot: Bot | None, settings: "SettingsService"):
        self.bot = bot
        self.settings = settings
        self._username: str | None = None
        self._pending: set[asyncio.Task] = set()

    async def configure_bot(self) -> None:
        if not self.bot:
            return
        try:
            await self.bot_username()
            await self.bot.set_my_commands(COMMANDS)
            await self.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("Bot identity cached as @%s; customer commands menu configured.", self._username)
        except Exception as exc:
            logger.warning("Could not configure bot commands: %s", type(exc).__name__)

    async def bot_username(self) -> str:
        if self._username:
            return self._username
        if self.bot:
            try:
                me = await self.bot.get_me()
                self._username = me.username or FALLBACK_USERNAME
                return self._username
            except Exception:
                pass
        return FALLBACK_USERNAME

    def in_background(self, notification: Coroutine[Any, Any, Any]) -> None:
        """
        Send a notification without making the request that caused it wait for Telegram.
        Notifications are best effort; anything that must arrive goes through the delivery outbox.
        """
        if not self.bot:
            notification.close()
            return
        task = asyncio.create_task(self._quietly(notification))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    @staticmethod
    async def _quietly(notification: Coroutine[Any, Any, Any]) -> None:
        try:
            await notification
        except Exception:
            logger.exception("Background notification failed.")

    async def drain(self, timeout: float = 5.0) -> None:
        if self._pending:
            _, pending = await asyncio.wait(set(self._pending), timeout=timeout)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

    async def send(self, chat_id: int | str, text: str, keyboard: InlineKeyboardMarkup | None = None,
                   *, clears_after: int = 0) -> bool:
        """Send a message, optionally one that takes itself away again.

        ``clears_after`` is for the notices that say something happened rather than
        carrying anything worth keeping: a payment confirmed, a purchase gone through.
        The balance and the order are both somewhere better, and a chat that fills up
        with them buries the messages that do matter. Anything a customer might need
        later Ã¢ÂÂ credentials, a receipt Ã¢ÂÂ is sent without it."""
        if not self.bot or not chat_id:
            return False
        try:
            message = await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            if clears_after > 0:
                self.in_background(self._clear_later(chat_id, message.message_id, clears_after))
            return True
        except TelegramRetryAfter:
            if require_admin_delivery.get():
                raise
            return False
        except Exception as exc:
            logger.warning("Could not send Telegram message to %s: %s", chat_id, type(exc).__name__)
            return False

    async def _clear_later(self, chat_id: int | str, message_id: int, seconds: int) -> None:
        """Telegram only lets a bot delete its own message for 48 hours; well within that."""
        await asyncio.sleep(seconds)
        try:
            await self.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            # Already gone, or the customer cleared the chat. Nothing to repair.
            pass

    async def send_admin(self, text: str, event: str = "general", keyboard: InlineKeyboardMarkup | None = None) -> bool:
        """
        Send a notification to all configured admin Telegram accounts.
        If an event type is toggled off in settings, the message is skipped.
        Mandatory events (waiting_order, deposit, system_error, general) cannot be toggled off.
        """
        if not self.bot:
            if require_admin_delivery.get():
                raise RuntimeError("Telegram bot unavailable")
            return False

        # Configurable event toggles
        if event == "order" and not await self.settings.flag("notify_admin_orders"):
            return False
        if event == "payment" and not await self.settings.flag("notify_admin_payments"):
            return False
        if event == "restock" and not await self.settings.flag("notify_admin_restock"):
            return False
        if event == "low_stock" and not await self.settings.flag("notify_admin_low_stock"):
            return False
        if event == "price_change" and not await self.settings.flag("notify_admin_price_change"):
            return False
        if event == "new_user" and not await self.settings.flag("notify_admin_new_user"):
            return False

        chat_ids = await self.settings.admin_chat_ids()
        if not chat_ids:
            if require_admin_delivery.get():
                raise RuntimeError("No admin recipient configured")
            return False

        async def deliver(chat_id):
            job_id = require_admin_delivery.get()
            if job_id:
                async with self.settings.db.connect() as conn:
                    if await conn.fetchval('SELECT 1 FROM admin_notification_deliveries WHERE job_id=$1 AND chat_id=$2 AND event=$3', job_id, chat_id, event):
                        return True
            sent = await self.send(chat_id, text, keyboard=keyboard)
            if sent and job_id:
                async with self.settings.db.connect() as conn:
                    await conn.execute('INSERT INTO admin_notification_deliveries(job_id,chat_id,event) VALUES($1,$2,$3) ON CONFLICT DO NOTHING', job_id, chat_id, event)
            return sent

        results = await asyncio.gather(
            *(deliver(chat_id) for chat_id in chat_ids),
            return_exceptions=True,
        )
        throttled = [r for r in results if isinstance(r, TelegramRetryAfter)]
        if require_admin_delivery.get() and throttled:
            raise max(throttled, key=lambda exc: exc.retry_after)
        if require_admin_delivery.get() and not all(r is True for r in results):
            raise RuntimeError("Admin alert delivery incomplete")
        return any(r is True for r in results)

    async def is_member(self, chat: str, user_id: int) -> bool:
        """Raises when membership cannot be verified, so callers can fail closed."""
        if not self.bot:
            raise RuntimeError("Telegram bot is not configured.")
        member = await self.bot.get_chat_member(chat_id=chat, user_id=user_id)
        return not (member.status in ("left", "kicked") or (member.status == "restricted" and not member.is_member))
