from __future__ import annotations

import asyncio
import inspect
import logging
import math
import re
import time
from contextlib import suppress
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.customer_copy import payment_summary
from app.bot.deposit_input import parse_deposit_amount, payment_instruction_note
from app.bot.formatting import (
    format_dual_price,
    resolve_user_currency,
    callback_int,
    get_last_menu_message,
    price,
    remember_menu_message,
    resolve_support_url,
    respond,
)
from app.core.identifiers import format_deposit_id
from app.bot.handlers.navigation import is_navigation, navigate
from app.bot.icons import (
    ICON_CROSS,
    ICON_LIGHTNING,
    ICON_NEXT,
    ICON_WARNING,
)
from app.bot.keyboards import (
    get_cancel_keyboard,
    get_deposit_confirm_keyboard,
    get_deposit_input_inline_keyboard,
    get_deposit_methods_keyboard,
    get_deposit_quick_amount_keyboard,
    get_deposit_status_keyboard,
    get_deposit_trxid_prompt_keyboard,
    get_deposit_txid_keyboard,
    get_manual_deposit_invoice_keyboard,
)
from app.core.i18n import t
from app.services import Services
from app.services.deposits import DuplicateTransactionError, PendingDepositError
from app.services.errors import InvalidInputError

logger = logging.getLogger("app.bot.deposit")

router = Router(name="deposit_router")

# Validates standard transaction IDs and numeric UIDs (bKash, Nagad, Binance, etc.)
TRANSACTION_ID_REGEX = re.compile(r"^[A-Za-z0-9_\-]{5,80}$")
# Hosted-invoice references this bot issues; see PaymentService.create_invoice.
PAYMENT_REFERENCE = re.compile(r"SM[0-9A-F]{16}")
# Rate limiting and attempt limits for automated TrxID verification
MAX_VERIFY_ATTEMPTS = 3
VERIFY_COOLDOWN_SECONDS = 600  # 10 minutes lockout after 3 failed attempts


async def _delete_user_message(message: Message) -> None:
    """Quietly delete user input message in private chat to maintain a single clean card."""
    chat = getattr(message, "chat", None)
    if chat and getattr(chat, "type", "") == "private":
        with suppress(Exception):
            await message.delete()


async def _send_input_prompt(
    message: Message, state: FSMContext, text: str, *, field: str, placeholder: str,
) -> None:
    """Replace only this step's previous prompt; never delete payment details."""
    data = await state.get_data()
    previous_id = data.get(field)
    sent = await message.answer(
        text, reply_markup=ForceReply(force_reply=True, input_field_placeholder=placeholder),
    )
    sent_id = getattr(sent, "message_id", None)
    if isinstance(sent_id, int):
        await state.update_data({field: sent_id})
    chat_id = getattr(getattr(message, "chat", None), "id", None)
    bot = getattr(message, "bot", None)
    if (
        bot and chat_id and isinstance(sent_id, int) and isinstance(previous_id, int) and previous_id != sent_id
        and previous_id != data.get("card_msg_id")
    ):
        with suppress(Exception):
            await bot.delete_message(chat_id=chat_id, message_id=previous_id)


async def _retry_payment_input(
    status_msg: Message, message: Message, state: FSMContext, text: str, *, amount: bool = False,
) -> None:
    """Keep the valid field and route the next reply to the field that needs correction."""
    data = await state.get_data()
    is_binance = (
        data.get("is_binance") or "binance" in data.get("method_name", "").lower()
        or data.get("auto_verify") in ("binance", "binance_pay")
    )
    if amount:
        await state.update_data(manual_amount=None, pay_amount=None, usd_amount=None, binance_usdt=None)
        await state.set_state(DepositStates.waiting_for_amount)
        field, placeholder = "amount_prompt_id", "Amount in USDT" if is_binance else "Amount in BDT"
    else:
        await state.update_data(manual_txid=None)
        await state.set_state(
            DepositStates.waiting_for_binance_ref if is_binance else DepositStates.waiting_for_txid,
        )
        field, placeholder = "reference_prompt_id", "Order ID" if is_binance else "Transaction ID"
    await _safe_edit_or_answer(
        status_msg, message, "Payment not verified.",
        reply_markup=get_deposit_trxid_prompt_keyboard(),
    )
    await _send_input_prompt(message, state, text, field=field, placeholder=placeholder)


def get_account_type_labels(account_type: str | None) -> tuple[str, str]:
    """Returns (type_display, action_display)"""
    at = (account_type or "personal").lower()
    if at == "agent":
        return ("Agent (Cash Out)", "Cash Out")
    elif at == "merchant":
        return ("Merchant (Payment)", "Payment")
    else:  # personal
        return ("Personal (Send Money)", "Send Money")


async def _payment_summary_for(services: Services, user_id: int, amount: float, pay_amount: float,
                               is_binance: bool, *, paid: bool = False, rate: float | None = None) -> str:
    currency = await resolve_user_currency(services, user_id)
    # Binance's settlement rate is 1; it is never the USD-to-BDT display rate.
    display_rate = await services.settings.number("usd_rate") if rate is None or is_binance else rate
    return payment_summary(amount, pay_amount, is_binance=is_binance, currency=currency,
                           usd_rate=display_rate, paid=paid)


def format_deposit_method_card(
    method_name: str,
    account_info: str,
    account_type: str = "personal",
    min_dep: float = 1.0,
    rate: float = 1.0,
    symbol: str = "৳",
    is_binance: bool = False,
    lang: str = "en",
    error_note: str | None = None,
) -> str:
    is_payment_link = account_info.startswith("https://")
    if is_binance:
        if lang == "bn":
            dest_line = "নিচের লিংকে ক্লিক করুন:\n\n" if is_payment_link else f"Pay ID: <code>{escape(account_info)}</code>\n\n"
            prompt_line = f"⚠️ <b>{escape(error_note)}</b>" if error_note else "অ্যামাউন্ট নির্বাচন করুন বা লিখুন:"
            return (
                f"<b>{escape(method_name or 'Binance')}</b>\n\n"
                f"{dest_line}"
                f"মিনিমাম: <b>{min_dep:.2f} USDT</b>\n\n"
                f"{prompt_line}"
            )
        else:
            dest_line = "Open link below:\n\n" if is_payment_link else f"Pay ID: <code>{escape(account_info)}</code>\n\n"
            prompt_line = f"⚠️ <b>{escape(error_note)}</b>" if error_note else "Select or enter amount:"
            return (
                f"<b>{escape(method_name or 'Binance')}</b>\n\n"
                f"{dest_line}"
                f"Minimum: <b>{min_dep:.2f} USDT</b>\n\n"
                f"{prompt_line}"
            )
    else:
        type_display, _ = get_account_type_labels(account_type)
        if lang == "bn":
            at_lower = (account_type or "personal").lower()
            if at_lower == "agent":
                type_display = "এজেন্ট (Cash Out)"
            elif at_lower == "merchant":
                type_display = "মার্চেন্ট (Payment)"
            else:
                type_display = "পার্সোনাল (Send Money)"
            dest_line = "নিচের লিংকে ক্লিক করুন:\n\n" if is_payment_link else f"নম্বর: <code>{escape(account_info)}</code>\n\n"
            prompt_line = f"⚠️ <b>{escape(error_note)}</b>" if error_note else "অ্যামাউন্ট নির্বাচন করুন বা লিখুন:"
            return (
                f"<b>{escape(method_name)} {escape(type_display)}</b>\n\n"
                f"{dest_line}"
                f"মিনিমাম: <b>{min_dep:g} ৳</b>\n"
                f"{prompt_line}"
            )
        else:
            dest_line = "Open link below:\n\n" if is_payment_link else f"Number: <code>{escape(account_info)}</code>\n\n"
            prompt_line = f"⚠️ <b>{escape(error_note)}</b>" if error_note else "Select or enter amount:"
            return (
                f"<b>{escape(method_name)} {escape(type_display)}</b>\n\n"
                f"{dest_line}"
                f"Minimum: <b>{min_dep:g} ৳</b>\n"
                f"{prompt_line}"
            )


def format_deposit_status_card(
    dep_id: int,
    method_name: str,
    amount_str: str,
    txid: str,
    status: str,
    current_balance: str | None = None,
    lang: str = "en",
    error_note: str | None = None,
) -> str:
    st = (status or "").lower()
    dep_prefix = format_deposit_id(dep_id) if dep_id else "---"
    if lang == "bn":
        st_display = "⏳ <code>পেন্ডিং</code>"
        if st in ("approved", "completed"):
            st_display = "✅ <code>অনুমোদিত</code>"
        elif st in ("rejected", "failed", "cancelled"):
            st_display = "❌ <code>বাতিল</code>"

        card = (
            f"<b>ডিপোজিট {dep_prefix}</b>\n"
            f"মেথড: <b>{escape(method_name)}</b> (<code>{amount_str}</code>)\n"
            f"TrxID: <code>{escape(txid)}</code>\n"
            f"স্ট্যাটাস: {st_display}"
        )
        if current_balance and st in ("approved", "completed"):
            card += f"\nবর্তমান ব্যালেন্স: <code>{current_balance}</code>"
        if error_note and st not in ("approved", "completed"):
            card += f"\n\nℹ️ <i>{escape(error_note)}</i>"
    else:
        st_display = "⏳ <code>Pending</code>"
        if st in ("approved", "completed"):
            st_display = "✅ <code>Approved</code>"
        elif st in ("rejected", "failed", "cancelled"):
            st_display = "❌ <code>Rejected</code>"

        card = (
            f"<b>Top-up {dep_prefix}</b>\n"
            f"Method: <b>{escape(method_name)}</b> (<code>{amount_str}</code>)\n"
            f"TrxID: <code>{escape(txid)}</code>\n"
            f"Status: {st_display}"
        )
        if current_balance and st in ("approved", "completed"):
            card += f"\nCurrent Balance: <code>{current_balance}</code>"
        if error_note and st not in ("approved", "completed"):
            card += f"\n\nℹ️ <i>{escape(error_note)}</i>"
    return card


def format_deposit_success_card(
    provider: str,
    amount_display: str,
    balance_display: str,
    txid: str | None = None,
    credited_display: str | None = None,
    lang: str = "en",
) -> str:
    clean_tx = (txid or "").strip()
    lines = [
        "✅ <b>Deposit Successful!</b>\n",
        f"Method: <b>{escape(provider)}</b> (<code>{amount_display}</code>)",
    ]
    if clean_tx:
        lines.append(f"TrxID: <code>{escape(clean_tx)}</code>")
    if credited_display:
        lines.append(f"Added: <code>{credited_display}</code>")
    lines.append(f"Current Balance: <code>{balance_display}</code>")
    return "\n".join(lines)


class DepositStates(StatesGroup):
    method_selected = State()
    waiting_for_amount = State()
    waiting_for_txid = State()
    waiting_for_confirm = State()
    waiting_for_binance_amount = State()
    waiting_for_binance_ref = State()
    waiting_for_instant_amount = State()


@router.callback_query(F.data == "cancel_deposit")
async def cancel_deposit_flow(query: CallbackQuery, state: FSMContext):
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.delete()


