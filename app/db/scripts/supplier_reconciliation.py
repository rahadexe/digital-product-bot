"""Read-only recovery report: python -m app.db.scripts.supplier_reconciliation.

Lists stalled/uncertain attempts and accepted attempts without a committed order.
Never sends an upstream purchase, changes a wallet, or prints delivered credentials.
"""

import asyncio
import json

from app.core.config import get_settings
from app.db import Database


async def unresolved_attempts(db: Database) -> list[dict]:
    async with db.connect() as conn:
        rows = await conn.fetch("""
            SELECT a.request_key, a.customer_request_id, a.tg_user_id,
                   a.local_product_id, a.supplier_code, a.product_id AS upstream_product_id,
                   a.quantity, a.status, a.updated_at, o.id AS local_order_id,
                   a.response->>'order_id' AS supplier_order_id
            FROM supplier_order_attempts a
            LEFT JOIN orders o ON o.tg_user_id=a.tg_user_id AND o.request_id=a.customer_request_id
            WHERE a.updated_at < now() - interval '5 minutes'
              AND (a.status IN ('sending','unknown') OR (a.status='accepted' AND o.id IS NULL))
            ORDER BY a.updated_at LIMIT 500
        """)
    return [dict(row) for row in rows]


async def main() -> None:
    config = get_settings()
    db = Database(config.database_url, max_size=2,
                  statement_cache_size=config.db_statement_cache_size)
    try:
        rows = await unresolved_attempts(db)
        print(json.dumps({'attempts': rows, 'limit': 500, 'possibly_truncated': len(rows) == 500},
                         default=str, indent=2))
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(main())
