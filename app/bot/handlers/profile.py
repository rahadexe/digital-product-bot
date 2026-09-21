from __future__ import annotations

import math
from contextlib import suppress
from datetime import datetime
from html import escape
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

from app.bot.formatting import callback_int, format_dual_price, price, respond
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BALANCE,
    ICON_CART,
    ICON_CHECK,
    ICON_COIN,
    ICON_CROSS,
    ICON_DEPOSIT,
    ICON_GLOBE,
    ICON_ID,
    ICON_KEY,
    ICON_LIGHTNING,
    ICON_LOCK,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_REFER,
    ICON_RESELLER,
    ICON_ROCKET,
    ICON_SHIELD,
    ICON_SHOP,
    ICON_SPENT,
    ICON_STATS,
    ICON_SUPPORT,
    ICON_TIMER,
    ICON_VIP,
    ICON_WARNING,
    Icons,
)
from app.bot.keyboards import get_account_keyboard
from app.services import Services

router = Router(name="profile_router")

ORDERS_PAGE_SIZE = 5
INLINE_CREDENTIAL_LIMIT = 500


def reseller_api_links(config) -> tuple[str, list[list[InlineKeyboardButton]]]:
    """The endpoint to show and the docs button row.

    Telegram refuses a button pointing at a private address and drops the whole message with it,
    so a store without a public https address gets the text without the link.
    """
    base = config.console_url
    if not base:
        return "<i>Available once the store has a public address. Contact support.</i>", []
    return (
        f"<code>{base}/api/v1/reseller</code>",
        [[InlineKeyboardButton(
            text="View API Docs",
            url=f"{base}/api/v1/reseller/docs",
            style="primary",
            icon_custom_emoji_id=Icons.NOTE,
        )]],
    )