@router.callback_query(F.data == "open_deposit")
@router.callback_query(F.data == "open_wallet")
@router.callback_query(F.data == "dep_methods")
@router.callback_query(F.data == "dep_back")
@router.callback_query(F.data.startswith("open_deposit_prod_"))
async def show_deposit_methods(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Show the current balance and payment options in an inline keyboard."""
    prior_data: dict[str, Any] = {}
    if hasattr(state, "get_data"):
        maybe_data = state.get_data()
        if inspect.isawaitable(maybe_data):
            res = await maybe_data
            if isinstance(res, dict):
                prior_data = res
    await state.clear()
    user = event.from_user
    if not user:
        return

    bot_obj = getattr(event, "bot", None) or (getattr(getattr(event, "message", None), "bot", None))
    ev_chat = getattr(event, "chat", None) or getattr(getattr(event, "message", None), "chat", None)
    ev_chat_id = getattr(ev_chat, "id", None) or prior_data.get("card_chat_id")
    if bot_obj and ev_chat_id and isinstance(prior_data, dict):
        for prompt_key in ("reference_prompt_id", "amount_prompt_id"):
            pid = prior_data.get(prompt_key)
            if isinstance(pid, int) and pid != prior_data.get("card_msg_id"):
                with suppress(Exception):
                    await bot_obj.delete_message(chat_id=ev_chat_id, message_id=pid)

    back_target: str | None = "back_to_main"
    target_prod_id: int | None = None
    if isinstance(event, CallbackQuery) and event.data and event.data.startswith("open_deposit_prod_"):
        prod_id = event.data.removeprefix("open_deposit_prod_")
        back_target = f"prod_{prod_id}"
        if prod_id.isdigit():
            target_prod_id = int(prod_id)
    elif isinstance(event, CallbackQuery) and event.data in ("dep_methods", "dep_back") and isinstance(prior_data, dict):
        saved_prod_id = prior_data.get("target_prod_id")
        if saved_prod_id is not None:
            target_prod_id = int(saved_prod_id)
            back_target = f"prod_{target_prod_id}"

    if target_prod_id is not None and hasattr(state, "update_data"):
        maybe_upd = state.update_data(target_prod_id=target_prod_id)
        if inspect.isawaitable(maybe_upd):
            await maybe_upd

    paused_msg = await services.settings.paused_message()
    if paused_msg:
        await respond(event, f"<b>Top-ups paused</b>\n\n{escape(paused_msg)}", None)
        return

    instant = await services.payments.instant_options()
    # Independent reads, so they share one database round trip instead of queueing.
    all_methods, pending, user_data = await asyncio.gather(
        services.deposits.methods(active_only=True),
        services.deposits.pending_for(user.id),
        services.users.get(user.id),
    )
    displayed_methods = list(all_methods)

    curr = await resolve_user_currency(services, user.id)
    lang = await services.users.get_language(user.id)
    usd_rate = await services.settings.number("usd_rate")
    user_balance = float(user_data.get("balance", 0.0)) if user_data else 0.0
    balance_display = format_dual_price(user_balance, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)

    if pending:
        if lang == "bn":
            text = (
                f"💰 <b>ব্যালেন্স:</b> <code>{balance_display}</code>\n\n"
                f"⏳ ডিপোজিট {format_deposit_id(pending['id'])} যাচাই হচ্ছে। যাচাই শেষ হলে ব্যালেন্স যোগ হবে।"
            )
        else:
            text = (
                f"💰 <b>Balance:</b> <code>{balance_display}</code>\n\n"
                f"Top-up {format_deposit_id(pending['id'])} is being verified. Do not pay again."
            )
        keyboard = get_deposit_methods_keyboard([], instant_label=None, show_history=True, lang=lang, back_target=back_target)
    else:
        if lang == "bn":
            prompt = (
                "পেমেন্ট মেথড নির্বাচন করুন:"
                if displayed_methods or instant
                else "এই মুহূর্তে কোনো পেমেন্ট মেথড চালু নেই।"
            )
            text = f"💰 <b>ব্যালেন্স:</b> <code>{balance_display}</code>\n\n{prompt}"
        else:
            prompt = (
                "Choose a payment method:"
                if displayed_methods or instant
                else "No payment methods are available right now."
            )
            text = f"💰 <b>Balance:</b> <code>{balance_display}</code>\n\n{prompt}"
        keyboard = get_deposit_methods_keyboard(
            displayed_methods,
            instant_label=instant["label"] if instant else None,
            show_history=True,
            lang=lang,
            back_target=back_target,
        )

    await respond(event, text, keyboard)


class InstantPaymentTextFilter(BaseFilter):
    """Matches the configured hosted-checkout button on the reply keyboard, with or without emojis."""

    async def __call__(self, message: Message, services: Services) -> bool | dict[str, Any]:
        text = (message.text or "").strip()
        if not text:
            return False
        instant = await services.payments.instant_options()
        if not instant or not instant.get("label"):
            return False

        label_raw = str(instant["label"]).strip().casefold()
        label_clean = re.sub(r"^[^\w\s]+\s*", "", label_raw).strip()

        text_raw = text.casefold()
        text_clean = re.sub(r"^[^\w\s]+\s*", "", text_raw).strip()

        # 1. Exact raw or clean match
        if (
            text_raw == label_raw
            or text_clean == label_clean
            or text_raw == label_clean
            or text_clean == label_raw
        ):
            return {"instant": instant}

        # 2. Check brand name "zinipay" containment
        if "zinipay" in text_clean and "zinipay" in label_clean:
            return {"instant": instant}

        # 3. Flexible prefix / containment
        if label_clean and (label_clean in text_clean or text_clean in label_clean):
            return {"instant": instant}

        return False


@router.message(StateFilter(None), InstantPaymentTextFilter())
async def ask_instant_amount_from_text(
    message: Message,
    state: FSMContext,
    services: Services,
    instant: dict[str, Any],
):
    min_dep = float(instant.get("min_amount") or 1.0)
    lang = await services.users.get_language(message.from_user.id) if message.from_user else "en"
    await state.set_state(DepositStates.waiting_for_instant_amount)
    if lang == "bn":
        text = (
            f"{ICON_LIGHTNING} <b>{escape(instant['label'])}</b>\n\n"
            f"মিনিমাম: <b>{min_dep:g} ৳</b>\n\n"
            f"ডিপোজিট অ্যামাউন্ট লিখুন (টাকায়):\n\n"
            f"💡 <i>(যেমন: ৫০ বা ১০০)</i>"
        )
    else:
        text = (
            f"{ICON_LIGHTNING} <b>{escape(instant['label'])}</b>\n\n"
            f"Minimum: <b>{min_dep:g} ৳</b>\n\n"
            f"Enter deposit amount (in BDT):\n\n"
            f"💡 <i>(e.g. 50 or 100)</i>"
        )
    await message.answer(text, reply_markup=get_cancel_keyboard(lang=lang))


class MethodTextFilter(BaseFilter):
    """Matches deposit payment method names from reply keyboard, with or without emojis."""
    async def __call__(self, message: Message, services: Services) -> bool | dict[str, Any]:
        text = (message.text or "").strip()
        if not text or len(text) < 2:
            return False
        clean = text.casefold()
        regex_clean = re.sub(r'^[^\w\s]+\s*', '', clean).strip()

        ignored = {
            "search", "products", "wallet", "orders", "refer", "help", "account", "profile", "support", "admin panel",
            "all catalog", "all products", "back to main", "main menu", "back to catalog",
            "back to products", "back to wallet", "back", "cancel", "refresh", "balance history",
            "deposit history", "price list", "refer & earn", "language", "reseller panel", "become reseller",
            "সার্চ", "ওয়ালেট", "অর্ডার", "একাউন্ট", "প্রোফাইল", "সাপোর্ট", "অ্যাডমিন প্যানেল",
            "সকল প্রোডাক্ট", "মেইন মেনু", "ব্যাক", "বাতিল", "রিফ্রেশ", "ব্যালেন্স হিস্ট্রি", "ডিপোজিট হিস্ট্রি",
        }
        if clean in ignored or regex_clean in ignored:
            return False

        all_methods = await services.deposits.methods(active_only=True)
        for m in all_methods:
            m_raw = m["name"].strip().casefold()
            m_clean = re.sub(r'^[^\w\s]+\s*', '', m_raw).strip()

            # 1. Exact raw or clean match
            if clean == m_raw or clean == m_clean or regex_clean == m_raw or regex_clean == m_clean:
                return {"method": m}

            # 2. Key brand matching (e.g. "bkash", "nagad", "rocket", "binance", "upay")
            for brand in ("bkash", "nagad", "rocket", "binance", "upay", "cellfin"):
                if brand in m_clean and (brand in regex_clean or brand in clean):
                    return {"method": m}

            # 3. Flexible containment for custom method names
            if m_clean and len(m_clean) >= 3:
                if m_clean in regex_clean or regex_clean in m_clean:
                    return {"method": m}

        return False


async def render_method_details(
    event: Message | CallbackQuery,
    state: FSMContext,
    services: Services,
    method: dict[str, Any],
):
    user = event.from_user
    if not user:
        return

    if await services.deposits.pending_for(user.id):
        user_lang = await services.users.get_language(user.id)
        pending_msg = "⚠️ আপনার একটি ডিপোজিট রিকোয়েস্ট পেন্ডিং আছে।" if user_lang == "bn" else "⚠️ You already have a pending deposit request."
        if isinstance(event, CallbackQuery):
            with suppress(TelegramBadRequest):
                await event.answer(pending_msg, show_alert=True)
        else:
            await event.answer(pending_msg)
        return

    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()

    prior_data: dict[str, Any] = {}
    if hasattr(state, "get_data"):
        maybe_data = state.get_data()
        if inspect.isawaitable(maybe_data):
            res = await maybe_data
            if isinstance(res, dict):
                prior_data = res
    target_prod_id = prior_data.get("target_prod_id") if isinstance(prior_data, dict) else None

    await state.clear()
    await state.set_state(DepositStates.method_selected)

    symbol = "৳"

    usd_rate = 125.0
    if hasattr(services, "settings") and hasattr(services.settings, "number"):
        try:
            val = services.settings.number("usd_rate")
            if asyncio.iscoroutine(val) or hasattr(val, "__await__"):
                res = await val
                usd_rate = float(res or 125.0)
            elif isinstance(val, (int, float)):
                usd_rate = float(val)
        except Exception:
            usd_rate = 125.0

    min_dep = float(method.get("min_deposit") or 1.0)
    account_info = str(method.get("account_info") or "").strip()
    method_name = str(method.get("name") or "Payment").strip()
    rate = float(method.get("rate_to_currency") or 0.0)
    account_type = method.get("account_type") or "personal"
    auto_verify = method.get("auto_verify") or "none"
    custom_inst = payment_instruction_note(str(method.get("instructions") or "").strip())

    is_binance = "binance" in method_name.lower() or account_type == "crypto" or auto_verify in ("binance", "binance_pay")
    is_mfs = not is_binance and (account_type in ("personal", "agent", "merchant") or any(w in method_name.lower() for w in ("bkash", "nagad", "rocket", "upay")))
    try:
        if is_mfs and auto_verify == "none" and await services.zinipay.is_enabled():
            auto_verify = "zinipay"
    except Exception:
        pass
    # Binance/USDT and USD are 1:1; local methods display their BDT minimum.
    is_payment_link = account_info.startswith("https://")

    # USD wallet credit converts at one global rate; Binance USDT is 1:1.
    rate = 1.0 if is_binance else float(usd_rate or 125.0)

    state_payload: dict[str, Any] = {
        "method_id": method["id"],
        "method_name": method_name,
        "account_info": account_info,
        "account_type": account_type,
        "min_deposit": min_dep,
        "rate": rate,
        "auto_verify": auto_verify,
        "is_binance": is_binance,
    }
    if target_prod_id is not None:
        state_payload["target_prod_id"] = int(target_prod_id)
    await state.set_data(state_payload)

    user_id = event.from_user.id if event.from_user else 0
    lang = await services.users.get_language(user_id) if user_id else "en"

    shortfall_usd = 0.0
    get_prod_fn = getattr(getattr(services, "catalog", None), "product", None) or getattr(getattr(services, "catalog", None), "get_product", None)
    if target_prod_id is not None and user_id and get_prod_fn:
        try:
            prod_coro = get_prod_fn(int(target_prod_id))
            user_coro = services.users.get(user_id) if hasattr(services.users, "get") else None
            prod_row = await prod_coro if asyncio.iscoroutine(prod_coro) or hasattr(prod_coro, "__await__") else prod_coro
            user_row = (await user_coro if asyncio.iscoroutine(user_coro) or hasattr(user_coro, "__await__") else user_coro) if user_coro is not None else None
            if isinstance(prod_row, dict) and prod_row.get("price") is not None:
                bal = float(user_row.get("balance", 0.0)) if isinstance(user_row, dict) else 0.0
                shortfall_usd = round(max(0.0, float(prod_row["price"]) - bal), 2)
        except Exception:
            shortfall_usd = 0.0

    _, action = get_account_type_labels(account_type)
    heading = method_name if is_binance else f"{method_name} ({action})"
    custom_eid = str(method.get("custom_emoji_id") or "").strip()
    heading_prefix = f'<tg-emoji emoji-id="{custom_eid}">💳</tg-emoji> ' if custom_eid.isdigit() else ""
    destination_label = "Pay ID" if is_binance else "Number"
    destination = "Open the payment page below." if is_payment_link else f"{destination_label}: <code>{escape(account_info)}</code>"
    minimum = f"{min_dep:g} USDT" if is_binance else f"{min_dep:g} ৳"

    card_lines = [
        f"⚠️ Minimum: <b>{minimum}</b>",
    ]
    if shortfall_usd > 0:
        if is_binance:
            card_lines.append(f"Amount needed: <b>{shortfall_usd:.2f} USDT</b>")
        else:
            shortfall_bdt = math.ceil(shortfall_usd * rate)
            card_lines.append(f"Amount needed: <b>{shortfall_bdt:g} ৳</b> (${shortfall_usd:.2f})")

    lines = [
        f"{heading_prefix}<b>{escape(heading)}</b>",
        "",
        "<blockquote>" + "\n".join(card_lines) + "</blockquote>",
        "",
        destination,
        "",
    ]
    if custom_inst:
        lines.append(escape(custom_inst))
    else:
        target_name = "number" if not is_binance else "Pay ID"
        target_phrase = f"Pay to the {target_name} above" if not is_binance else f"Send USDT to the {target_name} above"
        lines.append(f"{target_phrase}, then tap <b>✅ Payment Done</b> to submit your TrxID.")

    inst = "\n".join(lines)
    keyboard = get_manual_deposit_invoice_keyboard(
        account_info, lang=lang, method_id=method["id"], is_binance=is_binance,
    )
    card_msg_id = None
    card_chat_id = None
    if isinstance(event, CallbackQuery):
        q_msg = getattr(event, "message", None)
        if q_msg:
            card_msg_id = getattr(q_msg, "message_id", None)
            q_chat = getattr(q_msg, "chat", None)
            card_chat_id = getattr(q_chat, "id", None)
        await respond(event, inst, keyboard)
    else:
        sent = await event.answer(inst, reply_markup=keyboard)
        if sent:
            card_msg_id = getattr(sent, "message_id", None)
            card_chat = getattr(sent, "chat", None)
            card_chat_id = getattr(card_chat, "id", None) if card_chat else (getattr(event.chat, "id", None) if getattr(event, "chat", None) else None)

    if card_msg_id and card_chat_id:
        remember_menu_message(card_chat_id, card_msg_id)
        await state.update_data(card_msg_id=card_msg_id, card_chat_id=card_chat_id)


@router.message(StateFilter(None), MethodTextFilter())
async def handle_deposit_method_by_text(message: Message, state: FSMContext, services: Services, method: dict[str, Any]):
    """Dynamic handler when customer taps a payment method button from the reply keyboard."""
    await render_method_details(message, state, services, method)


# --- Instant payment via Payment Gateway ---
@router.callback_query(F.data == "dep_instant")
async def ask_instant_amount(query: CallbackQuery, state: FSMContext, services: Services):
    instant = await services.payments.instant_options()
    if not instant:
        with suppress(TelegramBadRequest):
            await query.answer("Instant payment gateway is not active.", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await query.answer()
    min_dep = float(instant.get("min_amount") or 1.0)
    lang = await services.users.get_language(query.from_user.id) if query.from_user else "en"
    await state.set_state(DepositStates.waiting_for_instant_amount)
    if query.message:
        if lang == "bn":
            text = (
                f"{ICON_LIGHTNING} <b>{escape(instant['label'])}</b>\n\n"
                f"মিনিমাম: <b>{min_dep:g} ৳</b>\n\n"
                f"ডিপোজিট অ্যামাউন্ট লিখুন (টাকায়):\n\n"
                f"💡 <i>(যেমন: ৫০ বা ১০০)</i>"
            )
        else:
            text = (
                f"{ICON_LIGHTNING} <b>{escape(instant['label'])}</b>\n\n"
                f"Minimum: <b>{min_dep:g} ৳</b>\n\n"
                f"Enter deposit amount (in BDT):\n\n"
                f"💡 <i>(e.g. 50 or 100)</i>"
            )
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                text,
                reply_markup=get_cancel_keyboard(lang=lang),
            )


def _instant_keyboard(invoice: dict) -> InlineKeyboardMarkup:
    rows = []
    if invoice.get("payment_url"):
        rows.append(
            [InlineKeyboardButton(text=f"Pay ৳{invoice['pay_amount']:.2f}", url=invoice["payment_url"])]
        )
    rows.append(
        [InlineKeyboardButton(text="Payment Done", callback_data=f"inst_chk_{invoice['reference']}")]
    )
    rows.append(
        [InlineKeyboardButton(text="Cancel Payment", callback_data=f"inst_can_{invoice['reference']}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_instant_invoice(invoice: dict, services: Services, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    credit = float(invoice.get("credit_amount") or 0.0)
    pay_amount = float(invoice.get("pay_amount") or 0.0)
    ref = escape(str(invoice.get("reference") or invoice.get("id") or ""))
    ref_suffix = f" #{ref}" if ref else ""
    summary = await _payment_summary_for(services, user_id, credit, pay_amount, False)
    text = (
        f"<b>Top-up{ref_suffix}</b>\n"
        f"{summary}\n"
        "Status: Awaiting payment\n\n"
        "Tap Pay to open checkout. Balance is added after verification."
    )
    return text, _instant_keyboard(invoice)

@router.message(DepositStates.waiting_for_instant_amount)
async def create_instant_payment(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return
    try:
        bdt_amount = float(parse_deposit_amount(raw_text))
        usd_rate = float(await services.settings.number("usd_rate") or 125)
        clean_amount = str(round(bdt_amount / max(usd_rate, 0.0001), 4))
        invoice = await services.payments.create_invoice(message.from_user.id, clean_amount)
    except ValueError as exc:
        await message.answer(f"{ICON_WARNING} {escape(str(exc))}", reply_markup=get_cancel_keyboard())
        return
    text, keyboard = await _render_instant_invoice(invoice, services, message.from_user.id)
    await state.clear()
    sent = await message.answer(text, reply_markup=keyboard)
    if sent and invoice.get("reference"):
        await services.payments.bind_telegram_message(invoice["reference"], sent.chat.id, sent.message_id)


@router.callback_query(F.data.startswith("inst_chk_"))
async def check_instant_payment(query: CallbackQuery, state: FSMContext, services: Services):
    reference = (query.data or "")[len("inst_chk_") :]
    if not PAYMENT_REFERENCE.fullmatch(reference):
        with suppress(TelegramBadRequest):
            await query.answer("Payment reference not found.", show_alert=True)
        return
    invoice = await services.payments.refresh(reference, tg_user_id=query.from_user.id)
    if not invoice:
        with suppress(TelegramBadRequest):
            await query.answer("Invoice not found.", show_alert=True)
        return

    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    if invoice["status"] == "completed":
        ref = escape(str(invoice.get("reference") or invoice.get("id") or ""))
        ref_suffix = f" #{ref}" if ref else ""
        pay_amt = float(invoice.get("pay_amount") or 0.0)
        credit = float(invoice.get("credit_amount") or 0.0)
        summary = await _payment_summary_for(services, query.from_user.id, credit, pay_amt, False, paid=True)
        text = (
            f"<b>Payment verified{ref_suffix}</b>\n"
            f"{summary}\n"
            "Your balance has been updated."
        )
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="Balance", callback_data="open_deposit")]]
                    ),
                )
        with suppress(TelegramBadRequest):
            await query.answer("Payment verified!")
    elif invoice["status"] in ("expired", "failed"):
        text = (
            f"{ICON_CROSS} <b>Payment Invoice #{escape(reference)} is no longer active.</b>\n\n"
            f"Status: <code>{invoice['status'].title()}</code>\n"
            "If you have already paid, contact Support before paying again."
        )
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="Balance", callback_data="open_deposit")]]
                    ),
                )
        with suppress(TelegramBadRequest):
            await query.answer("Invoice is no longer active.", show_alert=True)
    else:
        with suppress(TelegramBadRequest):
            await query.answer("Payment is not verified yet. If you have paid, wait and check again. Do not pay twice.", show_alert=True)


@router.callback_query(F.data.startswith("inst_can_"))
async def ask_cancel_instant_payment(query: CallbackQuery, state: FSMContext, services: Services):
    reference = (query.data or "")[len("inst_can_") :]
    if not PAYMENT_REFERENCE.fullmatch(reference):
        with suppress(TelegramBadRequest):
            await query.answer("Payment reference not found.", show_alert=True)
        return
    invoice = await services.payments.get(reference, tg_user_id=query.from_user.id)
    if not invoice or invoice.get("status") != "pending":
        with suppress(TelegramBadRequest):
            await query.answer("Invoice is no longer active.", show_alert=True)
        return

    text = (
        f"<b>Cancel payment #{escape(reference)}?</b>\n\n"
        "Already paid? Keep this payment and tap Payment Done."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Cancel Payment", callback_data=f"inst_cancfm_{reference}", style="danger"),
                InlineKeyboardButton(text="Keep Payment", callback_data=f"inst_view_{reference}"),
            ]
        ]
    )
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)
    with suppress(TelegramBadRequest):
        await query.answer()


@router.callback_query(F.data.startswith("inst_view_"))
async def view_instant_invoice(query: CallbackQuery, state: FSMContext, services: Services):
    reference = (query.data or "")[len("inst_view_") :]
    invoice = await services.payments.get(reference, tg_user_id=query.from_user.id)
    if not invoice or invoice.get("status") != "pending":
        with suppress(TelegramBadRequest):
            await query.answer("Invoice is no longer active.", show_alert=True)
        return
    text, keyboard = await _render_instant_invoice(invoice, services, query.from_user.id)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)
        if invoice.get("reference"):
            await services.payments.bind_telegram_message(invoice["reference"], query.message.chat.id, query.message.message_id)
    with suppress(TelegramBadRequest):
        await query.answer()


@router.callback_query(F.data.startswith("inst_cancfm_"))
async def confirm_cancel_instant_payment(query: CallbackQuery, state: FSMContext, services: Services):
    reference = (query.data or "")[len("inst_cancfm_") :]
    if not PAYMENT_REFERENCE.fullmatch(reference):
        with suppress(TelegramBadRequest):
            await query.answer("Payment reference not found.", show_alert=True)
        return

    invoice = await services.payments.cancel_invoice(reference, tg_user_id=query.from_user.id)
    if not invoice:
        with suppress(TelegramBadRequest):
            await query.answer("Invoice not found.", show_alert=True)
        return

    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")

    if invoice["status"] == "completed":
        user = await services.users.get(query.from_user.id)
        curr = await resolve_user_currency(services, query.from_user.id)
        text = (
            "<b>Payment already verified</b>\n"
            f"Added: <code>{format_dual_price(invoice['credit_amount'], usd_rate=usd_rate, currency=curr)}</code>\n"
            f"Balance: <code>{format_dual_price(user['balance'] if user else 0.0, usd_rate=usd_rate, currency=curr)}</code>"
        )
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Balance", callback_data="open_deposit")]]
        )
    else:
        text = (
            f"<b>Payment cancelled · {escape(reference)}</b>\n\n"
            "This invoice is closed. If you already paid, contact Support before paying again."
        )
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Balance", callback_data="open_deposit")]]
        )

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=reply_markup)
    with suppress(TelegramBadRequest):
        await query.answer("Payment already verified." if invoice["status"] == "completed" else "Invoice cancelled.")


# --- Manual deposit (bKash, Nagad, Binance) ---
@router.callback_query(F.data.startswith("dep_method_"))
async def handle_deposit_method_select(query: CallbackQuery, state: FSMContext, services: Services):
    method_id = callback_int(query.data, "dep_method_")
    all_methods = await services.deposits.methods(active_only=True)
    method = next((m for m in all_methods if m["id"] == method_id), None)
    if not method:
        with suppress(TelegramBadRequest):
            await query.answer("Payment method not found.", show_alert=True)
        return
    await render_method_details(query, state, services, method)


@router.callback_query(F.data == "dep_invoice")
async def handle_deposit_invoice_back(query: CallbackQuery, state: FSMContext, services: Services):
    data = await state.get_data()
    method_id = data.get("method_id")
    if method_id:
        method = await services.deposits.get_method(method_id)
    else:
        all_methods = await services.deposits.methods(active_only=True)
        method = all_methods[0] if all_methods else None

    if not method or not method.get("is_active", True):
        with suppress(TelegramBadRequest):
            await query.answer("Payment method no longer available.", show_alert=True)
        return
    await render_method_details(query, state, services, method)


@router.callback_query(F.data == "binance_help_order_id")
async def binance_help_order_id_handler(query: CallbackQuery, state: FSMContext, services: Services):
    with suppress(TelegramBadRequest):
        await query.answer()
    data = await state.get_data()
    method_id = data.get("method_id")
    lang = await services.users.get_language(query.from_user.id)

    if lang == "bn":
        text = (
            f"❓ <b>Order ID কোথায় পাবেন?</b>\n\n"
            f"1. Binance App ওপেন করুন\n"
            f"2. <b>Wallets</b> -> <b>History</b> (ঘড়ির আইকন) এ যান\n"
            f"3. আপনার পেমেন্ট ট্রানজেকশনে ট্যাপ করুন\n"
            f"4. <b>Order ID</b> কপি করে এখানে পেস্ট করুন"
        )
    else:
        text = (
            f"❓ <b>Where to find Order ID?</b>\n\n"
            f"1. Open Binance App\n"
            f"2. Go to <b>Wallets</b> -> <b>History</b> (clock icon)\n"
            f"3. Tap on the transfer you sent\n"
            f"4. Copy the <b>Order ID</b> and paste it here"
        )
    back_target = f"dep_method_{method_id}" if method_id else "open_deposit"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔙 Payment details",
                    callback_data=back_target,
                )
            ]
        ]
    )
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("dep_amt_"))
async def handle_deposit_quick_amount(query: CallbackQuery, state: FSMContext, services: Services):
    with suppress(TelegramBadRequest):
        await query.answer()

    data = await state.get_data()
    method_id = data.get("method_id", 0)
    method_name = data.get("method_name", "Payment")
    account_info = data.get("account_info", "")
    account_type = data.get("account_type", "personal")
    min_dep = float(data.get("min_deposit") or 1.0)
    is_binance = data.get("is_binance", False) or "binance" in method_name.lower() or data.get("auto_verify") == "binance_pay"
    curr_label = "USDT" if is_binance else "৳"
    lang = await services.users.get_language(query.from_user.id) if query.from_user else "en"

    raw_val = query.data.removeprefix("dep_amt_")
    try:
        amount_num = float(raw_val)
        if amount_num <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        with suppress(TelegramBadRequest):
            await query.answer("Invalid amount.", show_alert=True)
        return

    rate = float(data.get("rate") or 1.0)
    if amount_num < min_dep:
        err_msg = (
            f"মিনিমাম ডিপোজিট {min_dep:.2f} USDT:"
            if is_binance
            else f"মিনিমাম ডিপোজিট {min_dep:.0f} ৳:"
        ) if lang == "bn" else (
            f"Minimum deposit is {min_dep:.2f} USDT:"
            if is_binance
            else f"Minimum deposit is {min_dep:.0f} ৳:"
        )
        with suppress(TelegramBadRequest):
            await query.answer(err_msg, show_alert=True)
        return

    max_dep = await services.settings.number("max_deposit_limit")
    usd_amount = amount_num if is_binance else round(amount_num / rate, 4)
    if max_dep and usd_amount > max_dep:
        limit = max_dep if is_binance else max_dep * rate
        unit = "USDT" if is_binance else "৳"
        err_msg = f"Maximum payment is {limit:g} {unit}."
        with suppress(TelegramBadRequest):
            await query.answer(err_msg, show_alert=True)
        return

    rate = float(data.get("rate") or 1.0)
    if is_binance:
        pay_amount = amount_num
    else:
        pay_amount = amount_num

    q_msg = getattr(query, "message", None)
    card_msg_id = getattr(q_msg, "message_id", None) if q_msg else None
    q_chat = getattr(q_msg, "chat", None) if q_msg else None
    card_chat_id = getattr(q_chat, "id", None) if q_chat else None
    if card_msg_id and card_chat_id:
        remember_menu_message(card_chat_id, card_msg_id)

    amount_summary = await _payment_summary_for(services, query.from_user.id, usd_amount, pay_amount, is_binance, rate=rate)

    await state.update_data(
        manual_amount=usd_amount,
        pay_amount=pay_amount,
        usd_amount=usd_amount,
        binance_usdt=usd_amount,
        rate=rate,
        card_msg_id=card_msg_id,
        card_chat_id=card_chat_id,
    )
    await state.set_state(DepositStates.waiting_for_txid)

    if is_binance:
        if lang == "bn":
            tx_prompt = (
                f"<b>{escape(method_name)}</b>\n"
                f"Pay ID: <code>{escape(account_info)}</code>\n"
                f"{amount_summary}\n\n"
                "পেমেন্টের Order ID নিচে লিখুন:"
            )
        else:
            tx_prompt = (
                f"<b>{escape(method_name)}</b>\n"
                f"Pay ID: <code>{escape(account_info)}</code>\n"
                f"{amount_summary}\n\n"
                "Enter Order ID below:"
            )
    else:
        type_display, _ = get_account_type_labels(account_type)
        if lang == "bn":
            at_lower = (account_type or "personal").lower()
            if at_lower == "agent":
                type_display = "এজেন্ট (Cash Out)"
            elif at_lower == "merchant":
                type_display = "মার্চেন্ট (Payment)"
            else:
                type_display = "পার্সোনাল (Send Money)"
            tx_prompt = (
                f"<b>{escape(method_name)} {type_display}</b>\n"
                f"নম্বর: <code>{escape(account_info)}</code>\n"
                f"{amount_summary}\n\n"
                "পেমেন্টের TrxID নিচে লিখুন:"
            )
        else:
            tx_prompt = (
                f"<b>{escape(method_name)} {type_display}</b>\n"
                f"Number: <code>{escape(account_info)}</code>\n"
                f"{amount_summary}\n\n"
                "Enter TrxID below:"
            )

    keyboard = get_deposit_trxid_prompt_keyboard(lang=lang)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(tx_prompt, reply_markup=keyboard)


@router.callback_query(F.data == "dep_change_amt")
async def handle_deposit_change_amount(query: CallbackQuery, state: FSMContext, services: Services):
    data = await state.get_data()
    method_id = data.get("method_id")
    method = None
    if method_id:
        method = await services.deposits.get_method(method_id)
    if not method:
        all_methods = await services.deposits.methods(active_only=True)
        method = all_methods[0] if all_methods else None
    if not method:
        await show_deposit_methods(query, state, services)
        return
    await render_method_details(query, state, services, method)


@router.callback_query(F.data.startswith("dep_paid_"))
async def begin_payment_reference(query: CallbackQuery, state: FSMContext, services: Services):
    """Open Telegram's reply input, without replacing the payment instructions."""
    data = await state.get_data()
    selected_id = data.get("method_id")
    requested_id = (query.data or "").removeprefix("dep_paid_")
    if (
        not requested_id.isdecimal()
        or str(selected_id) != requested_id
        or await state.get_state() != DepositStates.method_selected.state
    ):
        await query.answer("This payment screen is no longer active. Open Balance.", show_alert=True)
        return
    method = await services.deposits.get_method(selected_id)
    if not method or not method.get("is_active", True):
        await query.answer("This payment method is unavailable. Open Balance.", show_alert=True)
        return
    if await services.deposits.pending_for(query.from_user.id):
        await query.answer("Your previous payment is still being checked.", show_alert=True)
        return
    if not query.message:
        return
    is_binance = bool(data.get("is_binance"))
    reference_label = "Order ID" if is_binance else "Transaction ID"
    prompt = f"Enter your {escape(str(data.get('method_name') or 'payment'))} {reference_label}."
    sent = await query.message.answer(
        prompt,
        reply_markup=ForceReply(force_reply=True, input_field_placeholder=reference_label),
    )
    await state.update_data(
        reference_first=True, manual_amount=None, manual_txid=None, pay_amount=None,
        binance_usdt=None, reference_prompt_id=getattr(sent, "message_id", None),
    )
    await state.set_state(DepositStates.waiting_for_txid)
    with suppress(TelegramBadRequest):
        await query.answer()


@router.callback_query(F.data.in_({"dep_change_amount", "dep_confirm_paid", "dep_paid"}))
async def ask_deposit_input(query: CallbackQuery, state: FSMContext, services: Services):
    data = await state.get_data()
    method_id = data.get("method_id")
    if not method_id:
        with suppress(TelegramBadRequest):
            await query.answer("Please select a payment method again.", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer()

    await state.set_state(DepositStates.waiting_for_amount)
    await state.update_data(manual_amount=None, manual_txid=None, binance_usdt=None)

    method_name = data.get("method_name", "Payment")
    account_info = data.get("account_info", "")
    min_dep = float(data.get("min_deposit") or 1.0)
    is_binance = data.get("is_binance", False) or "binance" in method_name.lower() or data.get("auto_verify") == "binance_pay"

    if is_binance:
        amount_text = (
            f"Minimum: <b>{min_dep:.2f} USDT</b>\n\n"
            f"Enter amount sent in USDT:"
        )
    else:
        amount_text = (
            f"Minimum: <b>{min_dep:.0f} ৳</b>\n\n"
            f"Enter amount sent in ৳:"
        )

    reply_kb = get_deposit_input_inline_keyboard(
        account_info=account_info,
        method_name=method_name,
        is_binance=is_binance,
        change_amount=False,
    )

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(amount_text, reply_markup=reply_kb)


@router.message(DepositStates.method_selected)
async def handle_method_selected_input(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if raw_text in {"🔙 Back", "🔙 ব্যাক", "Back", "ব্যাক", "Cancel", "বাতিল", "❌ Cancel", "❌ বাতিল", "back", "cancel"}:
        await state.clear()
        await show_deposit_methods(message, state, services)
        return
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return
    await process_deposit_amount(message, state, services)


@router.message(DepositStates.waiting_for_amount)
@router.message(DepositStates.waiting_for_binance_amount)
async def process_deposit_amount(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if raw_text in {"🔙 Back", "🔙 ব্যাক", "Back", "ব্যাক", "Cancel", "বাতিল", "❌ Cancel", "❌ বাতিল", "back", "cancel"}:
        await state.clear()
        await show_deposit_methods(message, state, services)
        return
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    data = await state.get_data()
    method_id = data.get("method_id", 0)
    method_name = data.get("method_name", "Payment")
    account_info = data.get("account_info", "")
    min_dep = float(data.get("min_deposit") or 1.0)
    is_binance = data.get("is_binance", False) or "binance" in method_name.lower() or data.get("auto_verify") == "binance_pay"
    currency_label = "USDT" if is_binance else "৳"
    lang = await services.users.get_language(message.from_user.id) if message.from_user else "en"

    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)

    target_msg_id = data.get("card_msg_id") or (get_last_menu_message(chat_id) if chat_id else None)

    symbol = "৳"

    rate = float(data.get("rate") or 1.0)
    account_type = data.get("account_type", "personal")

    quick_kb = get_deposit_quick_amount_keyboard(
        is_binance=is_binance,
        lang=lang,
        back_target="dep_methods",
    )

    def _build_err_card(err_text: str) -> str:
        if data.get("reference_first"):
            return escape(err_text)
        return format_deposit_method_card(
            method_name=method_name,
            account_info=account_info,
            account_type=account_type,
            min_dep=min_dep,
            rate=rate,
            symbol=symbol,
            is_binance=is_binance,
            lang=lang,
            error_note=err_text,
        )

    async def _send_or_edit_error(err_text: str, kb):
        if data.get("reference_first"):
            await _send_input_prompt(
                message, state, err_text, field="amount_prompt_id",
                placeholder="Amount in USDT" if is_binance else "Amount in BDT",
            )
            return
        if target_msg_id and getattr(message, "bot", None) and chat_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=target_msg_id,
                    text=err_text,
                    reply_markup=kb,
                )
                remember_menu_message(chat_id, target_msg_id)
                return
            except Exception:
                pass
        await message.answer(
            err_text,
            reply_markup=kb,
        )

    try:
        amount_num = float(parse_deposit_amount(raw_text, is_binance=is_binance))
        if not math.isfinite(amount_num) or amount_num <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        if lang == "bn":
            err_msg = f"সঠিক পরিমাণ লিখুন ({currency_label}), যেমন: ৫০।"
        else:
            unit = "USDT" if is_binance else "BDT"
            example = max(min_dep, 1.0 if is_binance else 50.0)
            err_msg = f"Enter valid amount in {unit}, e.g. {example:g}."
        await _send_or_edit_error(_build_err_card(err_msg), quick_kb)
        return

    if amount_num < min_dep:
        if lang == "bn":
            err_msg = (
                f"মিনিমাম ডিপোজিট {min_dep:.2f} USDT:"
                if is_binance
                else f"মিনিমাম ডিপোজিট {min_dep:.0f} ৳:"
            )
        else:
            err_msg = (
                f"Minimum deposit is {min_dep:.2f} USDT:"
                if is_binance
                else f"Minimum deposit is {min_dep:.0f} ৳:"
            )
        await _send_or_edit_error(_build_err_card(err_msg), quick_kb)
        return

    rate = float(data.get("rate") or 1.0)
    max_dep = await services.settings.number("max_deposit_limit")
    usd_amount = amount_num if is_binance else round(amount_num / rate, 4)
    if max_dep and usd_amount > max_dep:
        limit = max_dep if is_binance else max_dep * rate
        unit = "USDT" if is_binance else "৳"
        err_msg = f"Maximum payment is {limit:g} {unit}."
        await _send_or_edit_error(_build_err_card(err_msg), quick_kb)
        return

    if chat_id and getattr(chat, "type", "") == "private":
        asyncio.create_task(_delete_user_message(message))

    if is_binance:
        pay_amount = amount_num
    else:
        pay_amount = amount_num

    amount_summary = await _payment_summary_for(services, message.from_user.id, usd_amount, pay_amount, is_binance, rate=rate)

    await state.update_data(
        manual_amount=usd_amount,
        pay_amount=pay_amount,
        usd_amount=usd_amount,
        binance_usdt=usd_amount,
        rate=rate,
    )
    if data.get("reference_first") and data.get("manual_txid"):
        # Current verification providers require an amount. Ask once, after the
        # reference, and continue without asking for the same reference again.
        await execute_deposit_submission(message, state, services)
        return
    await state.set_state(DepositStates.waiting_for_txid)

    if is_binance:
        if lang == "bn":
            tx_prompt = (
                f"<b>{escape(method_name)}</b>\n"
                f"Pay ID: <code>{escape(account_info)}</code>\n"
                f"{amount_summary}\n\n"
                "পেমেন্টের Order ID নিচে লিখুন:"
            )
        else:
            tx_prompt = (
                f"<b>{escape(method_name)}</b>\n"
                f"Pay ID: <code>{escape(account_info)}</code>\n"
                f"{amount_summary}\n\n"
                "Enter Order ID below:"
            )
    else:
        account_type = data.get("account_type", "personal")
        type_display, _ = get_account_type_labels(account_type)
        if lang == "bn":
            at_lower = (account_type or "personal").lower()
            if at_lower == "agent":
                type_display = "এজেন্ট (Cash Out)"
            elif at_lower == "merchant":
                type_display = "মার্চেন্ট (Payment)"
            else:
                type_display = "পার্সোনাল (Send Money)"
            tx_prompt = (
                f"<b>{escape(method_name)} {type_display}</b>\n"
                f"নম্বর: <code>{escape(account_info)}</code>\n"
                f"{amount_summary}\n\n"
                "পেমেন্টের TrxID নিচে লিখুন:"
            )
        else:
            tx_prompt = (
                f"<b>{escape(method_name)} {type_display}</b>\n"
                f"Number: <code>{escape(account_info)}</code>\n"
                f"{amount_summary}\n\n"
                "Enter TrxID below:"
            )

    keyboard = get_deposit_trxid_prompt_keyboard(lang=lang)

    edited = False
    if target_msg_id and getattr(message, "bot", None) and chat_id:
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=target_msg_id,
                text=tx_prompt,
                reply_markup=keyboard,
            )
            remember_menu_message(chat_id, target_msg_id)
            await state.update_data(card_msg_id=target_msg_id, card_chat_id=chat_id)
            edited = True
        except Exception:
            edited = False

    if not edited:
        sent = await message.answer(
            tx_prompt,
            reply_markup=keyboard,
        )
        if sent and chat_id:
            sent_id = getattr(sent, "message_id", None)
            if sent_id:
                remember_menu_message(chat_id, sent_id)
                await state.update_data(card_msg_id=sent_id, card_chat_id=chat_id)


@router.message(DepositStates.waiting_for_txid)
@router.message(DepositStates.waiting_for_binance_ref)
async def process_deposit_txid(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if raw_text in {"🔙 Back", "🔙 ব্যাক", "Back", "ব্যাক", "Cancel", "বাতিল", "❌ Cancel", "❌ বাতিল", "back", "cancel"}:
        await state.clear()
        await show_deposit_methods(message, state, services)
        return
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    data = await state.get_data()
    method_id = data.get("method_id", 0)
    method_name = data.get("method_name", "Payment")
    account_info = data.get("account_info", "")
    account_type = data.get("account_type", "personal")
    amount_num = float(data.get("manual_amount") or data.get("binance_usdt") or 0.0)
    is_binance = data.get("is_binance", False) or "binance" in method_name.lower() or data.get("auto_verify") == "binance_pay"
    lang = await services.users.get_language(message.from_user.id) if message.from_user else "en"

    clean_tx = re.sub(r"^(uid|order\s*id|order|txid|trxid|trx\s*id|ref)[\s:#=]*", "", raw_text, flags=re.IGNORECASE).strip()
    clean_tx = clean_tx.strip("<>#[](){}\"':; \t\r\n")
    if " " in clean_tx and not is_binance:
        sms_tx_match = re.search(
            r"\b(?:trx\s*id|tx\s*n\s*id|transaction\s*id)[\s:#=]*([A-Za-z0-9]{5,30})\b",
            raw_text,
            re.IGNORECASE,
        )
        if sms_tx_match:
            clean_tx = sms_tx_match.group(1).strip()

    back_kb = get_deposit_trxid_prompt_keyboard(lang=lang)

    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)

    target_msg_id = data.get("card_msg_id") or (get_last_menu_message(chat_id) if chat_id else None)

    pay_amount = float(data.get("pay_amount") or amount_num)
    usd_amount = float(data.get("usd_amount") or amount_num)

    amount_summary = await _payment_summary_for(services, message.from_user.id, usd_amount, pay_amount, is_binance, rate=float(data.get("rate") or 125))

    if not TRANSACTION_ID_REGEX.fullmatch(clean_tx) or len(clean_tx) < 5 or " " in clean_tx:
        if data.get("reference_first"):
            label = "Order ID" if is_binance else "Transaction ID"
            await _send_input_prompt(
                message, state, f"Enter a valid {label} from your receipt.",
                field="reference_prompt_id", placeholder=label,
            )
            return
        err_msg = f"সঠিক {'Order ID' if is_binance else 'TrxID'} দিন:" if lang == "bn" else f"Enter valid {'Order ID' if is_binance else 'TrxID'}:"
        if is_binance:
            if lang == "bn":
                tx_err_card = (
                    f"<b>{escape(method_name)}</b>\n"
                    f"Pay ID: <code>{escape(account_info)}</code>\n"
                    f"{amount_summary}\n\n"
                    f"⚠️ <b>{err_msg}</b>"
                )
            else:
                tx_err_card = (
                    f"<b>{escape(method_name)}</b>\n"
                    f"Pay ID: <code>{escape(account_info)}</code>\n"
                    f"{amount_summary}\n\n"
                    f"⚠️ <b>{err_msg}</b>"
                )
        else:
            type_display, _ = get_account_type_labels(account_type)
            if lang == "bn":
                at_lower = (account_type or "personal").lower()
                if at_lower == "agent":
                    type_display = "এজেন্ট (Cash Out)"
                elif at_lower == "merchant":
                    type_display = "মার্চেন্ট (Payment)"
                else:
                    type_display = "পার্সোনাল (Send Money)"
                tx_err_card = (
                    f"<b>{escape(method_name)} {type_display}</b>\n"
                    f"নম্বর: <code>{escape(account_info)}</code>\n"
                    f"{amount_summary}\n\n"
                    f"⚠️ <b>{err_msg}</b>"
                )
            else:
                tx_err_card = (
                    f"<b>{escape(method_name)} {type_display}</b>\n"
                    f"Number: <code>{escape(account_info)}</code>\n"
                    f"{amount_summary}\n\n"
                    f"⚠️ <b>{err_msg}</b>"
                )

        edited = False
        if target_msg_id and getattr(message, "bot", None) and chat_id:
            try:
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=target_msg_id,
                    text=tx_err_card,
                    reply_markup=back_kb,
                )
                remember_menu_message(chat_id, target_msg_id)
                edited = True
            except Exception:
                edited = False
        if not edited:
            await message.answer(
                tx_err_card,
                reply_markup=back_kb,
            )
        return

    if chat_id and getattr(chat, "type", "") == "private":
        asyncio.create_task(_delete_user_message(message))
    await state.update_data(manual_txid=clean_tx)
    if data.get("reference_first") and not (data.get("pay_amount") or amount_num):
        # 1. Check if an incoming statement was already captured via SMS forwarder or statement webhook
        received_tx = await _get_unused_statement(services, clean_tx)
        if received_tx:
            auto_amt = float(received_tx["amount"])
            await state.update_data(manual_amount=auto_amt, pay_amount=auto_amt)
            await execute_deposit_submission(message, state, services)
            return

        # 2. Try direct ZiniPay auto-verify with only TrxID if enabled
        try:
            if hasattr(services, "zinipay") and callable(getattr(services.zinipay, "is_enabled", None)):
                is_on = services.zinipay.is_enabled()
                if inspect.isawaitable(is_on):
                    is_on = await is_on
                if is_on:
                    probe = await services.zinipay.verify(amount=None, transaction_id=clean_tx)
                    if probe.get("ok"):
                        auto_amt = float(probe.get("amount") or 0.0)
                        if auto_amt > 0:
                            rate = float(data.get("rate") or 125.0)
                            usd_amt = round(auto_amt / rate, 4)
                            await state.update_data(manual_amount=usd_amt, pay_amount=auto_amt, usd_amount=usd_amt)
                            await execute_deposit_submission(message, state, services)
                            return
        except Exception as exc:
            logger.debug("TrxID-only verify probe: %s", exc)

        # 3. Safe fallback: prompt for the amount if statement has not arrived yet and TrxID-only lookup requires amount
        await state.set_state(DepositStates.waiting_for_amount)
        unit = "USDT" if is_binance else "BDT"
        example = max(float(data.get("min_deposit") or 1.0), 1.0 if is_binance else 50.0)
        user_lang = await services.users.get_language(message.from_user.id) if message.from_user else "en"
        if user_lang == "bn":
            amount_prompt = (
                f"💳 <b>পেমেন্ট ভেরিফিকেশন</b>\n\n"
                f"TrxID: <code>{escape(clean_tx)}</code>\n\n"
                f"অটো-ভেরিফাই করার জন্য আপনি <b>কত টাকা পাঠিয়েছেন</b> তা লিখুন (যেমন: {example:g}):"
            )
        else:
            amount_prompt = f"Enter the amount you sent in {unit}, e.g. {example:g}."
        await _send_input_prompt(
            message, state, amount_prompt,
            field="amount_prompt_id", placeholder=f"Amount in {unit}",
        )
        return
    # Plan 1: Direct submission without redundant confirmation step
    await execute_deposit_submission(message, state, services)


