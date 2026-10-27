from app.services.notifications import COMMANDS


def test_customer_command_menu_lists_start_api_and_reseller():
    assert [(command.command, command.description) for command in COMMANDS] == [
        ("start", "Start"),
        ("api", "API"),
        ("reseller", "Reseller"),
    ]
