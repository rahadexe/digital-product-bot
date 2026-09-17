from __future__ import annotations

import re
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
from app.bot.handlers.start import render_main_dashboard
from app.bot.keyboards import (
    get_cancel_keyboard,
    get_deposit_methods_keyboard,
    get_manual_deposit_invoice_keyboard,
)
from app.services import Services
from app.services.deposits import DuplicateTransactionError

router = Router(name="deposit_router")

# Validates standard transaction IDs (bKash, Nagad, Binance, etc.)
TRANSACTION_ID_REGEX = re.compile(r"^[A-Za-z0-9_\-]{6,80}$")
PAYMENT_REFERENCE = re.compile(r"SM[0-9A-F]{16}")


class DepositStates(StatesGroup):
    method_selected = State()
    waiting_for_txid = State()
    waiting_for_amount = State()
    waiting_for_instant_amount = State()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, services: Services):
    await state.clear()
    await message.answer("❌ Current operation cancelled.")
    await render_main_dashboard(message, services, message.from_user.id)


@router.callback_query(F.data == "cancel_deposit")
async def cancel_deposit_flow(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer("Cancelled.")
    if query.message:
        await render_main_dashboard(query.message, services, query.from_user.id, edit=True)


@router.message(Command("deposit"))
@router.message(F.text == "💰 Add Balance")
@router.message(F.text == "💳 Deposit")
@router.message(F.text == "ডিপোজিট করুন")
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
        await respond(event, f"⚠️ <b>Deposits Temporarily Paused</b>\n\n{escape(paused_msg)}", None)
        return

    instant = await services.payments.instant_options()
    setting_values = await services.settings.values()
    binance_enabled = setting_values.get("binance_enabled") == "1"

    all_methods = await services.deposits.methods(active_only=True)
    displayed_methods = []

    if binance_enabled:
        binance_m = await services.deposits.get_or_create_binance_method()
        if binance_m:
            displayed_methods.append(binance_m)

    for m in all_methods:
        if m.get("auto_verify") == "none":
            displayed_methods.append(m)

    pending = await services.deposits.pending_for(user.id)
    if pending:
        symbol = await services.settings.get("currency_symbol")
        text = (
            f"⏳ <b>Deposit #{pending['id']} Pending Review</b>\n\n"
            f"Method: {escape(pending['method_name'])}\n"
            f"Amount: {price(symbol, pending['amount'])}\n"
            f"TrxID: <code>{escape(pending['transaction_id'])}</code>\n\n"
            f"<i>Balance will be credited once verified by an admin.</i>"
        )
        keyboard = get_deposit_methods_keyboard([], instant["label"], back_target=back_target) if instant else None
    else:
        text = "<b>Choose your payment method:</b>"
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
    await state.set_state(DepositStates.waiting_for_instant_amount)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"⚡ <b>{escape(instant['label'])}</b>\n"
                f"Minimum {price(symbol, instant['min_amount'])}\n\n"
                "Enter amount to deposit (e.g. <code>100</code>):",
                reply_markup=get_cancel_keyboard(),
            )



