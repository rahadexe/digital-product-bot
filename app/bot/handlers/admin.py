"""Admin bot commands: broadcast, broadcast status, and admin quick utilities."""

from __future__ import annotations

import html
import io
import logging
import re
import time
from contextlib import suppress
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.handlers.navigation import NAVIGATION_TEXTS, is_navigation, navigate
from app.bot.keyboards import ADMIN_PANEL_TEXT
from app.core.identifiers import format_deposit_id, format_order_id
from app.services import Services

logger = logging.getLogger("app.bot.admin")

router = Router()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()
    confirming = State()


class AdminFindStates(StatesGroup):
    waiting_for_input = State()


class AdminProductStates(StatesGroup):
    waiting_for_stock = State()


class AdminSettingsStates(StatesGroup):
    waiting_for_banner = State()


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
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data="bc_cancel",
                    style="danger",
                ),
            ]
        ]
    )


async def _show_preview(message: Message, text: str, services: Services, state: FSMContext, panel_msg_id: int | None = None) -> None:
    recipients = await services.delivery.recipient_count()
    if recipients == 0:
        if panel_msg_id:
            with suppress(Exception):
                await message.delete()
            text_dash, keyboard = await build_admin_dashboard(services)
            with suppress(TelegramBadRequest):
                await message.bot.edit_message_text(
                    text="No active recipients found.",
                    chat_id=message.chat.id,
                    message_id=panel_msg_id,
                    reply_markup=keyboard,
                )
            await state.clear()
            return
        await message.answer("No active recipients found.")
        await state.clear()
        return

    await state.set_state(BroadcastStates.confirming)
    await state.update_data(broadcast_text=text, recipient_count=recipients)

    preview_body = (
        "<b>Broadcast Preview</b>\n\n"
        f"{text}\n\n"
        f"Recipients: <b>{recipients}</b>"
    )

    if panel_msg_id:
        with suppress(Exception):
            await message.delete()
        try:
            await message.bot.edit_message_text(
                text=preview_body,
                chat_id=message.chat.id,
                message_id=panel_msg_id,
                reply_markup=_build_preview_keyboard(),
                disable_web_page_preview=True,
            )
            return
        except Exception:
            pass

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
        "<b>Broadcast Message</b>\n"
        "\n"
        "Send or forward the message to broadcast.\n"
        "<i>Supports text, photos & HTML formatting.</i>\n\n"
        "Tap Cancel below to abort.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger")
        ]])
    )


@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_input(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    data = await state.get_data()
    panel_msg_id = data.get("panel_msg_id")

    raw_text = (message.text or "").strip()
    # A menu button is plain text, and would otherwise be composed into a broadcast.
    if raw_text in NAVIGATION_TEXTS:
        await navigate(raw_text, message, state, services)
        return
    if raw_text.startswith("/"):
        cmd = raw_text.split()[0].lower().lstrip("/")
        if cmd in ("cancel", "admin"):
            await state.clear()
            with suppress(Exception):
                await message.delete()
            if panel_msg_id:
                text_dash, keyboard = await build_admin_dashboard(services)
                with suppress(TelegramBadRequest):
                    await message.bot.edit_message_text(
                        text=text_dash,
                        chat_id=message.chat.id,
                        message_id=panel_msg_id,
                        reply_markup=keyboard,
                    )
            else:
                await message.answer("Broadcast cancelled.")
            return

        if cmd in ("start",):
            await state.clear()
            from app.bot.handlers.start import render_main_dashboard
            await render_main_dashboard(message, services, message.from_user.id)
            return

        if cmd in ("broadcast", "bc"):
            await state.clear()
            await cmd_broadcast(message, state, services)
            return

        await message.answer(
            "<b>Invalid input:</b> Bot commands cannot be broadcast.\n\n"
            "Please send the message you want to broadcast, or tap Cancel below to abort.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger")
            ]])
        )
        return

    text = message.html_text or message.caption or message.text
    if not text or not text.strip():
        await message.answer(
            "Please send a text message or tap Cancel below.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger")
            ]])
        )
        return

    await _show_preview(message, text.strip(), services, state, panel_msg_id=panel_msg_id)


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
            await query.message.edit_text("<b>Queuing broadcast...</b>")

    try:
        result = await services.delivery.enqueue_broadcast(broadcast_text)
        await state.clear()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(
                    "<b>Broadcast Queued</b>\n"
                    "\n"
                    f"Job ID: <code>#{result['id']}</code>\n"
                    f"Recipients: <b>{result['total']}</b>\n\n"
                    "<i>Sending in the background. Tap below to track progress:</i>",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="BC Status", callback_data="adm_view_bcstatus"),
                            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
                        ],
                        [
                            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
                        ],
                    ]),
                )
    except Exception as e:
        logger.exception("Failed to enqueue broadcast from Telegram: %s", e)
        await state.clear()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(f"Failed: {html.escape(str(e))}")


@router.callback_query(F.data == "bc_cancel")
async def handle_bc_cancel(query: CallbackQuery, state: FSMContext, services: Services):
    if not query.from_user or not await _is_admin(query.from_user.id, services):
        await query.answer("Access denied.", show_alert=True)
        return

    await state.clear()
    await query.answer("Cancelled.")
    text, keyboard = await build_admin_dashboard(services)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


async def build_admin_dashboard(services: Services) -> tuple[str, InlineKeyboardMarkup]:
    paused = await services.settings.flag("store_paused")
    stats = await services.dashboard.stats()
    waiting = stats.get("waiting_orders", 0)
    pending = stats.get("pending_deposits", 0)

    get_fn = getattr(services.settings, "get", None)
    raw_symbol = await get_fn("currency_symbol") if get_fn else "৳"
    symbol = html.escape(raw_symbol or "৳")

    today_orders = 0
    today_rev = 0.0
    db = getattr(services, "db", None)
    if db:
        try:
            async with db.connect() as conn:
                today = await conn.fetchrow(
                    "SELECT COUNT(*) AS orders, COALESCE(SUM(price), 0) AS revenue FROM orders "
                    "WHERE status = 'completed' AND created_at >= CURRENT_DATE"
                )
            today_orders = int(today["orders"] or 0) if today else 0
            today_rev = float(today["revenue"] or 0) if today else 0.0
        except Exception:
            pass

    status_str = "Paused" if paused else "Active"

    text = (
        "<b>Admin Panel</b>\n\n"
        f"<b>Status:</b> {status_str}\n"
        f"<b>Today:</b> {today_orders} orders ({today_rev:.2f} {symbol})\n"
        f"<b>Pending Deposits:</b> {pending}\n"
        f"<b>Waiting Orders:</b> {waiting}\n"
        f"<b>Total Customers:</b> {stats.get('total_users', 0)}"
    )

    pause_text = "Resume Store" if paused else "Pause Store"
    pause_style = "success" if paused else "danger"

    deposits_text = f"Deposits ({pending})" if pending else "Deposits"
    orders_text = f"Orders ({waiting})" if waiting else "Orders"

    pending_reseller = await services.reseller_applications.count_applications(status="pending")
    reseller_apps_text = f"Reseller Apps ({pending_reseller})" if pending_reseller else "Reseller Apps"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Store Status", callback_data="adm_view_status"),
            InlineKeyboardButton(text="Broadcast", callback_data="adm_start_broadcast"),
        ],
        [
            InlineKeyboardButton(text=deposits_text, callback_data="adm_queue_dep",
                                 style="danger" if pending else "primary"),
            InlineKeyboardButton(text=orders_text, callback_data="adm_queue_ord",
                                 style="danger" if waiting else "primary"),
        ],
        [
            InlineKeyboardButton(text="Stock", callback_data="adm_start_stock"),
            InlineKeyboardButton(text=reseller_apps_text, callback_data="adm_queue_reseller",
                                 style="danger" if pending_reseller else "primary"),
        ],
        [
            InlineKeyboardButton(text="Find Customer", callback_data="adm_start_find"),
            InlineKeyboardButton(text="Settings", callback_data="adm_start_settings"),
        ],
        [
            InlineKeyboardButton(text=pause_text, callback_data="adm_toggle_pause", style=pause_style),
        ],
        [
            InlineKeyboardButton(text="Back to Store", callback_data="back_to_main", style="primary"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
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
        "<b>Store Status</b>\n\n"
        f"<b>Store:</b> {'Paused' if paused else 'Active'}\n"
        f"<b>Needs you:</b> {needs_you}\n\n"
        f"<b>Today:</b> <code>{int(today['orders'] or 0)}</code> order(s), "
        f"<code>{float(today['revenue'] or 0):.2f} {symbol}</code>\n"
        f"<b>Pending deposits:</b> <code>{pending}</code> "
        f"(<code>{pending_amount:.2f} {symbol}</code>)\n"
        f"<b>All time:</b> <code>{stats.get('total_orders', 0)}</code> order(s), "
        f"<code>{float(stats.get('total_revenue') or 0):.2f} {symbol}</code>\n"
        f"<b>Customers:</b> <code>{stats.get('total_users', 0)}</code>\n\n"
        f"<b>Low stock:</b>\n{low_line}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Refresh", callback_data="adm_view_status"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ],
        [
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
        ]
    ])
    return text, keyboard


