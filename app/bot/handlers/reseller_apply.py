"""Interactive multi-step application flow for users applying to become a Reseller."""

from __future__ import annotations

from contextlib import suppress
import html
import logging
import re
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.icons import (
    ICON_CHECK,
    ICON_CROSS,
    ICON_NOTE,
    ICON_RESELLER,
    ICON_WARNING,
    Icons,
)
from app.services import Services

logger = logging.getLogger("app.bot.handlers.reseller_apply")
router = Router(name="reseller_apply")


class ResellerApplyStates(StatesGroup):
    waiting_name = State()
    waiting_telegram = State()
    waiting_phone = State()
    waiting_channel = State()
    confirm = State()


def validate_name(val: str) -> tuple[bool, str]:
    """Validate applicant's name: letters, 2-70 chars, not numbers/spam."""
    clean = re.sub(r"\s+", " ", val or "").strip()
    if len(clean) < 2:
        return False, "Name is too short. Please enter at least 2 characters."
    if len(clean) > 70:
        return False, "Name is too long. Please keep it under 70 characters."
    # Must have at least 2 alphabetic characters (Latin, Bengali, etc.)
    letter_count = sum(1 for c in clean if c.isalpha())
    if letter_count < 2:
        return False, "Please enter a valid real name containing letters."
    # Reject if it's mostly digits or punctuation
    if sum(1 for c in clean if c.isdigit()) > 2:
        return False, "Please enter your real name without numbers."
    return True, clean


def validate_telegram(val: str) -> tuple[bool, str]:
    """Validate and normalize Telegram handle or ID."""
    clean = (val or "").strip()
    # Strip t.me link prefixes
    clean = re.sub(r"^https?://(www\.)?t\.me/", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^t\.me/", "", clean, flags=re.IGNORECASE)
    clean = clean.lstrip("@").strip()

    if not clean:
        return False, "Please provide your Telegram username or ID."
    # If numeric Telegram ID
    if clean.isdigit() and len(clean) >= 5:
        return True, f"ID: {clean}"
    # If username: alphanumeric + underscore, 3-40 chars
    if re.fullmatch(r"[A-Za-z0-9_]{3,40}", clean):
        return True, f"@{clean}"
    return False, "Invalid username. Please enter a valid username (e.g. @username) or ID."


def validate_phone(val: str) -> tuple[bool, str]:
    """Validate phone or WhatsApp number: 10-16 digits."""
    raw = (val or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 16:
        return False, "Please enter a valid phone number (10 to 15 digits, e.g. 017XXXXXXXX)."
    # Check if dummy repeated digit
    if len(set(digits)) <= 2:
        return False, "Please enter your real, active contact number."
    # Re-add + if user provided international format
    if raw.startswith("+"):
        formatted = f"+{digits}"
    elif digits.startswith("880"):
        formatted = f"+{digits}"
    else:
        formatted = digits
    return True, formatted


def validate_channel(val: str) -> tuple[bool, str]:
    """Validate and normalize Telegram channel, Facebook page, or website link."""
    clean = (val or "").strip()
    if len(clean) < 3 or len(clean) > 250:
        return False, "Please enter a valid channel link or username (between 3 and 250 characters)."

    # If it's a telegram handle e.g. @mychannel or t.me/mychannel
    if clean.startswith("@"):
        uname = clean.lstrip("@")
        if re.fullmatch(r"[A-Za-z0-9_]{3,50}", uname):
            return True, f"https://t.me/{uname}"
    if clean.lower().startswith("t.me/"):
        return True, f"https://{clean}"

    # If it's a Facebook page or profile
    if re.search(r"^(https?://)?(www\.)?(facebook\.com|fb\.me|fb\.com)/", clean, re.IGNORECASE):
        if not clean.lower().startswith("http"):
            clean = f"https://{clean}"
        return True, clean

    # If it's any http/https URL
    if clean.lower().startswith("http://") or clean.lower().startswith("https://"):
        if "." in clean and len(clean) >= 10:
            return True, clean
        return False, "Please provide a valid active link URL."

    # If user provided domain like mypage.com or facebook.com/shop
    if "." in clean and "/" in clean and not any(c in clean for c in (" ", "\n", "\t")):
        return True, f"https://{clean}"

    # If single word without spaces, assume Telegram channel handle
    if re.fullmatch(r"[A-Za-z0-9_]{3,50}", clean):
        return True, f"https://t.me/{clean}"

    return False, "Could not recognize the link. Please provide a link (e.g. t.me/channel, facebook.com/page, or website)."


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Cancel Application",
                    callback_data="reseller_cancel_apply",
                    style="danger",
                )
            ]
        ]
    )