def _instant_keyboard(invoice: dict) -> InlineKeyboardMarkup:
    rows = []
    if invoice.get("payment_url"):
        rows.append(
            [InlineKeyboardButton(text=f"💳 Pay ৳{invoice['pay_amount']:.2f}", url=invoice["payment_url"])]
        )
    rows.append(
        [InlineKeyboardButton(text="✅ I've paid — Check", callback_data=f"inst_chk_{invoice['reference']}")]
    )
    rows.append([InlineKeyboardButton(text="◀ Back", callback_data="open_deposit", style="danger")])
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
        await message.answer(f"⚠️ {escape(str(exc))}", reply_markup=get_cancel_keyboard())
        return
    await state.clear()
    symbol = await services.settings.get("currency_symbol")
    await message.answer(
        f"🧾 <b>Payment Invoice: {price(symbol, invoice['credit_amount'])}</b>\n"
        f"Payable Amount: <b>{symbol}{invoice['pay_amount']:.2f}</b>\n\n"
        "Tap the Pay button below to complete payment. Your balance will be credited automatically upon confirmation.",
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
    if invoice["status"] == "completed":
        user = await services.users.get(query.from_user.id)
        text = (
            f"✅ <b>Payment Successful!</b>\n"
            f"🎉 {price(symbol, invoice['credit_amount'])} has been credited to your account.\n\n"
            f"💰 <b>Current Balance:</b> <code>{price(symbol, user['balance'] if user else 0.0)}</code>"
        )
    else:
        text = "⏳ <b>Payment not completed yet.</b> Please complete payment and check again."
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Back", callback_data="open_deposit", style="danger")]]
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
    min_dep = float(method["min_deposit"])
    account_info = method["account_info"]
    method_name = method["name"]
    rate = float(method["rate_to_currency"])

    if method.get("auto_verify") == "binance_pay":
        account_info = setting_values.get("binance_pay_id") or account_info
        rate = float(setting_values.get("binance_pay_rate") or rate) or 125.0
        min_dep = float(setting_values.get("binance_pay_min") or min_dep)
        method_id = method["id"]

    await state.set_state(DepositStates.method_selected)
    await state.set_data({
        "method_id": method_id,
        "method_name": method_name,
        "account_info": account_info,
        "min_deposit": min_dep,
        "rate": rate,
        "auto_verify": method.get("auto_verify", "none"),
    })

    if method.get("auto_verify") == "binance_pay":
        coin = setting_values.get("binance_coin", "USDT")
        min_coin = round(min_dep / rate, 2) if rate > 0 else min_dep
        text = (
            f"<b>{escape(method_name)} Deposit</b>\n\n"
            f"↳ <b>Binance UID:</b>\n"
            f"<code>{escape(account_info)}</code> <i>(Tap to copy)</i>\n"
            f"↳ <b>Currency:</b> {escape(coin)} ($)\n"
            f"↳ <b>Exchange Rate:</b> 1 {escape(coin)} = {rate:g} {symbol}\n"
            f"↳ <b>Minimum Deposit:</b> {min_coin:g} {escape(coin)} (~{price(symbol, min_dep)})"
        )
        custom_inst = (setting_values.get("binance_pay_instructions") or "").strip()
        if custom_inst:
            text += f"\n\n<b>Instructions:</b>\n{escape(custom_inst)}"
    else:
        text = (
            f"<b>{escape(method_name)} Deposit</b>\n\n"
            f"↳ <b>Account Number:</b>\n"
            f"<code>{escape(account_info)}</code> <i>(Tap to copy)</i>\n"
            f"↳ <b>Minimum Deposit:</b> {price(symbol, min_dep)}"
        )
        custom_instructions = (method.get("instructions") or "").strip()
        if custom_instructions:
            text += f"\n\n<b>Instructions:</b>\n{escape(custom_instructions)}"

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=get_manual_deposit_invoice_keyboard(account_info))


@router.callback_query(F.data == "dep_confirm_paid")
async def ask_txid_input(query: CallbackQuery, state: FSMContext, services: Services):
    data = await state.get_data()
    if not data.get("method_id"):
        with suppress(TelegramBadRequest):
            await query.answer("Please select a payment method again.", show_alert=True)
        return

    await state.set_state(DepositStates.waiting_for_txid)
    with suppress(TelegramBadRequest):
        await query.answer()

    if data.get("auto_verify") == "binance_pay":
        text = "Please enter your <b>Binance UID</b> (e.g. <code>87654321</code>):"
    else:
        text = "Please enter your payment <b>Transaction ID (TrxID)</b>:"

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=get_cancel_keyboard())


