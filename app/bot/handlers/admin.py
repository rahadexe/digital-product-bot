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
        f"{ICON_CHANNEL} <b>Broadcast Message</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Send or forward the message to broadcast.\n"
        f"<i>Supports text, photos & HTML formatting.</i>\n\n"
        f"Send /cancel to abort.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
        ]])
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
                    f"{ICON_CHECK} <b>Broadcast Queued</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{ICON_ID} Job ID: <code>#{result['id']}</code>\n"
                    f"{ICON_ACCOUNT} Recipients: <b>{result['total']}</b>\n\n"
                    f"<i>Sending in the background. Tap below to track progress:</i>",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="BC Status", callback_data="adm_view_bcstatus", icon_custom_emoji_id=Icons.TIMER),
                            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
                        ],
                        [
                            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
                        ],
                    ]),
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
            InlineKeyboardButton(text=f"Deposits ({pending})" if pending else "Deposits",
                                 callback_data="adm_queue_dep",
                                 style="danger" if pending else "primary",
                                 icon_custom_emoji_id=Icons.DEPOSIT),
            InlineKeyboardButton(text=f"Deliveries ({waiting})" if waiting else "Deliveries",
                                 callback_data="adm_queue_ord",
                                 style="danger" if waiting else "primary",
                                 icon_custom_emoji_id=Icons.ORDERS),
        ],
        [
            InlineKeyboardButton(text="Products", callback_data="adm_start_prod", icon_custom_emoji_id=Icons.PRODUCTS),
            InlineKeyboardButton(text="Add stock", callback_data="adm_start_stock", icon_custom_emoji_id=Icons.PLUS),
        ],
        [
            InlineKeyboardButton(text="Re-check payments", callback_data="adm_recheck", icon_custom_emoji_id=Icons.DEPOSIT),
            InlineKeyboardButton(text="Find Customer", callback_data="adm_start_find", icon_custom_emoji_id=Icons.ACCOUNT),
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
            f"Send or forward the message to broadcast.\n"
            f"<i>Supports text, photos & HTML formatting.</i>\n\n"
            f"Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
            ]])
        )


@router.callback_query(F.data == "adm_start_welcome")
async def adm_cb_start_welcome(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    values = await services.settings.values()
    current_welcome = values.get("welcome_text", "").strip()

    await state.set_state(WelcomeStates.waiting_for_welcome)
    status_hint = (
        f"<blockquote>{html.escape(current_welcome)}</blockquote>\n\n"
        if current_welcome
        else "<i>Status: Default greeting active</i>\n\n"
    )
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await query.message.answer(
            f"{ICON_NOTE} <b>Set Welcome Message</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{status_hint}"
            f"Send new greeting text below.\n"
            f"• Use <code>{{store_name}}</code> for store name\n"
            f"• Send /cancel to abort",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Use default", callback_data="adm_reset_welcome",
                                     icon_custom_emoji_id=Icons.REFRESH),
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger",
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
        await query.answer("Reset to default greeting.")
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
            f"Send Telegram ID (e.g. <code>100200300</code>) or <code>@username</code>.\n\n"
            f"Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
            ]])
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

    await state.set_state(WelcomeStates.waiting_for_welcome)
    status_hint = (
        f"<blockquote>{html.escape(current_welcome)}</blockquote>\n\n"
        if current_welcome
        else "<i>Status: Default greeting active</i>\n\n"
    )

    await message.answer(
        f"{ICON_NOTE} <b>Set Welcome Message</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{status_hint}"
        f"Send new greeting text below.\n"
        f"• Use <code>{{store_name}}</code> for store name\n"
        f"• Send /cancel to abort",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Use default", callback_data="adm_reset_welcome",
                                 icon_custom_emoji_id=Icons.REFRESH),
            InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger",
                                 icon_custom_emoji_id=Icons.CLOSE),
        ]]),
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
            f"{ICON_WARNING} <b>Invalid input:</b> Commands cannot be saved as welcome message.\n\n"
            f"Send greeting text, or /cancel."
        )
        return

    text = message.html_text or message.caption or message.text
    if not text or not text.strip():
        await message.answer(f"{ICON_WARNING} Please send text message, or /cancel.")
        return

    await _save_welcome_text(message, text.strip(), services)
    await state.clear()