@router.callback_query(F.data == "reseller_start_apply")
async def start_reseller_apply(query: CallbackQuery, state: FSMContext, services: Services):
    """Start the interactive 4-step Reseller Application flow."""
    tg_user = query.from_user
    if not tg_user:
        return
    await state.clear()
    await state.set_state(ResellerApplyStates.waiting_name)

    text = (
        f"{ICON_RESELLER} <b>Become a Reseller (Step 1/4)</b>\n\n"
        f"Please enter your <b>Full Name</b>:\n\n"
        f"<i>(Type your real name below and send)</i>"
    )
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=cancel_keyboard())


@router.callback_query(F.data == "reseller_cancel_apply")
async def cancel_reseller_apply(query: CallbackQuery, state: FSMContext, services: Services):
    """Cancel the active application flow."""
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer("Application cancelled.")
    # Show main reseller info menu
    from app.bot.handlers.profile import show_reseller_hub
    await show_reseller_hub(query, state, services)


@router.callback_query(F.data == "reseller_cancel_pending")
async def cancel_pending_application(query: CallbackQuery, state: FSMContext, services: Services):
    """Cancel user's existing pending application."""
    tg_user = query.from_user
    if not tg_user:
        return
    pending = await services.reseller_applications.get_pending_by_user(tg_user.id)
    if pending:
        await services.reseller_applications.cancel_application(pending["id"], tg_user.id)
        with suppress(TelegramBadRequest):
            await query.answer("Your application has been withdrawn.")
    else:
        with suppress(TelegramBadRequest):
            await query.answer("No pending application found.")
    from app.bot.handlers.profile import show_reseller_hub
    await show_reseller_hub(query, state, services)


@router.message(ResellerApplyStates.waiting_name)
async def process_name_step(message: Message, state: FSMContext):
    """Handle Step 1: Full Name input."""
    raw = (message.text or "").strip()
    is_valid, result = validate_name(raw)
    if not is_valid:
        await message.reply(
            f"❌ <b>Invalid Name</b>\n\n{result}\n\n<i>Please enter your real full name:</i>",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(full_name=result)
    await state.set_state(ResellerApplyStates.waiting_telegram)

    user_username = f"@{message.from_user.username}" if message.from_user and message.from_user.username else ""
    quick_btn = []
    if user_username:
        quick_btn.append([
            InlineKeyboardButton(
                text=f"Use Current Username ({user_username})",
                callback_data=f"reseller_use_current_tg",
            )
        ])
    quick_btn.append([
        InlineKeyboardButton(
            text="❌ Cancel Application",
            callback_data="reseller_cancel_apply",
            style="danger",
        )
    ])

    await message.reply(
        f"✅ <b>Name saved:</b> <code>{html.escape(result)}</code>\n\n"
        f"{ICON_RESELLER} <b>Step 2/4: Telegram Username or ID</b>\n\n"
        f"Please enter your Telegram handle (e.g. <code>@username</code> or <code>username</code>):\n"
        f"<i>(If you don't have a username, send your Telegram ID)</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=quick_btn),
    )


@router.callback_query(F.data == "reseller_use_current_tg", ResellerApplyStates.waiting_telegram)
async def use_current_telegram(query: CallbackQuery, state: FSMContext):
    """Quick button to use the user's current Telegram handle."""
    tg_user = query.from_user
    handle = f"@{tg_user.username}" if tg_user and tg_user.username else f"ID: {tg_user.id if tg_user else '0'}"
    await state.update_data(telegram_handle=handle)
    await state.set_state(ResellerApplyStates.waiting_phone)
    with suppress(TelegramBadRequest):
        await query.answer()

    text = (
        f"✅ <b>Telegram handle saved:</b> <code>{html.escape(handle)}</code>\n\n"
        f"{ICON_RESELLER} <b>Step 3/4: Contact Phone / WhatsApp Number</b>\n\n"
        f"Please enter your active mobile or WhatsApp number:\n"
        f"<i>(e.g. 017XXXXXXXX or +88017XXXXXXXX)</i>"
    )
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=cancel_keyboard())


