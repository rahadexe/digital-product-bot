"""Menu buttons and commands sent while the bot is waiting for typed text (an amount or a transaction ID)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.icons import ICON_CROSS
from app.services import Services

logger = logging.getLogger("app.bot.navigation")

router = Router(name="navigation_router")


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
    "🔍 Search": "search",
    "Add Balance": "deposit",
    "💳 Add Balance": "deposit",
    "Wallet": "deposit",
    "💳 Wallet": "deposit",
    "💼 Wallet": "deposit",
    "My Orders": "orders",
    "📦 My Orders": "orders",
    "My Balance": "account",
    "💰 My Balance": "account",
    "Refer & Earn": "referral",
    "🎁 Refer & Earn": "referral",
    "My Profile": "account",
    "👤 My Profile": "account",
    "Account": "account",
    "👤 Account": "account",
    "Refer": "referral",
    "🎁 Refer": "referral",
    "Support": "support",
    "🎧 Support": "support",
    "Apply as a Reseller": "reseller",
    "Become Reseller": "reseller",
    "💼 Become Reseller": "reseller",
    "become reseller": "reseller",
    "Reseller Panel": "reseller",
    "💼 Reseller Panel": "reseller",
    "👑 Admin Panel": "admin",
    # Bengali (bn)
    "💳 অ্যাড ব্যালেন্স": "deposit",
    "অ্যাড ব্যালেন্স": "deposit",
    "💳 ওয়ালেট": "deposit",
    "ওয়ালেট": "deposit",
    "📦 আমার অর্ডার": "orders",
    "আমার অর্ডার": "orders",
    "💰 আমার ব্যালেন্স": "account",
    "আমার ব্যালেন্স": "account",
    "🔍 সার্চ": "search",
    "সার্চ": "search",
    "🎁 রেফার ও ইনকাম": "referral",
    "রেফার ও ইনকাম": "referral",
    "🎁 রেফার": "referral",
    "রেফার": "referral",
    "👤 আমার প্রোফাইল": "account",
    "আমার প্রোফাইল": "account",
    "👤 একাউন্ট": "account",
    "একাউন্ট": "account",
    "🎧 সাপোর্ট": "support",
    "💼 রিসেলার হন": "reseller",
    "রিসেলার হন": "reseller",
    "💼 রিসেলার প্যানেল": "reseller",
    "রিসেলার প্যানেল": "reseller",
    "👑 অ্যাডমিন প্যানেল": "admin",
    "অ্যাডমিন প্যানেল": "admin",
    "🛍️ অন্যান্য প্রোডাক্ট": "other_products",
    "অন্যান্য প্রোডাক্ট": "other_products",
    "🛍️ সকল প্রোডাক্ট": "other_products",
    "সকল প্রোডাক্ট": "other_products",
    # Hindi (hi)
    "💳 बैलेंस जोड़ें": "deposit",
    "बैलेंस जोड़ें": "deposit",
    "💳 वॉलेट": "deposit",
    "वॉलेट": "deposit",
    "🔍 खोजें": "search",
    "खोजें": "search",
    "🎁 रेफर और कमाएं": "referral",
    "रेफर और कमाएं": "referral",
    "🎁 रेफर": "referral",
    "रेफर": "referral",
    "👤 मेरी प्रोफाइल": "account",
    "मेरी प्रोफाइल": "account",
    "👤 अकाउंट": "account",
    "अकाउंट": "account",
    "🎧 सहायता": "support",
    "सहायता": "support",
    "💼 रीसेलर बनें": "reseller",
    "रीसेलर बनें": "reseller",
    "💼 रीसेलर पैनल": "reseller",
    "रीसेलर पैनल": "reseller",
    "👑 एडमिन पैनल": "admin",
    "एडमिन पैनल": "admin",
    "🛍️ अन्य उत्पाद": "other_products",
    "अन्य उत्पाद": "other_products",
    # Urdu (ur)
    "💳 بیلنس شامل کریں": "deposit",
    "بیلنس شامل کریں": "deposit",
    "💳 والٹ": "deposit",
    "والٹ": "deposit",
    "🔍 تلاش کریں": "search",
    "تلاش کریں": "search",
    "🎁 ریفر اور کمائیں": "referral",
    "ریفر اور کمائیں": "referral",
    "🎁 ریفر": "referral",
    "ریفر": "referral",
    "👤 میری پروفائل": "account",
    "میری پروفائل": "account",
    "👤 اکاؤنٹ": "account",
    "اکاؤنٹ": "account",
    "🎧 سپورٹ": "support",
    "سپورٹ": "support",
    "💼 ری سیلر بنیں": "reseller",
    "ری سیلر بنیں": "reseller",
    "💼 ری سیلر پینل": "reseller",
    "ری سیلر پینل": "reseller",
    "👑 ایڈمن پینل": "admin",
    "ایڈمن پینل": "admin",
    "🛍️ دیگر مصنوعات": "other_products",
    "دیگر مصنوعات": "other_products",
    # Legacy / Emoji variations
    "🛡️ Buy VPN": "vpn",
    "🌐 Proxy Hub": "proxy",
    "💎 Other Products": "other_products",
    "🛍️ Other Products": "other_products",
    "🛍️ All Products": "other_products",
    "All Products": "other_products",
    "👑 Premium Products": "other_products",
    "✉️ Mail Box": "mailbox",
    "🎁 Refer & Earn": "referral",
    "👤 My Profile": "account",
    "💼 Apply as a Reseller": "reseller",
    "💼 Reseller Panel": "reseller",
    "reseller panel": "reseller",
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
    # Deposit
    "💳 Deposit": "deposit",
    "💰 Add Balance": "deposit",
    "Deposit": "deposit",
    # Account
    "👤 Account": "account",
    "💳 My Balance": "account",
    "💼 Account": "account",
    "💰 My Balance": "account",
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
    "/language": "language",
    "/lang": "language",
}


def is_navigation(text: str) -> bool:
    return text in NAVIGATION_TEXTS or text.startswith("/")


async def navigate(text: str, message: Message, state: FSMContext, services: Services) -> None:
    """Leave the current conversation and run the action behind a menu button or command."""
    # Imported here because every handler module imports this one.
    from app.bot.handlers import admin, deposit, help_guide, profile, search, shop, start

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
        "admin": "admin.cmd_admin_help",
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
        "language": "profile.show_language_menu",
    }
    modules = {"admin": admin, "shop": shop, "profile": profile, "deposit": deposit,
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


@router.message(F.text.func(lambda text: bool(text and text.strip() in NAVIGATION_TEXTS)))
async def handle_navigation_message(message: Message, state: FSMContext, services: Services):
    text = (message.text or "").strip()
    await navigate(text, message, state, services)

