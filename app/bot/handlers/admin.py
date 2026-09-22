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

from app.bot.handlers.navigation import NAVIGATION_TEXTS, is_navigation, navigate
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_CHANNEL,
    ICON_CHECK,
    ICON_CROSS,
    ICON_CROWN,
    ICON_DEPOSIT,
    ICON_ID,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_PLUS,
    ICON_SHIELD,
    ICON_SHOP,
    ICON_SPARKLES,
    ICON_STATS,
    ICON_TIMER,
    ICON_VIP,
    ICON_WARNING,
    Icons,
    tg_icon,
)
from app.services import Services

logger = logging.getLogger("app.bot.admin")

router = Router()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    confirming = State()


class WelcomeStates(StatesGroup):
    waiting_for_welcome = State()


class AdminFindStates(StatesGroup):
    waiting_for_input = State()


class AdminProductStates(StatesGroup):
    waiting_for_search = State()
    waiting_for_stock = State()
    waiting_for_name = State()
    waiting_for_price = State()


async def _is_admin(user_id: int, services: Services) -> bool:
    admin_ids = await services.settings.admin_chat_ids()
    return user_id in admin_ids


async def _deny(query: CallbackQuery, services: Services) -> bool:
    """True when this tap did not come from an administrator."""
    if query.from_user and await _is_admin(query.from_user.id, services):
        return False
    with suppress(TelegramBadRequest):
        await query.answer("This is for administrators.", show_alert=True)
    return True


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
    # A menu button is plain text, and would otherwise be composed into a broadcast.
    if raw_text in NAVIGATION_TEXTS:
        await navigate(raw_text, message, state, services)
        return
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


async def build_admin_dashboard(services: Services) -> tuple[str, InlineKeyboardMarkup]:
    recipients = await services.delivery.recipient_count()
    paused = await services.settings.flag("store_paused")
    symbol = html.escape(await services.settings.get("currency_symbol"))

    stats = await services.dashboard.stats()
    waiting = stats.get("waiting_orders", 0)
    pending = stats.get("pending_deposits", 0)

    async with services.db.connect() as conn:
        today = await conn.fetchrow(
            "SELECT COUNT(*) AS orders, COALESCE(SUM(price), 0) AS revenue FROM orders "
            "WHERE status = 'completed' AND created_at >= CURRENT_DATE"
        )

    today_orders = int(today["orders"] or 0) if today else 0
    today_rev = float(today["revenue"] or 0) if today else 0.0

    jobs = []
    if pending:
        jobs.append(f"{pending} deposit(s) to review")
    if waiting:
        jobs.append(f"{waiting} order(s) to deliver")
    needs_attention = ", ".join(jobs) or "All clear"

    store_status = "<b>PAUSED</b>" if paused else "<b>Open</b>"
    store_icon = ICON_WARNING if paused else ICON_CHECK

    text = (
        f"{ICON_CROWN} <b>Admin Control Panel</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{store_icon} <b>Store:</b> {store_status}  ·  {ICON_ACCOUNT} <b>Reach:</b> <code>{recipients}</code>\n"
        f"{ICON_TIMER} <b>Needs attention:</b> {needs_attention}\n"
        f"{ICON_CHECK} <b>Today:</b> <code>{today_orders}</code> order(s) · <code>{today_rev:.2f} {symbol}</code>\n\n"
        f"<i>Select an option below to manage the store:</i>"
    )

    pause_text = "Resume Store" if paused else "Pause Store"
    pause_icon = Icons.CHECK if paused else Icons.WARNING
    pause_style = "success" if paused else "danger"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Store Status", callback_data="adm_view_status", icon_custom_emoji_id=Icons.STATS),
            InlineKeyboardButton(text=pause_text, callback_data="adm_toggle_pause", style=pause_style, icon_custom_emoji_id=pause_icon),
        ],
        [
            InlineKeyboardButton(text="Broadcast", callback_data="adm_start_broadcast", icon_custom_emoji_id=Icons.CHANNEL),
            InlineKeyboardButton(text="BC Status", callback_data="adm_view_bcstatus", icon_custom_emoji_id=Icons.TIMER),
        ],
        [
            InlineKeyboardButton(text="Find Customer", callback_data="adm_start_find", icon_custom_emoji_id=Icons.ACCOUNT),
            InlineKeyboardButton(text="Set Welcome", callback_data="adm_start_welcome", icon_custom_emoji_id=Icons.NOTE),
        ],
        [
            InlineKeyboardButton(text="Needs you", callback_data="adm_queue", icon_custom_emoji_id=Icons.TIMER),
            InlineKeyboardButton(text="Products", callback_data="adm_start_prod", icon_custom_emoji_id=Icons.PRODUCTS),
        ],
        [
            InlineKeyboardButton(text="Re-check payments", callback_data="adm_recheck", icon_custom_emoji_id=Icons.DEPOSIT),
            InlineKeyboardButton(text="Add stock", callback_data="adm_start_stock", icon_custom_emoji_id=Icons.PLUS),
        ],
        [
            InlineKeyboardButton(text="Refresh", callback_data="adm_refresh_panel", icon_custom_emoji_id=Icons.REFRESH),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
        ],
    ])
    return text, keyboard


