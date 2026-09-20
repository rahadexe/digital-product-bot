"""Telegram Custom Emoji icons extracted from user-provided packs.

Packs:
- http_dxauniverse_by_fStikBot
- Raika_Games
- emoji1912
- NewsEmoji
- G8yg_by_fStikBot
"""

from __future__ import annotations

from typing import Any


class Icons:
    # Navigation & Core Buttons
    PRODUCTS = "6084664543152183861"       # 🛍️ (Raika_Games)
    CART = "6102911544205515696"           # 🛒 (Raika_Games)
    DEPOSIT = "6233367447789899509"        # 💰 Add Balance (tongyong_renmin)
    REFER = "5379742233853451967"          # 🔗 Refer & Earn (MeshChainEmoji)
    BALANCE = "6102735781258861018"        # 💰 (Raika_Games)
    MONEY = "5956180995924300841"          # 💵 (emoji1912)
    SPENT = "6251349286152316652"          # 💸 (Raika_Games)
    COIN = "6251368935627692476"           # 🪙 (Raika_Games)
    ORDERS = "6084747049473940188"         # 🎁 (Raika_Games)
    ACCOUNT = "5208604387156448480"        # 👤 My Profile (EmergeTeamAnimated)
    USER_ID = "5278510335723066039"        # 🆔 (G8yg_by_fStikBot)
    VIP = "6084472820107057290"            # 💎 (Raika_Games)
    CROWN = "6102443543094105763"          # 👑 (Raika_Games)
    LIGHTNING = "6084566793991494246"      # ⚡ (Raika_Games)
    FIRE = "6084435123179100660"           # 🔥 (Raika_Games)
    SPARKLES = "5325547803936572038"       # ✨ (NewsEmoji)
    STAR = "5337102391244263212"           # 🌟 (http_dxauniverse_by_fStikBot)
    CHANNEL = "6082236434930998087"        # 📢 (Raika_Games)
    SUPPORT = "5438511323631609540"        # 🎧 Support (SAIDOVSEMOJIS)
    CALL = "5438511323631609540"           # 🎧 Support (SAIDOVSEMOJIS)
    CHECK = "6084595583157278741"          # ✅ (Raika_Games)
    CROSS = "6082643408852099504"          # ❌ (Raika_Games)
    WARNING = "6084842505122094054"        # ⚠️ (Raika_Games)
    TIMER = "5386367538735104399"          # ⌛ (NewsEmoji)
    ROCKET = "5352597830089347330"         # 🚀 (http_dxauniverse_by_fStikBot)
    SHIELD = "5190447043545438788"         # 🛡️ (http_dxauniverse_by_fStikBot)
    LOCK = "6084535127197620168"           # 🔒 (Raika_Games)
    KEY = "6105118564690172709"            # 🔐 (Raika_Games)
    STATS = "5231200819986047254"          # 📊 (NewsEmoji)
    NOTE = "5192739271886282680"           # 📝 (http_dxauniverse_by_fStikBot)
    GLOBE = "5334590977837403844"          # 🌐 (http_dxauniverse_by_fStikBot)
    ROBOT = "6084700423308975252"          # 🤖 (Raika_Games)
    COMPUTER = "6251457360414382759"       # 💻 (Raika_Games)
    MAIL = "5253742260054409879"           # ✉️ (NewsEmoji)
    RESELLER = "5312361253610475399"       # 🛒 Apply as a Reseller (FinanceEmoji)
    REFRESH = "6082234751303817560"        # 🔄 (Raika_Games 3D circular arrows)
    BACK = "6206505206197261313"           # 🔙 (Earning_ON_World_by_TgEmojis_bot)
    NEXT = "6206325217002788818"           # ➡️ (Earning_ON_World_by_TgEmojis_bot)
    CLOSE = "6206110936789423908"          # ❌ (Earning_ON_World_by_TgEmojis_bot)
    PLUS = "6206375377925839184"           # ➕ (Earning_ON_World_by_TgEmojis_bot)
    MINUS = "6206302088603900186"          # ➖ (Earning_ON_World_by_TgEmojis_bot)
    CLEAR = "6206108815075579644"          # 🗑 (Earning_ON_World_by_TgEmojis_bot)
    QUESTION = "6206306186002698906"       # ❓ (Earning_ON_World_by_TgEmojis_bot)
    CONFIRM = "6206185428702206246"        # ✅ (Earning_ON_World_by_TgEmojis_bot)
    BINANCE = "5348212415077064131"        # 🟡 Binance (http_dxauniverse_by_fStikBot)
    BYBIT = "5348372939479751825"          # ⚫ Bybit (http_dxauniverse_by_fStikBot)
    BKASH = "6217678000977089090"          # 🌸 bKash
    NAGAD = "6217625168584380551"          # 🔴 Nagad
    ROCKET_METHOD = "4911601033496494993"  # 🟣 Rocket (Payment Method)


