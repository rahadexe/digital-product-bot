from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.formatting import callback_int, price, respond
from app.bot.handlers.navigation import is_navigation, navigate
from app.bot.icons import (
    ICON_BALANCE,
    ICON_BINANCE,
    ICON_CHECK,
    ICON_COIN,
    ICON_CROSS,
    ICON_DEPOSIT,
    ICON_ID,
    ICON_KEY,
    ICON_LIGHTNING,
    ICON_MONEY,
    ICON_NEXT,
    ICON_NOTE,
    ICON_QUESTION,
    ICON_SPARKLES,
    ICON_TIMER,
    ICON_USER,
    ICON_WARNING,
    Icons,
    get_method_icon,
)
from app.bot.keyboards import (
    get_cancel_keyboard,
    get_deposit_amount_keyboard,
    get_deposit_methods_keyboard,
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


def get_account_type_labels(account_type: str | None) -> tuple[str, str]:
    """Returns (type_display, action_display)"""
    at = (account_type or "personal").lower()
    if at == "agent":
        return ("Agent", "Cash Out")
    elif at == "merchant":
        return ("Merchant", "Payment")
    else:  # personal
        return ("Personal", "Send Money")


class DepositStates(StatesGroup):
    method_selected = State()
    waiting_for_amount = State()
    waiting_for_txid = State()
    waiting_for_binance_amount = State()
    waiting_for_binance_ref = State()
    waiting_for_instant_amount = State()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"{ICON_CROSS} Current operation cancelled.")


@router.callback_query(F.data == "cancel_deposit")
async def cancel_deposit_flow(query: CallbackQuery, state: FSMContext):
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.delete()


