import asyncio

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

from app.bot.icons import ICON_LIGHTNING, ICON_MONEY, ICON_NOTE, ICON_TIMER, Icons
from app.core.config import get_settings


async def main():
    load_dotenv()
    cfg = get_settings()
    bot = Bot(cfg.bot_token)
    text = (
        "1️⃣6️⃣ <b>[CUSTOMER NOTIFICATION] Instant Payment Invoice Generated</b>\n\n"
        f"{ICON_NOTE} <b>Payment Invoice #INV-1048</b>\n\n"
        f"{ICON_MONEY} <b>Payable Amount:</b> <code>1000.00 ৳ ($8.00)</code>\n"
        f"{ICON_LIGHTNING} <b>Method:</b> Instant Auto Gateway\n"
        f"{ICON_TIMER} <b>Status:</b> Waiting for Payment\n\n"
        "🇬🇧 Tap the <b>Pay</b> button below to open the payment page. You can complete payment using any preferred method (bKash, Nagad, Rocket, Cards), and your balance will be added automatically.\n\n"
        "🇧🇩 নিচের <b>Pay</b> বাটনে ট্যাপ করলে পেমেন্ট পেজে নিয়ে যাবে। সেখান থেকে আপনার পছন্দ অনুযায়ী যেকোনো মেথডে (bKash, Nagad, Rocket ইত্যাদি) পেমেন্ট সম্পন্ন করতে পারবেন এবং অটোমেটিক ব্যালেন্স যুক্ত হয়ে যাবে।"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Pay ৳1000.00", url="https://zinipay.com", style="success", icon_custom_emoji_id=Icons.DEPOSIT)
        ],
        [
            InlineKeyboardButton(text="I've Paid", callback_data="inst_chk_sample", style="primary", icon_custom_emoji_id=Icons.CHECK)
        ],
        [
            InlineKeyboardButton(text="Back", callback_data="open_deposit", style="danger", icon_custom_emoji_id=Icons.BACK)
        ]
    ])
    await bot.send_message(6775546602, text, reply_markup=kb, parse_mode="HTML")
    print("Polished Sample 16 sent successfully!")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
