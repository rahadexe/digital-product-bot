"""Payment entry accepts normal money formatting without guessing at invalid text."""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ForceReply

from app.bot.deposit_input import parse_deposit_amount, payment_instruction_note
from app.bot.handlers.deposit import (
    DepositStates,
    create_instant_payment,
    process_deposit_amount,
    process_deposit_txid,
    render_method_details,
)


def context():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=2))


def message(text):
    return SimpleNamespace(
        text=text, message_id=45, from_user=SimpleNamespace(id=2),
        chat=SimpleNamespace(id=2, type="private"),
        answer=AsyncMock(return_value=SimpleNamespace(message_id=200)),
        delete=AsyncMock(), bot=SimpleNamespace(delete_message=AsyncMock()),
    )


def services():
    return SimpleNamespace(
        users=SimpleNamespace(get_language=AsyncMock(return_value="en")),
        settings=SimpleNamespace(number=AsyncMock(return_value=1000)),
    )


async def waiting_state(*, reference_first=True):
    state = context()
    await state.set_state(DepositStates.waiting_for_amount)
    await state.set_data({
        "method_id": 3, "method_name": "Rocket", "reference_first": reference_first,
        "manual_txid": "ROCKET12345" if reference_first else None,
        "min_deposit": 50, "rate": 125, "card_msg_id": 90, "amount_prompt_id": 60,
    })
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [
    ("50", 50), ("৫০", 50), ("৳50", 50), ("50 tk", 50), ("৫০ টাকা", 50),
    ("BDT 50.50", 50.5), ("1,000", 1000), ("১,০০০.৫০ টাকা", 1000.5),
    ("\u200e৳ ৫০.০০\u200f", 50),
])
async def test_formatted_bdt_amount_submits_the_existing_reference(raw, expected):
    state = await waiting_state()
    incoming = message(raw)
    svc = services()
    with patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit:
        await process_deposit_amount(incoming, state, svc)
    submit.assert_awaited_once_with(incoming, state, svc)
    data = await state.get_data()
    assert data["pay_amount"] == expected
    assert data["manual_txid"] == "ROCKET12345"


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["-500", "500-1", "BK100000", "100 200", "100,00", "$500"])
async def test_legacy_amount_entry_never_strips_invalid_text_into_money(raw):
    state = await waiting_state(reference_first=False)
    incoming = message(raw)
    await process_deposit_amount(incoming, state, services())
    data = await state.get_data()
    assert data.get("pay_amount") is None
    assert await state.get_state() == DepositStates.waiting_for_amount.state


@pytest.mark.asyncio
async def test_invalid_amount_stays_visible_and_replaces_the_previous_prompt():
    state = await waiting_state()
    incoming = message("not an amount")
    await process_deposit_amount(incoming, state, services())
    await asyncio.sleep(0)
    incoming.delete.assert_not_awaited()
    prompt = incoming.answer.await_args.args[0]
    assert "50" in prompt
    assert isinstance(incoming.answer.await_args.kwargs["reply_markup"], ForceReply)
    incoming.bot.delete_message.assert_awaited_once_with(chat_id=2, message_id=60)
    assert (await state.get_data())["amount_prompt_id"] == 200


@pytest.mark.parametrize("raw,expected", [
    ("50", "50"), ("৫০.৫০", "50.50"), ("৳50", "50"), ("50tk", "50"),
    ("Tk. 50", "50"), ("BDT 50.50", "50.50"), ("50 টাকা", "50"),
    ("1,000", "1000"), ("1,00,000.50", "100000.50"), ("10,00,000", "1000000"),
    ("১,০০০.৫০ টাকা", "1000.50"), ("৫০\u00a0টাকা", "50"),
    ("\u200e৳৫০\u200f", "50"), ("৫০\u200b.৫০", "50.50"),
    ("５０.５０", "50.50"), ("١٬٠٠٠٫٥٠", "1000.50"),
])
def test_parser_supports_money_notation_and_mobile_keyboards(raw, expected):
    assert parse_deposit_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [
    "", " ", "-500", "+500", "500-1", "BK100000", "50 paid", "100 200",
    "100,00", "1,23,45", "1000,000", "50.123", "50..0", "5e2",
    "NaN", "Infinity", "0", "০", "9" * 400, "$500", "50 USD", "50 USDT",
    "৳500 USDT", "https://example.com/pay?amount=500",
])
def test_parser_rejects_ambiguous_or_wrong_currency_inputs(raw):
    with pytest.raises(ValueError):
        parse_deposit_amount(raw)


@pytest.mark.parametrize("raw", ["2", "$2", "2 USDT", "USD 2.00", "২.০০ USDT"])
def test_crypto_amounts_accept_only_their_own_currency_labels(raw):
    assert parse_deposit_amount(raw, is_binance=True) == Decimal("2")


@pytest.mark.parametrize("raw", ["৳2", "2 টাকা", "BDT 2", "2 tk", "NaN", "-2"])
def test_crypto_amounts_do_not_silently_convert_bdt_or_invalid_values(raw):
    with pytest.raises(ValueError):
        parse_deposit_amount(raw, is_binance=True)


