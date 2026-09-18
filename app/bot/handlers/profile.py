from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from html import escape
import math
from urllib.parse import quote

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
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BALANCE,
    ICON_CHECK,
    ICON_COIN,
    ICON_ID,
    ICON_KEY,
    ICON_MONEY,
    ICON_ORDERS,
    ICON_RESELLER,
    ICON_ROCKET,
    ICON_SPENT,
    ICON_STATS,
    ICON_TIMER,
    ICON_VIP,
    Icons,
)
from app.bot.keyboards import get_account_keyboard
from app.services import Services

router = Router(name="profile_router")

ORDERS_PAGE_SIZE = 8
INLINE_CREDENTIAL_LIMIT = 2800




@router.message(Command("account"))
@router.message(Command("profile"))
@router.message(F.text == "👤 My Profile")
@router.message(F.text == "My Profile")
@router.message(F.text.casefold() == "my profile")
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

    rank_val = (user.get("rank") or "Standard").strip()
    if rank_val.lower() in {"affiliate", "affiliate partner"}:
        account_type = "Affiliate Partner 🤝"
    elif rank_val.lower() in {"reseller", "reseller partner"}:
        account_type = "Reseller Partner 💼"
    elif rank_val.lower() in {"vip", "vip member", "vip customer"}:
        account_type = "VIP Member 💎"
    elif user.get("referral_count", 0) > 0:
        account_type = "Affiliate Partner 🤝"
    else:
        account_type = "Normal User 👤"

    text = (
        f"{ICON_ACCOUNT} <b>My Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_ID} <b>User ID:</b> <code>{tg_user.id}</code>\n"
        f"{ICON_ACCOUNT} <b>Name:</b> {user_name}\n"
        f"{ICON_RESELLER} <b>Account Type:</b> <b>{account_type}</b>\n"
        f"{ICON_BALANCE} <b>Current Balance:</b> <code>{price(symbol, user.get('balance', 0.0))}</code>\n"
        f"{ICON_ORDERS} <b>Total Orders:</b> {stats.get('order_count', 0)}\n"
        f"{ICON_SPENT} <b>Total Spent:</b> <code>{price(symbol, stats.get('total_spent', 0.0))}</code>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    await respond(event, text, get_account_keyboard())


@router.message(Command("referral"))
@router.message(Command("refer"))
@router.message(F.text.in_({"🎁 Refer & Earn", "Refer & Earn", "refer & earn", "রেফার", "রেফার করুন", "🎁 রেফার ও ইনকাম", "🎁 রেফার ও আর্ন", "রেফারেল", "🎁 রেফারেল"}))
@router.callback_query(F.data == "open_referral")
async def show_referral_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user = await services.users.get(tg_user.id)
    balance = user["balance"] if user else 0.0
    symbol = await services.settings.get("currency_symbol")
    reward_amount = await services.settings.number("referral_reward_amount")
    reward_enabled = await services.settings.flag("referral_enabled")

    reward_str = f"{reward_amount:g} {symbol}" if reward_amount == int(reward_amount) else f"{reward_amount:.2f} {symbol}"
    balance_str = f"{balance:g} {symbol}" if balance == int(balance) else f"{balance:.2f} {symbol}"

    async with services.db.connect() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) AS total_invited,
                COALESCE(SUM(amount), 0) AS total_earned
            FROM referral_rewards
            WHERE referrer_tg_id = $1
            """,
            tg_user.id,
        )
        total_invited = row["total_invited"] if row else 0
        total_earned = float(row["total_earned"]) if row else 0.0

    total_earned_str = f"{total_earned:g} {symbol}" if total_earned == int(total_earned) else f"{total_earned:.2f} {symbol}"
    status_badge = "🟢 Active" if reward_enabled and reward_amount > 0 else "⚪ Disabled"

    bot_user = await services.notifier.bot_username()
    ref_link = f"https://t.me/{bot_user}?start=ref_{tg_user.id}"
    store_name = (await services.settings.get("store_name")) or "Premium Haven"

    reward_unit = "TK"
    reward_display = f"{reward_amount:g} {reward_unit}" if reward_enabled and reward_amount > 0 else f"0 {reward_unit}"
    earned_display = f"{total_earned:g} {reward_unit}" if total_earned == int(total_earned) else f"{total_earned:.2f} {reward_unit}"

    tagline = (
        f"{ICON_ROCKET} <i>Share your link and earn {reward_display} per referral!</i>"
        if reward_enabled and reward_amount > 0
        else f"{ICON_ROCKET} <i>Share your referral link with friends!</i>"
    )

    text = (
        f"{ICON_ORDERS} <b>REFER & EARN</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_ACCOUNT} <b>Total Refers:</b> <code>{total_invited}</code>\n"
        f"{ICON_COIN} <b>Reward Per Refer:</b> <code>{reward_display}</code>\n"
        f"{ICON_BALANCE} <b>Total Earned:</b> <code>{earned_display}</code>\n\n"
        f"{tagline}\n\n"
        f"🔗 <b>Your Referral Link:</b>\n"
        f"<code>{ref_link}</code>"
    )

    share_text = quote(f"🔥 Join {store_name} for premium digital subscriptions and services!\n\n👉 Start now:\n{ref_link}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Share Referral Link",
                    url=f"https://t.me/share/url?url={ref_link}&text={share_text}",
                    style="success",
                    icon_custom_emoji_id=Icons.CHANNEL,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Close",
                    callback_data="close_menu",
                    style="danger",
                    icon_custom_emoji_id=Icons.CLOSE,
                )
            ],
        ]
    )
    await respond(event, text, kb)


@router.message(Command("reseller"))
@router.message(F.text.in_({"💼 Apply as a Reseller", "Apply as a Reseller", "apply as a reseller", "reseller", "রিসেলার"}))
@router.callback_query(F.data == "open_reseller")
async def show_reseller_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    handle = (await services.settings.get("support_username")).lstrip("@")
    store_name = (await services.settings.get("store_name")) or "Premium Haven"
    text = (
        f"{ICON_RESELLER} <b>Reseller Program</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌟 <b>Wholesale Rates:</b> Bulk discounts on all products\n"
        f"⚡ <b>Priority Stock:</b> Instant reservation & rapid delivery\n"
        f"💬 <b>VIP Support:</b> Direct 24/7 management access\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Tap below to apply with our management team."
    )

    rows = []
    if handle:
        msg = quote(f"Hello, I would like to apply as a Reseller at {store_name}.")
        rows.append([
            InlineKeyboardButton(
                text="Contact Management",
                url=f"https://t.me/{handle}?text={msg}",
                style="success",
                icon_custom_emoji_id=Icons.RESELLER,
            )
        ])
    rows.append([InlineKeyboardButton(text="Back", callback_data="back_to_main", style="danger", icon_custom_emoji_id=Icons.BACK)])
    await respond(event, text, InlineKeyboardMarkup(inline_keyboard=rows))


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

    back = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data="open_orders", style="primary", icon_custom_emoji_id=Icons.BACK)]])
    if order["status"] == "completed" and order.get("fulfillment") == "waiting":
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_TIMER} <b>Order #{order['id']}: {escape(order['product_title'])}</b>\n\n"
                "Paid. Your item is being prepared and will be delivered here shortly.",
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
        f"{ICON_ORDERS} <b>Order #{order['id']} Details</b>\n\n"
        f"{ICON_VIP} <b>Product:</b> {escape(order['product_title'])}\n"
        f"{ICON_MONEY} <b>Price Paid:</b> <code>{price(symbol, order['price'])}</code>\n"
        f"{ICON_TIMER} <b>Date:</b> {date}\n"
        f"{ICON_CHECK} <b>Status:</b> <code>{order['status'].upper()}</code>\n\n"
        f"{ICON_KEY} <b>Delivered Credentials:</b>\n"
        f"<code>{escape(order['delivered_item'])}</code>\n\n"
        "<i>(Tap the button below or tap the code to copy)</i>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Copy Credentials", copy_text=CopyTextButton(text=order["delivered_item"]), style="success", icon_custom_emoji_id=Icons.KEY)],
            [InlineKeyboardButton(text="Back", callback_data="open_orders", style="primary", icon_custom_emoji_id=Icons.BACK)],
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
            [InlineKeyboardButton(text="Deposit", callback_data="open_deposit_from_history", style="success", icon_custom_emoji_id=Icons.DEPOSIT)],
            [InlineKeyboardButton(text="◀ Back", callback_data="open_account", style="danger")],
        ]
    )
    await respond(event, text, keyboard)



