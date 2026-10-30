from __future__ import annotations

import asyncio
import inspect
import math
from contextlib import suppress
from datetime import datetime
from html import escape
from typing import Any
from urllib.parse import quote

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.formatting import format_dual_price, price, resolve_user_currency, respond
from app.core.identifiers import format_deposit_id, format_order_id
from app.bot.icons import (
    ICON_CHECK,
    ICON_CROSS,
    ICON_STATS,
    ICON_TIMER,
)
from app.bot.keyboards import product_display_labels
from app.core.i18n import t
from app.services import Services

router = Router(name="profile_router")

ORDERS_PAGE_SIZE = 5
INLINE_CREDENTIAL_LIMIT = 500


def reseller_api_links(config) -> tuple[str, list[list[InlineKeyboardButton]]]:
    """The endpoint to show and the docs button row.

    Telegram refuses a button pointing at a private address and drops the whole message with it,
    so if no public https console_url is configured, we provide the in-bot Quick Guide button.
    """
    base = config.console_url
    if base and base.startswith("https://"):
        return (
            f"<code>{base}/api/v1/reseller</code>",
            [[InlineKeyboardButton(
                text="API Docs",
                url=f"{base}/api/v1/reseller/docs",
            )]],
        )
    return (
        "<code>https://api.yourdomain.com/api/v1/reseller</code>",
        [[InlineKeyboardButton(
            text="API Docs",
            callback_data="reseller_quick_guide",
        )]],
    )




_EXTRA_ALERT_PREFS: dict[int, dict[str, bool]] = {}


@router.callback_query(F.data == "open_account")
async def show_account_hub(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user, lang, usd_rate, orders_res, user_currency = await asyncio.gather(
        services.users.get(tg_user.id),
        services.users.get_language(tg_user.id),
        services.settings.number("usd_rate"),
        services.purchases.customer_orders(tg_user.id, limit=1, offset=0),
        resolve_user_currency(services, tg_user.id),
    )
    total_orders = int(orders_res[1]) if isinstance(orders_res, tuple) and len(orders_res) == 2 else 0
    user_balance = float(user.get("balance", 0.0)) if isinstance(user, dict) else 0.0
    is_reseller = (user.get("rank") or "").strip().lower() in {"reseller", "reseller partner"} if isinstance(user, dict) else False
    balance_str = format_dual_price(user_balance, usd_rate=usd_rate, lang=lang, currency=user_currency, show_usd=False)

    curr_label = "৳ BDT" if user_currency == "BDT" else "$ USD"
    curr_btn_label = f"💱 Currency: ৳ BDT" if user_currency == "BDT" else f"💱 Currency: $ USD"

    ref_earned = 0.0
    if hasattr(services.users, "referral_summary"):
        try:
            summary = await services.users.referral_summary(tg_user.id)
            if isinstance(summary, dict):
                ref_earned = float(summary.get("earned") or 0.0)
        except Exception:
            ref_earned = 0.0
    ref_earned_str = format_dual_price(ref_earned, usd_rate=usd_rate, lang=lang, currency=user_currency, show_usd=False)

    user_name = escape(tg_user.full_name or tg_user.first_name or "Account")

    bot_user = ""
    notifier = getattr(services, "notifier", None)
    if notifier and hasattr(notifier, "bot_username"):
        try:
            bu = notifier.bot_username()
            bot_user = (await bu) if inspect.isawaitable(bu) else str(bu)
        except Exception:
            bot_user = ""
    if not bot_user:
        bot_user = "bot"
    ref_link = f"https://t.me/{bot_user}?start={tg_user.id}"

    raw_username = getattr(tg_user, "username", None)
    user_handle = f"@{escape(raw_username.lstrip('@'))}" if raw_username else None
    lines = [
        f"User ID: <code>{tg_user.id}</code>",
    ]
    if user_handle:
        lines.append(f"Username: {user_handle}")
    elif user_name:
        lines.append(f"Name: <b>{user_name}</b>")
    if is_reseller:
        lines.append("Rank: <code>Reseller Partner</code>")
    else:
        rank_str = (user.get("rank") or "Standard").title() if isinstance(user, dict) else "Standard"
        lines.append(f"Rank: <code>{escape(rank_str)}</code>")
    lines.append(f"Current Balance: <code>{balance_str}</code>")
    lines.append(f"Total Orders: <code>{total_orders}</code>")
    if ref_earned > 0:
        lines.append(f"Referral Earned: <code>{ref_earned_str}</code>")
    lines.append(f"Currency: <code>{curr_label}</code>")

    text = (
        "👤 <b>Account Overview</b>\n\n"
        + "\n".join(lines)
        + f"\n\n🔗 <b>Your Referral Link:</b>\n<code>{ref_link}</code>"
    )
    orders_label = f"📦 My Orders ({total_orders})" if total_orders > 0 else "📦 My Orders"
    refer_label = "🎁 Refer"
    alerts_label = "🔔 Alerts"
    api_label = "🔑 API"
    reseller_label = "💎 Reseller"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=orders_label, callback_data="acct_orders")],
            [
                InlineKeyboardButton(text=refer_label, callback_data="acct_referral"),
                InlineKeyboardButton(text=alerts_label, callback_data="open_alerts"),
            ],
            [
                InlineKeyboardButton(text=api_label, callback_data="open_api_hub"),
                InlineKeyboardButton(text=reseller_label, callback_data="open_reseller_hub"),
            ],
            [
                InlineKeyboardButton(text=curr_btn_label, callback_data="acct_toggle_currency"),
            ],
        ]
    )
    await respond(event, text, kb)


@router.callback_query(F.data == "acct_toggle_currency")
async def toggle_user_currency(query: CallbackQuery, state: FSMContext, services: Services):
    tg_user = query.from_user
    if not tg_user:
        return
    new_curr = await services.users.toggle_currency(tg_user.id)
    with suppress(TelegramBadRequest):
        toast_msg = "Currency switched to ৳ BDT" if new_curr == "BDT" else "Currency switched to $ USD"
        await query.answer(toast_msg)
    await show_account_hub(query, state, services)


