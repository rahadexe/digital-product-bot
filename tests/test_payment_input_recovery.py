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
    claim_binance_payment,
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
        settings=SimpleNamespace(number=AsyncMock(return_value=100000)),
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


def test_admin_payment_instructions_are_displayed_without_rewriting():
    notes = (
        "Send Money only. Do not use Cash Out.\n"
        "Enter the amount below.\n"
        "আপনি কত টাকা পাঠিয়েছেন তা নিচে লিখুন\n"
        "Contact support if your receipt is missing."
    )
    assert payment_instruction_note(notes) == notes
    bangla_instruction = "বিকাশে টাকা পাঠিয়ে TrxID-টি এখানে লিখুন।"
    assert payment_instruction_note(bangla_instruction) == bangla_instruction


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
@pytest.mark.parametrize("raw,expected", [("৳50", "0.4"), ("৫০ টাকা", "0.4"), ("1,000.50", "8.004")])
async def test_hosted_checkout_uses_the_same_safe_bdt_parser(raw, expected):
    state = context()
    incoming = message(raw)
    svc = services()
    svc.settings.number = AsyncMock(return_value=125.0)
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
async def test_payment_details_preserve_admin_custom_instructions_verbatim():
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
    assert old_instruction in text
    assert "Send Money only." in text
    assert old_instruction in method["instructions"]
    assert await state.get_state() == DepositStates.method_selected.state


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["৳49", "৪৯ টাকা", "৳12,500,001"])
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
async def test_bdt_maximum_uses_converted_usd_wallet_credit():
    state = await waiting_state()
    svc = services()
    svc.settings.number.return_value = 8
    with patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit:
        await process_deposit_amount(message("৳1001"), state, svc)
    submit.assert_not_awaited()
    assert (await state.get_data()).get("pay_amount") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["not_found", "already_used"])
async def test_binance_reference_retry_keeps_the_valid_amount(error):
    state = await waiting_state()
    await state.update_data(
        is_binance=True, method_name="Binance", manual_amount=2, pay_amount=2,
        binance_usdt=2, min_deposit=0.2,
    )
    incoming = message("2")
    svc = services()
    svc.binance = SimpleNamespace(claim=AsyncMock(return_value={"error": error}))
    status = SimpleNamespace(edit_text=AsyncMock())
    await claim_binance_payment(incoming, state, svc, 3, "OLD-ORDER-1", expected_usdt=2, status_msg=status)
    assert await state.get_state() == DepositStates.waiting_for_binance_ref.state
    assert (await state.get_data())["pay_amount"] == 2
    assert (await state.get_data())["manual_txid"] is None
    assert isinstance(incoming.answer.await_args.kwargs["reply_markup"], ForceReply)
    incoming.text = "NEW-ORDER-1"
    with patch("app.bot.handlers.deposit.execute_deposit_submission", new_callable=AsyncMock) as submit:
        await process_deposit_txid(incoming, state, svc)
    submit.assert_awaited_once_with(incoming, state, svc)
    assert (await state.get_data())["manual_txid"] == "NEW-ORDER-1"


@pytest.mark.asyncio
async def test_binance_method_uses_usdt_minimum_without_legacy_rate_conversion():
    state = context()
    incoming = message("Binance Chain")
    svc = services()
    svc.deposits = SimpleNamespace(pending_for=AsyncMock(return_value=None))
    svc.settings.get = AsyncMock(return_value="৳")
    svc.settings.number.return_value = 125
    await render_method_details(incoming, state, svc, {
        "id": 3, "name": "Binance Chain", "account_info": "chain-test-address",
        "min_deposit": 25, "rate_to_currency": 0.008, "auto_verify": "binance",
        "account_type": "crypto",
    })
    assert (await state.get_data())["min_deposit"] == pytest.approx(25.0)
    assert "Minimum: <b>25 USDT</b>" in incoming.answer.await_args.args[0]


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
