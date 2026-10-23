from __future__ import annotations

import math
from contextlib import suppress
from datetime import datetime
from html import escape
from typing import Any
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
from app.core.identifiers import format_deposit_id, format_order_id
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BALANCE,
    ICON_CART,
    ICON_CHECK,
    ICON_COIN,
    ICON_CROSS,
    ICON_CROWN,
    ICON_GLOBE,
    ICON_ID,
    ICON_KEY,
    ICON_LIGHTNING,
    ICON_LINK,
    ICON_LOCK,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_REFER,
    ICON_RESELLER,
    ICON_ROCKET,
    ICON_SHIELD,
    ICON_SHOP,
    ICON_SPARKLES,
    ICON_SPENT,
    ICON_STATS,
    ICON_SUPPORT,
    ICON_TIMER,
    ICON_USER,
    ICON_VIP,
    ICON_WARNING,
    Icons,
)
from app.bot.keyboards import (
    get_account_keyboard,
    get_language_selection_keyboard,
    get_more_inline_keyboard,
    get_notification_settings_keyboard,
    product_display_labels,
)
from app.core.i18n import t
from app.services import Services

router = Router(name="profile_router")

ORDERS_PAGE_SIZE = 5
INLINE_CREDENTIAL_LIMIT = 500


@router.callback_query(F.data == "open_more")
async def show_more_menu(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Unified secondary account, support, language and operator actions hub."""
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user = (await services.users.get(tg_user.id)) if hasattr(services.users, "get") else {}
    user = user or {}
    lang = (await services.users.get_language(tg_user.id)) if hasattr(services.users, "get_language") else "en"
    is_reseller = (user.get("rank") or "").strip().lower() in {"reseller", "reseller partner"}
    is_admin = False
    if hasattr(services, "settings") and hasattr(services.settings, "admin_chat_ids"):
        try:
            admin_ids = await services.settings.admin_chat_ids()
            is_admin = tg_user.id in admin_ids
        except Exception:
            is_admin = False

    if lang == "bn":
        text = "✨ <b>আরও অপশন</b>\nটুলস ও সেটিংস নির্বাচন করুন:"
    else:
        text = "✨ <b>More Options</b>\nSelect an option to manage tools and settings:"

    keyboard = get_more_inline_keyboard(lang=lang, is_reseller=is_reseller, is_admin=is_admin)
    await respond(event, text, keyboard)


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




@router.message(Command("me"))
@router.message(Command("profile"))
@router.message(Command("account"))
@router.message(F.text.in_({
    "My Profile",
    "my profile",
    "👤 My Profile",
    "👤 MY PROFILE",
    "MY PROFILE",
    "Profile",
    "profile",
    "👤 Profile",
    "Account",
    "account",
    "👤 Account",
    "👤 ACCOUNT",
    "ACCOUNT",
    "💼 Account",
    "👤 আমার প্রোফাইল",
    "আমার প্রোফাইল",
    "👤 একাউন্ট",
    "একাউন্ট",
    "👤 অ্যাকাউন্ট",
    "অ্যাকাউন্ট",
    "👤 একাউন্ট ও রেফার",
    "একাউন্ট ও রেফার",
    "👤 অ্যাকাউন্ট ও রেফার",
    "অ্যাকাউন্ট ও রেফার",
    "Account & Refer",
    "account & refer",
    "👤 Account & Refer",
    "👤 ACCOUNT & REFER",
    "ACCOUNT & REFER",
    "Settings",
    "settings",
    "⚙️ Settings",
}))
@router.message(F.text.casefold() == "my profile")
@router.message(F.text.casefold() == "profile")
@router.message(F.text.casefold() == "account")
@router.message(F.text.casefold() == "account & refer")
@router.message(F.text.casefold() == "account and refer")
@router.callback_query(F.data == "open_account")
async def show_user_profile(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Unified profile routed into More hub."""
    await show_more_menu(event, state, services)


@router.message(Command("language"))
@router.message(Command("lang"))
@router.callback_query(F.data == "open_language_menu")
async def show_language_menu(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return
    user_lang = await services.users.get_language(tg_user.id)
    text = t("select_language_prompt", user_lang)
    kb = get_language_selection_keyboard(current_lang=user_lang, back_target="open_more")
    await respond(event, text, kb)


async def _save_language_and_return_to_menu(
    event: CallbackQuery, state: FSMContext, services: Services, language: str
) -> None:
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    selected = await services.users.set_language(tg_user.id, language)
    with suppress(TelegramBadRequest):
        await event.answer(t("lang_switched_toast", selected))

    message = event.message
    if isinstance(message, Message):
        with suppress(TelegramBadRequest):
            await message.delete()
        from app.bot.handlers.start import render_main_dashboard

        await render_main_dashboard(message, services, tg_user.id)


@router.callback_query(F.data == "set_lang_en")
async def select_english_language(event: CallbackQuery, state: FSMContext, services: Services):
    await _save_language_and_return_to_menu(event, state, services, "en")


@router.callback_query(F.data == "set_lang_bn")
async def select_bengali_language(event: CallbackQuery, state: FSMContext, services: Services):
    await _save_language_and_return_to_menu(event, state, services, "bn")


@router.message(Command("en"))
@router.message(Command("english"))
@router.message(F.text.casefold().in_({"english", "en"}))
async def switch_to_en(message: Message, state: FSMContext, services: Services):
    """Direct 1-step switch to English."""
    await state.clear()
    tg_user = message.from_user
    if not tg_user:
        return
    await services.users.set_language(tg_user.id, "en")
    with suppress(TelegramBadRequest):
        await message.answer(t("lang_switched_toast", "en"))
    from app.bot.handlers.start import render_main_dashboard
    await render_main_dashboard(message, services, tg_user.id)


@router.message(Command("bn"))
@router.message(Command("bangla"))
@router.message(F.text.casefold().in_({"bangla", "bn", "বাংলা"}))
async def switch_to_bn(message: Message, state: FSMContext, services: Services):
    """Direct 1-step switch to Bengali."""
    await state.clear()
    tg_user = message.from_user
    if not tg_user:
        return
    await services.users.set_language(tg_user.id, "bn")
    with suppress(TelegramBadRequest):
        await message.answer(t("lang_switched_toast", "bn"))
    from app.bot.handlers.start import render_main_dashboard
    await render_main_dashboard(message, services, tg_user.id)


@router.message(Command("referral"))
@router.message(Command("refer"))
@router.message(F.text.in_({
    "🎁 Refer & Earn",
    "Refer & Earn",
    "refer & earn",
    "🎁 REFER & EARN",
    "REFER & EARN",
    "🎁 Refer",
    "Refer",
    "🎁 REFER",
    "REFER",
    "🎁 Referral",
    "Referral",
    "referral",
    "🎁 REFERRAL",
    "REFERRAL",
    "🎁 রেফার ও ইনকাম",
    "রেফার ও ইনকাম",
    "🎁 রেফারেল",
    "রেফারেল",
    "🎁 রেফার",
    "রেফার",
}))
@router.callback_query(F.data == "open_referral")
async def show_referral_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user = await services.users.get(tg_user.id)
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"

    symbol = await services.settings.get("currency_symbol")
    reward_amount = await services.settings.number("referral_reward_amount")
    reward_enabled = await services.settings.flag("referral_enabled")
    usd_rate = await services.settings.number("usd_rate")

    reward_str = format_dual_price(reward_amount, symbol, usd_rate=usd_rate, lang=lang)

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

    total_earned_str = format_dual_price(total_earned, symbol, usd_rate=usd_rate, lang=lang)

    bot_user = await services.notifier.bot_username()
    ref_link = f"https://t.me/{bot_user}?start={tg_user.id}"
    store_name = (await services.settings.get("store_name")) or "Premium Haven"

    reward_display = reward_str if reward_enabled and reward_amount > 0 else f"0 {symbol}"
    earned_display = total_earned_str

    if lang != "bn":
        reward_line = (
            f"Earn <b>{reward_display}</b> per new friend.\n"
            "They must start the bot and complete any required channel check."
            if reward_enabled and reward_amount > 0
            else "Referral rewards are currently paused."
        )
        text = (
            "<b>Refer & Earn</b>\n\n"
            f"{reward_line}\n\n"
            f"Successful invites: <code>{total_invited}</code>\n"
            f"Earned: <code>{earned_display}</code>\n\n"
            "Your link:\n"
            f"<code>{ref_link}</code>"
        )
        copy_label = "Copy Link"
        share_label = "Share"
        back_label = "Back"
        share_msg = quote(f"Join {store_name}")
    else:
        reward_line = f"বোনাস: <code>{reward_display}</code> (প্রতি রেফার)\n" if reward_enabled and reward_amount > 0 else f"বোনাস: <code>0 {symbol}</code> (প্রতি রেফার)\n"
        text = (
            f"মোট ইনভাইট: <code>{total_invited}</code>\n"
            f"মোট আয়: <code>{earned_display}</code>\n"
            f"{reward_line}\n"
            "আপনার রেফারেল লিংক:\n"
            f"<code>{ref_link}</code>"
        )
        copy_label = "লিংক কপি করুন"
        share_label = "শেয়ার"
        back_label = "Back" if lang != "bn" else "ব্যাক"
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
        [
            InlineKeyboardButton(
                text=back_label,
                callback_data="open_more",
            ),
        ],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await respond(event, text, kb)



# --- Reseller Portal (Wholesale & Business Program) ---
@router.message(Command("reseller"))
@router.message(F.text.in_({
    "💼 Reseller Panel",
    "Reseller Panel",
    "reseller panel",
    "RESELLER PANEL",
    "💼 RESELLER PANEL",
    "reseller",
    "RESELLER",
    "💼 Reseller",
    "Reseller",
    "💼 RESELLER",
    "💼 Become Reseller",
    "Become Reseller",
    "become reseller",
    "💼 Apply as a Reseller",
    "Apply as a Reseller",
    "💼 রিসেলার হন",
    "রিসেলার হন",
    "💼 রিসেলার প্যানেল",
    "রিসেলার প্যানেল",
    "💼 রিসেলার",
    "রিসেলার",
}))
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
                "Status: Active\n"
                "Reseller pricing is enabled.\n"
                f"Orders: <b>{stats['total_orders']}</b>\n"
                f"Spent: <b>{recent_spend_str}</b>\n"
                f"Balance: <b>{balance_str}</b>"
            )
            api_btn_text = "API"
            refresh_btn_text = "Refresh"
            back_btn_text = "Back"
        else:
            text = (
                "<b>রিসেলার পার্টনার</b>\n\n"
                "স্ট্যাটাস: <b>সক্রিয় পার্টনার</b>\n"
                "টিয়ার: পাইকারি ডিসকাউন্ট চালু\n"
                f"অর্ডার: <b>{stats['total_orders']}</b>\n"
                f"খরচ: <b>{recent_spend_str}</b>\n"
                f"ব্যালেন্স: <b>{balance_str}</b>"
            )
            api_btn_text = "ডেভেলপার এপিআই"
            refresh_btn_text = "রিফ্রেশ"
            back_btn_text = "ব্যাক"

        rows.append([InlineKeyboardButton(text=api_btn_text, callback_data="open_api_hub")])
        rows.append([
            InlineKeyboardButton(text=refresh_btn_text, callback_data="open_reseller_hub"),
            InlineKeyboardButton(text=back_btn_text, callback_data="open_more"),
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
            rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="open_more")])
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
                comp_header = "<b>Price Comparison:</b>" if lang != "bn" else "<b>মূল্য তুলনা:</b>"
                comp_block = f"\n\n{comp_header}\n" + "\n".join(comparison_lines)

            if lang != "bn":
                text = (
                    "<b>Reseller Program</b>\n\n"
                    "Apply for reseller pricing on eligible products."
                    f"{comp_block}"
                )
                apply_btn_text = "Apply"
                contact_btn_text = "Contact Support"
                back_btn_text = "Back"
            else:
                text = (
                    "<b>রিসেলার প্রোগ্রাম</b>\n\n"
                    "আমাদের সম্পূর্ণ ক্যাটালগে আকর্ষণীয় পাইকারি ডিসকাউন্ট রেট উপভোগ করুন এবং প্রতিটি বিক্রয়ে সর্বোচ্চ মুনাফা নিশ্চিত করুন।"
                    f"{comp_block}"
                )
                apply_btn_text = "রিসেলার আবেদন করুন"
                contact_btn_text = "সাপোর্ট যোগাযোগ"
                back_btn_text = "ব্যাক"

            rows.append([InlineKeyboardButton(text=apply_btn_text, callback_data="reseller_start_apply")])
            if handle:
                prefill = f"Hello, I would like to inquire about becoming a Reseller at {store_name}."
                rows.append([InlineKeyboardButton(text=contact_btn_text, url=f"https://t.me/{handle}?text={quote(prefill)}")])
            rows.append([InlineKeyboardButton(text=back_btn_text, callback_data="open_more")])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await respond(event, text, kb)