async def build_bcstatus_view(services: Services) -> tuple[str, InlineKeyboardMarkup]:
    recent = await services.delivery.recent_broadcasts(limit=1)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Refresh", callback_data="adm_view_bcstatus"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ],
        [
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
        ],
    ])

    if not recent:
        text = (
            "<b>Broadcast Status</b>\n\n"
            "No broadcast history found."
        )
        return text, keyboard

    latest = recent[0]
    snippet = latest["text"][:120] + "..." if len(latest["text"]) > 120 else latest["text"]
    is_pending = latest["pending"] > 0
    status_title = "Sending" if is_pending else "Completed"

    text = (
        f"<b>Broadcast #{latest['id']} · {status_title}</b>\n\n"
        f"<i>{html.escape(snippet)}</i>\n\n"
        f"Total: <b>{latest['total']}</b>\n"
        f"Delivered: <b>{latest['success']}</b>\n"
        f"Failed: <b>{latest['failed']}</b>\n"
        f"Pending: <b>{latest['pending']}</b>"
    )
    return text, keyboard


@router.message(Command("bcstatus", "broadcast_status"))
async def cmd_broadcast_status(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text, keyboard = await build_bcstatus_view(services)
    await message.answer(text, reply_markup=keyboard)


_last_admin_panels: dict[int, int] = {}


@router.message(Command("admin"))
@router.message(F.text.in_({
    ADMIN_PANEL_TEXT, f"👑 {ADMIN_PANEL_TEXT}",
    "ADMIN PANEL", "👑 ADMIN PANEL",
    "Admin Panel", "👑 Admin Panel",
    "অ্যাডমিন প্যানেল", "👑 অ্যাডমিন প্যানেল",
}))
async def cmd_admin_help(message: Message, state: FSMContext | Services | None = None, services: Services | None = None):
    # The keyboard button reaches here from any screen, including the middle of a
    # deposit or a search, so whatever that screen was waiting for is dropped. Anyone
    # else who types the same words gets nothing: not a refusal that says it exists.
    if isinstance(state, Services):
        services = state
        state = None
    if not message.from_user or not services or not await _is_admin(message.from_user.id, services):
        return
    if state:
        await state.clear()

    text, keyboard = await build_admin_dashboard(services)
    sent = await message.answer(text, reply_markup=keyboard)
    _last_admin_panels[message.chat.id] = sent.message_id


@router.callback_query(F.data.in_({"adm_dashboard", "adm_refresh_panel"}))
async def adm_cb_dashboard(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.clear()
    text, keyboard = await build_admin_dashboard(services)
    with suppress(TelegramBadRequest):
        await query.answer("Updated" if query.data == "adm_refresh_panel" else None)
    if query.message:
        _last_admin_panels[query.message.chat.id] = query.message.message_id
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
    if not paused:
        text = (
            "<b>Confirm Store Pause</b>\n\n"
            "<b>While the store is paused:</b>\n"
            "• Customers cannot view or purchase products.\n"
            "• New deposits will be temporarily suspended.\n\n"
            "Are you sure you want to pause the store?"
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Confirm",
                        callback_data="adm_confirm_pause",
                        style="danger",
                    ),
                    InlineKeyboardButton(
                        text="Keep Open",
                        callback_data="adm_dashboard",
                        style="primary",
                    ),
                ]
            ]
        )
        with suppress(TelegramBadRequest):
            await query.answer()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(text, reply_markup=keyboard)
        return

    # Unpausing / Resuming store
    await services.settings.update({"store_paused": "0"})
    with suppress(TelegramBadRequest):
        await query.answer("Store resumed — now active.")
    text, keyboard = await build_admin_dashboard(services)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_confirm_pause")
async def adm_cb_confirm_pause(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    await services.settings.update({"store_paused": "1"})
    with suppress(TelegramBadRequest):
        await query.answer("Store paused.")
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
        await state.update_data(panel_msg_id=query.message.message_id)
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                "<b>Broadcast Message</b>\n"
                "\n"
                f"Active recipients: <b>{recipients}</b>\n\n"
                "Send or forward the message to broadcast.\n"
                "<i>Supports text, photos & HTML formatting.</i>\n\n"
                "Tap Cancel below to abort.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
                    InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger")
                ]])
            )


async def build_admin_settings_view(services: Services) -> tuple[str, InlineKeyboardMarkup]:
    values = await services.settings.values()
    store_name = values.get("store_name", "Premium Haven")
    currency = values.get("currency_symbol", "৳")
    support = values.get("support_username", "None")
    is_paused = values.get("store_paused") == "1"
    banner_file_id = (values.get("welcome_banner_file_id") or "").strip()
    status_str = "Paused" if is_paused else "Active"
    banner_str = "Active (Telegram CDN)" if banner_file_id else "None (Clean Text)"
    text = (
        "⚙️ <b>Store Settings</b>\n\n"
        f"• <b>Store Name:</b> {html.escape(store_name)}\n"
        f"• <b>Status:</b> <code>{status_str}</code>\n"
        f"• <b>Currency:</b> <code>{html.escape(currency)}</code>\n"
        f"• <b>Support:</b> <code>{html.escape(support)}</code>\n"
        f"• <b>Home Banner:</b> <code>{banner_str}</code>\n\n"
        "<i>Use the button below to update your home welcome banner:</i>"
    )
    rows = [
        [
            InlineKeyboardButton(
                text="🖼️ Set Banner" if not banner_file_id else "🖼️ Change Banner",
                callback_data="adm_prompt_banner"
            ),
        ],
    ]
    if banner_file_id:
        rows.append([
            InlineKeyboardButton(text="🗑️ Remove Banner", callback_data="adm_clear_banner", style="danger"),
        ])
    rows.append([
        InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
    ])
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    return text, keyboard


@router.callback_query(F.data == "adm_start_settings")
async def adm_cb_start_settings(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.clear()
    text, keyboard = await build_admin_settings_view(services)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_prompt_banner")
async def adm_cb_prompt_banner(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.set_state(AdminSettingsStates.waiting_for_banner)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await state.update_data(panel_msg_id=query.message.message_id)
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                "🖼️ <b>Upload Welcome Banner</b>\n\n"
                "Please send or forward any photo now.\n\n"
                "The photo will be saved and served directly from Telegram's cloud CDN.\n\n"
                "<i>Tap Cancel below to abort.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Cancel", callback_data="adm_cancel_settings", style="danger")
                ]])
            )


@router.callback_query(F.data == "adm_clear_banner")
async def adm_cb_clear_banner(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    await services.settings.update({"welcome_banner_file_id": ""})
    with suppress(TelegramBadRequest):
        await query.answer("✅ Welcome banner removed.", show_alert=True)
    text, keyboard = await build_admin_settings_view(services)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_cancel_settings")
async def adm_cb_cancel_settings(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.clear()
    text, keyboard = await build_admin_settings_view(services)
    with suppress(TelegramBadRequest):
        await query.answer("Cancelled")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.message(AdminSettingsStates.waiting_for_banner, F.photo)
async def adm_receive_banner_photo(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    photo = message.photo[-1]
    file_id = photo.file_id
    await services.settings.update({"welcome_banner_file_id": file_id})
    await state.clear()
    await message.reply(
        "✅ <b>Welcome banner saved successfully!</b>\n\n"
        "<i>Image is now served directly from Telegram's cloud CDN.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⚙️ Return to Settings", callback_data="adm_start_settings"),
            InlineKeyboardButton(text="🏠 Admin Panel", callback_data="adm_dashboard"),
        ]])
    )


@router.message(AdminSettingsStates.waiting_for_banner)
async def adm_invalid_banner_input(message: Message):
    await message.reply(
        "❌ Please send a <b>photo</b> image file, or tap Cancel below.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Cancel", callback_data="adm_cancel_settings", style="danger")
        ]])
    )


@router.callback_query(F.data == "adm_start_find")
async def adm_cb_start_find(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.set_state(AdminFindStates.waiting_for_input)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await state.update_data(panel_msg_id=query.message.message_id)
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                "<b>Find Customer</b>\n"
                "\n"
                "Send Telegram ID (e.g. <code>100200300</code>) or <code>@username</code>.\n\n"
                "Tap Cancel below to abort.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
                    InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger")
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
            "<b>Group invite rejected</b>\n"
            "\n"
            f"{html.escape(chat.title or 'Unknown')} · <code>{chat.id}</code>\n"
            f"Added by <code>{actor_id}</code>\n\n"
            "<i>The bot left. Groups are never allowed.</i>",
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
                "<b>Unauthorised channel</b>\n"
                "\n"
                f"{html.escape(chat.title or 'Unknown')}"
                f"{' · @' + chat_user if chat_user else ''} · <code>{chat.id}</code>\n"
                f"Added by <code>{actor_id}</code>\n\n"
                "<i>The bot left, so nothing can be broadcast from it. Add the channel in "
                "Settings → Channels first.</i>",
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





def _confirm_keyboard(yes_data: str, label: str = "Confirm", danger: bool = False, back_data: str = "adm_cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text=label,
                callback_data=yes_data,
                style="danger" if danger else "success",
            ),
            InlineKeyboardButton(text="Back", callback_data=back_data),
        ]]
    )


