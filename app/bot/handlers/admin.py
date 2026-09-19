"""Admin bot commands: broadcast, broadcast status, and admin quick utilities."""

from __future__ import annotations

import html
import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_CHANNEL,
    ICON_CHECK,
    ICON_CROSS,
    ICON_CROWN,
    ICON_ID,
    ICON_NOTE,
    ICON_ROCKET,
    ICON_TIMER,
    ICON_WARNING,
    Icons,
)
from app.services import Services

logger = logging.getLogger("app.bot.admin")

router = Router()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    confirming = State()


async def _is_admin(user_id: int, services: Services) -> bool:
    admin_ids = await services.settings.admin_chat_ids()
    return user_id in admin_ids


def _build_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="পাঠান",
                    callback_data="bc_confirm",
                    style="success",
                    icon_custom_emoji_id=Icons.ROCKET,
                ),
                InlineKeyboardButton(
                    text="বাতিল",
                    callback_data="bc_cancel",
                    style="danger",
                    icon_custom_emoji_id=Icons.CLOSE,
                ),
            ]
        ]
    )


async def _show_preview(message: Message, text: str, services: Services, state: FSMContext) -> None:
    recipients = await services.delivery.recipient_count()
    if recipients == 0:
        await message.answer(f"{ICON_WARNING} কোনো অ্যাক্টিভ কাস্টমার নেই।")
        await state.clear()
        return

    await state.set_state(BroadcastStates.confirming)
    await state.update_data(broadcast_text=text, recipient_count=recipients)

    preview_body = (
        f"{ICON_CHANNEL} <b>ব্রডকাস্ট প্রিভিউ</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_ACCOUNT} প্রাপক: <code>{recipients}</code> জন"
    )

    await message.answer(preview_body, reply_markup=_build_preview_keyboard(), disable_web_page_preview=True)


@router.message(Command("broadcast", "bc"))
async def cmd_broadcast(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    # Check if replying to an existing message
    if message.reply_to_message:
        reply = message.reply_to_message
        text = reply.html_text or reply.caption or reply.text
        if text:
            await _show_preview(message, text, services, state)
            return

    # Check if text provided directly: e.g. /broadcast Hello
    full_html = message.html_text or message.text or ""
    parts = full_html.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        broadcast_text = parts[1].strip()
        await _show_preview(message, broadcast_text, services, state)
        return

    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer(
        f"{ICON_NOTE} <b>ব্রডকাস্ট মেসেজটি লিখুন:</b>\n"
        f"<i>(বাতিল করতে /cancel লিখুন)</i>"
    )


@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_input(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(f"{ICON_CROSS} <b>ব্রডকাস্ট বাতিল করা হয়েছে</b>")
        return

    text = message.html_text or message.caption or message.text
    if not text or not text.strip():
        await message.answer(f"{ICON_WARNING} টেক্সট মেসেজ পাঠান অথবা /cancel লিখুন।")
        return

    await _show_preview(message, text.strip(), services, state)


@router.callback_query(F.data == "bc_confirm")
async def handle_bc_confirm(query: CallbackQuery, state: FSMContext, services: Services):
    if not query.from_user or not await _is_admin(query.from_user.id, services):
        await query.answer("Access denied.", show_alert=True)
        return

    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")
    if not broadcast_text:
        await query.answer("সেশনের মেয়াদ শেষ হয়েছে।", show_alert=True)
        await state.clear()
        return

    await query.answer("শুরু হচ্ছে...")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(f"{ICON_TIMER} <b>ব্রডকাস্ট প্রসেস হচ্ছে...</b>")

    try:
        result = await services.delivery.enqueue_broadcast(broadcast_text)
        await state.clear()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(
                    f"{ICON_CHECK} <b>ব্রডকাস্ট শুরু হয়েছে</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"{ICON_ID} আইডি: <code>#{result['id']}</code>\n"
                    f"{ICON_ACCOUNT} প্রাপক: <code>{result['total']}</code> জন\n\n"
                    f"<i>প্রগ্রেস দেখতে /bcstatus লিখুন</i>"
                )
    except Exception as e:
        logger.exception("Failed to enqueue broadcast from Telegram: %s", e)
        await state.clear()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(f"{ICON_CROSS} ব্যর্থ হয়েছে: {html.escape(str(e))}")


@router.callback_query(F.data == "bc_cancel")
async def handle_bc_cancel(query: CallbackQuery, state: FSMContext, services: Services):
    if not query.from_user or not await _is_admin(query.from_user.id, services):
        await query.answer("Access denied.", show_alert=True)
        return

    await state.clear()
    await query.answer("বাতিল করা হয়েছে।")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(f"{ICON_CROSS} <b>ব্রডকাস্ট বাতিল করা হয়েছে</b>")


@router.message(Command("bcstatus", "broadcast_status"))
async def cmd_broadcast_status(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    recent = await services.delivery.recent_broadcasts(limit=1)
    if not recent:
        await message.answer(f"{ICON_WARNING} কোনো ব্রডকাস্ট হিস্ট্রি নেই।")
        return

    latest = recent[0]
    snippet = latest["text"][:100] + "..." if len(latest["text"]) > 100 else latest["text"]

    is_pending = latest["pending"] > 0
    status_icon = ICON_TIMER if is_pending else ICON_CHECK
    status_title = "চলমান" if is_pending else "সম্পন্ন"
    await message.answer(
        f"{status_icon} <b>ব্রডকাস্ট #{latest['id']} ({status_title})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>{html.escape(snippet)}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_ACCOUNT} মোট: <code>{latest['total']}</code> | {ICON_CHECK} সফল: <code>{latest['success']}</code>\n"
        f"{ICON_CROSS} ব্যর্থ: <code>{latest['failed']}</code> | {ICON_TIMER} বাকি: <code>{latest['pending']}</code>"
    )


@router.message(Command("admin"))
async def cmd_admin_help(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    recipients = await services.delivery.recipient_count()
    await message.answer(
        f"{ICON_CROWN} <b>ব্রডকাস্ট কন্ট্রোল</b>\n"
        f"{ICON_ACCOUNT} প্রাপক: <code>{recipients}</code> জন\n\n"
        f"• <code>/bc &lt;মেসেজ&gt;</code> — সরাসরি পাঠান\n"
        f"• <code>/bc</code> — মেসেজ ইনপুট দিন\n"
        f"• মেসেজে রিপ্লাই করে <code>/bc</code> — ফরোয়ার্ড\n"
        f"• <code>/bcstatus</code> — প্রগ্রেস রিপোর্ট\n"
        f"• <code>/cancel</code> — বাতিল"
    )