@router.message(DepositStates.waiting_for_confirm)
async def process_confirm_text(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip().lower()
    if is_navigation(message.text or ""):
        await navigate(message.text or "", message, state, services)
        return

    lang = await services.users.get_language(message.from_user.id) if message.from_user else "en"
    if raw_text in {"yes", "confirm", "হ্যাঁ", "হাঁ", "ok", "ঠিক আছে", "হ্যা"}:
        await execute_deposit_submission(message, state, services)
    elif raw_text in {"no", "cancel", "বাতিল", "না", "/cancel", "back", "🔙 back", "🔙 ব্যাক"}:
        await state.clear()
        await message.answer("❌ ডিপোজিট বাতিল করা হয়েছে।" if lang == "bn" else "❌ Deposit cancelled.")
        await show_deposit_methods(message, state, services)
    else:
        prompt_txt = "জমা দিতে ✅ কনফার্ম অথবা বাতিল করতে ❌ বাতিল চাপুন।" if lang == "bn" else "Tap ✅ Confirm to submit or ❌ Cancel to abort."
        await message.answer(
            prompt_txt,
            reply_markup=get_deposit_confirm_keyboard(lang=lang),
        )


@router.callback_query(F.data.in_({"dep_conf_yes", "d_conf_yes"}))
async def confirm_deposit_callback(query: CallbackQuery, state: FSMContext, services: Services):
    if await state.get_state() != DepositStates.waiting_for_confirm.state:
        with suppress(TelegramBadRequest):
            await query.answer("This confirmation is no longer active. Open Balance to check your deposit.")
        return
    with suppress(TelegramBadRequest):
        await query.answer()
    await execute_deposit_submission(query, state, services)


@router.callback_query(F.data.in_({"dep_conf_cancel", "d_conf_cancel"}))
async def cancel_deposit_callback(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer("Deposit cancelled.")
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text("❌ Deposit cancelled.")
        await show_deposit_methods(query.message, state, services)
    else:
        await show_deposit_methods(query, state, services)


async def _get_unused_statement(services: Services, clean_tx: str) -> dict[str, Any] | None:
    if not hasattr(services, "deposits") or not hasattr(services.deposits, "get_unused_received_transaction"):
        return None
    fn = getattr(services.deposits, "get_unused_received_transaction")
    if not callable(fn):
        return None
    res = fn(clean_tx)
    if inspect.isawaitable(res):
        res = await res
    return res if isinstance(res, dict) else None


async def _claim_statement(services: Services, clean_tx: str, user_id: int, dep_id: int) -> None:
    if not hasattr(services, "deposits") or not hasattr(services.deposits, "claim_received_transaction"):
        return
    fn = getattr(services.deposits, "claim_received_transaction")
    if not callable(fn):
        return
    res = fn(clean_tx, user_id, dep_id)
    if inspect.isawaitable(res):
        await res


async def _safe_edit_or_answer(status_msg: Message, user_msg: Message, text: str, reply_markup=None):
    try:
        await status_msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return
        await user_msg.answer(text, reply_markup=reply_markup)
    except Exception:
        await user_msg.answer(text, reply_markup=reply_markup)


async def execute_deposit_submission(
    event: Message | CallbackQuery,
    state: FSMContext,
    services: Services,
):
    status_msg = None
    user_id = event.from_user.id
    lang = await services.users.get_language(user_id) if user_id else "en"
    data = await state.get_data()
    method_id = data.get("method_id")
    raw_amount = float(data.get("manual_amount") or data.get("binance_usdt") or 0.0)
    pay_amount = float(data.get("pay_amount") or 0.0)
    clean_tx = (data.get("manual_txid") or "").strip().upper()
    method_name = data.get("method_name", "Payment")
    account_info = data.get("account_info", "")
    account_type = data.get("account_type", "personal")
    rate = float(data.get("rate") or 1.0)
    is_binance = data.get("is_binance", False) or "binance" in method_name.lower() or data.get("auto_verify") == "binance_pay"

    curr = await resolve_user_currency(services, user_id)
    display_rate = await services.settings.number("usd_rate")

    if is_binance:
        credit_amount = raw_amount if raw_amount > 0 else pay_amount
        actual_pay = credit_amount
        amt_display = f"{credit_amount:g} USDT"
    else:
        if pay_amount > 0:
            actual_pay = pay_amount
            credit_amount = round(actual_pay / rate, 4)
        elif raw_amount > 0:
            credit_amount = raw_amount
            actual_pay = round(credit_amount * rate, 2)
        else:
            actual_pay = 0.0
            credit_amount = 0.0
        amt_display = f"{actual_pay:g} ৳"

    user_msg = event.message if isinstance(event, CallbackQuery) else event
    chat = getattr(event, "chat", None) or (getattr(user_msg, "chat", None) if user_msg else None)
    chat_id = getattr(chat, "id", None)
    target_msg_id = data.get("card_msg_id") or (get_last_menu_message(chat_id) if chat_id else None)
    bot_obj = getattr(event, "bot", None) or (getattr(user_msg, "bot", None) if user_msg else None)
    if bot_obj and chat_id:
        for prompt_key in ("reference_prompt_id", "amount_prompt_id"):
            pid = data.get(prompt_key)
            if isinstance(pid, int) and pid != target_msg_id:
                with suppress(Exception):
                    await bot_obj.delete_message(chat_id=chat_id, message_id=pid)

    if not method_id or not clean_tx or (credit_amount <= 0 and actual_pay <= 0):
        await state.clear()
        expired_msg = "⏳ Session expired. Please select a deposit method to try again."
        if isinstance(event, CallbackQuery) and event.message:
            with suppress(TelegramBadRequest):
                await event.message.edit_text(expired_msg)
        else:
            edited = False
            if target_msg_id and getattr(event, "bot", None) and chat_id:
                try:
                    await event.bot.edit_message_text(chat_id=chat_id, message_id=target_msg_id, text=expired_msg)
                    edited = True
                except Exception:
                    edited = False
            if not edited:
                await event.answer(expired_msg)
        return

    # Status message while verifying
    checking_txt = (
        f"⏳ <b>Checking payment...</b>\n\n"
        f"Method: <b>{escape(method_name)}</b>\n"
        f"Amount: <b>{amt_display}</b>\n"
        f"TrxID: <code>{escape(clean_tx)}</code>"
    )

    if isinstance(event, CallbackQuery) and event.message:
        status_msg = event.message
        with suppress(TelegramBadRequest):
            await status_msg.edit_text(checking_txt)
    else:
        if target_msg_id and getattr(event, "bot", None) and chat_id:
            try:
                res = await event.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=target_msg_id,
                    text=checking_txt,
                )
                if hasattr(res, "edit_text"):
                    status_msg = res
            except Exception:
                status_msg = None

        if status_msg is None:
            status_msg = await event.answer(checking_txt)
            if chat_id and status_msg:
                sent_id = getattr(status_msg, "message_id", None)
                if sent_id:
                    remember_menu_message(chat_id, sent_id)
                    await state.update_data(card_msg_id=sent_id, card_chat_id=chat_id)

    # 1. Fast pre-check: active pending deposit
    existing_pending = await services.deposits.pending_for(user_id)
    if existing_pending:
        existing_tx = str(existing_pending.get("transaction_id") or "").strip().upper()
        if existing_tx and clean_tx and existing_tx == clean_tx and hasattr(services, "zinipay") and await services.zinipay.is_enabled():
            try:
                credited = await services.zinipay._finish_awaiting(existing_pending)
                if credited:
                    await services.deposits.clear_verification_failures(user_id)
                    await state.clear()
                    user = await services.users.get(user_id)
                    user_balance = float(user.get("balance", 0.0)) if user else 0.0
                    provider = method_name
                    balance_display = format_dual_price(user_balance, usd_rate=display_rate, lang=lang, currency=curr, show_usd=False)
                    keyboard = get_deposit_status_keyboard(dep_id=existing_pending["id"], status="approved", lang=lang)
                    text = format_deposit_success_card(
                        provider=provider,
                        amount_display=amt_display,
                        balance_display=balance_display,
                        credited_display=(format_dual_price(float(existing_pending["amount"]), currency=curr, usd_rate=display_rate)
                                          if curr == "USD" else None),
                        txid=clean_tx,
                        lang=lang,
                    )
                    await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)
                    return
            except Exception as exc:
                logger.warning("Retry finish awaiting error: %s", exc)

        await state.clear()
        kb = [
            [InlineKeyboardButton(text="🔄 Check Again", callback_data=f"dep_refresh_{existing_pending['id']}")],
            [InlineKeyboardButton(text="✏️ Fix TrxID", callback_data=f"dep_fix_trx_{existing_pending['id']}")],
            [InlineKeyboardButton(text="📊 Balance History", callback_data="open_deposits")],
        ]
        text = (
            f"⏳ <b>আপনার পূর্বের একটি ডিপোজিট (TrxID: <code>{escape(existing_tx or clean_tx)}</code>) এখনও যাচাই হচ্ছে।</b>\n\nঅনুগ্রহ করে অপেক্ষা করুন অথবা রিফ্রেশ চাপুন।"
            if lang == "bn"
            else "⏳ A deposit of yours is still being checked. Please wait for it to finish."
        )
        await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 2. Rate limiting / attempts check
    now = time.time()
    fails = await services.deposits.verification_failures(user_id)
    if len(fails) >= MAX_VERIFY_ATTEMPTS:
        remaining_sec = int(VERIFY_COOLDOWN_SECONDS - (now - fails[0]))
        rem_min = max(1, (remaining_sec + 59) // 60)
        await state.clear()
        support_user = await services.settings.get("support_username")
        kb = []
        sup_url = resolve_support_url(support_user)
        if sup_url:
            kb.append([InlineKeyboardButton(text="💬 Contact Support", url=sup_url)])
        text = (
            f"❌ পরপর ভুল TrxID দেওয়ার কারণে সাময়িকভাবে ব্লক করা হয়েছে। {rem_min} মিনিট পর চেষ্টা করুন।"
            if lang == "bn"
            else f"❌ Too many wrong TrxIDs entered. Try again in {rem_min} minute(s)."
        )
        await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    # 3. Binance Flow
    if is_binance:
        await claim_binance_payment(user_msg, state, services, method_id, clean_tx, expected_usdt=credit_amount, status_msg=status_msg, user_id=user_id)
        return

    # 3.5 Statement / SMS Sync Instant Approval Flow
    received_tx = await _get_unused_statement(services, clean_tx)
    if received_tx:
        auto_amt = float(received_tx["amount"])
        rate = float(data.get("rate") or 125.0)
        credit_amount = round(auto_amt / rate, 4)
        actual_pay = auto_amt
        amt_display = f"{actual_pay:g} ৳"

        try:
            dep_id = await services.deposits.create_request(
                tg_user_id=user_id,
                method_id=method_id,
                amount=credit_amount,
                transaction_id=clean_tx,
                pay_amount=actual_pay,
                quoted_rate=rate,
                admin_note="Auto-verified via Instant Statement Sync",
                notify_admin=True,
            )
            ok, err, details = await services.deposits.approve(
                dep_id,
                admin_note="Auto-verified via Instant Statement Sync",
                notify_customer=False,
            )
            if ok:
                await _claim_statement(services, clean_tx, user_id, dep_id)
                await services.deposits.clear_verification_failures(user_id)
                await state.clear()
                user = await services.users.get(user_id)
                user_balance = float(user.get("balance", 0.0)) if user else 0.0
                balance_display = format_dual_price(user_balance, usd_rate=display_rate, lang=lang, currency=curr, show_usd=False)
                keyboard = get_deposit_status_keyboard(dep_id=dep_id, status="approved", lang=lang)
                success_txt = format_deposit_success_card(
                    provider=method_name,
                    amount_display=amt_display,
                    balance_display=balance_display,
                    credited_display=format_dual_price(credit_amount, currency=curr, usd_rate=display_rate) if curr == "USD" else None,
                    txid=clean_tx,
                    lang=lang,
                )
                await _safe_edit_or_answer(status_msg, user_msg, success_txt, reply_markup=keyboard)
                return
        except DuplicateTransactionError:
            lang = await services.users.get_language(user_id)
            text = "❌ এই TrxID আগেই ব্যবহার করা হয়েছে।" if lang == "bn" else "❌ This TrxID has already been used. Send a new one."
            await _retry_payment_input(status_msg, user_msg, state, text)
            return
        except Exception as exc:
            logger.warning("Statement sync claim error: %s", exc)

    # 4. ZiniPay Flow
    method_data = await services.deposits.get_method(method_id) if method_id else None
    auto_verify_mode = method_data.get("auto_verify") if method_data else data.get("auto_verify", "none")
    zinipay_on = await services.zinipay.is_enabled()
    is_mfs = not is_binance and (account_type in ("personal", "agent", "merchant") or any(w in method_name.lower() for w in ("bkash", "nagad", "rocket", "upay")))
    is_zinipay_auto = zinipay_on and (auto_verify_mode == "zinipay" or is_mfs)

    async def on_sync_wait(waited: float, total: float) -> None:
        await _safe_edit_or_answer(
            status_msg,
            user_msg,
            f"⏳ <b>Checking payment... ({int(waited)}/{int(total)}s)</b>\n\n"
            f"Method: <b>{escape(method_name)}</b>\n"
            f"Amount: <b>{amt_display}</b>\n"
            f"TrxID: <code>{escape(clean_tx)}</code>",
        )

    if is_zinipay_auto:
        try:
            res = await services.zinipay.claim(
                user_id,
                method_id,
                credit_amount,
                clean_tx,
                pay_amount=actual_pay,
                quoted_rate=rate,
                on_sync_wait=on_sync_wait,
            )
        except DuplicateTransactionError:
            lang = await services.users.get_language(user_id)
            text = "❌ এই TrxID আগেই ব্যবহার করা হয়েছে।" if lang == "bn" else "❌ This TrxID has already been used. Send a new one."
            await _retry_payment_input(status_msg, user_msg, state, text)
            return
        except PendingDepositError:
            await state.clear()
            kb = [
                [InlineKeyboardButton(text="📊 Balance History", callback_data="open_deposits")],
            ]
            text = "⏳ A deposit of yours is still being checked. Please wait for it to finish."
            await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
            return
        except (InvalidInputError, ValueError) as exc:
            await state.clear()
            await _safe_edit_or_answer(status_msg, user_msg, f"❌ {escape(str(exc))}")
            return
        except Exception as exc:
            logger.warning("ZiniPay claim interrupted (%s); preserving the payment for review.", type(exc).__name__)
            try:
                # The gateway call may have succeeded after a local reservation.
                # Never file a second request or lose the saved payment on this path.
                existing = await services.deposits.find_by_transaction(clean_tx)
                if existing and existing.get("tg_user_id") == user_id:
                    await state.clear()
                    await _safe_edit_or_answer(
                        status_msg, user_msg,
                        "Your payment is already recorded. Open History to check its status. Do not pay again.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="History", callback_data="open_deposits"),
                        ]]),
                    )
                    return
                dep_id = await services.deposits.create_request(
                    tg_user_id=user_id,
                    method_id=method_id,
                    amount=credit_amount,
                    transaction_id=clean_tx,
                    pay_amount=actual_pay,
                    quoted_rate=rate,
                    admin_note="ZiniPay verification interrupted. Review the merchant statement before approval.",
                )
                await state.clear()
                lang = await services.users.get_language(user_id)
                keyboard = get_deposit_status_keyboard(dep_id=dep_id, status="pending", can_fix_trx=False, lang=lang)
                text = format_deposit_status_card(
                    dep_id=dep_id,
                    method_name=method_name,
                    amount_str=amt_display,
                    txid=clean_tx,
                    status="pending",
                    lang=lang,
                )
                await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)
                return
            except Exception:
                await state.clear()
                await _safe_edit_or_answer(
                    status_msg, user_msg,
                    "Verification is unavailable. Check History or contact Help before retrying. Do not pay again.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="History", callback_data="open_deposits")],
                        [InlineKeyboardButton(text="Help", callback_data="open_support")],
                    ]),
                )
                return

        if res.get("auto_verified") and res.get("credited"):
            await services.deposits.clear_verification_failures(user_id)
            await state.clear()
            user = await services.users.get(user_id)
            user_balance = float(user.get("balance", 0.0)) if user else 0.0
            provider = res.get("provider") or method_name
            lang = await services.users.get_language(user_id)
            balance_display = format_dual_price(user_balance, usd_rate=display_rate, lang=lang, currency=curr, show_usd=False)
            keyboard = get_deposit_status_keyboard(dep_id=0, status="approved", lang=lang)
            text = format_deposit_success_card(
                provider=provider,
                amount_display=amt_display,
                balance_display=balance_display,
                credited_display=format_dual_price(credit_amount, currency=curr, usd_rate=display_rate) if curr == "USD" else None,
                txid=clean_tx,
                lang=lang,
            )
            await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)
            return

        if res.get("pending_sync"):
            await state.set_state(None)
            dep_id = res.get("deposit_id") or 0
            lang = await services.users.get_language(user_id)
            keyboard = get_deposit_status_keyboard(dep_id=dep_id, status="pending", can_fix_trx=True, lang=lang)
            text = format_deposit_status_card(
                dep_id=dep_id,
                method_name=method_name,
                amount_str=amt_display,
                txid=clean_tx,
                status="pending",
                lang=lang,
            )
            await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)
            return

        if res.get("fallback_manual"):
            await state.clear()
            dep_id = res.get("deposit_id") or 0
            lang = await services.users.get_language(user_id)
            keyboard = get_deposit_status_keyboard(dep_id=dep_id, status="pending", can_fix_trx=True, lang=lang)
            detail = res.get("detail") or res.get("error_msg")
            text = format_deposit_status_card(
                dep_id=dep_id,
                method_name=method_name,
                amount_str=amt_display,
                txid=clean_tx,
                status="pending",
                error_note=detail,
                lang=lang,
            )
            await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)
            return

        if res.get("error"):
            now = time.time()
            fails = await services.deposits.verification_failures(user_id, record_failure=True)
            remaining_attempts = MAX_VERIFY_ATTEMPTS - len(fails)

            if remaining_attempts <= 0:
                await services.deposits.clear_verification_failures(user_id)
                await state.clear()
                admin_note = f"ZiniPay auto-verify failed 3x ({res.get('error')}). Review the receipt and amount before approval."
                try:
                    dep_id = await services.deposits.create_request(
                        tg_user_id=user_id,
                        method_id=method_id,
                        amount=credit_amount,
                        transaction_id=clean_tx,
                        pay_amount=actual_pay,
                        quoted_rate=rate,
                        admin_note=admin_note,
                    )
                    lang = await services.users.get_language(user_id)
                    keyboard = get_deposit_status_keyboard(dep_id=dep_id, status="pending", can_fix_trx=False, lang=lang)
                    text = format_deposit_status_card(
                        dep_id=dep_id,
                        method_name=method_name,
                        amount_str=amt_display,
                        txid=clean_tx,
                        status="pending",
                        lang=lang,
                    )
                    await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)
                    return
                except Exception:
                    await _safe_edit_or_answer(
                        status_msg, user_msg,
                        "Unable to save this payment. Check History or contact Help before retrying. Do not pay again.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="History", callback_data="open_deposits")],
                            [InlineKeyboardButton(text="Help", callback_data="open_support")],
                        ]),
                    )
                    return

            if res["error"] == "amount_mismatch":
                await _retry_payment_input(
                    status_msg, user_msg, state,
                    "Amount does not match the receipt. Enter the amount you sent in BDT.",
                    amount=True,
                )
            else:
                error_msg = (
                    "This TrxID has already been used. Enter a new Transaction ID."
                    if res["error"] == "already_used" else
                    f"Invalid TrxID for {escape(method_name)}. Enter the Transaction ID from your receipt."
                )
                await _retry_payment_input(status_msg, user_msg, state, error_msg)
            return

    # 5. Standard Manual Deposit
    try:
        dep_id = await services.deposits.create_request(
            user_id,
            method_id,
            amount=credit_amount,
            transaction_id=clean_tx,
            pay_amount=actual_pay,
            quoted_rate=rate,
        )
    except DuplicateTransactionError:
        lang = await services.users.get_language(user_id)
        text = "❌ এই TrxID আগেই ব্যবহার করা হয়েছে।" if lang == "bn" else "❌ This TrxID has already been used."
        await _retry_payment_input(status_msg, user_msg, state, text)
        return
    except PendingDepositError:
        await state.clear()
        kb = [
            [InlineKeyboardButton(text="📊 Balance History", callback_data="open_deposits")],
        ]
        await _safe_edit_or_answer(
            status_msg,
            user_msg,
            "⏳ A previous deposit of yours is still being checked. Please wait for it to finish.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        )
        return
    except (InvalidInputError, ValueError) as exc:
        await state.clear()
        await _safe_edit_or_answer(status_msg, user_msg, f"❌ {escape(str(exc))}")
        return
    except Exception as exc:
        logger.exception("execute_deposit_submission error: %s", exc)
        await state.clear()
        lang = await services.users.get_language(user_id)
        err_msg = (
            "❌ <b>পেমেন্ট প্রসেস করার সময় একটি ত্রুটি হয়েছে।</b>\nঅনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন বা সাপোর্টে জানান।"
            if lang == "bn"
            else "❌ <b>An error occurred while processing your payment.</b>\nPlease try again shortly or contact support."
        )
        await _safe_edit_or_answer(status_msg, user_msg, err_msg)
        return

    await state.clear()
    lang = await services.users.get_language(user_id)
    support_user = await services.settings.get("support_username")
    keyboard = get_deposit_status_keyboard(
        dep_id=dep_id,
        status="pending",
        can_fix_trx=False,
        support_username=support_user,
        lang=lang,
    )
    text = format_deposit_status_card(
        dep_id=dep_id,
        method_name=method_name,
        amount_str=amt_display,
        txid=clean_tx,
        status="pending",
        lang=lang,
    )
    await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)


