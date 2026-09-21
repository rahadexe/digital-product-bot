import asyncio

from app.core.config import get_settings
from app.db.database import Database


async def add_mailbox():
    db = Database(get_settings().database_url)
    async with db.transaction() as conn:
        # Check if already exists
        existing = await conn.fetchrow("SELECT id FROM categories WHERE LOWER(name) = 'mail box'")
        if existing:
            await conn.execute("UPDATE categories SET custom_emoji_id = '5253742260054409879', is_pinned = 1 WHERE id = $1", existing["id"])
            cat_id = existing["id"]
        else:
            cat_id = await conn.fetchval(
                "INSERT INTO categories (name, icon, is_pinned, custom_emoji_id, is_active, sort_order) "
                "VALUES ('Mail Box', '✉️', 1, '5253742260054409879', 1, 4) RETURNING id"
            )
        print("Mail Box Category ID:", cat_id)

    await db.close()

if __name__ == "__main__":
    asyncio.run(add_mailbox())
