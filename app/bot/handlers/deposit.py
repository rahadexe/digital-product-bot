from __future__ import annotations

import asyncio
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
from app.bot.icons import (
    ICON_BALANCE,
    ICON_BINANCE,
    ICON_CHECK,
    ICON_CROSS,
    ICON_DEPOSIT,
    ICON_KEY,
    ICON_LIGHTNING,
    ICON_MONEY,
    ICON_NOTE,
    ICON_SPARKLES,
    ICON_TIMER,
    ICON_WARNING,
    Icons,
    get_method_icon,
)
from app.bot.handlers.navigation import is_navigation, navigate
from app.bot.handlers.start import render_main_dashboard
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

router = Router(name="deposit_router")

# Validates standard transaction IDs and numeric UIDs (bKash, Nagad, Binance, etc.)
TRANSACTION_ID_REGEX = re.compile(r"^[A-Za-z0-9_\-]{5,80}$")
PAYMENT_REFERENCE = re.compile(r"SM[0-9A-F]{16}")


class DepositStates(StatesGroup):
    method_selected = State()
    waiting_for_amount = State()
    waiting_for_txid = State()
    waiting_for_binance_amount = State()
    waiting_for_binance_ref = State()
    waiting_for_instant_amount = State()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, services: Services):
    await state.clear()
    await message.answer(f"{ICON_CROSS} Current operation cancelled.")
    await render_main_dashboard(message, services, message.from_user.id)


