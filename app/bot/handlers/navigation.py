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
    "Account & Refer": "account",
    "👤 Account & Refer": "account",
    "Refer": "referral",
    "🎁 Refer": "referral",
    "Support": "support",
    "🎧 Support": "support",
    "Help": "help",
    "help": "help",
    "💬 Help": "help",
    "💬 হেল্প": "help",
    "হেল্প": "help",
    "Apply as a Reseller": "reseller",
    "Become Reseller": "reseller",
    "💼 Become Reseller": "reseller",
    "become reseller": "reseller",
    "Reseller Panel": "reseller",
    "💼 Reseller Panel": "reseller",
    "👑 Admin Panel": "admin",
    "Admin Panel": "admin",
    # Uppercase layout (Free Otp Panel ALL CAPS style)
    "🛍️ PRODUCTS": "other_products",
    "PRODUCTS": "other_products",
    "🔍 SEARCH": "search",
    "SEARCH": "search",
    "🛍️ ALL CATALOG": "other_products",
    "ALL CATALOG": "other_products",
    "🛍️ ALL PRODUCTS": "other_products",
    "ALL PRODUCTS": "other_products",
    "💳 WALLET": "deposit",
    "WALLET": "deposit",
    "💳 ADD BALANCE": "deposit",
    "ADD BALANCE": "deposit",
    "📦 ORDERS": "orders",
    "ORDERS": "orders",
    "📦 MY ORDERS": "orders",
    "MY ORDERS": "orders",
    "👤 ACCOUNT": "account",
    "ACCOUNT": "account",
    "👤 ACCOUNT & REFER": "account",
    "ACCOUNT & REFER": "account",
    "👤 MY PROFILE": "account",
    "MY PROFILE": "account",
    "🎧 SUPPORT": "support",
    "SUPPORT": "support",
    "👑 ADMIN PANEL": "admin",
    "ADMIN PANEL": "admin",
    "🎁 REFER": "referral",
    "REFER": "referral",
    "🎁 REFERRAL": "referral",
    "REFERRAL": "referral",
    "🎁 REFER & EARN": "referral",
    "REFER & EARN": "referral",
    "💼 RESELLER": "reseller",
    "RESELLER": "reseller",
    "💼 BECOME RESELLER": "reseller",
    "BECOME RESELLER": "reseller",
    "🔑 RESELLER PANEL": "reseller",
    "💼 RESELLER PANEL": "reseller",
    "RESELLER PANEL": "reseller",
    "🔑 API & RESELLER": "reseller",
    "👤 একাউন্ট": "account",
    "একাউন্ট": "account",
    "👤 অ্যাকাউন্ট": "account",
    "অ্যাকাউন্ট": "account",
    "👤 একাউন্ট ও রেফার": "account",
    "একাউন্ট ও রেফার": "account",
    "👤 অ্যাকাউন্ট ও রেফার": "account",
    "অ্যাকাউন্ট ও রেফার": "account",
    "🎁 রেফারেল": "referral",
    "রেফারেল": "referral",
    "💼 রিসেলার": "reseller",
    "রিসেলার": "reseller",
    "💼 রিসেলার আবেদন": "reseller",
    "রিসেলার আবেদন": "reseller",
    "💼 রিসেলার প্যানেল": "reseller",
    "রিসেলার প্যানেল": "reseller",
    "💳 ওয়ালেট": "deposit",
    "ওয়ালেট": "deposit",
    "🔍 সার্চ": "search",
    "সার্চ": "search",
    "🎧 সাপোর্ট": "support",
    "সাপোর্ট": "support",
    "📊 PRICE LIST": "pricelist",
    "PRICE LIST": "pricelist",
    "Price List": "pricelist",
    "Prices": "pricelist",
    "prices": "pricelist",
    "📊 Price List": "pricelist",
    "📊 BALANCE HISTORY": "balance_history",
    "BALANCE HISTORY": "balance_history",
    "Balance History": "balance_history",
    "📊 Balance History": "balance_history",
    "📊 DEPOSIT HISTORY": "balance_history",
    "DEPOSIT HISTORY": "balance_history",
    "Deposit History": "balance_history",
    "📊 Deposit History": "balance_history",
    "HISTORY": "balance_history",
    "📊 HISTORY": "balance_history",
    "History": "balance_history",
    "📊 History": "balance_history",
    "ডিপোজিট হিস্ট্রি": "balance_history",
    "📊 ডিপোজিট হিস্ট্রি": "balance_history",
    "হিস্ট্রি": "balance_history",
    "📊 হিস্ট্রি": "balance_history",
    "ব্যালেন্স হিস্ট্রি": "balance_history",
    "📊 ব্যালেন্স হিস্ট্রি": "balance_history",
    "🏠 MAIN MENU": "start",
    "MAIN MENU": "start",
    "🏠 Main Menu": "start",
    "Main Menu": "start",
    "🔙 BACK TO MAIN": "start",
    "BACK TO MAIN": "start",
    "🔙 Back to Main": "start",
    "Back to Main": "start",
    "🔙 BACK TO CATALOG": "other_products",
    "BACK TO CATALOG": "other_products",
    "🔙 Back to Catalog": "other_products",
    "Back to Catalog": "other_products",
    "🔙 BACK TO PRODUCTS": "other_products",
    "BACK TO PRODUCTS": "other_products",
    "🔙 Back to Products": "other_products",
    "Back to Products": "other_products",
    "🔙 BACK TO WALLET": "deposit",
    "BACK TO WALLET": "deposit",
    "🔙 Back to Wallet": "deposit",
    "Back to Wallet": "deposit",
    "📊 STATS": "admin",
    "STATS": "admin",
    "📊 Stats": "admin",
    "Stats": "admin",
    "📦 PRODUCTS": "other_products",
    "📦 Products": "other_products",
    "💳 DEPOSITS": "deposit",
    "DEPOSITS": "deposit",
    "💳 Deposits": "deposit",
    "Deposits": "deposit",
    "👥 USERS": "admin",
    "USERS": "admin",
    "👥 Users": "admin",
    "Users": "admin",
    "⚙️ SETTINGS": "admin",
    "SETTINGS": "admin",
    "⚙️ Settings": "admin",
    "Settings": "admin",
    "📖 GUIDE": "guide",
    "GUIDE": "guide",
    "📖 Guide": "guide",
    "Guide": "guide",
    "🔄 REFRESH": "orders",
    "REFRESH": "orders",
    "🔄 Refresh": "orders",
    "Refresh": "orders",
    "🔄 রিফ্রেশ": "orders",
    "🌐 LANGUAGE": "language",
    "LANGUAGE": "language",
    "🌐 Language": "language",
    "Language": "language",
    "🌐 ভাষা": "language",
    "ভাষা": "language",
    "🇬🇧 English": "set_lang_en",
    "English": "set_lang_en",
    "ENGLISH": "set_lang_en",
    "🇧🇩 বাংলা": "set_lang_bn",
    "বাংলা": "set_lang_bn",
    "🔙 BACK": "start",
    "BACK": "start",
    "🔙 Back": "start",
    "Back": "start",
    "❌ CANCEL": "cancel",
    "CANCEL": "cancel",
    "❌ Cancel": "cancel",
    "Cancel": "cancel",
    "❌ বাতিল": "cancel",
    "বাতিল": "cancel",
    "🔙 ব্যাক": "start",
    "ব্যাক": "start",
    "🏠 মেইন মেনু": "start",
    "মেইন মেনু": "start",
    "🔙 ক্যাটালগ": "other_products",
    "ক্যাটালগ": "other_products",
    "🔙 প্রোডাক্ট তালিকা": "other_products",
    "প্রোডাক্ট তালিকা": "other_products",
    "📖 গাইড": "guide",
    "গাইড": "guide",
    "📊 প্রাইস লিস্ট": "pricelist",
    "প্রাইস লিস্ট": "pricelist",
    "প্রাইস": "pricelist",
    "রিফ্রেশ": "orders",
    # Bengali (bn)
    "💳 অ্যাড ব্যালেন্স": "deposit",
    "অ্যাড ব্যালেন্স": "deposit",
    "💳 ওয়ালেট": "deposit",
    "ওয়ালেট": "deposit",
    "📦 আমার অর্ডার": "orders",
    "আমার অর্ডার": "orders",
    "📦 অর্ডার": "orders",
    "অর্ডার": "orders",
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
    "সাপোর্ট": "support",
    "🛍️ শপ": "shop",
    "শপ": "shop",
    "🛍️ স্টোর": "other_products",
    "স্টোর": "other_products",
    "🛍️ Store": "other_products",
    "Store": "other_products",
    "STORE": "other_products",
    "🛍️ STORE": "other_products",
    "🛍️ Shop": "other_products",
    "Shop": "other_products",
    "SHOP": "shop",
    "🛍️ SHOP": "shop",
    "📦 অর্ডারস": "orders",
    "অর্ডারস": "orders",
    "🎁 Referral": "referral",
    "Referral": "referral",
    "REFERRAL": "referral",
    "🎁 REFERRAL": "referral",
    "💼 রিসেলার হন": "reseller",
    "রিসেলার হন": "reseller",
    "💼 রিসেলার প্যানেল": "reseller",
    "রিসেলার প্যানেল": "reseller",
    "👑 অ্যাডমিন প্যানেল": "admin",
    "অ্যাডমিন প্যানেল": "admin",
    "🛍️ প্রোডাক্টস": "other_products",
    "প্রোডাক্টস": "other_products",
    "🛍️ অন্যান্য প্রোডাক্ট": "other_products",
    "অন্যান্য প্রোডাক্ট": "other_products",
    "🛍️ সকল প্রোডাক্ট": "other_products",
    "সকল প্রোডাক্ট": "other_products",
    # Legacy / Emoji variations
    "🛡️ Buy VPN": "vpn",
    "🌐 Proxy Hub": "proxy",
    "💎 Other Products": "other_products",
    "🛍️ Other Products": "other_products",
    "🛍️ All Products": "other_products",
    "All Products": "other_products",
    "🛍️ All Catalog": "other_products",
    "All Catalog": "other_products",
    "🛍️ সকল ক্যাটালগ": "other_products",
    "সকল ক্যাটালগ": "other_products",
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
    "🛍️ Shop": "other_products",
    "🛒 Shop": "shop",
    "🔥 Shop 🔥": "shop",
    "Shop": "other_products",
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
# Canonical compact labels take precedence over legacy spelling variants above.
NAVIGATION_TEXTS.update({
    "🛍 Products": "shop", "🛍️ Products": "shop", "Products": "shop", "PRODUCTS": "shop",
    "💰 Wallet": "deposit", "Wallet": "deposit", "WALLET": "deposit",
    "📦 Orders": "orders", "Orders": "orders", "ORDERS": "orders",
    "🎁 Refer": "referral", "Refer": "referral", "REFER": "referral",
    "👤 Account": "account", "Account": "account", "ACCOUNT": "account",
    "👤 Profile": "account", "Profile": "account", "PROFILE": "account",
    "👤 PROFILE": "account", "profile": "account",
    "👤 প্রোফাইল": "account", "প্রোফাইল": "account",
    "💬 Help": "help", "Help": "help", "HELP": "help",
    "💰 My Balance": "deposit", "My Balance": "deposit", "MY BALANCE": "deposit",
    "💳 My Balance": "deposit", "my balance": "deposit",
    "Balance": "deposit", "balance": "deposit", "BALANCE": "deposit", "💰 Balance": "deposit",
    "💰 আমার ব্যালেন্স": "deposit", "আমার ব্যালেন্স": "deposit",
})

