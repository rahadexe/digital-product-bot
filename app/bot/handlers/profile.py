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
    ICON_VIP,
    ICON_WARNING,
    Icons,
)
from app.bot.keyboards import get_account_keyboard, get_language_selection_keyboard
from app.core.i18n import t
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
    "👤 আমার প্রোফাইল",
    "আমার প্রোফাইল",
    "👤 मेरी प्रोफाइल",
    "मेरी प्रोफाइल",
    "👤 میری پروفائل",
    "میری پروفائل",
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

    lang = (user.get("language") or "en").strip().lower()
    rank_val = (user.get("rank") or "Standard").strip()
    if rank_val.lower() in {"reseller", "reseller partner"}:
        account_type_label = t("rank_reseller", lang)
    else:
        account_type_label = t("rank_standard", lang)

    balance_display = price(symbol, user.get("balance", 0.0), usd_rate=usd_rate, show_usd=show_usd)
    spent_display = price(symbol, stats.get("total_spent", 0.0), usd_rate=usd_rate, show_usd=show_usd)
    order_count = stats.get("order_count", 0)

    tg_username = tg_user.username
    username_line = (
        f"{ICON_SPARKLES} <b>{t('profile_username', lang)}:</b> @{escape(tg_username)}\n"
        if tg_username
        else ""
    )

    async with services.db.connect() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS total_invited FROM referral_rewards WHERE referrer_tg_id = $1",
            tg_user.id,
        )
        total_invited = row["total_invited"] if row else 0

    bot_user = await services.notifier.bot_username()
    ref_link = f"https://t.me/{bot_user}?start=ref_{tg_user.id}" if bot_user else ""

    text = (
        f"{t('profile_title', lang, icon_account=ICON_ACCOUNT)}\n\n"
        f"{ICON_CROWN} <b>{t('profile_name', lang)}:</b> {user_name}\n"
        f"{username_line}"
        f"{ICON_ID} <b>{t('profile_user_id', lang)}:</b> <code>{tg_user.id}</code>\n"
        f"{ICON_RESELLER} <b>{t('profile_account_type', lang)}:</b> <b>{account_type_label}</b>\n\n"
        f"{ICON_BALANCE} <b>{t('profile_current_balance', lang)}:</b> <code>{balance_display}</code>\n"
        f"{ICON_ORDERS} <b>{t('profile_total_orders', lang)}:</b> {order_count}\n"
        f"{ICON_SPENT} <b>{t('profile_total_spent', lang)}:</b> <code>{spent_display}</code>\n"
        f"{ICON_REFER} <b>{t('profile_referrals', lang)}:</b> {total_invited}\n\n"
        f"{ICON_LINK} <b>{t('profile_referral_link', lang)}:</b>\n"
        f"<code>{ref_link}</code>"
    )
    is_admin = tg_user.id in await services.settings.admin_chat_ids()
    await respond(event, text, get_account_keyboard(lang=lang, is_admin=is_admin, ref_link=ref_link))


