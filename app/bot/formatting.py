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

# Tracks active interactive menu message_id per chat for seamless single-screen UX.
_last_menu_messages: dict[int, int] = {}
_chat_active_messages: dict[int, set[int]] = {}


def remember_menu_message(chat_id: int, message_id: int) -> None:
    """Store the active menu message ID for a chat."""
    _last_menu_messages[chat_id] = message_id
    if chat_id not in _chat_active_messages:
        _chat_active_messages[chat_id] = set()
    _chat_active_messages[chat_id].add(message_id)


def forget_menu_message(chat_id: int) -> None:
    """Clear the stored active menu message ID for a chat."""
    _last_menu_messages.pop(chat_id, None)
    _chat_active_messages.pop(chat_id, None)


async def _quiet_delete(bot: Any, chat_id: int, message_id: int) -> None:
    """Quietly delete a message in the background without raising exceptions."""
    if not bot or not chat_id or not message_id:
        return
    with suppress(Exception):
        await bot.delete_message(chat_id=chat_id, message_id=message_id)


def clean_previous_menu(bot: Any, chat_id: int, current_msg_id: int | None = None) -> None:
    """Clean up any previously active menu message in the background."""
    old_id = _last_menu_messages.pop(chat_id, None)
    all_ids = _chat_active_messages.pop(chat_id, set())
    if old_id:
        all_ids.add(old_id)
    if bot and all_ids:
        for mid in all_ids:
            if mid != current_msg_id:
                asyncio.create_task(_quiet_delete(bot, chat_id, mid))


async def respond(event: Message | CallbackQuery, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    """Replace the message behind a pressed button, or reply to a typed message or command.
    
    When replying to a Message (e.g. persistent keyboard button tap), any previously
    active menu and the incoming command message are automatically cleaned up in the
    background (non-blocking), keeping the chat pristine like a single-screen app.
    """
    if isinstance(event, CallbackQuery):
        msg = getattr(event, "message", None)
        if msg:
            chat = getattr(msg, "chat", None)
            chat_id = getattr(chat, "id", None)
            msg_id = getattr(msg, "message_id", None)
            if chat_id and msg_id:
                remember_menu_message(chat_id, msg_id)

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
        chat = getattr(event, "chat", None)
        chat_id = getattr(chat, "id", None)
        old_menu_id = _last_menu_messages.get(chat_id) if chat_id else None

        # 1. Answer immediately (zero delay for user perception)
        sent = await event.answer(text, reply_markup=keyboard)
        sent_id = getattr(sent, "message_id", None)
        if chat_id and sent_id:
            remember_menu_message(chat_id, sent_id)

        # 2. Quietly clean up previous menu in background
        bot = getattr(event, "bot", None)
        if bot and chat_id and old_menu_id and old_menu_id != sent_id:
            asyncio.create_task(_quiet_delete(bot, chat_id, old_menu_id))

        # 3. Quietly clean user's trigger message in private chats
        msg_id = getattr(event, "message_id", None)
        if bot and chat_id and msg_id and getattr(chat, "type", "") == "private":
            asyncio.create_task(_quiet_delete(bot, chat_id, msg_id))


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