@router.callback_query(F.data == "open_alerts")
async def show_alerts_hub(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    get_prefs = getattr(services.users, "get_notification_preferences", None)
    prefs = await get_prefs(tg_user.id) if callable(get_prefs) else {"notify_news": True}
    lang = await services.users.get_language(tg_user.id)

    promos_on = bool(prefs.get("notify_news", True)) if isinstance(prefs, dict) else True
    extra = _EXTRA_ALERT_PREFS.setdefault(tg_user.id, {"restock": True, "price_drop": True})
    restock_on = bool(extra.get("restock", True))
    price_drop_on = bool(extra.get("price_drop", True))

    if lang == "bn":
        promo_status = "চালু ✅" if promos_on else "বন্ধ 🔕"
        restock_status = "চালু ✅" if restock_on else "বন্ধ 🔕"
        price_status = "চালু ✅" if price_drop_on else "বন্ধ 🔕"
        text = (
            "<b>🔔 নোটিফিকেশন</b>\n\n"
            "<blockquote>অর্ডার ও পেমেন্ট: <b>সর্বদা চালু 🔒</b>\n"
            f"প্রমোশন ও অফার: <b>{promo_status}</b>\n"
            f"স্টক অ্যালার্ট: <b>{restock_status}</b>\n"
            f"প্রাইস ড্রপ: <b>{price_status}</b></blockquote>"
        )
        promo_btn = f"🎁 প্রমোশন ও অফার: {'✅ চালু' if promos_on else '🔕 বন্ধ'}"
        restock_btn = f"🔄 স্টক অ্যালার্ট: {'✅ চালু' if restock_on else '🔕 বন্ধ'}"
        price_btn = f"🏷 প্রাইস ড্রপ: {'✅ চালু' if price_drop_on else '🔕 বন্ধ'}"
        back_btn = "ব্যাক"
    else:
        promo_status = "On ✅" if promos_on else "Off 🔕"
        restock_status = "On ✅" if restock_on else "Off 🔕"
        price_status = "On ✅" if price_drop_on else "Off 🔕"
        text = (
            "<b>🔔 Notifications</b>\n\n"
            "<blockquote>Orders & Wallet: <b>Always On 🔒</b>\n"
            f"Promotions: <b>{promo_status}</b>\n"
            f"Stock Alerts: <b>{restock_status}</b>\n"
            f"Price Drops: <b>{price_status}</b></blockquote>"
        )
        promo_btn = f"🎁 Promotions: {'✅ ON' if promos_on else '🔕 OFF'}"
        restock_btn = f"🔄 Stock Alerts: {'✅ ON' if restock_on else '🔕 OFF'}"
        price_btn = f"🏷 Price Drops: {'✅ ON' if price_drop_on else '🔕 OFF'}"
        back_btn = "Back"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=promo_btn, callback_data="acct_toggle_alert_promos")],
            [InlineKeyboardButton(text=restock_btn, callback_data="acct_toggle_alert_restock")],
            [InlineKeyboardButton(text=price_btn, callback_data="acct_toggle_alert_price")],
            [InlineKeyboardButton(text=back_btn, callback_data="open_account")],
        ]
    )
    await respond(event, text, kb)


@router.callback_query(F.data.startswith("acct_toggle_alert_"))
async def toggle_account_alert_item(query: CallbackQuery, state: FSMContext, services: Services):
    tg_user = query.from_user
    if not tg_user:
        return

    kind = (query.data or "").removeprefix("acct_toggle_alert_")
    extra = _EXTRA_ALERT_PREFS.setdefault(tg_user.id, {"restock": True, "price_drop": True})

    if kind == "promos":
        prefs = await services.users.toggle_notification_preference(tg_user.id, "notify_news")
        now_on = bool(prefs.get("notify_news", True))
        label = "Promotions"
    elif kind == "restock":
        now_on = not bool(extra.get("restock", True))
        extra["restock"] = now_on
        label = "Stock Alerts"
    else:
        now_on = not bool(extra.get("price_drop", True))
        extra["price_drop"] = now_on
        label = "Price Drops"

    toast = f"{label}: On" if now_on else f"{label}: Off"
    with suppress(TelegramBadRequest):
        await query.answer(toast)
    await show_alerts_hub(query, state, services)


