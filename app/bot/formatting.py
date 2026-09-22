"""Telegram presentation helpers: replying to either kind of update, escaped money, operator HTML and callback data."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from html import escape
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

TELEGRAM_TEXT_LIMIT = 4000


_ACTIVE_MENU_MESSAGES: dict[int, int] = {}
_MAX_TRACKED_CHATS = 20000


def clear_active_menu(chat_id: int) -> None:
    """Clear tracking for this chat's active menu message."""
    _ACTIVE_MENU_MESSAGES.pop(chat_id, None)


async def delete_active_menu(bot: Any, chat_id: int) -> None:
    """Delete the active menu message for this chat if one exists."""
    old_msg_id = _ACTIVE_MENU_MESSAGES.pop(chat_id, None)
    if old_msg_id and bot:
        with suppress(Exception):
            await bot.delete_message(chat_id=chat_id, message_id=old_msg_id)


async def respond(
    event: Message | CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
    *,
    delete_trigger: bool = True,
) -> None:
    """Replace the message behind a pressed button, or reply to a typed message or command.

    Option A Auto-Cleanup: When a user taps a bottom reply keyboard button, delete their previous
    active menu box and delete the incoming user command message so that the chat stays clean and free
    of duplicate menu blocks.
    """
    if isinstance(event, CallbackQuery):
        chat_id = event.message.chat.id if event.message and event.message.chat else 0
        if event.message and chat_id:
            _ACTIVE_MENU_MESSAGES[chat_id] = event.message.message_id

        # Both calls go to Telegram; sent together they cost one round trip instead of two.
        async def acknowledge() -> None:
            with suppress(TelegramBadRequest):
                await event.answer()

        async def replace() -> None:
            if event.message:
                with suppress(TelegramBadRequest):
                    await event.message.edit_text(text, reply_markup=keyboard)

        await asyncio.gather(acknowledge(), replace())
    else:
        chat_id = event.chat.id if event.chat else 0

        # 1. Delete previous active menu message in this chat
        if chat_id:
            await delete_active_menu(event.bot, chat_id)

        # 2. Delete the user's incoming button command message (e.g. "Buy VPN", "Proxy Shop")
        if delete_trigger:
            with suppress(Exception):
                await event.delete()

        # 3. Send the new menu message and track it
        new_msg = await event.answer(text, reply_markup=keyboard)
        if chat_id and new_msg:
            msg_id = getattr(new_msg, "message_id", None)
            if msg_id is not None:
                if len(_ACTIVE_MENU_MESSAGES) >= _MAX_TRACKED_CHATS:
                    for _ in range(1000):
                        _ACTIVE_MENU_MESSAGES.pop(next(iter(_ACTIVE_MENU_MESSAGES)), None)
                _ACTIVE_MENU_MESSAGES[chat_id] = msg_id


_DEFAULT_USD_RATE: float = 125.0
_SHOW_USD: bool = True


def configure_pricing(usd_rate: float | None = None, show_usd: bool | None = None) -> None:
    """Keep in-memory pricing defaults up to date with database settings."""
    global _DEFAULT_USD_RATE, _SHOW_USD
    if usd_rate is not None and usd_rate > 0:
        _DEFAULT_USD_RATE = float(usd_rate)
    if show_usd is not None:
        _SHOW_USD = bool(show_usd)


def format_dual_price(
    amount: float,
    symbol: str = "৳",
    usd_rate: float | None = None,
    show_usd: bool | None = None,
) -> str:
    try:
        amt = float(amount)
        amt_str = f"{amt:g} {symbol}" if amt == int(amt) else f"{amt:.2f} {symbol}"
    except (ValueError, TypeError):
        amt = 0.0
        amt_str = f"{amount} {symbol}"

    rate = usd_rate if usd_rate is not None else _DEFAULT_USD_RATE
    display_usd = show_usd if show_usd is not None else _SHOW_USD

    if display_usd and rate and rate > 0 and symbol not in ("$", "USD"):
        usd = round(amt / rate, 2)
        return f"{amt_str} ≈ ${usd:.2f}"
    return amt_str


def price(
    symbol: str,
    amount: float,
    usd_rate: float | None = None,
    show_usd: bool | None = None,
) -> str:
    return format_dual_price(amount, symbol=escape(symbol), usd_rate=usd_rate, show_usd=show_usd)


def callback_int(data: str | None, prefix: str) -> int | None:
    """The integer after ``prefix``. Modified clients can send any callback data, so anything else is None."""
    if not data or not data.startswith(prefix):
        return None
    value = data[len(prefix) :]
    return int(value) if value.isdigit() and len(value) <= 18 else None


def truncate(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def send_operator_html(send: Callable[..., Awaitable[Any]], text: str, **kwargs: Any) -> Any:
    """Send HTML written by an operator (notices, guides); fall back to plain text if Telegram rejects the markup."""
    try:
        return await send(text, **kwargs)
    except TelegramBadRequest as exc:
        if "parse" not in str(exc).lower():
            raise
        return await send(escape(text), **kwargs)
