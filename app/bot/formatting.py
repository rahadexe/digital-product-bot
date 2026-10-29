"""Telegram presentation helpers: replying to either kind of update, escaped money, operator HTML and callback data."""

from __future__ import annotations

import asyncio
import inspect
import math
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


async def respond(
    event: Message | CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    *,
    new_message: bool = False,
) -> None:
    """Replace the message behind a pressed button, or reply to a typed message or command.

    If new_message=True on a CallbackQuery, cleanly deletes the origin message and sends a fresh
    message so the Telegram client viewport naturally snaps to it without scroll collapse.
    """
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
                if isinstance(keyboard, ReplyKeyboardMarkup) or new_message:
                    with suppress(TelegramBadRequest):
                        await event.message.delete()
                    sent = await event.message.answer(text, reply_markup=keyboard)
                    sent_id = getattr(sent, "message_id", None)
                    if sent_id is not None and chat_id:
                        remember_menu_message(chat_id, int(sent_id))
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


def _money_text(value: float, digits: int = 2) -> str:
    if abs(value) < 1 and value != 0:
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def format_dual_price(
    amount: float,
    symbol: str = "$",
    usd_rate: float | None = None,
    show_usd: bool | None = None,
    lang: str | None = None,
    currency: str | None = None,
) -> str:
    """Format a canonical USD amount into user currency or dual equivalent."""
    try:
        usd = float(amount)
        if not math.isfinite(usd):
            usd = 0.0
    except (ValueError, TypeError):
        usd = 0.0
    usd_text = f"${_money_text(usd)}"
    rate = usd_rate if usd_rate is not None else _DEFAULT_USD_RATE

    # If explicit user currency is set:
    if currency:
        curr_upper = currency.strip().upper()
        if curr_upper == "BDT" and rate and rate > 0:
            bdt_text = f"{_money_text(usd * rate)} ৳"
            if show_usd is True:
                return f"{bdt_text} (≈{usd_text})"
            return bdt_text
        elif curr_upper == "USD":
            return usd_text

    # Legacy locale-based formatting:
    if (lang or "").lower() in {"bn", "en-bd"} and rate and rate > 0:
        bdt_text = f"{_money_text(usd * rate)} ৳"
        return f"{bdt_text} (≈{usd_text})"

    return usd_text


async def resolve_user_currency(services: Any, tg_user_id: int) -> str:
    """Safely get user currency ('BDT' or 'USD') with mock and fallback tolerance."""
    users_svc = getattr(services, "users", None)
    if users_svc:
        get_curr = getattr(users_svc, "get_currency", None)
        if callable(get_curr):
            try:
                res = get_curr(tg_user_id)
                if inspect.isawaitable(res):
                    val = await res
                    if isinstance(val, str) and val.upper() in {"BDT", "USD"}:
                        return val.upper()
                elif isinstance(res, str) and res.upper() in {"BDT", "USD"}:
                    return res.upper()
            except Exception:
                pass
        get_lang = getattr(users_svc, "get_language", None)
        if callable(get_lang):
            try:
                res = get_lang(tg_user_id)
                if inspect.isawaitable(res):
                    lang_val = await res
                else:
                    lang_val = str(res)
                return "USD" if str(lang_val).lower() == "en" else "BDT"
            except Exception:
                pass
    return "BDT"


def price(
    symbol: str,
    amount: float,
    usd_rate: float | None = None,
    show_usd: bool | None = None,
    lang: str | None = None,
) -> str:
    return format_dual_price(amount, symbol="$", usd_rate=usd_rate, show_usd=show_usd, lang=lang)


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
