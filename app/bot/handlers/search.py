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

from app.bot.formatting import delete_active_menu, format_dual_price, respond
from app.bot.icons import ICON_CROSS, ICON_SHOP, Icons
from app.services import Services

router = Router(name="search_router")

MAX_TERM = 64
RESULTS = 8


async def prompt_search(message: Message, state: FSMContext, services: Services) -> None:
    """What the Search button does: say that typing is the search.

    No conversation state is started. The next thing they type falls through to the
    handler below exactly as it would have anyway, so tapping the button and simply
    typing lead to the same place."""
    await state.clear()
    products = await services.catalog.products(limit=3, active_only=True)
    examples = ", ".join(p["title"].strip()[:18] for p in products) if products else "Netflix, VPN"
    await respond(
        message,
        f"{ICON_SHOP} <b>Find a Product</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Type what you are looking for.\n\n"
        f"<i>Try: {escape(examples)}</i>\n\n"
        f"Send /cancel to abort.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
        ]]),
    )


@router.message(F.text.in_({"Search Products", "Search"}))
async def search_button(message: Message, state: FSMContext, services: Services) -> None:
    await prompt_search(message, state, services)

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
        recent_products = await services.catalog.products(limit=4, active_only=True)
        rows = []
        for product in recent_products:
            emoji_id = str(product.get("custom_emoji_id") or "")
            price = format_dual_price(product["price"], symbol, usd_rate=usd_rate, show_usd=show_usd)
            label = f"{product['title'][:26]} · {price}"
            btn: dict = {"text": label[:64], "callback_data": f"prod_{product['id']}"}
            if emoji_id.isdigit():
                btn["icon_custom_emoji_id"] = emoji_id
            else:
                btn["icon_custom_emoji_id"] = Icons.CART
            rows.append([InlineKeyboardButton(**btn)])

        rows.append([
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
        ])
        await message.answer(
            f"{ICON_CROSS} <b>Nothing found for “{shown}”</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Try searching with a different product name:</i>",
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
