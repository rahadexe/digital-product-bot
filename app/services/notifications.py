"""Telegram messages outside the durable outbox: customer and admin alerts, channel posts, membership checks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from aiogram import Bot
from aiogram.types import BotCommand, InlineKeyboardMarkup, MenuButtonCommands, MenuButtonWebApp, WebAppInfo

if TYPE_CHECKING:
    from app.services.settings import SettingsService

logger = logging.getLogger("app.services.notifications")

FALLBACK_USERNAME = "subsmarket247bot"

COMMANDS = [
    BotCommand(command="start", description="Start the Bot"),
]


def menu_button(webapp_url: str) -> MenuButtonCommands | MenuButtonWebApp:
    """The button beside the chat input: the Mini App when it has an HTTPS address, otherwise the command list."""
    return MenuButtonCommands()


class Notifier:
    def __init__(self, bot: Bot | None, settings: "SettingsService"):
        self.bot = bot
        self.settings = settings
        self._username: str | None = None
        self._pending: set[asyncio.Task] = set()

    async def configure_bot(self, webapp_url: str = "") -> None:
        if not self.bot:
            return
        try:
            await self.bot_username()
            await self.bot.set_my_commands(COMMANDS)
            button = menu_button(webapp_url)
            await self.bot.set_chat_menu_button(menu_button=button)
            logger.info("Bot identity cached as @%s; commands and %s menu button configured.", self._username, button.type)
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
            await asyncio.wait(set(self._pending), timeout=timeout)

    async def send(self, chat_id: int | str, text: str, keyboard: InlineKeyboardMarkup | None = None) -> bool:
        if not self.bot or not chat_id:
            return False
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
            return True
        except Exception as exc:
            logger.warning("Could not send Telegram message to %s: %s", chat_id, type(exc).__name__)
            return False

    async def send_admin(self, text: str, event: str = "general", keyboard: InlineKeyboardMarkup | None = None) -> bool:
        """
        Send a notification to all configured admin Telegram accounts.
        If an event type is toggled off in settings, the message is skipped.
        Mandatory events (waiting_order, system_error, general) cannot be toggled off.
        """
        if not self.bot:
            return False

        # Configurable event toggles
        if event == "order" and not await self.settings.flag("notify_admin_orders"):
            return False
        if event == "deposit" and not await self.settings.flag("notify_admin_deposits"):
            return False
        if event == "payment" and not await self.settings.flag("notify_admin_payments"):
            return False
        if event == "restock" and not await self.settings.flag("notify_admin_restock"):
            return False
        if event == "price_change" and not await self.settings.flag("notify_admin_price_change"):
            return False
        if event == "new_user" and not await self.settings.flag("notify_admin_new_user"):
            return False

        chat_ids = await self.settings.admin_chat_ids()
        if not chat_ids:
            return False

        results = await asyncio.gather(
            *(self.send(chat_id, text, keyboard=keyboard) for chat_id in chat_ids),
            return_exceptions=True,
        )
        return any(r is True for r in results)

    async def is_member(self, chat: str, user_id: int) -> bool:
        """Raises when membership cannot be verified, so callers can fail closed."""
        if not self.bot:
            raise RuntimeError("Telegram bot is not configured.")
        member = await self.bot.get_chat_member(chat_id=chat, user_id=user_id)
        return not (member.status in ("left", "kicked") or (member.status == "restricted" and not member.is_member))
