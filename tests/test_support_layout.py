from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.help_guide import FAQ_ITEMS, show_faq_answer, show_help_faq_hub
from app.bot.keyboards import (
    get_help_faq_keyboard,
    get_support_reply_keyboard,
)


EMOJI_ICONS = "⚡💳📦🎁🛍️👤⏱️💡🧑‍💻💬📢🎬🔙"


@pytest.mark.parametrize(
    ("lang", "expected_rows"),
    [
        (
            "en",
            [
                ["Buying"],
                ["Payments"],
                ["Delivery"],
                ["Referrals"],
                ["Support"],
                ["Updates"],
                ["Back"],
            ],
        ),
        (
            "bn",
            [
                ["Buying"],
                ["Payments"],
                ["Delivery"],
                ["Referrals"],
                ["Support"],
                ["Updates"],
                ["Back"],
            ],
        ),
    ],
)
def test_help_keyboard_uses_text_only_stacked_topics(lang, expected_rows):
    keyboard = get_help_faq_keyboard(
        support_handle="support_team",
        channels=[{"title": "News", "url": "https://t.me/news"}],
        lang=lang,
    )

    assert [[button.text for button in row] for row in keyboard.inline_keyboard] == expected_rows
    assert all(not any(icon in button.text for icon in EMOJI_ICONS)
               for row in keyboard.inline_keyboard for button in row)
    # Direct clickable URL buttons
    assert keyboard.inline_keyboard[-3][0].url == "https://t.me/support_team"
    assert keyboard.inline_keyboard[-2][0].url == "https://t.me/news"


def test_help_keyboard_omits_unconfigured_support_and_channels():
    keyboard = get_help_faq_keyboard(
        support_handle="",
        channels=[],
        lang="en",
    )
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "Support" not in labels
    assert "Updates" not in labels
    assert len(labels) == 5


def test_faq_answers_have_no_decorative_icons():
    for item in FAQ_ITEMS.values():
        for answer in item["answer"].values():
            assert not any(icon in answer for icon in EMOJI_ICONS)


def test_faq_answers_match_current_purchase_payment_referral_and_delivery_flows():
    answers = {
        key: item["answer"]
        for key, item in FAQ_ITEMS.items()
    }

    assert "quantity" in answers["buy"]["en"].lower()
    assert "Binance Order ID" in answers["deposit"]["en"]
    assert "prepared" in answers["delivery"]["en"]
    assert "channel check" in answers["referral"]["en"]
    assert "not for link clicks" in answers["referral"]["en"]
    assert all(set(item["answer"]) == {"en"} for item in FAQ_ITEMS.values())


def test_support_reply_keyboard_uses_plain_labels():
    reply_keyboard = get_support_reply_keyboard()
    labels = [button.text for row in reply_keyboard.keyboard for button in row]
    assert labels == ["Guide", "Back to Main"]


@pytest.mark.asyncio
async def test_technical_support_detail_has_plain_text_and_action():
    services = MagicMock()
    services.users.get_language = AsyncMock(return_value="en")
    services.settings.values = AsyncMock(return_value={"support_username": "@support_team"})

    query = MagicMock(spec=CallbackQuery)
    query.data = "faq_support"
    query.from_user = MagicMock(id=123)
    query.message = MagicMock(spec=Message)
    query.message.edit_text = AsyncMock()
    query.answer = AsyncMock()

    await show_faq_answer(query, MagicMock(), services)

    text, kwargs = query.message.edit_text.call_args.args[0], query.message.edit_text.call_args.kwargs
    assert "<b>Support</b>" in text
    assert "order or top-up reference" in text
    assert "24/7" not in text
    assert "@support_team" in text
    assert not any(icon in text for icon in EMOJI_ICONS)
    buttons = kwargs["reply_markup"].inline_keyboard
    assert buttons[0][0].text == "Message support"
    assert buttons[-1][0].text == "Back to help"
    assert all(not any(icon in button.text for icon in EMOJI_ICONS)
               for row in buttons for button in row)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lang", "expected_text"),
    [
        ("en", "Choose a topic."),
        ("bn", "Choose a topic."),
    ],
)
async def test_show_help_faq_hub_heading_text(lang, expected_text):
    services = MagicMock()
    services.users.get_language = AsyncMock(return_value=lang)
    services.settings.values = AsyncMock(return_value={})
    services.update_channels.channels = AsyncMock(return_value=[])

    event = MagicMock(spec=Message)
    event.from_user = MagicMock(id=123)
    event.answer = AsyncMock()

    state = MagicMock()
    state.clear = AsyncMock()

    await show_help_faq_hub(event, state, services)

    text = event.answer.call_args.args[0]
    assert text == expected_text