@router.callback_query(F.data == "open_referral")
@router.callback_query(F.data == "acct_referral")
@router.callback_query(F.data == "home_referral")
async def show_referral_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user = await services.users.get(tg_user.id)
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    curr = await resolve_user_currency(services, tg_user.id)

    symbol = await services.settings.get("currency_symbol")
    reward_amount = await services.settings.number("referral_reward_amount")
    reward_enabled = await services.settings.flag("referral_enabled")
    usd_rate = await services.settings.number("usd_rate")

    reward_str = format_dual_price(reward_amount, symbol, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)

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

    total_earned_str = format_dual_price(total_earned, symbol, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)

    bot_user = await services.notifier.bot_username()
    ref_link = f"https://t.me/{bot_user}?start={tg_user.id}"
    store_name = (await services.settings.get("store_name")) or "Premium Haven"

    reward_display = reward_str if reward_enabled and reward_amount > 0 else f"0 {symbol}"
    earned_display = total_earned_str

    if lang != "bn":
        reward_line = (
            f"Get <b>{reward_display}</b> bonus per invite!"
            if reward_enabled and reward_amount > 0
            else "Referral rewards are currently paused."
        )
        text = (
            f"{reward_line}\n\n"
            f"<blockquote>👥 Successful invites: <code>{total_invited}</code>\n"
            f"💵 Earned: <code>{earned_display}</code></blockquote>\n\n"
            "🔗 Your referral link:\n"
            f"<code>{ref_link}</code>"
        )
        copy_label = "Copy Link"
        share_label = "Share"
        share_msg = quote(f"Join {store_name}")
    else:
        reward_line = (
            f"প্রতি ইনভাইটে <b>{reward_display}</b> বোনাস!"
            if reward_enabled and reward_amount > 0
            else "রেফারেল বোনাস বর্তমানে বন্ধ আছে।"
        )
        text = (
            f"{reward_line}\n\n"
            f"<blockquote>👥 মোট ইনভাইট: <code>{total_invited}</code>\n"
            f"💵 মোট আয়: <code>{earned_display}</code></blockquote>\n\n"
            "🔗 আপনার রেফারেল লিংক:\n"
            f"<code>{ref_link}</code>"
        )
        copy_label = "লিংক কপি করুন"
        share_label = "শেয়ার"
        share_msg = quote(f"{store_name}-এ জয়েন করুন")

    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=copy_label,
                copy_text=CopyTextButton(text=ref_link),
            ),
            InlineKeyboardButton(
                text=share_label,
                url=f"https://t.me/share/url?url={quote(ref_link, safe='')}&text={share_msg}",
            ),
        ],
    ]
    if isinstance(event, CallbackQuery):
        cb_data = getattr(event, "data", "")
        if cb_data == "home_referral":
            buttons.append([
                InlineKeyboardButton(
                    text="Back" if lang != "bn" else "ব্যাক",
                    callback_data="back_to_main",
                )
            ])
        elif cb_data == "acct_referral":
            buttons.append([
                InlineKeyboardButton(
                    text="Back" if lang != "bn" else "ব্যাক",
                    callback_data="open_account",
                )
            ])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await respond(event, text, kb)



# --- Reseller Portal (Wholesale & Business Program) ---
@router.callback_query(F.data == "open_reseller_hub")
@router.callback_query(F.data == "open_reseller")
async def show_reseller_hub(event: Message | CallbackQuery, state: FSMContext | None, services: Services):
    if state:
        await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user = await services.users.get(tg_user.id)
    is_reseller = (user.get("rank") or "").strip().lower() in {"reseller", "reseller partner"} if user else False
    lang = await services.users.get_language(tg_user.id)
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    handle = ((await services.settings.get("support_username")) or "").lstrip("@")
    store_name = (await services.settings.get("store_name")) or "Premium Haven"

    rows: list[list[InlineKeyboardButton]] = []

    if is_reseller:
        stats = await services.reseller.get_reseller_stats(tg_user.id)
        balance_str = price(symbol, user.get("balance", 0.0), usd_rate=usd_rate, lang=lang)
        recent_spend_str = price(symbol, stats["total_spent"], usd_rate=usd_rate, lang=lang)

        if lang != "bn":
            text = (
                "<b>Reseller</b>\n\n"
                "<blockquote>Status: <b>Active</b>\n"
                "Pricing: <b>Wholesale Discount</b>\n"
                f"Orders: <code>{stats['total_orders']}</code> · Spent: <code>{recent_spend_str}</code>\n"
                f"Balance: <code>{balance_str}</code></blockquote>"
            )
            refresh_btn_text = "Refresh"
            back_btn_text = "Back"
        else:
            text = (
                "<b>রিসেলার</b>\n\n"
                "<blockquote>স্ট্যাটাস: <b>সক্রিয় পার্টনার</b>\n"
                "টিয়ার: <b>পাইকারি ডিসকাউন্ট</b>\n"
                f"অর্ডার: <code>{stats['total_orders']}</code> · খরচ: <code>{recent_spend_str}</code>\n"
                f"ব্যালেন্স: <code>{balance_str}</code></blockquote>"
            )
            refresh_btn_text = "রিফ্রেশ"
            back_btn_text = "ব্যাক"

        rows.append([
            InlineKeyboardButton(text=refresh_btn_text, callback_data="open_reseller_hub"),
            InlineKeyboardButton(text=back_btn_text, callback_data="open_account"),
        ])
    else:
        # Check pending applications
        async with services.db.connect() as conn:
            pending_app = await conn.fetchrow(
                "SELECT id, status FROM reseller_applications WHERE tg_user_id = $1 AND status = 'pending'",
                tg_user.id,
            )

        if pending_app:
            if lang != "bn":
                text = (
                    "<b>Reseller Application</b>\n\n"
                    "Your application is under review."
                )
                cancel_btn_text = "Cancel Application"
                contact_btn_text = "Contact Support"
                back_btn_text = "Back"
            else:
                text = (
                    "<b>রিসেলার আবেদন</b>\n\n"
                    "স্ট্যাটাস: <b>পর্যালোচনায় রয়েছে</b>\n\n"
                    "আপনার আবেদনটি জমা হয়েছে এবং বর্তমানে যাচাই করা হচ্ছে।"
                )
                cancel_btn_text = "আবেদন বাতিল করুন"
                contact_btn_text = "সাপোর্ট যোগাযোগ"
                back_btn_text = "ব্যাক"

            rows.append([InlineKeyboardButton(text=cancel_btn_text, callback_data="reseller_cancel_pending")])
            if handle:
                rows.append([InlineKeyboardButton(text=contact_btn_text, url=f"https://t.me/{handle}")])
            rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="open_account")])
        else:
            # Fetch up to 3 active products with configured reseller discounts
            async with services.db.connect() as conn:
                sample_prods = await conn.fetch(
                    """
                    SELECT title, price, reseller_price
                    FROM products
                    WHERE is_active = 1
                      AND reseller_price IS NOT NULL
                      AND reseller_price > 0
                      AND reseller_price < price
                    ORDER BY id DESC
                    LIMIT 3
                    """
                )

            comparison_lines = []
            for p in sample_prods:
                reg_str = price(symbol, p["price"], usd_rate=usd_rate, lang=lang)
                res_str = price(symbol, p["reseller_price"], usd_rate=usd_rate, lang=lang)
                comparison_lines.append(f"• {p['title']}: {reg_str} → <b>{res_str}</b>")

            comp_block = ""
            if comparison_lines:
                comp_header = "<b>Wholesale Discounts:</b>" if lang != "bn" else "<b>পাইকারি মূল্য তুলনা:</b>"
                comp_block = f"\n\n{comp_header}\n<blockquote>" + "\n".join(comparison_lines) + "</blockquote>"

            if lang != "bn":
                text = (
                    "<b>Reseller Program</b>\n\n"
                    "Apply for wholesale pricing across the catalog."
                    f"{comp_block}"
                )
                apply_btn_text = "Apply"
                contact_btn_text = "Contact Support"
                back_btn_text = "Back"
            else:
                text = (
                    "<b>রিসেলার প্রোগ্রাম</b>\n\n"
                    "সম্পূর্ণ ক্যাটালগে পাইকারি ডিসকাউন্ট রেট আনলক করুন।"
                    f"{comp_block}"
                )
                apply_btn_text = "রিসেলার আবেদন করুন"
                contact_btn_text = "সাপোর্ট যোগাযোগ"
                back_btn_text = "ব্যাক"

            rows.append([InlineKeyboardButton(text=apply_btn_text, callback_data="reseller_start_apply")])
            if handle:
                prefill = f"Hello, I would like to inquire about becoming a Reseller at {store_name}."
                rows.append([InlineKeyboardButton(text=contact_btn_text, url=f"https://t.me/{handle}?text={quote(prefill)}")])
            rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="open_account")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await respond(event, text, kb)



