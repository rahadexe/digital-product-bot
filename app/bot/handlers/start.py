from __future__ import annotations

import asyncio
import datetime
import logging
from contextlib import suppress
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    LinkPreviewOptions,
    Message,
)

from app.bot.formatting import (
    format_dual_price,
    resolve_user_currency,
    AUTO_DELETE_ENABLED,
    _quiet_delete,
    clean_previous_menu,
    remember_menu_message,
    send_operator_html,
)
from app.bot.handlers.search import forget_search_origin
from app.bot.handlers.shop import product_view
from app.bot.icons import (
    ICON_CHANNEL,
    ICON_LOCK,
    ICON_WARNING,
)
from app.bot.keyboards import (
    get_gate_keyboard,
    get_main_inline_keyboard,
    get_persistent_reply_keyboard,
)
from app.core.i18n import t
from app.services import Services

logger = logging.getLogger("app.bot.start")


def build_welcome_text(
    *,
    paused_notice: str | None = None,
    lang: str = "en",
    balance_str: str = "",
    order_count: int = 0,
    support_username: str = "",
    currency: str = "BDT",
) -> str:
    prefix = t("maintenance_notice", lang, icon_warning=ICON_WARNING, notice=escape(paused_notice)) + "\n\n" if paused_notice else ""
    support = f"@{support_username.lstrip('@')}" if support_username else "@support"
    balance = balance_str or "$0.00"
    orders = f"Orders: <code>{order_count}</code>" if order_count else "Orders: <code>0</code>"
    curr_label = "৳ BDT" if currency == "BDT" else "$ USD"
    card = "<blockquote>" + "\n".join((
        f"💰 Balance: <code>{balance}</code>",
        f"📦 {orders}",
        f"💱 Currency: <code>{curr_label}</code>",
    )) + "</blockquote>"
    tip = "💡 <i>Switch currency & refer friends to earn in <b>👤 Account</b></i>"
    tagline = "⚡ <i>Instant Delivery · 24/7 Active</i>"
    return prefix + "\n".join(("Welcome! 🤝", "", card, "", tip, tagline, f"💬 Support: {support}"))


router = Router(name="start_router")


async def render_main_dashboard(message: Message, services: Services, tg_user_id: int, edit: bool = False) -> None:
    values, paused_notice, user, admin_ids = await asyncio.gather(
        services.settings.values(),
        services.settings.paused_message(),
        services.users.get(tg_user_id),
        services.settings.admin_chat_ids(),
    )
    lang = await services.users.get_language(tg_user_id)

    usd_rate = float(values.get("usd_rate") or 125) if isinstance(values, dict) else 125.0
    user_balance = float(user.get("balance", 0.0)) if user and isinstance(user, dict) else 0.0
    curr = await resolve_user_currency(services, tg_user_id)
    balance_str = format_dual_price(user_balance, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)
    banner_file_id = (values.get("welcome_banner_file_id") or "").strip() if isinstance(values, dict) else ""
    support_username = (values.get("support_username") or "").strip() if isinstance(values, dict) else ""
    order_count = 0
    if hasattr(services, "purchases") and hasattr(services.purchases, "customer_orders"):
        try:
            res = await services.purchases.customer_orders(tg_user_id, limit=1)
            if isinstance(res, tuple) and len(res) == 2:
                order_count = int(res[1])
        except Exception:
            order_count = 0

    text = build_welcome_text(
        paused_notice=paused_notice,
        lang=lang,
        balance_str=balance_str,
        order_count=order_count,
        support_username=support_username,
        currency=curr,
    )

    is_admin = tg_user_id in admin_ids
    is_reseller = (user.get("rank") or "").strip().lower() in {"reseller", "reseller partner"} if user and isinstance(user, dict) else False

    main_reply_kb = get_persistent_reply_keyboard(
        is_reseller=is_reseller,
        is_admin=is_admin,
        lang=lang,
        show_icons=True,
    )
    main_inline_kb = get_main_inline_keyboard(
        is_reseller=is_reseller,
        is_admin=is_admin,
        lang=lang,
        currency=curr,
    )

    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    bot = getattr(message, "bot", None)

    if edit and message:
        if getattr(message, "photo", None) and banner_file_id:
            try:
                await message.edit_caption(caption=text, reply_markup=None)
                if chat_id and message.message_id:
                    remember_menu_message(chat_id, message.message_id)
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    return
        elif not banner_file_id and not getattr(message, "photo", None):
            try:
                await message.edit_text(text, reply_markup=None)
                if chat_id and message.message_id:
                    remember_menu_message(chat_id, message.message_id)
                return
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    return

        if AUTO_DELETE_ENABLED:
            with suppress(TelegramBadRequest):
                await message.delete()

    if chat_id and bot:
        clean_previous_menu(bot, chat_id)

    sent = None
    if banner_file_id and hasattr(message, "answer_photo"):
        try:
            sent = await message.answer_photo(
                photo=banner_file_id,
                caption=text,
                reply_markup=main_reply_kb,
            )
        except Exception as exc:
            logger.warning("Could not send banner photo: %s", exc)
            sent = await send_operator_html(message.answer, text, reply_markup=main_reply_kb)
    else:
        sent = await send_operator_html(message.answer, text, reply_markup=main_reply_kb)

    if sent and chat_id:
        remember_menu_message(chat_id, sent.message_id)

    # In private chat, quietly delete the incoming command message.
    msg_id = getattr(message, "message_id", None)
    msg_text = (getattr(message, "text", "") or "").strip()
    if bot and chat_id and msg_id and getattr(chat, "type", "") == "private" and msg_text.startswith("/"):
        asyncio.create_task(_quiet_delete(bot, chat_id, msg_id))