@router.message(Command("me"))
@router.message(Command("profile"))
@router.message(Command("balance"))
@router.message(Command("account"))
@router.message(F.text.in_({
    "My Profile",
    "my profile",
    "👤 My Profile",
    "Profile",
    "profile",
    "👤 Profile",
    "Account",
    "account",
    "👤 Account",
    "💼 Account",
    "Balance",
    "balance",
    "💰 Balance",
    "💰 My Balance",
    "My Balance",
    "my balance",
    "আমার প্রোফাইল",
    "প্রোফাইল",
    "ব্যালেন্স",
}))
@router.message(F.text.casefold() == "my profile")
@router.message(F.text.casefold() == "profile")
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
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    user_name = escape(tg_user.full_name or tg_user.first_name or "Customer")

    rank_val = (user.get("rank") or "Standard").strip()
    if rank_val.lower() in {"reseller", "reseller partner"}:
        account_type = "Reseller"
    else:
        account_type = "Normal"

    text = (
        f"{ICON_ACCOUNT} <b>My Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{ICON_ACCOUNT} <b>Name:</b> {user_name}\n"
        f"{ICON_ID} <b>User ID:</b> <code>{tg_user.id}</code>\n"
        f"{ICON_RESELLER} <b>Account Type:</b> <b>{account_type}</b>\n\n"
        f"{ICON_BALANCE} <b>Current Balance:</b> <code>{price(symbol, user.get('balance', 0.0), usd_rate=usd_rate, show_usd=show_usd)}</code>\n"
        f"{ICON_ORDERS} <b>Total Orders:</b> {stats.get('order_count', 0)}\n"
        f"{ICON_SPENT} <b>Total Spent:</b> <code>{price(symbol, stats.get('total_spent', 0.0), usd_rate=usd_rate, show_usd=show_usd)}</code>"
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

    symbol = await services.settings.get("currency_symbol")
    reward_amount = await services.settings.number("referral_reward_amount")
    reward_enabled = await services.settings.flag("referral_enabled")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")

    reward_str = format_dual_price(reward_amount, symbol, usd_rate=usd_rate, show_usd=show_usd)

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

    total_earned_str = format_dual_price(total_earned, symbol, usd_rate=usd_rate, show_usd=show_usd)

    bot_user = await services.notifier.bot_username()
    ref_link = f"https://t.me/{bot_user}?start=ref_{tg_user.id}"
    store_name = (await services.settings.get("store_name")) or "Premium Haven"

    reward_display = reward_str if reward_enabled and reward_amount > 0 else f"0 {symbol}"
    earned_display = total_earned_str

    tagline = (
        f"{ICON_ROCKET} <i>Earn {reward_display} per referral!</i>"
        if reward_enabled and reward_amount > 0
        else f"{ICON_ROCKET} <i>Invite friends to join!</i>"
    )

    text = (
        f"{ICON_REFER} <b>Refer & Earn</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
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


@router.message(Command("api"))
@router.message(Command("reseller"))
@router.message(F.text.in_({
    "💼 Apply as a Reseller",
    "Apply as a Reseller",
    "apply as a reseller",
    "Reseller Panel",
    "💼 Reseller Panel",
    "reseller panel",
    "reseller",
    "রিসেলার",
    "রিসেলার প্যানেল",
    "/api",
    "api",
    "API",
}))
@router.callback_query(F.data == "open_reseller")
async def show_reseller_info(event: Message | CallbackQuery, state: FSMContext | None, services: Services):
    if state:
        await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user = await services.users.get(tg_user.id)
    is_reseller = (user.get("rank") or "").strip().lower() == "reseller" if user else False

    endpoint_text, docs_rows = reseller_api_links(services.config)

    if is_reseller:
        key = await services.reseller.get_latest_key(tg_user.id)
        stats = await services.reseller.get_reseller_stats(tg_user.id)
        symbol = await services.settings.get("currency_symbol")
        usd_rate = await services.settings.number("usd_rate")
        show_usd = await services.settings.flag("show_usd_price")

        balance_str = price(symbol, user.get("balance", 0.0), usd_rate=usd_rate, show_usd=show_usd)
        recent_spend_str = price(symbol, stats["total_spent"], usd_rate=usd_rate, show_usd=show_usd)

        if key and key.get("is_active"):
            status_line = f"{ICON_CHECK} <b>Status:</b> Connected"
            key_display = f"<code>{key['key_prefix']}••••••••</code>"
            is_connected = True
        elif key:
            status_line = f"{ICON_CROSS} <b>Status:</b> Disabled"
            key_display = f"<code>{key['key_prefix']}••••••••</code>"
            is_connected = False
        else:
            status_line = f"{ICON_WARNING} <b>Status:</b> Not Generated"
            key_display = "<i>None</i>"
            is_connected = False

        text = (
            f"{ICON_RESELLER} <b>Reseller Product API</b>\n\n"
            f"Connect your own bot, website, or reseller panel to this shop. "
            f"Orders are delivered from live stock and paid from your wallet balance.\n\n"
            f"{status_line}\n"
            f"{ICON_BALANCE} <b>API Balance:</b> <code>{balance_str}</code>\n"
            f"{ICON_ORDERS} <b>Total API Orders:</b> <code>{stats['total_orders']}</code>\n"
            f"{ICON_SPENT} <b>Recent Spend:</b> <code>{recent_spend_str}</code>\n"
            f"{ICON_KEY} <b>Current Key:</b> {key_display}\n\n"
            f"<b>Available actions</b>\n"
            f"{ICON_SHOP} <b>Product list:</b> <code>GET /api/v1/reseller/products</code>\n"
            f"{ICON_ACCOUNT} <b>Balance check:</b> <code>GET /api/v1/reseller/me</code>\n"
            f"{ICON_CART} <b>Place order:</b> <code>POST /api/v1/reseller/orders</code>\n\n"
            f"<b>Endpoint URL</b>\n"
            f"{endpoint_text}"
        )

        rows = []
        if key:
            rows.append([
                InlineKeyboardButton(
                    text="Regenerate Key",
                    callback_data="reseller_regen_prompt",
                    style="primary",
                    icon_custom_emoji_id=Icons.REFRESH,
                )
            ])
            if is_connected:
                rows.append([
                    InlineKeyboardButton(
                        text="Disable API",
                        callback_data="reseller_toggle_active",
                        style="danger",
                        icon_custom_emoji_id=Icons.CROSS,
                    )
                ])
            else:
                rows.append([
                    InlineKeyboardButton(
                        text="Enable API",
                        callback_data="reseller_toggle_active",
                        style="success",
                        icon_custom_emoji_id=Icons.CHECK,
                    )
                ])
        else:
            rows.append([
                InlineKeyboardButton(
                    text="Generate Key",
                    callback_data="reseller_generate_key",
                    style="success",
                    icon_custom_emoji_id=Icons.KEY,
                )
            ])

        rows.extend(docs_rows)
        rows.append([
            InlineKeyboardButton(
                text="Refresh",
                callback_data="open_reseller",
                style="primary",
                icon_custom_emoji_id=Icons.REFRESH,
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="Back to Settings",
                callback_data="open_account",
                style="primary",
                icon_custom_emoji_id=Icons.ACCOUNT,
            )
        ])
        await respond(event, text, InlineKeyboardMarkup(inline_keyboard=rows))
        return

    # Non-reseller flow (Application form)
    handle = (await services.settings.get("support_username")).lstrip("@")
    store_name = (await services.settings.get("store_name")) or "Premium Haven"

    format_copy_text = (
        "Name: \n"
        "Telegram Username: \n"
        "Mobile Number: \n"
        "Channel Link: "
    )

    text = (
        f"{ICON_RESELLER} <b>Reseller Program</b>\n\n"
        f"🇬🇧 If you want to become a reseller in our bot, fill out the details below and message our <b>Contact Management</b>.\n\n"
        f"🇧🇩 আপনি যদি আমাদের বটে রিসেলার হতে চান, তাহলে নিচের তথ্যগুলো পূরণ করে আমাদের <b>Contact Management</b> এ মেসেজ পাঠান:\n\n"
        f"{ICON_NOTE} <b>Application Format:</b>\n"
        f"<code>{format_copy_text}</code>\n\n"
        f"{ICON_VIP} <b>Reseller Benefits:</b>\n"
        f"{ICON_COIN} Bulk discounts & wholesale reseller rates\n"
        f"{ICON_KEY} REST API Key to integrate your bot or website\n"
        f"{ICON_LIGHTNING} Rapid delivery & instant automatic credentials\n"
        f"{ICON_SUPPORT} 24/7 direct management access"
    )

    rows = [
        [
            InlineKeyboardButton(
                text="Copy Format",
                copy_text=CopyTextButton(text=format_copy_text),
                style="primary",
                icon_custom_emoji_id=Icons.NOTE,
            )
        ]
    ]
    if handle:
        prefill = (
            f"Hello, I would like to apply as a Reseller at {store_name}.\n\n"
            f"{format_copy_text}"
        )
        rows.append([
            InlineKeyboardButton(
                text="Contact Management",
                url=f"https://t.me/{handle}?text={quote(prefill)}",
                style="success",
                icon_custom_emoji_id=Icons.RESELLER,
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="Close",
            callback_data="close_menu",
            style="danger",
            icon_custom_emoji_id=Icons.CLOSE,
        )
    ])
    await respond(event, text, InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "reseller_toggle_active")
async def reseller_toggle_active_handler(event: CallbackQuery, services: Services):
    tg_user = event.from_user
    if not tg_user:
        return
    user = await services.users.get(tg_user.id)
    if not user or (user.get("rank") or "").strip().lower() != "reseller":
        await event.answer("Access denied.", show_alert=True)
        return

    key = await services.reseller.get_latest_key(tg_user.id)
    if not key:
        await event.answer("No API key found. Please generate one first.", show_alert=True)
        return

    new_active = not bool(key.get("is_active"))
    await services.reseller.set_key_status(tg_user.id, new_active)
    alert_text = "API Key enabled successfully!" if new_active else "API Key disabled."
    with suppress(TelegramBadRequest):
        await event.answer(alert_text)
    await show_reseller_info(event, None, services)


@router.callback_query(F.data == "reseller_generate_key")
async def reseller_generate_key_handler(event: CallbackQuery, services: Services):
    tg_user = event.from_user
    if not tg_user:
        return
    user = await services.users.get(tg_user.id)
    if not user or (user.get("rank") or "").strip().lower() != "reseller":
        await event.answer("Access denied. You must be an authorized Reseller.", show_alert=True)
        return

    raw_key, _ = await services.reseller.generate_key(tg_user.id)
    endpoint_text, docs_rows = reseller_api_links(services.config)

    text = (
        f"{ICON_CHECK} <b>Reseller API Key Generated!</b>\n\n"
        f"{ICON_KEY} <b>Your Secret API Key:</b>\n"
        f"<code>{raw_key}</code>\n\n"
        f"{ICON_WARNING} <b>Important Security Notice:</b>\n"
        f"• এই এপিআই কি-টি সম্পূর্ণ গোপন রাখুন। এর মাধ্যমে আপনার ওয়ালেট ব্যালেন্স ব্যবহার করে কেনাকাটা করা সম্ভব।\n"
        f"• এটি শুধুমাত্র একবারই সম্পূর্ণ প্রদর্শিত হবে। কপি করে নিরাপদ স্থানে সংরক্ষণ করুন।\n\n"
        f"{ICON_GLOBE} <b>API Base URL:</b>\n{endpoint_text}"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Copy API Key",
                    copy_text=CopyTextButton(text=raw_key),
                    style="primary",
                    icon_custom_emoji_id=Icons.NOTE,
                )
            ],
            *docs_rows,
            [
                InlineKeyboardButton(
                    text="Back to Portal",
                    callback_data="open_reseller",
                    style="danger",
                    icon_custom_emoji_id=Icons.BACK,
                )
            ],
        ]
    )
    if event.message:
        await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_reveal_key")
