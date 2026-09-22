"""Product search, started by the Search button and over after one search.

It used to be the other way round: this router is included last, and every text nothing
else claimed was searched. Tapping Search only printed a hint, so there was no search mode
to leave — a customer who had moved on to Deposit or a category still had whatever they
typed next searched, which read as a mode that never switched off.

Now Search arms a single search. The next text is the search term; results come with a
Search again button for a second one. Tapping anything else first disarms it
(EndSearchWhenLeaving), so search never outlives the screen that asked for it. A product
opened from the results has a Back button that returns to them. Text typed without
tapping Search gets no reply at all.
"""

from __future__ import annotations

from collections import OrderedDict
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


def _product_button(product: dict, symbol: str, usd_rate: float | None, show_usd: bool,
                    callback: str = "prod") -> InlineKeyboardButton:
    emoji_id = str(product.get("custom_emoji_id") or "")
    price = format_dual_price(product["price"], symbol, usd_rate=usd_rate, show_usd=show_usd)
    label = f"{product['title'][:26]} · {price}"
    return InlineKeyboardButton(
        text=label[:64], callback_data=f"{callback}_{product['id']}",
        icon_custom_emoji_id=emoji_id if emoji_id.isdigit() else Icons.CART,
    )


_CLOSING_ROW = [
    InlineKeyboardButton(text="Search again", callback_data="search_again", icon_custom_emoji_id=Icons.REFRESH),
    InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
]


# Which product screens were opened from a search, and with what term, so their Back
# button returns to the results instead of the product's category. Keyed by customer
# and product because the product screen is redrawn on every +/- tap and only knows
# those two. In memory: after a restart Back falls back to the category, which is
# where it always went before. Bounded so a busy shop cannot grow it without limit.
_OPENED_FROM_SEARCH: OrderedDict[tuple[int, int], str] = OrderedDict()
_LAST_TERM: OrderedDict[int, str] = OrderedDict()
_REMEMBERED = 20000


def _remember(store: OrderedDict, key, value) -> None:
    store[key] = value
    store.move_to_end(key)
    while len(store) > _REMEMBERED:
        store.popitem(last=False)


def opened_from_search(tg_user_id: int, product_id: int) -> bool:
    return (tg_user_id, product_id) in _OPENED_FROM_SEARCH


def forget_search_origin(tg_user_id: int, product_id: int) -> None:
    """The product was reached some other way, so its Back goes to the category again."""
    _OPENED_FROM_SEARCH.pop((tg_user_id, product_id), None)


async def _results(services: Services, term: str) -> tuple[str, InlineKeyboardMarkup]:
    matches = await services.catalog.search(term, limit=RESULTS)
    values = await services.settings.values()
    symbol = values.get("currency_symbol", "৳")
    usd_rate = float(values.get("usd_rate") or 0) or None
    show_usd = values.get("show_usd_price", "1") != "0"

    if not matches:
        recent_products = await services.catalog.products(limit=5, active_only=True)
        rows = [[_product_button(p, symbol, usd_rate, show_usd, "sprod")] for p in recent_products]
        rows.append(_CLOSING_ROW)
        return f"{ICON_CROSS} <b>Please try a different name:</b>", InlineKeyboardMarkup(inline_keyboard=rows)

    rows = [[_product_button(p, symbol, usd_rate, show_usd, "sprod")] for p in matches]
    rows.append(_CLOSING_ROW)
    shown = escape(term[:40])
    more = ("\n<i>Showing the closest matches. Type more of the name to narrow it.</i>"
            if len(matches) >= RESULTS else "")
    text = (f"{ICON_SHOP} <b>{len(matches)} match{'es' if len(matches) != 1 else ''} "
            f"for “{shown}”</b>{more}")
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(SearchStates.waiting_for_term, F.text)
async def search_products(message: Message, state: FSMContext, services: Services) -> None:
    _search_handled.set(True)
    # One search per tap of Search; "Search again" arms the next one.
    await state.clear()
    term = (message.text or "").strip()
    if not term or term.startswith("/") or len(term) > MAX_TERM or not message.from_user:
        return
    _remember(_LAST_TERM, message.from_user.id, term)
    text, keyboard = await _results(services, term)
    with suppress(TelegramBadRequest):
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^sprod_\d+$"))
async def open_search_result(query: CallbackQuery, state: FSMContext, services: Services) -> None:
    """A product opened from the results: the same screen, with Back leading to the results."""
    _search_handled.set(True)
    from app.bot.handlers.shop import show_product  # shop imports this module

    product_id = int(query.data.removeprefix("sprod_"))
    term = _LAST_TERM.get(query.from_user.id)
    if term:
        _remember(_OPENED_FROM_SEARCH, (query.from_user.id, product_id), term)
    await show_product(query, state, services, product_id)


@router.callback_query(F.data.regexp(r"^sback_\d+$"))
async def back_to_results(query: CallbackQuery, state: FSMContext, services: Services) -> None:
    _search_handled.set(True)
    product_id = int(query.data.removeprefix("sback_"))
    term = _OPENED_FROM_SEARCH.get((query.from_user.id, product_id))
    if not term:
        # Forgotten across a restart: go where Back went before search existed.
        from app.bot.handlers.shop import show_product
        await show_product(query, state, services, product_id, category_back=True)
        return
    await state.clear()
    text, keyboard = await _results(services, term)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)

# Anything else a customer types gets no reply at all. There is deliberately no
# catch-all handler here: text no router claims is dropped by the dispatcher without
# a database write or a message back.