# --- Developer REST API Portal ---
@router.callback_query(F.data == "open_api_hub")
async def show_api_hub(event: Message | CallbackQuery, state: FSMContext | None, services: Services):
    if state:
        await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user = await services.users.get(tg_user.id)
    is_reseller = (user.get("rank") or "").strip().lower() in {"reseller", "reseller partner"} if user else False
    lang = await services.users.get_language(tg_user.id)

    endpoint_text, docs_rows = reseller_api_links(services.config)
    key = await services.reseller.get_latest_key(tg_user.id)
    stats = await services.reseller.get_reseller_stats(tg_user.id)
    usd_rate = await services.settings.number("usd_rate")
    user_balance = float(user.get("balance", 0.0)) if user else 0.0
    balance_str = format_dual_price(user_balance, usd_rate=usd_rate, lang=lang)
    recent_spend_str = format_dual_price(stats["total_spent"], usd_rate=usd_rate, lang=lang)

    if key and key.get("is_active"):
        status_line = "Connected"
        raw_prefix = (key.get("key_prefix") or "").strip()
        last4 = raw_prefix[-4:] if len(raw_prefix) >= 4 else "••••"
        key_display = f"<code>rklive••••••••{last4}</code>"
        is_connected = True
    elif key:
        status_line = "Disabled"
        raw_prefix = (key.get("key_prefix") or "").strip()
        last4 = raw_prefix[-4:] if len(raw_prefix) >= 4 else "••••"
        key_display = f"<code>rklive••••••••{last4}</code>"
        is_connected = False
    else:
        status_line = "Not Generated"
        key_display = "None"
        is_connected = False

    tier_label = ("রিসেলার" if is_reseller else "সদস্য") if lang == "bn" else ("Reseller" if is_reseller else "Member")
    if lang == "bn":
        status_line = {
            "Connected": "সংযুক্ত",
            "Disabled": "বন্ধ",
            "Not Generated": "তৈরি করা হয়নি",
        }.get(status_line, status_line)

    if lang != "bn":
        text = (
            "<b>API Access</b>\n\n"
            f"<blockquote>Status: <b>{status_line}</b>\n"
            f"API Key: {key_display}\n"
            f"Balance: <code>{balance_str}</code>\n"
            f"Orders: <code>{stats['total_orders']}</code></blockquote>\n\n"
            "Endpoint:\n"
            f"{endpoint_text}"
        )
        refresh_text = "Refresh"
        back_text = "Back"
    else:
        text = (
            "<b>এপিআই অ্যাক্সেস</b>\n\n"
            f"<blockquote>স্ট্যাটাস: <b>{status_line}</b>\n"
            f"এপিআই কি: {key_display}\n"
            f"ব্যালেন্স: <code>{balance_str}</code>\n"
            f"অর্ডার: <code>{stats['total_orders']}</code></blockquote>\n\n"
            "এন্ডপয়েন্ট:\n"
            f"{endpoint_text}"
        )
        refresh_text = "রিফ্রেশ"
        back_text = "ব্যাক"

    rows = []
    if key:
        toggle_label = (
            ("Disable API" if lang != "bn" else "এপিআই বন্ধ")
            if is_connected
            else ("Enable API" if lang != "bn" else "এপিআই চালু")
        )
        rows.append([
            InlineKeyboardButton(
                text="Regenerate Key" if lang != "bn" else "কি পুনরায় তৈরি",
                callback_data="reseller_regen_prompt",
            ),
            InlineKeyboardButton(
                text=toggle_label,
                callback_data="reseller_toggle_active",
            ),
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="Generate API Key" if lang != "bn" else "এপিআই কি তৈরি করুন",
                callback_data="reseller_generate_key",
            )
        ])

    if docs_rows and docs_rows[0]:
        docs_btn = docs_rows[0][0]
        docs_btn.text = "API Docs" if lang != "bn" else "এপিআই ডক্স"
        rows.append([docs_btn])

    rows.append([
        InlineKeyboardButton(text=back_text, callback_data="open_account"),
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await respond(event, text, kb)


@router.callback_query(F.data == "reseller_toggle_active")
async def reseller_toggle_active_handler(event: CallbackQuery, services: Services):
    tg_user = event.from_user
    if not tg_user:
        return
    user = await services.users.get(tg_user.id)
    if not user or user.get("is_banned"):
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
    await show_api_hub(event, None, services)


@router.callback_query(F.data == "reseller_generate_key")
async def reseller_generate_key_handler(event: CallbackQuery, services: Services):
    tg_user = event.from_user
    if not tg_user:
        return
    user = await services.users.get(tg_user.id)
    if not user or user.get("is_banned"):
        await event.answer("Access denied.", show_alert=True)
        return

    raw_key, _ = await services.reseller.generate_key(tg_user.id)
    endpoint_text, docs_rows = reseller_api_links(services.config)

    text = (
        "<b>API Key Generated</b>\n\n"
        "Your Secret API Key:\n"
        f"<code>{raw_key}</code>\n\n"
        "<b>Important Notice:</b>\n"
        "• Anyone with this key can make purchases using your wallet balance.\n"
        "• It will only be displayed once. Copy and store it safely.\n\n"
        f"Endpoint URL:\n{endpoint_text}"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Copy API Key",
                    copy_text=CopyTextButton(text=raw_key),
                )
            ],
            *docs_rows,
            [
                InlineKeyboardButton(
                    text="Back",
                    callback_data="open_api_hub",
                )
            ],
        ]
    )
    if event.message:
        with suppress(TelegramBadRequest):
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
    created_at_str = active_key['created_at'].strftime('%Y-%m-%d %H:%M') if active_key.get('created_at') else 'N/A'
    last_used_str = active_key['last_used_at'].strftime('%Y-%m-%d %H:%M') if active_key.get('last_used_at') else 'Never'

    text = (
        "<b>API Key Details</b>\n\n"
        f"Prefix: <code>{active_key['key_prefix']}</code>\n"
        f"Created: {created_at_str}\n"
        f"Last Used: {last_used_str}\n\n"
        "<i>Your full secret key is securely hashed. If lost, you can regenerate a new key below.</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Regenerate Key",
                    callback_data="reseller_regen_prompt",
                )
            ],
            *docs_rows,
            [
                InlineKeyboardButton(
                    text="Back",
                    callback_data="open_api_hub",
                )
            ],
        ]
    )
    if event.message:
        with suppress(TelegramBadRequest):
            await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_regen_prompt")