async def reseller_reveal_key_handler(event: CallbackQuery, services: Services):
    tg_user = event.from_user
    if not tg_user:
        return
    active_key = await services.reseller.get_active_key(tg_user.id)
    if not active_key:
        await event.answer("No active key found. Please generate one.", show_alert=True)
        return

    _, docs_rows = reseller_api_links(services.config)

    text = (
        f"{ICON_KEY} <b>Reseller API Key Info</b>\n\n"
        f"{ICON_LOCK} <b>Active Key Prefix:</b> <code>{active_key['key_prefix']}</code>\n"
        f"{ICON_TIMER} <b>Created At:</b> {active_key['created_at'].strftime('%Y-%m-%d %H:%M') if active_key.get('created_at') else 'N/A'}\n"
        f"{ICON_STATS} <b>Last Used:</b> {active_key['last_used_at'].strftime('%Y-%m-%d %H:%M') if active_key.get('last_used_at') else 'Never'}\n\n"
        f"{ICON_SHIELD} <i>সর্বোচ্চ নিরাপত্তার জন্য সম্পূর্ণ সিক্রেট কি ডাটাবেজে এনক্রিপ্ট/হ্যাশ আকারে সংরক্ষিত থাকে। আপনি যদি আপনার পূর্বের কি হারিয়ে ফেলেন, তবে নিচে থেকে নতুন কি জেনারেট (Regenerate) করতে পারবেন।</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Regenerate Key",
                    callback_data="reseller_regen_prompt",
                    style="danger",
                    icon_custom_emoji_id=Icons.REFRESH,
                )
            ],
            *docs_rows,
            [
                InlineKeyboardButton(
                    text="Back to Portal",
                    callback_data="open_reseller",
                    style="primary",
                    icon_custom_emoji_id=Icons.BACK,
                )
            ],
        ]
    )
    if event.message:
        await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_regen_prompt")
