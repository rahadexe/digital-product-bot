"""Admin bot commands: broadcast, broadcast status, and admin quick utilities."""

from __future__ import annotations

import html
import logging
import re
import time
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

    raw_text = (message.text or "").strip()
    if raw_text.startswith("/"):
        cmd = raw_text.split()[0].lower().lstrip("/")
        if cmd in ("cancel",):
            await state.clear()
            await message.answer(f"{ICON_CROSS} Broadcast cancelled.")
            return

        if cmd in ("start",):
            await state.clear()
            from app.bot.handlers.start import render_main_dashboard
            await render_main_dashboard(message, services, message.from_user.id)
            return

        if cmd in ("admin",):
            await state.clear()
            await cmd_admin_help(message, services)
            return

        if cmd in ("broadcast", "bc"):
            await state.clear()
            await cmd_broadcast(message, state, services)
            return

        if cmd in ("setwelcome", "welcome", "sw"):
            await state.clear()
            await cmd_set_welcome(message, state, services)
            return

        if cmd in ("resetwelcome", "rw"):
            await state.clear()
            await cmd_reset_welcome(message, services)
            return

        await message.answer(
            f"{ICON_WARNING} <b>Invalid input:</b> Bot commands cannot be broadcast.\n\n"
            f"Please send the message you want to broadcast, or send /cancel to abort."
        )
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
        f"• <code>/sw &lt;text&gt;</code> (or <code>/setwelcome</code>) — Set custom welcome message\n"
        f"• <code>/rw</code> (or <code>/resetwelcome</code>) — Reset welcome message to default\n"
        f"\n<b>While you are away from the desk</b>\n"
        f"• <code>/status</code> (or <code>/st</code>) — What needs you, today's takings, low stock\n"
        f"• <code>/pause</code> · <code>/resume</code> — Stop and restart selling\n"
        f"• <code>/find &lt;id or @username&gt;</code> — A customer, with a ban button\n"
        f"• Deposit alerts carry <b>Approve</b> and <b>Reject</b>\n"
        f"• Manual order alerts carry <b>Deliver here</b>\n"
        f"\n• <code>/cancel</code> — Cancel active action"
    )


@router.message(Command("resetwelcome", "rw"))
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


@router.message(Command("setwelcome", "welcome", "sw"))
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

    raw_text = (message.text or "").strip()

    # Reset keywords
    if raw_text.lower() in ("reset", "default", "clear"):
        await state.clear()
        await cmd_reset_welcome(message, services)
        return

    # Intercept commands typed while waiting for welcome input
    if raw_text.startswith("/"):
        cmd = raw_text.split()[0].lower().lstrip("/")
        if cmd in ("cancel",):
            await state.clear()
            await message.answer(f"{ICON_CROSS} Cancelled.")
            return

        if cmd in ("resetwelcome", "rw"):
            await state.clear()
            await cmd_reset_welcome(message, services)
            return

        if cmd in ("start",):
            await state.clear()
            from app.bot.handlers.start import render_main_dashboard
            await render_main_dashboard(message, services, message.from_user.id)
            return

        if cmd in ("admin",):
            await state.clear()
            await cmd_admin_help(message, services)
            return

        if cmd in ("setwelcome", "welcome", "sw"):
            await state.clear()
            await cmd_set_welcome(message, state, services)
            return

        if cmd in ("broadcast", "bc"):
            await state.clear()
            await cmd_broadcast(message, state, services)
            return

        if cmd in ("bcstatus", "broadcast_status"):
            await state.clear()
            await cmd_broadcast_status(message, services)
            return

        await message.answer(
            f"{ICON_WARNING} <b>Invalid input:</b> Bot commands (like <code>{html.escape(raw_text)}</code>) cannot be saved as the welcome message.\n\n"
            f"Please send your custom greeting text, or send /cancel to abort."
        )
        return

    text = message.html_text or message.caption or message.text
    if not text or not text.strip():
        await message.answer(f"{ICON_WARNING} Please send a text message or send /cancel.")
        return

    await _save_welcome_text(message, text.strip(), services)
    await state.clear()