@router.message(Command("language"))
@router.message(Command("lang"))
@router.callback_query(F.data == "open_language_menu")
async def show_language_menu(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return
    current_lang = await services.users.get_language(tg_user.id)
    text = t("select_language_prompt", current_lang)
    back_target = "back_to_main" if isinstance(event, CallbackQuery) else None
    kb = get_language_selection_keyboard(current_lang=current_lang, back_target=back_target)
    await respond(event, text, kb)


@router.message(Command("referral"))
@router.message(Command("refer"))
@router.message(F.text.in_({
    "🎁 Refer & Earn",
    "Refer & Earn",
    "refer & earn",
    "🎁 রেফার ও ইনকাম",
    "রেফার ও ইনকাম",
    "🎁 रेफर और कमाएं",
    "रेफर और कमाएं",
    "🎁 ریفر اور کمائیں",
    "ریفر اور کمائیں",
}))
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

    user = await services.users.get(tg_user.id)
    lang = (user.get("language") or "en").strip().lower() if user else "en"

    if reward_enabled and reward_amount > 0:
        steps_text = (
            f"{t('referral_step_1', lang)}\n"
            f"{t('referral_step_2', lang)}\n"
            f"{t('referral_step_3', lang, reward=reward_display)}\n\n"
        )
    else:
        steps_text = f"{t('referral_step_1', lang)}\n\n"

    stats_header = t("referral_stats_header", lang, icon_stats=ICON_STATS)

    text = (
        f"{t('referral_title', lang, icon_refer=ICON_REFER)}\n\n"
        f"{steps_text}"
        f"{stats_header}\n"
        f"{ICON_ACCOUNT} <b>{t('referral_stat_total', lang)}:</b> <code>{total_invited}</code>\n"
        f"{ICON_COIN} <b>{t('referral_stat_earned', lang)}:</b> <code>{earned_display}</code>\n\n"
        f"{ICON_LINK} <b>{t('referral_link_label', lang)}:</b>\n"
        f"<code>{ref_link}</code>"
    )

    share_text = quote(f"🔥 Join {store_name}!\n\n👉 {ref_link}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_share_referral", lang),
                    url=f"https://t.me/share/url?url={ref_link}&text={share_text}",
                    style="success",
                    icon_custom_emoji_id=Icons.CHANNEL,
                ),
                InlineKeyboardButton(
                    text=t("btn_copy_link", lang),
                    copy_text=CopyTextButton(text=ref_link),
                    style="primary",
                    icon_custom_emoji_id=Icons.NOTE,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=t("btn_back", lang),
                    callback_data="back_to_main",
                    style="primary",
                    icon_custom_emoji_id=Icons.BACK,
                ),
                InlineKeyboardButton(
                    text=t("btn_close", lang),
                    callback_data="close_menu",
                    style="danger",
                    icon_custom_emoji_id=Icons.CLOSE,
                ),
            ],
        ]
    )
    await respond(event, text, kb)


