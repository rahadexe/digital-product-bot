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

import asyncio
from collections import OrderedDict
from contextlib import suppress
from contextvars import ContextVar
from html import escape
from typing import Any

from aiogram import BaseMiddleware, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.formatting import (
    _quiet_delete,
    format_dual_price,
    get_last_menu_message,
    remember_menu_message,
    respond,
)
from app.bot.icons import ICON_CROSS, ICON_SHOP, ICON_VIP, Icons
from app.bot.keyboards import extract_emoji_and_name
from app.core.i18n import t
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


def _prompt_text(examples: str, lang: str = "en") -> str:
    return (
        f"{t('search_title', lang)}\n\n"
        f"{t('search_prompt', lang)}\n\n"
        f"<i>{t('search_try', lang)}: {escape(examples)}</i>"
    )


def _prompt_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data="back_to_main",
        ),
        InlineKeyboardButton(
            text=t("btn_all_products", lang),
            callback_data="open_categories",
        ),
    ]])


async def _examples(services: Services) -> str:
    products = await services.catalog.products(limit=3, active_only=True)
    return ", ".join(p["title"].strip()[:18] for p in products) if products else "Netflix, VPN"


async def prompt_search(message: Message, state: FSMContext, services: Services) -> None:
    """What the Search button does: arm one search and ask for the term."""
    await search_entry(message, state, services)


@router.message(Command("search"))
@router.message(F.text.in_({
    "🔍 Search", "Search Products", "Search", "search",
    "🔍 SEARCH", "SEARCH", "SEARCH PRODUCTS",
    "🔍 সার্চ", "সার্চ",
}))
@router.callback_query(F.data == "open_search")
async def search_entry(event: Message | CallbackQuery, state: FSMContext, services: Services) -> None:
    _search_handled.set(True)
    await state.clear()
    await state.set_state(SearchStates.waiting_for_term)
    tg_user = event.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    examples = await _examples(services)
    text = _prompt_text(examples, lang=lang)
    kb = _prompt_keyboard(lang=lang)

    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()
        if event.message:
            await state.update_data(search_msg_id=event.message.message_id)
            with suppress(TelegramBadRequest):
                await event.message.edit_text(text, reply_markup=kb)
    else:
        sent = await event.answer(text, reply_markup=kb)
        if sent:
            await state.update_data(search_msg_id=sent.message_id)


@router.callback_query(F.data == "search_again")
async def search_again(query: CallbackQuery, state: FSMContext, services: Services) -> None:
    _search_handled.set(True)
    await state.clear()
    await state.set_state(SearchStates.waiting_for_term)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await state.update_data(search_msg_id=query.message.message_id)
        lang = await services.users.get_language(query.from_user.id) if query.from_user else "en"
        examples = await _examples(services)
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                _prompt_text(examples, lang=lang),
                reply_markup=_prompt_keyboard(lang=lang),
            )


def _product_button(product: dict, symbol: str, usd_rate: float | None = None,
                    show_usd: bool = True, callback: str = "prod", lang: str = "en", **kwargs) -> InlineKeyboardButton:
    icon = (product.get("icon") or "").strip()
    title = product['title'].strip()
    custom_id = str(product.get("custom_emoji_id") or "").strip()
    if custom_id.isdigit():
        leading_emoji, remaining_title = extract_emoji_and_name(title)
        if leading_emoji and remaining_title:
            title = remaining_title
    elif icon and not title.startswith(icon):
        title = f"{icon} {title}"
    price = format_dual_price(product["price"], symbol, usd_rate=usd_rate, show_usd=show_usd, lang=lang)
    label = f"{title[:26]} · {price}"
    return InlineKeyboardButton(
        text=label[:64],
        callback_data=f"{callback}_{product['id']}",
        icon_custom_emoji_id=custom_id if custom_id.isdigit() else None,
    )


def _closing_row(lang: str = "en") -> list[list[InlineKeyboardButton]]:
    search_again = "🔍 Search again" if lang != "bn" else "🔍 আবার খুঁজুন"
    return [
        [
            InlineKeyboardButton(
                text=search_again,
                callback_data="search_again",
            )
        ],
        [
            InlineKeyboardButton(
                text=t("btn_all_products", lang),
                callback_data="open_categories",
            ),
            InlineKeyboardButton(
                text=t("btn_main_menu", lang),
                callback_data="back_to_main",
            ),
        ],
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


async def _results(services: Services, term: str, lang: str = "en") -> tuple[str, InlineKeyboardMarkup]:
    matches = await services.catalog.search(term, limit=RESULTS)
    values = await services.settings.values()
    symbol = values.get("currency_symbol", "$")
    usd_rate = float(values.get("usd_rate") or 0) or None
    closing = _closing_row(lang)

    if not matches:
        recent_products = await services.catalog.products(limit=5, active_only=True)
        rows = [[_product_button(p, symbol, usd_rate=usd_rate, callback="sprod", lang=lang)] for p in recent_products]
        rows.extend(closing)
        no_match_text = (
            f"{ICON_CROSS} <b>Please try a different name:</b>"
            if lang != "bn"
            else f"{ICON_CROSS} <b>ভিন্ন নাম লিখে চেষ্টা করুন:</b>"
        )
        return no_match_text, InlineKeyboardMarkup(inline_keyboard=rows)

    rows = [[_product_button(p, symbol, usd_rate=usd_rate, callback="sprod", lang=lang)] for p in matches]
    rows.extend(closing)
    shown = escape(term[:40])
    if lang == "bn":
        text = f"{ICON_SHOP} <b>“{shown}”-এর জন্য {len(matches)}টি ফলাফল পাওয়া গেছে:</b>"
    else:
        more = ("\n<i>Showing the closest matches. Type more of the name to narrow it.</i>"
                if len(matches) >= RESULTS else "")
        text = (f"{ICON_SHOP} <b>{len(matches)} match{'es' if len(matches) != 1 else ''} "
                f"for “{shown}”</b>{more}")
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(SearchStates.waiting_for_term, F.text)
async def search_products(message: Message, state: FSMContext, services: Services) -> None:
    _search_handled.set(True)
    state_data = await state.get_data()
    search_msg_id = state_data.get("search_msg_id")
    await state.clear()

    term = (message.text or "").strip()
    if not term or term.startswith("/") or len(term) > MAX_TERM or not message.from_user:
        return

    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    if chat_id and getattr(chat, "type", "") == "private":
        asyncio.create_task(_quiet_delete(message.bot, chat_id, message.message_id))

    _remember(_LAST_TERM, message.from_user.id, term)
    lang = await services.users.get_language(message.from_user.id)
    text, keyboard = await _results(services, term, lang=lang)

    target_msg_id = search_msg_id or (get_last_menu_message(chat_id) if chat_id else None)
    edited = False
    if target_msg_id and message.bot and chat_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=target_msg_id,
                text=text,
                reply_markup=keyboard,
            )
            remember_menu_message(chat_id, target_msg_id)
            edited = True
        except Exception:
            edited = False

    if not edited and chat_id:
        sent = await message.answer(text, reply_markup=keyboard)
        if sent:
            remember_menu_message(chat_id, sent.message_id)


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
    lang = await services.users.get_language(query.from_user.id) if query.from_user else "en"
    text, keyboard = await _results(services, term, lang=lang)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)

# Anything else a customer types gets no reply at all. There is deliberately no
# catch-all handler here: text no router claims is dropped by the dispatcher without
# a database write or a message back.
