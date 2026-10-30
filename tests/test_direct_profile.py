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
    for command in ["/menu", "/more", "/profile", "/account", "/wallet", "/balance", "/deposit", "/shop", "/orders", "/refer", "/search", "/help", "/channel", "/updates"]:
        assert not is_navigation(command)
    assert not is_navigation("/admin")  # admin commands must reach the admin router


def test_removed_profile_and_more_labels_are_not_menu_routes():
    for label in ["Profile", "👤 Profile", "Wallet", "More", "Settings", "Price List", "My Balance"]:
        assert not is_navigation(label)
        assert label not in NAVIGATION_TEXTS


@pytest.mark.asyncio
@pytest.mark.parametrize("label", ["Account", "👤 Account"])
async def test_account_button_opens_account_hub(label):
    state = SimpleNamespace(get_state=AsyncMock(return_value=None), clear=AsyncMock())
    message = SimpleNamespace(from_user=SimpleNamespace(id=2))
    services = SimpleNamespace()
    with patch("app.bot.handlers.profile.show_account_hub", new_callable=AsyncMock) as open_account:
        await navigate(label, message, state, services)
    open_account.assert_awaited_once_with(message, state, services)


@pytest.mark.asyncio
async def test_show_account_hub_renders_card_and_three_hub_actions():
    from app.bot.handlers.profile import show_account_hub

    state = SimpleNamespace(clear=AsyncMock())
    message = SimpleNamespace(from_user=SimpleNamespace(id=123456, full_name="Rahad"))
    services = SimpleNamespace(
        users=SimpleNamespace(
            get=AsyncMock(return_value={"id": 123456, "balance": 12.50, "is_reseller": 0, "language": "en"}),
            get_language=AsyncMock(return_value="en"),
            ensure=AsyncMock(),
        ),
        purchases=SimpleNamespace(customer_orders=AsyncMock(return_value=([{}], 3))),
        settings=SimpleNamespace(
            number=AsyncMock(return_value=125.0),
            get=AsyncMock(return_value="$"),
            flag=AsyncMock(return_value=True),
        ),
    )
    with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as mock_respond:
        await show_account_hub(message, state, services)

    mock_respond.assert_awaited_once()
    text = mock_respond.call_args[0][1]
    kb = mock_respond.call_args[0][2]
    assert "Rahad" in text
    assert "Your Referral Link" in text
    assert "123456" in text
    assert "$12.5" in text
    assert [[btn.callback_data for btn in row] for row in kb.inline_keyboard] == [
        ["acct_orders"],
        ["acct_referral", "open_alerts"],
        ["open_api_hub", "open_reseller_hub"],
        ["acct_toggle_currency"],
    ]
    assert kb.inline_keyboard[0][0].text == "📦 My Orders (3)"
    assert kb.inline_keyboard[1][0].text == "🎁 Refer"
    assert kb.inline_keyboard[1][1].text == "🔔 Alerts"
    assert kb.inline_keyboard[2][0].text == "🔑 API"
    assert kb.inline_keyboard[2][1].text == "💎 Reseller"
    assert "Currency" in kb.inline_keyboard[3][0].text


@pytest.mark.asyncio
async def test_alerts_submenu_renders_and_toggles_options():
    from app.bot.handlers.profile import show_alerts_hub, toggle_account_alert_item

    state = SimpleNamespace(clear=AsyncMock())
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=777888),
        data="acct_toggle_alert_restock",
        answer=AsyncMock(),
    )
    services = SimpleNamespace(
        users=SimpleNamespace(
            get_notification_preferences=AsyncMock(return_value={"notify_news": True}),
            toggle_notification_preference=AsyncMock(return_value={"notify_news": False}),
            get_language=AsyncMock(return_value="en"),
        ),
    )

    with patch("app.bot.handlers.profile.respond", new_callable=AsyncMock) as mock_respond:
        await show_alerts_hub(query, state, services)
        kb1 = mock_respond.call_args[0][2]
        assert [row[0].text for row in kb1.inline_keyboard] == [
            "🎁 Promotions: ✅ ON",
            "🔄 Stock Alerts: ✅ ON",
            "🏷 Price Drops: ✅ ON",
            "Back",
        ]

        await toggle_account_alert_item(query, state, services)
        kb2 = mock_respond.call_args[0][2]
        assert [row[0].text for row in kb2.inline_keyboard] == [
            "🎁 Promotions: ✅ ON",
            "🔄 Stock Alerts: 🔕 OFF",
            "🏷 Price Drops: ✅ ON",
            "Back",
        ]


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
    assert "Current Balance: <code>$3.50</code>" in text
    assert "User ID:" not in text
    assert "Name:" not in text


def test_dashboard_shows_personalized_customer_details():
    text = build_welcome_text(
        user_name="Rahad",
        username="rahadhasanrafi",
        user_id=6775546602,
        membership="Standard",
        store_name="Premium Haven",
        balance_str="0.00 ৳",
        order_count=5,
        total_users=12798,
        support_username="admin_support",
    )
    assert "Welcome, Rahad!" in text
    assert "Date:" in text
    assert "Time:" in text
    assert "Account Information:" in text
    assert "User ID: <code>6775546602</code>" in text
    assert "Username: @rahadhasanrafi" in text
    assert "Rank: <code>Standard</code>" in text
    assert "Current Balance: <code>0.00 ৳</code>" in text
    assert "Total Users: <code>12,798</code>" in text
    assert "@admin_support" in text
    assert "Use the menu buttons below to continue:" in text