@router.message(ResellerApplyStates.waiting_telegram)
async def process_telegram_step(message: Message, state: FSMContext):
    """Handle Step 2: Telegram handle input."""
    raw = (message.text or "").strip()
    is_valid, result = validate_telegram(raw)
    if not is_valid:
        await message.reply(
            f"❌ <b>Invalid Handle</b>\n\n{result}\n\n<i>Please enter a valid Telegram username or numeric ID:</i>",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(telegram_handle=result)
    await state.set_state(ResellerApplyStates.waiting_phone)

    await message.reply(
        f"✅ <b>Telegram handle saved:</b> <code>{html.escape(result)}</code>\n\n"
        f"{ICON_RESELLER} <b>Step 3/4: Contact Phone / WhatsApp Number</b>\n\n"
        f"Please enter your active mobile or WhatsApp number:\n"
        f"<i>(e.g. 017XXXXXXXX or +88017XXXXXXXX)</i>",
        reply_markup=cancel_keyboard(),
    )


@router.message(ResellerApplyStates.waiting_phone)
async def process_phone_step(message: Message, state: FSMContext):
    """Handle Step 3: Phone number input."""
    raw = (message.text or "").strip()
    is_valid, result = validate_phone(raw)
    if not is_valid:
        await message.reply(
            f"❌ <b>Invalid Phone Number</b>\n\n{result}\n\n<i>Please enter your 10 to 15 digit active number:</i>",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(phone_number=result)
    await state.set_state(ResellerApplyStates.waiting_channel)

    await message.reply(
        f"✅ <b>Phone number saved:</b> <code>{html.escape(result)}</code>\n\n"
        f"{ICON_RESELLER} <b>Step 4/4: Channel / Store / Page Link</b>\n\n"
        f"Please enter the link to your Telegram channel, Facebook page, or online store:\n"
        f"<i>(Examples: <code>https://t.me/yourchannel</code>, <code>@yourchannel</code>, or <code>https://facebook.com/yourpage</code>)</i>",
        reply_markup=cancel_keyboard(),
    )


@router.message(ResellerApplyStates.waiting_channel)
async def process_channel_step(message: Message, state: FSMContext):
    """Handle Step 4: Channel link input and show confirmation summary."""
    raw = (message.text or "").strip()
    is_valid, result = validate_channel(raw)
    if not is_valid:
        await message.reply(
            f"❌ <b>Invalid Channel Link</b>\n\n{result}\n\n<i>Please provide a valid channel link, username, or page URL:</i>",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(channel_link=result)
    await state.set_state(ResellerApplyStates.confirm)
    data = await state.get_data()

    text = (
        f"📋 <b>Review Your Reseller Application</b>\n\n"
        f"👤 <b>Full Name:</b> <code>{html.escape(data.get('full_name', ''))}</code>\n"
        f"✈️ <b>Telegram:</b> <code>{html.escape(data.get('telegram_handle', ''))}</code>\n"
        f"📱 <b>Phone / WhatsApp:</b> <code>{html.escape(data.get('phone_number', ''))}</code>\n"
        f"📢 <b>Channel / Store:</b> <code>{html.escape(data.get('channel_link', ''))}</code>\n\n"
        f"<i>Please verify the information above. If everything is accurate, tap <b>Submit Application</b>.</i>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Submit Application",
                    callback_data="reseller_submit_confirm",
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Edit Info",
                    callback_data="reseller_start_apply",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="reseller_cancel_apply",
                    style="danger",
                ),
            ],
        ]
    )
    await message.reply(text, reply_markup=keyboard)


