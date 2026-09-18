from __future__ import annotations

import asyncio
from contextlib import suppress
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.bot.formatting import price, send_operator_html
from app.bot.handlers.shop import product_view
from app.bot.icons import (
    ICON_CHANNEL,
    ICON_LOCK,
    ICON_SPARKLES,
    ICON_WARNING,
)
from app.bot.keyboards import (
    get_gate_keyboard,
    get_persistent_reply_keyboard,
)
from app.services import Services

router = Router(name="start_router")

# Telegram file_id of the uploaded welcome banner, keyed by its versioned setting value.
BANNER_FILE_IDS: dict[str, str] = {}


def build_welcome_text(store_name: str, support_handle: str, custom_text: str = "", paused_notice: str = "") -> str:
    prefix = f"{ICON_WARNING} <b>Maintenance Notice:</b> {escape(paused_notice)}\n━━━━━━━━━━━━━━━━━━\n\n" if paused_notice else ""
    if custom_text:
        return prefix + custom_text
    return prefix



async def render_main_dashboard(message: Message, services: Services, tg_user_id: int, edit: bool = False) -> None:
    """The welcome screen — photo banner and text with NO inline buttons, only persistent keyboard."""
    values = await services.settings.values()
    store_name = values.get("store_name", "Premium Haven")
    support_handle = values.get("support_username", "")
    banner_url = values.get("notice_banner", "").strip()
    custom_welcome = values.get("welcome_text", "").strip()
    paused_notice = await services.settings.paused_message()

    text = build_welcome_text(store_name, support_handle, custom_welcome, paused_notice)
    if not text:
        text = (
            f"{ICON_SPARKLES} Welcome to <b>{escape(store_name)}</b>!\n"
            f"<i>YOUR DIGITAL PREMIUM SERVICES.</i>\n\n"
            f"Please select an option from the keyboard menu below 👇"
        )
    pinned_categories = await services.catalog.pinned_categories(active_only=True)
    unpinned_categories = await services.catalog.unpinned_categories(active_only=True)
    reply_kb = get_persistent_reply_keyboard(
        pinned_categories=pinned_categories,
        has_unpinned=bool(unpinned_categories),
    )

    if edit and message:
        if message.photo:
            with suppress(TelegramBadRequest):
                await message.edit_caption(caption=text, reply_markup=None)
                return
        else:
            with suppress(TelegramBadRequest):
                await message.delete()

    # 1. An uploaded banner.
    cached_file_id = BANNER_FILE_IDS.get(banner_url)
    if cached_file_id:
        try:
            await message.answer_photo(photo=cached_file_id, caption=text, reply_markup=reply_kb)
            return
        except Exception:
            BANNER_FILE_IDS.pop(banner_url, None)

    uploaded_banner = await services.media.get_welcome_banner()
    if uploaded_banner:
        data, content_type, _w, _h, _v = uploaded_banner
        ext = "png" if "png" in content_type else "webp" if "webp" in content_type else "jpg"
        photo_file = BufferedInputFile(data, filename=f"banner.{ext}")
        try:
            sent = await message.answer_photo(
                photo=photo_file,
                caption=text,
                reply_markup=reply_kb,
            )
            if banner_url.startswith("/media/") and sent.photo:
                BANNER_FILE_IDS[banner_url] = sent.photo[-1].file_id
            return
        except Exception:
            pass

    # 2. External banner URL
    if banner_url and not banner_url.startswith("/media/") and (
        banner_url.startswith("http://") or banner_url.startswith("https://") or banner_url.startswith("AgAC")
    ):
        try:
            await message.answer_photo(
                photo=banner_url,
                caption=text,
                reply_markup=reply_kb,
            )
            return
        except Exception:
            pass

    # 3. Fallback text
    await send_operator_html(message.answer, text, reply_markup=reply_kb)


def gate_text(missing: list[dict[str, Any]]) -> str:
    titles = "\n".join(f"• <b>{escape(ch.get('title') or ch.get('channel_username') or 'Official Channel')}</b>" for ch in missing)
    return (
        f"{ICON_LOCK} <b>Access Required: Join Our Channel(s)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
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
        with suppress(TelegramBadRequest):
            await query.message.delete()
        await render_main_dashboard(query.message, services, query.from_user.id)


@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await render_main_dashboard(query.message, services, query.from_user.id, edit=True)
