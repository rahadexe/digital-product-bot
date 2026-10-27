"""Tests for the English customer menu and removed legacy routes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.bot.handlers.navigation import COMMAND_ACTIONS, NAVIGATION_TEXTS, is_navigation, navigate
from app.bot.handlers.start import build_welcome_text


def test_only_current_customer_commands_are_routed():
    assert COMMAND_ACTIONS == {"/start": "start", "/api": "api", "/reseller": "reseller"}
    for command in COMMAND_ACTIONS:
        assert is_navigation(command)
    for command in ["/menu", "/more", "/profile", "/account", "/wallet", "/balance", "/deposit", "/shop", "/orders", "/refer", "/search", "/help"]:
        assert not is_navigation(command)
    assert not is_navigation("/admin")  # admin commands must reach the admin router


def test_removed_profile_and_more_labels_are_not_menu_routes():
    for label in ["Profile", "👤 Profile", "Account", "Wallet", "More", "Settings", "Price List", "My Balance"]:
        assert not is_navigation(label)
        assert label not in NAVIGATION_TEXTS


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["Balance", "💰 Balance", "Add Balance"])
async def test_balance_button_opens_balance_screen(label):
    state = SimpleNamespace(get_state=AsyncMock(return_value=None), clear=AsyncMock())
    message = SimpleNamespace(from_user=SimpleNamespace(id=2))
    services = SimpleNamespace()
    with patch("app.bot.handlers.deposit.show_deposit_methods", new_callable=AsyncMock) as open_balance:
        await navigate(label, message, state, services)
    open_balance.assert_awaited_once_with(message, state, services)


@pytest.mark.asyncio
@pytest.mark.parametrize(("command", "handler"), [("/api", "show_api_hub"), ("/reseller", "show_reseller_hub")])
async def test_api_and_reseller_commands_open_their_hubs(command, handler):
    state = SimpleNamespace(get_state=AsyncMock(return_value=None), clear=AsyncMock())
    message = SimpleNamespace(from_user=SimpleNamespace(id=2))
    services = SimpleNamespace()
    with patch(f"app.bot.handlers.profile.{handler}", new_callable=AsyncMock) as open_hub:
        await navigate(command, message, state, services)
    open_hub.assert_awaited_once_with(message, state, services)


def test_dashboard_shows_balance_without_personal_identity():
    text = build_welcome_text(balance_str="$3.50", order_count=2)
    assert "Welcome!" in text
    assert "Balance: <code>$3.50</code>" in text
    assert "ID:" not in text
    assert "Name:" not in text
