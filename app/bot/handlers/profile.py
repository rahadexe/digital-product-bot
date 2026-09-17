from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from html import escape
import math

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.formatting import callback_int, price, respond
from app.bot.keyboards import get_account_keyboard
from app.services import Services

router = Router(name="profile_router")

ORDERS_PAGE_SIZE = 8
INLINE_CREDENTIAL_LIMIT = 2800




@router.message(Command("account"))
@router.message(F.text == "👤 Account")
@router.message(F.text == "💳 My Balance")
@router.message(F.text == "💰 My Balance")
@router.message(F.text == "💼 Account")
@router.message(F.text.casefold() == "account")
@router.message(F.text.casefold() == "balance")
@router.callback_query(F.data == "open_account")
@router.callback_query(F.data == "open_balance")
async def show_user_profile(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    stats = await services.users.stats(tg_user.id)
    user = stats.get("user", {})
    symbol = await services.settings.get("currency_symbol")
    user_name = escape(tg_user.full_name or tg_user.first_name or "Customer")
    text = (
        f"👤 <b>Account</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>User ID:</b> <code>{tg_user.id}</code>\n"
        f"👤 <b>Name:</b> {user_name}\n"
        f"💰 <b>Current Balance:</b> <code>{price(symbol, user.get('balance', 0.0))}</code>\n"
        f"📦 <b>Total Orders:</b> {stats.get('order_count', 0)}\n"
        f"💸 <b>Total Spent:</b> {price(symbol, stats.get('total_spent', 0.0))}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await respond(event, text, get_account_keyboard())


@router.message(Command("orders"))
@router.message(F.text == "📦 Orders")
@router.message(F.text == "📦 My Orders")
@router.message(F.text == "📦 Order History")
@router.message(F.text.casefold() == "orders")
@router.callback_query(F.data == "open_orders")
@router.callback_query(F.data.startswith("orders_page_"))
async def show_order_history(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    page = (callback_int(event.data, "orders_page_") or 0) if isinstance(event, CallbackQuery) else 0
    orders, total = await services.purchases.customer_orders(tg_user.id, limit=ORDERS_PAGE_SIZE, offset=page * ORDERS_PAGE_SIZE)
    symbol = await services.settings.get("currency_symbol")

    if not orders:
        text = "📦 <b>Orders:</b>\n\nYou have no orders yet."
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛍️ Products", callback_data="open_shop", style="success")],
            ]
        )
    else:
        total_pages = max(1, math.ceil(total / ORDERS_PAGE_SIZE))
        cur_page = page + 1
        text = f"📦 <b>Orders ({total}):</b>"
        buttons = []
        for order in orders:
            status = "↩️" if order["status"] != "completed" else "⏳" if order.get("fulfillment") == "waiting" else "✅"
            price_val = order["price"]
            price_str = f"{price_val:g}{symbol}" if price_val == int(price_val) else f"{price_val:.1f}{symbol}"
            label = f"#{order['id']} {order['product_title']} {price_str} ({status})"
            buttons.append([InlineKeyboardButton(text=label[:64], callback_data=f"view_order_{order['id']}", style="primary")])

        nav_row = []
        if total_pages > 1:
            if cur_page == 1:
                nav_row = [
                    InlineKeyboardButton(text="🔄 Refresh", callback_data=f"orders_page_{page}", style="success"),
                    InlineKeyboardButton(text=f"{cur_page}/{total_pages}", callback_data=f"orders_page_{page}"),
                    InlineKeyboardButton(text="▶ Next", callback_data=f"orders_page_{page + 1}", style="primary"),
                ]
            elif cur_page == total_pages:
                nav_row = [
                    InlineKeyboardButton(text="◀ Prev", callback_data=f"orders_page_{page - 1}", style="primary"),
                    InlineKeyboardButton(text=f"{cur_page}/{total_pages}", callback_data=f"orders_page_{page}"),
                    InlineKeyboardButton(text="🔄 Refresh", callback_data=f"orders_page_{page}", style="success"),
                ]
            else:
                nav_row = [
                    InlineKeyboardButton(text="◀ Prev", callback_data=f"orders_page_{page - 1}", style="primary"),
                    InlineKeyboardButton(text=f"🔄 {cur_page}/{total_pages}", callback_data=f"orders_page_{page}", style="success"),
                    InlineKeyboardButton(text="▶ Next", callback_data=f"orders_page_{page + 1}", style="primary"),
                ]
        elif total > 0:
            nav_row = [
                InlineKeyboardButton(text="🔄 Refresh", callback_data="orders_page_0", style="success"),
                InlineKeyboardButton(text="1/1", callback_data="orders_page_0"),
            ]

        if nav_row:
            buttons.append(nav_row)
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await respond(event, text, keyboard)


@router.callback_query(F.data.startswith("view_order_"))
async def view_order_detail(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    order_id = callback_int(query.data, "view_order_")
    # Ownership is part of the lookup: another customer's order ID finds nothing.
    order = await services.purchases.order_for_customer(query.from_user.id, order_id) if order_id is not None else None
    if not order:
        with suppress(TelegramBadRequest):
            await query.answer("Order not found.", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await query.answer()
    if not query.message:
        return

    back = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀ Back", callback_data="open_orders", style="danger")]])
    if order["status"] == "completed" and order.get("fulfillment") == "waiting":
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"⏳ <b>Order #{order['id']}: {escape(order['product_title'])}</b>\n\n"
                "Paid. Your item is being prepared and will be sent here soon.",
                reply_markup=back,
            )
        return

    if len(order["delivered_item"]) > INLINE_CREDENTIAL_LIMIT:
        await query.message.answer_document(BufferedInputFile(order["delivered_item"].encode(), filename=f"order-{order_id}.txt"))
        return

    created = order["created_at"]
    date = created.strftime("%Y-%m-%d %H:%M UTC") if isinstance(created, datetime) else str(created)
    symbol = await services.settings.get("currency_symbol")
    text = (
        f"📦 <b>Order #{order['id']} Details</b>\n\n"
        f"🏷️ <b>Product:</b> {escape(order['product_title'])}\n"
        f"💵 <b>Price Paid:</b> {price(symbol, order['price'])}\n"
        f"📅 <b>Date:</b> {date}\n"
        f"🔖 <b>Status:</b> {order['status'].upper()}\n\n"
        f"🔑 <b>Delivered Credentials:</b>\n"
        f"<code>{escape(order['delivered_item'])}</code>\n\n"
        "<i>(Tap the button below or tap the code to copy)</i>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Copy Credentials", copy_text=CopyTextButton(text=order["delivered_item"]), style="success")],
            [InlineKeyboardButton(text="◀ Back", callback_data="open_orders", style="danger")],
        ]
    )
    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=keyboard)


