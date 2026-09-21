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


class WelcomeStates(StatesGroup):
    waiting_for_welcome = State()


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
        f"• <code>/setwelcome &lt;text&gt;</code> — Set custom welcome message\n"
        f"• <code>/resetwelcome</code> — Reset welcome message to default\n"
        f"• <code>/cancel</code> — Cancel active action"
    )


@router.message(Command("resetwelcome"))
async def cmd_reset_welcome(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    try:
        await services.settings.update({"welcome_text": ""})
    except Exception as e:
        logger.exception("Failed to reset welcome_text: %s", e)
        await message.answer(f"{ICON_CROSS} Failed to reset: {html.escape(str(e))}")
        return

    values = await services.settings.values()
    store_name = values.get("store_name", "Premium Haven")
    await message.answer(
        f"{ICON_CHECK} <b>Welcome message reset to default!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Default greeting:</b>\n"
        f"Welcome to <b>{html.escape(store_name)}</b>!\n\n"
        f"💡 <i>This is now active for all users and updated in the console.</i>"
    )


@router.message(Command("setwelcome", "welcome"))
async def cmd_set_welcome(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    # Check if replying to an existing message
    if message.reply_to_message:
        reply = message.reply_to_message
        text = reply.html_text or reply.caption or reply.text
        if text and text.strip():
            await _save_welcome_text(message, text.strip(), services)
            await state.clear()
            return

    # Check if arguments provided directly: e.g. /setwelcome Welcome to our shop!
    full_html = message.html_text or message.text or ""
    parts = full_html.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        arg_text = parts[1].strip()
        if arg_text.lower() in ("reset", "default", "clear"):
            await cmd_reset_welcome(message, services)
            await state.clear()
            return
        await _save_welcome_text(message, arg_text, services)
        await state.clear()
        return

    # Prompt interactive composer
    values = await services.settings.values()
    current_welcome = values.get("welcome_text", "").strip()
    store_name = values.get("store_name", "Premium Haven")

    await state.set_state(WelcomeStates.waiting_for_welcome)
    status_hint = (
        f"<b>Current Custom Message:</b>\n<blockquote>{html.escape(current_welcome)}</blockquote>\n\n"
        if current_welcome
        else f"<b>Current Status:</b> <i>Using default ('Welcome to {html.escape(store_name)}')</i>\n\n"
    )

    await message.answer(
        f"{ICON_NOTE} <b>Set Welcome Message</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{status_hint}"
        f"Send the new greeting message you want customers to see on /start.\n\n"
        f"• HTML formatting (bold, italic, links) is supported.\n"
        f"• Use <code>{{store_name}}</code> to automatically insert the store name.\n"
        f"• Send <code>reset</code> or <code>default</code> to restore default greeting.\n"
        f"• Send /cancel to abort."
    )


@router.message(WelcomeStates.waiting_for_welcome)
async def process_welcome_input(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
        await state.clear()
        await message.answer(f"{ICON_CROSS} Cancelled.")
        return

    if message.text and message.text.strip().lower() in ("reset", "default", "clear"):
        await cmd_reset_welcome(message, services)
        await state.clear()
        return

    text = message.html_text or message.caption or message.text
    if not text or not text.strip():
        await message.answer(f"{ICON_WARNING} Please send a text message or send /cancel.")
        return

    await _save_welcome_text(message, text.strip(), services)
    await state.clear()


async def _save_welcome_text(message: Message, text: str, services: Services):
    values = await services.settings.values()
    store_name = values.get("store_name", "Premium Haven")

    try:
        await services.settings.update({"welcome_text": text})
    except Exception as e:
        logger.exception("Failed to update welcome_text from Telegram: %s", e)
        await message.answer(f"{ICON_CROSS} Failed to update: {html.escape(str(e))}")
        return

    preview_display = (
        text.replace("{store_name}", html.escape(store_name))
        .replace("[Store Name]", html.escape(store_name))
        .replace("{store}", html.escape(store_name))
    )

    await message.answer(
        f"{ICON_CHECK} <b>Welcome message updated successfully!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Preview:</b>\n"
        f"{preview_display}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>This is now active for all users and updated in the console.</i>\n"
        f"<i>(To reset to default anytime, send <code>/resetwelcome</code>)</i>"
    )


@router.my_chat_member()
async def on_bot_chat_member_updated(event: ChatMemberUpdated, services: Services, bot: Bot):
    """
    Security check: when bot is added to a group or channel, verify authorization.
    1. Groups / Supergroups: The bot NEVER operates in groups.
       If added to any group, it immediately leaves without responding or posting anything,
       and alerts the store admin.
    2. Channels: The bot only operates in explicitly configured announcement
       or gate channels. If added to an unauthorized channel, it leaves
       immediately without posting, and alerts the store admin.
    """
    new_status = event.new_chat_member.status
    if new_status not in ("member", "administrator"):
        return

    chat = event.chat
    if chat.type == "private":
        return

    actor_id = event.from_user.id if event.from_user else 0

    # 1. GROUP / SUPERGROUP: Always leave immediately. No exceptions.
    if chat.type in ("group", "supergroup"):
        logger.warning(
            "Security: Bot added to group '%s' (ID: %s) by user %s. Leaving immediately.",
            chat.title, chat.id, actor_id
        )
        with suppress(Exception):
            await bot.leave_chat(chat.id)

        # Alert store admins of unauthorized addition
        await services.notifier.send_admin(
            f"🛡️ <b>Security Alert: Group Invite Rejected</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"The bot was added to a group:\n"
            f"• <b>Title:</b> {html.escape(chat.title or 'Unknown')}\n"
            f"• <b>Chat ID:</b> <code>{chat.id}</code>\n"
            f"• <b>Added By:</b> <code>{actor_id}</code>\n\n"
            f"<i>Groups are completely disabled. The bot automatically left without responding.</i>"
        )
        return

    # 2. CHANNEL: Only allow explicitly authorized announcement or gate channels.
    if chat.type == "channel":
        values = await services.settings.values()
        admin_ids = await services.settings.admin_chat_ids()
        is_actor_admin = actor_id in admin_ids

        authorized_chats = set()

        # Announcement channels from settings
        raw_announcements = values.get("announcement_channel", "")
        for part in re.split(r"[\s,;]+", raw_announcements):
            p = part.strip()
            if p:
                authorized_chats.add(p.lower())
                if p.startswith("@"):
                    authorized_chats.add(p[1:].lower())
                try:
                    authorized_chats.add(str(int(p)))
                except ValueError:
                    pass

        # Gate channels (force-join channels)
        try:
            gate_list = await services.gate.channels(active_only=False)
            for g in gate_list:
                uname = (g.get("channel_username") or "").strip().lower()
                if uname:
                    authorized_chats.add(uname)
                    if uname.startswith("@"):
                        authorized_chats.add(uname[1:])
                cid = str(g.get("chat_id") or "").strip()
                if cid:
                    authorized_chats.add(cid)
        except Exception:
            logger.exception("Failed to load gate channels for chat authorization check")

        chat_id_str = str(chat.id)
        chat_user = (chat.username or "").lower()

        is_authorized = (
            chat_id_str in authorized_chats
            or (chat_user and (chat_user in authorized_chats or f"@{chat_user}" in authorized_chats))
            or (is_actor_admin and not authorized_chats)  # admin adding bot before saving config
        )

        if not is_authorized:
            logger.warning(
                "Security: Bot added to unauthorized channel '%s' (ID: %s) by user %s. Leaving.",
                chat.title, chat.id, actor_id
            )
            with suppress(Exception):
                await bot.leave_chat(chat.id)

            await services.notifier.send_admin(
                f"🛡️ <b>Security Alert: Unauthorized Channel</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"The bot was added to an unauthorized channel:\n"
                f"• <b>Title:</b> {html.escape(chat.title or 'Unknown')}\n"
                f"• <b>Channel ID:</b> <code>{chat.id}</code>\n"
                f"• <b>Username:</b> @{chat_user or 'None'}\n"
                f"• <b>Added By:</b> <code>{actor_id}</code>\n\n"
                f"<i>The bot automatically left the channel to prevent unauthorized broadcasts.</i>"
            )
            return

        logger.info(
            "Bot successfully added to authorized channel '%s' (ID: %s).",
            chat.title, chat.id
        )
