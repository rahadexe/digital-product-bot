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
                InlineKeyboardButton(text="🚀 ব্রডকাস্ট পাঠান (Send)", callback_data="bc_confirm"),
                InlineKeyboardButton(text="❌ বাতিল (Cancel)", callback_data="bc_cancel"),
            ]
        ]
    )


async def _show_preview(message: Message, text: str, services: Services, state: FSMContext) -> None:
    recipients = await services.delivery.recipient_count()
    if recipients == 0:
        await message.answer("⚠️ আপনার বটে বর্তমানে কোনো অ্যাক্টিভ কাস্টমার নেই।")
        await state.clear()
        return

    # Keep broadcast text in FSM state
    await state.set_state(BroadcastStates.confirming)
    await state.update_data(broadcast_text=text, recipient_count=recipients)

    preview_body = (
        f"📢 <b>ব্রডকাস্ট প্রিভিউ (Broadcast Preview):</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>মোট প্রাপক:</b> <code>{recipients}</code> জন গ্রাহক\n\n"
        f"⚠️ <i>আপনি কি নিশ্চিত যে এই মেসেজটি সকল গ্রাহকের কাছে পাঠাতে চান?</i>"
    )

    await message.answer(preview_body, reply_markup=_build_preview_keyboard(), disable_web_page_preview=True)


@router.message(Command("broadcast", "bc"))
async def cmd_broadcast(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    # Check if this command is replying to an existing message
    if message.reply_to_message:
        reply = message.reply_to_message
        text = reply.html_text or reply.caption or reply.text
        if text:
            await _show_preview(message, text, services, state)
            return

    # Check if text was provided directly with the command: e.g. /broadcast Hello
    full_html = message.html_text or message.text or ""
    parts = full_html.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        broadcast_text = parts[1].strip()
        await _show_preview(message, broadcast_text, services, state)
        return

    # Otherwise, enter waiting state
    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer(
        "✍️ <b>ব্রডকাস্ট মেসেজটি লিখুন:</b>\n\n"
        "যে মেসেজটি আপনি সকল কাস্টমারকে পাঠাতে চান তা এখানে লিখে পাঠান।\n"
        "💡 <i>টেলিগ্রাম ফরম্যাটিং (Bold, Italic, Code, Links) এবং কাস্টম ইমোজি সমর্থিত।</i>\n\n"
        "বাতিল করতে /cancel পাঠান।"
    )


@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_input(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer("❌ ব্রডকাস্ট বাতিল করা হয়েছে।")
        return

    text = message.html_text or message.caption or message.text
    if not text or not text.strip():
        await message.answer("⚠️ অনুগ্রহ করে একটি টেক্সট মেসেজ পাঠান।")
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
        await query.answer("সেশনটি মেয়াদোত্তীর্ণ হয়েছে। আবার চেষ্টা করুন।", show_alert=True)
        await state.clear()
        return

    await query.answer("ব্রডকাস্ট শুরু হচ্ছে...")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                "⏳ <b>ব্রডকাস্ট প্রসেসিং শুরু হয়েছে...</b>\n\n"
                "কাস্টমারদের কাছে মেসেজ পাঠানোর জন্য কিউতে যুক্ত করা হচ্ছে..."
            )

    try:
        result = await services.delivery.enqueue_broadcast(broadcast_text)
        await state.clear()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(
                    f"✅ <b>ব্রডকাস্ট সফলভাবে কিউতে যুক্ত হয়েছে!</b>\n\n"
                    f"🆔 <b>জব আইডি:</b> <code>#{result['id']}</code>\n"
                    f"👥 <b>মোট কাস্টমার:</b> <code>{result['total']}</code> জন\n"
                    f"📨 ব্যাকগ্রাউন্ড ডেলিভারি শুরু হয়েছে। ডেলিভারি প্রগ্রেস দেখতে /bcstatus লিখুন।"
                )
    except Exception as e:
        logger.exception("Failed to enqueue broadcast from Telegram: %s", e)
        await state.clear()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(f"❌ ব্রডকাস্ট ব্যর্থ হয়েছে: {html.escape(str(e))}")


@router.callback_query(F.data == "bc_cancel")
async def handle_bc_cancel(query: CallbackQuery, state: FSMContext, services: Services):
    if not query.from_user or not await _is_admin(query.from_user.id, services):
        await query.answer("Access denied.", show_alert=True)
        return

    await state.clear()
    await query.answer("বাতিল করা হয়েছে।")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text("❌ <b>ব্রডকাস্ট বাতিল করা হয়েছে।</b>")


@router.message(Command("bcstatus", "broadcast_status"))
async def cmd_broadcast_status(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    recent = await services.delivery.recent_broadcasts(limit=1)
    if not recent:
        await message.answer("ℹ️ সাম্প্রতিক কোনো ব্রডকাস্ট পাওয়া যায়নি।")
        return

    latest = recent[0]
    snippet = latest['text'][:120] + "..." if len(latest['text']) > 120 else latest['text']

    status_icon = "⏳" if latest['pending'] > 0 else "✅"
    await message.answer(
        f"{status_icon} <b>সর্বশেষ ব্রডকাস্ট রিপোর্ট (#{latest['id']}):</b>\n\n"
        f"📝 <b>মেসেজ:</b> <i>{html.escape(snippet)}</i>\n\n"
        f"👥 <b>মোট প্রাপক:</b> <code>{latest['total']}</code>\n"
        f"✅ <b>সফলভাবে পৌঁছেছে:</b> <code>{latest['success']}</code>\n"
        f"❌ <b>ব্যর্থ (ব্লকড):</b> <code>{latest['failed']}</code>\n"
        f"⏳ <b>বাকি আছে (Pending):</b> <code>{latest['pending']}</code>"
    )


@router.message(Command("admin"))
async def cmd_admin_help(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    recipients = await services.delivery.recipient_count()
    await message.answer(
        f"👑 <b>অ্যাডমিন কন্ট্রোল প্যানেল (Telegram):</b>\n\n"
        f"👥 <b>মোট অ্যাক্টিভ কাস্টমার:</b> <code>{recipients}</code> জন\n\n"
        f"📌 <b>ব্রডকাস্ট কমান্ডসমূহ:</b>\n"
        f"• <code>/broadcast &lt;মেসেজ&gt;</code> - সরাসরি সকল কাস্টমারকে ব্রডকাস্ট পাঠান\n"
        f"• <code>/bc</code> - ইন্টারঅ্যাক্টিভভাবে ব্রডকাস্ট মেসেজ ইনপুট দিন\n"
        f"• কোনো মেসেজে রিপ্লাই করে <code>/bc</code> - সেই মেসেজটি সরাসরি ব্রডকাস্ট করুন\n"
        f"• <code>/bcstatus</code> - সর্বশেষ ব্রডকাস্টের ডেলিভারি রিপোর্ট দেখুন\n"
        f"• <code>/cancel</code> - চলমান অপারেশন বাতিল করুন\n\n"
        f"🌐 <i>ওয়েব অ্যাডমিন কনসোলেও পূর্ণ নিয়ন্ত্রণ ও লাইভ হিস্ট্রি রয়েছে।</i>"
    )
