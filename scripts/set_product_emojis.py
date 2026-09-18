import asyncio
from app.db.database import Database
from app.core.config import get_settings

# Emoji map based on product titles and categories
EMOJIS = {
    "shield": "5190447043545438788",   # 🛡️ http_dxauniverse_by_fStikBot
    "globe": "5334590977837403844",    # 🌐 http_dxauniverse_by_fStikBot
    "lightning": "6084566793991494246",# ⚡ Raika_Games
    "mobile": "5355208818017999139",   # 📱 http_dxauniverse_by_fStikBot
    "rocket": "5352597830089347330",   # 🚀 http_dxauniverse_by_fStikBot
    "robot": "6084700423308975252",    # 🤖 Raika_Games
    "brain": "5278628322769654561",    # 🧠 G8yg_by_fStikBot
    "art": "5190751148704833975",      # 🎨 http_dxauniverse_by_fStikBot
    "code": "6251457360414382759",     # 💻 Raika_Games
    "sparkle": "5325547803936572038",  # ✨ NewsEmoji
    "popcorn": "5960740614810112719",  # 🍿 emoji1912
    "music": "5463107823946717464",    # 🎵 NewsEmoji
    "play": "5264919878082509254",     # ▶️ NewsEmoji
    "star": "6082362698379565136",     # ⭐ Raika_Games
    "diamond": "6084472820107057290",  # 💎 Raika_Games
    "movie": "5269514462297104098",    # 🎥 http_dxauniverse_by_fStikBot
}

import re

EMOJI_REGEX = re.compile(
    r"^[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u200d\ufe0f\s]+"
)

from aiogram import Bot

async def run():
    bot = Bot(get_settings().bot_token)
    packs = ['http_dxauniverse_by_fStikBot', 'Raika_Games', 'emoji1912', 'NewsEmoji', 'G8yg_by_fStikBot', 'Earning_ON_World_by_TgEmojis_bot']
    for p in packs:
        try:
            s = await bot.get_sticker_set(p)
            for st in s.stickers:
                if any(k in st.emoji for k in ['🔄', '🔁', '◀', '▶', '⬅', '➡️', '🔙', '❌', '🚫', '🔺', '🔻']):
                    print(f"Pack {p}: emoji={st.emoji} id={st.custom_emoji_id}")
        except Exception as e:
            print(f"Error {p}: {e}")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(run())