async def reseller_regen_prompt_handler(event: CallbackQuery):
    text = (
        f"{ICON_WARNING} <b>Regenerate Reseller API Key?</b>\n\n"
        f"{ICON_WARNING} <b>সতর্কতা:</b>\n"
        f"নতুন এপিআই কি তৈরি করলে আপনার আগের কি-টি সাথে সাথে নিষ্ক্রিয় (Deactivate) হয়ে যাবে।\n\n"
        f"আপনার যেসকল বট বা ওয়েবসাইটে আগের কি ইন্টিগ্রেট করা আছে, সেগুলোতে নতুন কি আপডেট না করা পর্যন্ত অর্ডার পাঠানো বন্ধ থাকবে।\n\n"
        f"আপনি কি নিশ্চিত যে নতুন কি তৈরি করতে চান?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Yes, Regenerate Key",
                    callback_data="reseller_regen_confirm",
                    style="danger",
                    icon_custom_emoji_id=Icons.CHECK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data="open_reseller",
                    style="primary",
                    icon_custom_emoji_id=Icons.CROSS,
                )
            ],
        ]
    )
    if event.message:
        await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_regen_confirm")
async def reseller_regen_confirm_handler(event: CallbackQuery, services: Services):
    tg_user = event.from_user
    if not tg_user:
        return
    user = await services.users.get(tg_user.id)
    if not user or (user.get("rank") or "").strip().lower() != "reseller":
        await event.answer("Access denied.", show_alert=True)
        return

    raw_key, _ = await services.reseller.generate_key(tg_user.id)
    _, docs_rows = reseller_api_links(services.config)

    text = (
        f"{ICON_CHECK} <b>New API Key Generated Successfully!</b>\n\n"
        f"{ICON_KEY} <b>Your New Secret API Key:</b>\n"
        f"<code>{raw_key}</code>\n\n"
        f"{ICON_WARNING} আপনার আগের এপিআই কি নিষ্ক্রিয় করা হয়েছে। আপনার বট বা ওয়েবসাইটে এই নতুন কি-টি কনফিগার করুন।"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Copy New Key",
                    copy_text=CopyTextButton(text=raw_key),
                    style="primary",
                    icon_custom_emoji_id=Icons.NOTE,
                )
            ],
            *docs_rows,
            [
                InlineKeyboardButton(
                    text="Back to Portal",
                    callback_data="open_reseller",
                    style="danger",
                    icon_custom_emoji_id=Icons.BACK,
                )
            ],
        ]
    )
    if event.message:
        await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_quick_guide")