@router.callback_query(F.data == "adm_cancel")
async def adm_cancel(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer("Cancelled.")
    text, keyboard = await build_admin_dashboard(services)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


def _format_deposit_card(deposit: dict, symbol: str, back_cb: str = "adm_queue_dep") -> tuple[str, InlineKeyboardMarkup]:
    cust_handle = f"@{html.escape(deposit['username'])}" if deposit.get("username") else "No username"
    amount = f"{float(deposit['amount']):.2f} {symbol}"
    method_name = html.escape(str(deposit.get("method_name") or "N/A"))
    trx_id = html.escape(str(deposit.get("transaction_id") or "N/A"))
    dep_id = deposit["id"]
    status_raw = str(deposit.get("status") or "pending")
    status_badge = {
        "pending": "Pending",
        "approved": "Approved",
        "rejected": "Rejected",
    }.get(status_raw, status_raw.title())

    created_at = deposit.get("created_at")
    time_str = created_at.strftime("%d %b %Y, %I:%M %p") if hasattr(created_at, "strftime") else ""
    time_line = f"\n<b>Submitted:</b> <code>{time_str}</code>" if time_str else ""

    text = (
        f"<b>Deposit Details {format_deposit_id(dep_id)}</b>\n\n"
        f"<b>Customer:</b> {cust_handle}\n"
        f"<b>Customer ID:</b> <code>{deposit['tg_user_id']}</code>\n"
        f"<b>Method:</b> {method_name}\n"
        f"<b>Amount:</b> <code>{amount}</code>\n"
        f"<b>TrxID:</b> <code>{trx_id}</code>\n"
        f"<b>Status:</b> {status_badge}"
        f"{time_line}"
    )
    if deposit.get("admin_note"):
        text += f"\n\n<b>Note:</b> <i>{html.escape(deposit['admin_note'])}</i>"

    from app.core.config import get_settings
    console = get_settings().console_url
    rows: list[list[InlineKeyboardButton]] = []
    if status_raw == "pending":
        rows.append([
            InlineKeyboardButton(
                text="Approve",
                callback_data=f"adm_dep_ask_approve_{dep_id}",
                style="success",
            ),
            InlineKeyboardButton(
                text="Reject",
                callback_data=f"adm_dep_ask_reject_{dep_id}",
                style="danger",
            ),
        ])
    if console:
        rows.append([
            InlineKeyboardButton(
                text="Open in Console",
                url=f"{console}/#deposits",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="Back",
            callback_data=back_cb,
            style="primary",
        )
    ])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def _deposit_summary(services: Services, deposit_id: int) -> dict | None:
    async with services.db.connect() as conn:
        row = await conn.fetchrow(
            "SELECT d.*, u.username FROM deposits d LEFT JOIN users u ON u.id = d.user_id WHERE d.id = $1",
            deposit_id,
        )
    return dict(row) if row else None


async def _order_summary(services: Services, order_id: int) -> dict | None:
    async with services.db.connect() as conn:
        row = await conn.fetchrow(
            "SELECT o.id, o.product_title, o.price, o.status, o.fulfillment, o.source, "
            "o.supplier_code, o.supplier_error, o.product_id, "
            "o.tg_user_id, o.created_at, u.username "
            "FROM orders o LEFT JOIN users u ON u.tg_user_id = o.tg_user_id "
            "WHERE o.id = $1",
            order_id,
        )
    return dict(row) if row else None


def _format_order_card(order: dict, symbol: str, back_cb: str = "adm_queue_ord") -> tuple[str, InlineKeyboardMarkup]:
    from app.core.config import get_settings
    console = get_settings().console_url
    order_id = order["id"]
    cust_handle = f"@{html.escape(order['username'])}" if order.get("username") else f"<code>{order['tg_user_id']}</code>"
    amount = f"{float(order['price']):.2f} {symbol}"
    product_title = html.escape(str(order.get("product_title") or "N/A"))
    fulfillment = str(order.get("fulfillment") or "delivered")
    status = str(order.get("status") or "completed")

    created_at = order.get("created_at")
    time_str = created_at.strftime("%d %b %Y, %I:%M %p") if hasattr(created_at, "strftime") else ""
    time_line = f"\n<b>Ordered:</b> <code>{time_str}</code>" if time_str else ""

    sup_info = ""
    if order.get("supplier_code"):
        sup_info += f"\n<b>Supplier:</b> <code>{html.escape(str(order['supplier_code']))}</code>"
    if order.get("supplier_error"):
        sup_info += f"\n<b>Supplier Issue:</b> <code>{html.escape(str(order['supplier_error']))}</code>"

    cust_input_line = ""
    if order.get("customer_input"):
        cust_input_line = f"\n<b>Customer Info:</b> <code>{html.escape(str(order['customer_input']))}</code>"

    text = (
        f"<b>Order Details {format_order_id(order_id)}</b>\n\n"
        f"<b>Customer:</b> {cust_handle}\n"
        f"<b>Customer ID:</b> <code>{order['tg_user_id']}</code>\n"
        f"<b>Product:</b> {product_title}\n"
        f"<b>Price:</b> <code>{amount}</code>"
        f"{cust_input_line}\n"
        f"<b>Status:</b> <code>{status.title()}</code>\n"
        f"<b>Delivery:</b> {fulfillment.title()}"
        f"{sup_info}"
        f"{time_line}"
    )
    rows: list[list[InlineKeyboardButton]] = []
    if status == "completed" and fulfillment == "waiting":
        is_supplier = bool(
            order.get("supplier_code")
            or order.get("supplier_error")
            or order.get("source") in ("supplier_pending", "upstream_fallback", "upstream_reseller")
        )
        if is_supplier:
            rows.append([
                InlineKeyboardButton(
                    text="Retry Supplier Delivery",
                    callback_data=f"adm_ord_sup_retry_{order_id}",
                    style="primary",
                )
            ])
        rows.append([
            InlineKeyboardButton(
                text="Deliver Manually",
                callback_data=f"adm_ord_deliver_{order_id}",
                style="success",
            ),
            InlineKeyboardButton(
                text="Refund",
                callback_data=f"adm_ord_ref_ask_{order_id}",
                style="danger",
            ),
        ])
    if console:
        rows.append([
            InlineKeyboardButton(
                text="Open in Console",
                url=f"{console}/#orders/{order_id}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="Back",
            callback_data=back_cb,
            style="primary",
        )
    ])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.regexp(r"^adm_ord_(view|back)_\d+$"))
async def adm_ord_view(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    raw_id = re.sub(r"^adm_ord_(view|back)_", "", query.data)
    if not raw_id.isdigit():
        return
    order = await _order_summary(services, int(raw_id))
    if not order:
        with suppress(TelegramBadRequest):
            await query.answer("That order no longer exists.", show_alert=True)
        return

    symbol = html.escape(await services.settings.get("currency_symbol"))
    text, keyboard = _format_order_card(order, symbol, back_cb="adm_queue_ord")
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^adm_dep_ask_(approve|reject)_\d+(_q)?$"))
async def adm_deposit_ask(query: CallbackQuery, services: Services):
    """Crediting a wallet is money in. Say what is about to happen first."""
    if await _deny(query, services):
        return
    data_str = query.data.removeprefix("adm_dep_ask_")
    parts = data_str.split("_")
    action = parts[0]
    raw_id = parts[1]
    from_queue = len(parts) > 2 and parts[2] == "q"
    back_cb = "adm_queue_dep" if from_queue else f"adm_dep_view_{raw_id}"

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
    method_name = html.escape(str(deposit.get("method_name") or "N/A"))
    trx_id = html.escape(str(deposit.get("transaction_id") or "N/A"))

    if action == "approve":
        text = (
            "<b>Confirm Deposit Approval</b>\n"
            "\n"
            f"<b>Customer:</b> {cust_handle}\n"
            f"<b>Customer ID:</b> <code>{deposit['tg_user_id']}</code>\n"
            f"<b>Method:</b> {method_name}\n"
            f"<b>Amount:</b> <code>{amount}</code>\n"
            f"<b>TrxID:</b> <code>{trx_id}</code>\n\n"
            "<i>Check money arrived before approving.</i>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm", callback_data=f"adm_dep_do_approve_{raw_id}", style="success"),
            ],
            [
                InlineKeyboardButton(text="Back", callback_data=back_cb),
            ],
        ])
    else:
        text = (
            "<b>Confirm Deposit Rejection</b>\n"
            "\n"
            f"<b>Customer:</b> {cust_handle}\n"
            f"<b>Customer ID:</b> <code>{deposit['tg_user_id']}</code>\n"
            f"<b>Method:</b> {method_name}\n"
            f"<b>Amount:</b> <code>{amount}</code>\n"
            f"<b>TrxID:</b> <code>{trx_id}</code>\n\n"
            "<i>Customer will be told it could not be verified.</i>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm", callback_data=f"adm_dep_do_reject_{raw_id}", style="danger"),
            ],
            [
                InlineKeyboardButton(text="Back", callback_data=back_cb),
            ],
        ])

    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^adm_dep_(view|back)_\d+$"))