async def claim_binance_payment(
    user_msg: Message,
    state: FSMContext,
    services: Services,
    method_id: int,
    ref: str,
    expected_usdt: float | None = None,
    status_msg: Message | None = None,
    *,
    user_id: int,
):
    lang = await services.users.get_language(user_id)
    if status_msg is None:
        status_msg = await user_msg.answer(
            f"⏳ <b>Checking payment...</b>\n\n"
            f"Method: <b>Binance</b>\n"
            f"Amount: <b>{expected_usdt or 0:.2f} USDT</b>\n"
            f"Order ID: <code>{escape(ref)}</code>"
        )

    try:
        result = await services.binance.claim(user_id, method_id, ref, expected_usdt=expected_usdt)
    except DuplicateTransactionError:
        await _retry_payment_input(
            status_msg, user_msg, state,
            "This Order ID has already been used. Enter a new Order ID from Binance.",
        )
        return
    except PendingDepositError:
        await state.clear()
        kb = [
            [InlineKeyboardButton(text="📊 Balance History" if lang != "bn" else "📊 ডিপোজিট হিস্ট্রি", callback_data="open_deposits")],
        ]
        await _safe_edit_or_answer(
            status_msg,
            user_msg,
            "⏳ A previous deposit of yours is still being checked. Please wait for it to finish.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        )
        return
    except (InvalidInputError, ValueError) as exc:
        await state.clear()
        await _safe_edit_or_answer(status_msg, user_msg, f"❌ {escape(str(exc))}")
        return
    except Exception as exc:
        logger.exception("execute_deposit_submission error: %s", exc)
        await state.clear()
        lang = await services.users.get_language(user_id)
        err_msg = (
            "❌ <b>পেমেন্ট প্রসেস করার সময় একটি ত্রুটি হয়েছে।</b>\nঅনুগ্রহ করে কিছুক্ষণ পর আবার চেষ্টা করুন বা সাপোর্টে জানান।"
            if lang == "bn"
            else "❌ <b>An error occurred while processing your payment.</b>\nPlease try again shortly or contact support."
        )
        await _safe_edit_or_answer(status_msg, user_msg, err_msg)
        return

    if result.get("error") in ("not_found", "already_used"):
        if result["error"] == "already_used":
            err_text = "❌ এই Order ID আগেই ব্যবহার করা হয়েছে।" if lang == "bn" else "❌ This Order ID has already been used."
        else:
            err_text = "❌ Order ID পাওয়া যায়নি। Binance থেকে চেক করে আবার দিন।" if lang == "bn" else "❌ Order ID not found. Check it in Binance and send it again."
        await _retry_payment_input(status_msg, user_msg, state, err_text)
        return

    await state.clear()
    symbol = await services.settings.get("currency_symbol") or "৳"

    if result.get("credited"):
        user = await services.users.get(user_id)
        user_balance = float(user.get("balance", 0.0)) if user else 0.0
        received_coin = result.get("received_coin") or expected_usdt or 0.0
        coin = result.get("coin", "USDT")
        credited_amount = result.get("amount", 0.0)
        usd_rate = await services.settings.number("usd_rate")
        curr = await resolve_user_currency(services, user_id)
        balance_display = format_dual_price(user_balance, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)
        credited_display = format_dual_price(credited_amount, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)

        keyboard = get_deposit_status_keyboard(dep_id=0, status="approved", lang=lang)
        text = format_deposit_success_card(
            provider="Binance",
            amount_display=f"{received_coin:g} {escape(coin)}",
            balance_display=balance_display,
            txid=ref,
            credited_display=credited_display,
            lang=lang,
        )
        await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)
    else:
        dep_id = result.get("deposit_id") or 0
        support_user = await services.settings.get("support_username")
        keyboard = get_deposit_status_keyboard(dep_id=dep_id, status="pending", support_username=support_user, lang=lang)
        text = format_deposit_status_card(
            dep_id=dep_id,
            method_name="Binance",
            amount_str=f"{expected_usdt or 0:g} USDT",
            txid=ref,
            status="pending",
            lang=lang,
        )
        await _safe_edit_or_answer(status_msg, user_msg, text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("dep_refresh_"))