@router.message(DepositStates.waiting_for_txid)
@router.message(DepositStates.method_selected)
async def process_deposit_txid(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    data = await state.get_data()
    if not data.get("method_id"):
        await state.clear()
        await message.answer("⌛ Session expired. Please tap Deposit to try again.")
        return

    # If Binance Pay, sanitize UID (support formats like "UID: 12345678" or "12345678")
    if data.get("auto_verify") == "binance_pay":
        clean_uid = re.sub(r"[^\d]", "", raw_text)
        if clean_uid and 5 <= len(clean_uid) <= 20:
            raw_text = clean_uid

    # Exact error message matching method type
    if not TRANSACTION_ID_REGEX.fullmatch(raw_text):
        err_msg = (
            "❌ Invalid Binance UID format. Please enter a valid numeric UID."
            if data.get("auto_verify") == "binance_pay"
            else "❌ Invalid TRX ID format. Please enter a valid Transaction ID."
        )
        await message.answer(
            err_msg,
            reply_markup=get_cancel_keyboard(),
        )
        return

    await state.update_data(txid=raw_text)

    # If Binance auto-verify is configured on this method, claim directly
    if data.get("auto_verify") in ("binance", "binance_pay"):
        await claim_binance_payment(message, state, services, data["method_id"], raw_text)
        return

    # Prompt for the deposit amount
    symbol = await services.settings.get("currency_symbol")
    await state.set_state(DepositStates.waiting_for_amount)
    await message.answer(
        f"Enter the amount sent (numbers only, e.g. <code>150</code>):",
        reply_markup=get_cancel_keyboard(),
    )


async def claim_binance_payment(message: Message, state: FSMContext, services: Services, method_id: int, txid: str):
    try:
        result = await services.binance.claim(message.from_user.id, method_id, txid)
    except DuplicateTransactionError as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=get_cancel_keyboard())
        return
    except ValueError as exc:
        await state.clear()
        await message.answer(f"❌ {escape(str(exc))}")
        return

    await state.clear()
    symbol = await services.settings.get("currency_symbol")
    if result.get("credited"):
        user = await services.users.get(message.from_user.id)
        await message.answer(
            f"✅ <b>Payment Received!</b> · {price(symbol, result.get('amount') or 0)} credited.\n"
            f"💰 <b>Current Balance:</b> <code>{price(symbol, user['balance'] if user else 0.0)}</code>"
        )
    else:
        await message.answer(
            f"⏳ <b>Searching for payment...</b>\n\n{escape(result.get('detail', ''))}\n\n"
            "Your balance will be credited automatically once confirmed."
        )


@router.message(DepositStates.waiting_for_amount)
async def process_deposit_amount(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    clean_amount = raw_text.replace("৳", "").replace("$", "").replace(",", "").strip()
    try:
        amount_num = float(clean_amount)
        if amount_num <= 0:
            raise ValueError("Amount must be greater than 0.")
    except ValueError:
        await message.answer("⚠️ Please enter a valid number (e.g. 150):", reply_markup=get_cancel_keyboard())
        return

    data = await state.get_data()
    method_id = data.get("method_id")
    txid = data.get("txid")
    min_dep = data.get("min_deposit", 1.0)

    if amount_num < min_dep:
        symbol = await services.settings.get("currency_symbol")
        await message.answer(
            f"⚠️ Minimum deposit is {price(symbol, min_dep)}. Please enter a valid amount:",
            reply_markup=get_cancel_keyboard(),
        )
        return

    try:
        deposit_id = await services.deposits.create_request(
            message.from_user.id,
            method_id,
            amount_num,
            txid,
            quoted_rate=data.get("rate", 1.0),
        )
    except DuplicateTransactionError:
        await message.answer(
            "❌ This Transaction ID has already been submitted! Please check your receipt.",
            reply_markup=get_cancel_keyboard(),
        )
        return
    except ValueError as exc:
        await state.clear()
        await message.answer(f"❌ <b>Deposit failed:</b> {escape(str(exc))}")
        return

    await state.clear()
    symbol = await services.settings.get("currency_symbol")

    # Notify customer
    method_name = data.get("method_name", "Payment")
    await message.answer(
        f"✅ <b>Deposit Request Submitted!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💳 <b>Method:</b> {escape(method_name)}\n"
        f"💰 <b>Amount:</b> <code>{price(symbol, amount_num)}</code>\n"
        f"📝 <b>TrxID:</b> <code>{escape(txid)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Your wallet balance will be credited as soon as an admin verifies it.</i>"
    )

