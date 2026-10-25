"""Direct profile actions, short identity text and backward-compatible navigation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers.deposit import DepositStates, MethodTextFilter
from app.bot.handlers.help_guide import FAQ_ITEMS, GUIDE_TEXTS
from app.bot.handlers.navigation import is_navigation, navigate
from app.bot.handlers.profile import open_wallet_from_legacy_account
from app.bot.keyboards import get_account_keyboard


def context():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=2, user_id=2))


@pytest.mark.parametrize("is_reseller", [False, True])
@pytest.mark.parametrize("lang", ["en", "bn"])
def test_profile_actions_stay_direct_even_with_legacy_options(is_reseller, lang):
    keyboard = get_account_keyboard(
        lang=lang,
        is_admin=True,
        is_reseller=is_reseller,
        order_count=99,
        include_referral=True,
        ref_link="https://t.me/example_bot?start=2",
        share_url="https://t.me/share/url",
    )
    assert [[button.callback_data for button in row] for row in keyboard.inline_keyboard] == [
        ["open_language_menu"],
        ["open_notifications_hub"],
        ["open_api_hub", "open_reseller_hub" if is_reseller else "open_reseller"],
        ["back_to_main"],
    ]
    assert all(button.url is None for row in keyboard.inline_keyboard for button in row)


@pytest.mark.asyncio
async def test_legacy_profile_entry_redirects_to_wallet_without_identity_details():
    state = context()
    await state.set_state(DepositStates.waiting_for_txid)
    event = SimpleNamespace(from_user=SimpleNamespace(id=2, full_name="<Buyer> & Co"))
    services = SimpleNamespace()
    with patch("app.bot.handlers.deposit.show_deposit_methods", new_callable=AsyncMock) as show_wallet:
        await open_wallet_from_legacy_account(event, state, services)
    show_wallet.assert_awaited_once_with(event, state, services)
    assert await state.get_state() is None
    assert await state.get_data() == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("label", [
    "👤 Profile", "Profile", "profile", "PROFILE", "👤 PROFILE",
    "/profile", "/profile@example_bot", "/me", "Account", "👤 Account", "/account",
])
async def test_profile_and_legacy_labels_leave_payment_prompts(label):
    state = context()
    await state.set_state(DepositStates.waiting_for_amount)
    message = SimpleNamespace(from_user=SimpleNamespace(id=2))
    services = SimpleNamespace()
    assert is_navigation(label)
    with patch("app.bot.handlers.deposit.show_deposit_methods", new_callable=AsyncMock) as show_wallet:
        await navigate(label, message, state, services)
    show_wallet.assert_awaited_once_with(message, state, services)
    assert await state.get_state() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("label", [
    "/balance", "Balance", "My Balance", "💰 My Balance", "💳 My Balance", "MY BALANCE",
])
async def test_balance_aliases_keep_wallet_access(label):
    state = context()
    message = SimpleNamespace(from_user=SimpleNamespace(id=2))
    services = SimpleNamespace()
    with patch("app.bot.handlers.deposit.show_deposit_methods", new_callable=AsyncMock) as show:
        await navigate(label, message, state, services)
    show.assert_awaited_once_with(message, state, services)


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["👤 Profile", "Profile", "PROFILE", "প্রোফাইল"])
async def test_profile_button_cannot_be_mistaken_for_a_payment_method(label):
    message = SimpleNamespace(text=label)
    assert await MethodTextFilter()(message, SimpleNamespace()) is False


def test_help_points_to_the_main_menu_instead_of_removed_profile_shortcuts():
    delivery = FAQ_ITEMS["delivery"]["answer"]["en"]
    assert "Open Orders" in delivery
    assert "Open Account" not in delivery
    assert "Open Refer" in FAQ_ITEMS["referral"]["answer"]["en"]
    assert "<b>Orders</b>" in GUIDE_TEXTS["en"]
    assert "<b>Refer</b>" in GUIDE_TEXTS["en"]
    assert "My Profile" not in GUIDE_TEXTS["en"]
