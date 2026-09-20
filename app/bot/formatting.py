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


async def respond(event: Message | CallbackQuery, text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    """Replace the message behind a pressed button, or reply to a typed message or command."""
    if isinstance(event, CallbackQuery):
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
        await event.answer(text, reply_markup=keyboard)


def price(symbol: str, amount: float) -> str:
    return f"{escape(symbol)}{amount:.2f}"


def format_dual_price(
    amount: float,
    symbol: str = "৳",
    usd_rate: float | None = None,
    show_usd: bool = True,
) -> str:
    amount_str = f"{amount:g} {symbol}" if amount == int(amount) else f"{amount:.2f} {symbol}"
    if show_usd and usd_rate and usd_rate > 0:
        usd = round(amount / usd_rate, 2)
        return f"{amount_str} (${usd:.2f})"
    return amount_str


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