def gate_text(missing: list[dict[str, Any]], store_name: str = "Premium Haven") -> str:
    is_single = len(missing) == 1
    channel_word = "our channel" if is_single else "our channels"
    links = []
    for ch in missing:
        title = escape(ch.get('title') or ch.get('channel_username') or 'Official Channel')
        raw_user = (ch.get('channel_username') or '').lstrip('@')
        url = ch.get("invite_link") or (f"https://t.me/{raw_user}" if raw_user else "")
        if url:
            links.append(f"{ICON_CHANNEL} <a href=\"{escape(url)}\"><b>{title}</b></a>")
        else:
            links.append(f"{ICON_CHANNEL} <b>{title}</b>")
    titles = "\n".join(links)
    notice = ("Verification is temporarily unavailable. Please try again shortly.\n\n"
              if any(ch.get("verification_unavailable") for ch in missing) else "")
    return (
        f"{ICON_LOCK} <b>Membership Required</b>\n\n"
        f"{notice}"
        f"Please join {channel_word} to continue:\n\n"
        f"{titles}\n\n"
        f"👇 <i>Join and click <b>I've Joined</b> to unlock!</i>"
    )


def start_parameter(text: str | None) -> int | None:
    """Product ID from a /start deep link (e.g. /start prod_123)."""
    parts = (text or "").split(maxsplit=1)
    param = parts[1].strip() if len(parts) > 1 else ""
    if param.startswith("prod_"):
        val = param[5:]
        if val.isdigit() and len(val) <= 18:
            return int(val)
    return None