async def adm_dep_view(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    raw_id = re.sub(r"^adm_dep_(view|back)_", "", query.data)
    if not raw_id.isdigit():
        return
    deposit = await _deposit_summary(services, int(raw_id))
    if not deposit:
        with suppress(TelegramBadRequest):
            await query.answer("That deposit no longer exists.", show_alert=True)
        return

    symbol = html.escape(await services.settings.get("currency_symbol"))
    text, keyboard = _format_deposit_card(deposit, symbol, back_cb="adm_queue_dep")
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

    deposit = await _deposit_summary(services, deposit_id)
    if not deposit:
        with suppress(TelegramBadRequest):
            await query.answer("That deposit no longer exists.", show_alert=True)
        return

    if action == "approve":
        ok, message, _ = await services.deposits.approve(deposit_id, f"Approved from Telegram by {by}")
    else:
        ok, message, _ = await services.deposits.reject(deposit_id, "Transaction could not be verified.")

    with suppress(TelegramBadRequest):
        await query.answer(message[:180], show_alert=not ok)
    if query.message:
        symbol = html.escape(await services.settings.get("currency_symbol"))
        cust_handle = f"@{html.escape(deposit['username'])}" if deposit.get("username") else "No username"
        amount = f"{float(deposit['amount']):.2f} {symbol}"
        method_name = html.escape(str(deposit.get("method_name") or "N/A"))
        trx_id = html.escape(str(deposit.get("transaction_id") or "N/A"))

        if ok:
            header = (
                f"<b>Deposit {format_deposit_id(deposit_id)} Approved</b>"
                if action == "approve"
                else f"<b>Deposit {format_deposit_id(deposit_id)} Rejected</b>"
            )
        else:
            header = f"<b>Deposit {format_deposit_id(deposit_id)}</b>"

        text = (
            f"{header}\n"
            "\n"
            f"<b>Customer:</b> {cust_handle}\n"
            f"<b>Customer ID:</b> <code>{deposit['tg_user_id']}</code>\n"
            f"<b>Method:</b> {method_name}\n"
            f"<b>Amount:</b> <code>{amount}</code>\n"
            f"<b>TrxID:</b> <code>{trx_id}</code>\n"
            "\n"
            f"<i>{html.escape(message)}</i>"
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Pending Deposits", callback_data="adm_queue_dep"),
            ],
            [
                InlineKeyboardButton(text="Back to Admin", callback_data="adm_dashboard"),
            ],
        ])
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=reply_markup)


@router.callback_query(F.data.regexp(r"^adm_ord_deliver_\d+(_q)?$"))
async def adm_order_deliver(query: CallbackQuery, state: FSMContext, services: Services):
    """Manual orders are paid and waiting. Send what the customer bought here."""
    if await _deny(query, services):
        return
    parts = query.data.removeprefix("adm_ord_deliver_").split("_")
    order_id = int(parts[0])
    from_queue = len(parts) > 1 and parts[1] == "q"
    back_cb = "adm_queue_ord" if from_queue else f"adm_ord_back_{order_id}"

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
    await state.update_data(deliver_order_id=order_id, deliver_asked_at=time.time(), from_queue=from_queue)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        await state.update_data(panel_msg_id=query.message.message_id)
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"<b>Deliver Order {format_order_id(order_id)}</b>\n"
                "\n"
                f"<b>Product:</b> {html.escape(order['product_title'])}\n\n"
                "Send credentials or item to deliver below:\n"
                "<i>(Tap Cancel below to stop)</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Back", callback_data=back_cb),
                    InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger")
                ]])
            )


@router.message(AdminOpsStates.waiting_for_delivery)
async def adm_order_deliver_send(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text = (message.text or message.caption or "").strip()
    if is_navigation(text):
        await navigate(text, message, state, services)
        return
    data = await state.get_data()
    panel_msg_id = data.get("panel_msg_id")

    asked_at = float(data.get("deliver_asked_at") or 0)
    if not asked_at or time.time() - asked_at > DELIVERY_PROMPT_SECONDS:
        await state.clear()
        if panel_msg_id:
            with suppress(Exception):
                await message.delete()
            from_queue = data.get("from_queue", False)
            if from_queue:
                text_queue, keyboard = await build_queue_view(services, "orders")
            else:
                order = await _order_summary(services, int(data.get("deliver_order_id") or 0))
                if order:
                    symbol = html.escape(await services.settings.get("currency_symbol"))
                    text_queue, keyboard = _format_order_card(order, symbol)
                else:
                    text_queue, keyboard = await build_queue_view(services, "orders")
            with suppress(TelegramBadRequest):
                await message.bot.edit_message_text(
                    text="That delivery prompt expired. Tap <b>Deliver</b> again.\n\n" + text_queue,
                    chat_id=message.chat.id,
                    message_id=panel_msg_id,
                    reply_markup=keyboard,
                )
            return
        await message.answer(
            "<b>Nothing was sent</b>\n"
            "\n"
            "That delivery prompt expired, so this message was not passed on.\n"
            "Tap <b>Deliver</b> on the order again."
        )
        return

    # A command typed here is a command, never something to deliver.
    if text.startswith("/"):
        await state.clear()
        cmd = text.split()[0].lower().lstrip("/").split("@")[0]
        with suppress(Exception):
            await message.delete()
        if cmd == "cancel":
            if panel_msg_id:
                from_queue = data.get("from_queue", False)
                if from_queue:
                    text_cancel, keyboard = await build_queue_view(services, "orders")
                else:
                    order = await _order_summary(services, int(data.get("deliver_order_id") or 0))
                    if order:
                        symbol = html.escape(await services.settings.get("currency_symbol"))
                        text_cancel, keyboard = _format_order_card(order, symbol)
                    else:
                        text_cancel, keyboard = await build_queue_view(services, "orders")
                with suppress(TelegramBadRequest):
                    await message.bot.edit_message_text(
                        text=text_cancel,
                        chat_id=message.chat.id,
                        message_id=panel_msg_id,
                        reply_markup=keyboard,
                    )
            else:
                await message.answer("Cancelled. The order is still waiting.")
        elif cmd in ("status", "st"):
            await cmd_status(message, services)
        elif cmd == "admin":
            if panel_msg_id:
                text_dash, keyboard = await build_admin_dashboard(services)
                with suppress(TelegramBadRequest):
                    await message.bot.edit_message_text(
                        text=text_dash,
                        chat_id=message.chat.id,
                        message_id=panel_msg_id,
                        reply_markup=keyboard,
                    )
            else:
                await cmd_admin_help(message, services)
        else:
            await message.answer(
                "<b>Nothing was sent</b>\n"
                "\n"
                f"<code>{html.escape(text.split()[0])}</code> looks like a command, so it was not "
                "delivered to the customer. Tap <b>Deliver</b> again to retry."
            )
        return
    if not text:
        await message.answer(
            "Send the credentials as text, or tap Cancel below.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger")
            ]])
        )
        return

    order_id = int(data.get("deliver_order_id") or 0)
    try:
        await services.purchases.fulfill_manually(order_id, text)
    except Exception as exc:
        await message.answer(f"Could not deliver: {html.escape(str(exc))}")
        return
    await state.clear()

    conf_text = (
        f"<b>Order {format_order_id(order_id)} Delivered</b>\n"
        "\n"
        "<i>Item delivered to customer successfully.</i>"
    )
    conf_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Pending Deliveries", callback_data="adm_queue_ord"),
        ],
        [
            InlineKeyboardButton(text="Back to Admin", callback_data="adm_dashboard"),
        ],
    ])
    if panel_msg_id:
        with suppress(Exception):
            await message.delete()
        try:
            await message.bot.edit_message_text(
                text=conf_text,
                chat_id=message.chat.id,
                message_id=panel_msg_id,
                reply_markup=conf_keyboard,
            )
            return
        except Exception:
            pass
    await message.answer(conf_text, reply_markup=conf_keyboard)


# ── Quick controls ──────────────────────────────────────────────────────────


@router.message(Command("status", "st"))
async def cmd_status(message: Message, services: Services):
    """The one thing worth checking while away from the desk."""
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    text, keyboard = await build_store_status_view(services)
    await message.answer(text, reply_markup=keyboard)





