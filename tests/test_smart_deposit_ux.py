"""Tests for Smart Frictionless Deposit UX:
1. Auto SMS Receipt Parsing (TrxID + Amount extracted together)
2. Reference-First Quick Amount Selection without redundant TrxID loops
3. Amount-First currency parsing without format errors
4. Single-card in-place transitions
5. Late Inbound SMS Auto-Reconciliation in DepositService
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from aiogram.types import CallbackQuery, Chat, Message, User

from app.bot.handlers.deposit import (
    DepositStates,
    begin_payment_reference,
    handle_deposit_quick_amount,
    process_deposit_amount,
    process_deposit_txid,
)
from app.services.sms_parser import parse_mfs_sms


def test_sms_parser_patterns():
    # bKash incoming
    res1 = parse_mfs_sms("You have received Tk 500.00 from 01712345678. Fee Tk 0.00. Balance Tk 1500. TrxID 9ABC123456 at 30/10/2026")
    assert res1 is not None
    assert res1["transaction_id"] == "9ABC123456"
    assert res1["amount"] == 500.0

    # bKash customer outgoing (Send Money)
    res2 = parse_mfs_sms("Send Money Tk 500.00 to 01712345678 successful. Fee Tk 5.00. Balance Tk 1000. TrxID 9DEF123456 at 30/10/2026")
    assert res2 is not None
    assert res2["transaction_id"] == "9DEF123456"
    assert res2["amount"] == 500.0

    # bKash customer outgoing with ৳ symbol
    res3 = parse_mfs_sms("Send Money ৳ 750.00 to 01712345678 successful. TrxID 9GHI123456")
    assert res3 is not None
    assert res3["transaction_id"] == "9GHI123456"
    assert res3["amount"] == 750.0

    # Nagad
    res4 = parse_mfs_sms("Money Received. Amount: Tk 300.00. Sender: 01712345678. TxnID: 7XYZ987654. Balance: Tk 1200", sender_hint="Nagad")
    assert res4 is not None
    assert res4["transaction_id"] == "7XYZ987654"
    assert res4["amount"] == 300.0

    # Rocket
    res5 = parse_mfs_sms("Tk 200.00 received from 01712345678. TxnId: 1234567890. Balance Tk 500", sender_hint="Rocket")
    assert res5 is not None
    assert res5["transaction_id"] == "1234567890"
    assert res5["amount"] == 200.0


@pytest.mark.asyncio
async def test_pasted_sms_auto_extracts_both_and_submits():
    """When a customer pastes a full bKash SMS, both TrxID and Amount are captured and submitted directly."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)
    await state.set_state(DepositStates.waiting_for_txid)
    await state.set_data({
        "method_id": 1,
        "method_name": "bKash",
        "account_info": "01700000000",
        "account_type": "personal",
        "min_deposit": 50.0,
        "rate": 125.0,
        "reference_first": True,
        "card_msg_id": 555,
        "card_chat_id": 456,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.deposits.verification_failures = AsyncMock(return_value=[])
    services.deposits.find_by_transaction = AsyncMock(return_value=None)
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.deposits.get_unused_received_transaction = AsyncMock(return_value=None)
    services.deposits.create_request = AsyncMock(return_value=101)
    services.deposits.get_method = AsyncMock(return_value={"id": 1, "auto_verify": "none"})
    services.zinipay.is_enabled = AsyncMock(return_value=False)
    services.settings.number = AsyncMock(return_value=125.0)
    services.settings.get = AsyncMock(return_value="৳")

    bot = MagicMock()
    card_mock = MagicMock(spec=Message, message_id=555)
    card_mock.edit_text = AsyncMock()
    bot.edit_message_text = AsyncMock(return_value=card_mock)

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.bot = bot
    message.text = "You have received Tk 500.00 from 01712345678. Fee Tk 0.00. Balance Tk 1500. TrxID 9ABC123456 at 30/10/2026"
    message.answer = AsyncMock()
    message.delete = AsyncMock()

    await process_deposit_txid(message, state, services)

    # Submission was executed directly without asking for amount!
    assert services.deposits.create_request.called
    kwargs = services.deposits.create_request.call_args.kwargs
    assert kwargs["transaction_id"] == "9ABC123456"
    assert kwargs["pay_amount"] == 500.0
    assert kwargs["amount"] == 4.0  # 500 / 125
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_reference_first_quick_amount_chip_submits_without_looping():
    """In Reference-First flow, tapping a quick amount chip submits directly instead of asking for TrxID again."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)
    await state.set_state(DepositStates.waiting_for_amount)
    await state.set_data({
        "method_id": 1,
        "method_name": "bKash",
        "account_info": "01700000000",
        "account_type": "personal",
        "min_deposit": 50.0,
        "rate": 125.0,
        "manual_txid": "9ABC123456",
        "reference_first": True,
        "card_msg_id": 555,
        "card_chat_id": 456,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.deposits.verification_failures = AsyncMock(return_value=[])
    services.deposits.find_by_transaction = AsyncMock(return_value=None)
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.deposits.get_unused_received_transaction = AsyncMock(return_value=None)
    services.deposits.create_request = AsyncMock(return_value=102)
    services.deposits.get_method = AsyncMock(return_value={"id": 1, "auto_verify": "none"})
    services.zinipay.is_enabled = AsyncMock(return_value=False)
    services.settings.number = AsyncMock(return_value=125.0)
    services.settings.get = AsyncMock(return_value="৳")

    bot = MagicMock()
    card_mock = MagicMock(spec=Message, message_id=555)
    card_mock.edit_text = AsyncMock()
    bot.edit_message_text = AsyncMock(return_value=card_mock)

    user = User(id=789, is_bot=False, first_name="Test")
    query = MagicMock(spec=CallbackQuery)
    query.from_user = user
    query.data = "dep_amt_500"
    query.answer = AsyncMock()
    query.message = card_mock
    query.bot = bot

    await handle_deposit_quick_amount(query, state, services)

    # Assert: create_request was called directly with the existing TrxID!
    assert services.deposits.create_request.called
    kwargs = services.deposits.create_request.call_args.kwargs
    assert kwargs["transaction_id"] == "9ABC123456"
    assert kwargs["pay_amount"] == 500.0
    assert kwargs["amount"] == 4.0
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_user_types_amount_with_currency_symbol_captured_smoothly():
    """If user types '500tk' or '৳500' when prompted for TrxID, it captures amount first without erroring."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)
    await state.set_state(DepositStates.waiting_for_txid)
    await state.set_data({
        "method_id": 1,
        "method_name": "bKash",
        "account_info": "01700000000",
        "account_type": "personal",
        "min_deposit": 50.0,
        "rate": 125.0,
        "reference_first": True,
        "card_msg_id": 555,
        "card_chat_id": 456,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.settings.number = AsyncMock(return_value=125.0)
    services.settings.get = AsyncMock(return_value="৳")

    bot = MagicMock()
    bot.edit_message_text = AsyncMock()

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.bot = bot
    message.text = "500tk"
    message.answer = AsyncMock()
    message.delete = AsyncMock()

    await process_deposit_txid(message, state, services)

    # State still at waiting_for_txid, but pay_amount has been recorded!
    data = await state.get_data()
    assert data["pay_amount"] == 500.0
    assert data["manual_amount"] == 4.0

    # Card updated to ask for TrxID with amount confirmed
    assert bot.edit_message_text.called
    card_text = bot.edit_message_text.call_args.kwargs["text"]
    assert "Send Money করুন: <b>500 ৳</b>" in card_text
    assert "Enter TrxID below:" in card_text


@pytest.mark.asyncio
async def test_late_sms_auto_reconciliation_approves_pending_deposit():
    """When an incoming SMS arrives for a pending deposit, DepositService automatically matches and approves it."""
    from app.services.deposits import DepositService
    from unittest.mock import AsyncMock, patch

    mock_db = MagicMock()
    mock_settings = MagicMock()
    mock_notifier = MagicMock()

    service = DepositService(mock_db, mock_settings, mock_notifier)
    service.claim_received_transaction = AsyncMock(return_value=True)
    service.approve = AsyncMock(return_value=(True, "", None))

    # Mock DB insert and pending deposit lookup
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=[
        # 1. INSERT INTO received_transactions RETURNING *
        {"id": 1, "transaction_id": "9ABC123456", "amount": 500.0, "status": "unused"},
        # 2. SELECT id, tg_user_id, amount, pay_amount FROM deposits WHERE ...
        {"id": 88, "tg_user_id": 789, "amount": 4.0, "pay_amount": 500.0},
    ])
    mock_db.connect.return_value.__aenter__.return_value = conn

    res = await service.record_received_transaction(
        transaction_id="9ABC123456",
        amount=500.0,
        provider="bKash",
        sender_number="01712345678",
        raw_message="You have received Tk 500.00 ... TrxID 9ABC123456",
    )

    assert res is not None
    assert res["transaction_id"] == "9ABC123456"

    # Assert auto-reconciliation claimed and approved deposit #88!
    service.claim_received_transaction.assert_called_once_with("9ABC123456", 789, 88, provider="bKash")
    service.approve.assert_called_once_with(
        88,
        admin_note="Auto-verified via delayed SMS statement match.",
        notify_customer=True,
    )


@pytest.mark.asyncio
async def test_payment_done_presets_to_trxid_flow():
    """End-to-end: Payment Done -> Preset ৳500 -> Enter TrxID -> Direct Submission."""
    from app.bot.handlers.deposit import handle_deposit_change_amount

    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)
    await state.set_state(DepositStates.method_selected)
    await state.set_data({
        "method_id": 1,
        "method_name": "bKash",
        "account_info": "01700000000",
        "account_type": "personal",
        "min_deposit": 50.0,
        "rate": 125.0,
        "card_msg_id": 555,
        "card_chat_id": 456,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.deposits.get_method = AsyncMock(return_value={"id": 1, "is_active": True, "name": "bKash", "account_info": "01700000000"})
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.deposits.find_by_transaction = AsyncMock(return_value=None)
    services.deposits.get_unused_received_transaction = AsyncMock(return_value=None)
    services.deposits.verification_failures = AsyncMock(return_value=[])
    services.deposits.create_request = AsyncMock(return_value=105)
    services.zinipay.is_enabled = AsyncMock(return_value=False)
    services.settings.number = AsyncMock(return_value=125.0)
    services.settings.get = AsyncMock(return_value="৳")

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    card_msg = MagicMock(spec=Message, message_id=555)
    card_msg.chat = chat
    card_msg.edit_text = AsyncMock()

    # Step 1: User taps "Payment Done"
    query_paid = MagicMock(spec=CallbackQuery)
    query_paid.from_user = user
    query_paid.data = "dep_paid_1"
    query_paid.message = card_msg
    query_paid.answer = AsyncMock()

    await begin_payment_reference(query_paid, state, services)

    # Asserts for Step 1:
    assert await state.get_state() == DepositStates.waiting_for_amount.state
    assert card_msg.edit_text.called
    step1_text = card_msg.edit_text.call_args[0][0]
    assert "How much balance do you want to add?" in step1_text
    step1_kb = card_msg.edit_text.call_args[1]["reply_markup"]
    step1_chips = [b.text for r in step1_kb.inline_keyboard for b in r]
    assert "৳50" in step1_chips
    assert "৳500" in step1_chips

    # Step 2: User taps preset [ ৳500 ]
    card_msg.edit_text.reset_mock()
    query_chip = MagicMock(spec=CallbackQuery)
    query_chip.from_user = user
    query_chip.data = "dep_amt_500"
    query_chip.message = card_msg
    query_chip.answer = AsyncMock()

    await handle_deposit_quick_amount(query_chip, state, services)

    # Asserts for Step 2:
    assert await state.get_state() == DepositStates.waiting_for_txid.state
    data = await state.get_data()
    assert data["pay_amount"] == 500.0
    assert data["manual_amount"] == 4.0
    assert card_msg.edit_text.called
    step2_text = card_msg.edit_text.call_args[0][0]
    assert "Send Money করুন: <b>500 ৳</b>" in step2_text
    assert "Enter TrxID below:" in step2_text

    # Step 3: User submits TrxID
    bot = MagicMock()
    bot.edit_message_text = AsyncMock(return_value=card_msg)
    trx_message = MagicMock(spec=Message)
    trx_message.from_user = user
    trx_message.chat = chat
    trx_message.bot = bot
    trx_message.text = "BLA7X8Y9Z0"
    trx_message.answer = AsyncMock()
    trx_message.delete = AsyncMock()

    await process_deposit_txid(trx_message, state, services)

    # Asserts for Step 3:
    assert services.deposits.create_request.called
    kwargs = services.deposits.create_request.call_args.kwargs
    assert kwargs["transaction_id"] == "BLA7X8Y9Z0"
    assert kwargs["pay_amount"] == 500.0
    assert kwargs["amount"] == 4.0
    assert await state.get_state() is None
