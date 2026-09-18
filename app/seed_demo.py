"""Fill an empty test database with sample products, stock, payment methods and a funded admin wallet.

Run inside the app container: ``python -m app.seed_demo``. It refuses to touch a database that already
has products or categories, and everything is added in one transaction.
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg

from app.core.config import get_settings
from app.db import Database

SEED_SQL = """
WITH cats AS (
  INSERT INTO categories (name, icon, sort_order) VALUES
    ('VPN', '🛡️', 1), ('AI Tools', '🤖', 2), ('Streaming', '🎬', 3)
  RETURNING id, name
)
INSERT INTO products (category_id, title, description, price, icon, duration_label, sort_order)
SELECT c.id, p.title, p.description, p.price, p.icon, p.duration, p.sort
FROM (VALUES
  ('VPN',       'NordVPN 30 Days',         'Premium NordVPN account',     200, '🛡️', '30 Days', 1),
  ('VPN',       'ExpressVPN 7 Days',       'Fast ExpressVPN access',       60, '🛡️', '7 Days',  2),
  ('VPN',       'Surfshark 30 Days',       'Unlimited devices',           180, '🛡️', '30 Days', 3),
  ('AI Tools',  'ChatGPT Plus 1 Month',    'Shared ChatGPT Plus seat',    650, '🤖', '1 Month', 4),
  ('AI Tools',  'Gemini Advanced 1 Month', 'Google Gemini Advanced',      300, '💎', '1 Month', 5),
  ('Streaming', 'Netflix Premium 1 Month', '4K UHD shared profile',       350, '🎬', '1 Month', 6),
  ('Streaming', 'YouTube Premium 1 Month', 'Ad-free YouTube, 5 seats',    120, '▶️', '1 Month', 7),
  ('Streaming', 'CapCut Pro 7 Days',       'Out-of-stock test item',       50, '🎬', '7 Days',  8)
) AS p(cat, title, description, price, icon, duration, sort)
JOIN cats c ON c.name = p.cat;

INSERT INTO inventory_items (product_id, content)
SELECT p.id, format(E'Email: test%s_%s@example.com\\nPassword: Test#%s%s', p.id, n, p.id, n)
FROM products p CROSS JOIN generate_series(1, 3) AS n
WHERE p.title IN ('NordVPN 30 Days', 'ExpressVPN 7 Days', 'Surfshark 30 Days',
                  'ChatGPT Plus 1 Month', 'Gemini Advanced 1 Month', 'Netflix Premium 1 Month');

-- One account shared by five customers.
INSERT INTO inventory_items (product_id, content, max_uses)
SELECT id, E'Email: family@example.com\\nPassword: Shared#123', 5
FROM products WHERE title = 'YouTube Premium 1 Month';

INSERT INTO deposit_methods (name, account_info, instructions, min_deposit, rate_to_currency, sort_order, auto_verify) VALUES
  ('bKash', '01700000000', 'Send Money to this number, then send the TrxID.', 50, 1, 1, 'none'),
  ('Nagad', '01800000000', 'Send Money to this number, then send the TrxID.', 50, 1, 2, 'none');

INSERT INTO update_channels (title, url, sort_order) VALUES
  ('Updates Channel', 'https://t.me/telegram', 1),
  ('Official Community', 'https://t.me/telegram', 2);

INSERT INTO bot_settings (key, value) VALUES
  ('store_name', 'BM Digital (Test)'), ('currency', 'BDT'), ('currency_symbol', '৳')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
"""

ADMIN_BALANCE = 5000


async def seed(conn: asyncpg.Connection, admin_tg_id: int) -> None:
    await conn.execute(SEED_SQL)
    if admin_tg_id:
        await conn.execute(
            "INSERT INTO users (tg_user_id, first_name, balance) VALUES ($1, 'Admin', $2) "
            "ON CONFLICT (tg_user_id) DO UPDATE SET balance = EXCLUDED.balance",
            admin_tg_id,
            ADMIN_BALANCE,
        )


async def main() -> int:
    config = get_settings()
    db = Database(config.database_url, statement_cache_size=config.db_statement_cache_size)
    try:
        async with db.transaction() as conn:
            if await conn.fetchval("SELECT EXISTS (SELECT 1 FROM products) OR EXISTS (SELECT 1 FROM categories)"):
                print("The database already has products or categories; nothing was added.")
                return 1
            await seed(conn, config.admin_tg_id)
            counts = await conn.fetchrow(
                "SELECT (SELECT count(*) FROM products) AS products, (SELECT count(*) FROM inventory_items) AS stock_rows, "
                "(SELECT count(*) FROM deposit_methods) AS deposit_methods"
            )
        print(
            f"Added {counts['products']} products, {counts['stock_rows']} stock rows and "
            f"{counts['deposit_methods']} deposit methods."
        )
        if config.admin_tg_id:
            print(f"Wallet of Telegram user {config.admin_tg_id} set to {ADMIN_BALANCE}.")
        return 0
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