def referral_parameter(text: str | None) -> int | None:
    """Referrer ID from a /start deep link (e.g. /start ref_123456 or /start ref123456)."""
    parts = (text or "").split(maxsplit=1)
    param = parts[1].strip() if len(parts) > 1 else ""
    if param.startswith("ref_"):
        val = param[4:]
        if val.isdigit() and len(val) <= 18:
            return int(val)
    elif param.startswith("ref"):
        val = param[3:]
        if val.isdigit() and len(val) <= 18:
            return int(val)
    elif param.isdigit() and len(param) <= 18:
        return int(param)
    return None


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, services: Services):
    await state.clear()
    tg_user = message.from_user
    if not tg_user:
        return
    ref_id = referral_parameter(message.text)
    product_id = start_parameter(message.text)
    _, (passed, missing) = await asyncio.gather(
        services.users.sync_profile(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name, referred_by=ref_id),
        services.gate.check(tg_user.id),
    )
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    bot = getattr(message, "bot", None)

    if not passed:
        errored = [ch for ch in missing if ch.get("verification_unavailable")]
        if errored:
            services.notifier.in_background(services.gate.notify_admin_channel_issue(errored, tg_user))
        store_name = await services.settings.get("store_name")
        if chat_id and bot:
            clean_previous_menu(bot, chat_id)
        sent = await message.answer(
            gate_text(missing, store_name),
            reply_markup=get_gate_keyboard(missing, product_id=product_id),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        if sent and chat_id:
            remember_menu_message(chat_id, sent.message_id)
        if bot and chat_id and getattr(chat, "type", "") == "private":
            asyncio.create_task(_quiet_delete(bot, chat_id, message.message_id))
        return

    # User passed gate directly (or no gate channels configured): process pending referral reward
    await services.users.process_referral_reward(tg_user.id)

    # Opened from an announcement button: show that product directly.
    if product_id:
        product = await services.catalog.product(product_id)
        if product and product["is_active"]:
            forget_search_origin(tg_user.id, product["id"])
            text, keyboard = await product_view(services, product, tg_user.id)
            if chat_id and bot:
                clean_previous_menu(bot, chat_id)
            sent = await message.answer(text, reply_markup=keyboard)
            if sent and chat_id:
                remember_menu_message(chat_id, sent.message_id)
            if bot and chat_id and getattr(chat, "type", "") == "private":
                asyncio.create_task(_quiet_delete(bot, chat_id, message.message_id))
            return

    # Render main welcome banner directly with keyboard attached
    await render_main_dashboard(message, services, tg_user.id)




@router.callback_query(F.data == "gate_verify")
@router.callback_query(F.data.startswith("gate_verify_prod_"))
async def handle_gate_verify(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = query.from_user
    if not tg_user:
        return
    raw_data = query.data or ""
    product_id = None
    if raw_data.startswith("gate_verify_prod_"):
        pid_str = raw_data.removeprefix("gate_verify_prod_")
        if pid_str.isdigit() and len(pid_str) <= 18:
            product_id = int(pid_str)

    passed, missing = await services.gate.check(tg_user.id)
    if not passed:
        unjoined = [c for c in missing if not c.get("verification_unavailable")]
        errored = [c for c in missing if c.get("verification_unavailable")]
        if errored:
            services.notifier.in_background(services.gate.notify_admin_channel_issue(errored, tg_user))

        if unjoined:
            with suppress(TelegramBadRequest):
                alert_msg = "Please join our channel first!" if len(unjoined) == 1 else "Please join the channels first!"
                await query.answer(f"⚠️ {alert_msg}", show_alert=True)
            return

        if errored:
            with suppress(TelegramBadRequest):
                await query.answer("Verification is temporarily unavailable. Please try again shortly.", show_alert=True)
            return

    # User verified channel join: award referral bonus to referrer
    await services.users.process_referral_reward(tg_user.id)

    with suppress(TelegramBadRequest):
        await query.answer("✅ Verified successfully!")
    if query.message:
        if product_id:
            product = await services.catalog.product(product_id)
            if product and product.get("is_active"):
                forget_search_origin(tg_user.id, product["id"])
                text, keyboard = await product_view(services, product, tg_user.id)
                with suppress(TelegramBadRequest):
                    await query.message.edit_text(text, reply_markup=keyboard)
                return
        await render_main_dashboard(query.message, services, tg_user.id, edit=True)


@router.chat_member()
async def on_gate_channel_membership_changed(event: ChatMemberUpdated, services: Services):
    """Close the gate again the moment someone leaves a channel they had to join.

    A confirmed membership is cached, because checking every channel on every update would
    mean a Telegram call for each tap. That cache is what lets someone join, walk in, leave
    and keep browsing. Telegram reports the departure straight away when the bot is an
    administrator of the channel, so this drops the cached pass and the next tap is checked
    for real. Without that admin right no report arrives and the cache is the only bound.
    """
    status = event.new_chat_member.status
    if status not in ("left", "kicked", "member", "administrator", "creator", "restricted"):
        return
    user_id = event.new_chat_member.user.id
    if not await services.gate.guards(event.chat.id, event.chat.username):
        return
    services.gate.forget(user_id)
    logger.info("Gate: user %s left channel %s; cached membership dropped", user_id, event.chat.id)


@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    if not tg_user:
        return
    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()
        if event.message:
            await render_main_dashboard(event.message, services, tg_user.id, edit=True)
    else:
        await render_main_dashboard(event, services, tg_user.id, edit=False)


@router.callback_query(F.data == "home_toggle_currency")
async def handle_home_toggle_currency(query: CallbackQuery, state: FSMContext, services: Services):
    tg_user = query.from_user
    if not tg_user:
        return
    new_curr = await services.users.toggle_currency(tg_user.id)
    with suppress(TelegramBadRequest):
        toast_msg = "Currency switched to ৳ BDT" if new_curr == "BDT" else "Currency switched to $ USD"
        await query.answer(toast_msg)
    if query.message:
        await render_main_dashboard(query.message, services, tg_user.id, edit=True)