async def reseller_quick_guide_handler(event: CallbackQuery, services: Services):
    _, docs_rows = reseller_api_links(services.config)

    text = (
        f"{ICON_NOTE} <b>Reseller API Quick Integration Guide</b>\n\n"
        f"<b>1. Header Authentication:</b>\n"
        f"প্রতিটি রিকোয়েস্টের হেডারে আপনার API Key পাঠান:\n"
        f"<code>X-API-Key: rk_live_your_key</code>\n\n"
        f"<b>2. Endpoints:</b>\n"
        f"• <code>GET /api/v1/reseller/me</code>\n  ব্যালেন্স ও প্রোফাইল চেক\n"
        f"• <code>GET /api/v1/reseller/products</code>\n  প্রোডাক্ট লিস্ট ও রিসেলার রেট\n"
        f"• <code>POST /api/v1/reseller/orders</code>\n  ইনস্ট্যান্ট অর্ডার প্লেস (JSON: <code>{{\"product_id\": 1, \"quantity\": 1}}</code>)\n\n"
        f"<b>3. Response:</b>\n"
        f"অর্ডার সফল হলে ক্রেডেনশিয়াল বা লাইসেন্স কি রেসপন্সের <code>credentials</code> ফিল্ডে চলে আসবে!\n\n"
        f"🌐 <i>বিস্তারিত কোড ও প্যারামিটার দেখতে নিচের লিংকে সম্পূর্ণ ওয়েব ডকুমেন্টেশন ওপেন করুন।</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            *docs_rows,
            [
                InlineKeyboardButton(
                    text="Back to Portal",
                    callback_data="open_reseller",
                    style="danger",
                    icon_custom_emoji_id=Icons.BACK,
                )
            ],
        ]
    )
    if event.message:
        await event.message.edit_text(text, reply_markup=kb)


