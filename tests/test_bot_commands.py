from app.bot.keyboards import get_main_inline_keyboard, get_persistent_reply_keyboard
from app.services.notifications import COMMANDS


def test_customer_command_menu_lists_start_api_and_reseller():
    assert [(command.command, command.description) for command in COMMANDS] == [
        ("start", "Start"),
        ("api", "API"),
        ("reseller", "Reseller"),
    ]



def test_customer_keyboard_places_orders_referral_and_support_on_second_row():
    inline_rows = get_main_inline_keyboard().inline_keyboard
    assert [[button.callback_data for button in row] for row in inline_rows] == [
        ["open_categories", "open_deposit"],
        ["open_orders", "open_referral", "open_help"],
    ]

    reply_rows = get_persistent_reply_keyboard(show_icons=False).keyboard
    assert [[button.text for button in row] for row in reply_rows] == [
        ["Shop", "Balance"],
        ["Orders", "Refer", "Help"],
    ]