async def refresh_deposit_status(query: CallbackQuery, services: Services):
    user = query.from_user
    if not user:
        return
    raw_id = query.data.removeprefix("dep_refresh_")
    if not raw_id.isdigit():
        with suppress(TelegramBadRequest):
            await query.answer("Invalid request.")
        return
    dep_id = int(raw_id)

    dep = await services.deposits.get_for_customer(user.id, dep_id)
    if not dep:
        with suppress(TelegramBadRequest):
            await query.answer("Deposit not found.", show_alert=True)
        return

    lang = await services.users.get_language(user.id)
    support_username = await services.settings.get("support_username")
    status = (dep.get("status") or "pending").lower()

    if status == "pending" and hasattr(services, "zinipay") and await services.zinipay.is_enabled():
        try:
            if await services.zinipay._finish_awaiting(dep):
                dep = await services.deposits.get_for_customer(user.id, dep_id) or dep
                status = (dep.get("status") or "approved").lower()
        except Exception:
            pass

    if status in ("approved", "completed"):
        toast = "✅ ডিপোজিট অনুমোদিত হয়েছে!" if lang == "bn" else "✅ Deposit Approved!"
    elif status in ("rejected", "failed", "cancelled"):
        toast = "❌ ডিপোজিট বাতিল করা হয়েছে" if lang == "bn" else "❌ Deposit Rejected"
    else:
        toast = "⏳ এখনও পর্যালোচনায় আছে" if lang == "bn" else "⏳ Still in review"

    with suppress(TelegramBadRequest):
        await query.answer(toast)

    is_bin = "binance" in (dep.get("method_name") or "").lower()
    amt = float(dep.get("amount") or 0.0)
    pay_amt = float(dep.get("pay_amount") or 0.0)
    usd_rate = await services.settings.number("usd_rate")
    curr = await resolve_user_currency(services, user.id)
    amt_str = format_dual_price(amt, usd_rate=usd_rate, currency=curr)

    user_balance_str = None
    if status in ("approved", "completed"):
        user_data = await services.users.get(user.id)
        user_bal = float(user_data.get("balance", 0.0)) if user_data else 0.0
        user_balance_str = format_dual_price(user_bal, usd_rate=usd_rate, currency=curr)

    card_text = format_deposit_status_card(
        dep_id=dep_id,
        method_name=dep.get("method_name") or "Payment",
        amount_str=amt_str,
        txid=dep.get("transaction_id") or "",
        status=status,
        current_balance=user_balance_str,
        lang=lang,
    )

    kb = get_deposit_status_keyboard(
        dep_id=dep_id,
        status=status,
        support_username=support_username,
        lang=lang,
    )

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(card_text, reply_markup=kb)