async def _save_welcome_text(message: Message, text: str, services: Services):
    clean_text = text.strip()
    if clean_text.startswith("/"):
        await message.answer(
            f"{ICON_CROSS} <b>Error:</b> Bot commands (like <code>{html.escape(clean_text)}</code>) cannot be saved as the welcome message.\n\n"
            f"Please send your custom greeting text without a leading slash, or use /resetwelcome to restore the default."
        )
        return

    values = await services.settings.values()
    store_name = values.get("store_name", "Premium Haven")

    try:
        await services.settings.update({"welcome_text": clean_text})
    except Exception as e:
        logger.exception("Failed to update welcome_text from Telegram: %s", e)
        await message.answer(f"{ICON_CROSS} Failed to update: {html.escape(str(e))}")
        return

    preview_display = (
        clean_text.replace("{store_name}", html.escape(store_name))
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


async def _alert_once(services: Services, scope: str, key: str, text: str) -> None:
    """Send a security alert, but not the same one over and over.

    Adding the bot to a group is something anyone can do, repeatedly, and every
    attempt used to reach the owner's Telegram. One alert per chat per hour says
    the same thing without handing a stranger a way to flood the owner.
    """
    try:
        if await services.rate_limits.consume(f"security-alert:{scope}", key, 1, 3600):
            return
    except Exception:
        logger.exception("Could not check the security alert budget; sending anyway")
    await services.notifier.send_admin(text)


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
            f"<i>Groups are completely disabled. The bot automatically left without responding.</i>",
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
                f"<i>The bot automatically left the channel to prevent unauthorized broadcasts.</i>",
            )
            return

        logger.info(
            "Bot successfully added to authorized channel '%s' (ID: %s).",
            chat.title, chat.id
        )


# ── Acting on an alert where the alert arrives ──────────────────────────────
# A notification that can only offer a link to the console is a notification
# that costs the operator a browser and a login before a waiting customer is
# served. These handlers do the work in the chat the alert landed in.
#
# Callback filters are exact patterns, not startswith: the first handler whose
# filter matches a callback is the one that runs, and a prefix that is also the
# start of another callback silently swallows it.


class AdminOpsStates(StatesGroup):
    waiting_for_delivery = State()


# How long a "send the credentials" prompt stays live before it stops listening.
DELIVERY_PROMPT_SECONDS = 30 * 60


async def _deny(query: CallbackQuery, services: Services) -> bool:
    """True when this tap did not come from an administrator."""
    if query.from_user and await _is_admin(query.from_user.id, services):
        return False
    with suppress(TelegramBadRequest):
        await query.answer("This is for administrators.", show_alert=True)
    return True


def _confirm_keyboard(yes_data: str, label: str, danger: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=label,
                callback_data=yes_data,
                style="danger" if danger else "success",
                icon_custom_emoji_id=Icons.CROSS if danger else Icons.CONFIRM,
            ),
            InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="primary", icon_custom_emoji_id=Icons.BACK),
        ]]
    )


