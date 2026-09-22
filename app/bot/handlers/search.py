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
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.formatting import format_dual_price, respond
from app.bot.handlers.navigation import is_navigation, navigate
from app.bot.icons import ICON_CROSS, ICON_SHOP, Icons
from app.services import Services

router = Router(name="search_router")

MAX_TERM = 64
RESULTS = 8


async def _cleanup_search(event: Message | CallbackQuery, state: FSMContext) -> None:
    """Clean up the search card and ForceReply prompt, dismissing the soft keyboard."""
    data = await state.get_data()
    prompt_id = data.get("search_prompt_id")
    card_id = data.get("search_card_id")
    chat_id = 0
    if isinstance(event, CallbackQuery) and event.message and event.message.chat:
        chat_id = event.message.chat.id
    elif isinstance(event, Message) and event.chat:
        chat_id = event.chat.id
    bot = event.bot
    if bot and chat_id:
        if prompt_id:
            with suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=prompt_id)
        if card_id:
            with suppress(Exception):
                await bot.delete_message(chat_id=chat_id, message_id=card_id)
    await state.update_data(search_prompt_id=None, search_card_id=None)


async def prompt_search(message: Message, state: FSMContext, services: Services) -> None:
    """What the Search button does: open the typing keyboard and show a card with a Back button."""
    await _cleanup_search(message, state)
    await state.clear()
    products = await services.catalog.products(limit=3, active_only=True)
    examples = ", ".join(p["title"].strip()[:18] for p in products) if products else "Netflix, VPN"

    card_msg = await message.answer(
        f"{ICON_SHOP} <b>Find a Product</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Type what you are looking for.\n\n"
        f"<i>Try: {escape(examples)}</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="⬅️ Back",
                callback_data="search_back",
                style="primary",
                icon_custom_emoji_id=Icons.BACK,
            )
        ]]),
    )

    prompt_msg = await message.answer(
        "✍️ Type what you are looking for:",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder="Type product name (e.g. Netflix, VPN)...",
        ),
    )

    await state.update_data(
        search_card_id=card_msg.message_id,
        search_prompt_id=prompt_msg.message_id,
    )


@router.callback_query(F.data == "search_back")
async def handle_search_back(query: CallbackQuery, state: FSMContext, services: Services) -> None:
    with suppress(TelegramBadRequest):
        await query.answer()
    await _cleanup_search(query, state)
    await state.clear()


@router.message(Command("cancel"))
async def cancel_search(message: Message, state: FSMContext) -> None:
    await _cleanup_search(message, state)
    await state.clear()
    await message.answer(f"{ICON_CROSS} Search cancelled.")


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

    # If the customer tapped a menu button or typed a cancel/back word
    if is_navigation(term):
        await _cleanup_search(message, state)
        await navigate(term, message, state, services)
        return

    if term.lower() in ("back", "cancel", "exit", "close", "⬅️ back", "❌ cancel", "বাতিল", "ফিরে যান"):
        await _cleanup_search(message, state)
        await state.clear()
        return

    await _cleanup_search(message, state)
    await state.clear()

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
