import asyncio

from app.bot.icons import Icons
from app.core.config import get_settings
from app.db.database import Database


async def update_db():
    db = Database(get_settings().database_url)
    async with db.transaction() as conn:
        await conn.execute("UPDATE categories SET custom_emoji_id = $1 WHERE name = 'VPN'", Icons.SHIELD)
        await conn.execute("UPDATE categories SET custom_emoji_id = $1 WHERE name = 'Proxy Shop'", Icons.GLOBE)
        await conn.execute("UPDATE categories SET custom_emoji_id = $1 WHERE name = 'AI Tools'", Icons.ROBOT)
        await conn.execute("UPDATE categories SET custom_emoji_id = $1 WHERE name = 'Premium Subscriptions'", Icons.VIP)
        
        await conn.execute("UPDATE products SET custom_emoji_id = $1 WHERE LOWER(title) LIKE '%vpn%'", Icons.SHIELD)
        await conn.execute("UPDATE products SET custom_emoji_id = $1 WHERE LOWER(title) LIKE '%proxy%'", Icons.GLOBE)
        await conn.execute("UPDATE products SET custom_emoji_id = $1 WHERE custom_emoji_id IS NULL", Icons.VIP)
        
        cats = await conn.fetch("SELECT id, name, custom_emoji_id FROM categories")
        print("Updated categories:")
        for c in cats:
            print(" ", dict(c))
        prods = await conn.fetch("SELECT id, title, custom_emoji_id FROM products LIMIT 10")
        print("Updated products:")
        for p in prods:
            print(" ", dict(p))

    await db.close()

if __name__ == "__main__":
    asyncio.run(update_db())