def tg_icon(emoji_id: str, fallback: str) -> str:
    """Render a custom emoji in HTML with fallback."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


ICON_SHOP = tg_icon(Icons.PRODUCTS, "🛍️")
ICON_CART = tg_icon(Icons.CART, "🛒")
ICON_DEPOSIT = tg_icon(Icons.DEPOSIT, "💳")
ICON_REFER = tg_icon(Icons.REFER, "🔗")
ICON_BALANCE = tg_icon(Icons.BALANCE, "💰")
ICON_MONEY = tg_icon(Icons.MONEY, "💵")
ICON_SPENT = tg_icon(Icons.SPENT, "💸")
ICON_COIN = tg_icon(Icons.COIN, "🪙")
ICON_ORDERS = tg_icon(Icons.ORDERS, "🎁")
ICON_ACCOUNT = tg_icon(Icons.ACCOUNT, "👤")
ICON_ID = tg_icon(Icons.USER_ID, "🆔")
ICON_VIP = tg_icon(Icons.VIP, "💎")
ICON_CROWN = tg_icon(Icons.CROWN, "👑")
ICON_LIGHTNING = tg_icon(Icons.LIGHTNING, "⚡")
ICON_FIRE = tg_icon(Icons.FIRE, "🔥")
ICON_SPARKLES = tg_icon(Icons.SPARKLES, "✨")
ICON_STAR = tg_icon(Icons.STAR, "🌟")
ICON_CHANNEL = tg_icon(Icons.CHANNEL, "📢")
ICON_SUPPORT = tg_icon(Icons.SUPPORT, "🎧")
ICON_CALL = tg_icon(Icons.CALL, "🎧")
ICON_CHECK = tg_icon(Icons.CHECK, "✅")
ICON_CROSS = tg_icon(Icons.CROSS, "❌")
ICON_WARNING = tg_icon(Icons.WARNING, "⚠️")
ICON_TIMER = tg_icon(Icons.TIMER, "⌛")
ICON_ROCKET = tg_icon(Icons.ROCKET, "🚀")
ICON_SHIELD = tg_icon(Icons.SHIELD, "🛡️")
ICON_LOCK = tg_icon(Icons.LOCK, "🔒")
ICON_KEY = tg_icon(Icons.KEY, "🔐")
ICON_STATS = tg_icon(Icons.STATS, "📊")
ICON_NOTE = tg_icon(Icons.NOTE, "📝")
ICON_GLOBE = tg_icon(Icons.GLOBE, "🌐")
ICON_ROBOT = tg_icon(Icons.ROBOT, "🤖")
ICON_COMPUTER = tg_icon(Icons.COMPUTER, "💻")
ICON_MAIL = tg_icon(Icons.MAIL, "✉️")
ICON_RESELLER = tg_icon(Icons.RESELLER, "💼")
ICON_PLUS = tg_icon(Icons.PLUS, "➕")
ICON_MINUS = tg_icon(Icons.MINUS, "➖")
ICON_BACK = tg_icon(Icons.BACK, "🔙")
ICON_NEXT = tg_icon(Icons.NEXT, "➡️")
ICON_CLOSE = tg_icon(Icons.CLOSE, "❌")
ICON_BINANCE = tg_icon(Icons.BINANCE, "🟡")
ICON_BYBIT = tg_icon(Icons.BYBIT, "⚫")
ICON_BKASH = tg_icon(Icons.BKASH, "🌸")
ICON_NAGAD = tg_icon(Icons.NAGAD, "🔴")
ICON_ROCKET_PURPLE = tg_icon(Icons.ROCKET_METHOD, "🟣")

ICON_CONFIRM = tg_icon(Icons.CONFIRM, "✅")


def get_method_icon(method: dict[str, Any]) -> str:
    """Render the custom emoji HTML tag for a deposit method matching its keyboard icon."""
    custom_emoji_id = method.get("custom_emoji_id")
    name = (method.get("name") or "").lower()
    auto_verify = method.get("auto_verify")

    if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
        emoji_id = str(custom_emoji_id).strip()
        fallback = (
            "🌸" if "bkash" in name
            else ("🔴" if "nagad" in name
            else ("🟣" if "rocket" in name
            else ("🟡" if "binance" in name or auto_verify == "binance_pay"
            else "💳")))
        )
        return tg_icon(emoji_id, fallback)

    if auto_verify == "binance_pay" or "binance" in name:
        return ICON_BINANCE
    if "bkash" in name:
        return ICON_BKASH
    if "nagad" in name:
        return ICON_NAGAD
    if "rocket" in name:
        return ICON_ROCKET_PURPLE
    return ICON_DEPOSIT