@router.callback_query(F.data.startswith("dep_fix_trx_"))
async def fix_awaiting_transaction_id(query: CallbackQuery, state: FSMContext, services: Services):
    """"I typed the TrxID wrong" — stop waiting for a receipt that will never arrive.

    Without this the customer is held by the one-pending-deposit rule until the worker
    gives up, which is a long time to sit with a typo they have already spotted."""
    deposit_id = int(query.data.removeprefix("dep_fix_trx_") or 0)
    cancelled = await services.deposits.cancel_awaiting_sms(deposit_id, query.from_user.id)
    lang = await services.users.get_language(query.from_user.id)
    if not cancelled:
        with suppress(TelegramBadRequest):
            cannot_cancel = "এই রিকোয়েস্ট আর বাতিল করা সম্ভব নয়।" if lang == "bn" else "This request cannot be cancelled anymore."
            await query.answer(cannot_cancel, show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await query.answer()
    await state.set_state(DepositStates.waiting_for_txid)
    if query.message:
        prompt_txt = (
            f"{ICON_NEXT} সঠিক TrxID লিখুন:\n💡 <i>যেমন: <code>BLA7X8Y9Z0</code></i>"
            if lang == "bn" else
            f"{ICON_NEXT} Please enter the correct TrxID:\n💡 <i>e.g. <code>BLA7X8Y9Z0</code></i>"
        )
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                prompt_txt,
                reply_markup=get_deposit_txid_keyboard(lang=lang),
            )