async def build_store_status_view(services: Services) -> tuple[str, InlineKeyboardMarkup]:
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
    jobs = [f"{pending} deposit(s) to review"] if pending else []
    if waiting:
        jobs.append(f"{waiting} order(s) to deliver")
    needs_you = ", ".join(jobs) or "nothing waiting on you"

    text = (
        f"{ICON_STATS} <b>Store Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_WARNING if paused else ICON_CHECK} <b>Store:</b> {'PAUSED' if paused else 'Open'}\n"
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
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Refresh", callback_data="adm_view_status", icon_custom_emoji_id=Icons.REFRESH),
            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
        ],
        [
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
        ]
    ])
    return text, keyboard


async def build_bcstatus_view(services: Services) -> tuple[str, InlineKeyboardMarkup]:
    recent = await services.delivery.recent_broadcasts(limit=1)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Refresh", callback_data="adm_view_bcstatus", icon_custom_emoji_id=Icons.REFRESH),
            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
        ],
        [
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
        ]
    ])

    if not recent:
        text = (
            f"{ICON_CHANNEL} <b>Broadcast Status</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"No broadcast history found."
        )
        return text, keyboard

    latest = recent[0]
    snippet = latest["text"][:120] + "..." if len(latest["text"]) > 120 else latest["text"]
    is_pending = latest["pending"] > 0
    status_icon = ICON_TIMER if is_pending else ICON_CHECK
    status_title = "Sending" if is_pending else "Completed"

    text = (
        f"{status_icon} <b>Broadcast #{latest['id']} · {status_title}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>{html.escape(snippet)}</i>\n\n"
        f"{ICON_ACCOUNT} Total: <b>{latest['total']}</b>\n"
        f"{ICON_CHECK} Delivered: <b>{latest['success']}</b>\n"
        f"{ICON_CROSS} Failed: <b>{latest['failed']}</b>\n"
        f"{ICON_TIMER} Pending: <b>{latest['pending']}</b>"
    )
    return text, keyboard