@router.callback_query(F.data == "cancel_deposit")
async def cancel_deposit_flow(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer("Cancelled.")
    if query.message:
        await render_main_dashboard(query.message, services, query.from_user.id, edit=True)


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
    await state.set_state(DepositStates.waiting_for_instant_amount)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{ICON_LIGHTNING} <b>{escape(instant['label'])}</b>\n"
                f"Minimum {price(symbol, instant['min_amount'])}\n\n"
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
        [InlineKeyboardButton(text="I've Paid — Check", callback_data=f"inst_chk_{invoice['reference']}", style="primary", icon_custom_emoji_id=Icons.CHECK)]
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
    await state.clear()
    symbol = await services.settings.get("currency_symbol")
    await message.answer(
        f"{ICON_NOTE} <b>Payment Invoice: {price(symbol, invoice['credit_amount'])}</b>\n"
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
            f"{ICON_CHECK} <b>Payment Successful!</b>\n"
            f"{ICON_SPARKLES} {price(symbol, invoice['credit_amount'])} has been credited to your account.\n\n"
            f"{ICON_BALANCE} <b>Current Balance:</b> <code>{price(symbol, user['balance'] if user else 0.0)}</code>"
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
    await state.set_data({
        "method_id": method_id,
        "method_name": method_name,
        "account_info": account_info,
        "min_deposit": min_dep,
        "min_coin": min_coin,
        "rate": rate,
        "auto_verify": method.get("auto_verify", "none"),
    })

    if method.get("auto_verify") == "binance_pay":
        coin = setting_values.get("binance_coin", "USDT")
        custom_inst = (setting_values.get("binance_pay_instructions") or "").strip()
        inst_body = (
            f"\n\n<b>Instructions:</b>\n{escape(custom_inst)}"
            if custom_inst
            else (
                "\n\n<b>কিভাবে পেমেন্ট করবেন:</b>\n"
                "1. <b>Binance App</b> → <b>Assets</b> → <b>Send</b>\n"
                f"2. <b>{escape(coin)}</b> সিলেক্ট করুন → <b>Send to Binance User</b>\n"
                f"3. Binance UID দিন: <code>{escape(account_info)}</code>\n"
                f"4. <b>{escape(coin)}</b> পাঠান এবং নিচে <b>Payment Done</b> ট্যাপ করুন\n\n"
                f"<i>আপনি যত ডলার পাঠাবেন এই রেটে কনভার্ট হয়ে স্বয়ংক্রিয়ভাবে অ্যাকাউন্টে টাকা যোগ হয়ে যাবে।</i>"
            )
        )
        method_icon = get_method_icon(method)
        text = (
            f"{method_icon} <b>{escape(method_name)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"↳ <b>Binance UID:</b>\n"
            f"<code>{escape(account_info)}</code>\n\n"
            f"↳ <b>Minimum Deposit:</b> {min_coin:g} {escape(coin)} (~{price(symbol, min_dep)})\n"
            f"↳ <b>Exchange Rate:</b> 1 {escape(coin)} = {rate:g} {symbol}"
            f"{inst_body}"
        )
        reply_kb = get_manual_deposit_invoice_keyboard(account_info, is_binance=True)
    else:
        method_icon = get_method_icon(method)
        text = (
            f"{method_icon} <b>{escape(method_name)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"↳ <b>Account Number:</b>\n"
            f"<code>{escape(account_info)}</code>\n\n"
            f"↳ <b>Minimum Deposit:</b> {price(symbol, min_dep)}"
        )
        custom_instructions = (method.get("instructions") or "").strip()
        if custom_instructions:
            text += f"\n\n<b>Instructions:</b>\n{escape(custom_instructions)}"
        reply_kb = get_manual_deposit_invoice_keyboard(account_info, is_binance=False)

    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=reply_kb)


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
    auto_verify = data.get("auto_verify")
    method_name = data.get("method_name", "Payment")
    account_info = data.get("account_info", "")

    if auto_verify == "binance_pay":
        rate = data.get("rate", 125.0)
        min_coin = data.get("min_coin", 1.0)
        min_dep = data.get("min_deposit", min_coin * rate)
        await state.set_state(DepositStates.waiting_for_binance_amount)
        method_row = {"name": method_name, "auto_verify": auto_verify}
        method_icon = get_method_icon(method_row)
        text = (
            f"{method_icon} <b>{escape(method_name)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"↳ <b>Binance UID:</b>\n"
            f"<code>{escape(account_info)}</code>\n\n"
            f"↳ <b>Minimum Deposit:</b> {min_coin:g} USDT (~{price(symbol, min_dep)})\n"
            f"↳ <b>Exchange Rate:</b> 1 USDT = {rate:g} {symbol}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💬 <b>USDT পরিমাণ লিখুন:</b>\n"
            f"আপনি কত USDT পাঠিয়েছেন তা লিখুন\n\n"
            f"<i>নিচে পরিমাণ লিখুন (যেমন: <code>10</code> বা <code>25.5</code>):</i>"
        )
        reply_kb = get_deposit_amount_keyboard(account_info, method_id, is_binance=True)
    else:
        min_dep = data.get("min_deposit", 1.0)
        await state.set_state(DepositStates.waiting_for_amount)
        method_row = {"name": method_name, "auto_verify": auto_verify}
        method_icon = get_method_icon(method_row)
        text = (
            f"{method_icon} <b>{escape(method_name)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"↳ <b>Account Number:</b>\n"
            f"<code>{escape(account_info)}</code>\n\n"
            f"↳ <b>Minimum Deposit:</b> {price(symbol, min_dep)}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💬 <b>টাকার পরিমাণ লিখুন:</b>\n"
            f"আপনি কত টাকা পাঠিয়েছেন তা লিখুন\n\n"
            f"<i>নিচে পরিমাণ লিখুন (যেমন: <code>500</code>):</i>"
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
            f"{ICON_WARNING} সঠিক USDT পরিমাণ লিখুন (যেমন: <code>10</code> বা <code>25.5</code>):",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=True),
        )
        return

    if amount_num < min_coin:
        await message.answer(
            f"{ICON_WARNING} সর্বনিম্ন ডিপোজিট <b>{min_coin:g} USDT</b> (~{price(symbol, min_dep)})।\n"
            f"অন্তত <b>{min_coin:g} USDT</b> লিখুন:",
            reply_markup=get_deposit_amount_keyboard(account_info, method_id, is_binance=True),
        )
        return

    await state.update_data(binance_usdt=amount_num)
    await state.set_state(DepositStates.waiting_for_binance_ref)

    bdt_approx = round(amount_num * rate, 2)
    await message.answer(
        f"{ICON_NOTE} <b>পেমেন্ট রেফারেন্স</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"↳ <b>পরিমাণ:</b> <b>{amount_num:g} USDT</b> (~{price(symbol, bdt_approx)})\n"
        f"↳ <b>Binance UID:</b> <code>{escape(account_info)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"আপনার <b>Binance Pay Order ID</b> অথবা আপনার <b>Binance UID</b> দিন\n\n"
        f"↳ <b>Order ID:</b> <code>454711565717520384</code> (Pay রিসিট থেকে)\n"
        f"↳ <b>অথবা Sender UID:</b> <code>580150694</code> (আপনার Binance UID)",
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
            f"{ICON_CROSS} ভুল রেফারেন্স ফরম্যাট। সঠিক Binance Pay Order ID অথবা Sender Binance UID দিন:\n\n"
            f"<i>যেমন: <code>454711565717520384</code> অথবা <code>580150694</code></i>",
            reply_markup=get_deposit_txid_keyboard(),
        )
        return

    data = await state.get_data()
    method_id = data.get("method_id")
    expected_usdt = data.get("binance_usdt")

    if not method_id:
        await state.clear()
        await message.answer(f"{ICON_TIMER} সেশন মেয়াদোত্তীর্ণ। আবার ডিপোজিট করতে Deposit এ ট্যাপ করুন।")
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
        f"{ICON_TIMER} <b>Binance পেমেন্ট যাচাই করা হচ্ছে...</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"↳ <b>রেফারেন্স:</b> <code>{escape(ref)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>Binance Pay রেকর্ড চেক করা হচ্ছে, অপেক্ষা করুন...</i>"
    )
    try:
        result = await services.binance.claim(message.from_user.id, method_id, ref, expected_usdt=expected_usdt)
    except DuplicateTransactionError:
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_CROSS} <b>পেমেন্ট ইতোমধ্যে প্রসেস হয়েছে</b>\n\n"
            f"এই রেফারেন্স (<code>{escape(ref)}</code>) আগেই জমা দেওয়া হয়েছে।\n"
            f"সাহায্য প্রয়োজন হলে সাপোর্টে যোগাযোগ করুন।",
            reply_markup=get_deposit_txid_keyboard(),
        )
        return
    except PendingDepositError:
        await state.clear()
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_TIMER} <b>পেন্ডিং ডিপোজিট আছে</b>\n\n"
            f"আপনার একটি ডিপোজিট রিকোয়েস্ট রিভিউ এর জন্য অপেক্ষায় আছে।\n"
            f"নতুন রিকোয়েস্ট পাঠানোর আগে সেটি কনফার্ম হওয়া পর্যন্ত অপেক্ষা করুন।",
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
            f"{ICON_CHECK} <b>Binance ডিপোজিট সফল!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_BINANCE} <b>পেয়েছি:</b> <code>{received_coin:g} {escape(coin)}</code>\n"
            f"{ICON_MONEY} <b>জমা হয়েছে:</b> <code>{price(symbol, credited_amount)}</code>\n"
            f"{ICON_BALANCE} <b>ব্যালেন্স:</b> <code>{price(symbol, user_balance)}</code>\n"
            f"{ICON_KEY} <b>রেফারেন্স:</b> <code>{escape(ref)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>আপনার ওয়ালেটে স্বয়ংক্রিয়ভাবে টাকা যোগ হয়েছে। ধন্যবাদ!</i>",
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
        expected_text = f"↳ <b>প্রত্যাশিত:</b> <code>{expected_usdt:g} USDT</code>\n" if expected_usdt else ""
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_TIMER} <b>পেমেন্ট যাচাই চলছে...</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"↳ <b>রেফারেন্স:</b> <code>{escape(ref)}</code>\n"
            f"{expected_text}"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Binance থেকে আপনার ট্রান্সফার খোঁজা হচ্ছে। সদ্য পাঠালে ১-২ মিনিট অপেক্ষা করুন।\n\n"
            f"<i>সিস্টেম ব্যাকগ্রাউন্ডে চেক করছে। কনফার্ম হলে স্বয়ংক্রিয়ভাবে ব্যালেন্স যোগ হবে!</i>",
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

    await state.update_data(manual_amount=amount_num)
    await state.set_state(DepositStates.waiting_for_txid)

    method_name = data.get("method_name", "Payment")
    await message.answer(
        f"{ICON_KEY} <b>ট্রানজ্যাকশন আইডি (TrxID)</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"↳ <b>পরিমাণ:</b> <b>{price(symbol, amount_num)}</b>\n"
        f"↳ <b>অ্যাকাউন্ট:</b> <code>{escape(account_info)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"আপনার {escape(method_name)} SMS / রিসিট থেকে <b>Transaction ID (TrxID)</b> দিন\n\n"
        f"<i>(যেমন: <code>BLA7X8Y9Z0</code>)</i>",
        reply_markup=get_deposit_txid_keyboard(),
    )