async def reseller_regen_prompt_handler(event: CallbackQuery):
    text = (
        "<b>Regenerate API Key</b>\n\n"
        "Generating a new API key will immediately deactivate your existing key. "
        "Any bots or systems using your current key will stop working until updated.\n\n"
        "Are you sure you want to proceed?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Yes, Regenerate Key",
                    callback_data="reseller_regen_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    callback_data="open_api_hub",
                ),
            ],
        ]
    )
    if event.message:
        with suppress(TelegramBadRequest):
            await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_regen_confirm")
async def reseller_regen_confirm_handler(event: CallbackQuery, services: Services):
    tg_user = event.from_user
    if not tg_user:
        return
    user = await services.users.get(tg_user.id)
    if not user or user.get("is_banned"):
        await event.answer("Access denied.", show_alert=True)
        return

    raw_key, _ = await services.reseller.generate_key(tg_user.id)
    _, docs_rows = reseller_api_links(services.config)

    text = (
        "<b>New API Key Generated</b>\n\n"
        "Your New Secret API Key:\n"
        f"<code>{raw_key}</code>\n\n"
        "<i>Your previous API key has been deactivated. Configure this new key in your integration.</i>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Copy New Key",
                    copy_text=CopyTextButton(text=raw_key),
                )
            ],
            *docs_rows,
            [
                InlineKeyboardButton(
                    text="Back",
                    callback_data="open_api_hub",
                )
            ],
        ]
    )
    if event.message:
        with suppress(TelegramBadRequest):
            await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_quick_guide")
