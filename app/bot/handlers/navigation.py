"""Menu buttons and commands sent while the bot is waiting for typed text (an amount or a transaction ID)."""

from __future__ import annotations

import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.icons import ICON_CROSS
from app.services import Services

logger = logging.getLogger("app.bot.navigation")


NAVIGATION_TEXTS = {
    "Cancel": "cancel",
    "❌ Cancel": "cancel",
    "❌ Cancel Operation": "cancel",
    "❌ Cancel Deposit": "cancel",
    # 9-button layout
    "Buy VPN": "vpn",
    "Proxy Hub": "proxy",
    "Other Products": "other_products",
    "Other Product": "other_products",
    "Premium Products": "other_products",
    "Mail Box": "mailbox",
    "Search Products": "search",
    "Search": "search",
    "Add Balance": "deposit",
    "Refer & Earn": "referral",
    "My Profile": "account",
    "Support": "support",
    "Apply as a Reseller": "reseller",
    "Reseller Panel": "reseller",
    # Legacy / Emoji variations
    "🛡️ Buy VPN": "vpn",
    "🌐 Proxy Hub": "proxy",
    "💎 Other Products": "other_products",
    "👑 Premium Products": "other_products",
    "✉️ Mail Box": "mailbox",
    "🎁 Refer & Earn": "referral",
    "👤 My Profile": "account",
    "💼 Apply as a Reseller": "reseller",
    "💼 Reseller Panel": "reseller",
    "reseller panel": "reseller",
    "রিসেলার প্যানেল": "reseller",
    # Shop
    "🛍️ Products": "other_products",
    "🛒 Products": "other_products",
    "Products": "other_products",
    "🛍️ Buy Products": "other_products",
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
    from app.bot.handlers import deposit, help_guide, profile, search, shop, start

    await state.clear()
    action = NAVIGATION_TEXTS.get(text) or COMMAND_ACTIONS.get(text.split()[0].split("@")[0], "start")
    if action == "cancel":
        await message.answer(f"{ICON_CROSS} Current operation cancelled.")
        return
    if action == "start":
        await start.render_main_dashboard(message, services, message.from_user.id)
        return
    # A button naming a shop section is resolved against the catalogue, because
    # categories are configured in the console: there is no fixed handler per shop,
    # and hard-coding one per category is what left this map pointing at functions
    # that no longer existed.
    matched = await shop.CategoryTextFilter()(message, services)
    if matched:
        await shop.show_category_or_validity(
            message, state, services, category=matched["category"], back_target="back_to_main"
        )
        return

    handlers = {
        "other_products": "shop.show_other_products_hub",
        "premium": "shop.show_other_products_hub",
        "referral": "profile.show_referral_info",
        "reseller": "profile.show_reseller_info",
        "search": "search.prompt_search",
        "shop": "shop.show_shop_entry",
        "deposit": "deposit.show_deposit_methods",
        "account": "profile.show_user_profile",
        "orders": "profile.show_order_history",
        "support": "help_guide.show_support_info",
        "guide": "help_guide.show_guide_en",
        "channel": "help_guide.show_channel_info",
    }
    modules = {"shop": shop, "profile": profile, "deposit": deposit,
               "help_guide": help_guide, "start": start, "search": search}
    target = handlers.get(action)
    handler = None
    if target:
        module_name, _, func_name = target.partition(".")
        # Looked up by name so a renamed handler falls back to the dashboard rather
        # than raising while the map is built, which broke every menu button at once.
        handler = getattr(modules[module_name], func_name, None)
        if handler is None:
            logger.error("Navigation target %s no longer exists", target)
    if handler is None:
        await start.render_main_dashboard(message, services, message.from_user.id)
        return
    await handler(message, state, services)