async def _save_welcome_text(message: Message, text: str, services: Services):
    clean_text = text.strip()
    if clean_text.startswith("/"):
        await message.answer(
            f"{ICON_CROSS} <b>Error:</b> Commands cannot be saved as welcome message.\n\n"
            f"Send custom text without a leading slash."
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
        f"{ICON_CHECK} <b>Welcome Message Saved</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{preview_display}\n\n"
        f"<i>Live for all customers now.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
        ]])
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
            f"{ICON_WARNING} <b>Confirm Deposit Approval</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Customer:</b> {cust_handle}\n"
            f"🆔 <b>Customer ID:</b> <code>{deposit['tg_user_id']}</code>\n"
            f"💵 <b>Amount:</b> <code>{amount}</code>\n"
            f"🔐 <b>TrxID:</b> <code>{html.escape(str(deposit['transaction_id']))}</code>\n\n"
            f"<i>Check money arrived before approving.</i>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"Confirm ({amount})", callback_data=f"adm_dep_do_approve_{raw_id}", style="success", icon_custom_emoji_id=Icons.CHECK),
            InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="primary", icon_custom_emoji_id=Icons.BACK),
        ]])
    else:
        text = (
            f"{ICON_WARNING} <b>Confirm Deposit Rejection</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Customer:</b> {cust_handle}\n"
            f"🆔 <b>Customer ID:</b> <code>{deposit['tg_user_id']}</code>\n"
            f"💵 <b>Amount:</b> <code>{amount}</code>\n\n"
            f"<i>Customer will be told it could not be verified.</i>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Confirm Reject", callback_data=f"adm_dep_do_reject_{raw_id}", style="danger", icon_custom_emoji_id=Icons.CROSS),
            InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="primary", icon_custom_emoji_id=Icons.BACK),
        ]])

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
                f"{ICON_NOTE} <b>Deliver Order #{order_id}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📦 {html.escape(order['product_title'])}\n\n"
                f"Send credentials or item to deliver below:\n"
                f"<i>(Send /cancel to stop)</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
                ]])
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
        f"{ICON_CHECK} <b>Order #{order_id} Delivered</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>Item delivered to customer successfully.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Needs you", callback_data="adm_queue", icon_custom_emoji_id=Icons.TIMER),
            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
        ]])
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
    is_admin_target = int(user["tg_user_id"]) in await services.settings.admin_chat_ids()
    symbol = html.escape(await services.settings.get("currency_symbol"))
    name = html.escape(" ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "No name")
    handle = f"@{html.escape(user['username'])}" if user.get("username") else "no username"
    banned_tag = f" · {ICON_CROSS} <b>BANNED</b>" if user.get("is_banned") else ""
    is_banned = bool(user.get("is_banned"))

    buttons = []
    if not is_admin_target:
        buttons.append([
            InlineKeyboardButton(
                text="Unban Customer" if is_banned else "Ban Customer",
                callback_data=f"adm_ban_ask_{user['tg_user_id']}",
                style="success" if is_banned else "danger",
                icon_custom_emoji_id=Icons.CHECK if is_banned else Icons.CROSS,
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
    ])

    await message.answer(
        f"{ICON_ACCOUNT} <b>Customer Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Name:</b> {name} ({handle})\n"
        f"🆔 <b>Customer ID:</b> <code>{user['tg_user_id']}</code>\n"
        f"👑 <b>Rank:</b> {html.escape(user.get('rank') or 'Standard')}{banned_tag}\n"
        f"💵 <b>Balance:</b> <code>{float(user.get('balance') or 0):.2f} {symbol}</code>\n"
        f"📦 <b>Orders:</b> <code>{found['order_count']}</code> · <b>Spent:</b> <code>{float(found['total_spent'] or 0):.2f} {symbol}</code>"
        + (f"\n\n{ICON_CROWN} <i>Administrator account.</i>" if is_admin_target else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
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


async def build_queue_view(services: Services, kind: str = "all") -> tuple[str, InlineKeyboardMarkup]:
    """One list or the other, or both.

    Split because "needs attention" did not say what was waiting, and the two are
    different jobs: money to check against a receipt, and something to send a customer.
    Each view links to the other, so moving between them is one tap rather than a trip
    back through the menu."""
    symbol = html.escape(await services.settings.get("currency_symbol"))
    async with services.db.connect() as conn:
        deposits = await conn.fetch(
            "SELECT d.id, d.amount, d.transaction_id, u.username, u.tg_user_id "
            "FROM deposits d LEFT JOIN users u ON u.id = d.user_id "
            "WHERE d.status = 'pending' ORDER BY d.id LIMIT 8") if kind in ("all", "deposits") else []
        orders = await conn.fetch(
            "SELECT o.id, o.product_title, o.price, u.username, u.tg_user_id "
            "FROM orders o LEFT JOIN users u ON u.tg_user_id = o.tg_user_id "
            "WHERE o.status = 'completed' AND o.fulfillment = 'waiting' "
            "ORDER BY o.id LIMIT 8") if kind in ("all", "orders") else []

    rows: list[list[InlineKeyboardButton]] = []
    lines = []
    if deposits:
        if kind == "all":
            lines.append(f"{ICON_DEPOSIT} <b>Pending Deposits ({len(deposits)}):</b>")
        for d in deposits:
            who = f"@{html.escape(d['username'])}" if d['username'] else f"<code>{d['tg_user_id']}</code>"
            lines.append(f"• #{d['id']} · <code>{float(d['amount']):.2f} {symbol}</code> · {who}")
            rows.append([
                InlineKeyboardButton(text=f"Approve #{d['id']}",
                                     callback_data=f"adm_dep_ask_approve_{d['id']}",
                                     style="success", icon_custom_emoji_id=Icons.CHECK),
                InlineKeyboardButton(text="Reject",
                                     callback_data=f"adm_dep_ask_reject_{d['id']}",
                                     style="danger", icon_custom_emoji_id=Icons.CROSS),
            ])
    if orders:
        if lines:
            lines.append("")
        if kind == "all":
            lines.append(f"{ICON_ORDERS} <b>Pending Deliveries ({len(orders)}):</b>")
        for o in orders:
            who = f"@{html.escape(o['username'])}" if o['username'] else f"<code>{o['tg_user_id']}</code>"
            lines.append(f"• #{o['id']} · {html.escape(o['product_title'])[:24]} · {who}")
            rows.append([
                InlineKeyboardButton(text=f"Deliver #{o['id']}",
                                     callback_data=f"adm_ord_deliver_{o['id']}",
                                     style="success", icon_custom_emoji_id=Icons.ORDERS),
                InlineKeyboardButton(text="Refund",
                                     callback_data=f"adm_ord_ref_ask_{o['id']}",
                                     style="danger", icon_custom_emoji_id=Icons.SPENT),
            ])
    if not lines:
        lines.append(f"{ICON_CHECK} All clear! Nothing waiting on you.")

    here = {"deposits": "adm_queue_dep", "orders": "adm_queue_ord"}.get(kind, "adm_queue")
    switch: list[InlineKeyboardButton] = []
    if kind == "deposits":
        switch.append(InlineKeyboardButton(text="Deliveries", callback_data="adm_queue_ord",
                                           icon_custom_emoji_id=Icons.ORDERS))
    elif kind == "orders":
        switch.append(InlineKeyboardButton(text="Deposits", callback_data="adm_queue_dep",
                                           icon_custom_emoji_id=Icons.DEPOSIT))
    rows.append(switch + [
        InlineKeyboardButton(text="Refresh", callback_data=here, icon_custom_emoji_id=Icons.REFRESH),
        InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
    ])
    rows.append([
        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
    ])
    heading = {
        "deposits": f"{ICON_DEPOSIT} <b>Pending Deposits ({len(deposits)})</b>",
        "orders": f"{ICON_ORDERS} <b>Pending Deliveries ({len(orders)})</b>",
    }.get(kind, f"{ICON_TIMER} <b>Needs Attention</b>")
    text = (
        heading + "\n"
        "━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines)
    )
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


@router.callback_query(F.data.in_({"adm_queue_dep", "adm_queue_ord"}))
async def adm_cb_queue_one(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    kind = "deposits" if query.data == "adm_queue_dep" else "orders"
    text, keyboard = await build_queue_view(services, kind)
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
    note = f"\n\n<i>{html.escape(', '.join(problems))}</i>" if problems else ""
    if query.message:
        text, keyboard = await build_queue_view(services)
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_DEPOSIT} <b>Checked {checked} unpaid invoice(s)</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<i>Confirmed payments credit automatically.</i>{note}\n\n"
                + text,
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
                f"{ICON_WARNING} <b>Confirm Order Refund</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📦 <b>Product:</b> {html.escape(order['product_title'])}\n"
                f"💵 <b>Refund Amount:</b> <code>{amount}</code>\n\n"
                f"<i>Amount will be refunded to customer's wallet.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=f"Confirm Refund ({amount})", callback_data=f"adm_ord_ref_do_{order_id}",
                                         style="danger", icon_custom_emoji_id=Icons.SPENT),
                    InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="primary",
                                         icon_custom_emoji_id=Icons.BACK),
                ]]))


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
                f"{icon} <b>Order #{order_id}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{html.escape(message)}",
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
            f"{ICON_SHOP} <b>Find Product</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Send part of the product name to manage or toggle sale status.\n\n"
            f"Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
            ]])
        )


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
        text=f"{p['title'][:24]} · {int(p['stock'] or 0)} left",
        callback_data=f"adm_stock_{p['id']}",
        style="danger" if not int(p["stock"] or 0) else "success",
        icon_custom_emoji_id=Icons.PLUS)] for p in short]
    rows.append([InlineKeyboardButton(text="Search by Name", callback_data="adm_stock_search",
                                      icon_custom_emoji_id=Icons.PRODUCTS)])
    rows.append([
        InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                             icon_custom_emoji_id=Icons.BACK),
        InlineKeyboardButton(text="Close", callback_data="close_menu",
                             style="danger", icon_custom_emoji_id=Icons.CLOSE),
    ])

    header = f"{ICON_WARNING} <b>These items are running low:</b>" if short else f"{ICON_CHECK} <b>All products have sufficient stock.</b>"
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_PLUS} <b>Add Stock</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{header}\n\n"
                f"<i>Select a product to restock, or search by name.</i>",
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
            f"{ICON_PLUS} <b>Add Stock · Search</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Send part of the product name to find and restock.\n\n"
            f"Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
            ]])
        )

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
        lines.append(f"{mark} {html.escape(p['title'])[:30]} · <code>{float(p['price']):.2f} {symbol}</code>"
                     + (f" · {stock} left" if stock is not None else ""))
        if adding_stock:
            rows.append([InlineKeyboardButton(
                text=f"Add to {p['title'][:22]}", callback_data=f"adm_stock_{p['id']}",
                style="success", icon_custom_emoji_id=Icons.PLUS)])
        else:
            rows.append([InlineKeyboardButton(
                text=p['title'][:26],
                callback_data=f"adm_prod_{p['id']}",
                style="success" if p["is_active"] else "danger",
                icon_custom_emoji_id=Icons.PRODUCTS)])
    rows.append([
        InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                             icon_custom_emoji_id=Icons.BACK),
        InlineKeyboardButton(text="Close", callback_data="close_menu",
                             style="danger", icon_custom_emoji_id=Icons.CLOSE),
    ])
    await message.answer(
        f"{ICON_SHOP} <b>Product Matches</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines),
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
    status_str = f"{ICON_CHECK} On sale" if live else f"{ICON_CROSS} Hidden"
    stock_line = f"{ICON_SHOP} <b>Stock:</b> <code>{stock}</code>\n" if stock is not None else ""
    text = (
        f"{icon} <b>{html.escape(product['title'])}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_MONEY} <b>Price:</b> <code>{float(product['price']):.2f} {symbol}</code>\n"
        f"{stock_line}"
        f"{ICON_ORDERS} <b>Sold:</b> <code>{sold['orders']}</code> · <code>{sold['revenue']:.2f} {symbol}</code>\n"
        f"<b>Status:</b> {status_str}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Rename", callback_data=f"adm_prod_name_{product_id}",
                                 icon_custom_emoji_id=Icons.NOTE),
            InlineKeyboardButton(text="Change Price", callback_data=f"adm_prod_price_{product_id}",
                                 icon_custom_emoji_id=Icons.MONEY),
        ],
        [
            InlineKeyboardButton(text="Add Stock", callback_data=f"adm_stock_{product_id}",
                                 style="success", icon_custom_emoji_id=Icons.PLUS),
            InlineKeyboardButton(text="Hide Product" if live else "Show Product",
                                 callback_data=f"adm_prod_toggle_{product_id}",
                                 style="danger" if live else "success",
                                 icon_custom_emoji_id=Icons.CROSS if live else Icons.CHECK),
        ],
        [
            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                                 icon_custom_emoji_id=Icons.BACK),
            InlineKeyboardButton(text="Close", callback_data="close_menu",
                                 style="danger", icon_custom_emoji_id=Icons.CLOSE),
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
            f"{ICON_NOTE} <b>Rename Product</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Product: <b>{html.escape(product['title'])}</b>\n\n"
            f"Send the new product name.\n"
            f"<i>Custom emoji in text will be saved as its icon.</i>\n\n"
            f"Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
            ]])
        )


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
    kept = (f"{ICON_SPARKLES} <i>Custom emoji saved as product icon.</i>\n\n" if emoji_id else "")
    await message.answer(
        f"{ICON_CHECK} <b>Product Renamed</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        + kept + text,
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
            f"{ICON_MONEY} <b>Change Price</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Product: <b>{html.escape(product['title'])}</b>\n"
            f"Current: <code>{float(product['price']):.2f} {symbol}</code>\n\n"
            f"Send the new price (e.g. <code>85</code>).\n\n"
            f"Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
            ]])
        )


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
        await message.answer(f"{ICON_WARNING} Send a valid number (e.g. <code>85</code>), or /cancel.")
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
    await message.answer(
        f"{ICON_WARNING} <b>Confirm Price Change</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_SHOP} <b>{html.escape(product['title'])}</b>\n"
        f"Price: <code>{old_price:.2f} {symbol}</code> ➔ <code>{new_price:.2f} {symbol}</code>\n\n"
        f"<i>Customers will see the new price immediately.</i>",
        reply_markup=_confirm_keyboard(f"adm_prod_setp_{product_id}_{round(new_price * 100)}",
                                      f"Confirm ({new_price:.2f} {symbol})",
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
                f"{ICON_CHECK} <b>Price Updated</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                + (f"{ICON_CHANNEL} <i>Posted to channel.</i>\n\n" if announced else "\n")
                + text,
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
        status_txt = "Product is now live and visible to customers." if now_active else "Product is now hidden from the store."
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{icon} <b>{html.escape(product['title'])}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{status_txt}",
                reply_markup=(await build_product_card(services, product_id))[1])


# ──── Stock ───────────────────────────────────────────────────────────


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
            f"{ICON_PLUS} <b>Add Stock</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Product: <b>{html.escape(product['title'])}</b>\n\n"
            f"Send items to add, one item per line.\n"
            f"<i>Duplicates already in stock will be skipped automatically.</i>\n\n"
            f"Send /cancel to abort.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)
            ]])
        )