@router.message(DepositStates.waiting_for_txid)
async def process_deposit_txid(message: Message, state: FSMContext, services: Services):
    raw_text = (message.text or "").strip()
    if is_navigation(raw_text):
        await navigate(raw_text, message, state, services)
        return

    clean_tx = re.sub(r"^(trxid|trx\s*id|txid|ref)[\s:#=]*", "", raw_text, flags=re.IGNORECASE).strip()
    clean_tx = clean_tx.strip("<>#[](){}\"':; \t\r\n")

    if not TRANSACTION_ID_REGEX.fullmatch(clean_tx):
        await message.answer(
            f"{ICON_CROSS} ভুল Transaction ID ফরম্যাট। আপনার SMS/রিসিট থেকে সঠিক TrxID দিন।",
            reply_markup=get_deposit_txid_keyboard(),
        )
        return

    data = await state.get_data()
    method_id = data.get("method_id")
    amount_num = data.get("manual_amount")

    if not method_id or not amount_num:
        await state.clear()
        await message.answer(f"{ICON_TIMER} সেশন মেয়াদোত্তীর্ণ। আবার ডিপোজিট করতে Deposit এ ট্যাপ করুন।")
        return

    symbol = await services.settings.get("currency_symbol")
    method_name = data.get("method_name", "Payment")

    status_msg = await message.answer(
        f"{ICON_TIMER} <b>ট্রানজ্যাকশন যাচাই করা হচ্ছে...</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"↳ <b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
        f"↳ <b>পরিমাণ:</b> <code>{price(symbol, amount_num)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>পেমেন্ট গেটওয়ে থেকে যাচাই করা হচ্ছে, একটু অপেক্ষা করুন...</i>"
    )

    # If ZiniPay auto-verify is configured, attempt automated verification
    if await services.zinipay.is_enabled():
        try:
            res = await services.zinipay.claim(
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
                f"{ICON_CROSS} <b>পেমেন্ট ইতোমধ্যে প্রসেস হয়েছে</b>\n\n"
                f"এই Transaction ID (<code>{escape(clean_tx)}</code>) আগেই জমা দেওয়া হয়েছে।",
                reply_markup=get_deposit_txid_keyboard(),
            )
            return
        except PendingDepositError:
            await state.clear()
            await _safe_edit_or_answer(
                status_msg,
                message,
                f"{ICON_TIMER} <b>পেন্ডিং ডিপোজিট আছে</b>\n\n"
                f"আপনার একটি ডিপোজিট রিকোয়েস্ট রিভিউ এর জন্য অপেক্ষায় আছে।\n"
                f"নতুন রিকোয়েস্ট পাঠানোর আগে সেটি কনফার্ম হওয়া পর্যন্ত অপেক্ষা করুন।",
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

        if res.get("auto_verified") and res.get("credited"):
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
            await _safe_edit_or_answer(
                status_msg,
                message,
                f"{ICON_CHECK} <b>ডিপোজিট সফল!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ICON_DEPOSIT} <b>মেথড:</b> {escape(provider)}\n"
                f"{ICON_MONEY} <b>জমা হয়েছে:</b> <code>{price(symbol, amount_num)}</code>\n"
                f"{ICON_BALANCE} <b>ব্যালেন্স:</b> <code>{price(symbol, user_balance)}</code>\n"
                f"{ICON_KEY} <b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<i>আপনার ওয়ালেটে স্বয়ংক্রিয়ভাবে টাকা যোগ হয়েছে। ধন্যবাদ!</i>",
                reply_markup=keyboard,
            )
            return

        if res.get("error"):
            await _safe_edit_or_answer(
                status_msg,
                message,
                f"{ICON_CROSS} <b>যাচাই ব্যর্থ</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{escape(res.get('detail', ''))}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"আপনার TrxID চেক করে আবার দিন, অথবা ভুল পরিমাণ দিলে <b>Change Amount</b> এ ক্লিক করুন:",
                reply_markup=get_deposit_txid_keyboard(),
            )
            return

        if res.get("fallback_manual"):
            await state.clear()
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER),
                        InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
                    ]
                ]
            )
            await _safe_edit_or_answer(
                status_msg,
                message,
                f"{ICON_CHECK} <b>ডিপোজিট রিকোয়েস্ট জমা হয়েছে!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ICON_DEPOSIT} <b>মেথড:</b> {escape(method_name)}\n"
                f"{ICON_MONEY} <b>পরিমাণ:</b> <code>{price(symbol, amount_num)}</code>\n"
                f"{ICON_KEY} <b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"<i>আপনার পেমেন্ট রিকোয়েস্ট অ্যাডমিন রিভিউ এর জন্য জমা হয়েছে। যাচাই হলে ব্যালেন্স যোগ হবে।</i>",
                reply_markup=keyboard,
            )
            return

    # Standard fallback when ZiniPay verification is not enabled
    try:
        await services.deposits.create_request(
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
            f"{ICON_CROSS} এই Transaction ID আগেই জমা দেওয়া হয়েছে! আপনার রিসিট চেক করুন।",
            reply_markup=get_deposit_txid_keyboard(),
        )
        return
    except PendingDepositError:
        await state.clear()
        await _safe_edit_or_answer(
            status_msg,
            message,
            f"{ICON_TIMER} <b>পেন্ডিং ডিপোজিট আছে</b>\n\n"
            f"আপনার একটি ডিপোজিট রিকোয়েস্ট রিভিউ এর জন্য অপেক্ষায় আছে।\n"
            f"নতুন রিকোয়েস্ট পাঠানোর আগে সেটি কনফার্ম হওয়া পর্যন্ত অপেক্ষা করুন।",
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
        await _safe_edit_or_answer(status_msg, message, f"{ICON_CROSS} <b>ডিপোজিট ব্যর্থ:</b> {escape(str(exc))}")
        return

    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Deposit History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER),
                InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
            ]
        ]
    )

    await _safe_edit_or_answer(
        status_msg,
        message,
        f"{ICON_CHECK} <b>ডিপোজিট রিকোয়েস্ট জমা হয়েছে!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_DEPOSIT} <b>মেথড:</b> {escape(method_name)}\n"
        f"{ICON_MONEY} <b>পরিমাণ:</b> <code>{price(symbol, amount_num)}</code>\n"
        f"{ICON_KEY} <b>TrxID:</b> <code>{escape(clean_tx)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>অ্যাডমিন যাচাই করলে আপনার ওয়ালেটে ব্যালেন্স যোগ হবে।</i>",
        reply_markup=keyboard,
    )

