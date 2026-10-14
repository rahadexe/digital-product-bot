"""Telegram presentation helpers: replying to either kind of update, escaped money, operator HTML and callback data."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from html import escape
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup

TELEGRAM_TEXT_LIMIT = 4000

# Tracks active interactive menu message_id per chat for seamless single-screen UX.
_last_menu_messages: dict[int, int] = {}
_chat_active_messages: dict[int, set[int]] = {}
MAX_TRACKED_MENU_CHATS = 10000
MAX_TRACKED_MENU_MESSAGES = 32


def remember_menu_message(chat_id: int, message_id: int) -> None:
    """Store the active menu message ID for a chat."""
    _last_menu_messages[chat_id] = message_id
    if chat_id not in _chat_active_messages:
        _chat_active_messages[chat_id] = set()
    _chat_active_messages[chat_id].add(message_id)
    while len(_chat_active_messages[chat_id]) > MAX_TRACKED_MENU_MESSAGES:
        _chat_active_messages[chat_id].remove(min(_chat_active_messages[chat_id]))
    while len(_last_menu_messages) > MAX_TRACKED_MENU_CHATS:
        forget_menu_message(next(iter(_last_menu_messages)))


def forget_menu_message(chat_id: int) -> None:
    """Clear the stored active menu message ID for a chat."""
    _last_menu_messages.pop(chat_id, None)
    _chat_active_messages.pop(chat_id, None)


def get_last_menu_message(chat_id: int) -> int | None:
    """Retrieve the stored active menu message ID for a chat."""
    return _last_menu_messages.get(chat_id)


AUTO_DELETE_ENABLED: bool = False


async def _quiet_delete(bot: Any, chat_id: int, message_id: int) -> None:
    """Quietly delete a message in the background without raising exceptions."""
    if not AUTO_DELETE_ENABLED:
        return
    if not bot or not chat_id or not message_id:
        return
    with suppress(Exception):
        async with asyncio.timeout(5):
            await bot.delete_message(chat_id=chat_id, message_id=message_id)


def clean_previous_menu(bot: Any, chat_id: int, current_msg_id: int | None = None) -> None:
    """Clean up any previously active menu message in the background."""
    if not AUTO_DELETE_ENABLED:
        return
    old_id = _last_menu_messages.pop(chat_id, None)
    all_ids = _chat_active_messages.pop(chat_id, set())
    if old_id:
        all_ids.add(old_id)
    if bot and all_ids:
        for mid in all_ids:
            if mid != current_msg_id:
                asyncio.create_task(_quiet_delete(bot, chat_id, mid))


async def respond(event: Message | CallbackQuery, text: str, keyboard: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None) -> None:
    """Replace the message behind a pressed button, or reply to a typed message or command."""
    if isinstance(event, CallbackQuery):
        msg = getattr(event, "message", None)
        chat = getattr(msg, "chat", None)
        chat_id = getattr(chat, "id", None)
        msg_id = getattr(msg, "message_id", None)
        if chat_id and msg_id:
            remember_menu_message(chat_id, msg_id)

        async def acknowledge() -> None:
            with suppress(TelegramBadRequest):
                await event.answer()

        async def replace() -> None:
            if event.message:
                if isinstance(keyboard, ReplyKeyboardMarkup):
                    if AUTO_DELETE_ENABLED:
                        with suppress(TelegramBadRequest):
                            await event.message.delete()
                    await event.message.answer(text, reply_markup=keyboard)
                else:
                    with suppress(TelegramBadRequest):
                        await event.message.edit_text(text, reply_markup=keyboard)

        await asyncio.gather(acknowledge(), replace())
    else:
        try:
            await event.answer(text, reply_markup=keyboard)
        except TelegramBadRequest as exc:
            err_msg = str(exc).lower()
            if "document_invalid" in err_msg or "custom_emoji" in err_msg or "parse" in err_msg:
                from app.bot.middlewares import strip_custom_emojis
                with suppress(Exception):
                    await event.answer(strip_custom_emojis(text), reply_markup=keyboard)
            else:
                raise


_DEFAULT_USD_RATE: float = 125.0


def configure_pricing(usd_rate: float | None = None, *args, **kwargs) -> None:
    """Keep in-memory pricing defaults up to date with database settings."""
    global _DEFAULT_USD_RATE
    if usd_rate is not None and usd_rate > 0:
        _DEFAULT_USD_RATE = float(usd_rate)


def format_dual_price(
    amount: float,
    symbol: str = "$",
    usd_rate: float | None = None,
    show_usd: bool | None = None,
    lang: str | None = None,
) -> str:
    try:
        amt = float(amount)
        amt_str = f"{amt:g} {symbol}" if amt == int(amt) else f"{amt:.2f} {symbol}"
    except (ValueError, TypeError):
        amt = 0.0
        amt_str = f"{amount} {symbol}"

    rate = usd_rate if usd_rate is not None else _DEFAULT_USD_RATE
    display_usd = show_usd if show_usd is not None else False

    if symbol in ("$", "USD"):
        return f"${amt:g}" if amt == int(amt) else f"${amt:.2f}"

    # If language is English and USD display is active, show clean USD ($):
    if lang == "en" and display_usd and rate and rate > 0:
        usd = round(amt / rate, 2)
        return f"${usd:g}" if usd == int(usd) else f"${usd:.2f}"

    # In Bengali (or default), show clean single Tk currency (e.g. 44 ৳):
    return amt_str


def price(
    symbol: str,
    amount: float,
    usd_rate: float | None = None,
    show_usd: bool | None = None,
    lang: str | None = None,
) -> str:
    return format_dual_price(amount, symbol=escape(symbol), usd_rate=usd_rate, show_usd=show_usd, lang=lang)


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
