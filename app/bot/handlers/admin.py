"""Admin bot commands: broadcast, broadcast status, and admin quick utilities."""

from __future__ import annotations

import html
import logging
import re
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_CHANNEL,
    ICON_CHECK,
    ICON_CROSS,
    ICON_CROWN,
    ICON_ID,
    ICON_NOTE,
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
                    text="Send Now",
                    callback_data="bc_confirm",
                    style="success",
                    icon_custom_emoji_id=Icons.ROCKET,
                ),
                InlineKeyboardButton(
                    text="Cancel",
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
        await message.answer(f"{ICON_WARNING} No active recipients found.")
        await state.clear()
        return

    await state.set_state(BroadcastStates.confirming)
    await state.update_data(broadcast_text=text, recipient_count=recipients)

    preview_body = (
        f"{ICON_CHANNEL} <b>Broadcast Preview</b>\n\n"
        f"{text}\n\n"
        f"{ICON_ACCOUNT} Recipients: <b>{recipients}</b>"
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
        f"{ICON_NOTE} <b>Send Broadcast Message</b>\n\n"
        f"Type or forward the message you want to broadcast.\n"
        f"<i>HTML formatting (bold, italic, links) is supported.</i>\n\n"
        f"Send /cancel to abort."
    )


@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_input(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(f"{ICON_CROSS} Broadcast cancelled.")
        return

    text = message.html_text or message.caption or message.text
    if not text or not text.strip():
        await message.answer(f"{ICON_WARNING} Please send a text message or type /cancel.")
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
        await query.answer("Session expired.", show_alert=True)
        await state.clear()
        return

    await query.answer("Processing...")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(f"{ICON_TIMER} <b>Queuing broadcast...</b>")

    try:
        result = await services.delivery.enqueue_broadcast(broadcast_text)
        await state.clear()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(
                    f"{ICON_CHECK} <b>Broadcast Queued</b>\n\n"
                    f"{ICON_ID} Job ID: <code>#{result['id']}</code>\n"
                    f"{ICON_ACCOUNT} Recipients: <b>{result['total']}</b>\n\n"
                    f"<i>Check progress with /bcstatus</i>"
                )
    except Exception as e:
        logger.exception("Failed to enqueue broadcast from Telegram: %s", e)
        await state.clear()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(f"{ICON_CROSS} Failed: {html.escape(str(e))}")


@router.callback_query(F.data == "bc_cancel")
async def handle_bc_cancel(query: CallbackQuery, state: FSMContext, services: Services):
    if not query.from_user or not await _is_admin(query.from_user.id, services):
        await query.answer("Access denied.", show_alert=True)
        return

    await state.clear()
    await query.answer("Cancelled.")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(f"{ICON_CROSS} Broadcast cancelled.")


@router.message(Command("bcstatus", "broadcast_status"))
async def cmd_broadcast_status(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    recent = await services.delivery.recent_broadcasts(limit=1)
    if not recent:
        await message.answer(f"{ICON_WARNING} No broadcast history found.")
        return

    latest = recent[0]
    snippet = latest["text"][:120] + "..." if len(latest["text"]) > 120 else latest["text"]

    is_pending = latest["pending"] > 0
    status_icon = ICON_TIMER if is_pending else ICON_CHECK
    status_title = "Sending" if is_pending else "Completed"
    await message.answer(
        f"{status_icon} <b>Broadcast #{latest['id']} · {status_title}</b>\n\n"
        f"<i>{html.escape(snippet)}</i>\n\n"
        f"{ICON_ACCOUNT} Total: <b>{latest['total']}</b>\n"
        f"{ICON_CHECK} Delivered: <b>{latest['success']}</b>\n"
        f"{ICON_CROSS} Failed: <b>{latest['failed']}</b>\n"
        f"{ICON_TIMER} Pending: <b>{latest['pending']}</b>"
    )


@router.message(Command("admin"))
async def cmd_admin_help(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    recipients = await services.delivery.recipient_count()
    await message.answer(
        f"{ICON_CROWN} <b>Admin Commands</b>\n"
        f"{ICON_ACCOUNT} Active Recipients: <b>{recipients}</b>\n\n"
        f"• <code>/bc &lt;message&gt;</code> — Quick broadcast\n"
        f"• <code>/bc</code> — Interactive composer\n"
        f"• Reply to message with <code>/bc</code> — Forward & send\n"
        f"• <code>/bcstatus</code> — Check latest delivery status\n"
        f"• <code>/cancel</code> — Cancel active action"
    )


@router.my_chat_member()
async def on_bot_chat_member_updated(event: ChatMemberUpdated, services: Services, bot: Bot):
    """
    Security check: when bot is added to a group or channel,
    verify authorization. If added to an unauthorized group by a non-admin,
    the bot automatically leaves the chat and alerts admins.
    """
    new_status = event.new_chat_member.status
    if new_status not in ("member", "administrator"):
        return

    chat = event.chat
    if chat.type == "private":
        return

    values = await services.settings.values()
    admin_ids = await services.settings.admin_chat_ids()
    actor_id = event.from_user.id if event.from_user else 0
    is_actor_admin = actor_id in admin_ids

    authorized_chats = set()
    for key in ("order_notification_group", "announcement_channel"):
        raw = values.get(key, "")
        for part in re.split(r"[\s,;]+", raw):
            p = part.strip()
            if p:
                authorized_chats.add(p.lower())
                if p.startswith("@"):
                    authorized_chats.add(p[1:].lower())
                try:
                    authorized_chats.add(str(int(p)))
                except ValueError:
                    pass

    chat_id_str = str(chat.id)
    chat_user = (chat.username or "").lower()

    is_authorized = (
        is_actor_admin
        or chat_id_str in authorized_chats
        or (chat_user and chat_user in authorized_chats)
    )

    if not is_authorized:
        logger.warning(
            "Security: Bot added to unauthorized chat '%s' (ID: %s) by user %s. Leaving.",
            chat.title, chat.id, actor_id
        )
        with suppress(Exception):
            await bot.leave_chat(chat.id)
        # Alert admins of unauthorized addition
        await services.notifier.send_admin(
            f"🛡️ <b>Security Alert: Unauthorized Group</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"The bot was added to an unauthorized group:\n"
            f"• <b>Title:</b> {html.escape(chat.title or 'Unknown')}\n"
            f"• <b>Chat ID:</b> <code>{chat.id}</code>\n"
            f"• <b>Added By:</b> <code>{actor_id}</code>\n\n"
            f"<i>The bot automatically left the group to protect store data.</i>"
        )
        return

    # If this is the authorized order notification group, announce readiness
    order_groups_raw = values.get("order_notification_group", "")
    order_groups = [g.strip().lower() for g in re.split(r"[\s,;]+", order_groups_raw) if g.strip()]
    if chat.type in ("group", "supergroup") and (chat_id_str in order_groups or (chat_user and chat_user in order_groups)):
        with suppress(Exception):
            await bot.send_message(
                chat.id,
                f"✅ <b>Order Notification Group Connected</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Real-time order receipts and delivery alerts will be delivered here."
            )