show_reseller_info = show_reseller_hub


# --- Developer REST API Portal ---
@router.message(Command("api"))
@router.message(F.text.in_({
    "🔑 Developer API",
    "Developer API",
    "🔑 API",
    "API",
    "api",
    "/api",
    "🔑 ডেভেলপার এপিআই",
    "ডেভেলপার এপিআই",
    "🔑 এপিআই",
    "এপিআই",
}))
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
    symbol = (await services.settings.get("currency_symbol") or "৳").strip()
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    user_balance = float(user.get("balance", 0.0)) if user else 0.0

    if lang == "en" and show_usd and usd_rate and usd_rate > 0:
        usd = round(user_balance / usd_rate, 2)
        balance_str = f"${usd:g}" if usd == int(usd) else f"${usd:.2f}"
    else:
        balance_str = f"{symbol}{user_balance:g}" if user_balance == int(user_balance) else f"{symbol}{user_balance:.2f}"

    recent_spend_str = price(symbol, stats["total_spent"], usd_rate=usd_rate, lang=lang)

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
            f"Status: <b>{status_line}</b> ({tier_label})\n"
            f"API Key: {key_display}\n"
            f"Balance: <b>{balance_str}</b>\n"
            f"Orders: <b>{stats['total_orders']}</b>\n\n"
            "Endpoint:\n"
            f"{endpoint_text}"
        )
        refresh_text = "Refresh"
        back_text = "Back"
    else:
        text = (
            f"স্ট্যাটাস: <b>{status_line}</b> ({tier_label})\n"
            f"এপিআই কি: {key_display}\n"
            f"ব্যালেন্স: <b>{balance_str}</b>\n"
            f"অর্ডার: <b>{stats['total_orders']}</b>\n\n"
            "এন্ডপয়েন্ট:\n"
            f"{endpoint_text}"
        )
        refresh_text = "রিফ্রেশ"
        back_text = "ব্যাক"

    rows = []
    if key:
        rows.append([
            InlineKeyboardButton(
                text="Regenerate Key" if lang != "bn" else "কি পুনরায় তৈরি",
                callback_data="reseller_regen_prompt",
            )
        ])
        if is_connected:
            rows.append([
                InlineKeyboardButton(
                    text="Disable API" if lang != "bn" else "এপিআই বন্ধ করুন",
                    callback_data="reseller_toggle_active",
                )
            ])
        else:
            rows.append([
                InlineKeyboardButton(
                    text="Enable API" if lang != "bn" else "এপিআই চালু করুন",
                    callback_data="reseller_toggle_active",
                )
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
        InlineKeyboardButton(text=back_text, callback_data="open_more"),
    ])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await respond(event, text, kb)