@router.callback_query(F.data == "reseller_submit_confirm", ResellerApplyStates.confirm)
async def process_submit_confirmation(query: CallbackQuery, state: FSMContext, services: Services):
    """Finalize submission: save application in database and notify administrators."""
    tg_user = query.from_user
    if not tg_user:
        return

    data = await state.get_data()
    full_name = data.get("full_name", "").strip()
    telegram_handle = data.get("telegram_handle", "").strip()
    phone_number = data.get("phone_number", "").strip()
    channel_link = data.get("channel_link", "").strip()

    if not (full_name and telegram_handle and phone_number and channel_link):
        with suppress(TelegramBadRequest):
            await query.answer("Some information was missing. Please fill the form again.", show_alert=True)
        await state.clear()
        return

    user_row = await services.users.get(tg_user.id)
    if not user_row:
        with suppress(TelegramBadRequest):
            await query.answer("User profile not found. Please send /start first.", show_alert=True)
        await state.clear()
        return

    # Save application in DB
    app_id = await services.reseller_applications.create_application(
        user_id=user_row["id"],
        tg_user_id=tg_user.id,
        full_name=full_name,
        telegram_handle=telegram_handle,
        phone_number=phone_number,
        channel_link=channel_link,
    )
    await state.clear()

    with suppress(TelegramBadRequest):
        await query.answer("Application submitted successfully!", show_alert=True)

    # 1. Update user view
    user_confirm_text = (
        f"{ICON_CHECK} <b>Reseller Application Submitted!</b>\n\n"
        f"Your application (<b>#{app_id}</b>) has been received and is now pending review by our management team.\n\n"
        f"👤 <b>Name:</b> {html.escape(full_name)}\n"
        f"✈️ <b>Handle:</b> {html.escape(telegram_handle)}\n"
        f"📱 <b>Phone:</b> <code>{html.escape(phone_number)}</code>\n"
        f"📢 <b>Channel:</b> {html.escape(channel_link)}\n\n"
        f"⏳ <i>You will receive an automated Telegram alert once your application is approved.</i>"
    )
    nav_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data="back_to_main",
                )
            ]
        ]
    )
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(user_confirm_text, reply_markup=nav_kb)

    # 2. Notify Administrators on Telegram
    admin_alert_text = (
        f"💼 <b>New Reseller Application!</b>\n\n"
        f"🆔 <b>Application ID:</b> #{app_id}\n"
        f"👤 <b>Name:</b> {html.escape(full_name)}\n"
        f"✈️ <b>Telegram:</b> {html.escape(telegram_handle)} (ID: <code>{tg_user.id}</code>)\n"
        f"📱 <b>Phone:</b> <code>{html.escape(phone_number)}</code>\n"
        f"📢 <b>Channel / Store:</b> {html.escape(channel_link)}\n\n"
        f"👉 <i>Review and choose an action below or via Admin Dashboard:</i>"
    )
    admin_actions_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approve",
                    callback_data=f"adm_appr_res_{app_id}",
                    style="success",
                ),
                InlineKeyboardButton(
                    text="❌ Reject",
                    callback_data=f"adm_rej_res_{app_id}",
                    style="danger",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Admin Panel",
                    callback_data="adm_dashboard",
                )
            ],
        ]
    )
    admin_chat_ids = await services.settings.admin_chat_ids()
    for admin_id in admin_chat_ids:
        await services.notifier.send_message(admin_id, admin_alert_text, reply_markup=admin_actions_kb)
