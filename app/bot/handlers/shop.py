from __future__ import annotations

import math
import re
from contextlib import suppress
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.formatting import callback_int, price, respond
from app.bot.keyboards import (
    get_product_detail_keyboard,
    get_products_keyboard,
)
from app.services import Services

router = Router(name="shop_router")

PAGE_SIZE = 12


def is_redundant_description(title: str, description: str) -> bool:
    if not description or not description.strip():
        return True
    t = re.sub(r"[^a-zA-Z0-9]", "", title).lower()
    d = re.sub(r"[^a-zA-Z0-9]", "", description).lower()
    if not d or t == d:
        return True
    t_no_vpn = t.replace("vpn", "")
    d_no_vpn = d.replace("vpn", "")
    if t_no_vpn == d_no_vpn or t_no_vpn in d_no_vpn or d_no_vpn in t_no_vpn:
        if abs(len(d) - len(t)) < 8:
            return True
    return False


async def product_view(services: Services, product: dict[str, Any], tg_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user = await services.users.get(tg_user_id)
    balance = user["balance"] if user else 0.0
    symbol = await services.settings.get("currency_symbol")
    stock = product.get("stock", 0)
    description = escape(product.get("description") or "").strip()
    icon = escape(product.get("icon") or "💎")
    title = escape(product["title"])

    stock_text = f"<b>{stock}</b> Available" if stock > 0 else "<b>Out of Stock ❌</b>"
    duration = escape(product.get("duration_label") or "Instant")

    text = f"{icon} <b>{title}</b>\n\n"
    if description and not is_redundant_description(product["title"], product.get("description") or ""):
        text += f"<i>{description}</i>\n\n"
    text += (
        f"💵 <b>Price:</b> <code>{price(symbol, product['price'])}</code>\n"
        f"⏳ <b>Validity:</b> {duration}\n"
        f"📦 <b>Stock:</b> {stock_text}\n"
        f"💳 <b>Your Balance:</b> <code>{price(symbol, balance)}</code>"
    )

    keyboard = get_product_detail_keyboard(
        product_id=product["id"],
        category_id=product.get("category_id") or 0,
        has_stock=stock > 0,
        user_has_enough_balance=balance >= product["price"],
        price=product["price"],
        currency_symbol=symbol,
    )
    return text, keyboard


@router.message(Command("products"))
@router.message(Command("shop"))
@router.message(Command("buy"))
@router.message(F.text == "🛍️ Products")
@router.message(F.text == "🛒 Products")
@router.message(F.text == "🛍️ Buy Products")
@router.message(F.text == "🛒 Buy Products")
@router.message(F.text == "🛍️ Shop")
@router.message(F.text == "🛒 Shop")
@router.message(F.text == "🔥 Shop 🔥")
@router.message(F.text.casefold() == "products")
@router.message(F.text.casefold() == "shop")
@router.message(F.text.casefold().contains("products"))
@router.message(F.text.casefold().contains("buy products"))
@router.message(F.text == "পণ্য কিনুন")
@router.callback_query(F.data == "open_shop")
async def show_products_list(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Direct 1-click product catalog list matching Screenshot 2."""
    await state.clear()
    paused_msg = await services.settings.paused_message()
    if paused_msg:
        await respond(event, f"⚠️ <b>Shop Temporarily Closed</b>\n\n{escape(paused_msg)}")
        return


    products = await services.catalog.products(active_only=True, limit=100, in_stock_first=True)
    symbol = await services.settings.get("currency_symbol")

    if not products:
        await respond(event, "🛍️ <b>No products currently available.</b>\nPlease check back later.")
        return

    total_pages = max(1, math.ceil(len(products) / PAGE_SIZE))
    page = 1
    page_products = products[0:PAGE_SIZE]

    keyboard = get_products_keyboard(
        products=page_products,
        page=page,
        total_pages=total_pages,
        currency_symbol=symbol,
    )
    await respond(
        event,
        "🛍️ <b>Available Products:</b>",
        keyboard,
    )


@router.callback_query(F.data == "noop")
async def handle_noop(query: CallbackQuery):
    with suppress(TelegramBadRequest):
        await query.answer()


@router.callback_query(F.data.startswith("shop_p_all_"))
async def paginate_products(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    parts = query.data.split("_")
    requested_page = int(parts[-1]) if parts[-1].isdigit() else 1

    with suppress(TelegramBadRequest):
        await query.answer("Refreshed! 🔄")

    products = await services.catalog.products(active_only=True, limit=100, in_stock_first=True)
    symbol = await services.settings.get("currency_symbol")

    total_pages = max(1, math.ceil(len(products) / PAGE_SIZE))
    page = min(max(requested_page, 1), total_pages)
    page_products = products[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    keyboard = get_products_keyboard(
        products=page_products,
        page=page,
        total_pages=total_pages,
        currency_symbol=symbol,
    )
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                "🛍️ <b>Available Products:</b>",
                reply_markup=keyboard,
            )


@router.callback_query(F.data.startswith("prod_"))
async def show_product_detail(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    product_id = callback_int(query.data, "prod_")
    product = await services.catalog.product(product_id) if product_id is not None else None
    if not product or not product["is_active"]:
        with suppress(TelegramBadRequest):
            await query.answer("Product not found or currently unavailable.", show_alert=True)
        return
    text, keyboard = await product_view(services, product, query.from_user.id)
    await respond(query, text, keyboard)


@router.callback_query(F.data.startswith("buy_"))
async def execute_purchase(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    parts = (query.data or "").split("_")
    if len(parts) != 3 or not parts[1].isdigit() or not re.fullmatch(r"[0-9a-f]{32}", parts[2]):
        await query.answer("Please reopen the product to confirm your purchase.", show_alert=True)
        return

    success, message, order = await services.purchases.purchase(
        query.from_user.id, int(parts[1]), request_id=f"bot-{parts[2]}"
    )
    if not success or not order:
        with suppress(TelegramBadRequest):
            await query.answer(f"⚠️ {message}", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer("🎉 Purchase Successful!", show_alert=False)

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"✅ <b>Purchase Successful!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>{escape(order.get('product_title', 'Product'))}</b>\n\n"
                "<i>Your order details and delivery are below 👇</i>",
                reply_markup=None,
            )