async def _handle_find_customer(message: Message, term: str, services: Services, panel_msg_id: int | None = None):
    if not term:
        text = (
            "<b>Find Customer</b>\n\n"
            "Please provide a customer ID or @username to search.\n"
            "Example: <code>/find 100200300</code> or <code>/find @username</code>"
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ]])
        if panel_msg_id:
            with suppress(Exception):
                await message.delete()
            try:
                await message.bot.edit_message_text(text=text, chat_id=message.chat.id, message_id=panel_msg_id, reply_markup=reply_markup)
                return
            except Exception:
                pass
        await message.answer(text, reply_markup=reply_markup)
        return

    async with services.db.connect() as conn:
        if term.isdigit():
            row = await conn.fetchrow("SELECT tg_user_id FROM users WHERE tg_user_id = $1", int(term))
        else:
            row = await conn.fetchrow(
                "SELECT tg_user_id FROM users WHERE lower(username) = lower($1)", term.lstrip("@"))
    if not row:
        text = (
            "<b>Customer Not Found</b>\n\n"
            f"No customer matches <code>{html.escape(term)}</code>.\n"
            "Please check the ID or username and try again."
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Search Again", callback_data="adm_start_find"),
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
        ]])
        if panel_msg_id:
            with suppress(Exception):
                await message.delete()
            try:
                await message.bot.edit_message_text(text=text, chat_id=message.chat.id, message_id=panel_msg_id, reply_markup=reply_markup)
                return
            except Exception:
                pass
        await message.answer(text, reply_markup=reply_markup)
        return

    found = await services.users.stats(row["tg_user_id"])
    if not found:
        text = (
            "<b>Customer Profile Error</b>\n\n"
            f"Could not read records for user <code>{row['tg_user_id']}</code>.\n"
            "Please try again or inspect in the admin console."
        )
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ]])
        if panel_msg_id:
            with suppress(Exception):
                await message.delete()
            try:
                await message.bot.edit_message_text(text=text, chat_id=message.chat.id, message_id=panel_msg_id, reply_markup=reply_markup)
                return
            except Exception:
                pass
        await message.answer(text, reply_markup=reply_markup)
        return
    user = found["user"]
    is_admin_target = int(user["tg_user_id"]) in await services.settings.admin_chat_ids()
    symbol = html.escape(await services.settings.get("currency_symbol"))
    name = html.escape(" ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "No name")
    handle = f"@{html.escape(user['username'])}" if user.get("username") else "no username"
    banned_tag = " · <b>BANNED</b>" if user.get("is_banned") else ""
    is_banned = bool(user.get("is_banned"))

    buttons = []
    if not is_admin_target:
        buttons.append([
            InlineKeyboardButton(
                text="Unban Customer" if is_banned else "Ban Customer",
                callback_data=f"adm_ban_ask_{user['tg_user_id']}",
                style="success" if is_banned else "danger",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
    ])

    text = (
        "<b>Customer Profile</b>\n\n"
        f"<b>Name:</b> {name} ({handle})\n"
        f"<b>Customer ID:</b> <code>{user['tg_user_id']}</code>\n"
        f"<b>Rank:</b> {html.escape(user.get('rank') or 'Standard')}{banned_tag}\n"
        f"<b>Balance:</b> <code>{float(user.get('balance') or 0):.2f} {symbol}</code>\n"
        f"<b>Orders:</b> <code>{found['order_count']}</code> · <b>Spent:</b> <code>{float(found['total_spent'] or 0):.2f} {symbol}</code>"
        + ("\n\n<i>Administrator account.</i>" if is_admin_target else "")
    )
    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if panel_msg_id:
        with suppress(Exception):
            await message.delete()
        try:
            await message.bot.edit_message_text(text=text, chat_id=message.chat.id, message_id=panel_msg_id, reply_markup=reply_markup)
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=reply_markup)


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
    data = await state.get_data()
    panel_msg_id = data.get("panel_msg_id")

    if is_navigation(text):
        await state.clear()
        await navigate(text, message, state, services)
        return
    if text.startswith("/"):
        cmd = text.split()[0].lower().lstrip("/").split("@")[0]
        await state.clear()
        with suppress(Exception):
            await message.delete()
        if cmd in ("cancel", "admin"):
            if panel_msg_id:
                text_dash, keyboard = await build_admin_dashboard(services)
                with suppress(TelegramBadRequest):
                    await message.bot.edit_message_text(
                        text=text_dash,
                        chat_id=message.chat.id,
                        message_id=panel_msg_id,
                        reply_markup=keyboard,
                    )
            else:
                await cmd_admin_help(message, services)
            return
        elif cmd in ("status", "st"):
            await cmd_status(message, services)
            return
    await state.clear()
    await _handle_find_customer(message, text, services, panel_msg_id=panel_msg_id)


# ──── The work queue ──────────────────────────────────────────────────
# The panel used to report how much was waiting without offering a way to reach it:
# the Approve and Deliver buttons lived only on the alert, so a missed alert meant
# opening the console. These turn the counts into the list they were counting.


async def build_queue_view(services: Services, kind: str = "all", page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    """One list or the other, or both.

    Renders items as individual clickable buttons that open their detail cards,
    just like products, allowing admins to inspect full information before acting."""
    symbol = html.escape(await services.settings.get("currency_symbol"))
    async with services.db.connect() as conn:
        deposits = await conn.fetch(
            "SELECT d.id, d.amount, d.transaction_id, d.method_name, d.created_at, u.username, u.tg_user_id "
            "FROM deposits d LEFT JOIN users u ON u.id = d.user_id "
            "WHERE d.status = 'pending' ORDER BY d.id"
        ) if kind in ("all", "deposits") else []
        orders = await conn.fetch(
            "SELECT o.id, o.product_title, o.price, o.fulfillment, o.created_at, u.username, u.tg_user_id "
            "FROM orders o LEFT JOIN users u ON u.tg_user_id = o.tg_user_id "
            "WHERE o.status = 'completed' AND o.fulfillment = 'waiting' "
            "ORDER BY o.id"
        ) if kind in ("all", "orders") else []

    rows: list[list[InlineKeyboardButton]] = []

    if kind == "deposits":
        page_size = 5
        total_pages = max(1, (len(deposits) + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        page_items = deposits[page * page_size : (page + 1) * page_size]

        for d in page_items:
            who = f"@{html.escape(d['username'])}" if d['username'] else f"{d['tg_user_id']}"
            amt_str = f"{float(d['amount']):.2f} {symbol}"
            btn_text = f"{format_deposit_id(d['id'])} · {amt_str} · {who}"[:60]
            rows.append([
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"adm_dep_view_{d['id']}",
                    style="primary",
                )
            ])

        if total_pages > 1:
            nav_row: list[InlineKeyboardButton] = []
            if page > 0:
                nav_row.append(InlineKeyboardButton(text="Prev", callback_data=f"adm_queue_dep_page_{page - 1}"))
            nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="adm_noop"))
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton(text="Next", callback_data=f"adm_queue_dep_page_{page + 1}"))
            rows.append(nav_row)

        rows.append([
            InlineKeyboardButton(text="Deliveries Queue", callback_data="adm_queue_ord"),
        ])
        rows.append([
            InlineKeyboardButton(text="Refresh", callback_data=f"adm_queue_dep_page_{page}"),
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ])

        if deposits:
            text = (
                f"<b>Pending Deposits ({len(deposits)})</b>\n\n"
                "<i>Select a deposit to review full details and take action:</i>"
            )
        else:
            text = (
                "<b>Pending Deposits (0)</b>\n\n"
                "All clear! Nothing waiting on you."
            )
        return text, InlineKeyboardMarkup(inline_keyboard=rows)

    elif kind == "orders":
        page_size = 5
        total_pages = max(1, (len(orders) + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        page_items = orders[page * page_size : (page + 1) * page_size]

        for o in page_items:
            amt_str = f"{float(o['price']):.2f} {symbol}"
            prod_title = html.escape(str(o.get("product_title") or "Item"))[:20]
            btn_text = f"{format_order_id(o['id'])} · {prod_title} · {amt_str}"[:60]
            rows.append([
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"adm_ord_view_{o['id']}",
                    style="primary",
                )
            ])

        if total_pages > 1:
            nav_row: list[InlineKeyboardButton] = []
            if page > 0:
                nav_row.append(InlineKeyboardButton(text="Prev", callback_data=f"adm_queue_ord_page_{page - 1}"))
            nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="adm_noop"))
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton(text="Next", callback_data=f"adm_queue_ord_page_{page + 1}"))
            rows.append(nav_row)

        rows.append([
            InlineKeyboardButton(text="Deposits Queue", callback_data="adm_queue_dep"),
        ])
        rows.append([
            InlineKeyboardButton(text="Refresh", callback_data=f"adm_queue_ord_page_{page}"),
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ])

        if orders:
            text = (
                f"<b>Pending Deliveries ({len(orders)})</b>\n\n"
                "<i>Select an order to review full details and deliver or refund:</i>"
            )
        else:
            text = (
                "<b>Pending Deliveries (0)</b>\n\n"
                "All clear! Nothing waiting on you."
            )
        return text, InlineKeyboardMarkup(inline_keyboard=rows)

    else:
        # kind == "all"
        lines = []
        if deposits:
            lines.append(f"<b>Pending Deposits ({len(deposits)}):</b>")
            for d in deposits[:4]:
                who = f"@{html.escape(d['username'])}" if d['username'] else f"{d['tg_user_id']}"
                amt_str = f"{float(d['amount']):.2f} {symbol}"
                rows.append([
                    InlineKeyboardButton(
                        text=f"Deposit {format_deposit_id(d['id'])} · {amt_str} · {who}"[:60],
                        callback_data=f"adm_dep_view_{d['id']}",
                        style="primary",
                    )
                ])
        if orders:
            if lines:
                lines.append("")
            lines.append(f"<b>Pending Deliveries ({len(orders)}):</b>")
            for o in orders[:4]:
                amt_str = f"{float(o['price']):.2f} {symbol}"
                prod_title = html.escape(str(o.get("product_title") or "Item"))[:18]
                rows.append([
                    InlineKeyboardButton(
                        text=f"Order {format_order_id(o['id'])} · {prod_title} · {amt_str}"[:60],
                        callback_data=f"adm_ord_view_{o['id']}",
                        style="primary",
                    )
                ])
        if not deposits and not orders:
            lines.append("All clear! Nothing waiting on you.")

        rows.append([
            InlineKeyboardButton(text="Refresh", callback_data="adm_queue"),
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ])

        text = (
            "<b>Needs Attention</b>\n\n"
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
    text, keyboard = await build_queue_view(services, kind, page=0)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^adm_queue_(dep|ord)_page_\d+$"))
async def adm_cb_queue_page(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    m = re.match(r"^adm_queue_(dep|ord)_page_(\d+)$", query.data)
    if not m:
        return
    kind = "deposits" if m.group(1) == "dep" else "orders"
    page = int(m.group(2))
    text, keyboard = await build_queue_view(services, kind, page=page)
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
                f"<b>Checked {checked} unpaid invoice(s)</b>\n"
                "\n"
                f"<i>Confirmed payments credit automatically.</i>{note}\n\n"
                + text,
                reply_markup=keyboard)


# ──── Refund ──────────────────────────────────────────────────────────
# Money leaving the shop, so it asks first, the same as crediting one does.


@router.callback_query(F.data.regexp(r"^adm_ord_ref_ask_\d+(_q)?$"))
async def adm_order_refund_ask(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    parts = query.data.removeprefix("adm_ord_ref_ask_").split("_")
    order_id = int(parts[0])
    from_queue = len(parts) > 1 and parts[1] == "q"
    cancel_cb = "adm_queue_ord" if from_queue else f"adm_ord_back_{order_id}"

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
                "<b>Confirm Order Refund</b>\n"
                "\n"
                f"<b>Product:</b> {html.escape(order['product_title'])}\n"
                f"<b>Refund Amount:</b> <code>{amount}</code>\n\n"
                "<i>Amount will be refunded to customer's wallet.</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Confirm", callback_data=f"adm_ord_ref_do_{order_id}",
                                             style="danger"),
                    ],
                    [
                        InlineKeyboardButton(text="Back", callback_data=cancel_cb),
                    ],
                ]))