def test_old_amount_entry_note_is_hidden_without_changing_other_payment_notes():
    notes = (
        "Send Money only. Do not use Cash Out.\n"
        "Enter the amount below.\n"
        "আপনি কত টাকা পাঠিয়েছেন তা নিচে লিখুন\n"
        "Contact support if your receipt is missing."
    )
    assert payment_instruction_note(notes) == (
        "Send Money only. Do not use Cash Out.\n"
        "Contact support if your receipt is missing."
    )
    assert payment_instruction_note("Enter the amount in your Rocket app.") == (
        "Enter the amount in your Rocket app."
    )


@pytest.mark.asyncio
async def test_retries_replace_only_amount_prompts_and_keep_reference_and_instructions():
    state = await waiting_state()
    incoming = message("bad input")
    for next_id in (200, 201):
        incoming.answer.return_value = SimpleNamespace(message_id=next_id)
        await process_deposit_amount(incoming, state, services())
    deleted = [call.kwargs["message_id"] for call in incoming.bot.delete_message.await_args_list]
    assert deleted == [60, 200]
    assert 90 not in deleted
    data = await state.get_data()
    assert data["manual_txid"] == "ROCKET12345"
    assert data["amount_prompt_id"] == 201
    assert await state.get_state() == DepositStates.waiting_for_amount.state


@pytest.mark.asyncio
async def test_invalid_reference_is_not_deleted_and_uses_its_own_prompt():
    state = await waiting_state()
    await state.set_state(DepositStates.waiting_for_txid)
    await state.update_data(manual_txid=None, reference_prompt_id=55)
    incoming = message("bad")
    await process_deposit_txid(incoming, state, services())
    await asyncio.sleep(0)
    incoming.delete.assert_not_awaited()
    incoming.bot.delete_message.assert_awaited_once_with(chat_id=2, message_id=55)
    assert await state.get_state() == DepositStates.waiting_for_txid.state
    assert (await state.get_data())["manual_txid"] is None


@pytest.mark.asyncio
async def test_error_recovery_never_deletes_the_payment_details_card():
    state = await waiting_state()
    await state.update_data(amount_prompt_id=90)
    incoming = message("bad input")
    await process_deposit_amount(incoming, state, services())
    incoming.bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw,expected", [("৳50", "50"), ("৫০ টাকা", "50"), ("1,000.50", "1000.50")])
async def test_hosted_checkout_uses_the_same_safe_bdt_parser(raw, expected):
    state = context()
    incoming = message(raw)
    svc = services()
    svc.payments = SimpleNamespace(create_invoice=AsyncMock(return_value={}))
    with patch("app.bot.handlers.deposit._render_instant_invoice", new_callable=AsyncMock) as render:
        render.return_value = ("Pay using checkout.", None)
        await create_instant_payment(incoming, state, svc)
    svc.payments.create_invoice.assert_awaited_once_with(2, expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["$500", "BK100000", "-500"])
async def test_hosted_checkout_does_not_treat_other_currency_or_reference_as_bdt(raw):
    state = context()
    incoming = message(raw)
    svc = services()
    svc.payments = SimpleNamespace(create_invoice=AsyncMock())
    await create_instant_payment(incoming, state, svc)
    svc.payments.create_invoice.assert_not_awaited()


@pytest.mark.asyncio
async def test_payment_details_hide_old_amount_directions_but_preserve_merchant_warnings():
    state = context()
    incoming = message("Rocket")
    svc = services()
    svc.settings.get = AsyncMock(return_value="৳")
    svc.deposits = SimpleNamespace(pending_for=AsyncMock(return_value=None))
    old_instruction = "আপনি কত টাকা পাঠিয়েছেন তা নিচে লিখুন"
    method = {
        "id": 3, "name": "Rocket", "account_info": "01700000000",
        "min_deposit": 50, "instructions": f"Send Money only.\n{old_instruction}",
    }
    await render_method_details(incoming, state, svc, method)
    text = incoming.answer.await_args.args[0]
    assert old_instruction not in text
    assert "Send Money only." in text
    assert "After paying, tap Payment Done." in text
    assert old_instruction in method["instructions"]
    assert await state.get_state() == DepositStates.method_selected.state


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["৳49", "৪৯ টাকা", "৳125,001"])
async def test_formatted_amounts_still_obey_minimum_and_maximum_limits(raw):
    state = await waiting_state()
    incoming = message(raw)
    with patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit:
        await process_deposit_amount(incoming, state, services())
    submit.assert_not_awaited()
    assert await state.get_state() == DepositStates.waiting_for_amount.state
    assert (await state.get_data())["manual_txid"] == "ROCKET12345"
    assert (await state.get_data()).get("pay_amount") is None


@pytest.mark.asyncio
async def test_amount_prompt_example_respects_the_selected_method_minimum():
    state = await waiting_state()
    await state.set_state(DepositStates.waiting_for_txid)
    await state.update_data(manual_txid=None, min_deposit=1000)
    incoming = message("ROCKET12345")
    await process_deposit_txid(incoming, state, services())
    assert "e.g. 1000" in incoming.answer.await_args.args[0]
    incoming.text = "not an amount"
    await process_deposit_amount(incoming, state, services())
    assert "e.g. 1000" in incoming.answer.await_args.args[0]