@router.callback_query(F.data.startswith("back_to_dep_req_"))
async def back_to_deposit_request(query: CallbackQuery, services: Services):
    raw_id = query.data.removeprefix("back_to_dep_req_")
    if not raw_id.isdigit():
        return
    dep_id = int(raw_id)
    user = query.from_user
    if not user:
        return
    dep = await services.deposits.get_for_customer(user.id, dep_id)
    if not dep:
        with suppress(TelegramBadRequest):
            await query.answer("Deposit request not found.", show_alert=True)
        return

    lang = await services.users.get_language(user.id)
    support_username = await services.settings.get("support_username")
    status = (dep.get("status") or "pending").lower()

    is_bin = "binance" in (dep.get("method_name") or "").lower()
    amt = float(dep.get("amount") or 0.0)
    pay_amt = float(dep.get("pay_amount") or 0.0)
    usd_rate = await services.settings.number("usd_rate")
    curr = await resolve_user_currency(services, user.id)
    amt_str = format_dual_price(amt, usd_rate=usd_rate, currency=curr)

    user_balance_str = None
    if status in ("approved", "completed"):
        user_data = await services.users.get(user.id)
        user_bal = float(user_data.get("balance", 0.0)) if user_data else 0.0
        user_balance_str = format_dual_price(user_bal, usd_rate=usd_rate, currency=curr)

    text = format_deposit_status_card(
        dep_id=dep_id,
        method_name=dep.get("method_name") or "Payment",
        amount_str=amt_str,
        txid=dep.get("transaction_id") or "",
        status=status,
        current_balance=user_balance_str,
        lang=lang,
    )
    keyboard = get_deposit_status_keyboard(
        dep_id=dep_id,
        status=status,
        support_username=support_username,
        lang=lang,
    )
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)