@router.callback_query(F.data.regexp(r"^adm_ord_ref_do_\d+$"))
async def adm_order_refund_do(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    order_id = int(query.data.removeprefix("adm_ord_ref_do_"))
    ok, message = await services.purchases.refund(order_id)
    with suppress(TelegramBadRequest):
        await query.answer(message[:180], show_alert=not ok)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"<b>Order {format_order_id(order_id)}</b>\n"
                "\n"
                f"<i>{html.escape(message)}</i>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Pending Deliveries", callback_data="adm_queue_ord"),
                    ],
                    [
                        InlineKeyboardButton(text="Back to Admin", callback_data="adm_dashboard"),
                    ],
                ]))


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


@router.callback_query(F.data.regexp(r"^adm_ord_sup_retry_\d+$"))
async def adm_order_supplier_retry(query: CallbackQuery, services: Services):
    """Admin clicked to retry upstream supplier fulfillment."""
    if await _deny(query, services):
        return
    order_id = int(query.data.removeprefix("adm_ord_sup_retry_"))
    with suppress(TelegramBadRequest):
        await query.answer("Retrying with supplier...")

    success, msg, _ = await services.purchases.retry_supplier_fulfillment(order_id)
    if success:
        with suppress(TelegramBadRequest):
            await query.answer(f"✅ {msg}", show_alert=True)
        order = await _order_summary(services, order_id)
        if order and query.message:
            symbol = html.escape(await services.settings.get("currency_symbol"))
            text, keyboard = _format_order_card(order, symbol, back_cb="adm_queue_ord")
            with suppress(TelegramBadRequest):
                await query.message.edit_text(text, reply_markup=keyboard)
    else:
        with suppress(TelegramBadRequest):
            await query.answer(f"❌ {msg}", show_alert=True)


async def build_stock_overview_view(services: Services, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    products = await services.catalog.products(active_only=False, limit=200)
    threshold = int(await services.settings.number("low_stock_threshold") or 3)

    out_of_stock = [p for p in products if p.get("stock") is not None and int(p["stock"] or 0) == 0]
    low_stock = [p for p in products if p.get("stock") is not None and 0 < int(p["stock"] or 0) <= threshold]
    healthy_stock = [p for p in products if p.get("stock") is None or int(p["stock"] or 0) > threshold]

    # Priority sorting: out of stock first, then low stock, then healthy
    ordered = out_of_stock + low_stock + healthy_stock

    page_size = 6
    total_pages = max(1, (len(ordered) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    page_items = ordered[page * page_size : (page + 1) * page_size]

    rows: list[list[InlineKeyboardButton]] = []
    for p in page_items:
        stk = p.get("stock")
        if stk is None:
            badge = "Unlimited"
            style = "primary"
        elif int(stk) == 0:
            badge = "0 in stock"
            style = "danger"
        elif int(stk) <= threshold:
            badge = f"{stk} in stock"
            style = "primary"
        else:
            badge = f"{stk} in stock"
            style = "success"

        title = p["title"][:22]
        btn_kwargs = {
            "text": f"{title} · {badge}"[:64],
            "callback_data": f"adm_stock_{p['id']}",
            "style": style,
        }
        rows.append([InlineKeyboardButton(**btn_kwargs)])

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="Prev", callback_data=f"adm_stock_page_{page - 1}"))
        nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="adm_noop"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="Next", callback_data=f"adm_stock_page_{page + 1}"))
        rows.append(nav_row)

    rows.append([
        InlineKeyboardButton(text="Refresh", callback_data=f"adm_stock_page_{page}"),
        InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
    ])

    text = (
        "<b>Stock Management</b>\n"
        "\n"
        f"<b>Total Products:</b> <code>{len(products)}</code>\n"
        f"<b>Out of Stock:</b> <code>{len(out_of_stock)}</code>\n"
        f"<b>Low Stock:</b> <code>{len(low_stock)}</code>\n"
        f"<b>In Stock:</b> <code>{len(healthy_stock)}</code>"
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm_start_stock")
async def adm_cb_start_stock(query: CallbackQuery, state: FSMContext, services: Services):
    if await _deny(query, services):
        return
    await state.clear()
    text, keyboard = await build_stock_overview_view(services, page=0)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.regexp(r"^adm_stock_page_\d+$"))
async def adm_cb_stock_page(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    page = int(query.data.removeprefix("adm_stock_page_"))
    text, keyboard = await build_stock_overview_view(services, page=page)
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "adm_noop")
async def adm_cb_noop(query: CallbackQuery):
    with suppress(TelegramBadRequest):
        await query.answer()



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
        await state.update_data(panel_msg_id=query.message.message_id)
        symbol = html.escape(await services.settings.get("currency_symbol"))
        stock = product.get("stock")
        stock_str = f"<code>{stock}</code> items available" if stock is not None else "<i>Unlimited / Manual</i>"
        price_str = f"<code>{float(product['price']):.2f} {symbol}</code>"
        status_str = "On sale" if product["is_active"] else "Hidden"

        text = (
            "<b>Add Stock</b>\n"
            "\n"
            f"<b>Product:</b> {html.escape(product['title'])}\n"
            f"<b>Price:</b> {price_str}\n"
            f"<b>Current Stock:</b> {stock_str}\n"
            f"<b>Status:</b> {status_str}\n"
            "\n"
            "<b>How to add stock:</b>\n"
            "1. <b>Paste text:</b> Send accounts, keys or codes — one item per line.\n"
            "2. <b>Upload a file:</b> Send a <code>.txt</code> file instead.\n\n"
            "<b>Shared items?</b> Add <code>uses:N</code> as the first line.\n\n"
            "<b>Example (single use):</b>\n"
            "<code>user1@email.com:pass1</code>\n"
            "<code>user2@email.com:pass2</code>\n\n"
            "<b>Example (shared, 3 users each):</b>\n"
            "<code>uses:3</code>\n"
            "<code>user1@email.com:pass1</code>\n"
            "<code>user2@email.com:pass2</code>"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="View Stock Items", callback_data=f"adm_stock_items_{product_id}"),
            ],
            [
                InlineKeyboardButton(text="Back", callback_data="adm_start_stock"),
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
            ],
        ])
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)





