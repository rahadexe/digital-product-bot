import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, Chat, User, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey

from app.bot.handlers.deposit import (
    render_method_details,
    process_deposit_amount,
    process_deposit_txid,
    DepositStates,
    show_deposit_methods,
)
from app.bot.keyboards import get_deposit_amount_keyboard, get_back_reply_keyboard


@pytest.mark.asyncio
async def test_wallet_shows_balance_and_inline_payment_actions():
    services = MagicMock()
    services.settings.paused_message = AsyncMock(return_value=None)
    services.settings.get = AsyncMock(return_value="৳")
    services.settings.number = AsyncMock(return_value=125.0)
    services.settings.flag = AsyncMock(return_value=False)
    services.payments.instant_options = AsyncMock(return_value=None)
    services.deposits.methods = AsyncMock(return_value=[
        {"id": 1, "name": "bKash"},
        {"id": 2, "name": "Nagad"},
        {"id": 3, "name": "Rocket"},
        {"id": 4, "name": "Binance"},
    ])
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.users.get = AsyncMock(return_value={"language": "en", "balance": 45.0})
    services.users.get_language = AsyncMock(return_value="en")

    state = MagicMock()
    state.clear = AsyncMock()
    user = User(id=789, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.text = "Add Balance"
    message.answer = AsyncMock()

    await show_deposit_methods(message, state, services)

    text = message.answer.call_args.args[0]
    keyboard = message.answer.call_args.kwargs["reply_markup"]
    assert "<b>Balance:</b>" in text
    assert "Add funds to your balance:" in text
    assert "💰" in text
    assert "45" in text
    assert "User:" not in text
    assert "Manual:" not in text
    assert isinstance(keyboard, InlineKeyboardMarkup)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels == ["bKash", "Nagad", "Rocket", "Binance", "📜 Deposit History"]
    assert [[button.text for button in row] for row in keyboard.inline_keyboard] == [
        ["bKash", "Nagad"],
        ["Rocket", "Binance"],
        ["📜 Deposit History"],
    ]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert callbacks == ["dep_method_1", "dep_method_2", "dep_method_3", "dep_method_4", "open_deposits"]


@pytest.mark.asyncio
async def test_wallet_with_pending_deposit_keeps_history_and_hides_new_payment_methods():
    services = MagicMock()
    services.settings.paused_message = AsyncMock(return_value=None)
    services.settings.get = AsyncMock(return_value="৳")
    services.settings.number = AsyncMock(return_value=125.0)
    services.settings.flag = AsyncMock(return_value=False)
    services.payments.instant_options = AsyncMock(return_value=None)
    services.deposits.methods = AsyncMock(return_value=[{"id": 1, "name": "bKash"}])
    services.deposits.pending_for = AsyncMock(return_value={"id": 20})
    services.users.get = AsyncMock(return_value={"language": "en", "balance": 45.0})
    services.users.get_language = AsyncMock(return_value="en")

    state = MagicMock()
    state.clear = AsyncMock()
    user = User(id=789, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.text = "Add Balance"
    message.answer = AsyncMock()

    await show_deposit_methods(message, state, services)

    text = message.answer.call_args.args[0]
    keyboard = message.answer.call_args.kwargs["reply_markup"]
    assert "<b>Balance:</b>" in text
    assert "💰" in text
    assert "Top-up D20 is being verified" in text
    assert [button.text for row in keyboard.inline_keyboard for button in row] == [
        "📜 Deposit History",
    ]
    assert keyboard.inline_keyboard[0][0].callback_data == "open_deposits"


@pytest.mark.asyncio
async def test_deposit_card_and_keyboards():
    # 1. Keyboard checks
    kb = get_deposit_amount_keyboard("01700000000", method_name="bKash", is_binance=False)
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[1][0].callback_data == 'dep_invoice'
    assert kb.inline_keyboard[0][0].text == "📋 Copy payment details"
    assert kb.inline_keyboard[0][0].copy_text.text == "01700000000"

    rkb = get_back_reply_keyboard("en")
    assert isinstance(rkb, ReplyKeyboardMarkup)
    assert len(rkb.keyboard) == 1
    assert rkb.keyboard[0][0].text == "🔙 Back"

    rkb_bn = get_back_reply_keyboard("bn")
    assert rkb_bn.keyboard[0][0].text == "🔙 ব্যাক"


@pytest.mark.asyncio
async def test_render_method_details_flow():
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.settings.get = AsyncMock(return_value="৳")

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.answer = AsyncMock()

    method = {
        "id": 1,
        "name": "bKash",
        "account_type": "personal",
        "account_info": "01700000000",
        "min_deposit": 50.0,
        "rate_to_currency": 125.0,
        "auto_verify": "none",
        "instructions": "Send Money to this personal number",
    }

    await render_method_details(message, state, services, method)

    current_state = await state.get_state()
    assert current_state == DepositStates.method_selected.state

    # The method opens payment instructions directly, without amount chips.
    assert message.answer.call_count == 1
    call = message.answer.call_args_list[0]
    text = call[0][0]
    assert "bKash (Send Money)" in text
    assert "01700000000" in text
    assert "Minimum: <b>৳50</b>" in text
    assert "Rate: 1 USD = ৳125 BDT" in text
    assert "tap Payment Done" in text
    assert "Send Money to this personal number" in text

    kb = call[1]["reply_markup"]
    assert isinstance(kb, InlineKeyboardMarkup)
    assert [button.text for row in kb.inline_keyboard for button in row] == [
        "📋 Copy Number", "✅ Payment Done", "🔙 Back",
    ]
    assert [button.callback_data for row in kb.inline_keyboard for button in row] == [
        None, "dep_paid_1", "dep_methods",
    ]


@pytest.mark.asyncio
async def test_method_details_binance_hides_rate_and_empty_instructions():
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.settings.get = AsyncMock(return_value="৳")

    user = User(id=789, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.text = "Add Balance"
    message.answer = AsyncMock()
    method = {
        "id": 2,
        "name": "Binance",
        "account_type": "crypto",
        "account_info": "12345678",
        "min_deposit": 1.0,
        "rate_to_currency": 1.0,
        "auto_verify": "binance_pay",
        "instructions": "",
    }

    await render_method_details(message, state, services, method)

    text = message.answer.call_args.args[0]
    assert "Instructions:" not in text
    assert "Exchange Rate:" not in text
    assert "Minimum: <b>1 USDT</b>" in text


@pytest.mark.asyncio
async def test_process_deposit_amount_validation():
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)
    await state.set_state(DepositStates.waiting_for_amount)
    await state.set_data({
        "method_id": 1,
        "method_name": "bKash",
        "account_info": "01700000000",
        "min_deposit": 50.0,
        "is_binance": False,
        "rate": 125.0,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.settings.number = AsyncMock(return_value=25000.0)

    user = User(id=789, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.text = "Add Balance"
    message.answer = AsyncMock()

    # 1. Non-numeric
    message.text = "invalid_amount"
    await process_deposit_amount(message, state, services)
    assert "Enter valid amount" in message.answer.call_args[0][0]

    # 2. Below minimum
    message.text = "30"
    await process_deposit_amount(message, state, services)
    assert "Minimum deposit is 50 ৳" in message.answer.call_args[0][0]

    # 3. Valid amount
    message.text = "100"
    await process_deposit_amount(message, state, services)
    new_state = await state.get_state()
    assert new_state == DepositStates.waiting_for_txid.state
    resp_text = message.answer.call_args[0][0]
    assert "৳100 (USD equivalent: $0.80)" in resp_text
    assert "Enter TrxID below:" in resp_text


@pytest.mark.asyncio
async def test_back_button_navigation():
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)
    await state.set_state(DepositStates.waiting_for_amount)

    services = MagicMock()
    user = User(id=789, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user

    with patch("app.bot.handlers.deposit.show_deposit_methods", new_callable=AsyncMock) as mock_show:
        message.text = "🔙 Back"
        await process_deposit_amount(message, state, services)
        assert mock_show.called
        assert await state.get_state() is None


@pytest.mark.asyncio
async def test_ask_deposit_input_dep_paid_callback():
    from app.bot.handlers.deposit import ask_deposit_input
    from aiogram.types import CallbackQuery

    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)
    await state.set_state(DepositStates.method_selected)
    await state.set_data({
        "method_id": 1,
        "method_name": "bKash",
        "account_info": "01700000000",
        "min_deposit": 50.0,
        "is_binance": False,
    })

    services = MagicMock()
    query = MagicMock(spec=CallbackQuery)
    query.answer = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.edit_text = AsyncMock()
    query.message = msg

    await ask_deposit_input(query, state, services)

    assert await state.get_state() == DepositStates.waiting_for_amount.state
    assert msg.edit_text.called
    text = msg.edit_text.call_args[0][0]
    assert "Minimum: <b>50 ৳</b>" in text
    assert "Enter amount sent in ৳:" in text
    kb = msg.edit_text.call_args[1]["reply_markup"]
    assert kb.inline_keyboard[0][0].text == "📋 Copy payment details"
    assert kb.inline_keyboard[1][0].callback_data == "dep_invoice"


@pytest.mark.asyncio
async def test_process_deposit_txid_direct_submission():
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)
    await state.set_state(DepositStates.waiting_for_txid)
    await state.set_data({
        "method_id": 1,
        "method_name": "bKash",
        "account_info": "01700000000",
        "manual_amount": 0.80,
        "pay_amount": 100.0,
        "usd_amount": 0.80,
        "rate": 125.0,
        "account_type": "personal",
        "is_binance": False,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.deposits.verification_failures = AsyncMock(return_value=[])
    services.deposits.get_method = AsyncMock(return_value={"id": 1, "name": "bKash", "auto_verify": "none"})
    services.zinipay.is_enabled = AsyncMock(return_value=False)
    services.deposits.create_request = AsyncMock(return_value=42)
    services.settings.get = AsyncMock(return_value="৳")

    user = User(id=789, is_bot=False, first_name="Test")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.text = "Add Balance"
    message.answer = AsyncMock()

    # 1. Invalid TrxID
    message.text = "abc"
    await process_deposit_txid(message, state, services)
    assert "Enter valid TrxID:" in message.answer.call_args[0][0]

    # 2. Valid TrxID -> Direct Submission (Plan 1)
    message.text = "BL12345678"
    await process_deposit_txid(message, state, services)
    assert services.deposits.create_request.called
    create_kwargs = services.deposits.create_request.call_args.kwargs
    assert create_kwargs.get("amount") == 0.8
    assert create_kwargs.get("quoted_rate") == 125.0
    assert create_kwargs.get("pay_amount") == 100.0
    assert await state.get_state() is None

    # Initial progress answer, then in-place edit with final status card
    status_msg = message.answer.return_value
    assert status_msg.edit_text.called
    status_text = status_msg.edit_text.call_args[0][0]
    assert "Top-up D42" in status_text
    assert "bKash" in status_text
    assert "৳100" in status_text
    assert "BL12345678" in status_text
    assert "Pending" in status_text
    status_kb = status_msg.edit_text.call_args[1]["reply_markup"]
    assert status_kb.inline_keyboard[0][0].callback_data == "dep_refresh_42"
    assert status_kb.inline_keyboard[1][0].callback_data == "open_deposit"


@pytest.mark.asyncio
async def test_quick_amount_selection_flow():
    from app.bot.handlers.deposit import handle_deposit_quick_amount
    from aiogram.types import CallbackQuery

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
        "is_binance": False,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.settings.get = AsyncMock(return_value="৳")
    services.settings.number = AsyncMock(return_value=25000.0)

    user = User(id=789, is_bot=False, first_name="Test")
    query = MagicMock(spec=CallbackQuery)
    query.from_user = user
    query.data = "dep_amt_500"
    query.answer = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.edit_text = AsyncMock()
    query.message = msg

    await handle_deposit_quick_amount(query, state, services)

    assert await state.get_state() == DepositStates.waiting_for_txid.state
    data = await state.get_data()
    assert data["pay_amount"] == 500.0
    assert data["usd_amount"] == 4.0

    assert msg.edit_text.called
    text = msg.edit_text.call_args[0][0]
    assert "bKash Personal (Send Money)" in text
    assert "01700000000" in text
    assert "৳500 (USD equivalent: $4.00)" in text
    assert "Enter TrxID below:" in text
    kb = msg.edit_text.call_args[1]["reply_markup"]
    assert [b.callback_data for row in kb.inline_keyboard for b in row] == ["dep_change_amt", "dep_methods"]


@pytest.mark.asyncio
async def test_deposit_refresh_callback():
    from app.bot.handlers.deposit import refresh_deposit_status
    from aiogram.types import CallbackQuery

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.settings.get = AsyncMock(return_value="৳")
    services.settings.number = AsyncMock(return_value=125.0)
    services.deposits.get_for_customer = AsyncMock(return_value={
        "id": 42,
        "method_name": "bKash",
        "amount": 4.0,
        "pay_amount": 500.0,
        "rate_to_currency": 234.0,
        "transaction_id": "BL12345678",
        "status": "approved",
    })
    services.users.get = AsyncMock(return_value={"balance": 750.0})

    user = User(id=789, is_bot=False, first_name="Test")
    query = MagicMock(spec=CallbackQuery)
    query.from_user = user
    query.data = "dep_refresh_42"
    query.answer = AsyncMock()
    msg = MagicMock(spec=Message)
    msg.edit_text = AsyncMock()
    query.message = msg

    await refresh_deposit_status(query, services)

    query.answer.assert_called_with("✅ Deposit Approved!")
    assert msg.edit_text.called
    text = msg.edit_text.call_args[0][0]
    assert "Top-up D42" in text
    assert "Approved" in text
    assert "৳500 → $4.00 USD" in text
    assert "Current Balance: <code>$750</code>" in text
    kb = msg.edit_text.call_args[1]["reply_markup"]
    assert [b.callback_data for row in kb.inline_keyboard for b in row] == ["open_shop", "open_deposit"]


@pytest.mark.asyncio
async def test_exchange_rate_and_dollar_conversion_flow():
    """Verify BDT deposits show an explicit USD equivalent at the configured exchange rate."""
    storage = MemoryStorage()
    key = StorageKey(bot_id=123, chat_id=456, user_id=789)
    state = FSMContext(storage=storage, key=key)

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.settings.get = AsyncMock(return_value="৳")
    services.settings.number = AsyncMock(side_effect=lambda key, default=0: 125.0 if key == "usd_rate" else 25000.0)

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.answer = AsyncMock()

    method = {
        "id": 1,
        "name": "bKash",
        "account_type": "personal",
        "account_info": "01700000000",
        "min_deposit": 50.0,
        "rate_to_currency": 234.0,
        "auto_verify": "none",
        "instructions": "",
    }

    # Screen 1: Method details
    await render_method_details(message, state, services, method)
    screen1_text = message.answer.call_args_list[0][0][0]
    assert "bKash (Send Money)" in screen1_text
    assert "Number: <code>01700000000</code>" in screen1_text
    assert "Minimum: <b>৳50</b>" in screen1_text
    assert "Rate: 1 USD = ৳125 BDT" in screen1_text
    assert "tap Payment Done" in screen1_text

    # Screen 2: User enters 500
    message.text = "500"
    message.answer = AsyncMock()
    await process_deposit_amount(message, state, services)
    screen2_text = message.answer.call_args[0][0]
    assert "bKash Personal (Send Money)" in screen2_text
    assert "Number: <code>01700000000</code>" in screen2_text
    assert "Amount: <b>৳500 (USD equivalent: $4.00)</b>" in screen2_text
    assert "Enter TrxID below:" in screen2_text

    # Screen 3: User enters TrxID
    services.deposits.verification_failures = AsyncMock(return_value=[])
    services.deposits.get_method = AsyncMock(return_value=method)
    services.zinipay.is_enabled = AsyncMock(return_value=False)
    services.deposits.create_request = AsyncMock(return_value=99)

    message.text = "BLA7X8Y9Z0"
    status_mock = MagicMock(spec=Message)
    status_mock.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=status_mock)

    await process_deposit_txid(message, state, services)
    assert services.deposits.create_request.called
    kwargs = services.deposits.create_request.call_args.kwargs
    assert kwargs["amount"] == 4.0
    assert kwargs["pay_amount"] == 500.0
    assert kwargs["quoted_rate"] == 125.0

    status_card = status_mock.edit_text.call_args[0][0]
    assert "Top-up D99" in status_card
    assert "bKash" in status_card
    assert "৳500" in status_card
    assert "BLA7X8Y9Z0" in status_card
    assert "Pending" in status_card


@pytest.mark.asyncio
async def test_process_deposit_amount_in_place_edit():
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
    services.settings.number = AsyncMock(return_value=25000.0)

    bot = MagicMock()
    bot.edit_message_text = AsyncMock(return_value=MagicMock(spec=Message, message_id=555))

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.bot = bot
    message.message_id = 999
    message.text = "500"
    message.answer = AsyncMock()
    message.delete = AsyncMock()

    await process_deposit_amount(message, state, services)

    # In-place edit asserts:
    # 1. bot.edit_message_text called on the existing card (555)
    assert bot.edit_message_text.called
    edit_kwargs = bot.edit_message_text.call_args.kwargs
    assert edit_kwargs["chat_id"] == 456
    assert edit_kwargs["message_id"] == 555
    assert "৳500 (USD equivalent: $4.00)" in edit_kwargs["text"]
    assert "Enter TrxID below:" in edit_kwargs["text"]

    # 2. No new message was sent via message.answer!
    message.answer.assert_not_called()

    # 3. User typed message was deleted in background
    await asyncio.sleep(0.01)
    message.delete.assert_called_once()

    # 4. State was updated
    data = await state.get_data()
    assert data["card_msg_id"] == 555
    assert data["pay_amount"] == 500.0
    assert data["usd_amount"] == 4.0
    assert await state.get_state() == DepositStates.waiting_for_txid.state


@pytest.mark.asyncio
async def test_process_deposit_txid_in_place_edit():
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
        "manual_amount": 4.0,
        "pay_amount": 500.0,
        "usd_amount": 4.0,
        "card_msg_id": 555,
        "card_chat_id": 456,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.deposits.pending_for = AsyncMock(return_value=None)
    services.deposits.verification_failures = AsyncMock(return_value=[])
    services.deposits.get_method = AsyncMock(return_value={"id": 1, "name": "bKash", "auto_verify": "none"})
    services.zinipay.is_enabled = AsyncMock(return_value=False)
    services.deposits.create_request = AsyncMock(return_value=101)
    services.settings.get = AsyncMock(return_value="৳")

    card_msg_mock = MagicMock(spec=Message)
    card_msg_mock.message_id = 555
    card_msg_mock.edit_text = AsyncMock()

    bot = MagicMock()
    bot.edit_message_text = AsyncMock(return_value=card_msg_mock)

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.bot = bot
    message.message_id = 1000
    message.text = "BLA7X8Y9Z0"
    message.answer = AsyncMock()
    message.delete = AsyncMock()

    await process_deposit_txid(message, state, services)

    # 1. bot.edit_message_text called to update card 555 with checking status
    assert bot.edit_message_text.called
    edit_args = bot.edit_message_text.call_args.kwargs
    assert edit_args["chat_id"] == 456
    assert edit_args["message_id"] == 555
    assert "Checking payment..." in edit_args["text"]

    # 2. No new message was sent via message.answer!
    message.answer.assert_not_called()

    # 3. User typed message was deleted in background
    await asyncio.sleep(0.01)
    message.delete.assert_called_once()

    # 4. Status card edited onto the existing card
    assert card_msg_mock.edit_text.called
    status_text = card_msg_mock.edit_text.call_args[0][0]
    assert "Top-up D101" in status_text
    assert "bKash" in status_text
    assert "৳500" in status_text
    assert "BLA7X8Y9Z0" in status_text
    assert "Pending" in status_text


@pytest.mark.asyncio
async def test_process_deposit_amount_invalid_keeps_full_card_and_chips():
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
    services.settings.number = AsyncMock(return_value=25000.0)
    services.settings.get = AsyncMock(return_value="৳")

    bot = MagicMock()
    bot.edit_message_text = AsyncMock(return_value=MagicMock(spec=Message, message_id=555))

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.bot = bot
    message.message_id = 999
    message.text = "20"  # Below minimum (50)
    message.answer = AsyncMock()
    message.delete = AsyncMock()

    await process_deposit_amount(message, state, services)

    # Asserts:
    # 1. Card 555 is edited in-place with error and full structure
    assert bot.edit_message_text.called
    kwargs = bot.edit_message_text.call_args.kwargs
    assert kwargs["message_id"] == 555
    text = kwargs["text"]
    assert "bKash Personal (Send Money)" in text
    assert "01700000000" in text
    assert "Minimum: <b>50 ৳</b>" in text
    assert "Exchange rate: <b>1 USD = ৳125 BDT</b>" in text
    assert "Minimum deposit is 50 ৳" in text

    # 2. Quick amount chips keyboard is preserved!
    kb = kwargs["reply_markup"]
    assert isinstance(kb, InlineKeyboardMarkup)
    labels = [b.text for r in kb.inline_keyboard for b in r]
    assert "৳100" in labels
    assert "৳500" in labels
    assert "Back" in labels

    # 3. User typed message was deleted
    await asyncio.sleep(0.01)
    message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_process_deposit_txid_invalid_keeps_full_card():
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
        "manual_amount": 4.0,
        "pay_amount": 500.0,
        "usd_amount": 4.0,
        "card_msg_id": 555,
        "card_chat_id": 456,
    })

    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")

    bot = MagicMock()
    bot.edit_message_text = AsyncMock()

    user = User(id=789, is_bot=False, first_name="Test")
    chat = Chat(id=456, type="private")
    message = MagicMock(spec=Message)
    message.from_user = user
    message.chat = chat
    message.bot = bot
    message.message_id = 1000
    message.text = "abc"  # Invalid TrxID
    message.answer = AsyncMock()
    message.delete = AsyncMock()

    await process_deposit_txid(message, state, services)

    assert bot.edit_message_text.called
    kwargs = bot.edit_message_text.call_args.kwargs
    assert kwargs["message_id"] == 555
    text = kwargs["text"]
    assert "bKash Personal (Send Money)" in text
    assert "01700000000" in text
    assert "৳500 (USD equivalent: $4.00)" in text
    assert "Enter valid TrxID:" in text


