"""Menu buttons and commands sent while the bot is waiting for typed text (an amount or a transaction ID)."""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.services import Services

NAVIGATION_TEXTS = {
    "❌ Cancel": "cancel",
    "❌ Cancel Operation": "cancel",
    "❌ Cancel Deposit": "cancel",
    # Shop
    "🛍️ Products": "shop",
    "🛒 Products": "shop",
    "Products": "shop",
    "🛍️ Buy Products": "shop",
    "🛒 Buy Products": "shop",
    "🛍️ Shop": "shop",
    "🛒 Shop": "shop",
    "🔥 Shop 🔥": "shop",
    "Shop": "shop",
    "পণ্য কিনুন": "shop",
    # Deposit
    "💳 Deposit": "deposit",
    "💰 Add Balance": "deposit",
    "ডিপোজিট করুন": "deposit",
    "Deposit": "deposit",
    # Account
    "👤 Account": "account",
    "💳 My Balance": "account",
    "💼 Account": "account",
    "💰 My Balance": "account",
    "আমার ব্যালেন্স": "account",
    "Balance": "account",
    "Account": "account",
    # Orders
    "📦 Orders": "orders",
    "📦 My Orders": "orders",
    "📦 Order History": "orders",
    "Orders": "orders",
    "Order History": "orders",
    # Support
    "🎧 Support": "support",
    "💬 Support": "support",
    "Support": "support",
    "কাস্টমার সাপোর্ট": "support",
    # Channel / Updates
    "📢 Channel": "channel",
    "📢 Updates": "channel",
    "📢 Update Channel": "channel",
    "Channel": "channel",
    "Updates": "channel",
    # Guide
    "📚 Guide": "guide",
    "Guide": "guide",
}
COMMAND_ACTIONS = {
    "/start": "start",
    "/menu": "start",
    "/cancel": "cancel",
    "/products": "shop",
    "/shop": "shop",
    "/buy": "shop",
    "/deposit": "deposit",
    "/account": "account",
    "/orders": "orders",
    "/support": "support",
    "/channel": "channel",
    "/updates": "channel",
}


def is_navigation(text: str) -> bool:
    return text in NAVIGATION_TEXTS or text.startswith("/")


async def navigate(text: str, message: Message, state: FSMContext, services: Services) -> None:
    """Leave the current conversation and run the action behind a menu button or command."""
    # Imported here because every handler module imports this one.
    from app.bot.handlers import deposit, help_guide, profile, shop, start

    await state.clear()
    action = NAVIGATION_TEXTS.get(text) or COMMAND_ACTIONS.get(text.split()[0].split("@")[0], "start")
    if action in ("start", "cancel"):
        if action == "cancel":
            await message.answer("❌ Current operation cancelled.")
        await start.render_main_dashboard(message, services, message.from_user.id)
        return
    handlers = {
        "shop": shop.show_categories,
        "deposit": deposit.show_deposit_methods,
        "account": profile.show_user_profile,
        "orders": profile.show_order_history,
        "support": help_guide.show_support_info,
        "guide": help_guide.show_guide_info,
        "channel": help_guide.show_channel_info,
    }
    if action in handlers:
        await handlers[action](message, state, services)
    else:
        await start.render_main_dashboard(message, services, message.from_user.id)
