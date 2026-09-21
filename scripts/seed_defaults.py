"""Seed default payment methods (bKash, Nagad, Binance) and sample products from screenshot."""

import asyncio

from app.core.config import get_settings
from app.db import Database


async def seed():
    settings = get_settings()
    db = Database(settings.database_url, statement_cache_size=settings.db_statement_cache_size)
    
    async with db.transaction() as conn:
        # 1. Deposit Methods
        methods_count = await conn.fetchval("SELECT count(*) FROM deposit_methods")
        if methods_count == 0:
            print("Seeding default deposit methods...")
            await conn.execute("""
                INSERT INTO deposit_methods (name, account_info, instructions, min_deposit, rate_to_currency, is_active, sort_order, auto_verify)
                VALUES 
                ('bKash', '01700000000', 'Send Money (Personal) to this bKash number. Then submit your Trx ID.', 50, 1.0, 1, 1, 'none'),
                ('Nagad', '01800000000', 'Send Money (Personal) to this Nagad number. Then submit your Trx ID.', 50, 1.0, 1, 2, 'none'),
                ('Binance Pay', '12345678', 'Send USDT via Binance Pay ID or Pay QR code. Then submit your Pay ID / TxID.', 100, 1.0, 1, 3, 'none')
            """)
            print("Deposit methods seeded.")
        else:
            print(f"Deposit methods already exist: {methods_count}")

        # 2. Categories
        cat_count = await conn.fetchval("SELECT count(*) FROM categories")
        if cat_count == 0:
            print("Seeding categories...")
            await conn.execute("""
                INSERT INTO categories (name, icon, sort_order, is_active)
                VALUES 
                ('VPN Services', '🛡️', 1, 1),
                ('AI Tools', '🤖', 2, 1),
                ('Premium Subscriptions', '🎬', 3, 1)
            """)
            print("Categories seeded.")
        
        vpn_cat_id = await conn.fetchval("SELECT id FROM categories WHERE name = 'VPN Services'")
        ai_cat_id = await conn.fetchval("SELECT id FROM categories WHERE name = 'AI Tools'")
        sub_cat_id = await conn.fetchval("SELECT id FROM categories WHERE name = 'Premium Subscriptions'")

        # 3. Products
        prod_count = await conn.fetchval("SELECT count(*) FROM products")
        if prod_count == 0:
            print("Seeding products matching Screenshot 2...")
            products_data = [
                (vpn_cat_id, "Proton VPN 30 Days", "High-speed secure Proton VPN account", 150.0, "🛡️", "30 Days", 1),
                (vpn_cat_id, "NORD VPN 7 Days", "Nord VPN premium access for 7 days", 40.0, "🛡️", "7 Days", 2),
                (vpn_cat_id, "NORD VPN 30 Days", "Nord VPN premium access for 30 days", 200.0, "🛡️", "30 Days", 3),
                (vpn_cat_id, "Nord VPN 90 Days", "Nord VPN premium access for 90 days", 600.0, "❌", "90 Days", 4),
                (vpn_cat_id, "Express VPN 3 Days", "Express VPN ultra-fast trial account", 15.0, "🛡️", "3 Days", 5),
                (vpn_cat_id, "Surfshark VPN 7 Days", "Surfshark unlimited devices 7 days", 30.0, "🛡️", "7 Days", 6),
                (vpn_cat_id, "HMA VPN 7 Days", "HMA HideMyAss VPN for 7 days", 30.0, "🛡️", "7 Days", 7),
                (vpn_cat_id, "Hma VPN, 30 Days", "HMA HideMyAss VPN for 30 days", 100.0, "🛡️", "30 Days", 8),
                (vpn_cat_id, "Bitdefender VPN 6 Days", "Bitdefender security VPN 6 days", 25.0, "🛡️", "6 Days", 9),
                (vpn_cat_id, "Cyberghost VPN 3 Days", "Cyberghost VPN 3 days access", 15.0, "🛡️", "3 Days", 10),
                (vpn_cat_id, "IP Vanish, 3 Days", "IPVanish VPN 3 days", 15.0, "🛡️", "3 Days", 11),
                (ai_cat_id, "Gemini 18 month", "Google Gemini Advanced 18 Months subscription", 250.0, "💎", "18 Months", 12),
                (sub_cat_id, "CAPCUT PRO 7 Days", "CapCut Pro video editor for 7 days", 50.0, "🎬", "7 Days", 13),
                (sub_cat_id, "CAPCUT PRO 30 Days", "CapCut Pro video editor for 30 days", 350.0, "🎬", "30 Days", 14),
            ]
            
            for cat_id, title, desc, price, icon, duration, sort in products_data:
                p_id = await conn.fetchval("""
                    INSERT INTO products (category_id, title, description, price, icon, duration_label, sort_order, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 1)
                    RETURNING id
                """, cat_id, title, desc, price, icon, duration, sort)
                
                # Add sample stock for items (except Nord 90 days and CapCut 7 days which are out of stock in screenshot)
                if "90 Days" not in title and "CAPCUT PRO 7 Days" not in title:
                    await conn.execute("""
                        INSERT INTO inventory_items (product_id, content, status)
                        VALUES ($1, $2, 'available'), ($1, $3, 'available')
                    """, p_id, f"Email: sample_{p_id}@pixelstore.com\nPassword: Pass{p_id}#123", f"License Key: KEY-{p_id}-XXXX-YYYY")
            
            print("Products and inventory items seeded successfully.")
        else:
            print(f"Products already exist: {prod_count}")

    await db.close()

if __name__ == "__main__":
    asyncio.run(seed())
