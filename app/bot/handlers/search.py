"""Product search, started by the Search button and over after one search.

It used to be the other way round: this router is included last, and every text nothing
else claimed was searched. Tapping Search only printed a hint, so there was no search mode
to leave — a customer who had moved on to Deposit or a category still had whatever they
typed next searched, which read as a mode that never switched off.

Now Search arms a single search. The next text is the search term; results come with a
Search again button for a second one. Tapping anything else first disarms it
(EndSearchWhenLeaving), so search never outlives the screen that asked for it.
"""

from __future__ import annotations

from contextlib import suppress
from contextvars import ContextVar
from html import escape
from typing import Any

from aiogram import BaseMiddleware, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.formatting import format_dual_price
from app.bot.icons import ICON_CROSS, ICON_SHOP, ICON_VIP, Icons
from app.services import Services

router = Router(name="search_router")

MAX_TERM = 64
RESULTS = 6


class SearchStates(StatesGroup):
    waiting_for_term = State()


# Set by every search handler while it runs, so the middleware below can tell "the
# customer searched" apart from "the customer went somewhere else".
_search_handled: ContextVar[bool] = ContextVar("search_handled", default=False)


class EndSearchWhenLeaving(BaseMiddleware):
    """Disarm a pending search once the customer does anything other than search.

    Menu buttons and inline buttons are handled by earlier routers that do not know
    search exists, and several of them leave the conversation state alone, so the armed
    search survived them. This reads the state aiogram already loaded for the update
    (no extra query) and clears it only when a search was armed and nothing in this
    router answered.
    """

    async def __call__(self, handler, event, data: dict[str, Any]):
        token = _search_handled.set(False)
        try:
            return await handler(event, data)
        finally:
            state: FSMContext | None = data.get("state")
            if (not _search_handled.get() and state is not None
                    and data.get("raw_state") == SearchStates.waiting_for_term.state):
                with suppress(Exception):
                    # Only if a later step has not already moved them on to its own prompt.
                    if await state.get_state() == SearchStates.waiting_for_term.state:
                        await state.clear()
            _search_handled.reset(token)


def _prompt_text(examples: str) -> str:
    return (
        f"{ICON_VIP} <b>Find a Product</b>\n\n"
        f"Type what you are looking for.\n\n"
        f"<i>Try: {escape(examples)}</i>"
    )


_PROMPT_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
]])


async def _examples(services: Services) -> str:
    products = await services.catalog.products(limit=3, active_only=True)
    return ", ".join(p["title"].strip()[:18] for p in products) if products else "Netflix, VPN"


async def prompt_search(message: Message, state: FSMContext, services: Services) -> None:
    """What the Search button does: arm one search and ask for the term."""
    _search_handled.set(True)
    await state.clear()
    await state.set_state(SearchStates.waiting_for_term)
    await message.answer(_prompt_text(await _examples(services)), reply_markup=_PROMPT_KEYBOARD)


@router.message(F.text.in_({"Search Products", "Search"}))
async def search_button(message: Message, state: FSMContext, services: Services) -> None:
    await prompt_search(message, state, services)


@router.callback_query(F.data == "search_again")
async def search_again(query: CallbackQuery, state: FSMContext, services: Services) -> None:
    _search_handled.set(True)
    await state.clear()
    await state.set_state(SearchStates.waiting_for_term)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(_prompt_text(await _examples(services)), reply_markup=_PROMPT_KEYBOARD)


def _product_button(product: dict, symbol: str, usd_rate: float | None, show_usd: bool) -> InlineKeyboardButton:
    emoji_id = str(product.get("custom_emoji_id") or "")
    price = format_dual_price(product["price"], symbol, usd_rate=usd_rate, show_usd=show_usd)
    label = f"{product['title'][:26]} · {price}"
    return InlineKeyboardButton(
        text=label[:64], callback_data=f"prod_{product['id']}",
        icon_custom_emoji_id=emoji_id if emoji_id.isdigit() else Icons.CART,
    )


_CLOSING_ROW = [
    InlineKeyboardButton(text="Search again", callback_data="search_again", icon_custom_emoji_id=Icons.REFRESH),
    InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
]


@router.message(SearchStates.waiting_for_term, F.text)
async def search_products(message: Message, state: FSMContext, services: Services) -> None:
    _search_handled.set(True)
    # One search per tap of Search; "Search again" arms the next one.
    await state.clear()
    term = (message.text or "").strip()
    if not term or term.startswith("/") or len(term) > MAX_TERM:
        return

    matches = await services.catalog.search(term, limit=RESULTS)
    values = await services.settings.values()
    symbol = values.get("currency_symbol", "৳")
    usd_rate = float(values.get("usd_rate") or 0) or None
    show_usd = values.get("show_usd_price", "1") != "0"

    if not matches:
        recent_products = await services.catalog.products(limit=5, active_only=True)
        rows = [[_product_button(p, symbol, usd_rate, show_usd)] for p in recent_products]
        rows.append(_CLOSING_ROW)
        await message.answer(
            f"{ICON_CROSS} <b>Please try a different name:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    rows = [[_product_button(p, symbol, usd_rate, show_usd)] for p in matches]
    rows.append(_CLOSING_ROW)
    shown = escape(term[:40])
    more = ("\n<i>Showing the closest matches. Type more of the name to narrow it.</i>"
            if len(matches) >= RESULTS else "")
    with suppress(TelegramBadRequest):
        await message.answer(
            f"{ICON_SHOP} <b>{len(matches)} match{'es' if len(matches) != 1 else ''} "
            f"for “{shown}”</b>{more}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.message(F.text)
async def not_a_command(message: Message, state: FSMContext) -> None:
    """Text nobody asked for. It is no longer searched, but silence reads as a broken bot."""
    if await state.get_state() is not None:
        # A prompt is waiting on this customer; its own handler owns what they type.
        return
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    await message.answer(
        "মেনু থেকে একটা অপশন বেছে নিন। কোনো product খুঁজতে চাইলে <b>Search</b> চাপুন।",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Search", callback_data="search_again", icon_custom_emoji_id=Icons.REFRESH)
        ]]),
    )