# --- User Notification Settings Hub ---
@router.message(F.text.in_({
    "🔔 Notifications",
    "Notifications",
    "notifications",
    "🔔 নোটিফিকেশন",
    "নোটিফিকেশন",
}))
@router.callback_query(F.data == "open_notifications_hub")
async def show_notifications_hub(event: Message | CallbackQuery, state: FSMContext | None, services: Services):
    if state:
        await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    lang = await services.users.get_language(tg_user.id)
    prefs = await services.users.get_notification_preferences(tg_user.id)

    if lang != "bn":
        text = (
            "<b>Notifications</b>\n\n"
            "Payment results and order deliveries are always sent.\n"
            "News, offers and restock alerts are optional."
        )
    else:
        text = (
            "<b>নোটিফিকেশন</b>\n\n"
            "পেমেন্টের ফলাফল ও অর্ডার ডেলিভারি সবসময় পাঠানো হয়।\n"
            "খবর, অফার ও রিস্টক নোটিশ চালু বা বন্ধ করতে পারেন।"
        )

    kb = get_notification_settings_keyboard(prefs, lang=lang)
    await respond(event, text, kb)


@router.callback_query(F.data.startswith("notif_toggle_"))
async def handle_notification_toggle(query: CallbackQuery, services: Services):
    tg_user = query.from_user
    if not tg_user:
        return

    key = query.data.removeprefix("notif_toggle_")
    if key != "notify_news":
        with suppress(TelegramBadRequest):
            await query.answer("Payment results and order deliveries stay on.")
        return
    updated_prefs = await services.users.toggle_notification_preference(tg_user.id, key)
    lang = await services.users.get_language(tg_user.id)

    new_kb = get_notification_settings_keyboard(updated_prefs, lang=lang)
    with suppress(TelegramBadRequest):
        if query.message:
            await query.message.edit_reply_markup(reply_markup=new_kb)

    if lang == "bn":
        status_str = "চালু করা হয়েছে ✅" if updated_prefs.get(key, True) else "বন্ধ করা হয়েছে 🔕"
        toast = f"নোটিফিকেশন {status_str}"
    else:
        status_str = "On" if updated_prefs.get(key, True) else "Off"
        toast = f"News & Offers: {status_str}"
    with suppress(TelegramBadRequest):
        await query.answer(toast)


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
        await event.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "reseller_web_docs_notice")
