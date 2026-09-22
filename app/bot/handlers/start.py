from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from app.bot.formatting import send_operator_html
from app.bot.handlers.search import forget_search_origin
from app.bot.handlers.shop import product_view
from app.bot.icons import (
    ICON_LOCK,
    ICON_SPARKLES,
    ICON_WARNING,
)
from app.bot.keyboards import (
    get_gate_keyboard,
    get_persistent_reply_keyboard,
)
from app.services import Services

logger = logging.getLogger("app.bot.start")


def build_welcome_text(store_name: str, support_handle: str, custom_text: str = "", paused_notice: str = "") -> str:
    prefix = f"{ICON_WARNING} <b>Maintenance Notice:</b> {escape(paused_notice)}\n\n" if paused_notice else ""
    if custom_text:
        formatted = (
            custom_text
            .replace("{store_name}", escape(store_name))
            .replace("[Store Name]", escape(store_name))
            .replace("{store}", escape(store_name))
        )
        return prefix + formatted
    # One line, because the console promises one line and the keyboard is already on
    # screen: the tagline said nothing about this shop and the pointer named buttons
    # the customer can see. Anyone who wants more writes their own in Settings.
    default_text = f"{ICON_SPARKLES} Welcome to <b>{escape(store_name)}</b>!"
    return prefix + default_text


router = Router(name="start_router")


async def render_main_dashboard(message: Message, services: Services, tg_user_id: int, edit: bool = False) -> None:
    """The welcome screen — clean text message with NO image, only persistent reply keyboard."""
    values = await services.settings.values()
    store_name = values.get("store_name", "Premium Haven")
    support_handle = values.get("support_username", "")
    custom_welcome = values.get("welcome_text", "").strip()
    paused_notice = await services.settings.paused_message()

    text = build_welcome_text(store_name, support_handle, custom_welcome, paused_notice)
    pinned_categories = await services.catalog.pinned_categories(active_only=True)
    unpinned_categories = await services.catalog.unpinned_categories(active_only=True)

    user = await services.users.get(tg_user_id)
    is_reseller = (user.get("rank") or "").strip().lower() == "reseller" if user else False

    reply_kb = get_persistent_reply_keyboard(
        pinned_categories=pinned_categories,
        has_unpinned=bool(unpinned_categories),
        is_reseller=is_reseller,
        is_admin=tg_user_id in await services.settings.admin_chat_ids(),
    )

    if edit and message:
        with suppress(TelegramBadRequest):
            await message.delete()

    await send_operator_html(message.answer, text, reply_markup=reply_kb)


def gate_text(missing: list[dict[str, Any]]) -> str:
    titles = "\n".join(f"• <b>{escape(ch.get('title') or ch.get('channel_username') or 'Official Channel')}</b>" for ch in missing)
    return (
        f"{ICON_LOCK} <b>Access Required: Join Our Channel(s)</b>\n\n"
        f"To access <b>Premium Haven</b> and explore our services, please join our official Telegram channel(s) below:\n\n"
        f"{titles}\n\n"
        f"<i>Tap the button(s) below to join, then click <b>Joined</b> to unlock the bot!</i>"
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
    return None


@router.message(CommandStart())
@router.message(Command("menu"))
async def handle_start(message: Message, state: FSMContext, services: Services):
    await state.clear()
    tg_user = message.from_user
    if not tg_user:
        return
    ref_id = referral_parameter(message.text)
    product_id = start_parameter(message.text)
    # The membership check does not need the profile row, so both run at once.
    _, (passed, missing) = await asyncio.gather(
        services.users.sync_profile(tg_user.id, tg_user.username, tg_user.first_name, tg_user.last_name, referred_by=ref_id),
        services.gate.check(tg_user.id),
    )
    if not passed:
        await message.answer(gate_text(missing), reply_markup=get_gate_keyboard(missing))
        return

    # User passed gate directly (or no gate channels configured): process pending referral reward
    await services.users.process_referral_reward(tg_user.id)

    # Opened from an announcement button: show that product directly.
    if product_id:
        product = await services.catalog.product(product_id)
        if product and product["is_active"]:
            forget_search_origin(tg_user.id, product["id"])
            text, keyboard = await product_view(services, product, tg_user.id)
            await message.answer(text, reply_markup=keyboard)
            return

    # Render main welcome banner directly with persistent reply keyboard attached (no inline buttons)
    await render_main_dashboard(message, services, tg_user.id)


@router.callback_query(F.data == "gate_verify")
async def handle_gate_verify(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    passed, _ = await services.gate.check(query.from_user.id)
    if not passed:
        with suppress(TelegramBadRequest):
            await query.answer("⚠️ You haven't joined all required channels yet!", show_alert=True)
        return

    # User verified channel join: award referral bonus to referrer
    await services.users.process_referral_reward(query.from_user.id)

    with suppress(TelegramBadRequest):
        await query.answer("✅ Verified successfully!")
    if query.message:
        await render_main_dashboard(query.message, services, query.from_user.id, edit=True)


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
    if status not in ("left", "kicked"):
        return
    user_id = event.new_chat_member.user.id
    if not await services.gate.guards(event.chat.id, event.chat.username):
        return
    services.gate.forget(user_id)
    logger.info("Gate: user %s left channel %s; cached membership dropped", user_id, event.chat.id)


@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await render_main_dashboard(query.message, services, query.from_user.id, edit=True)