@router.message(Command("deposit"))
@router.message(F.text.in_({
    "Add Balance", "add balance", "💰 Add Balance", "💳 Add Balance", "Deposit", "deposit", "💳 Deposit",
    "💳 অ্যাড ব্যালেন্স", "অ্যাড ব্যালেন্স",
    "💳 बैलेंस जोड़ें", "बैलेंस जोड़ें",
    "💳 بیلنس شامل کریں", "بیلنس شامل کریں",
}))
@router.callback_query(F.data == "open_deposit")
@router.callback_query(F.data == "open_deposit_from_history")
@router.callback_query(F.data == "open_deposit_from_account")
async def show_deposit_methods(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Render deposit methods matching Screenshot 4."""
    await state.clear()
    user = event.from_user
    if not user:
        return

    back_target: str | None = "back_to_main"
    if isinstance(event, CallbackQuery):
        if event.data == "open_deposit_from_history":
            back_target = "open_deposits"
        elif event.data == "open_deposit_from_account":
            back_target = "open_account"
        else:
            back_target = "back_to_main"

    paused_msg = await services.settings.paused_message()
    if paused_msg:
        await respond(event, f"{ICON_WARNING} <b>Deposits Temporarily Paused</b>\n\n{escape(paused_msg)}", None)
        return

    instant = await services.payments.instant_options()
    setting_values = await services.settings.values()
    binance_enabled = setting_values.get("binance_enabled") == "1"

    # Independent reads, so they share one database round trip instead of queueing.
    all_methods, pending, user_data = await asyncio.gather(
        services.deposits.methods(active_only=True),
        services.deposits.pending_for(user.id),
        services.users.get(user.id),
    )
    displayed_methods = []

    if binance_enabled:
        # Saving Binance settings in the console already keeps this row in sync; rewriting it on every
        # tap cost several round trips and a row lock. Only create it when it has never been saved.
        binance_m = next((m for m in all_methods if m.get("auto_verify") == "binance_pay"), None)
        if binance_m is None:
            binance_m = await services.deposits.get_or_create_binance_method()
        if binance_m:
            displayed_methods.append(binance_m)

    for m in all_methods:
        if m.get("auto_verify") == "none":
            displayed_methods.append(m)

    lang = (user_data.get("language") or "en").strip().lower() if user_data else "en"
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    user_balance = float(user_data.get("balance", 0.0)) if user_data else 0.0
    balance_display = price(symbol, user_balance, usd_rate=usd_rate, show_usd=show_usd)

    if pending:
        text = t(
            "deposit_pending_summary",
            lang,
            icon_timer=ICON_TIMER,
            id=pending["id"],
            method=escape(pending["method_name"]),
            amount=price(symbol, pending["amount"], show_usd=False),
            trxid=escape(pending["transaction_id"]),
        )
        keyboard = get_deposit_methods_keyboard([], instant["label"], back_target=back_target, lang=lang) if instant else None
    else:
        text = t(
            "deposit_choose_method",
            lang,
            icon_deposit=ICON_DEPOSIT,
            icon_coin=ICON_COIN,
            icon_lightning=ICON_LIGHTNING,
            balance=balance_display,
        )
        keyboard = get_deposit_methods_keyboard(
            displayed_methods, instant["label"] if instant else None, back_target=back_target, lang=lang
        )
    await respond(event, text, keyboard)


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
    symbol = await services.settings.get("currency_symbol")
    await state.set_state(DepositStates.waiting_for_instant_amount)
    if query.message:
        text = (
            f"{ICON_LIGHTNING} <b>{escape(instant['label'])}</b>\n\n"
            f"{ICON_WARNING} <b>Minimum:</b> {price(symbol, instant['min_amount'], show_usd=False)}\n\n"
            f"{ICON_MONEY} <b>Enter deposit amount:</b>\n\n"
            f"💡 <i>(e.g. 100)</i>"
        )
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                text,
                reply_markup=get_cancel_keyboard(),
            )


def _instant_keyboard(invoice: dict) -> InlineKeyboardMarkup:
    rows = []
    if invoice.get("payment_url"):
        rows.append(
            [InlineKeyboardButton(text=f"Pay ৳{invoice['pay_amount']:.2f}", url=invoice["payment_url"], style="success", icon_custom_emoji_id=Icons.DEPOSIT)]
        )
    rows.append(
        [InlineKeyboardButton(text="I've Paid", callback_data=f"inst_chk_{invoice['reference']}", style="primary", icon_custom_emoji_id=Icons.CHECK)]
    )
    rows.append(
        [InlineKeyboardButton(text="Cancel Invoice", callback_data=f"inst_can_{invoice['reference']}", style="danger", icon_custom_emoji_id=Icons.CROSS)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_instant_invoice(invoice: dict, services: Services) -> tuple[str, InlineKeyboardMarkup]:
    symbol = await services.settings.get("currency_symbol")
    formatted_amount = price(symbol, invoice["pay_amount"], show_usd=False)
    ref = escape(str(invoice.get("reference") or invoice.get("id") or ""))
    ref_suffix = f" #{ref}" if ref else ""
    text = (
        f"{ICON_NOTE} <b>Payment Invoice{ref_suffix}</b>\n\n"
        f"{ICON_MONEY} <b>Payable Amount:</b> <code>{formatted_amount}</code>\n"
        f"{ICON_LIGHTNING} <b>Method:</b> Instant Auto Gateway\n"
        f"{ICON_TIMER} <b>Status:</b> Waiting for Payment\n\n"
        f"Click the <b>Pay</b> button below to complete payment (bKash, Nagad, Rocket, etc. supported). Your balance will be credited instantly upon successful payment."
    )
    return text, _instant_keyboard(invoice)


@router.message(DepositStates.waiting_for_instant_amount)
async def create_instant_payment(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return
    try:
        clean_amount = raw_text.replace("৳", "").replace("$", "").replace(",", "").strip()
        invoice = await services.payments.create_invoice(message.from_user.id, clean_amount)
    except ValueError as exc:
        await message.answer(f"{ICON_WARNING} {escape(str(exc))}", reply_markup=get_cancel_keyboard())
        return
    text, keyboard = await _render_instant_invoice(invoice, services)
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
    show_usd = await services.settings.flag("show_usd_price")
    if invoice["status"] == "completed":
        ref = escape(str(invoice.get("reference") or invoice.get("id") or ""))
        ref_suffix = f" #{ref}" if ref else ""
        pay_amt = float(invoice.get("pay_amount") or invoice.get("credit_amount") or 0.0)
        text = (
            f"{ICON_NOTE} <b>Payment Invoice{ref_suffix}</b>\n\n"
            f"{ICON_MONEY} <b>Payable Amount:</b> <code>{pay_amt:.2f} BDT</code>\n"
            f"{ICON_LIGHTNING} <b>Method:</b> Instant Auto Gateway\n"
            f"{ICON_CHECK} <b>Status:</b> <b>Paid / Completed</b>\n\n"
            f"✅ <i>Payment completed successfully! Balance has been added to your wallet.</i>"
        )
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="Deposit Menu", callback_data="open_deposit", style="primary", icon_custom_emoji_id=Icons.DEPOSIT)]]
                    ),
                )
        with suppress(TelegramBadRequest):
            await query.answer("Payment verified!")
    elif invoice["status"] in ("expired", "failed"):
        text = (
            f"{ICON_CROSS} <b>Payment Invoice #{escape(reference)} is no longer active.</b>\n\n"
            f"Status: <code>{invoice['status'].title()}</code>\n"
            f"Please create a new deposit request."
        )
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="Back to Deposit", callback_data="open_deposit", style="primary", icon_custom_emoji_id=Icons.DEPOSIT)]]
                    ),
                )
        with suppress(TelegramBadRequest):
            await query.answer("Invoice is no longer active.", show_alert=True)
    else:
        with suppress(TelegramBadRequest):
            await query.answer("Payment is not completed yet. Please complete the payment on the gateway and check again.", show_alert=True)


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
        f"{ICON_WARNING} <b>Cancel Payment Invoice #{escape(reference)}?</b>\n\n"
        f"Are you sure you want to cancel this payment invoice?\n\n"
        f"<i>⚠️ Note: If you have already sent money on the gateway, do not cancel. Tap \"I've Paid\" instead.</i>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm", callback_data=f"inst_cancfm_{reference}", style="danger", icon_custom_emoji_id=Icons.CROSS),
                InlineKeyboardButton(text="Keep", callback_data=f"inst_view_{reference}", style="primary", icon_custom_emoji_id=Icons.BACK),
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
    text, keyboard = await _render_instant_invoice(invoice, services)
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
    show_usd = await services.settings.flag("show_usd_price")

    if invoice["status"] == "completed":
        user = await services.users.get(query.from_user.id)
        text = (
            f"{ICON_CHECK} <b>Payment Already Completed!</b>\n"
            f"{ICON_SPARKLES} {price(symbol, invoice['credit_amount'], usd_rate=usd_rate, show_usd=show_usd)} has been credited to your account.\n\n"
            f"{ICON_BALANCE} <b>Current Balance:</b> <code>{price(symbol, user['balance'] if user else 0.0, usd_rate=usd_rate, show_usd=show_usd)}</code>"
        )
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Deposit Menu", callback_data="open_deposit", style="primary", icon_custom_emoji_id=Icons.DEPOSIT)]]
        )
    else:
        text = (
            f"{ICON_CROSS} <b>Payment Invoice #{escape(reference)} Cancelled</b>\n\n"
            f"Invoice has been successfully cancelled and no balance was deducted. You can make a new deposit anytime."
        )
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Back to Deposit", callback_data="open_deposit", style="primary", icon_custom_emoji_id=Icons.DEPOSIT)]]
        )

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=reply_markup)
    with suppress(TelegramBadRequest):
        await query.answer("Invoice cancelled.")


# --- Manual deposit (bKash, Nagad, Binance) ---
@router.callback_query(F.data.startswith("dep_method_"))
async def handle_deposit_method_select(query: CallbackQuery, state: FSMContext, services: Services):
    if await services.deposits.pending_for(query.from_user.id):
        with suppress(TelegramBadRequest):
            await query.answer("You already have a pending deposit request.", show_alert=True)
        return

    method_id = callback_int(query.data, "dep_method_")
    all_methods = await services.deposits.methods(active_only=True)
    method = next((m for m in all_methods if m["id"] == method_id), None)
    setting_values = await services.settings.values()

    if not method and setting_values.get("binance_enabled") == "1":
        binance_m = await services.deposits.get_or_create_binance_method()
        if binance_m and (binance_m["id"] == method_id or method_id == 6):
            method = binance_m

    if not method:
        with suppress(TelegramBadRequest):
            await query.answer("Payment method not found.", show_alert=True)
        return


    with suppress(TelegramBadRequest):
        await query.answer()

    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    min_dep = float(method["min_deposit"])
    account_info = method["account_info"]
    method_name = method["name"]
    rate = float(method["rate_to_currency"])

    min_coin = 1.0
    if method.get("auto_verify") == "binance_pay":
        account_info = setting_values.get("binance_pay_id") or account_info
        rate = float(setting_values.get("binance_pay_rate") or rate) or 125.0
        min_coin = float(setting_values.get("binance_pay_min") or 1.0)
        min_dep = round(min_coin * rate, 2)
        method_id = method["id"]

    await state.set_state(DepositStates.method_selected)
    account_type = method.get("account_type") or "personal"
    await state.set_data({
        "method_id": method_id,
        "method_name": method_name,
        "custom_emoji_id": method.get("custom_emoji_id"),
        "account_info": account_info,
        "account_type": account_type,
        "min_deposit": min_dep,
        "min_coin": min_coin,
        "rate": rate,
        "auto_verify": method.get("auto_verify", "none"),
    })

    if method.get("auto_verify") == "binance_pay":
        pay_id = setting_values.get("binance_pay_id") or account_info
        binance_name = (setting_values.get("binance_pay_name") or "").strip()
        name_line = f"{ICON_USER} <b>Binance Name:</b> <code>{escape(binance_name)}</code>\n" if binance_name else ""
        min_dep_line = f"{ICON_WARNING} <b>Minimum Deposit:</b> <code>{min_coin:g} USDT</code> (≈ {price(symbol, min_dep, show_usd=False)})\n"
        rate_line = f"{ICON_COIN} <b>Exchange Rate:</b> <code>1 USDT = {rate:.2f} {symbol}</code>\n" if rate and rate != 1.0 else ""

        text = (
            f"{ICON_BINANCE} <b>Binance Deposit</b>\n\n"
            f"{ICON_ID} <b>Binance ID:</b> <code>{escape(pay_id)}</code>\n"
            f"{name_line}"
            f"{min_dep_line}"
            f"{rate_line}\n"
            f"{ICON_NOTE} <b>Step-by-Step Payment Guide:</b>\n"
            f"1️⃣ Open the <b>Binance</b> app.\n"
            f"2️⃣ Go to <b>Assets</b> (or <b>Wallets</b>) at the bottom.\n"
            f"3️⃣ Tap <b>Send</b>.\n"
            f"4️⃣ Select <b>USDT</b> as the cryptocurrency.\n"
            f"5️⃣ Choose <b>Send to Binance User</b> (or <b>Send via Email / Phone / ID</b>).\n"
            f"6️⃣ Enter the <b>Binance ID</b> above and input the amount.\n"
            f"7️⃣ Review details and <b>Confirm</b> the payment.\n\n"
            f"💡 <i>After confirmation, you will receive an <b>Order ID</b>. Copy and send the Order ID below to automatically verify and credit your balance.</i>\n\n"
            f"👇 <b>Send your Binance Order ID below:</b>"
        )
        await state.set_state(DepositStates.waiting_for_binance_ref)
        await state.update_data(
            method_id=method_id,
            method_name=method_name,
            account_info=pay_id,
            auto_verify="binance_pay",
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Where to find Order ID?",
                        callback_data="binance_help_order_id",
                        style="primary",
                        icon_custom_emoji_id=Icons.QUESTION,
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Back",
                        callback_data="open_deposit",
                        style="primary",
                        icon_custom_emoji_id=Icons.BACK,
                    ),
                    InlineKeyboardButton(
                        text="Close",
                        callback_data="close_menu",
                        style="danger",
                        icon_custom_emoji_id=Icons.CLOSE,
                    ),
                ],
            ]
        )
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(text, reply_markup=kb)
        return

    type_label, action_label = get_account_type_labels(account_type)
    method_icon = get_method_icon(method)
    name_lower = method_name.lower()
    is_bd_wallet = any(w in name_lower for w in ("bkash", "nagad", "rocket", "upay", "cellfin", "tap")) or ("binance" not in name_lower and method.get("auto_verify") != "binance_pay")
    # BD wallets show BDT only — no USD conversion (would confuse users)
    effective_show_usd = False if is_bd_wallet else show_usd

    custom_instructions = (method.get("instructions") or "").strip()

    text = (
        f"{method_icon} <b>{escape(method_name)}</b>\n\n"
        f"{ICON_ID} <b>Number:</b> <code>{escape(account_info)}</code>\n"
        f"{ICON_DEPOSIT} <b>Account Type:</b> {type_label}\n"
        f"{ICON_MONEY} <b>Transaction:</b> {action_label}\n\n"
        f"{ICON_WARNING} <b>Minimum:</b> {price(symbol, min_dep, usd_rate=usd_rate, show_usd=effective_show_usd)}\n\n"
    )
    if custom_instructions:
        text += f"{ICON_NOTE} <b>Instructions:</b>\n{escape(custom_instructions)}\n\n"

    lang = await services.users.get_language(query.from_user.id)
    reply_kb = get_manual_deposit_invoice_keyboard(account_info, is_binance=False, lang=lang)

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=reply_kb)


@router.callback_query(F.data == "binance_help_order_id")
async def binance_help_order_id_handler(query: CallbackQuery, state: FSMContext, services: Services):
    data = await state.get_data()
    method_id = data.get("method_id")

    text = (
        f"{ICON_QUESTION} <b>Where to find your Order ID?</b>\n\n"
        f"1️⃣ Open the <b>Binance App</b> on your phone.\n"
        f"2️⃣ Tap <b>Assets</b> (or <b>Wallets</b>) at the bottom right.\n"
        f"3️⃣ Tap the <b>History</b> icon (clock symbol) at the top right.\n"
        f"4️⃣ Select the transfer you just sent.\n"
        f"5️⃣ Look for the <b>Order ID</b> (an 18–19 digit number).\n"
        f"6️⃣ Copy the <b>Order ID</b> and paste it here in the bot.\n\n"
        f"💡 <i>(e.g., <code>454711565717520384</code>)</i>"
    )
    back_target = f"dep_method_{method_id}" if method_id else "open_deposit"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Back to Deposit",
                    callback_data=back_target,
                    style="primary",
                    icon_custom_emoji_id=Icons.BACK,
                )
            ]
        ]
    )
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "dep_confirm_paid")
async def ask_deposit_input(query: CallbackQuery, state: FSMContext, services: Services):
    data = await state.get_data()
    method_id = data.get("method_id")
    if not method_id:
        with suppress(TelegramBadRequest):
            await query.answer("Please select a payment method again.", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer()

    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    auto_verify = data.get("auto_verify")
    method_name = data.get("method_name", "Payment")
    account_info = data.get("account_info", "")

    if auto_verify == "binance_pay":
        rate = data.get("rate", 125.0)
        min_coin = data.get("min_coin", 1.0)
        min_dep = data.get("min_deposit", min_coin * rate)
        await state.set_state(DepositStates.waiting_for_binance_ref)
        method_row = {"name": method_name, "auto_verify": auto_verify}
        method_icon = get_method_icon(method_row)
        min_dep_line = f"{ICON_WARNING} <b>Minimum Deposit:</b> <code>{min_coin:g} USDT</code> (≈ {price(symbol, min_dep, show_usd=False)})\n"
        rate_line = f"{ICON_COIN} <b>Exchange Rate:</b> <code>1 USDT = {rate:.2f} {symbol}</code>\n" if rate and rate != 1.0 else ""
        text = (
            f"{ICON_BINANCE} <b>{escape(method_name)} Deposit</b>\n\n"
            f"{ICON_ID} <b>Pay ID:</b> <code>{escape(account_info)}</code>\n"
            f"{min_dep_line}"
            f"{rate_line}\n"
            f"1️⃣ Send USDT (min {min_coin:g} USDT) to the Pay ID above\n"
            f"2️⃣ Paste your Order ID below\n\n"
            f"❗️ <i>Only up to 3 decimal places will be credited to your wallet.</i>\n\n"
            f"🥷 <i>Only payments started after opening this screen and completed within 30 minutes will be credited.</i>\n\n"
            f"<b>Please send your Order ID below:</b>"
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Where to find Order ID?",
                        callback_data="binance_help_order_id",
                        style="primary",
                        icon_custom_emoji_id=Icons.QUESTION,
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Back",
                        callback_data="open_deposit",
                        style="primary",
                        icon_custom_emoji_id=Icons.BACK,
                    ),
                    InlineKeyboardButton(
                        text="Close",
                        callback_data="close_menu",
                        style="danger",
                        icon_custom_emoji_id=Icons.CLOSE,
                    ),
                ],
            ]
        )
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(text, reply_markup=kb)
        return

    min_dep = data.get("min_deposit", 1.0)
    account_type = data.get("account_type", "personal")
    type_label, action_label = get_account_type_labels(account_type)
    await state.set_state(DepositStates.waiting_for_amount)
    method_row = {
        "name": method_name,
        "auto_verify": auto_verify,
        "custom_emoji_id": data.get("custom_emoji_id"),
    }
    method_icon = get_method_icon(method_row)
    name_lower = method_name.lower()
    is_bd_wallet = any(w in name_lower for w in ("bkash", "nagad", "rocket", "upay", "cellfin", "tap")) or ("binance" not in name_lower and auto_verify != "binance_pay")
    effective_show_usd = False if is_bd_wallet else show_usd
    text = (
        f"{method_icon} <b>{escape(method_name)}</b>\n\n"
        f"{ICON_ID} <b>Number:</b> <code>{escape(account_info)}</code>\n"
        f"{ICON_DEPOSIT} <b>Account Type:</b> {type_label}\n"
        f"{ICON_MONEY} <b>Transaction:</b> {action_label}\n\n"
        f"{ICON_WARNING} <b>Minimum:</b> {price(symbol, min_dep, usd_rate=usd_rate, show_usd=effective_show_usd)}\n\n"
        f"{ICON_MONEY} <b>Enter the amount you sent:</b>\n\n"
        f"💡 <i>(e.g. 100)</i>"
    )
    lang = await services.users.get_language(query.from_user.id)
    reply_kb = get_deposit_amount_keyboard(account_info, method_id, is_binance=False, lang=lang)

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=reply_kb)



@router.message(DepositStates.method_selected)
async def handle_method_selected_input(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    data = await state.get_data()
    auto_verify = data.get("auto_verify")
    if auto_verify == "binance_pay":
        await process_binance_amount(message, state, services)
    else:
        await process_deposit_amount(message, state, services)


# --- Binance Flow Handlers ---

@router.message(DepositStates.waiting_for_binance_amount)
async def process_binance_amount(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    data = await state.get_data()
    method_id = data.get("method_id", 0)
    account_info = data.get("account_info", "")
    rate = data.get("rate", 125.0)
    min_coin = data.get("min_coin", 1.0)
    min_dep = data.get("min_deposit", min_coin * rate)
    symbol = await services.settings.get("currency_symbol")

    clean_amount = re.sub(r"[^\d.]", "", raw_text)
    try:
        amount_num = float(clean_amount)
        if amount_num <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        await message.answer(
            f"{ICON_WARNING} Please enter a valid USDT amount (e.g. <code>10</code> or <code>25.5</code>):",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=True),
        )
        return

    if amount_num < min_coin:
        await message.answer(
            f"{ICON_WARNING} Minimum deposit is <b>{min_coin:g} USDT</b> (~{price(symbol, min_dep)}).\n"
            f"Please enter at least <b>{min_coin:g} USDT</b>:",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=True),
        )
        return

    await state.update_data(binance_usdt=amount_num)
    await state.set_state(DepositStates.waiting_for_binance_ref)

    bdt_approx = round(amount_num * rate, 2)
    await message.answer(
        f"{ICON_NOTE} <b>Payment Reference</b>\n\n"
        f"↳ <b>Amount:</b> <b>{amount_num:g} USDT</b> (~{price(symbol, bdt_approx)})\n"
        f"↳ <b>Binance ID:</b> <code>{escape(account_info)}</code>\n\n"
        f"Enter your <b>Binance Order ID</b> or your <b>Binance UID</b>:\n\n"
        f"↳ <b>Order ID:</b> <code>454711565717520384</code>\n"
        f"↳ <b>Or Sender UID:</b> <code>580150694</code> (your Binance UID)",
        reply_markup=get_deposit_txid_keyboard(),
    )


@router.message(DepositStates.waiting_for_binance_ref)
async def process_binance_ref(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    clean_ref = re.sub(r"^(uid|order\s*id|order|txid|trxid|trx\s*id|ref)[\s:#=]*", "", raw_text, flags=re.IGNORECASE).strip()
    clean_ref = clean_ref.strip("<>#[](){}\"':; \t\r\n")

    if not TRANSACTION_ID_REGEX.fullmatch(clean_ref):
        await message.answer(
            f"{ICON_CROSS} Invalid reference format. Please enter a valid Binance Order ID or sender Binance UID:\n\n"
            f"<i>💡 (e.g., <code>454711565717520384</code>)</i>",
            reply_markup=get_deposit_txid_keyboard(),
        )
        return

    data = await state.get_data()
    method_id = data.get("method_id")
    expected_usdt = data.get("binance_usdt")

    if not method_id:
        await state.clear()
        await message.answer(f"{ICON_TIMER} Session expired. Please tap Deposit to try again.")
        return

    await claim_binance_payment(message, state, services, method_id, clean_ref, expected_usdt=expected_usdt)


async def _safe_edit_or_answer(status_msg: Message, user_msg: Message, text: str, reply_markup=None):
    try:
        await status_msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        # Telegram refuses an edit that would change nothing. That is not a failure —
        # what this call wanted to say is already on screen — but answering instead
        # posted a second copy, so a three-step wait left the customer looking at the
        # same card three times over.
        if "message is not modified" in str(exc).lower():
            return
        await user_msg.answer(text, reply_markup=reply_markup)
    except Exception:
        await user_msg.answer(text, reply_markup=reply_markup)


async def claim_binance_payment(
    message: Message,
    state: FSMContext,
    services: Services,
    method_id: int,
    ref: str,
    expected_usdt: float | None = None,
):
    status_msg = await message.answer(
        f"{ICON_TIMER} <b>Verifying Binance payment...</b>\n\n"
        f"<b>Reference:</b> <code>{escape(ref)}</code>\n\n"
        f"<i>Checking Binance records, please wait...</i>"
    )
    try:
        result = await services.binance.claim(message.from_user.id, method_id, ref, expected_usdt=expected_usdt)
    except DuplicateTransactionError:
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_CROSS} <b>Payment Already Processed</b>\n\n"
            f"This transaction reference (<code>{escape(ref)}</code>) has already been submitted or credited.\n"
            f"If you need help, please contact support.",
            reply_markup=get_deposit_txid_keyboard(),
        )
        return
    except PendingDepositError:
        await state.clear()
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_TIMER} <b>Pending Deposit Exists</b>\n\n"
            f"You already have a deposit request waiting for review.\n"
            f"Please wait for it to be confirmed before submitting a new one.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER)],
                    [InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)],
                ]
            ),
        )
        return
    except (InvalidInputError, ValueError) as exc:
        await state.clear()
        await _safe_edit_or_answer(status_msg, message, f"{ICON_CROSS} {escape(str(exc))}")
        return

    if result.get("error") in ("not_found", "already_used"):
        # Nothing was filed, so the customer can simply send the right one; the step stays open.
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_CROSS} This Order ID has already been used. Send the Order ID of your new payment."
            if result["error"] == "already_used" else
            f"{ICON_CROSS} Order ID not found. Check it in Binance and send it again.",
            reply_markup=get_deposit_txid_keyboard(),
        )
        return

    await state.clear()
    symbol = await services.settings.get("currency_symbol")

    if result.get("credited"):
        user = await services.users.get(message.from_user.id)
        user_balance = user["balance"] if user else 0.0
        received_coin = result.get("received_coin") or expected_usdt or 0.0
        coin = result.get("coin", "USDT")
        credited_amount = result.get("amount", 0.0)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Products Hub", callback_data="open_shop", style="success", icon_custom_emoji_id=Icons.PRODUCTS),
                    InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
                ]
            ]
        )

        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_CHECK} <b>Binance Deposit Successful!</b>\n\n"
            f"{ICON_BINANCE} <b>Received:</b> <code>{received_coin:g} {escape(coin)}</code>\n"
            f"{ICON_MONEY} <b>Credited:</b> <code>{price(symbol, credited_amount)}</code>\n"
            f"{ICON_BALANCE} <b>Balance:</b> <code>{price(symbol, user_balance)}</code>\n"
            f"{ICON_KEY} <b>Reference:</b> <code>{escape(ref)}</code>\n\n"
            f"<i>Your wallet has been credited automatically. Thank you!</i>",
            reply_markup=keyboard,
        )
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Check Status", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER),
                    InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
                ]
            ]
        )
        if result.get("needs_person"):
            # Binance answered, and the answer was no. The reason goes to the admin note;
            # the customer only needs to know it is saved and not to pay twice.
            text = (
                f"{ICON_WARNING} <b>Couldn't verify this payment</b>\n"
                f"Order ID: <code>{escape(ref)}</code>\n\n"
                f"An admin will check it. Please don't pay again."
            )
        else:
            text = (
                f"{ICON_TIMER} <b>Checking payment...</b>\n"
                f"Order ID: <code>{escape(ref)}</code>\n\n"
                f"Your balance is added as soon as it's confirmed."
            )
        await _safe_edit_or_answer(status_msg, message, text, reply_markup=keyboard)


# --- Manual Flow Handlers (bKash / Nagad / Rocket) ---

@router.message(DepositStates.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    data = await state.get_data()
    method_id = data.get("method_id", 0)
    account_info = data.get("account_info", "")
    min_dep = data.get("min_deposit", 1.0)
    symbol = await services.settings.get("currency_symbol")

    clean_amount = raw_text.replace("৳", "").replace("$", "").replace(",", "").strip()
    try:
        amount_num = float(clean_amount)
        if amount_num <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        await message.answer(
            f"{ICON_WARNING} Please enter a valid number (e.g. <code>500</code>):",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=False),
        )
        return

    if amount_num < min_dep:
        await message.answer(
            f"{ICON_WARNING} Minimum deposit is {price(symbol, min_dep)}. Please enter a valid amount:",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=False),
        )
        return

    # The ceiling used to be enforced only once the customer came back with a
    # transaction ID — after the bot had shown them the number and the amount to send.
    # Someone following those instructions would have paid before being refused.
    max_dep = await services.settings.number("max_deposit_limit")
    if max_dep and amount_num > max_dep:
        await message.answer(
            f"{ICON_WARNING} Maximum deposit is {price(symbol, max_dep)}. Contact support for larger amounts.\n\n"
            f"Please enter an amount within this limit:",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=False),
        )
        return

    await state.update_data(manual_amount=amount_num)
    await state.set_state(DepositStates.waiting_for_txid)

    method_name = data.get("method_name", "Payment")
    account_type = data.get("account_type", "personal")
    _, action_label = get_account_type_labels(account_type)
    method_row = {
        "name": method_name,
        "auto_verify": data.get("auto_verify"),
        "custom_emoji_id": data.get("custom_emoji_id"),
    }
    method_icon = get_method_icon(method_row)  # ← fix: was missing this call
    await message.answer(
        f"{method_icon} <b>{escape(method_name)}</b>\n\n"
        f"{ICON_MONEY} <b>Amount:</b> {price(symbol, amount_num, show_usd=False)}\n"
        f"{ICON_ID} <b>Number:</b> <code>{escape(account_info)}</code> ({action_label})\n\n"
        f"{ICON_NOTE} <b>Enter Transaction ID (TrxID) from your {escape(method_name)} SMS / receipt:</b>\n\n"
        f"💡 <i>(e.g. <code>BLA7X8Y9Z0</code>)</i>",
        reply_markup=get_deposit_txid_keyboard(is_bangla=False),
    )


@router.message(DepositStates.waiting_for_txid)
async def process_deposit_txid(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    data = await state.get_data()
    method_id = data.get("method_id")
    amount_num = data.get("manual_amount")
    method_name = data.get("method_name", "Payment")
    is_binance = "binance" in method_name.lower() or data.get("auto_verify") == "binance_pay"

    clean_tx = re.sub(r"^(trxid|trx\s*id|txid|ref)[\s:#=]*", "", raw_text, flags=re.IGNORECASE).strip()
    clean_tx = clean_tx.strip("<>#[](){}\"':; \t\r\n")

    if not TRANSACTION_ID_REGEX.fullmatch(clean_tx):
        await message.answer(
            f"{ICON_CROSS} Invalid Transaction ID format. Please enter a valid Reference/TrxID from your SMS or receipt.\n"
            f"💡 <i>e.g. <code>BLA7X8Y9Z0</code></i>",
            reply_markup=get_deposit_txid_keyboard(is_bangla=False),
        )
        return

    user_id = message.from_user.id

    # Fast pre-check: if user already has an active pending deposit, avoid hitting external verification APIs
    existing_pending = await services.deposits.pending_for(user_id)
    if existing_pending:
        await state.clear()
        kb = [
            [InlineKeyboardButton(text="Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER)],
            [InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)],
        ]
        text = f"{ICON_TIMER} A deposit of yours is still being checked. Please wait for it to finish."
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    now = time.time()
    fails = await services.deposits.verification_failures(user_id)

    if len(fails) >= MAX_VERIFY_ATTEMPTS:
        remaining_sec = int(VERIFY_COOLDOWN_SECONDS - (now - fails[0]))
        rem_min = max(1, (remaining_sec + 59) // 60)
        await state.clear()
        support_user = await services.settings.get("support_username")
        kb = [[InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)]]
        if support_user:
            clean_sup = support_user.lstrip("@")
            kb.insert(0, [InlineKeyboardButton(text="Support", url=f"https://t.me/{clean_sup}", icon_custom_emoji_id=Icons.SUPPORT)])
        await message.answer(
            f"{ICON_CROSS} Too many wrong TrxIDs entered. Try again in {rem_min} minute(s).",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        )
        return

    if not method_id or not amount_num:
        await state.clear()
        await message.answer(
            f"{ICON_TIMER} Session expired. Please tap Deposit to try again."
        )
        return

    symbol = await services.settings.get("currency_symbol")

    status_msg = await message.answer(
        f"{ICON_TIMER} <b>Checking payment...</b>\n"
        f"Method: {escape(method_name)}\n"
        f"Amount: {price(symbol, amount_num, show_usd=False)}\n"
        f"TrxID: <code>{escape(clean_tx)}</code>"
    )

    logger.info("Processing deposit verification for user %s", message.from_user.id)

    async def on_sync_wait(waited: float, total: float) -> None:
        """Keep the customer company while the transaction is being verified."""
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_TIMER} <b>Checking payment... ({int(waited)}/{int(total)}s)</b>\n"
            f"Method: {escape(method_name)}\n"
            f"Amount: {price(symbol, amount_num, show_usd=False)}\n"
            f"TrxID: <code>{escape(clean_tx)}</code>",
        )

    # If ZiniPay auto-verify is configured, attempt automated verification
    zinipay_on = await services.zinipay.is_enabled()
    logger.info("ZiniPay is_enabled: %s", zinipay_on)
    if zinipay_on:
        try:
            res = await services.zinipay.claim(
                message.from_user.id,
                method_id,
                amount_num,
                clean_tx,
                quoted_rate=data.get("rate", 1.0),
                on_sync_wait=on_sync_wait,
            )
            logger.info("ZiniPay claim outcome: credited=%s", res.get("credited", False))
        except DuplicateTransactionError:
            # This TrxID is already credited in our own database, decided by an indexed
            # lookup before the gateway is ever called. Retrying it can never succeed, so
            # counting it as a verification attempt only punishes a customer who pastes the
            # same receipt twice, and locks them out of a deposit they are entitled to make.
            # The attempt budget is there to stop TrxIDs being guessed against the gateway,
            # and nothing on this path reaches the gateway.
            text = f"{ICON_CROSS} This TrxID has already been used. Send a new one."
            await _safe_edit_or_answer(
                status_msg,
                message,
                text,
                reply_markup=get_deposit_txid_keyboard(is_bangla=False),
            )
            return
        except PendingDepositError:
            await state.clear()
            kb = [
                [InlineKeyboardButton(text="Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER)],
                [InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)],
            ]
            text = f"{ICON_TIMER} A deposit of yours is still being checked. Please wait for it to finish."
            await _safe_edit_or_answer(
                status_msg,
                message,
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            )
            return
        except (InvalidInputError, ValueError) as exc:
            await state.clear()
            await _safe_edit_or_answer(status_msg, message, f"{ICON_CROSS} {escape(str(exc))}")
            return

        if res.get("auto_verified") and res.get("credited"):
            await services.deposits.clear_verification_failures(user_id)
            await state.clear()
            user = await services.users.get(message.from_user.id)
            user_balance = user["balance"] if user else 0.0
            provider = res.get("provider") or method_name
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Products Hub", callback_data="open_shop", style="success", icon_custom_emoji_id=Icons.PRODUCTS),
                        InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
                    ]
                ]
            )
            text = (
                f"{ICON_CHECK} <b>Deposit successful!</b>\n"
                f"Method: {escape(provider)}\n"
                f"Added: {price(symbol, amount_num, show_usd=False)}\n"
                f"Current balance: {price(symbol, user_balance, show_usd=False)}"
            )
            await _safe_edit_or_answer(status_msg, message, text, reply_markup=keyboard)
            return

        if res.get("pending_sync"):
            # The transaction is still syncing with the gateway. Drop the step so a
            # stray message is not read as another TrxID, but keep what the customer
            # already told us: the Fix button puts them back on this same deposit, and
            # clear() threw away the method and the amount, so the corrected TrxID
            # landed in an expired session and nothing was credited.
            # tests/test_deposit_flow.py fails if this goes back to clear().
            await state.set_state(None)
            dep_id = res.get("deposit_id")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Fix TrxID",
                                      callback_data=f"dep_fix_trx_{dep_id}",
                                      style="primary", icon_custom_emoji_id=Icons.BACK)],
                [InlineKeyboardButton(text="Deposit History",
                                      callback_data=f"open_deposits_dep_{dep_id}" if dep_id else "open_deposits",
                                      icon_custom_emoji_id=Icons.TIMER)],
            ])
            text = (
                f"{ICON_TIMER} <b>Checking payment...</b>\n"
                f"Method: {escape(method_name)}\n"
                f"Amount: {price(symbol, amount_num, show_usd=False)}\n"
                f"TrxID: <code>{escape(clean_tx)}</code>\n\n"
                f"Your balance will be added as soon as confirmed. Please do not send money again."
            )
            await _safe_edit_or_answer(status_msg, message, text, reply_markup=keyboard)
            return

        if res.get("error"):
            now = time.time()
            fails = await services.deposits.verification_failures(user_id, record_failure=True)
            remaining_attempts = MAX_VERIFY_ATTEMPTS - len(fails)

            if remaining_attempts <= 0:
                # 3rd attempt failed -> auto-convert to manual review so customer money is safe!
                await services.deposits.clear_verification_failures(user_id)
                await state.clear()

                err_type = res.get("error", "not_found")
                if err_type == "amount_mismatch":
                    admin_note = "ZiniPay auto-verify failed 3x (Amount mismatch). Auto-routed to manual review."
                elif err_type == "already_used":
                    admin_note = "ZiniPay auto-verify failed 3x (Already used on gateway). Auto-routed to manual review."
                elif err_type == "wrong_method":
                    admin_note = (f"ZiniPay auto-verify failed 3x: the transaction is {res.get('paid_with')}, "
                                  f"but the customer chose {method_name}. Do not credit without checking.")
                else:
                    admin_note = "ZiniPay auto-verify failed 3x (Not found - merchant SIM offline or SMS sync delay). Auto-routed to manual review."

                try:
                    dep_id = await services.deposits.create_request(
                        tg_user_id=user_id,
                        method_id=method_id,
                        amount=amount_num,
                        transaction_id=clean_tx,
                        quoted_rate=data.get("rate", 1.0),
                        admin_note=admin_note,
                    )
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="Deposit History",
                                    callback_data=f"open_deposits_dep_{dep_id}",
                                    style="primary",
                                    icon_custom_emoji_id=Icons.TIMER,
                                ),
                            ]
                        ]
                    )
                    success_text = (
                        f"{ICON_CHECK} <b>Deposit request submitted!</b>\n"
                        f"Method: {escape(method_name)}\n"
                        f"Amount: {price(symbol, amount_num, show_usd=False)}\n"
                        f"An admin will review it and add your balance."
                    )
                    await _safe_edit_or_answer(status_msg, message, success_text, reply_markup=keyboard)
                    return
                except DuplicateTransactionError:
                    support_user = await services.settings.get("support_username")
                    kb = [[InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)]]
                    if support_user:
                        clean_sup = support_user.lstrip("@")
                        kb.insert(0, [InlineKeyboardButton(text="Support", url=f"https://t.me/{clean_sup}", icon_custom_emoji_id=Icons.SUPPORT)])
                    await _safe_edit_or_answer(
                        status_msg,
                        message,
                        f"{ICON_CROSS} This TrxID has already been used.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                    )
                    return
                except PendingDepositError:
                    await _safe_edit_or_answer(
                        status_msg,
                        message,
                        f"{ICON_TIMER} A previous deposit of yours is still being checked. Please wait for it to finish.",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [InlineKeyboardButton(text="Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER)],
                                [InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)],
                            ]
                        ),
                    )
                    return
                except (InvalidInputError, ValueError) as exc:
                    await _safe_edit_or_answer(status_msg, message, f"{ICON_CROSS} {escape(str(exc))}")
                    return

            # Attempts 1 and 2 (remaining_attempts > 0)
            err_type = res.get("error", "not_found")
            left = f"\n<i>Tries left: {remaining_attempts}</i>"
            if err_type == "amount_mismatch":
                error_msg = f"{ICON_CROSS} Payment amount does not match. Tap 'Change Amount' to fix.{left}"
            elif err_type == "already_used":
                error_msg = f"{ICON_CROSS} This TrxID has already been used. Please enter a new TrxID.{left}"
            else:
                error_msg = f"{ICON_CROSS} Invalid TrxID. Please check your SMS / receipt and enter the correct TrxID.{left}"

            await _safe_edit_or_answer(
                status_msg,
                message,
                error_msg,
                reply_markup=get_deposit_txid_keyboard(is_bangla=False),
            )
            return

        lang = await services.users.get_language(message.from_user.id)
        if res.get("fallback_manual"):
            await state.clear()
            dep_id = res.get("deposit_id")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t("btn_balance_history", lang),
                            callback_data=f"open_deposits_dep_{dep_id}" if dep_id else "open_deposits",
                            style="primary",
                            icon_custom_emoji_id=Icons.TIMER,
                        ),
                    ]
                ]
            )
            text = t(
                "deposit_submitted_notice",
                lang,
                icon_check=ICON_CHECK,
                method=escape(method_name),
                amount=price(symbol, amount_num, show_usd=False),
            )
            await _safe_edit_or_answer(
                status_msg,
                message,
                text,
                reply_markup=keyboard,
            )
            return

    # Standard fallback when ZiniPay verification is not enabled
    try:
        dep_id = await services.deposits.create_request(
            message.from_user.id,
            method_id,
            amount_num,
            clean_tx,
            quoted_rate=data.get("rate", 1.0),
        )
    except DuplicateTransactionError:
        lang = await services.users.get_language(message.from_user.id)
        await _safe_edit_or_answer(
            status_msg,
            message,
            t("deposit_trxid_used", lang, icon_cross=ICON_CROSS),
            reply_markup=get_deposit_txid_keyboard(is_bangla=False, lang=lang),
        )
        return
    except PendingDepositError:
        await state.clear()
        lang = await services.users.get_language(message.from_user.id)
        await _safe_edit_or_answer(
            status_msg,
            message,
            t("deposit_pending_still", lang, icon_timer=ICON_TIMER),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=t("btn_balance_history", lang), callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER)],
                    [InlineKeyboardButton(text=t("btn_main_menu", lang), callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)],
                ]
            ),
        )
        return
    except (InvalidInputError, ValueError) as exc:
        await state.clear()
        await _safe_edit_or_answer(status_msg, message, f"{ICON_CROSS} {escape(str(exc))}")
        return

    await state.clear()
    lang = await services.users.get_language(message.from_user.id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_balance_history", lang),
                    callback_data=f"open_deposits_dep_{dep_id}" if dep_id else "open_deposits",
                    style="primary",
                    icon_custom_emoji_id=Icons.TIMER,
                ),
            ]
        ]
    )

    text = t(
        "deposit_submitted_notice",
        lang,
        icon_check=ICON_CHECK,
        method=escape(method_name),
        amount=price(symbol, amount_num, show_usd=False),
    )

    await _safe_edit_or_answer(
        status_msg,
        message,
        text,
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("dep_fix_trx_"))
async def fix_awaiting_transaction_id(query: CallbackQuery, state: FSMContext, services: Services):
    """"I typed the TrxID wrong" — stop waiting for a receipt that will never arrive.

    Without this the customer is held by the one-pending-deposit rule until the worker
    gives up, which is a long time to sit with a typo they have already spotted."""
    deposit_id = int(query.data.removeprefix("dep_fix_trx_") or 0)
    cancelled = await services.deposits.cancel_awaiting_sms(deposit_id, query.from_user.id)
    if not cancelled:
        with suppress(TelegramBadRequest):
            await query.answer("This request cannot be cancelled anymore.", show_alert=True)
        return
    with suppress(TelegramBadRequest):
        await query.answer()
    await state.set_state(DepositStates.waiting_for_txid)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_NEXT} Please enter the correct TrxID:\n"
                f"💡 <i>e.g. <code>BLA7X8Y9Z0</code></i>",
                reply_markup=get_deposit_txid_keyboard(is_bangla=False),
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
    async with services.db.connect() as conn:
        dep = await conn.fetchrow(
            "SELECT * FROM deposits WHERE id = $1 AND tg_user_id = $2",
            dep_id, user.id
        )
    if not dep:
        with suppress(TelegramBadRequest):
            await query.answer("Deposit request not found.", show_alert=True)
        return

    lang = await services.users.get_language(user.id)
    symbol = await services.settings.get("currency_symbol")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_balance_history", lang),
                    callback_data=f"open_deposits_dep_{dep_id}",
                    style="primary",
                    icon_custom_emoji_id=Icons.TIMER,
                ),
            ]
        ]
    )
    text = (
        f"{ICON_CHECK} <b>{t('deposit_submitted_notice', lang, icon_check=ICON_CHECK, method=escape(dep['method_name']), amount=price(symbol, dep['amount'], show_usd=False))}</b>\n\n"
        f"{ICON_KEY} <b>{t('deposit_trxid', lang)}:</b> <code>{escape(dep['transaction_id'])}</code>\n\n"
        f"<i>{t('status_pending_msg', lang)}</i>"
    )
    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=keyboard)


