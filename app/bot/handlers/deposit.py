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
    ICON_CROSS,
    ICON_DEPOSIT,
    ICON_KEY,
    ICON_LIGHTNING,
    ICON_MONEY,
    ICON_NEXT,
    ICON_NOTE,
    ICON_QUESTION,
    ICON_SPARKLES,
    ICON_TIMER,
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
@router.message(F.text.in_({"Add Balance", "add balance", "💰 Add Balance", "💳 Add Balance", "Deposit", "deposit", "💳 Deposit", "ডিপোজিট করুন"}))
@router.callback_query(F.data == "open_deposit")
@router.callback_query(F.data == "open_deposit_from_history")
@router.callback_query(F.data == "open_deposit_from_account")
async def show_deposit_methods(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Render deposit methods matching Screenshot 4."""
    await state.clear()
    user = event.from_user
    if not user:
        return

    back_target: str | None = None
    if isinstance(event, CallbackQuery):
        if event.data == "open_deposit_from_history":
            back_target = "open_deposits"
        elif event.data == "open_deposit_from_account":
            back_target = "open_account"

    paused_msg = await services.settings.paused_message()
    if paused_msg:
        await respond(event, f"{ICON_WARNING} <b>Deposits Temporarily Paused</b>\n\n{escape(paused_msg)}", None)
        return

    instant = await services.payments.instant_options()
    setting_values = await services.settings.values()
    binance_enabled = setting_values.get("binance_enabled") == "1"

    # Independent reads, so they share one database round trip instead of queueing.
    all_methods, pending = await asyncio.gather(
        services.deposits.methods(active_only=True), services.deposits.pending_for(user.id)
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

    if pending:
        symbol = await services.settings.get("currency_symbol")
        text = (
            f"{ICON_TIMER} <b>Deposit #{pending['id']} Pending Review</b>\n\n"
            f"Method: {escape(pending['method_name'])}\n"
            f"Amount: {price(symbol, pending['amount'])}\n"
            f"TrxID: <code>{escape(pending['transaction_id'])}</code>\n\n"
            f"<i>Balance will be credited once verified by an admin.</i>"
        )
        keyboard = get_deposit_methods_keyboard([], instant["label"], back_target=back_target) if instant else None
    else:
        text = f"{ICON_DEPOSIT} <b>Choose your payment method:</b>"
        keyboard = get_deposit_methods_keyboard(
            displayed_methods, instant["label"] if instant else None, back_target=back_target
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
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    await state.set_state(DepositStates.waiting_for_instant_amount)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_LIGHTNING} <b>{escape(instant['label'])}</b>\n"
                f"Minimum {price(symbol, instant['min_amount'], usd_rate=usd_rate, show_usd=show_usd)}\n\n"
                "Enter amount to deposit (e.g. <code>100</code>):",
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
    rows.append([InlineKeyboardButton(text="Back", callback_data="open_deposit", style="danger", icon_custom_emoji_id=Icons.BACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    formatted_amount = price(symbol, invoice["pay_amount"], usd_rate=usd_rate, show_usd=show_usd)
    ref = escape(str(invoice.get("reference") or invoice.get("id") or ""))
    ref_suffix = f" #{ref}" if ref else ""
    await message.answer(
        f"{ICON_NOTE} <b>Payment Invoice{ref_suffix}</b>\n\n"
        f"{ICON_MONEY} <b>Payable Amount:</b> <code>{formatted_amount}</code>\n"
        f"{ICON_LIGHTNING} <b>Method:</b> Instant Auto Gateway\n"
        f"{ICON_TIMER} <b>Status:</b> Waiting for Payment\n\n"
        f"🇬🇧 Tap the <b>Pay</b> button below to open the payment page. You can complete payment using any preferred method (bKash, Nagad, Rocket, Cards), and your balance will be added automatically.\n\n"
        f"🇧🇩 নিচের <b>Pay</b> বাটনে ট্যাপ করলে পেমেন্ট পেজে নিয়ে যাবে। সেখান থেকে আপনার পছন্দ অনুযায়ী যেকোনো মেথডে (bKash, Nagad, Rocket ইত্যাদি) পেমেন্ট সম্পন্ন করতে পারবেন এবং অটোমেটিক ব্যালেন্স যুক্ত হয়ে যাবে।",
        reply_markup=_instant_keyboard(invoice),
    )


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
        user = await services.users.get(query.from_user.id)
        text = (
            f"{ICON_CHECK} <b>Payment Successful!</b>\n"
            f"{ICON_SPARKLES} {price(symbol, invoice['credit_amount'], usd_rate=usd_rate, show_usd=show_usd)} has been credited to your account.\n\n"
            f"{ICON_BALANCE} <b>Current Balance:</b> <code>{price(symbol, user['balance'] if user else 0.0, usd_rate=usd_rate, show_usd=show_usd)}</code>"
        )
    else:
        text = f"{ICON_TIMER} <b>Payment not completed yet.</b> Please complete payment and check again."
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data="open_deposit", style="danger", icon_custom_emoji_id=Icons.BACK)]]
                ),
            )


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
        name_line = f"<b>Binance Name:</b> <code>{escape(binance_name)}</code>\n" if binance_name else ""

        text = (
            f"{ICON_BINANCE} <b>Binance Pay Deposit</b>\n\n"
            f"<b>Pay ID:</b> <code>{escape(pay_id)}</code>\n"
            f"{name_line}\n"
            f"1️⃣ Send any USDT amount to the Pay ID above\n"
            f"2️⃣ Paste your Order ID below\n\n"
            f"❗️ <i>Only up to 3 decimal places will be credited to your wallet.</i>\n\n"
            f"🥷 <i>Only payments started after opening this screen and completed within 30 minutes will be credited.</i>\n\n"
            f"<b>Please send your Order ID below:</b>"
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
        f"📱 <b>Number:</b> <code>{escape(account_info)}</code>\n"
        f"🏦 <b>Account Type:</b> {type_label}\n"
        f"💸 <b>Transaction:</b> {action_label}\n\n"
        f"{ICON_WARNING} <b>Minimum:</b> {price(symbol, min_dep, usd_rate=usd_rate, show_usd=effective_show_usd)}\n\n"
    )
    if custom_instructions:
        text += f"📋 <b>Instructions:</b>\n{escape(custom_instructions)}\n\n"

    reply_kb = get_manual_deposit_invoice_keyboard(account_info, is_binance=False)

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=reply_kb)


@router.callback_query(F.data == "binance_help_order_id")
async def binance_help_order_id_handler(query: CallbackQuery, state: FSMContext, services: Services):
    data = await state.get_data()
    method_id = data.get("method_id")

    text = (
        f"{ICON_QUESTION} <b>Where to find your Order ID?</b>\n\n"
        f"1. Open the <b>Binance App</b> on your phone\n"
        f"2. Tap <b>Pay</b> (top right or under Services)\n"
        f"3. Tap the <b>Payment History</b> icon (top right corner)\n"
        f"4. Select the payment you just sent to our Pay ID\n"
        f"5. Look for <b>Order ID</b> (a 18-19 digit number)\n"
        f"6. Tap the copy icon next to the Order ID and send it here in the chat!\n\n"
        f"<i>Example Order ID: <code>454711565717520384</code></i>"
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
            await query.answer("আবার পেমেন্ট মেথড সিলেক্ট করুন।", show_alert=True)
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
        text = (
            f"{method_icon} <b>{escape(method_name)} Deposit</b>\n\n"
            f"<b>Pay ID:</b> <code>{escape(account_info)}</code>\n\n"
            f"1️⃣ Send any USDT amount to the Pay ID above\n"
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
        f"📱 <b>Number:</b> <code>{escape(account_info)}</code>\n"
        f"🏦 <b>Account Type:</b> {type_label}\n"
        f"💸 <b>Transaction:</b> {action_label}\n\n"
        f"{ICON_WARNING} <b>Minimum:</b> {price(symbol, min_dep, usd_rate=usd_rate, show_usd=effective_show_usd)}\n\n"
        f"{ICON_MONEY} <b>কত টাকা পাঠিয়েছেন তা নিচে লিখুন:</b>\n\n"
        f"💡 <i>(যেমন: <code>100</code>)</i>"
    )
    reply_kb = get_deposit_amount_keyboard(account_info, method_id, is_binance=False)

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
        f"{ICON_NOTE} <b>Payment Reference</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"↳ <b>Amount:</b> <b>{amount_num:g} USDT</b> (~{price(symbol, bdt_approx)})\n"
        f"↳ <b>Binance UID:</b> <code>{escape(account_info)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Enter your <b>Binance Pay Order ID</b> or your <b>Binance UID</b>:\n\n"
        f"↳ <b>Order ID:</b> <code>454711565717520384</code> (from Pay receipt)\n"
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
            f"{ICON_CROSS} Invalid reference format. Please enter a valid Binance Pay Order ID or sender Binance UID:\n\n"
            f"<i>Example: <code>454711565717520384</code> or <code>580150694</code></i>",
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
        f"<i>Checking Binance Pay records, please wait...</i>"
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
        expected_text = f"<b>Expected:</b> <code>{expected_usdt:g} USDT</code>\n" if expected_usdt else ""
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_TIMER} <b>Payment Verification in Progress...</b>\n\n"
            f"<b>Reference:</b> <code>{escape(ref)}</code>\n"
            f"{expected_text}\n"
            f"Searching Binance for your transfer. If you just sent it, please allow 1–2 minutes.\n\n"
            f"<i>Your balance will be credited automatically once confirmed.</i>",
            reply_markup=keyboard,
        )


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
            f"{ICON_WARNING} সঠিক সংখ্যা লিখুন (যেমন: <code>500</code>):",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=False),
        )
        return

    if amount_num < min_dep:
        await message.answer(
            f"{ICON_WARNING} সর্বনিম্ন ডিপোজিট {price(symbol, min_dep)}। সঠিক পরিমাণ লিখুন:",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=False),
        )
        return

    # The ceiling used to be enforced only once the customer came back with a
    # transaction ID — after the bot had shown them the number and the amount to send.
    # Someone following those instructions would have paid before being refused.
    max_dep = await services.settings.number("max_deposit_limit")
    if max_dep and amount_num > max_dep:
        await message.answer(
            f"{ICON_WARNING} সর্বোচ্চ ডিপোজিট {price(symbol, max_dep)}। এর বেশি লাগলে সাপোর্টে যোগাযোগ করুন।\n\n"
            f"অনুগ্রহ করে এর মধ্যে একটি পরিমাণ লিখুন:",
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
        f"📱 <b>Number:</b> <code>{escape(account_info)}</code> ({action_label})\n\n"
        f"{ICON_NOTE} <b>আপনার {escape(method_name)} SMS বা রিসিট থেকে Transaction ID (TrxID) দিন:</b>\n\n"
        f"💡 <i>(যেমন: <code>BLA7X8Y9Z0</code>)</i>",
        reply_markup=get_deposit_txid_keyboard(is_bangla=True),
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
        if is_binance:
            await message.answer(
                f"{ICON_CROSS} Invalid Transaction ID format. Please enter a valid Reference/TrxID from your receipt.",
                reply_markup=get_deposit_txid_keyboard(is_bangla=False),
            )
        else:
            await message.answer(
                f"{ICON_CROSS} ভুল Transaction ID ফরম্যাট। আপনার SMS/রিসিট থেকে সঠিক TrxID দিন।\n\n"
                f"💡 <i>(যেমন: <code>BLA7X8Y9Z0</code>)</i>",
                reply_markup=get_deposit_txid_keyboard(is_bangla=True),
            )
        return

    now = time.time()
    user_id = message.from_user.id
    fails = await services.deposits.verification_failures(user_id)

    if len(fails) >= MAX_VERIFY_ATTEMPTS:
        remaining_sec = int(VERIFY_COOLDOWN_SECONDS - (now - fails[0]))
        rem_min = max(1, (remaining_sec + 59) // 60)
        await state.clear()
        support_user = await services.settings.get("support_username")
        kb = [[InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)]]
        if support_user:
            clean_sup = support_user.lstrip("@")
            kb.insert(0, [InlineKeyboardButton(text="Support", url=f"https://t.me/{clean_sup}", icon_custom_emoji_id=Icons.SUPPORT)])
        if is_binance:
            await message.answer(
                f"{ICON_CROSS} <b>Verification Paused!</b>\n\n"
                f"{ICON_WARNING} You entered incorrect Transaction IDs {MAX_VERIFY_ATTEMPTS} times.\n"
                f"For security, verification is paused for <b>{rem_min} minute(s)</b>.\n\n"
                f"If you made a valid payment, please contact our support team.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            )
        else:
            await message.answer(
                f"{ICON_CROSS} <b>ভেরিফিকেশন সাময়িক স্থগিত!</b>\n\n"
                f"{ICON_WARNING} আপনি পরপর {MAX_VERIFY_ATTEMPTS} বার ভুল Transaction ID দিয়েছেন।\n"
                f"নিরাপত্তার জন্য পরবর্তী <b>{rem_min} মিনিট</b> ডিপোজিট ভেরিফাই করা যাবে না।\n\n"
                f"আপনার পেমেন্ট সঠিক হলে অনুগ্রহ করে সাপোর্টে যোগাযোগ করুন।",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
            )
        return

    if not method_id or not amount_num:
        await state.clear()
        await message.answer(
            f"{ICON_TIMER} Session expired. Please tap Deposit to try again."
            if is_binance
            else f"{ICON_TIMER} সেশন মেয়াদোত্তীর্ণ। আবার ডিপোজিট করতে Deposit এ ট্যাপ করুন।"
        )
        return

    symbol = await services.settings.get("currency_symbol")

    status_msg = await message.answer(
        f"{ICON_TIMER} <b>Verifying transaction...</b>\n\n"
        f"<b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
        f"<b>Amount:</b> <code>{price(symbol, amount_num)}</code>\n\n"
        f"<i>Checking payment gateway, please wait...</i>"
        if is_binance
        else
        f"{ICON_TIMER} <b>ট্রানজ্যাকশন যাচাই করা হচ্ছে...</b>\n\n"
        f"<b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
        f"<b>Amount:</b> {price(symbol, amount_num, show_usd=False)}\n\n"
        f"<i>যাচাই করা হচ্ছে, একটু অপেক্ষা করুন...</i>"
    )

    logger.info("Processing deposit verification for user %s", message.from_user.id)

    async def on_sync_wait(waited: float, total: float) -> None:
        """Keep the customer company while the receipt SMS reaches the gateway."""
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_TIMER} <b>Waiting for your receipt...</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
            f"<b>Amount:</b> <code>{price(symbol, amount_num)}</code>\n\n"
            f"<i>The bank SMS has not reached the gateway yet. Checking again — "
            f"up to {int(total)} seconds. Please do not pay again.</i>"
            if is_binance
            else
            f"{ICON_TIMER} <b>পেমেন্টের SMS-এর জন্য অপেক্ষা করা হচ্ছে...</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
            f"<b>Amount:</b> {price(symbol, amount_num, show_usd=False)}\n\n"
            f"<i>ব্যাংকের SMS গেটওয়েতে পৌঁছাতে কিছুটা সময় লাগে। আবার চেক করা হচ্ছে — "
            f"সর্বোচ্চ {int(total)} সেকেন্ড। অনুগ্রহ করে আবার টাকা পাঠাবেন না।</i>",
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
            if is_binance:
                text = (
                    f"{ICON_CROSS} <b>This TrxID is Already Used</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"This Transaction ID (<code>{escape(clean_tx)}</code>) has already been credited.\n\n"
                    f"{ICON_NEXT} <b>What to do:</b>\n"
                    f"1. Send the TrxID from your newest payment receipt.\n"
                    f"2. If you entered the wrong amount, tap <b>Change Amount</b> below to fix it.\n\n"
                    f"{ICON_WARNING} If you need help, contact support."
                )
            else:
                text = (
                    f"{ICON_CROSS} <b>এই TrxID অলরেডি ব্যবহার হয়ে গেছে</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"এই Transaction ID (<code>{escape(clean_tx)}</code>) দিয়ে ইতিপূর্বে ব্যালেন্স নেওয়া হয়েছে।\n\n"
                    f"{ICON_NEXT} <b>আপনার করণীয়:</b>\n"
                    f"১. নতুন পেমেন্ট করে থাকলে SMS বা রিসিট দেখে সঠিক TrxID দিন।\n"
                    f"২. টাকার পরিমাণ ভুল লিখে থাকলে নিচে <b>Change Amount</b> বাটনে চাপ দিয়ে সঠিক পরিমাণ বসিয়ে পুনরায় চেষ্টা করুন।\n\n"
                    f"{ICON_WARNING} কোনো সমস্যা মনে হলে সাপোর্টে যোগাযোগ করুন।"
                )
            await _safe_edit_or_answer(
                status_msg,
                message,
                text,
                reply_markup=get_deposit_txid_keyboard(is_bangla=not is_binance),
            )
            return
        except PendingDepositError:
            await state.clear()
            kb = [
                [InlineKeyboardButton(text="📜 Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER)],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)],
            ]
            if is_binance:
                text = (
                    f"{ICON_TIMER} <b>Pending Deposit Exists</b>\n\n"
                    f"You already have a deposit request waiting for review.\n"
                    f"Please wait for it to be processed before submitting a new one."
                )
            else:
                text = (
                    f"{ICON_TIMER} <b>পেন্ডিং ডিপোজিট আছে</b>\n\n"
                    f"আপনার একটি ডিপোজিট রিকোয়েস্ট অলরেডি রিভিউ এর জন্য অপেক্ষায় আছে।\n"
                    f"নতুন রিকোয়েস্ট পাঠানোর আগে পূর্বের রিকোয়েস্ট কনফার্ম হওয়া পর্যন্ত অপেক্ষা করুন।"
                )
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
                        InlineKeyboardButton(text="🛍️ Products Hub", callback_data="open_shop", style="success", icon_custom_emoji_id=Icons.PRODUCTS),
                        InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
                    ]
                ]
            )
            if is_binance:
                text = (
                    f"{ICON_CHECK} <b>Deposit Successful!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{ICON_DEPOSIT} <b>Method:</b> {escape(provider)}\n"
                    f"{ICON_MONEY} <b>Amount:</b> <code>{price(symbol, amount_num)}</code>\n"
                    f"{ICON_BALANCE} <b>Balance:</b> <code>{price(symbol, user_balance)}</code>\n"
                    f"{ICON_KEY} <b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Your balance has been credited automatically. Thank you!</i>"
                )
            else:
                text = (
                    f"{ICON_CHECK} <b>ডিপোজিট সফল!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"↳ <b>Method:</b> {escape(provider)}\n"
                    f"↳ <b>Amount:</b> {price(symbol, amount_num, show_usd=False)}\n"
                    f"↳ <b>Current Balance:</b> {price(symbol, user_balance, show_usd=False)}\n"
                    f"↳ <b>Transaction ID:</b> <code>{escape(clean_tx)}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"আপনার ওয়ালেটে স্বয়ংক্রিয়ভাবে টাকা যোগ হয়েছে। ধন্যবাদ!"
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
                else:
                    admin_note = "ZiniPay auto-verify failed 3x (Not found - merchant SIM offline or SMS sync delay). Auto-routed to manual review."

                try:
                    dep_id = await services.deposits.create_request(
                        user_id=user_id,
                        method_id=method_id,
                        amount=amount_num,
                        transaction_id=clean_tx,
                        quoted_rate=data.get("rate", 1.0),
                        note=admin_note,
                    )
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="📜 Deposit History",
                                    callback_data=f"open_deposits_dep_{dep_id}",
                                    style="primary",
                                    icon_custom_emoji_id=Icons.TIMER,
                                ),
                            ]
                        ]
                    )
                    if is_binance:
                        success_text = (
                            f"{ICON_CHECK} <b>Deposit Request Submitted for Review!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{ICON_DEPOSIT} <b>Method:</b> {escape(method_name)}\n"
                            f"{ICON_MONEY} <b>Amount:</b> <code>{price(symbol, amount_num)}</code>\n"
                            f"{ICON_KEY} <b>Reference:</b> <code>{escape(clean_tx)}</code>\n"
                            f"{ICON_NOTE} <b>Request ID:</b> <code>#{dep_id}</code>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{ICON_WARNING} Automated gateway verification timed out.\n\n"
                            f"{ICON_CHECK} <b>Your funds are completely safe!</b> Your request has been forwarded to admin review. Our team will verify and credit your balance shortly."
                        )
                    else:
                        success_text = (
                            f"{ICON_CHECK} <b>ডিপোজিট রিকোয়েস্ট অ্যাডমিন রিভিউতে জমা হয়েছে!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"↳ <b>Method:</b> {escape(method_name)}\n"
                            f"↳ <b>Amount:</b> {price(symbol, amount_num, show_usd=False)}\n"
                            f"↳ <b>Transaction ID:</b> <code>{escape(clean_tx)}</code>\n"
                            f"↳ <b>Request ID:</b> <code>#{dep_id}</code>\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                            f"{ICON_WARNING} গেটওয়ে থেকে ট্রানজ্যাকশনটি তাৎক্ষণিক স্বয়ংক্রিয়ভাবে ডিটেক্ট হয়নি।\n\n"
                            f"{ICON_CHECK} <b>চিন্তার কোনো কারণ নেই, আপনার টাকা সম্পূর্ণ নিরাপদ!</b>\n"
                            f"আপনার ডিপোজিট রিকোয়েস্টটি আমাদের অ্যাডমিন প্যানেলে জমা হয়েছে। অ্যাডমিন ম্যানুয়ালি চেক করে খুব দ্রুত আপনার ওয়ালেটে ব্যালেন্স যুক্ত করে দেবেন।"
                        )
                    await _safe_edit_or_answer(status_msg, message, success_text, reply_markup=keyboard)
                    return
                except DuplicateTransactionError:
                    support_user = await services.settings.get("support_username")
                    kb = [[InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)]]
                    if support_user:
                        clean_sup = support_user.lstrip("@")
                        kb.insert(0, [InlineKeyboardButton(text="Support", url=f"https://t.me/{clean_sup}", icon_custom_emoji_id=Icons.SUPPORT)])
                    await _safe_edit_or_answer(
                        status_msg,
                        message,
                        f"{ICON_CROSS} <b>পেমেন্ট ইতোমধ্যে প্রসেস হয়েছে</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"এই Transaction ID (<code>{escape(clean_tx)}</code>) দিয়ে আগেই ব্যালেন্স নেওয়া হয়েছে।\n\n"
                        f"যদি কোনো সমস্যা থাকে, অনুগ্রহ করে সাপোর্ট অ্যাডমিনের সাথে যোগাযোগ করুন।",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
                    )
                    return
                except PendingDepositError:
                    await _safe_edit_or_answer(
                        status_msg,
                        message,
                        f"{ICON_TIMER} <b>পেন্ডিং ডিপোজিট আছে</b>\n\n"
                        f"আপনার একটি ডিপোজিট রিকোয়েস্ট ইতোমধ্যে রিভিউ এর জন্য অপেক্ষায় আছে। পূর্বের রিকোয়েস্ট কনফার্ম হওয়া পর্যন্ত অপেক্ষা করুন।",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [InlineKeyboardButton(text="📜 Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER)],
                                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)],
                            ]
                        ),
                    )
                    return
                except (InvalidInputError, ValueError) as exc:
                    await _safe_edit_or_answer(status_msg, message, f"{ICON_CROSS} {escape(str(exc))}")
                    return

            # Attempts 1 and 2 (remaining_attempts > 0)
            err_type = res.get("error", "not_found")
            if is_binance:
                error_msg = (
                    f"{ICON_CROSS} <b>Verification Failed ({len(fails)}/{MAX_VERIFY_ATTEMPTS})</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{escape(res.get('detail', ''))}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{ICON_WARNING} You have <b>{remaining_attempts} attempt(s)</b> remaining.\n\n"
                    f"Please verify your Reference/TrxID and try again, or click <b>Change Amount</b>:"
                )
            elif err_type == "amount_mismatch":
                error_msg = (
                    f"{ICON_CROSS} <b>টাকার পরিমাণ মেলেনি ({len(fails)}/{MAX_VERIFY_ATTEMPTS})</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"↳ <b>Method:</b> {escape(method_name)}\n"
                    f"↳ <b>Amount:</b> {price(symbol, amount_num, show_usd=False)}\n"
                    f"↳ <b>Transaction ID:</b> <code>{escape(clean_tx)}</code>\n\n"
                    f"{ICON_QUESTION} <b>কেন এই সমস্যা হতে পারে?</b>\n"
                    f"আপনি {escape(method_name)} এ যে পরিমাণ টাকা পাঠিয়েছেন, এখানে তার চেয়ে ভিন্ন পরিমাণ লিখেছেন।\n\n"
                    f"{ICON_NEXT} <b>এখন আপনার করণীয়:</b>\n"
                    f"১. নিচে <b>Change Amount</b> বাটনে চাপ দিয়ে সঠিক পরিমাণ লিখুন।\n"
                    f"২. অথবা আপনার SMS রিসিট দেখে সঠিক TrxID টি মিলিয়ে পুনরায় দিন।\n\n"
                    f"{ICON_WARNING} আর {remaining_attempts} বার চেষ্টা করতে পারবেন। ৩ বার না পেলে এটি স্বয়ংক্রিয়ভাবে অ্যাডমিন রিভিউতে জমা হবে।"
                )
            elif err_type == "already_used":
                error_msg = (
                    f"{ICON_CROSS} <b>TrxID অলরেডি ব্যবহার হয়ে গেছে ({len(fails)}/{MAX_VERIFY_ATTEMPTS})</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"↳ <b>Method:</b> {escape(method_name)}\n"
                    f"↳ <b>Transaction ID:</b> <code>{escape(clean_tx)}</code>\n\n"
                    f"{ICON_QUESTION} <b>কেন এই সমস্যা হতে পারে?</b>\n"
                    f"এই Transaction ID টি দিয়ে ইতিপূর্বে ব্যালেন্স নেওয়া হয়েছে।\n\n"
                    f"{ICON_NEXT} <b>এখন আপনার করণীয়:</b>\n"
                    f"১. আপনার SMS বা রিসিট চেক করে সর্বশেষ নতুন TrxID দিন।\n"
                    f"২. টাকার পরিমাণ ভুল লিখে থাকলে নিচে <b>Change Amount</b> বাটনে চাপ দিয়ে সঠিক পরিমাণ বসিয়ে পুনরায় চেষ্টা করুন।\n\n"
                    f"{ICON_WARNING} আর {remaining_attempts} বার চেষ্টা করতে পারবেন।"
                )
            else:  # "not_found" and other errors
                error_msg = (
                    f"{ICON_CROSS} <b>ট্রানজ্যাকশন পাওয়া যায়নি ({len(fails)}/{MAX_VERIFY_ATTEMPTS})</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"↳ <b>Method:</b> {escape(method_name)}\n"
                    f"↳ <b>Amount:</b> {price(symbol, amount_num, show_usd=False)}\n"
                    f"↳ <b>Transaction ID:</b> <code>{escape(clean_tx)}</code>\n\n"
                    f"{ICON_QUESTION} <b>কেন এই সমস্যা হতে পারে?</b>\n"
                    f"TrxID লেখার সময় কোনো অক্ষর বা সংখ্যা ভুল হতে পারে।\n\n"
                    f"{ICON_NEXT} <b>এখন আপনার করণীয়:</b>\n"
                    f"১. আপনার পেমেন্ট SMS বা স্টেটমেন্ট দেখে সঠিক TrxID টি মিলিয়ে আবার লিখুন।\n"
                    f"২. টাকা এইমাত্র পাঠিয়ে থাকলে আরও এক মিনিট পর আবার চেষ্টা করুন।\n"
                    f"৩. টাকার পরিমাণ ভুল দিয়ে থাকলে নিচে <b>Change Amount</b> বাটনে চাপুন।\n\n"
                    f"{ICON_WARNING} আর {remaining_attempts} বার চেষ্টা করতে পারবেন। ৩ বার না পেলে এটি স্বয়ংক্রিয়ভাবে অ্যাডমিন রিভিউতে জমা হবে।"
                )

            await _safe_edit_or_answer(
                status_msg,
                message,
                error_msg,
                reply_markup=get_deposit_txid_keyboard(is_bangla=not is_binance),
            )
            return

        if res.get("fallback_manual"):
            await state.clear()
            dep_id = res.get("deposit_id")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📜 Deposit History",
                            callback_data=f"open_deposits_dep_{dep_id}" if dep_id else "open_deposits",
                            style="primary",
                            icon_custom_emoji_id=Icons.TIMER,
                        ),
                    ]
                ]
            )
            if is_binance:
                text = (
                    f"{ICON_CHECK} <b>Deposit Request Submitted!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{ICON_DEPOSIT} <b>Method:</b> {escape(method_name)}\n"
                    f"{ICON_MONEY} <b>Amount:</b> <code>{price(symbol, amount_num)}</code>\n"
                    f"{ICON_KEY} <b>Reference:</b> <code>{escape(clean_tx)}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"<i>Your payment request has been submitted for admin review. Balance will be added once verified.</i>"
                )
            else:
                text = (
                    f"{ICON_CHECK} <b>ডিপোজিট রিকোয়েস্ট জমা হয়েছে!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{ICON_DEPOSIT} <b>মেথড:</b> {escape(method_name)}\n"
                    f"{ICON_MONEY} <b>পরিমাণ:</b> <code>{price(symbol, amount_num, show_usd=False)}</code>\n"
                    f"{ICON_KEY} <b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"<i>আপনার পেমেন্ট রিকোয়েস্ট অ্যাডমিন রিভিউ এর জন্য জমা হয়েছে। যাচাই হলে ব্যালেন্স যোগ হবে।</i>"
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
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_CROSS} This Transaction ID has already been submitted."
            if is_binance
            else f"{ICON_CROSS} এই Transaction ID আগেই জমা দেওয়া হয়েছে! আপনার রিসিট চেক করুন।",
            reply_markup=get_deposit_txid_keyboard(is_bangla=not is_binance),
        )
        return
    except PendingDepositError:
        await state.clear()
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_TIMER} <b>Pending Deposit Exists</b>\n\nYou already have a deposit request waiting for review."
            if is_binance
            else
            f"{ICON_TIMER} <b>পেন্ডিং ডিপোজিট আছে</b>\n\n"
            f"আপনার একটি ডিপোজিট রিকোয়েস্ট রিভিউ এর জন্য অপেক্ষায় আছে।\n"
            f"নতুন রিকোয়েস্ট পাঠানোর আগে পূর্বের রিকোয়েস্ট কনফার্ম হওয়া পর্যন্ত অপেক্ষা করুন।",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📜 Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER)],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK)],
                ]
            ),
        )
        return
    except (InvalidInputError, ValueError) as exc:
        await state.clear()
        await _safe_edit_or_answer(status_msg, message, f"{ICON_CROSS} {escape(str(exc))}")
        return

    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Deposit History",
                    callback_data=f"open_deposits_dep_{dep_id}" if dep_id else "open_deposits",
                    style="primary",
                    icon_custom_emoji_id=Icons.TIMER,
                ),
            ]
        ]
    )

    if is_binance:
        text = (
            f"{ICON_CHECK} <b>Deposit Request Submitted!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_DEPOSIT} <b>Method:</b> {escape(method_name)}\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>{price(symbol, amount_num)}</code>\n"
            f"{ICON_KEY} <b>Reference:</b> <code>{escape(clean_tx)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>Balance will be added to your wallet once approved by admin.</i>"
        )
    else:
        text = (
            f"{ICON_CHECK} <b>ডিপোজিট রিকোয়েস্ট জমা হয়েছে!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_DEPOSIT} <b>মেথড:</b> {escape(method_name)}\n"
            f"{ICON_MONEY} <b>পরিমাণ:</b> <code>{price(symbol, amount_num, show_usd=False)}</code>\n"
            f"{ICON_KEY} <b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>অ্যাডমিন যাচাই করলে আপনার ওয়ালেটে ব্যালেন্স যোগ হবে।</i>"
        )

    await _safe_edit_or_answer(
        status_msg,
        message,
        text,
        reply_markup=keyboard,
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

    symbol = await services.settings.get("currency_symbol")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Deposit History",
                    callback_data=f"open_deposits_dep_{dep_id}",
                    style="primary",
                    icon_custom_emoji_id=Icons.TIMER,
                ),
            ]
        ]
    )
    is_binance = "binance" in (dep["method_name"] or "").lower()
    if is_binance:
        text = (
            f"{ICON_CHECK} <b>Deposit Request Submitted!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_DEPOSIT} <b>Method:</b> {escape(dep['method_name'])}\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>{price(symbol, dep['amount'])}</code>\n"
            f"{ICON_KEY} <b>Reference:</b> <code>{escape(dep['transaction_id'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>Balance will be added to your wallet once approved by admin.</i>"
        )
    else:
        text = (
            f"{ICON_CHECK} <b>ডিপোজিট রিকোয়েস্ট জমা হয়েছে!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_DEPOSIT} <b>মেথড:</b> {escape(dep['method_name'])}\n"
            f"{ICON_MONEY} <b>পরিমাণ:</b> <code>{price(symbol, dep['amount'], show_usd=False)}</code>\n"
            f"{ICON_KEY} <b>TrxID:</b> <code>{escape(dep['transaction_id'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>আপনার পেমেন্ট রিকোয়েস্ট অ্যাডমিন রিভিউ এর জন্য জমা হয়েছে। যাচাই হলে ব্যালেন্স যোগ হবে।</i>"
        )
    with suppress(TelegramBadRequest):
        await query.message.edit_text(text, reply_markup=keyboard)