@router.message(Command("bcstatus", "broadcast_status"))
async def cmd_broadcast_status(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text, keyboard = await build_bcstatus_view(services)
    await message.answer(text, reply_markup=keyboard)


@router.message(Command("admin"))
async def cmd_admin_help(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text, keyboard = await build_admin_dashboard(services)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.in_({"adm_dashboard", "adm_refresh_panel"}))
async def adm_cb_dashboard(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    text, keyboard = await build_admin_dashboard(services)
    with suppress(TelegramBadRequest):
        await query.answer("Updated" if query.data == "adm_refresh_panel" else None)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_view_status")
async def adm_cb_view_status(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    text, keyboard = await build_store_status_view(services)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_toggle_pause")
async def adm_cb_toggle_pause(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    paused = await services.settings.flag("store_paused")
    new_val = "0" if paused else "1"
    await services.settings.update({"store_paused": new_val})
    with suppress(TelegramBadRequest):
        await query.answer("Store paused" if new_val == "1" else "Store opened")
    text, keyboard = await build_admin_dashboard(services)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_view_bcstatus")
async def adm_cb_view_bcstatus(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    text, keyboard = await build_bcstatus_view(services)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_start_broadcast")
async def adm_cb_start_broadcast(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.set_state(BroadcastStates.waiting_for_message)
    with suppress(TelegramBadRequest):
        await query.answer()
    recipients = await services.delivery.recipient_count()
    if query.message:
        await query.message.answer(
            f"{ICON_CHANNEL} <b>Broadcast Message</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Active recipients: <b>{recipients}</b>\n\n"
            f"Send the message you want to broadcast.\n"
            f"Text, photos, videos, and HTML formatting are supported.\n\n"
            f"Send /cancel to abort."
        )


@router.callback_query(F.data == "adm_start_welcome")
async def adm_cb_start_welcome(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    values = await services.settings.values()
    current_welcome = values.get("welcome_text", "").strip()
    store_name = values.get("store_name", "Premium Haven")

    await state.set_state(WelcomeStates.waiting_for_welcome)
    status_hint = (
        f"<b>Current Custom Message:</b>\n<blockquote>{html.escape(current_welcome)}</blockquote>\n\n"
        if current_welcome
        else f"<b>Current Status:</b> <i>Using default ('Welcome to {html.escape(store_name)}')</i>\n\n"
    )
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await query.message.answer(
            f"{ICON_NOTE} <b>Set Welcome Message</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{status_hint}"
            f"Send the new greeting message you want customers to see on /start.\n\n"
            f"• HTML formatting (bold, italic, links) is supported.\n"
            f"• Use <code>{{store_name}}</code> to insert the store name.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Use the default", callback_data="adm_reset_welcome",
                                     icon_custom_emoji_id=Icons.REFRESH),
                InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="danger",
                                     icon_custom_emoji_id=Icons.CLOSE),
            ]]),
        )


@router.callback_query(F.data == "adm_reset_welcome")
async def adm_cb_reset_welcome(query: CallbackQuery, state: FSMContext, services: Services):
    """The panel must be able to undo everything the panel can do."""
    if await _deny(query, services):
        return
    await state.clear()
    await services.settings.update({"welcome_text": ""})
    with suppress(TelegramBadRequest):
        await query.answer("Back to the default greeting.")
    if query.message:
        text, keyboard = await build_admin_dashboard(services)
        with suppress(TelegramBadRequest):
            await query.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_start_find")
async def adm_cb_start_find(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.set_state(AdminFindStates.waiting_for_input)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await query.message.answer(
            f"{ICON_ACCOUNT} <b>Find Customer</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Send the customer's Telegram ID (e.g. <code>100200300</code>) or username (e.g. <code>@username</code>).\n\n"
            f"Send /cancel to abort."
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
        f"{ICON_NOTE} <i>Live for every customer now, and visible in the console.</i>"
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

    # A menu button is plain text, and would otherwise be saved as the welcome message.
    if raw_text in NAVIGATION_TEXTS:
        await navigate(raw_text, message, state, services)
        return

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
        f"{ICON_NOTE} <i>Live for every customer now, and visible in the console.</i>\n"
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
        await _alert_once(
            services, "group", str(chat.id),
            f"{ICON_SHIELD} <b>Group invite rejected</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_CHANNEL} {html.escape(chat.title or 'Unknown')} · <code>{chat.id}</code>\n"
            f"{ICON_ACCOUNT} Added by <code>{actor_id}</code>\n\n"
            f"<i>The bot left. Groups are never allowed.</i>",
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
            await _alert_once(
                services, "channel", str(chat.id),
                f"{ICON_SHIELD} <b>Unauthorised channel</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ICON_CHANNEL} {html.escape(chat.title or 'Unknown')}"
                f"{' · @' + chat_user if chat_user else ''} · <code>{chat.id}</code>\n"
                f"{ICON_ACCOUNT} Added by <code>{actor_id}</code>\n\n"
                f"<i>The bot left, so nothing can be broadcast from it. Add the channel in "
                f"Settings → Channels first.</i>",
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
    cust_handle = f"@{html.escape(deposit['username'])}" if deposit.get("username") else "No username"
    amount = f"{float(deposit['amount']):.2f} {symbol}"
    if action == "approve":
        text = (
            f"{ICON_WARNING} <b>Credit this wallet?</b>\n\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> {cust_handle}\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>{deposit['tg_user_id']}</code>\n"
            f"{ICON_NOTE} <b>Amount:</b> <code>{amount}</code>\n"
            f"{ICON_ID} <b>Transaction:</b> <code>{html.escape(str(deposit['transaction_id']))}</code>\n\n"
            f"<i>Check the money actually arrived before approving.</i>"
        )
        keyboard = _confirm_keyboard(f"adm_dep_do_approve_{raw_id}", f"Yes, credit {amount}")
    else:
        text = (
            f"{ICON_WARNING} <b>Reject this deposit?</b>\n\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> {cust_handle}\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>{deposit['tg_user_id']}</code>\n"
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
    # A menu button is plain text, so without this it would be delivered to the customer
    # verbatim. Tapping one means the operator has moved on.
    if is_navigation(text):
        await navigate(text, message, state, services)
        return
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
    text, keyboard = await build_store_status_view(services)
    await message.answer(text, reply_markup=keyboard)


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


async def _handle_find_customer(message: Message, term: str, services: Services):
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


@router.message(Command("find", "customer"))
async def cmd_find(message: Message, services: Services):
    """Look a customer up while answering them, without opening the console."""
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    parts = (message.text or "").split(maxsplit=1)
    term = parts[1].strip() if len(parts) > 1 else ""
    await _handle_find_customer(message, term, services)


@router.message(AdminFindStates.waiting_for_input)
async def adm_find_input(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text = (message.text or "").strip()
    if is_navigation(text):
        await navigate(text, message, state, services)
        return
    if text.startswith("/"):
        await state.clear()
        cmd = text.split()[0].lower().lstrip("/").split("@")[0]
        if cmd == "cancel":
            await message.answer(f"{ICON_CROSS} Cancelled.")
            return
        elif cmd in ("admin",):
            await cmd_admin_help(message, services)
            return
        elif cmd in ("status", "st"):
            await cmd_status(message, services)
            return
    await state.clear()
    await _handle_find_customer(message, text, services)


# ──── The work queue ──────────────────────────────────────────────────
# The panel used to report how much was waiting without offering a way to reach it:
# the Approve and Deliver buttons lived only on the alert, so a missed alert meant
# opening the console. These turn the counts into the list they were counting.


async def build_queue_view(services: Services) -> tuple[str, InlineKeyboardMarkup]:
    symbol = html.escape(await services.settings.get("currency_symbol"))
    async with services.db.connect() as conn:
        deposits = await conn.fetch(
            "SELECT d.id, d.amount, d.transaction_id, u.username, u.tg_user_id "
            "FROM deposits d LEFT JOIN users u ON u.id = d.user_id "
            "WHERE d.status = 'pending' ORDER BY d.id LIMIT 8")
        orders = await conn.fetch(
            "SELECT o.id, o.product_title, o.price, u.username, u.tg_user_id "
            "FROM orders o LEFT JOIN users u ON u.tg_user_id = o.tg_user_id "
            "WHERE o.status = 'completed' AND o.fulfillment = 'waiting' "
            "ORDER BY o.id LIMIT 8")

    rows: list[list[InlineKeyboardButton]] = []
    lines = []
    if deposits:
        lines.append(f"{ICON_DEPOSIT} <b>Deposits to review</b>")
        for d in deposits:
            who = f"@{html.escape(d['username'])}" if d['username'] else f"<code>{d['tg_user_id']}</code>"
            lines.append(f"   #{d['id']} " + chr(0x00B7) + f" {float(d['amount']):.2f} {symbol} "
                         + chr(0x00B7) + f" {who}")
            rows.append([
                InlineKeyboardButton(text=f"Approve #{d['id']}",
                                     callback_data=f"adm_dep_ask_approve_{d['id']}",
                                     style="success", icon_custom_emoji_id=Icons.CONFIRM),
                InlineKeyboardButton(text="Reject",
                                     callback_data=f"adm_dep_ask_reject_{d['id']}",
                                     style="danger", icon_custom_emoji_id=Icons.CROSS),
            ])
    if orders:
        lines.append(f"{ICON_ORDERS} <b>Orders to deliver</b>")
        for o in orders:
            who = f"@{html.escape(o['username'])}" if o['username'] else f"<code>{o['tg_user_id']}</code>"
            lines.append(f"   #{o['id']} " + chr(0x00B7) + f" {html.escape(o['product_title'])[:28]} "
                         + chr(0x00B7) + f" {who}")
            rows.append([
                InlineKeyboardButton(text=f"Deliver #{o['id']}",
                                     callback_data=f"adm_ord_deliver_{o['id']}",
                                     style="success", icon_custom_emoji_id=Icons.ORDERS),
                InlineKeyboardButton(text="Refund",
                                     callback_data=f"adm_ord_ref_ask_{o['id']}",
                                     style="danger", icon_custom_emoji_id=Icons.SPENT),
            ])
    if not lines:
        lines.append(f"{ICON_CHECK} Nothing is waiting on you.")

    rows.append([
        InlineKeyboardButton(text="Refresh", callback_data="adm_queue", icon_custom_emoji_id=Icons.REFRESH),
        InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
    ])
    text = (f"{ICON_TIMER} <b>Needs you</b>" + chr(92) + "n"
            + chr(0x2501) * 18 + chr(92) + "n"
            + (chr(92) + "n").join(lines))
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm_queue")
async def adm_cb_queue(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    text, keyboard = await build_queue_view(services)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_recheck")
async def adm_cb_recheck(query: CallbackQuery, services: Services):
    """"I paid and nothing arrived" is the most common message an owner gets.

    This only asks the gateways again; nothing is credited that they do not confirm,
    so it is safe to press as often as the customer asks."""
    if await _deny(query, services):
        return
    with suppress(TelegramBadRequest):
        await query.answer("Asking the gateways...")
    checked = 0
    problems = []
    for name, call in (("ZiniPay", services.payments.recheck_pending),
                       ("Binance", services.binance.recheck_pending)):
        try:
            checked += int(await call() or 0)
        except Exception as exc:
            logger.exception("Re-check failed for %s", name)
            problems.append(f"{name}: {type(exc).__name__}")
    note = (chr(92) + "n") + (chr(92) + "n") + "<i>" + html.escape(", ".join(problems)) + "</i>" if problems else ""
    if query.message:
        text, keyboard = await build_queue_view(services)
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_DEPOSIT} <b>Checked {checked} unpaid invoice(s)</b>" + chr(92) + "n"
                + chr(0x2501) * 18 + chr(92) + "n"
                + "<i>Anything the gateway confirms is credited on its own.</i>" + note
                + (chr(92) + "n") + (chr(92) + "n") + text,
                reply_markup=keyboard)


# ──── Refund ──────────────────────────────────────────────────────────
# Money leaving the shop, so it asks first, the same as crediting one does.


@router.callback_query(F.data.regexp(r"^adm_ord_ref_ask_\d+$"))
async def adm_order_refund_ask(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    order_id = int(query.data.removeprefix("adm_ord_ref_ask_"))
    async with services.db.connect() as conn:
        order = await conn.fetchrow(
            "SELECT id, product_title, price, status FROM orders WHERE id = $1", order_id)
    if not order:
        with suppress(TelegramBadRequest):
            await query.answer("That order no longer exists.", show_alert=True)
        return
    symbol = html.escape(await services.settings.get("currency_symbol"))
    amount = f"{float(order['price']):.2f} {symbol}"
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_WARNING} <b>Refund order #{order_id}?</b>" + chr(92) + "n"
                + chr(0x2501) * 18 + chr(92) + "n"
                f"{ICON_VIP} {html.escape(order['product_title'])}" + chr(92) + "n"
                f"{ICON_MONEY} <code>{amount}</code>" + chr(92) + "n" + chr(92) + "n"
                "<i>The money goes back to their wallet.</i>",
                reply_markup=_confirm_keyboard(f"adm_ord_ref_do_{order_id}",
                                              f"Yes, refund {amount}", danger=True))


@router.callback_query(F.data.regexp(r"^adm_ord_ref_do_\d+$"))
async def adm_order_refund_do(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    order_id = int(query.data.removeprefix("adm_ord_ref_do_"))
    ok, message = await services.purchases.refund(order_id)
    with suppress(TelegramBadRequest):
        await query.answer(message[:180], show_alert=not ok)
    if query.message:
        icon = ICON_CHECK if ok else ICON_CROSS
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{icon} <b>Order #{order_id}</b>" + chr(92) + "n"
                + chr(0x2501) * 18 + chr(92) + "n" + html.escape(message),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Needs you", callback_data="adm_queue",
                                         icon_custom_emoji_id=Icons.TIMER),
                    InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                                         icon_custom_emoji_id=Icons.BACK),
                ]]))


@router.callback_query(F.data.regexp(r"^adm_ord_retry_\d+$"))
async def adm_order_retry(query: CallbackQuery, services: Services):
    """A delivery that failed on the way out, sent again."""
    if await _deny(query, services):
        return
    order_id = int(query.data.removeprefix("adm_ord_retry_"))
    try:
        await services.delivery.retry_order(order_id)
    except Exception as exc:
        logger.exception("Retry delivery failed for order %s", order_id)
        with suppress(TelegramBadRequest):
            await query.answer(f"Could not resend: {type(exc).__name__}", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await query.answer("Queued again.")


# ──── Products ────────────────────────────────────────────────────────
# Not the whole catalogue: only taking something off sale, which is the one product
# change that cannot wait for a laptop. Everything else stays in the console, where
# there is room to type it properly.


@router.callback_query(F.data == "adm_start_prod")
async def adm_cb_start_prod(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.set_state(AdminProductStates.waiting_for_search)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await query.message.answer(
            f"{ICON_SHOP} <b>Find a product</b>" + chr(92) + "n"
            + chr(0x2501) * 18 + chr(92) + "n"
            "Send part of its name, and you can take it off sale or put it back."
            + chr(92) + "n" + chr(92) + "n" + "Send /cancel to stop.")


@router.callback_query(F.data == "adm_start_stock")
async def adm_cb_start_stock(query: CallbackQuery, state: FSMContext, services: Services):
    """Open on the products that are actually short.

    Stock gets added because something ran out, so asking for a name first made the
    owner type out what the shop already knows. The short ones are listed straight
    away; searching is still there for the rest."""
    if await _deny(query, services):
        return
    await state.clear()
    products = await services.catalog.products(active_only=False, limit=200)
    threshold = int(await services.settings.number("low_stock_threshold") or 3)
    short = sorted(
        (p for p in products
         if p.get("stock") is not None and int(p["stock"] or 0) <= threshold),
        key=lambda p: int(p["stock"] or 0))[:8]

    rows = [[InlineKeyboardButton(
        text=f"{p['title'][:24]} " + chr(0x00B7) + f" {int(p['stock'] or 0)} left",
        callback_data=f"adm_stock_{p['id']}",
        style="danger" if not int(p["stock"] or 0) else "success",
        icon_custom_emoji_id=Icons.PLUS)] for p in short]
    rows.append([InlineKeyboardButton(text="Search by name", callback_data="adm_stock_search",
                                      icon_custom_emoji_id=Icons.QUESTION)])
    rows.append([InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                                      icon_custom_emoji_id=Icons.BACK)])

    lines = ([f"{ICON_WARNING} These are running out:"] if short
             else [f"{ICON_CHECK} Nothing is running low."])
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_PLUS} <b>Add stock</b>" + chr(92) + "n"
                + chr(0x2501) * 18 + chr(92) + "n"
                + (chr(92) + "n").join(lines) + chr(92) + "n" + chr(92) + "n"
                + "<i>Pick one, then paste the items.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "adm_stock_search")
async def adm_cb_stock_search(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.set_state(AdminProductStates.waiting_for_search)
    await state.update_data(adding_stock=True)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await query.message.answer(
            f"{ICON_PLUS} <b>Add stock</b>" + chr(92) + "n"
            + chr(0x2501) * 18 + chr(92) + "n"
            "Send part of the product's name." + chr(92) + "n" + chr(92) + "n"
            "Send /cancel to stop.")

async def _show_product_matches(message: Message, term: str, services: Services,
                               adding_stock: bool) -> None:
    matches = [p for p in await services.catalog.products(active_only=False, limit=200)
               if term.lower() in (p["title"] or "").lower()][:8]
    if not matches:
        await message.answer(f"{ICON_CROSS} Nothing matches <code>{html.escape(term)}</code>.")
        return
    symbol = html.escape(await services.settings.get("currency_symbol"))
    lines, rows = [], []
    for p in matches:
        mark = ICON_CHECK if p["is_active"] else ICON_CROSS
        stock = p.get("stock")
        lines.append(f"{mark} {html.escape(p['title'])[:30]} " + chr(0x00B7)
                     + f" <code>{float(p['price']):.2f} {symbol}</code>"
                     + (" " + chr(0x00B7) + f" {stock} left" if stock is not None else ""))
        if adding_stock:
            rows.append([InlineKeyboardButton(
                text=f"Add to {p['title'][:22]}", callback_data=f"adm_stock_{p['id']}",
                style="success", icon_custom_emoji_id=Icons.PLUS)])
        else:
            rows.append([InlineKeyboardButton(
                text=p['title'][:26],
                callback_data=f"adm_prod_{p['id']}",
                style="success" if p["is_active"] else "danger",
                icon_custom_emoji_id=Icons.SHOP)])
    rows.append([InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                                      icon_custom_emoji_id=Icons.BACK)])
    await message.answer(
        f"{ICON_SHOP} <b>Matches</b>" + chr(92) + "n" + chr(0x2501) * 18 + chr(92) + "n"
        + (chr(92) + "n").join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.message(AdminProductStates.waiting_for_search)
async def adm_product_search(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text = (message.text or "").strip()
    if is_navigation(text):
        await navigate(text, message, state, services)
        return
    data = await state.get_data()
    adding = bool(data.get("adding_stock"))
    await state.clear()
    if not text:
        await message.answer(f"{ICON_WARNING} Send part of the product's name.")
        return
    await _show_product_matches(message, text, services, adding)


def split_typed_name(message: Message) -> tuple[str, str, str]:
    """Pull a name, its fallback glyph and its premium emoji id out of one typed line.

    The owner types the name the way they want it read, premium emoji and all, and
    Telegram reports the emoji separately as an entity. Offsets are counted in UTF-16
    units, not characters, so the text is sliced in that encoding or an emoji halfway
    through a name would cut the wrong place."""
    text = message.text or message.caption or ""
    units = text.encode("utf-16-le")
    emoji_id, glyph, spans = "", "", []
    for entity in message.entities or message.caption_entities or []:
        if getattr(entity, "type", None) != "custom_emoji":
            continue
        eid = getattr(entity, "custom_emoji_id", None)
        if not eid:
            continue
        start, end = entity.offset * 2, (entity.offset + entity.length) * 2
        if not emoji_id:
            emoji_id, glyph = str(eid), units[start:end].decode("utf-16-le", "ignore")
        spans.append((start, end))
    keep, last = [], 0
    for start, end in sorted(spans):
        keep.append(units[last:start])
        last = end
    keep.append(units[last:])
    title = b"".join(keep).decode("utf-16-le", "ignore").strip()
    return title, glyph.strip(), emoji_id


async def build_product_card(services: Services, product_id: int):
    product = await services.catalog.product(product_id)
    if not product:
        return None, None
    symbol = html.escape(await services.settings.get("currency_symbol"))
    async with services.db.connect() as conn:
        sold = await conn.fetchrow(
            "SELECT COUNT(*)::int AS orders, COALESCE(SUM(price), 0)::float AS revenue "
            "FROM orders WHERE product_id = $1 AND status = 'completed'", product_id)
    live = bool(product["is_active"])
    icon = tg_icon(str(product["custom_emoji_id"]), product.get("icon") or chr(0x1F6CD)) \
        if str(product.get("custom_emoji_id") or "").isdigit() else (product.get("icon") or ICON_SHOP)
    stock = product.get("stock")
    text = (
        f"{icon} <b>{html.escape(product['title'])}</b>" + '\\n'
        + '━━━━━━━━━━━━━━━━━━' + '\\n'
        + f"{ICON_MONEY} <b>Price:</b> <code>{float(product['price']):.2f} {symbol}</code>" + '\\n'
        + (f"{ICON_SHOP} <b>Stock:</b> <code>{stock}</code>" + '\\n' if stock is not None else "")
        + f"{ICON_ORDERS} <b>Sold:</b> <code>{sold['orders']}</code> · "
        + f"<code>{sold['revenue']:.2f} {symbol}</code>" + '\\n'
        + (f"{ICON_CHECK} On sale" if live else f"{ICON_CROSS} Hidden from the shop")
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Rename", callback_data=f"adm_prod_name_{product_id}",
                                 icon_custom_emoji_id=Icons.NOTE),
            InlineKeyboardButton(text="Change price", callback_data=f"adm_prod_price_{product_id}",
                                 icon_custom_emoji_id=Icons.MONEY),
        ],
        [
            InlineKeyboardButton(text="Add stock", callback_data=f"adm_stock_{product_id}",
                                 style="success", icon_custom_emoji_id=Icons.PLUS),
            InlineKeyboardButton(text="Take off sale" if live else "Put back on sale",
                                 callback_data=f"adm_prod_toggle_{product_id}",
                                 style="danger" if live else "success",
                                 icon_custom_emoji_id=Icons.CROSS if live else Icons.CHECK),
        ],
        [
            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                                 icon_custom_emoji_id=Icons.BACK),
        ],
    ])
    return text, keyboard


