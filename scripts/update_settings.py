import asyncio

from app.core.config import get_settings
from app.db.database import Database


async def update_name():
    db = Database(get_settings().database_url)
    async with db.transaction() as conn:
        await conn.execute("UPDATE bot_settings SET value = $1 WHERE key = $2", "Premium Haven", "store_name")
        print("Store name updated to Premium Haven")
    await db.close()

if __name__ == "__main__":
    asyncio.run(update_name())