COMMAND_ACTIONS = {
    "/start": "start",
    "/menu": "start",
    "/cancel": "cancel",
    "/products": "shop",
    "/shop": "shop",
    "/buy": "shop",
    "/deposit": "deposit",
    "/wallet": "deposit",
    "/balance": "deposit",
    "/refer": "referral",
    "/account": "account",
    "/profile": "account",
    "/me": "account",
    "/orders": "orders",
    "/support": "support",
    "/help": "help",
    "/channel": "channel",
    "/updates": "channel",
    "/language": "language",
    "/lang": "language",
    "/pricelist": "pricelist",
    "/prices": "pricelist",
}


def is_navigation(text: str) -> bool:
    if not text:
        return False
    clean = text.strip()
    return clean in NAVIGATION_TEXTS or clean.upper() in NAVIGATION_TEXTS or clean.startswith("/")


async def navigate(text: str, message: Message, state: FSMContext, services: Services) -> None:
    """Leave the current conversation and run the action behind a menu button or command."""
    # Imported here because every handler module imports this one.
    from app.bot.handlers import admin, deposit, help_guide, profile, search, shop, start

    current_state = await state.get_state()
    clean = (text or "").strip()

    # If customer is in deposit flow and presses Back or Cancel, return directly to payment options menu
    if clean in {"🔙 Back", "🔙 ব্যাক", "Back", "ব্যাক", "Cancel", "বাতিল", "❌ Cancel", "❌ বাতিল", "back", "cancel"}:
        if current_state and ("DepositStates" in str(current_state) or "deposit" in str(current_state).lower() or "waiting_for_" in str(current_state)):
            await state.clear()
            await deposit.show_deposit_methods(message, state, services)
            return

    await state.clear()
    action = (
        NAVIGATION_TEXTS.get(clean)
        or NAVIGATION_TEXTS.get(clean.upper())
        or COMMAND_ACTIONS.get(clean.split()[0].split("@")[0], "start")
    )
    if action == "cancel":
        lang = await services.users.get_language(message.from_user.id) if message.from_user else "en"
        cancel_msg = f"{ICON_CROSS} বর্তমান কার্যক্রম বাতিল করা হয়েছে।" if lang == "bn" else f"{ICON_CROSS} Current operation cancelled."
        await message.answer(cancel_msg)
        return
    if action == "start":
        await start.render_main_dashboard(message, services, message.from_user.id)
        return
    if action == "set_lang_en":
        if message.from_user:
            await services.users.set_language(message.from_user.id, "en")
        await start.render_main_dashboard(message, services, message.from_user.id)
        return
    if action == "set_lang_bn":
        if message.from_user:
            await services.users.set_language(message.from_user.id, "bn")
        await start.render_main_dashboard(message, services, message.from_user.id)
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
        "help": "help_guide.show_help_faq_hub",
        "guide": "help_guide.show_guide",
        "channel": "help_guide.show_channel_info",
        "language": "profile.show_language_menu",
        "pricelist": "profile.show_price_list",
        "balance_history": "profile.show_deposit_history",
    }
    modules = {"admin": admin, "shop": shop, "profile": profile, "deposit": deposit,
               "help_guide": help_guide, "start": start, "search": search}
    target = handlers.get(action)
    if target:
        module_name, _, func_name = target.partition(".")
        handler = getattr(modules[module_name], func_name, None)
        if handler is not None:
            await handler(message, state, services)
            return
        logger.error("Navigation target %s no longer exists", target)

    # Dynamic match for category names configured in console
    matched = await shop.CategoryTextFilter()(message, services)
    if matched:
        await shop.show_category_or_validity(
            message, state, services, category=matched["category"], back_target="back_to_main"
        )
        return

    await start.render_main_dashboard(message, services, message.from_user.id)


@router.message(F.text.func(lambda text: bool(text and (text.strip() in NAVIGATION_TEXTS or text.strip().upper() in NAVIGATION_TEXTS))))
async def handle_navigation_message(message: Message, state: FSMContext, services: Services):
    text = (message.text or "").strip()
    await navigate(text, message, state, services)