async def reseller_web_docs_notice_handler(event: CallbackQuery, services: Services):
    with suppress(TelegramBadRequest):
        await event.answer(
            "Web docs are hosted at /api/v1/reseller/docs on your server.",
            show_alert=True,
        )


@router.message(Command("orders"))
@router.message(Command("order"))
@router.message(Command("history"))
@router.message(F.text.in_({
    "Orders",
    "orders",
    "📦 Orders",
    "📦 ORDERS",
    "ORDERS",
    "My Orders",
    "my orders",
    "📦 My Orders",
    "📦 MY ORDERS",
    "MY ORDERS",
    "Order History",
    "order history",
    "📦 Order History",
    "📦 ORDER HISTORY",
    "ORDER HISTORY",
}))
@router.message(F.text.casefold() == "orders")
@router.message(F.text.casefold() == "my orders")
@router.message(F.text.casefold() == "order history")
@router.callback_query(F.data == "open_orders")
@router.callback_query(F.data == "open_orders_acc")
@router.callback_query(F.data.startswith("orders_page_"))
@router.callback_query(F.data.startswith("orders_acc_page_"))
async def show_order_history(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    lang = await services.users.get_language(tg_user.id)

    from_acc = False
    page = 1
    if isinstance(event, CallbackQuery) and event.data:
        if event.data == "open_orders_acc" or event.data.startswith("orders_acc_page_"):
            from_acc = True
            suffix = event.data[len("orders_acc_page_") :]
            if suffix.isdigit():
                page = max(1, int(suffix))
        elif event.data.startswith("orders_page_"):
            suffix = event.data[len("orders_page_") :]
            if suffix.isdigit():
                page = max(1, int(suffix))

    back_target = "open_account" if from_acc else "back_to_main"
    page_prefix = "orders_acc_page_" if from_acc else "orders_page_"

    orders, total = await services.purchases.customer_orders(tg_user.id, limit=ORDERS_PAGE_SIZE, offset=(page - 1) * ORDERS_PAGE_SIZE)
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")

    if not orders:
        text = "📦 No orders yet." if lang != "bn" else "📦 এখনো কোনো অর্ডার নেই।"
        keyboard = None
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

            cb_data = f"vord_{order['id']}_{page}_1" if from_acc else f"vord_{order['id']}_{page}"
            buttons.append([
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=cb_data,
                )
            ])

        refresh_btn_text = t("btn_refresh", lang) or "Refresh"
        back_btn_text = "Back" if lang != "bn" else "ব্যাক"
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
            buttons.append([
                InlineKeyboardButton(
                    text=back_btn_text,
                    callback_data=back_target,
                )
            ])
        else:
            # 1 Page only: Refresh and Back side-by-side
            buttons.append([
                InlineKeyboardButton(text=refresh_btn_text, callback_data=f"{page_prefix}1"),
                InlineKeyboardButton(
                    text=back_btn_text,
                    callback_data=back_target,
                ),
            ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await respond(event, text, keyboard)


@router.callback_query(F.data.startswith("vord_"))
@router.callback_query(F.data.startswith("view_order_"))
async def view_order_detail(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    lang = await services.users.get_language(query.from_user.id)
    raw = query.data
    page = 1
    from_acc = False
    if raw.startswith("vord_"):
        parts = raw.removeprefix("vord_").split("_")
        order_id = int(parts[0]) if parts and parts[0].isdigit() else None
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        from_acc = len(parts) > 2 and parts[2] == "1"
    else:
        order_id = callback_int(raw, "view_order_")

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
            f"{status_line}\n"
            f"Product: {escape(order['product_title'])}\n"
            f"Price: <code>{price_str}</code>\n"
            f"Date: <code>{date_str}</code>"
        )
    else:
        text = (
            f"<b>অর্ডার:</b> <code>{format_order_id(order['id'])}</code>\n\n"
            f"{status_line}\n"
            f"প্রোডাক্ট: {escape(order['product_title'])}\n"
            f"মূল্য: <code>{price_str}</code>\n"
            f"তারিখ: <code>{date_str}</code>"
        )

    has_credentials = bool(order.get("delivered_item") and order.get("fulfillment") != "waiting")
    if has_credentials:
        cred_header = "Delivered Credentials" if lang != "bn" else "ডেলিভারিকৃত ক্রেডেনশিয়াল"
        text += (
            f"\n\n<b>{cred_header}:</b>\n"
            f"<code>{escape(order['delivered_item'])}</code>"
        )

    if from_acc:
        back_cb = f"orders_acc_page_{page}" if page > 1 else "open_orders_acc"
    else:
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

    claim_cb = f"claim_warranty_{order['id']}_{page}_1" if from_acc else f"claim_warranty_{order['id']}_{page}"
    action_row = [
        InlineKeyboardButton(
            text="Report Issue" if lang != "bn" else "সমস্যা জানান",
            callback_data=claim_cb,
        )
    ]
    if order.get("product_id"):
        from_acc_flag = 1 if from_acc else 0
        action_row.append(
            InlineKeyboardButton(
                text="Buy Again" if lang != "bn" else "আবার কিনুন",
                callback_data=f"prod_bo_{order['product_id']}_{order['id']}_{page}_{from_acc_flag}",
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
    from_acc = len(parts) > 2 and parts[2] == "1"

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
    back_to_order_cb = f"vord_{order['id']}_{page}_1" if from_acc else f"vord_{order['id']}_{page}"
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


@router.message(F.text.in_({
    "Balance History",
    "balance history",
    "📊 Balance History",
    "📊 BALANCE HISTORY",
    "BALANCE HISTORY",
    "Deposit History",
    "deposit history",
    "📊 Deposit History",
    "📊 DEPOSIT HISTORY",
    "DEPOSIT HISTORY",
    "ডিপোজিট হিস্ট্রি",
    "📊 ডিপোজিট হিস্ট্রি",
    "ব্যালেন্স হিস্ট্রি",
    "📊 ব্যালেন্স হিস্ট্রি",
}))
@router.message(F.text.casefold() == "balance history")
@router.message(F.text.casefold() == "deposit history")
@router.callback_query(F.data == "open_deposits")
@router.callback_query(F.data == "open_deposits_from_wallet")
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
    from_wallet = True
    if isinstance(event, CallbackQuery) and event.data:
        if event.data == "open_deposits_from_wallet":
            from_wallet = True
        elif event.data.startswith("open_deposits_dep_"):
            raw = event.data.removeprefix("open_deposits_dep_")
            if raw.isdigit():
                dep_id_ref = int(raw)
        elif event.data.startswith("dep_page_"):
            raw = event.data.removeprefix("dep_page_")
            if raw.endswith("_w"):
                from_wallet = True
                raw = raw[:-2]
            parts = raw.split("_")
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
    try:
        show_usd = await services.settings.flag("show_usd_price")
    except Exception:
        show_usd = False
    back_cb = f"back_to_dep_req_{dep_id_ref}" if dep_id_ref else ("open_deposit" if from_wallet else "open_account")

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
            if dep_id_ref:
                return f"dep_page_{p}_{dep_id_ref}"
            return f"dep_page_{p}_w"

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
        status_line = f"<b>{t('status_approved', lang)}</b> ✅"
    elif deposit["status"] == "rejected":
        status_line = f"<b>{t('status_rejected', lang)}</b> ❌"
        if deposit.get("admin_note"):
            status_line += f"\n<i>{escape(deposit['admin_note'])}</i>"
    else:
        status_line = f"<b>{t('status_pending', lang)}</b>"
    if lang != "bn" and deposit["status"] == "pending":
        status_line += "\n<i>Checking your payment details. Do not pay again.</i>"

    text = (
        f"{t('deposit_detail_title', lang, id=format_deposit_id(deposit['id']))}\n\n"
        f"{status_line}\n\n"
        f"<b>{t('deposit_amount', lang)}:</b> {amount_str}\n"
        f"<b>{t('deposit_method', lang)}:</b> {escape(deposit['method_name'])}\n"
        f"<b>{t('deposit_trxid', lang)}:</b> <code>{escape(deposit['transaction_id'])}</code>\n"
        f"\n<b>{t('deposit_submitted_at', lang)}:</b> {date_str}"
    )

    if deposit.get("reviewed_at"):
        rev = deposit["reviewed_at"]
        rev_str = rev.strftime("%d %b %Y · %H:%M") if isinstance(rev, datetime) else str(rev)[:16]
        text += f"\n<b>{t('deposit_reviewed_at', lang)}:</b> {rev_str}"

    back_to_history_cb = f"dep_page_{page}_{dep_id_ref}" if dep_id_ref else f"dep_page_{page}_w"

    detail_buttons = [[
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=back_to_history_cb,
        ),
    ]]

    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=detail_buttons))


@router.message(Command("pricelist"))
@router.message(Command("prices"))
@router.message(F.text.in_({
    "Price List",
    "price list",
    "📊 Price List",
    "📊 PRICE LIST",
    "PRICE LIST",
    "📊 প্রাইস লিস্ট",
    "প্রাইস লিস্ট",
}))
@router.message(F.text.casefold() == "price list")
@router.message(F.text.casefold() == "pricelist")
@router.callback_query(F.data == "open_price_list")
async def show_price_list(event: Message | CallbackQuery, state: FSMContext | None, services: Services):
    if state:
        await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return

    user = await services.users.get(tg_user.id)
    lang = await services.users.get_language(tg_user.id)
    is_reseller = (user.get("rank") or "").strip().lower() == "reseller" if user else False

    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")

    categories = await services.catalog.categories()
    products = await services.catalog.products(active_only=True, limit=500)

    # Group products by category_id
    cat_map: dict[int | None, str] = {c["id"]: c["name"] for c in categories}
    cat_products: dict[str, list[dict[str, Any]]] = {}

    for p in products:
        cid = p.get("category_id")
        cat_name = cat_map.get(cid, "Other Products" if lang == "en" else "অন্যান্য প্রোডাক্ট")
        if cat_name not in cat_products:
            cat_products[cat_name] = []
        cat_products[cat_name].append(p)

    title_text = "📊 <b>Live Price & Stock List</b>" if lang == "en" else "📊 <b>লাইভ প্রোডাক্ট প্রাইস লিস্ট</b>"

    sections = []
    for cat_name, prod_list in cat_products.items():
        cat_lines = [f"📂 <b>{escape(cat_name)}</b>"]
        for p in prod_list:
            p_price = p["price"]
            r_price = p.get("reseller_price")
            is_manual = p.get("delivery_type") == "manual"
            stock = p.get("stock", 0)

            if is_reseller and r_price is not None and float(r_price) > 0:
                price_str = format_dual_price(float(r_price), symbol, usd_rate=usd_rate, lang=lang)
            else:
                price_str = format_dual_price(p_price, symbol, usd_rate=usd_rate, lang=lang)

            if is_manual:
                stock_label = "Manual" if lang == "en" else "ম্যানুয়াল"
            elif stock > 0:
                stock_label = f"Stock: {stock}" if lang == "en" else f"স্টক: {stock}"
            else:
                stock_label = "Out of Stock" if lang == "en" else "স্টক শেষ"

            prod_icon = (p.get("icon") or "").strip()
            icon_prefix = f"{prod_icon} " if prod_icon else ""
            cat_lines.append(f"  {icon_prefix}<b>{escape(p['title'])}</b>: <code>{price_str}</code> (<i>{stock_label}</i>)")
        sections.append("\n".join(cat_lines))

    if not sections:
        body = "<i>No products currently available in the catalog.</i>" if lang == "en" else "<i>ক্যাটালগে বর্তমানে কোনো প্রোডাক্ট নেই।</i>"
    else:
        body = "\n\n".join(sections)

    footer = "\n\n💡 <i>All prices are live and updated instantly.</i>" if lang == "en" else "\n\n💡 <i>সকল মূল্য লাইভ এবং তাৎক্ষণিকভাবে আপডেট করা হয়।</i>"
    text = f"{title_text}\n\n{body}{footer}"

    buttons = [
        [
            InlineKeyboardButton(
                text=t("btn_browse_products", lang),
                callback_data="open_categories",
                icon_custom_emoji_id=Icons.PRODUCTS,
            ),
            InlineKeyboardButton(
                text=t("btn_refresh", lang),
                callback_data="open_price_list",
                icon_custom_emoji_id=Icons.REFRESH,
            ),
        ],
        [
            InlineKeyboardButton(
                text=t("btn_back", lang),
                callback_data="open_account",
                icon_custom_emoji_id=Icons.BACK,
            ),
        ],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await respond(event, text, kb)