@router.message(Command("api"))
@router.message(Command("reseller"))
@router.message(F.text.in_({
    "💼 Become Reseller",
    "Become Reseller",
    "become reseller",
    "💼 Apply as a Reseller",
    "Apply as a Reseller",
    "apply as a reseller",
    "Reseller Panel",
    "💼 Reseller Panel",
    "reseller panel",
    "reseller",
    "💼 রিসেলার হন",
    "রিসেলার হন",
    "💼 রিসেলার প্যানেল",
    "রিসেলার প্যানেল",
    "💼 रीसेलर बनें",
    "रीसेलर बनें",
    "💼 रीसेलर पैनल",
    "रीसेलर पैनल",
    "💼 ری سیلر بنیں",
    "ری سیلر بنیں",
    "💼 ری سیلر پینل",
    "ری سیلر پینل",
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

        lang = (user.get("language") or "en").strip().lower() if user else "en"
        text = (
            f"{t('reseller_panel_title', lang, icon_reseller=ICON_RESELLER)}\n\n"
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
                text="Close",
                callback_data="close_menu",
                style="danger",
                icon_custom_emoji_id=Icons.CLOSE,
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

    lang = (user.get("language") or "en").strip().lower() if user else "en"
    text = (
        f"{t('reseller_apply_title', lang, icon_reseller=ICON_RESELLER)}\n\n"
        f"{t('reseller_apply_text', lang)}\n\n"
        f"{ICON_NOTE} <b>{t('reseller_format_label', lang)}:</b>\n"
        f"<code>{format_copy_text}</code>\n\n"
        f"{ICON_VIP} <b>{t('reseller_benefits_title', lang)}:</b>\n"
        f"{ICON_COIN} {t('reseller_b1', lang)}\n"
        f"{ICON_KEY} {t('reseller_b2', lang)}\n"
        f"{ICON_LIGHTNING} {t('reseller_b3', lang)}\n"
        f"{ICON_SUPPORT} {t('reseller_b4', lang)}"
    )

    rows = [
        [
            InlineKeyboardButton(
                text=t("btn_copy_format", lang),
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
                text=t("btn_contact_management", lang),
                url=f"https://t.me/{handle}?text={quote(prefill)}",
                style="success",
                icon_custom_emoji_id=Icons.RESELLER,
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text=t("btn_close", lang),
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
        f"• Keep this API key confidential. Anyone with this key can make purchases using your wallet balance.\n"
        f"• It will only be displayed once. Copy and store it safely.\n\n"
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
        f"{ICON_SHIELD} <i>For maximum security, your complete secret key is securely hashed in the database. If you lost your key, you can regenerate a new one below.</i>"
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
        f"Generating a new API key will immediately deactivate your existing key. "
        f"Any bots or websites connected using your current key will stop working until updated with the new key.\n\n"
        f"Are you sure you want to regenerate your API key?"
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
                    text="Back",
                    callback_data="open_reseller",
                    style="primary",
                    icon_custom_emoji_id=Icons.BACK,
                ),
                InlineKeyboardButton(
                    text="Close",
                    callback_data="close_menu",
                    style="danger",
                    icon_custom_emoji_id=Icons.CLOSE,
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
    if not user or (user.get("rank") or "").strip().lower() != "reseller":
        await event.answer("Access denied.", show_alert=True)
        return

    raw_key, _ = await services.reseller.generate_key(tg_user.id)
    _, docs_rows = reseller_api_links(services.config)

    text = (
        f"{ICON_CHECK} <b>New API Key Generated Successfully!</b>\n\n"
        f"{ICON_KEY} <b>Your New Secret API Key:</b>\n"
        f"<code>{raw_key}</code>\n\n"
        f"{ICON_WARNING} <i>Your previous API key has been deactivated. Configure this new key in your bot or website.</i>"
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
        f"Include your API Key in every request header:\n"
        f"<code>X-API-Key: rk_live_your_key</code>\n\n"
        f"<b>2. Endpoints:</b>\n"
        f"• <code>GET /api/v1/reseller/me</code>\n  Check your balance & profile\n"
        f"• <code>GET /api/v1/reseller/products</code>\n  List products & reseller rates\n"
        f"• <code>POST /api/v1/reseller/orders</code>\n  Instant order placement (JSON: <code>{{\"product_id\": 1, \"quantity\": 1}}</code>)\n\n"
        f"<b>3. Response:</b>\n"
        f"Upon successful order, delivered credentials or license keys are returned in the <code>credentials</code> field!\n\n"
        f"{ICON_GLOBE} <i>For full API documentation, parameter specifications, and code samples, open the web docs link below.</i>"
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

    lang = await services.users.get_language(tg_user.id)

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
            f"{t('order_history_title', lang, icon_orders=ICON_ORDERS)}\n\n"
            f"{t('order_history_empty', lang)}"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t("btn_browse_products", lang),
                        callback_data="open_categories",
                        style="success",
                        icon_custom_emoji_id=Icons.PRODUCTS,
                    ),
                ],
                [
                    InlineKeyboardButton(text=t("btn_back", lang), callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=t("btn_close", lang), callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
                ],
            ]
        )
    else:
        total_pages = max(1, math.ceil(total / ORDERS_PAGE_SIZE)) if total > 0 else 1
        page = min(page, total_pages)
        if total_pages > 1:
            text = t("order_history_page", lang, icon_orders=ICON_ORDERS, page=page, total_pages=total_pages)
        else:
            text = t("order_history_title", lang, icon_orders=ICON_ORDERS)
        buttons = []
        for order in orders:
            price_val = order["price"]
            price_str = format_dual_price(price_val, symbol, usd_rate=usd_rate, show_usd=show_usd)
            is_completed = order["status"] == "completed" and order.get("fulfillment") != "waiting"
            is_waiting = order.get("fulfillment") == "waiting" or order["status"] in {"pending", "processing", "waiting"}
            if is_completed:
                status_emoji = "✅"
                status_icon = Icons.CHECK
            elif is_waiting:
                status_emoji = "⏳"
                status_icon = Icons.TIMER
            else:
                status_emoji = "❌"
                status_icon = Icons.CROSS

            max_title_len = max(8, 54 - len(str(order['id'])) - len(price_str) - 8)
            title_short = order['product_title'][:max_title_len].strip()
            label = f"{status_emoji} #{order['id']} · {title_short} · {price_str}"
            cb_data = f"vord_{order['id']}_{page}"
            buttons.append([InlineKeyboardButton(text=label[:64], callback_data=cb_data, style="primary", icon_custom_emoji_id=status_icon)])

        if total_pages > 1:
            if page == 1:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=f"orders_page_{page}", style="success", icon_custom_emoji_id=Icons.REFRESH),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_next", lang), callback_data=f"orders_page_{page + 1}", style="primary", icon_custom_emoji_id=Icons.NEXT),
                ]
            elif page == total_pages:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_prev", lang), callback_data=f"orders_page_{page - 1}", style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=f"orders_page_{page}", style="success", icon_custom_emoji_id=Icons.REFRESH),
                ]
            else:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_prev", lang), callback_data=f"orders_page_{page - 1}", style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_next", lang), callback_data=f"orders_page_{page + 1}", style="primary", icon_custom_emoji_id=Icons.NEXT),
                ]
            buttons.append(nav_row)
        else:
            buttons.append([
                InlineKeyboardButton(text=t("btn_refresh", lang), callback_data="orders_page_1", style="success", icon_custom_emoji_id=Icons.REFRESH),
            ])

        buttons.append([
            InlineKeyboardButton(text=t("btn_browse_products", lang), callback_data="open_categories", style="success", icon_custom_emoji_id=Icons.PRODUCTS),
        ])
        buttons.append([
            InlineKeyboardButton(text=t("btn_back", lang), callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
            InlineKeyboardButton(text=t("btn_close", lang), callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
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
    if raw.startswith("vord_"):
        parts = raw.removeprefix("vord_").split("_")
        order_id = int(parts[0]) if parts and parts[0].isdigit() else None
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
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
    show_usd = await services.settings.flag("show_usd_price")

    created = order["created_at"]
    date_str = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else str(created)[:16]

    if order["status"] == "completed" and order.get("fulfillment") != "waiting":
        status_line = f"{ICON_CHECK} <b>{t('order_status', lang)}:</b> <code>{t('status_completed', lang)}</code>\n<i>{t('status_completed_msg', lang)}</i>"
    elif order.get("fulfillment") == "waiting":
        status_line = f"{ICON_TIMER} <b>{t('order_status', lang)}:</b> <code>{t('status_waiting', lang)}</code>\n<i>{t('status_waiting_msg', lang)}</i>"
    elif order["status"] in {"refunded", "cancelled"}:
        status_line = f"{ICON_CROSS} <b>{t('order_status', lang)}:</b> <code>{t('status_refunded', lang)}</code>\n<i>{t('status_refunded_msg', lang)}</i>"
    else:
        status_line = f"{ICON_TIMER} <b>{t('order_status', lang)}:</b> <code>{order['status'].upper()}</code>"

    text = (
        f"{t('order_detail_title', lang, icon_orders=ICON_ORDERS, id=order['id'])}\n\n"
        f"{status_line}\n\n"
        f"{ICON_VIP} <b>{t('order_product', lang)}:</b> {escape(order['product_title'])}\n"
        f"{ICON_MONEY} <b>{t('order_price_paid', lang)}:</b> <code>{price(symbol, order['price'], usd_rate=usd_rate, show_usd=show_usd)}</code>\n"
        f"{ICON_TIMER} <b>{t('order_date', lang)}:</b> <code>{date_str}</code>"
    )

    has_credentials = bool(order.get("delivered_item") and order.get("fulfillment") != "waiting")
    if has_credentials:
        text += (
            f"\n\n{ICON_KEY} <b>{t('order_credentials', lang)}:</b>\n"
            f"<code>{escape(order['delivered_item'])}</code>"
        )

    back_cb = f"orders_page_{page}" if page > 1 else "open_orders"
    detail_buttons = []

    if has_credentials:
        if len(order["delivered_item"]) <= INLINE_CREDENTIAL_LIMIT:
            detail_buttons.append([
                InlineKeyboardButton(
                    text=t("btn_copy_credentials", lang),
                    copy_text=CopyTextButton(text=order["delivered_item"]),
                    style="success",
                    icon_custom_emoji_id=Icons.KEY,
                )
            ])
        else:
            await query.message.answer_document(BufferedInputFile(order["delivered_item"].encode(), filename=f"order-{order_id}.txt"))

    detail_buttons.append([
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=back_cb,
            style="primary",
            icon_custom_emoji_id=Icons.BACK,
        ),
        InlineKeyboardButton(
            text=t("btn_close", lang),
            callback_data="close_menu",
            style="danger",
            icon_custom_emoji_id=Icons.CLOSE,
        ),
    ])

    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=detail_buttons))


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
}))
@router.message(F.text.casefold() == "balance history")
@router.message(F.text.casefold() == "deposit history")
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
    show_usd = await services.settings.flag("show_usd_price")
    back_cb = f"back_to_dep_req_{dep_id_ref}" if dep_id_ref else "back_to_main"

    if not deposits:
        text = (
            f"{t('balance_history_title', lang, icon_stats=ICON_STATS)}\n\n"
            f"{t('balance_history_empty', lang)}"
        )
        buttons = []
        if not dep_id_ref:
            buttons.append([
                InlineKeyboardButton(text=t("btn_add_balance", lang), callback_data="open_deposit_from_history", style="success", icon_custom_emoji_id=Icons.DEPOSIT),
            ])
        buttons.append([
            InlineKeyboardButton(text=t("btn_back", lang), callback_data=back_cb, style="primary", icon_custom_emoji_id=Icons.BACK),
            InlineKeyboardButton(text=t("btn_close", lang), callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
        ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    else:
        if total_pages > 1:
            header = t("balance_history_page", lang, icon_stats=ICON_STATS, page=page, total_pages=total_pages)
        else:
            header = t("balance_history_title", lang, icon_stats=ICON_STATS)

        def page_cb(p: int) -> str:
            return f"dep_page_{p}_{dep_id_ref}" if dep_id_ref else f"dep_page_{p}"

        items_text = []
        for deposit in deposits:
            price_str = format_dual_price(deposit["amount"], symbol, usd_rate=usd_rate, show_usd=show_usd)
            method = deposit["method_name"].strip()
            trx_id = (deposit.get("transaction_id") or "").strip()
            created = deposit["created_at"]
            date_str = created.strftime("%d.%m.%y, %H:%M") if isinstance(created, datetime) else str(created)[:16]

            if deposit["status"] == "approved":
                status_emoji = "✅"
                status_label = t("status_approved", lang)
            elif deposit["status"] == "pending":
                status_emoji = "⏳"
                status_label = t("status_pending", lang)
            else:
                status_emoji = "❌"
                status_label = t("status_rejected", lang)

            lines = [
                f"<b>{escape(method)}</b> (<code>#{deposit['id']}</code>)",
                f"{status_emoji} <b>{t('order_status', lang)}:</b> {status_label} · <code>{price_str}</code>",
            ]
            if trx_id:
                lines.append(f"{ICON_KEY} <b>{t('deposit_trxid', lang)}:</b> <code>{escape(trx_id)}</code>")
            if deposit.get("admin_note"):
                lines.append(f"{ICON_NOTE} <b>{t('deposit_admin_note', lang)}:</b> <i>{escape(deposit['admin_note'])}</i>")
            lines.append(f"{ICON_TIMER} <b>{t('order_date', lang)}:</b> <code>{date_str}</code>")

            items_text.append("\n".join(lines))

        text = f"{header}\n\n" + "\n\n".join(items_text)
        buttons = []

        if total_pages > 1:
            if page == 1:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=page_cb(page), style="success", icon_custom_emoji_id=Icons.REFRESH),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_next", lang), callback_data=page_cb(page + 1), style="primary", icon_custom_emoji_id=Icons.NEXT),
                ]
            elif page == total_pages:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_prev", lang), callback_data=page_cb(page - 1), style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=page_cb(page), style="success", icon_custom_emoji_id=Icons.REFRESH),
                ]
            else:
                nav_row = [
                    InlineKeyboardButton(text=t("btn_prev", lang), callback_data=page_cb(page - 1), style="primary", icon_custom_emoji_id=Icons.BACK),
                    InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                    InlineKeyboardButton(text=t("btn_next", lang), callback_data=page_cb(page + 1), style="primary", icon_custom_emoji_id=Icons.NEXT),
                ]
            buttons.append(nav_row)
        else:
            buttons.append([
                InlineKeyboardButton(text=t("btn_refresh", lang), callback_data=page_cb(1), style="success", icon_custom_emoji_id=Icons.REFRESH),
            ])

        if not dep_id_ref:
            buttons.append([
                InlineKeyboardButton(text=t("btn_add_balance", lang), callback_data="open_deposit_from_history", style="success", icon_custom_emoji_id=Icons.DEPOSIT),
            ])
        buttons.append([
            InlineKeyboardButton(text=t("btn_back", lang), callback_data=back_cb, style="primary", icon_custom_emoji_id=Icons.BACK),
            InlineKeyboardButton(text=t("btn_close", lang), callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
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
    show_usd = await services.settings.flag("show_usd_price")

    amount_str = format_dual_price(deposit["amount"], symbol, usd_rate=usd_rate, show_usd=show_usd)
    created = deposit["created_at"]
    date_str = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else str(created)[:16]

    if deposit["status"] == "approved":
        status_line = f"{ICON_CHECK} <b>{t('order_status', lang)}:</b> <code>{t('status_approved', lang)}</code>\n<i>{t('status_approved_msg', lang)}</i>"
    elif deposit["status"] == "rejected":
        status_line = f"{ICON_CROSS} <b>{t('order_status', lang)}:</b> <code>{t('status_rejected', lang)}</code>\n<i>{t('status_rejected_msg', lang)}</i>"
        if deposit.get("admin_note"):
            status_line += f"\n{ICON_NOTE} <b>{t('deposit_admin_note', lang)}:</b> <i>{escape(deposit['admin_note'])}</i>"
    else:
        status_line = f"{ICON_TIMER} <b>{t('order_status', lang)}:</b> <code>{t('status_pending', lang)}</code>\n<i>{t('status_pending_msg', lang)}</i>"

    text = (
        f"{t('deposit_detail_title', lang, icon_stats=ICON_STATS, id=deposit['id'])}\n\n"
        f"{status_line}\n\n"
        f"{ICON_BALANCE} <b>{t('deposit_amount', lang)}:</b> <code>{amount_str}</code>\n"
        f"{ICON_ACCOUNT} <b>{t('deposit_method', lang)}:</b> {escape(deposit['method_name'])}\n"
        f"{ICON_KEY} <b>{t('deposit_trxid', lang)}:</b> <code>{escape(deposit['transaction_id'])}</code>\n"
        f"{ICON_TIMER} <b>{t('deposit_submitted_at', lang)}:</b> <code>{date_str}</code>"
    )

    if deposit.get("reviewed_at"):
        rev = deposit["reviewed_at"]
        rev_str = rev.strftime("%Y-%m-%d %H:%M") if isinstance(rev, datetime) else str(rev)[:16]
        rev_icon = ICON_CHECK if deposit["status"] == "approved" else ICON_CROSS
        text += f"\n{rev_icon} <b>{t('deposit_reviewed_at', lang)}:</b> <code>{rev_str}</code>"

    back_to_history_cb = f"dep_page_{page}_{dep_id_ref}" if dep_id_ref else f"dep_page_{page}"

    detail_buttons = []
    trx_id = (deposit.get("transaction_id") or "").strip()
    if trx_id:
        detail_buttons.append([
            InlineKeyboardButton(
                text=t("btn_copy_trxid", lang),
                copy_text=CopyTextButton(text=trx_id),
                style="primary",
                icon_custom_emoji_id=Icons.KEY,
            )
        ])

    if deposit["status"] == "rejected":
        detail_buttons.append([
            InlineKeyboardButton(
                text=t("btn_add_balance", lang),
                callback_data="open_deposit_from_history",
                style="success",
                icon_custom_emoji_id=Icons.DEPOSIT,
            )
        ])

    detail_buttons.append([
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=back_to_history_cb,
            style="primary",
            icon_custom_emoji_id=Icons.BACK,
        ),
        InlineKeyboardButton(
            text=t("btn_close", lang),
            callback_data="close_menu",
            style="danger",
            icon_custom_emoji_id=Icons.CLOSE,
        ),
    ])

    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=detail_buttons))