@router.callback_query(F.data.regexp(r"^adm_prod_\d+$"))
async def adm_product_card(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.clear()
    text, keyboard = await build_product_card(services, int(query.data.removeprefix("adm_prod_")))
    if not text:
        with suppress(TelegramBadRequest):
            await query.answer("That product no longer exists.", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^adm_prod_name_\d+$"))
async def adm_product_rename_ask(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    product_id = int(query.data.removeprefix("adm_prod_name_"))
    product = await services.catalog.product(product_id)
    if not product:
        with suppress(TelegramBadRequest):
            await query.answer("That product no longer exists.", show_alert=True)
        return
    await state.set_state(AdminProductStates.waiting_for_name)
    await state.update_data(prod_id=product_id, prod_asked_at=time.time())
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await query.message.answer(
            f"{ICON_NOTE} <b>Rename {html.escape(product['title'])}</b>" + '\\n'
            + '━━━━━━━━━━━━━━━━━━' + '\\n'
            + "Send the new name, written the way customers should see it." + '\\n\\n'
            + "Type a premium emoji into it and that emoji is kept as the product's icon." + '\\n\\n'
            + "Send /cancel to stop.")


@router.message(AdminProductStates.waiting_for_name)
async def adm_product_rename_save(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    data = await state.get_data()
    asked_at = float(data.get("prod_asked_at") or 0)
    if not asked_at or time.time() - asked_at > DELIVERY_PROMPT_SECONDS:
        await state.clear()
        await message.answer(f"{ICON_WARNING} That prompt expired. Open the product again.")
        return
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text) or raw_text.startswith("/"):
        await state.clear()
        if raw_text.lower().startswith("/cancel"):
            await message.answer(f"{ICON_CROSS} Cancelled. The name is unchanged.")
        else:
            await navigate(raw_text, message, state, services)
        return

    title, glyph, emoji_id = split_typed_name(message)
    if not title:
        await message.answer(
            f"{ICON_WARNING} A name needs some words, not only an emoji. Send it again, or /cancel.")
        return
    if len(title) > 120:
        await message.answer(f"{ICON_WARNING} That name is too long. Keep it under 120 characters.")
        return

    product_id = int(data.get("prod_id") or 0)
    await state.clear()
    fields: dict = {"title": title}
    if emoji_id:
        fields["custom_emoji_id"] = emoji_id
        fields["icon"] = glyph
    await services.catalog.update_product(product_id, **fields)
    text, keyboard = await build_product_card(services, product_id)
    if not text:
        await message.answer(f"{ICON_CROSS} That product no longer exists.")
        return
    kept = (f"{ICON_SPARKLES} <i>The premium emoji you typed is now its icon.</i>" + '\\n' if emoji_id else "")
    await message.answer(
        f"{ICON_CHECK} <b>Renamed</b>" + '\\n' + kept + '\\n' + text,
        reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^adm_prod_price_\d+$"))
async def adm_product_price_ask(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    product_id = int(query.data.removeprefix("adm_prod_price_"))
    product = await services.catalog.product(product_id)
    if not product:
        with suppress(TelegramBadRequest):
            await query.answer("That product no longer exists.", show_alert=True)
        return
    symbol = html.escape(await services.settings.get("currency_symbol"))
    await state.set_state(AdminProductStates.waiting_for_price)
    await state.update_data(prod_id=product_id, prod_asked_at=time.time())
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await query.message.answer(
            f"{ICON_MONEY} <b>Price for {html.escape(product['title'])}</b>" + '\\n'
            + '━━━━━━━━━━━━━━━━━━' + '\\n'
            + f"Now <code>{float(product['price']):.2f} {symbol}</code>. Send the new one." + '\\n\\n'
            + "Send /cancel to stop.")


@router.message(AdminProductStates.waiting_for_price)
async def adm_product_price_save(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    data = await state.get_data()
    asked_at = float(data.get("prod_asked_at") or 0)
    if not asked_at or time.time() - asked_at > DELIVERY_PROMPT_SECONDS:
        await state.clear()
        await message.answer(f"{ICON_WARNING} That prompt expired. Open the product again.")
        return
    text = (message.text or "").strip()
    if is_navigation(text) or text.startswith("/"):
        await state.clear()
        if text.lower().startswith("/cancel"):
            await message.answer(f"{ICON_CROSS} Cancelled. The price is unchanged.")
        else:
            await navigate(text, message, state, services)
        return
    try:
        new_price = float(text.replace(",", "").strip())
        if new_price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(f"{ICON_WARNING} Send a number, like <code>85</code>, or /cancel.")
        return

    product_id = int(data.get("prod_id") or 0)
    product = await services.catalog.product(product_id)
    if not product:
        await state.clear()
        await message.answer(f"{ICON_CROSS} That product no longer exists.")
        return
    symbol = html.escape(await services.settings.get("currency_symbol"))
    old_price = float(product["price"])
    await state.clear()
    # A slip of a digit here sells the whole shelf at a tenth of its price, so this
    # is confirmed the same way money leaving the shop is.
    await message.answer(
        f"{ICON_WARNING} <b>Change the price?</b>" + '\\n' + '━━━━━━━━━━━━━━━━━━' + '\\n'
        + f"{ICON_SHOP} {html.escape(product['title'])}" + '\\n'
        + f"<code>{old_price:.2f}</code> -> <code>{new_price:.2f} {symbol}</code>" + '\\n\\n'
        + "<i>Customers see it straight away.</i>",
        reply_markup=_confirm_keyboard(f"adm_prod_setp_{product_id}_{round(new_price * 100)}",
                                      f"Yes, set {new_price:.2f} {symbol}",
                                      danger=new_price < old_price))


@router.callback_query(F.data.regexp(r"^adm_prod_setp_\d+_\d+$"))
async def adm_product_price_do(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    _, raw_id, raw_cents = query.data.removeprefix("adm_prod_setp_").rpartition("_")[0], *query.data.removeprefix("adm_prod_setp_").rsplit("_", 1)
    product_id, new_price = int(raw_id), int(raw_cents) / 100
    old_price = await services.catalog.update_product(product_id, price=new_price)
    if old_price is None:
        with suppress(TelegramBadRequest):
            await query.answer("That product no longer exists.", show_alert=True)
        return
    # The console posts a price drop to the channel; doing it from a phone should not
    # quietly skip that.
    announced = False
    if float(old_price) != new_price:
        with suppress(Exception):
            announced = await services.announcements.price_change(product_id, float(old_price), new_price)
    with suppress(TelegramBadRequest):
        await query.answer("Price updated.")
    text, keyboard = await build_product_card(services, product_id)
    if query.message and text:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_CHECK} <b>Price updated</b>" + '\\n'
                + (f"{ICON_CHANNEL} <i>Posted to your channel.</i>" + '\\n' if announced else "")
                + '\\n' + text,
                reply_markup=keyboard)

@router.callback_query(F.data.regexp(r"^adm_prod_toggle_\d+$"))
async def adm_product_toggle(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    product_id = int(query.data.removeprefix("adm_prod_toggle_"))
    product = await services.catalog.product(product_id)
    if not product:
        with suppress(TelegramBadRequest):
            await query.answer("That product no longer exists.", show_alert=True)
        return
    now_active = not bool(product["is_active"])
    await services.catalog.update_product(product_id, is_active=1 if now_active else 0)
    with suppress(TelegramBadRequest):
        await query.answer("Back on sale." if now_active else "Off sale.")
    if query.message:
        icon = ICON_CHECK if now_active else ICON_CROSS
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{icon} <b>{html.escape(product['title'])}</b>" + chr(92) + "n"
                + chr(0x2501) * 18 + chr(92) + "n"
                + ("Customers can buy it again." if now_active
                   else "It is hidden from the shop. Nothing else changed."),
                reply_markup=(await build_product_card(services, product_id))[1])


# ──── Stock ───────────────────────────────────────────────────────────
# Running out at two in the morning is the thing that most often needs a laptop.


@router.callback_query(F.data.regexp(r"^adm_stock_\d+$"))
async def adm_stock_ask(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    product_id = int(query.data.removeprefix("adm_stock_"))
    product = await services.catalog.product(product_id)
    if not product:
        with suppress(TelegramBadRequest):
            await query.answer("That product no longer exists.", show_alert=True)
        return
    await state.set_state(AdminProductStates.waiting_for_stock)
    await state.update_data(stock_product_id=product_id, stock_asked_at=time.time())
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await query.message.answer(
            f"{ICON_PLUS} <b>Add stock to {html.escape(product['title'])}</b>" + chr(92) + "n"
            + chr(0x2501) * 18 + chr(92) + "n"
            "Send the items, one per line. A line already in stock is skipped, so you "
            "can paste the whole batch." + chr(92) + "n" + chr(92) + "n" + "Send /cancel to stop.")


@router.message(AdminProductStates.waiting_for_stock)
async def adm_stock_save(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text = (message.text or message.caption or "").strip()
    data = await state.get_data()

    # The same reasoning as the delivery prompt: what is typed here is stock, and a
    # prompt left open would swallow an unrelated message later.
    asked_at = float(data.get("stock_asked_at") or 0)
    if not asked_at or time.time() - asked_at > DELIVERY_PROMPT_SECONDS:
        await state.clear()
        await message.answer(f"{ICON_WARNING} That prompt expired. Tap <b>Add stock</b> again.")
        return
    if is_navigation(text) or text.startswith("/"):
        await state.clear()
        if text.lower().startswith("/cancel"):
            await message.answer(f"{ICON_CROSS} Cancelled. No stock was added.")
        else:
            await navigate(text, message, state, services)
        return

    items = [line.strip() for line in text.splitlines() if line.strip()]
    if not items:
        await message.answer(f"{ICON_WARNING} Send the items, one per line, or /cancel.")
        return
    product_id = int(data.get("stock_product_id") or 0)
    await state.clear()
    try:
        result = await services.inventory.add_stock(product_id, items)
    except Exception as exc:
        await message.answer(f"{ICON_CROSS} Could not add stock: {html.escape(str(exc))}")
        return
    product = await services.catalog.product(product_id)
    added, skipped = int(result.get("added", 0)), int(result.get("skipped", 0))
    if added:
        with suppress(Exception):
            await services.announcements.restock(product_id, added)
    await message.answer(
        f"{ICON_CHECK} <b>{html.escape((product or {}).get('title') or 'Product')}</b>" + chr(92) + "n"
        + chr(0x2501) * 18 + chr(92) + "n"
        f"{ICON_PLUS} Added <code>{added}</code>"
        + (f", skipped <code>{skipped}</code> already in stock" if skipped else "")
        + chr(92) + "n"
        f"{ICON_SHOP} Now <code>{(product or {}).get('stock', 0)}</code> in stock",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                                 icon_custom_emoji_id=Icons.BACK),
        ]]))

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
