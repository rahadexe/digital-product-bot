"""Anything a customer types that is not a button is treated as a product search.

This router is included last, after every other one, so it only ever sees text no other
handler wanted. Before it existed that text got no reply at all: a customer who typed
"netflix" was answered with silence, which reads as a broken bot rather than a miss.

There is no button and no conversation state. Searching is what typing already means.
"""

from __future__ import annotations

from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.formatting import format_dual_price
from app.bot.icons import ICON_CROSS, ICON_SHOP, Icons
from app.services import Services

router = Router(name="search_router")

MAX_TERM = 64
RESULTS = 8


@router.message(F.text)
async def search_products(message: Message, state: FSMContext, services: Services) -> None:
    if await state.get_state() is not None:
        # A prompt is waiting on this customer; its own handler owns what they type.
        return
    term = (message.text or "").strip()
    if not term or term.startswith("/") or len(term) > MAX_TERM:
        return

    matches = await services.catalog.search(term, limit=RESULTS)
    values = await services.settings.values()
    symbol = values.get("currency_symbol", "৳")
    usd_rate = float(values.get("usd_rate") or 0) or None
    show_usd = values.get("show_usd_price", "1") != "0"
    shown = escape(term[:40])

    if not matches:
        categories = await services.catalog.categories(active_only=True)
        rows = [[InlineKeyboardButton(text=c["name"][:28], callback_data=f"cat_{c['id']}",
                                      icon_custom_emoji_id=Icons.PRODUCTS)]
                for c in categories[:6]]
        await message.answer(
            f"{ICON_CROSS} <b>Nothing found for “{shown}”</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Try a shorter word, or pick a category:</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows) if rows else None,
        )
        return

    rows = []
    for product in matches:
        emoji_id = str(product.get("custom_emoji_id") or "")
        price = format_dual_price(product["price"], symbol, usd_rate=usd_rate, show_usd=show_usd)
        label = f"{product['title'][:26]} · {price}"
        button: dict = {"text": label[:64], "callback_data": f"prod_{product['id']}"}
        if emoji_id.isdigit():
            button["icon_custom_emoji_id"] = emoji_id
        else:
            button["icon_custom_emoji_id"] = Icons.CART
        rows.append([InlineKeyboardButton(**button)])

    more = ("\n<i>Showing the closest matches. Type more of the name to narrow it.</i>"
            if len(matches) >= RESULTS else "")
    with suppress(TelegramBadRequest):
        await message.answer(
            f"{ICON_SHOP} <b>{len(matches)} match{'es' if len(matches) != 1 else ''} "
            f"for “{shown}”</b>{more}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