@router.callback_query(F.data == "adm_cancel")
async def adm_cancel(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer("Cancelled.")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_reply_markup(reply_markup=None)


async def _deposit_summary(services: Services, deposit_id: int) -> dict | None:
    async with services.db.connect() as conn:
        row = await conn.fetchrow(
            "SELECT d.*, u.username FROM deposits d LEFT JOIN users u ON u.id = d.user_id WHERE d.id = $1",
            deposit_id,
        )
    return dict(row) if row else None


@router.callback_query(F.data.regexp(r"^adm_dep_ask_(approve|reject)_\d+$"))
async def adm_deposit_ask(query: CallbackQuery, services: Services):
    """Crediting a wallet is money in. Say what is about to happen first."""
    if await _deny(query, services):
        return
    action, raw_id = query.data.removeprefix("adm_dep_ask_").split("_", 1)
    deposit = await _deposit_summary(services, int(raw_id))
    if not deposit:
        with suppress(TelegramBadRequest):
            await query.answer("That deposit no longer exists.", show_alert=True)
        return
    if deposit["status"] != "pending":
        with suppress(TelegramBadRequest):
            await query.answer(f"Already {deposit['status']}.", show_alert=True)
        return

    symbol = html.escape(await services.settings.get("currency_symbol"))
    who = f"@{html.escape(deposit['username'])}" if deposit.get("username") else f"<code>{deposit['tg_user_id']}</code>"
    amount = f"{float(deposit['amount']):.2f} {symbol}"
    if action == "approve":
        text = (
            f"{ICON_WARNING} <b>Credit this wallet?</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> {who}\n"
            f"{ICON_NOTE} <b>Amount:</b> <code>{amount}</code>\n"
            f"{ICON_ID} <b>Transaction:</b> <code>{html.escape(str(deposit['transaction_id']))}</code>\n\n"
            f"<i>Check the money actually arrived before approving.</i>"
        )
        keyboard = _confirm_keyboard(f"adm_dep_do_approve_{raw_id}", f"Yes, credit {amount}")
    else:
        text = (
            f"{ICON_WARNING} <b>Reject this deposit?</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> {who}\n"
            f"{ICON_NOTE} <b>Amount:</b> <code>{amount}</code>\n\n"
            f"<i>The customer is told it could not be verified.</i>"
        )
        keyboard = _confirm_keyboard(f"adm_dep_do_reject_{raw_id}", "Yes, reject", danger=True)

    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^adm_dep_do_(approve|reject)_\d+$"))
async def adm_deposit_do(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    action, raw_id = query.data.removeprefix("adm_dep_do_").split("_", 1)
    deposit_id = int(raw_id)
    by = query.from_user.id if query.from_user else 0

    if action == "approve":
        ok, message, _ = await services.deposits.approve(deposit_id, f"Approved from Telegram by {by}")
    else:
        ok, message, _ = await services.deposits.reject(deposit_id, "Transaction could not be verified.")

    with suppress(TelegramBadRequest):
        await query.answer(message[:180], show_alert=not ok)
    if query.message:
        icon = ICON_CHECK if ok else ICON_CROSS
        verb = "Credited" if action == "approve" else "Rejected"
        line = f"{icon} <b>Deposit #{deposit_id} {verb.lower()}</b>" if ok else f"{ICON_CROSS} <b>Deposit #{deposit_id}</b>"
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{line}\n━━━━━━━━━━━━━━━━━━\n{html.escape(message)}", reply_markup=None
            )


@router.callback_query(F.data.regexp(r"^adm_ord_deliver_\d+$"))
async def adm_order_deliver(query: CallbackQuery, state: FSMContext, services: Services):
    """Manual orders are paid and waiting. Send what the customer bought here."""
    if await _deny(query, services):
        return
    order_id = int(query.data.removeprefix("adm_ord_deliver_"))
    async with services.db.connect() as conn:
        order = await conn.fetchrow("SELECT id, product_title, status, fulfillment FROM orders WHERE id = $1", order_id)
    if not order:
        with suppress(TelegramBadRequest):
            await query.answer("That order no longer exists.", show_alert=True)
        return
    if order["status"] != "completed" or order["fulfillment"] != "waiting":
        with suppress(TelegramBadRequest):
            await query.answer("Only a paid order still waiting can be delivered.", show_alert=True)
        return

    await state.set_state(AdminOpsStates.waiting_for_delivery)
    await state.update_data(deliver_order_id=order_id, deliver_asked_at=time.time())
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.answer(
                f"{ICON_NOTE} <b>Deliver order #{order_id}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ICON_CROWN} {html.escape(order['product_title'])}\n\n"
                f"Send what the customer should receive. It reaches them exactly as you type it.\n"
                f"Send /cancel to stop."
            )


@router.message(AdminOpsStates.waiting_for_delivery)
async def adm_order_deliver_send(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text = (message.text or message.caption or "").strip()
    data = await state.get_data()

    # Whatever is typed here is forwarded to a customer verbatim, so the state must not
    # outlive the moment. An owner who taps Deliver and gets distracted would otherwise
    # have their next unrelated message sent to that customer days later.
    asked_at = float(data.get("deliver_asked_at") or 0)
    if not asked_at or time.time() - asked_at > DELIVERY_PROMPT_SECONDS:
        await state.clear()
        await message.answer(
            f"{ICON_WARNING} <b>Nothing was sent</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"That delivery prompt expired, so this message was not passed on.\n"
            f"Tap <b>Deliver</b> on the order again."
        )
        return

    # A command typed here is a command, never something to deliver.
    if text.startswith("/"):
        await state.clear()
        cmd = text.split()[0].lower().lstrip("/").split("@")[0]
        if cmd == "cancel":
            await message.answer(f"{ICON_CROSS} Cancelled. The order is still waiting.")
        elif cmd in ("status", "st"):
            await cmd_status(message, services)
        elif cmd == "admin":
            await cmd_admin_help(message, services)
        else:
            await message.answer(
                f"{ICON_WARNING} <b>Nothing was sent</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<code>{html.escape(text.split()[0])}</code> looks like a command, so it was not "
                f"delivered to the customer. Tap <b>Deliver</b> again to retry."
            )
        return
    if not text:
        await message.answer(f"{ICON_WARNING} Send the credentials as text, or /cancel.")
        return

    order_id = int(data.get("deliver_order_id") or 0)
    try:
        await services.purchases.fulfill_manually(order_id, text)
    except Exception as exc:
        await message.answer(f"{ICON_CROSS} Could not deliver: {html.escape(str(exc))}")
        return
    await state.clear()
    await message.answer(
        f"{ICON_CHECK} <b>Order #{order_id} delivered</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>The customer has it now.</i>"
    )


# ── Quick controls ──────────────────────────────────────────────────────────


@router.message(Command("status", "st"))
async def cmd_status(message: Message, services: Services):
    """The one thing worth checking while away from the desk."""
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    stats = await services.dashboard.stats()
    symbol = html.escape(await services.settings.get("currency_symbol"))
    paused = await services.settings.flag("store_paused")

    async with services.db.connect() as conn:
        pending_amount = float(await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE status = 'pending'") or 0)
        today = await conn.fetchrow(
            "SELECT COUNT(*) AS orders, COALESCE(SUM(price), 0) AS revenue FROM orders "
            "WHERE status = 'completed' AND created_at >= CURRENT_DATE")

    low = [p for p in stats.get("stock_summary", []) if int(p.get("stock") or 0) <= 2][:5]
    low_line = "\n".join(
        f"   • {html.escape(p['title'])[:34]} — <code>{int(p['stock'] or 0)}</code>" for p in low
    ) or "   • nothing running low"

    waiting = stats.get("waiting_orders", 0)
    pending = stats.get("pending_deposits", 0)
    # Only name the queue that actually has something in it; "0 deposits to review" is noise.
    jobs = [f"{pending} deposit(s) to review"] if pending else []
    if waiting:
        jobs.append(f"{waiting} order(s) to deliver")
    needs_you = ", ".join(jobs) or "nothing waiting on you"

    await message.answer(
        f"{ICON_NOTE} <b>Store status</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_WARNING if paused else ICON_CHECK} <b>Store:</b> {'PAUSED' if paused else 'open'}\n"
        f"{ICON_TIMER} <b>Needs you:</b> {needs_you}\n\n"
        f"{ICON_CHECK} <b>Today:</b> <code>{int(today['orders'] or 0)}</code> order(s), "
        f"<code>{float(today['revenue'] or 0):.2f} {symbol}</code>\n"
        f"{ICON_NOTE} <b>Pending deposits:</b> <code>{pending}</code> "
        f"(<code>{pending_amount:.2f} {symbol}</code>)\n"
        f"{ICON_CROWN} <b>All time:</b> <code>{stats.get('total_orders', 0)}</code> order(s), "
        f"<code>{float(stats.get('total_revenue') or 0):.2f} {symbol}</code>\n"
        f"{ICON_ACCOUNT} <b>Customers:</b> <code>{stats.get('total_users', 0)}</code>\n\n"
        f"{ICON_WARNING} <b>Low stock</b>\n{low_line}"
    )


@router.message(Command("pause"))
async def cmd_pause(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    await services.settings.update({"store_paused": "1"})
    notice = await services.settings.get("maintenance_message")
    await message.answer(
        f"{ICON_WARNING} <b>Store paused</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"New orders and deposits are blocked. Customers see:\n"
        f"<blockquote>{html.escape(notice)}</blockquote>\n\n"
        f"<i>Send /resume to open again.</i>"
    )


@router.message(Command("resume", "unpause"))
async def cmd_resume(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    await services.settings.update({"store_paused": "0"})
    await message.answer(
        f"{ICON_CHECK} <b>Store open</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Orders and deposits are accepted again."
    )


@router.message(Command("find", "customer"))
async def cmd_find(message: Message, services: Services):
    """Look a customer up while answering them, without opening the console."""
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    parts = (message.text or "").split(maxsplit=1)
    term = parts[1].strip() if len(parts) > 1 else ""
    if not term:
        await message.answer(f"{ICON_NOTE} Send <code>/find 100200300</code> or <code>/find @username</code>.")
        return

    async with services.db.connect() as conn:
        if term.isdigit():
            row = await conn.fetchrow("SELECT tg_user_id FROM users WHERE tg_user_id = $1", int(term))
        else:
            row = await conn.fetchrow(
                "SELECT tg_user_id FROM users WHERE lower(username) = lower($1)", term.lstrip("@"))
    if not row:
        await message.answer(f"{ICON_CROSS} No customer matches <code>{html.escape(term)}</code>.")
        return

    found = await services.users.stats(row["tg_user_id"])
    if not found:
        await message.answer(f"{ICON_CROSS} That customer's record could not be read.")
        return
    user = found["user"]
    # An administrator bypasses the ban check, so offering Ban here would look like
    # it worked and change nothing. Say so instead.
    is_admin_target = int(user["tg_user_id"]) in await services.settings.admin_chat_ids()
    symbol = html.escape(await services.settings.get("currency_symbol"))
    name = html.escape(" ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "No name")
    handle = f"@{html.escape(user['username'])}" if user.get("username") else "no username"
    await message.answer(
        f"{ICON_ACCOUNT} <b>{name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_ID} <code>{user['tg_user_id']}</code> · {handle}\n"
        f"{ICON_CROWN} <b>Rank:</b> {html.escape(user.get('rank') or 'Standard')}"
        f"{'  ·  ' + ICON_CROSS + ' <b>BANNED</b>' if user.get('is_banned') else ''}\n"
        f"{ICON_CHECK} <b>Balance:</b> <code>{float(user.get('balance') or 0):.2f} {symbol}</code>\n"
        f"{ICON_NOTE} <b>Orders:</b> <code>{found['order_count']}</code> · "
        f"<b>Spent:</b> <code>{float(found['total_spent'] or 0):.2f} {symbol}</code>"
        + (f"\n\n{ICON_CROWN} <i>This account is an administrator, so it cannot be banned. "
           f"Remove it from Administrators in the console first.</i>" if is_admin_target else ""),
        reply_markup=None if is_admin_target else InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Unban" if user.get("is_banned") else "Ban",
                callback_data=f"adm_ban_ask_{user['tg_user_id']}",
                style="success" if user.get("is_banned") else "danger",
                icon_custom_emoji_id=Icons.CHECK if user.get("is_banned") else Icons.CROSS,
            )
        ]]),
    )


@router.callback_query(F.data.regexp(r"^adm_ban_ask_\d+$"))
async def adm_ban_ask(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    tg_user_id = int(query.data.removeprefix("adm_ban_ask_"))
    user = await services.users.get(tg_user_id)
    if not user:
        with suppress(TelegramBadRequest):
            await query.answer("No such customer.", show_alert=True)
        return
    banning = not user.get("is_banned")
    verb = "Ban" if banning else "Unban"
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_reply_markup(
                reply_markup=_confirm_keyboard(f"adm_ban_do_{tg_user_id}", f"Yes, {verb.lower()}", danger=banning)
            )


@router.callback_query(F.data.regexp(r"^adm_ban_do_\d+$"))
async def adm_ban_do(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    tg_user_id = int(query.data.removeprefix("adm_ban_do_"))
    user = await services.users.get(tg_user_id)
    if not user:
        with suppress(TelegramBadRequest):
            await query.answer("No such customer.", show_alert=True)
        return
    # The card may have been sent before this account became an administrator.
    if tg_user_id in await services.settings.admin_chat_ids():
        with suppress(TelegramBadRequest):
            await query.answer("Administrators cannot be banned.", show_alert=True)
        return
    banned = await services.users.set_banned(tg_user_id, not user.get("is_banned"))
    with suppress(TelegramBadRequest):
        await query.answer("Banned." if banned else "Unbanned.")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="Unban" if banned else "Ban",
                        callback_data=f"adm_ban_ask_{tg_user_id}",
                        style="success" if banned else "danger",
                        icon_custom_emoji_id=Icons.CHECK if banned else Icons.CROSS,
                    )
                ]])
            )