async def reseller_quick_guide_handler(event: CallbackQuery, services: Services):
    base = services.config.console_url

    text = (
        "<b>Developer API Quick Guide</b>\n\n"
        "<b>Authentication Header:</b>\n"
        "<code>X-API-Key: YOUR_API_KEY</code>\n"
        "<i>(Example placeholder — pass your secret key here)</i>\n\n"
        "<b>Endpoints:</b>\n"
        "• <code>GET /api/v1/reseller/me</code> — Profile & balance\n"
        "• <code>GET /api/v1/reseller/products</code> — Catalog & stock\n"
        "• <code>POST /api/v1/reseller/orders</code> — Instant purchase\n\n"
        "<i>For full interactive documentation, OpenAPI schemas, and code samples, open Web Docs below.</i>"
    )
    rows = []
    if base and base.startswith("https://"):
        rows.append([
            InlineKeyboardButton(
                text="Open Web Docs",
                url=f"{base}/api/v1/reseller/docs",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="Open Web Docs",
                callback_data="reseller_web_docs_notice",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="Back",
            callback_data="open_api_hub",
        )
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    if event.message:
        with suppress(TelegramBadRequest):
            await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_web_docs_notice")
async def reseller_web_docs_notice_handler(event: CallbackQuery, services: Services):
    with suppress(TelegramBadRequest):
        await event.answer(
            "Web docs are hosted at /api/v1/reseller/docs on your server.",
            show_alert=True,
        )


@router.callback_query(F.data == "open_orders")
@router.callback_query(F.data == "acct_orders")
@router.callback_query(F.data.startswith("orders_page_"))
@router.callback_query(F.data.startswith("acct_orders_page_"))
async def show_order_history(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    lang = await services.users.get_language(tg_user.id)

    page = 1
    if isinstance(event, CallbackQuery) and event.data:
        if event.data.startswith("acct_orders_page_"):
            suffix = event.data[len("acct_orders_page_") :]
            if suffix.isdigit():
                page = max(1, int(suffix))
        elif event.data.startswith("orders_page_"):
            suffix = event.data[len("orders_page_") :]
            if suffix.isdigit():
                page = max(1, int(suffix))

    back_target = "open_account"
    page_prefix = "acct_orders_page_"

    orders, total = await services.purchases.customer_orders(tg_user.id, limit=ORDERS_PAGE_SIZE, offset=(page - 1) * ORDERS_PAGE_SIZE)
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")

    if not orders:
        text = "📦 No orders yet." if lang != "bn" else "📦 এখনো কোনো অর্ডার নেই।"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Back" if lang != "bn" else "ব্যাক", callback_data="open_account")]]
        )
    else:
        total_pages = max(1, math.ceil(total / ORDERS_PAGE_SIZE)) if total > 0 else 1
        page = min(page, total_pages)
        badge = f" ({total})" if total > 0 else ""
        text = f"<b>Orders{badge}</b>" if lang != "bn" else f"<b>অর্ডার{badge}</b>"

        buttons = []
        for order in orders:
            price_val = order["price"]
            price_str = format_dual_price(price_val, symbol, usd_rate=usd_rate, lang=lang)
            is_completed = order["status"] == "completed" and order.get("fulfillment") != "waiting"
            is_waiting = order.get("fulfillment") == "waiting" or order["status"] in {"pending", "processing", "waiting"}
            if is_completed:
                status_emoji = "✅"
            elif is_waiting:
                status_emoji = "⏳"
            else:
                status_emoji = "❌"

            # Clean product title and extract validity / duration
            prod_title = order['product_title'].strip()
            clean_title, duration, _ = product_display_labels({"title": prod_title})
            if not duration and order.get("product_id") and hasattr(services, "catalog") and hasattr(services.catalog, "product"):
                try:
                    p_data = await services.catalog.product(order["product_id"])
                    if p_data and p_data.get("duration_label"):
                        duration = p_data["duration_label"].strip()
                except Exception:
                    pass

            # Format: [ <Icon> <Name> · <Validity> · <Price> ]
            elements = [clean_title]
            if duration and duration.lower() not in {"none", "n/a", "instant"}:
                elements.append(duration)
            elements.append(price_str)

            body = " · ".join(elements)
            label = f"{status_emoji} {body}"

            if len(label) > 64:
                overhead = len(label) - len(clean_title)
                max_clean_len = max(6, 64 - overhead - 1)
                clean_title = clean_title[:max_clean_len].rstrip() + "…"
                elements[0] = clean_title
                label = f"{status_emoji} " + " · ".join(elements)
                label = label[:64]

            cb_data = f"vord_{order['id']}_{page}"
            buttons.append([
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=cb_data,
                )
            ])

        refresh_btn_text = t("btn_refresh", lang) or "Refresh"
        back_btn_text = "Back" if lang != "bn" else "ব্যাক"
        include_back = bool(back_target and back_target != "back_to_main")

        if total_pages > 1:
            if page == 1:
                nav_row = [
                    InlineKeyboardButton(text=refresh_btn_text, callback_data=f"{page_prefix}{page}"),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text="Next" if lang != "bn" else "পরবর্তী", callback_data=f"{page_prefix}{page + 1}"),
                ]
            elif page == total_pages:
                nav_row = [
                    InlineKeyboardButton(text="Prev" if lang != "bn" else "পূর্ববর্তী", callback_data=f"{page_prefix}{page - 1}"),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=refresh_btn_text, callback_data=f"{page_prefix}{page}"),
                ]
            else:
                nav_row = [
                    InlineKeyboardButton(text="Prev" if lang != "bn" else "পূর্ববর্তী", callback_data=f"{page_prefix}{page - 1}"),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text="Next" if lang != "bn" else "পরবর্তী", callback_data=f"{page_prefix}{page + 1}"),
                ]
            buttons.append(nav_row)
            if include_back:
                buttons.append([
                    InlineKeyboardButton(
                        text=back_btn_text,
                        callback_data=back_target,
                    )
                ])
        else:
            # 1 Page only: Refresh only (or include Back if navigating from account sub-menu)
            bottom_row = [InlineKeyboardButton(text=refresh_btn_text, callback_data=f"{page_prefix}1")]
            if include_back:
                bottom_row.append(
                    InlineKeyboardButton(
                        text=back_btn_text,
                        callback_data=back_target,
                    )
                )
            buttons.append(bottom_row)

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await respond(event, text, keyboard)