@router.message(AdminProductStates.waiting_for_stock)
async def adm_stock_save(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text = (message.text or message.caption or "").strip()
    data = await state.get_data()

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
    stock_count = (product or {}).get('stock', 0)
    skipped_str = f" · Skipped: <code>{skipped}</code>" if skipped else ""
    await message.answer(
        f"{ICON_CHECK} <b>Stock Updated</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Product: <b>{html.escape((product or {}).get('title') or 'Product')}</b>\n"
        f"Added: <code>+{added}</code>{skipped_str}\n"
        f"Current Stock: <code>{stock_count}</code> items",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard",
                                 icon_custom_emoji_id=Icons.BACK),
            InlineKeyboardButton(text="Close", callback_data="close_menu",
                                 style="danger", icon_custom_emoji_id=Icons.CLOSE),
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
                reply_markup=_confirm_keyboard(f"adm_ban_do_{tg_user_id}", f"Confirm {verb}", danger=banning)
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
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Unban Customer" if banned else "Ban Customer",
                            callback_data=f"adm_ban_ask_{tg_user_id}",
                            style="success" if banned else "danger",
                            icon_custom_emoji_id=Icons.CHECK if banned else Icons.CROSS,
                        )
                    ],
                    [
                        InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
                        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
                    ]
                ])
            )