@router.callback_query(F.data.regexp(r"^adm_stock_items_\d+$"))
async def adm_cb_stock_items(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    product_id = int(query.data.removeprefix("adm_stock_items_"))
    product = await services.catalog.product(product_id)
    if not product:
        with suppress(TelegramBadRequest):
            await query.answer("That product no longer exists.", show_alert=True)
        return

    items, total_count, summary = await services.inventory.items(product_id=product_id, status="available", limit=8)
    with suppress(TelegramBadRequest):
        await query.answer()

    lines = []
    if items:
        for idx, it in enumerate(items, 1):
            content = it["content"]
            if ":" in content:
                user_part, pass_part = content.split(":", 1)
                masked_pass = pass_part[:2] + "***" if len(pass_part) > 2 else "***"
                display_content = f"{html.escape(user_part)}:{masked_pass}"
            elif len(content) > 30:
                display_content = html.escape(content[:26]) + "..."
            else:
                display_content = html.escape(content)
            lines.append(f"{idx}. <code>{display_content}</code>")
    else:
        lines.append("<i>No items currently in stock.</i>")

    text = (
        "<b>Stock Items Preview</b>\n"
        "\n"
        f"<b>Product:</b> {html.escape(product['title'])}\n"
        f"<b>Available:</b> <code>{summary.get('available_units', 0)}</code>  ·  "
        f"<b>Sold:</b> <code>{summary.get('sold_units', 0)}</code>\n"
        "\n"
        "<b>Available items (up to 8):</b>\n"
        + "\n".join(lines)
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Add Stock", callback_data=f"adm_stock_{product_id}", style="success"),
        ],
        [
            InlineKeyboardButton(text="Back", callback_data="adm_start_stock"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ],
    ])
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.message(AdminProductStates.waiting_for_stock)
async def adm_stock_save(message: Message, state: FSMContext, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return
    data = await state.get_data()
    panel_msg_id = data.get("panel_msg_id")
    product_id = int(data.get("stock_product_id") or 0)

    asked_at = float(data.get("stock_asked_at") or 0)
    if not asked_at or time.time() - asked_at > DELIVERY_PROMPT_SECONDS:
        await state.clear()
        if panel_msg_id:
            with suppress(Exception):
                await message.delete()
            text_stock, keyboard = await build_stock_overview_view(services)
            with suppress(TelegramBadRequest):
                await message.bot.edit_message_text(
                    text="That prompt expired. Tap <b>Add stock</b> again.\n\n" + text_stock,
                    chat_id=message.chat.id,
                    message_id=panel_msg_id,
                    reply_markup=keyboard,
                )
            return
        await message.answer("That prompt expired. Tap <b>Add stock</b> again.")
        return

    text_input = (message.text or message.caption or "").strip()
    if is_navigation(text_input) or text_input.startswith("/"):
        await state.clear()
        with suppress(Exception):
            await message.delete()
        if text_input.lower().startswith("/cancel"):
            if panel_msg_id:
                text_stock, keyboard = await build_stock_overview_view(services)
                with suppress(TelegramBadRequest):
                    await message.bot.edit_message_text(
                        text=text_stock,
                        chat_id=message.chat.id,
                        message_id=panel_msg_id,
                        reply_markup=keyboard,
                    )
            else:
                await message.answer("Cancelled. No stock was added.")
        elif text_input.lower().startswith("/admin"):
            if panel_msg_id:
                text_dash, keyboard = await build_admin_dashboard(services)
                with suppress(TelegramBadRequest):
                    await message.bot.edit_message_text(
                        text=text_dash,
                        chat_id=message.chat.id,
                        message_id=panel_msg_id,
                        reply_markup=keyboard,
                    )
            else:
                await cmd_admin_help(message, services)
        else:
            await navigate(text_input, message, state, services)
        return

    # Extract items from either document or text
    extracted_text = ""
    if message.document:
        doc = message.document
        fname = (doc.file_name or "").lower()
        if not (fname.endswith((".txt", ".csv", ".log", ".text")) or (doc.mime_type or "").startswith("text/")):
            await message.answer("Please upload a <code>.txt</code> or text file, or paste items directly.")
            return
        try:
            file_io = io.BytesIO()
            await message.bot.download(doc, destination=file_io)
            raw_bytes = file_io.getvalue()
            try:
                extracted_text = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                extracted_text = raw_bytes.decode("latin-1", errors="ignore")
        except Exception as exc:
            logger.exception("Failed to download or decode stock document: %s", exc)
            await message.answer(f"Failed to read uploaded file: {html.escape(str(exc))}")
            return
    else:
        extracted_text = text_input

    lines = [line.strip() for line in extracted_text.splitlines() if line.strip()]
    if not lines:
        await message.answer(
            "No valid stock lines found. Send the items, one per line, upload a .txt file, or tap Cancel below.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger")
            ]])
        )
        return

    # Parse optional "uses:N" directive from the first line.
    # Handles edge cases like "uses:2user@email.com:pass" (no newline after N).
    max_uses = 1
    m = re.match(r"^uses\s*:\s*(\d+)(.*)", lines[0], re.IGNORECASE)
    if m:
        parsed_uses = int(m.group(1))
        if 1 <= parsed_uses <= 1000:
            max_uses = parsed_uses
        remainder = m.group(2).strip()
        # Anything after the number on the same line becomes the first item
        lines = ([remainder] if remainder else []) + lines[1:]

    items = lines
    if not items:
        await message.answer("No stock items found after the uses directive.")
        return

    await state.clear()
    try:
        result = await services.inventory.add_stock(product_id, items, max_uses=max_uses)
    except Exception as exc:
        await message.answer(f"Could not add stock: {html.escape(str(exc))}")
        return

    product = await services.catalog.product(product_id)
    added = int(result.get("added", 0))
    skipped = int(result.get("skipped", 0))
    if added:
        with suppress(Exception):
            await services.announcements.restock(product_id, added)
    stock_count = (product or {}).get("stock", 0)
    uses_line = f"\n<b>Max Uses:</b> <code>{max_uses}</code> per item" if max_uses > 1 else ""

    stock_conf_text = (
        "<b>Stock added successfully!</b>\n"
        "\n"
        f"<b>Product:</b> {html.escape((product or {}).get('title') or 'Product')}\n"
        f"<b>Items sent:</b> <code>{len(items)}</code>\n"
        f"<b>Added:</b> <code>+{added}</code>\n"
        f"<b>Duplicates skipped:</b> <code>{skipped}</code>"
        f"{uses_line}\n"
        "\n"
        f"<b>Total stock now:</b> <code>{stock_count}</code>"
    )

    stock_conf_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Add More", callback_data=f"adm_stock_{product_id}", style="success"),
            InlineKeyboardButton(text="View Items", callback_data=f"adm_stock_items_{product_id}"),
        ],
        [
            InlineKeyboardButton(text="Back", callback_data="adm_start_stock"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ],
    ])

    if panel_msg_id:
        with suppress(Exception):
            await message.delete()
        try:
            await message.bot.edit_message_text(
                text=stock_conf_text,
                chat_id=message.chat.id,
                message_id=panel_msg_id,
                reply_markup=stock_conf_keyboard,
            )
            return
        except Exception:
            pass

    await message.answer(stock_conf_text, reply_markup=stock_conf_keyboard)


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
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_reply_markup(
                reply_markup=_confirm_keyboard(
                    f"adm_ban_do_{tg_user_id}",
                    "Confirm",
                    danger=banning,
                    back_data=f"adm_ban_cancel_{tg_user_id}",
                )
            )


@router.callback_query(F.data.regexp(r"^adm_ban_cancel_\d+$"))
async def adm_ban_cancel(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    tg_user_id = int(query.data.removeprefix("adm_ban_cancel_"))
    user = await services.users.get(tg_user_id)
    if not user:
        return
    is_banned = bool(user.get("is_banned"))
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Unban Customer" if is_banned else "Ban Customer",
                            callback_data=f"adm_ban_ask_{tg_user_id}",
                            style="success" if is_banned else "danger",
                        )
                    ],
                    [
                        InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
                        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
                    ]
                ])
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
                        )
                    ],
                    [
                        InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
                        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
                    ]
                ])
            )


