import asyncio
from dotenv import load_dotenv

load_dotenv()
from aiogram import Bot
from app.bot.icons import ICON_CROSS
from app.core.config import get_settings

async def main():
    cfg = get_settings()
    bot = Bot(cfg.bot_token)
    text = (
        "1️⃣8️⃣ <b>[CUSTOMER NOTIFICATION] Deposit Cancelled</b>\n\n"
        f"{ICON_CROSS} <b>Deposit Cancelled</b>"
    )
    await bot.send_message(6775546602, text, parse_mode="HTML")
    print("Simplified Sample 18 sent successfully!")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