@router.callback_query(F.data.startswith("vord_"))
@router.callback_query(F.data.startswith("view_order_"))
async def view_order_detail(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    lang = await services.users.get_language(query.from_user.id)
    raw_data = query.data or ""
    if raw_data.startswith("view_order_"):
        parts = raw_data.removeprefix("view_order_").split("_")
    else:
        parts = raw_data.removeprefix("vord_").split("_")
    order_id = int(parts[0]) if parts and parts[0].isdigit() else None
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

    # Ownership is part of the lookup: another customer's order ID finds nothing.
    order = await services.purchases.order_for_customer(query.from_user.id, order_id) if order_id is not None else None
    if not order:
        with suppress(TelegramBadRequest):
            await query.answer(t("order_not_found", lang), show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await query.answer()
    if not query.message:
        return

    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")

    created = order["created_at"]
    date_str = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else str(created)[:16]

    if order["status"] == "completed" and order.get("fulfillment") != "waiting":
        status_line = "Status: Delivered ✅" if lang != "bn" else "স্ট্যাটাস: ডেলিভারিকৃত ✅"
    elif order.get("fulfillment") == "waiting":
        status_line = "Status: Preparing ⏳" if lang != "bn" else "স্ট্যাটাস: প্রস্তুত হচ্ছে ⏳"
    elif order["status"] in {"refunded", "cancelled"}:
        status_line = "Status: Refunded ❌" if lang != "bn" else "স্ট্যাটাস: রিফান্ডকৃত ❌"
    else:
        status_line = f"Status: {order['status'].title()}" if lang != "bn" else f"স্ট্যাটাস: {order['status'].title()}"

    price_str = price(symbol, order["price"], usd_rate=usd_rate, lang=lang)

    if lang != "bn":
        text = (
            f"<b>Order:</b> <code>{format_order_id(order['id'])}</code>\n\n"
            f"<blockquote>{status_line}\n"
            f"Product: {escape(order['product_title'])}\n"
            f"Price: <code>{price_str}</code>\n"
            f"Date: <code>{date_str}</code></blockquote>"
        )
    else:
        text = (
            f"<b>অর্ডার:</b> <code>{format_order_id(order['id'])}</code>\n\n"
            f"<blockquote>{status_line}\n"
            f"প্রোডাক্ট: {escape(order['product_title'])}\n"
            f"মূল্য: <code>{price_str}</code>\n"
            f"তারিখ: <code>{date_str}</code></blockquote>"
        )

    has_credentials = bool(order.get("delivered_item") and order.get("fulfillment") != "waiting")
    if has_credentials:
        from app.services.delivery import format_credential_lines
        cred_header = "Delivered Credentials" if lang != "bn" else "ডেলিভারি ডিটেইলস"
        text += (
            f"\n\n<b>{cred_header}:</b>\n"
            f"{format_credential_lines(str(order['delivered_item']))}"
        )

    back_cb = f"orders_page_{page}" if page > 1 else "open_orders"
    detail_buttons = []

    if has_credentials:
        if len(order["delivered_item"]) <= INLINE_CREDENTIAL_LIMIT:
            detail_buttons.append([
                InlineKeyboardButton(
                    text="Copy Credentials" if lang != "bn" else "ক্রেডেনশিয়াল কপি",
                    copy_text=CopyTextButton(text=order["delivered_item"]),
                )
            ])
        else:
            await query.message.answer_document(BufferedInputFile(order["delivered_item"].encode(), filename=f"order-{order_id}.txt"))

    claim_cb = f"claim_warranty_{order['id']}_{page}"
    action_row = [
        InlineKeyboardButton(
            text="Report Issue" if lang != "bn" else "সমস্যা জানান",
            callback_data=claim_cb,
        )
    ]
    if order.get("product_id"):
        action_row.append(
            InlineKeyboardButton(
                text="Buy Again" if lang != "bn" else "আবার কিনুন",
                callback_data=f"prod_bo_{order['product_id']}_{order['id']}_{page}",
            )
        )
    detail_buttons.append(action_row)

    detail_buttons.append([
        InlineKeyboardButton(
            text="Back",
            callback_data=back_cb,
        ),
    ])

    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=detail_buttons))