@router.message(Command("upstream", "sync_reseller"))
async def adm_upstream_status(message: Message, services: Services):
    if await _deny(message, services):
        return
    reseller = services.upstream_reseller
    if reseller:
        await reseller._ensure_config()
    if not reseller or not reseller.is_configured:
        await message.answer("Configure the supplier API in the admin panel.")
        return

    account = await reseller.get_account()
    if not account:
        await message.answer("Failed to connect to upstream reseller API. Check your key and network.")
        return

    account = account.get("user", account)
    name = account.get("name") or "Reseller"
    tg_id = account.get("tg_user_id") or ""
    bal = account.get("balance", 0.0)
    curr = account.get("currency", "BDT")
    sym = account.get("currency_symbol", "৳")

    text = (
        "<b>Upstream Reseller Status</b>\n\n"
        f"<b>Account Name:</b> {html.escape(str(name))}\n"
        f"<b>TG User ID:</b> <code>{tg_id}</code>\n"
        f"<b>Balance:</b> <code>{sym}{bal:.2f} {curr}</code>\n"
        f"<b>API URL:</b> <code>{reseller.base_url}</code>\n\n"
        "<i>Tap below to sync catalog with upstream provider:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Sync Catalog Now", callback_data="adm_do_sync_upstream", style="success"),
        ],
        [
            InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger"),
        ],
    ])
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "adm_do_sync_upstream")
async def adm_do_sync_upstream_cb(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    reseller = services.upstream_reseller
    if reseller:
        await reseller._ensure_config()
    if not reseller or not reseller.is_configured:
        await query.answer("Upstream not configured.", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer("Syncing catalog with upstream provider...")

    from app.services.suppliers import SupplierError
    try:
        cats, prods = await reseller.sync_catalog()
    except SupplierError as exc:
        if query.message:
            await query.message.answer(html.escape(str(exc)))
        return
    services.catalog.invalidate()
    result_text = f"<b>Sync Complete</b>\n\n• Categories created: {cats}\n• Products synced/updated: {prods}"
    if query.message:
        await query.message.answer(result_text)


# ---------------------------------------------------------------------------
# Reseller Applications Management
# ---------------------------------------------------------------------------


def _format_reseller_app_card(app: dict[str, Any], back_cb: str = "adm_queue_reseller") -> tuple[str, InlineKeyboardMarkup]:
    status = (app.get("status") or "pending").lower()
    if status == "approved":
        status_badge = "Approved"
    elif status == "rejected":
        status_badge = "Rejected"
    else:
        status_badge = "Pending Review"

    created = app["created_at"].strftime("%Y-%m-%d %H:%M") if hasattr(app.get("created_at"), "strftime") else str(app.get("created_at", ""))[:16]

    text = (
        f"<b>Reseller Application #{app['id']}</b>\n\n"
        f"<b>Status:</b> <b>{status_badge}</b>\n"
        f"<b>Applicant:</b> <code>{html.escape(app['full_name'])}</code>\n"
        f"<b>Telegram:</b> <code>{html.escape(app['telegram_handle'])}</code> (ID: <code>{app['tg_user_id']}</code>)\n"
        f"<b>Phone/WA:</b> <code>{html.escape(app['phone_number'])}</code>\n"
        f"<b>Channel/Store:</b> {html.escape(app['channel_link'])}\n"
        f"<b>Submitted:</b> <code>{created}</code>\n"
    )
    if app.get("admin_notes"):
        text += f"\n<b>Admin Note:</b> <i>{html.escape(app['admin_notes'])}</i>\n"

    rows: list[list[InlineKeyboardButton]] = []
    if status == "pending":
        rows.append([
            InlineKeyboardButton(text="Approve", callback_data=f"adm_appr_res_{app['id']}", style="success"),
            InlineKeyboardButton(text="Reject", callback_data=f"adm_rej_res_{app['id']}", style="danger"),
        ])
    rows.append([
        InlineKeyboardButton(text="Back", callback_data=back_cb),
        InlineKeyboardButton(text="Admin Panel", callback_data="adm_dashboard"),
    ])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("adm_queue_reseller"))
async def adm_queue_reseller_cb(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    page = 0
    if query.data.startswith("adm_queue_reseller_p_"):
        try:
            page = int(query.data.split("_")[-1])
        except ValueError:
            page = 0

    PAGE_SIZE = 8
    offset = page * PAGE_SIZE
    apps = await services.reseller_applications.list_applications(status=None, limit=PAGE_SIZE, offset=offset)
    total = await services.reseller_applications.count_applications(status=None)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total > 0 else 1
    page = min(page, total_pages - 1)

    rows: list[list[InlineKeyboardButton]] = []
    for a in apps:
        st = a.get("status", "pending")
        btn_text = f"#{a['id']} {a['full_name'][:18]} ({a['telegram_handle'][:15]})"
        btn_style = "danger" if st == "pending" else "primary"
        rows.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"adm_view_res_app_{a['id']}", style=btn_style)
        ])

    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="Prev", callback_data=f"adm_queue_reseller_p_{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="adm_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="Next", callback_data=f"adm_queue_reseller_p_{page + 1}"))
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="Refresh", callback_data=f"adm_queue_reseller_p_{page}"),
        InlineKeyboardButton(text="Back", callback_data="adm_dashboard"),
    ])

    summary = await services.reseller_applications.get_summary()
    text = (
        f"<b>Reseller Applications ({summary['total']})</b>\n\n"
        f"Pending: <b>{summary['pending']}</b> · Approved: <b>{summary['approved']}</b> · Rejected: <b>{summary['rejected']}</b>\n\n"
        "<i>Select an application below to view details and approve/reject:</i>"
    )
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("adm_view_res_app_"))
async def adm_view_reseller_app_cb(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    app_id = int(query.data.split("_")[-1])
    app = await services.reseller_applications.get_application(app_id)
    if not app:
        await query.answer("Application not found.", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await query.answer()
    text, kb = _format_reseller_app_card(app)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm_appr_res_"))
async def adm_approve_reseller_cb(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    app_id = int(query.data.split("_")[-1])
    admin_id = query.from_user.id if query.from_user else 0
    app = await services.reseller_applications.approve_application(app_id, reviewed_by=admin_id)
    if not app:
        await query.answer("Could not approve application (may already be processed).", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer("Application Approved! User promoted to Reseller.", show_alert=True)

    user_notify_text = (
        "<b>Congratulations! Your Reseller Application has been Approved!</b>\n\n"
        "Your account status is now upgraded to <b>Reseller</b>.\n\n"
        "<b>Benefits Activated:</b>\n"
        "• Exclusive wholesale reseller prices on all products.\n"
        "• Direct REST API Key access for bot/store automation.\n"
        "• Priority automated delivery.\n\n"
        "Tap <b>Reseller Panel</b> on the keyboard below to view your stats and generate your API key!"
    )
    await services.notifier.send_message(app["tg_user_id"], user_notify_text)

    updated = await services.reseller_applications.get_application(app_id)
    if updated and query.message:
        text, kb = _format_reseller_app_card(updated)
        with suppress(TelegramBadRequest):
            await query.message.edit_text("<b>Approved by Admin</b>\n\n" + text, reply_markup=kb)


@router.callback_query(F.data.startswith("adm_rej_res_"))
async def adm_reject_reseller_cb(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    app_id = int(query.data.split("_")[-1])
    admin_id = query.from_user.id if query.from_user else 0
    app = await services.reseller_applications.reject_application(app_id, reviewed_by=admin_id, reason="Did not meet eligibility criteria at this time.")
    if not app:
        await query.answer("Could not reject application (may already be processed).", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer("Application Rejected.", show_alert=True)

    user_notify_text = (
        "<b>Reseller Application Update</b>\n\n"
        "Thank you for your interest in our Reseller Program.\n"
        f"Unfortunately, your application (<b>#{app_id}</b>) was not approved at this time.\n\n"
        "If you feel this was in error or your channel has grown, you are welcome to apply again in the future or contact support."
    )
    await services.notifier.send_message(app["tg_user_id"], user_notify_text)

    updated = await services.reseller_applications.get_application(app_id)
    if updated and query.message:
        text, kb = _format_reseller_app_card(updated)
        with suppress(TelegramBadRequest):
            await query.message.edit_text("<b>Rejected by Admin</b>\n\n" + text, reply_markup=kb)


@router.callback_query(F.data.startswith("mute_sup_"))
async def adm_mute_supplier_alert(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    sup_code = query.data.removeprefix("mute_sup_")
    key = "safwan_tiger_low_balance_notify" if sup_code == "safwan_tiger" else "upstream_low_balance_notify"
    sup_name = "Safwan Tiger" if sup_code == "safwan_tiger" else "Digital Mart"

    await services.settings.update({key: "0"})
    with suppress(TelegramBadRequest):
        await query.answer(f"✅ {sup_name} balance alerts turned off.", show_alert=True)

    unmute_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Turn On Alert", callback_data=f"unmute_sup_{sup_code}")]
    ])
    orig_text = query.message.text or query.message.caption or ""
    new_text = f"{orig_text}\n\n<i>🔕 Low balance alert has been turned off by admin.</i>"
    with suppress(TelegramBadRequest):
        await query.message.edit_text(new_text, reply_markup=unmute_kb)


@router.callback_query(F.data.startswith("unmute_sup_"))
async def adm_unmute_supplier_alert(query: CallbackQuery, services: Services):
    if await _deny(query, services):
        return
    sup_code = query.data.removeprefix("unmute_sup_")
    key = "safwan_tiger_low_balance_notify" if sup_code == "safwan_tiger" else "upstream_low_balance_notify"
    sup_name = "Safwan Tiger" if sup_code == "safwan_tiger" else "Digital Mart"

    await services.settings.update({key: "1"})
    with suppress(TelegramBadRequest):
        await query.answer(f"✅ {sup_name} balance alerts enabled.", show_alert=True)

    mute_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔕 Turn Off Alert", callback_data=f"mute_sup_{sup_code}")]
    ])
    orig_text = (query.message.text or query.message.caption or "").split("\n\n<i>🔕")[0]
    with suppress(TelegramBadRequest):
        await query.message.edit_text(orig_text, reply_markup=mute_kb)


@router.message(Command("setbanner", "banner"))
@router.message(F.photo, F.caption.func(lambda c: bool(c and ("/setbanner" in c.lower() or "/banner" in c.lower()))))
async def adm_set_banner(message: Message, services: Services):
    if not message.from_user or not await _is_admin(message.from_user.id, services):
        return

    text = (message.text or message.caption or "").strip()
    parts = text.split()
    arg = parts[1].lower() if len(parts) > 1 else ""

    if arg in {"clear", "off", "remove", "delete"}:
        await services.settings.update({"welcome_banner_file_id": ""})
        await message.reply("✅ Welcome banner removed. Home screen will show clean text.")
        return

    photo = None
    if message.photo:
        photo = message.photo[-1]
    elif message.reply_to_message and message.reply_to_message.photo:
        photo = message.reply_to_message.photo[-1]

    if photo:
        file_id = photo.file_id
        await services.settings.update({"welcome_banner_file_id": file_id})
        await message.reply(
            f"✅ <b>Welcome banner saved!</b>\n\n"
            f"<b>Telegram File ID:</b>\n<code>{file_id}</code>\n\n"
            f"<i>Served directly from Telegram's cloud CDN with zero server bandwidth.</i>"
        )
        return

    curr_banner = await services.settings.get("welcome_banner_file_id")
    status_text = f"<code>{curr_banner[:24]}...</code>" if curr_banner else "<i>None (Clean Text Mode)</i>"
    await message.reply(
        f"🖼️ <b>Home Banner Configuration</b>\n\n"
        f"<b>Current Banner:</b> {status_text}\n\n"
        f"<b>How to set a banner:</b>\n"
        f"1. Send or forward any photo with <code>/setbanner</code> in the caption.\n"
        f"2. Or reply to any photo in this chat with <code>/setbanner</code>.\n\n"
        f"<b>To remove banner:</b>\n"
        f"Send <code>/setbanner clear</code>"
    )
