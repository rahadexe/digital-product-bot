import asyncio

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BINANCE,
    ICON_DEPOSIT,
    ICON_ID,
    ICON_KEY,
    ICON_TIMER,
    ICON_WARNING,
    Icons,
)
from app.core.config import get_settings

ADMIN_CHAT_ID = 6775546602

async def main():
    load_dotenv()
    cfg = get_settings()
    bot = Bot(cfg.bot_token)
    console_url = cfg.console_url or "http://localhost:3000"

    # 1. Admin Alert for Binance Server Error
    admin_text = (
        "🔟 <b>[ADMIN ALERT] Binance Gateway Server Error / Timeout</b>\n\n"
        f"{ICON_WARNING} <b>Binance Gateway Needs Review</b>\n\n"
        f"{ICON_ACCOUNT} <b>Customer:</b> @JohnDoe\n"
        f"{ICON_ID} <b>Customer ID:</b> <code>589234120</code>\n"
        f"{ICON_DEPOSIT} <b>Method:</b> Binance Pay\n"
        f"{ICON_KEY} <b>Reference:</b> <code>BIN_PAY_89231490</code>\n"
        f"{ICON_WARNING} <b>Reason:</b> Binance API connection timeout (504 Gateway Timeout)\n\n"
        "<i>Nothing was credited yet. The background worker is automatically retrying.</i>"
    )
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Open in Console", url=f"{console_url}/#deposits", icon_custom_emoji_id=Icons.DEPOSIT)
        ]
    ])

    await bot.send_message(ADMIN_CHAT_ID, admin_text, reply_markup=admin_kb, parse_mode="HTML")
    await asyncio.sleep(1)

    # 2. Customer Notification / Screen during Verification / Delay
    customer_text = (
        "⏳ <b>[CUSTOMER SCREEN] Binance Verification in Progress / Delay</b>\n\n"
        f"{ICON_TIMER} <b>Payment Verification in Progress...</b>\n\n"
        f"{ICON_KEY} <b>Reference:</b> <code>BIN_PAY_89231490</code>\n"
        f"{ICON_BINANCE} <b>Expected:</b> <code>10.00 USDT</code>\n\n"
        "Searching Binance for your transfer. If you just sent it, please allow 1–2 minutes for blockchain/API confirmation.\n\n"
        "<i>Your balance will be credited automatically once confirmed.</i>"
    )
    customer_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Check Status", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.TIMER),
            InlineKeyboardButton(text="Contact Support", url="https://t.me/PremiumHavenSupport", icon_custom_emoji_id=Icons.SUPPORT),
        ],
        [
            InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
        ]
    ])

    await bot.send_message(ADMIN_CHAT_ID, customer_text, reply_markup=customer_kb, parse_mode="HTML")
    print("Binance server error samples sent successfully!")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
