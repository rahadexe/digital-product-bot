"""Built-in standard emoji constants and rendering helpers for optional catalog icons."""

from __future__ import annotations

from html import escape


class Icons:
    """Named slots for built-in controls; catalog icons are configured per category/product."""
    PRODUCTS = None
    SHOP = None
    HOME = None
    CART = None
    DEPOSIT = None
    BALANCE = None
    MONEY = None
    SPENT = None
    COIN = None
    ORDERS = None
    REFER = None
    LINK = None
    ACCOUNT = None
    USER = None
    USER_ID = None
    VIP = None
    CROWN = None
    LIGHTNING = None
    FIRE = None
    SPARKLES = None
    STAR = None
    CHANNEL = None
    SUPPORT = None
    CALL = None
    CHECK = None
    CROSS = None
    WARNING = None
    TIMER = None
    ROCKET = None
    SHIELD = None
    LOCK = None
    KEY = None
    STATS = None
    NOTE = None
    GLOBE = None
    ROBOT = None
    COMPUTER = None
    MAIL = None
    RESELLER = None
    REFRESH = None
    BACK = None
    NEXT = None
    CLOSE = None
    PLUS = None
    MINUS = None
    CLEAR = None
    QUESTION = None
    CONFIRM = None
    BINANCE = None
    BYBIT = None
    BKASH = None
    NAGAD = None
    ROCKET_METHOD = None


def tg_icon(emoji_id: str | None, icon: str) -> str:
    """Render an explicitly selected basic icon without synthesizing a custom-emoji fallback."""
    if emoji_id and str(emoji_id).strip().isdigit():
        return ""
    return escape(icon) if icon else ""


ICON_SHOP = "🛍️"
ICON_CART = "🛒"
ICON_DEPOSIT = "💳"
ICON_REFER = "🎁"
ICON_LINK = "🔗"
ICON_BALANCE = "💰"
ICON_MONEY = "💵"
ICON_SPENT = "💸"
ICON_COIN = "🪙"
ICON_ORDERS = "📦"
ICON_ACCOUNT = "👤"
ICON_USER = "👤"
ICON_ID = "🆔"
ICON_VIP = "💎"
ICON_CROWN = "👑"
ICON_LIGHTNING = "⚡"
ICON_FIRE = "🔥"
ICON_SPARKLES = "✨"
ICON_STAR = "🌟"
ICON_CHANNEL = "📢"
ICON_SUPPORT = "🎧"
ICON_CALL = "📞"
ICON_CHECK = "✅"
ICON_CROSS = "❌"
ICON_WARNING = "⚠️"
ICON_TIMER = "⌛"
ICON_ROCKET = "🚀"
ICON_SHIELD = "🛡️"
ICON_LOCK = "🔒"
ICON_KEY = "🔑"
ICON_STATS = "📊"
ICON_NOTE = "📝"
ICON_GLOBE = "🌐"
ICON_ROBOT = "🤖"
ICON_COMPUTER = "💻"
ICON_MAIL = "✉️"
ICON_RESELLER = "💼"
ICON_PLUS = "➕"
ICON_MINUS = "➖"
ICON_BACK = "🔙"
ICON_NEXT = "➡️"
ICON_CLOSE = "❌"
ICON_SEARCH = "🔍"
ICON_CONFIRM = "✅"
ICON_QUESTION = "❓"