DEPOSIT_STATUS = {"pending": "🟡 Pending review", "approved": "✅ Approved", "rejected": "❌ Rejected"}
DEPOSIT_HISTORY_LIMIT = 10


@router.callback_query(F.data == "open_deposits")
async def show_deposit_history(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    deposits = await services.deposits.history(tg_user.id, limit=DEPOSIT_HISTORY_LIMIT)
    symbol = await services.settings.get("currency_symbol")
    if not deposits:
        text = "💳 <b>Deposits:</b>\n\nYou have no deposits yet."
    else:
        lines = [f"💳 <b>Deposits (latest {len(deposits)}):</b>"]
        for deposit in deposits:
            created = deposit["created_at"]
            date = created.strftime("%Y-%m-%d") if isinstance(created, datetime) else str(created)[:10]
            lines.append(
                f"\n<b>#{deposit['id']}</b> · {price(symbol, deposit['amount'])} · {escape(deposit['method_name'])}\n"
                f"{DEPOSIT_STATUS.get(deposit['status'], deposit['status'])} · {date}"
            )
            if deposit["status"] == "rejected" and deposit["admin_note"]:
                lines.append(f"<i>{escape(deposit['admin_note'])}</i>")
        text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Deposit", callback_data="open_deposit_from_history", style="success")],
            [InlineKeyboardButton(text="◀ Back", callback_data="open_account", style="danger")],
        ]
    )
    await respond(event, text, keyboard)