@router.message(Command("orders"))
@router.message(Command("order"))
@router.message(Command("history"))
@router.message(F.text.in_({
    "Orders",
    "orders",
    "📦 Orders",
    "My Orders",
    "my orders",
    "📦 My Orders",
    "Order History",
    "order history",
    "📦 Order History",
    "আমার অর্ডার",
    "অর্ডার",
}))
@router.message(F.text.casefold() == "orders")
@router.message(F.text.casefold() == "my orders")
@router.message(F.text.casefold() == "order history")
@router.callback_query(F.data == "open_orders")
@router.callback_query(F.data.startswith("orders_page_"))
async def show_order_history(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    page = 1
    if isinstance(event, CallbackQuery) and event.data and event.data.startswith("orders_page_"):
        suffix = event.data[len("orders_page_") :]
        if suffix.isdigit():
            page = max(1, int(suffix))

    orders, total = await services.purchases.customer_orders(tg_user.id, limit=ORDERS_PAGE_SIZE, offset=(page - 1) * ORDERS_PAGE_SIZE)
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")

    if not orders:
        text = (
            f"{ICON_ORDERS} <b>Order History</b>\n\n"
            f"<i>You have no orders yet.</i>"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Back", callback_data="open_account", style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
                ],
            ]
        )
    else:
        total_pages = max(1, math.ceil(total / ORDERS_PAGE_SIZE))
        page = min(page, total_pages)
        page_suffix = f" (Page {page}/{total_pages})" if total_pages > 1 else ""
        text = f"{ICON_ORDERS} <b>Order History{page_suffix}</b>"
        buttons = []
        for order in orders:
            price_val = order["price"]
            price_str = format_dual_price(price_val, symbol, usd_rate=usd_rate, show_usd=show_usd)
            max_title_len = max(10, 60 - len(str(order['id'])) - len(price_str) - 6)
            title_short = order['product_title'][:max_title_len].strip()
            label = f"#{order['id']} · {title_short} · {price_str}"
            status_icon = Icons.CHECK if order["status"] == "completed" and order.get("fulfillment") != "waiting" else (Icons.TIMER if order.get("fulfillment") == "waiting" else Icons.CROSS)
            buttons.append([InlineKeyboardButton(text=label[:64], callback_data=f"view_order_{order['id']}", style="primary", icon_custom_emoji_id=status_icon)])

        nav_row = []
        if total_pages > 1:
            if page == 1:
                nav_row = [
                    InlineKeyboardButton(text="Refresh", callback_data=f"orders_page_{page}", style="success", icon_custom_emoji_id=Icons.REFRESH),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text="Next", callback_data=f"orders_page_{page + 1}", style="primary", icon_custom_emoji_id=Icons.NEXT),
                ]
            elif page == total_pages:
                nav_row = [
                    InlineKeyboardButton(text="Prev", callback_data=f"orders_page_{page - 1}", style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text="Refresh", callback_data=f"orders_page_{page}", style="success", icon_custom_emoji_id=Icons.REFRESH),
                ]
            else:
                nav_row = [
                    InlineKeyboardButton(text="Prev", callback_data=f"orders_page_{page - 1}", style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text="Next", callback_data=f"orders_page_{page + 1}", style="primary", icon_custom_emoji_id=Icons.NEXT),
                ]
            buttons.append(nav_row)

        action_row = [
            InlineKeyboardButton(text="Back", callback_data="open_account", style="primary", icon_custom_emoji_id=Icons.BACK),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
        ]
        buttons.append(action_row)
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
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    text = (
        f"{ICON_ORDERS} <b>Order #{order['id']} Details</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{ICON_VIP} <b>Product:</b> {escape(order['product_title'])}\n"
        f"{ICON_MONEY} <b>Price Paid:</b> <code>{price(symbol, order['price'], usd_rate=usd_rate, show_usd=show_usd)}</code>\n"
        f"{ICON_TIMER} <b>Date:</b> {date}\n"
        f"{ICON_CHECK} <b>Status:</b> <code>{order['status'].upper()}</code>\n\n"
        f"{ICON_KEY} <b>Delivered Credentials:</b>\n"
        f"<code>{escape(order['delivered_item'])}</code>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Copy Credentials", copy_text=CopyTextButton(text=order["delivered_item"]), style="success", icon_custom_emoji_id=Icons.KEY)],
            [InlineKeyboardButton(text="Back", callback_data="open_orders", style="danger", icon_custom_emoji_id=Icons.BACK)],
        ]
    )
    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=keyboard)