@router.callback_query(F.data.startswith("claim_warranty_"))
async def handle_claim_warranty(query: CallbackQuery, state: FSMContext, services: Services):
    """1-Tap Warranty & Support Flow with pre-filled message including Order ID."""
    await state.clear()
    raw = query.data.removeprefix("claim_warranty_")
    parts = raw.split("_")
    order_id = int(parts[0]) if parts and parts[0].isdigit() else None
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

    if not order_id:
        with suppress(TelegramBadRequest):
            await query.answer("Order not found.", show_alert=True)
        return

    order = await services.purchases.order_for_customer(query.from_user.id, order_id)
    if not order:
        with suppress(TelegramBadRequest):
            await query.answer("Order not found.", show_alert=True)
        return

    lang = await services.users.get_language(query.from_user.id)
    support_username = ((await services.settings.get("support_username")) or "").lstrip("@")
    store_name = (await services.settings.get("store_name")) or "Premium Haven"

    created = order["created_at"]
    date_str = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else str(created)[:16]
    prod_title = order.get("product_title", "Product")

    if lang == "bn":
        title = "<b>ওয়ারেন্টি ও সাপোর্ট রিপোর্ট</b>"
        body = (
            f"<b>অর্ডার আইডি:</b> <code>{format_order_id(order['id'])}</code>\n"
            f"<b>প্রোডাক্ট:</b> <b>{escape(prod_title)}</b>\n"
            f"<b>তারিখ:</b> <code>{date_str}</code>\n\n"
            f"আপনার অর্ডার সম্পর্কিত যেকোনো সমস্যায় নিচের বাটনে চাপ দিয়ে সরাসরি আমাদের সাপোর্ট টিমে জানান।"
        )
        chat_btn_text = "সাপোর্টে কথা বলুন"
        copy_id_text = "অর্ডার আইডি কপি"
    else:
        title = "<b>Warranty & Issue Report</b>"
        body = (
            f"<b>Order ID:</b> <code>{format_order_id(order['id'])}</code>\n"
            f"<b>Product:</b> <b>{escape(prod_title)}</b>\n"
            f"<b>Date:</b> <code>{date_str}</code>\n\n"
            f"For replacements, technical issues, or queries, tap below to contact our support team."
        )
        chat_btn_text = "Chat with Support"
        copy_id_text = "Copy Order ID"

    prefill = f"Hello {store_name} Support, I need help with my Order {format_order_id(order['id'])} ({prod_title})."
    kb_rows = []
    if support_username:
        kb_rows.append([
            InlineKeyboardButton(
                text=chat_btn_text,
                url=f"https://t.me/{support_username}?text={quote(prefill)}",
            )
        ])
    kb_rows.append([
        InlineKeyboardButton(
            text=copy_id_text,
            copy_text=CopyTextButton(text=format_order_id(order["id"])),
        )
    ])
    back_to_order_cb = f"vord_{order['id']}_{page}"
    kb_rows.append([
        InlineKeyboardButton(
            text="Back",
            callback_data=back_to_order_cb,
        ),
    ])

    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(f"{title}\n\n{body}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))



DEPOSITS_PAGE_SIZE = 5

DEPOSIT_STATUS_BADGES = {
    "approved": f"{ICON_CHECK} <b>Approved</b>",
    "pending": f"{ICON_TIMER} <b>Pending Review</b>",
    "rejected": f"{ICON_CROSS} <b>Rejected</b>",
}


@router.callback_query(F.data == "open_deposits")
@router.callback_query(F.data.startswith("open_deposits_dep_"))
@router.callback_query(F.data.startswith("dep_page_"))
async def show_deposit_history(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    lang = await services.users.get_language(tg_user.id)

    page = 1
    dep_id_ref: int | None = None
    if isinstance(event, CallbackQuery) and event.data:
        if event.data.startswith("open_deposits_dep_"):
            raw = event.data.removeprefix("open_deposits_dep_")
            if raw.isdigit():
                dep_id_ref = int(raw)
        elif event.data.startswith("dep_page_"):
            parts = event.data.removeprefix("dep_page_").split("_")
            if parts[0].isdigit():
                page = max(1, int(parts[0]))
            if len(parts) > 1 and parts[1].isdigit():
                dep_id_ref = int(parts[1])

    total_count = await services.deposits.count_for_user(tg_user.id)
    total_pages = max(1, math.ceil(total_count / DEPOSITS_PAGE_SIZE)) if total_count > 0 else 1
    page = min(page, total_pages)
    offset = (page - 1) * DEPOSITS_PAGE_SIZE

    deposits = await services.deposits.history(tg_user.id, limit=DEPOSITS_PAGE_SIZE, offset=offset)
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = False
    back_cb = f"back_to_dep_req_{dep_id_ref}" if dep_id_ref else "open_deposit"

    if not deposits:
        text = t("balance_history_empty", lang)
        buttons = [
            [
                InlineKeyboardButton(text=t("btn_back", lang), callback_data=back_cb),
            ],
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    else:
        badge = f" ({total_count})" if total_count > 0 else ""
        header = f"{t('balance_history_title', lang, icon_stats=ICON_STATS)}{badge}"

        buttons = []
        for deposit in deposits:
            price_str = format_dual_price(deposit["amount"], symbol, usd_rate=usd_rate, show_usd=show_usd, lang=lang)
            method = str(deposit["method_name"]).strip().replace("\n", " ")
            deposit_id = deposit["id"]

            if deposit["status"] == "approved":
                status_icon = "✅"
            elif deposit["status"] == "pending":
                status_icon = "⏳"
            else:
                status_icon = "❌"

            suffix = f" · {price_str} · {format_deposit_id(deposit_id)}"
            method_limit = max(0, 64 - len(status_icon) - len(suffix) - 1)
            label = f"{status_icon} {method[:method_limit]}{suffix}"
            detail_ref = dep_id_ref or 0
            buttons.append([
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"vdep_{deposit_id}_{page}_{detail_ref}",
                )
            ])

        text = header

        def page_cb(p: int) -> str:
            return f"dep_page_{p}_{dep_id_ref}" if dep_id_ref else f"dep_page_{p}"

        if total_pages > 1:
            if page == 1:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=page_cb(page)),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_next", lang), callback_data=page_cb(page + 1)),
                ]
            elif page == total_pages:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_prev", lang), callback_data=page_cb(page - 1)),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=page_cb(page)),
                ]
            else:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_prev", lang), callback_data=page_cb(page - 1)),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_next", lang), callback_data=page_cb(page + 1)),
                ]
            buttons.append(nav_row)

        if total_pages > 1:
            buttons.append([
                InlineKeyboardButton(text=t("btn_back", lang), callback_data=back_cb)
            ])
        else:
            buttons.append([
                InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=page_cb(1)),
                InlineKeyboardButton(text=t("btn_back", lang), callback_data=back_cb),
            ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await respond(event, text, keyboard)


@router.callback_query(F.data.startswith("vdep_"))
async def view_deposit_detail(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    lang = await services.users.get_language(query.from_user.id)
    raw = query.data.removeprefix("vdep_")
    parts = raw.split("_")
    deposit_id = int(parts[0]) if parts and parts[0].isdigit() else None
    page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    dep_id_ref = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() and int(parts[2]) > 0 else None

    if not deposit_id:
        with suppress(TelegramBadRequest):
            await query.answer(t("deposit_not_found", lang), show_alert=True)
        return

    deposit = await services.deposits.get_for_customer(query.from_user.id, deposit_id)
    if not deposit:
        with suppress(TelegramBadRequest):
            await query.answer(t("deposit_not_found", lang), show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer()
    if not query.message:
        return

    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")

    amount_str = format_dual_price(deposit["amount"], symbol, usd_rate=usd_rate, lang=lang)
    created = deposit["created_at"]
    date_str = created.strftime("%d %b %Y · %H:%M") if isinstance(created, datetime) else str(created)[:16]

    if deposit["status"] == "approved":
        status_line = "<b>Approved</b> ✅"
    elif deposit["status"] == "rejected":
        status_line = "<b>Rejected</b> ❌"
        if deposit.get("admin_note"):
            status_line += f"\n<i>{escape(deposit['admin_note'])}</i>"
    else:
        status_line = "<b>Pending</b> ⏳"
    if lang != "bn" and deposit["status"] == "pending":
        status_line += "\n<i>Checking your payment details. Do not pay again.</i>"

    text = (
        f"<b>Top-up {format_deposit_id(deposit['id'])}</b>\n\n"
        f"{status_line}\n\n"
        f"<b>Amount:</b> {amount_str}\n"
        f"<b>Method:</b> {escape(deposit['method_name'])}\n"
        f"<b>TrxID:</b> <code>{escape(deposit['transaction_id'])}</code>\n"
        f"\n<b>Submitted:</b> {date_str}"
    )

    if deposit.get("reviewed_at"):
        rev = deposit["reviewed_at"]
        rev_str = rev.strftime("%d %b %Y · %H:%M") if isinstance(rev, datetime) else str(rev)[:16]
        text += f"\n<b>Reviewed:</b> {rev_str}"

    back_to_history_cb = f"dep_page_{page}_{dep_id_ref}" if dep_id_ref else f"dep_page_{page}"

    detail_buttons = [[
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=back_to_history_cb,
        ),
    ]]

    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=detail_buttons))