DEPOSITS_PAGE_SIZE = 5

DEPOSIT_STATUS_BADGES = {
    "approved": f"{ICON_CHECK} <b>Approved</b>",
    "pending": f"{ICON_TIMER} <b>Pending Review</b>",
    "rejected": f"{ICON_CROSS} <b>Rejected</b>",
}


@router.callback_query(F.data == "open_deposits")
@router.callback_query(F.data.startswith("dep_page_"))
async def show_deposit_history(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    page = 1
    if isinstance(event, CallbackQuery) and event.data and event.data.startswith("dep_page_"):
        suffix = event.data[len("dep_page_") :]
        if suffix.isdigit():
            page = max(1, int(suffix))

    total_count = await services.deposits.count_for_user(tg_user.id)
    total_pages = max(1, (total_count + DEPOSITS_PAGE_SIZE - 1) // DEPOSITS_PAGE_SIZE) if total_count > 0 else 1
    page = min(page, total_pages)
    offset = (page - 1) * DEPOSITS_PAGE_SIZE

    deposits = await services.deposits.history(tg_user.id, limit=DEPOSITS_PAGE_SIZE, offset=offset)
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")

    if not deposits:
        text = (
            f"{ICON_STATS} <b>Balance History</b>\n\n"
            f"<i>You have no balance transaction records yet.</i>"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Add Balance", callback_data="open_deposit_from_history", style="success", icon_custom_emoji_id=Icons.DEPOSIT),
                    InlineKeyboardButton(text="Back", callback_data="open_account", style="danger", icon_custom_emoji_id=Icons.BACK),
                ],
            ]
        )
    else:
        page_suffix = f" (Page {page}/{total_pages})" if total_pages > 1 else ""
        text = f"{ICON_STATS} <b>Balance History{page_suffix}</b>\n\n"
        items = []
        for deposit in deposits:
            created = deposit["created_at"]
            date = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else str(created)[:16]
            status_badge = DEPOSIT_STATUS_BADGES.get(deposit["status"], f"<b>{escape(str(deposit['status']).title())}</b>")
            entry = (
                f"{ICON_DEPOSIT} <b>#{deposit['id']}</b> · <code>{price(symbol, deposit['amount'], usd_rate=usd_rate, show_usd=show_usd)}</code> · <b>{escape(deposit['method_name'])}</b>\n"
                f"↳ {status_badge} · <code>{date}</code>"
            )
            if deposit["status"] == "rejected" and deposit.get("admin_note"):
                entry += f"\n   <i>Note: {escape(deposit['admin_note'])}</i>"
            items.append(entry)
        text += "\n\n".join(items)

        buttons = []
        if total_pages > 1:
            nav_row = []
            if page == 1:
                nav_row = [
                    InlineKeyboardButton(text="Refresh", callback_data=f"dep_page_{page}", style="success", icon_custom_emoji_id=Icons.REFRESH),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text="Next", callback_data=f"dep_page_{page + 1}", style="primary", icon_custom_emoji_id=Icons.NEXT),
                ]
            elif page == total_pages:
                nav_row = [
                    InlineKeyboardButton(text="Prev", callback_data=f"dep_page_{page - 1}", style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text="Refresh", callback_data=f"dep_page_{page}", style="success", icon_custom_emoji_id=Icons.REFRESH),
                ]
            else:
                nav_row = [
                    InlineKeyboardButton(text="Prev", callback_data=f"dep_page_{page - 1}", style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text="Next", callback_data=f"dep_page_{page + 1}", style="primary", icon_custom_emoji_id=Icons.NEXT),
                ]
            buttons.append(nav_row)

        buttons.append([
            InlineKeyboardButton(text="Add Balance", callback_data="open_deposit_from_history", style="success", icon_custom_emoji_id=Icons.DEPOSIT),
            InlineKeyboardButton(text="Back", callback_data="open_account", style="danger", icon_custom_emoji_id=Icons.BACK),
        ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await respond(event, text, keyboard)



