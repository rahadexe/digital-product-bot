"""Local stock: credentials, keys and links delivered on purchase.

An item can be sold to more than one customer (an account with seven seats has ``max_uses`` 7). Each sale
takes the item used least, then the one used longest ago, so seats are handed out in turn.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import asyncpg

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.icons import Icons
from app.db import Database
from app.services.audit import record
from app.services.errors import InvalidInputError, NotFoundError
from app.services.notifications import Notifier

MAX_ITEMS_PER_UPLOAD = 5000
MAX_USES = 1000
# Another purchase may hold the only item with a free seat for a moment; wait for it instead of saying "sold out".
CLAIM_ATTEMPTS = 20
CLAIM_WAIT_SECONDS = 0.1


def _parse_datetime(dt: Any) -> datetime | None:
    if not dt:
        return None
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, str):
        s = dt.replace("Z", "+00:00").strip()
        if not s:
            return None
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None
    return None


class InventoryService:
    def __init__(self, db: Database, notifier: Notifier | None = None):
        self.db = db
        self.notifier = notifier

    async def add_stock(

        self, product_id: int, items: list[str], max_uses: int = 1, expires_at: Any = None
    ) -> dict[str, int]:
        """Adds each line once. A line already in stock for this product is skipped, so one key is never sold twice by mistake."""
        if not 1 <= max_uses <= MAX_USES:
            raise InvalidInputError(f"Each item can go to 1 to {MAX_USES} customers.")
        clean = list(dict.fromkeys(item.strip() for item in items if item.strip()))
        if len(clean) > MAX_ITEMS_PER_UPLOAD:
            raise InvalidInputError(f"Upload at most {MAX_ITEMS_PER_UPLOAD} items at a time.")
        if not clean:
            return {"added": 0, "skipped": 0}
        async with self.db.transaction() as conn:
            if not await conn.fetchval("SELECT 1 FROM products WHERE id = $1 FOR UPDATE", product_id):
                raise NotFoundError("Product not found.")
            existing = {
                row["content"]
                for row in await conn.fetch(
                    "SELECT content FROM inventory_items WHERE product_id = $1 AND content = ANY($2::text[])", product_id, clean
                )
            }
            fresh = [item for item in clean if item not in existing]
            if fresh:
                exp_dt = _parse_datetime(expires_at)
                await conn.executemany(
                    "INSERT INTO inventory_items (product_id, content, max_uses, expires_at) VALUES ($1, $2, $3, $4)",
                    [(product_id, item, max_uses, exp_dt) for item in fresh],
                )
                seats = f", {max_uses} customers each" if max_uses > 1 else ""
                await record(conn, "bulk_stock_added", f"Added {len(fresh)} stock items to Product ID {product_id}{seats}")
                if self.notifier:
                    subscribers = await conn.fetch(
                        "SELECT tg_user_id FROM restock_notifications WHERE product_id = $1", product_id
                    )
                    if subscribers:
                        prod = await conn.fetchrow("SELECT title FROM products WHERE id = $1", product_id)
                        title = prod["title"] if prod else "Product"
                        for s in subscribers:
                            uid = s["tg_user_id"]
                            kb = InlineKeyboardMarkup(
                                inline_keyboard=[[
                                    InlineKeyboardButton(
                                        text="Buy Now",
                                        callback_data=f"prod_{product_id}",
                                    )
                                ]]
                            )
                            self.notifier.in_background(
                                self.notifier.send(
                                    uid,
                                    f"🔔 <b>Product Restocked</b>\n\n"
                                    f"<b>{title}</b> is back in stock!\n"
                                    f"Available for purchase now.",
                                    keyboard=kb,
                                )
                            )
                        await conn.execute("DELETE FROM restock_notifications WHERE product_id = $1", product_id)
        skipped = len([item for item in items if item.strip()]) - len(fresh)
        return {"added": len(fresh), "skipped": skipped}


    async def items(
        self, product_id: int | None = None, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        where, params = "", []
        if product_id:
            params.append(product_id)
            where += f" AND i.product_id = ${len(params)}"
        if status == "available":
            where += " AND i.status = 'available' AND (i.expires_at IS NULL OR i.expires_at > NOW())"
        elif status == "expired":
            where += " AND i.status = 'available' AND i.expires_at IS NOT NULL AND i.expires_at <= NOW()"
        elif status == "sold":
            where += " AND i.status = 'sold'"
        elif status:
            params.append(status)
            where += f" AND i.status = ${len(params)}"

        async with self.db.connect() as conn:
            rows = await conn.fetch(
                f"""
                SELECT i.*, p.title AS product_title, COUNT(*) OVER () AS total_count
                FROM inventory_items i LEFT JOIN products p ON p.id = i.product_id
                WHERE 1=1{where}
                ORDER BY i.id DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
                *params,
                limit,
                offset,
            )
            total = rows[0]["total_count"] if rows else 0
            summary_row = await conn.fetchrow(
                """
                SELECT 
                    COALESCE(SUM(CASE WHEN status = 'available' AND (expires_at IS NULL OR expires_at > NOW()) THEN (max_uses - uses) ELSE 0 END), 0)::int AS available_units,
                    COALESCE(SUM(uses), 0)::int AS sold_units,
                    COALESCE(SUM(CASE WHEN status = 'available' AND expires_at IS NOT NULL AND expires_at <= NOW() THEN (max_uses - uses) ELSE 0 END), 0)::int AS expired_units,
                    COUNT(DISTINCT CASE WHEN status = 'available' AND (expires_at IS NULL OR expires_at > NOW()) THEN product_id END)::int AS in_stock_products
                FROM inventory_items
                """
            )
        summary = {
            "available_units": int(summary_row["available_units"] or 0) if summary_row else 0,
            "sold_units": int(summary_row["sold_units"] or 0) if summary_row else 0,
            "expired_units": int(summary_row["expired_units"] or 0) if summary_row else 0,
            "in_stock_products": int(summary_row["in_stock_products"] or 0) if summary_row else 0,
        }
        return [{key: value for key, value in row.items() if key != "total_count"} for row in rows], total, summary

    async def update_item(self, item_id: int, content: str, max_uses: int, expires_at: Any = None) -> dict[str, Any]:
        """Changes what future buyers get. Orders already made keep the copy they received."""
        content = content.strip()
        if not content:
            raise InvalidInputError("The item cannot be empty.")
        if not 1 <= max_uses <= MAX_USES:
            raise InvalidInputError(f"Each item can go to 1 to {MAX_USES} customers.")
        async with self.db.transaction() as conn:
            product_id = await conn.fetchval("SELECT product_id FROM inventory_items WHERE id = $1", item_id)
            if product_id is not None:
                await conn.fetchval("SELECT id FROM products WHERE id = $1 FOR UPDATE", product_id)
            item = await conn.fetchrow("SELECT * FROM inventory_items WHERE id = $1 FOR UPDATE", item_id)
            if not item:
                raise NotFoundError("Stock item not found.")
            if max_uses < item["uses"]:
                raise InvalidInputError(f"It has already gone to {item['uses']} customers.")
            duplicate = await conn.fetchval(
                "SELECT 1 FROM inventory_items WHERE product_id = $1 AND content = $2 AND id <> $3",
                item["product_id"],
                content,
                item_id,
            )
            if duplicate:
                raise InvalidInputError("This product already has that item in stock.")
            exp_dt = _parse_datetime(expires_at)
            row = await conn.fetchrow(
                """
                UPDATE inventory_items SET content = $1, max_uses = $2, expires_at = $3,
                       status = CASE WHEN uses >= $2 THEN 'sold' ELSE 'available' END
                WHERE id = $4 RETURNING *
                """,
                content,
                max_uses,
                exp_dt,
                item_id,
            )
            await record(conn, "stock_item_edited", f"Inventory item #{item_id}: {max_uses} customer(s)")
        return dict(row)

    async def remove_available(self, item_id: int) -> bool:
        """An unused item is deleted. One that has already gone to someone is only taken off sale, so its orders keep their link."""
        async with self.db.transaction() as conn:
            item = await conn.fetchrow("SELECT * FROM inventory_items WHERE id = $1 AND status = 'available' FOR UPDATE", item_id)
            if not item:
                return False
            if item["uses"] == 0:
                await conn.execute("DELETE FROM inventory_items WHERE id = $1", item_id)
                await record(conn, "stock_item_removed", f"Inventory item #{item_id}")
            else:
                await conn.execute("UPDATE inventory_items SET status = 'sold' WHERE id = $1", item_id)
                await record(conn, "stock_item_retired", f"Inventory item #{item_id} taken off sale after {item['uses']} use(s)")
        return True

    @staticmethod
    async def claim_seats(conn: asyncpg.Connection, product_id: int, tg_user_id: int, count: int = 1) -> list[asyncpg.Record] | None:
        """
        Lock the next `count` available items inside the caller's transaction.
        If fewer than `count` items are available, returns None.
        """
        if count <= 0:
            return None
        for _ in range(CLAIM_ATTEMPTS):
            items = await conn.fetch(
                """
                SELECT i.* FROM inventory_items i
                WHERE i.product_id = $1 AND i.status = 'available' AND i.uses < i.max_uses
                  AND (i.expires_at IS NULL OR i.expires_at > NOW())
                ORDER BY EXISTS (SELECT 1 FROM order_inventory_allocations a JOIN orders o ON o.id=a.order_id
                                 WHERE a.inventory_item_id = i.id AND o.tg_user_id = $2),
                         i.uses, i.last_used_at NULLS FIRST, i.id
                LIMIT $3 FOR UPDATE OF i SKIP LOCKED
                """,
                product_id,
                tg_user_id,
                count,
            )
            if sum(item['max_uses'] - item['uses'] for item in items) >= count:
                # Prefer different credentials, then allocate additional shared seats.
                claimed = list(items[:count])
                for item in items:
                    extra = min(count - len(claimed), item['max_uses'] - item['uses'] - 1)
                    claimed.extend([item] * max(0, extra))
                return claimed
            # Check if there are enough items at all
            total_available = await conn.fetchval(
                """
                SELECT COALESCE(SUM(max_uses - uses),0) FROM inventory_items
                WHERE product_id = $1 AND status = 'available' AND uses < max_uses
                  AND (expires_at IS NULL OR expires_at > NOW())
                """,
                product_id,
            )
            if (total_available or 0) < count:
                return None
            await asyncio.sleep(CLAIM_WAIT_SECONDS)
        return None

    @staticmethod
    async def claim_seat(conn: asyncpg.Connection, product_id: int, tg_user_id: int) -> asyncpg.Record | None:
        """
        Lock the next item with a free seat inside the caller's transaction, or return None when there is none.
        Items this customer already received come last, so buying twice gets a different account when there is one.
        """
        for _ in range(CLAIM_ATTEMPTS):
            item = await conn.fetchrow(
                """
                SELECT i.* FROM inventory_items i
                WHERE i.product_id = $1 AND i.status = 'available' AND i.uses < i.max_uses
                  AND (i.expires_at IS NULL OR i.expires_at > NOW())
                ORDER BY EXISTS (SELECT 1 FROM orders o WHERE o.inventory_item_id = i.id AND o.tg_user_id = $2),
                         i.uses, i.last_used_at NULLS FIRST, i.id
                LIMIT 1 FOR UPDATE OF i SKIP LOCKED
                """,
                product_id,
                tg_user_id,
            )
            if item:
                return item
            # Nothing unlocked: either the stock is gone, or another purchase is holding the last free seat.
            held = await conn.fetchval(
                "SELECT 1 FROM inventory_items WHERE product_id = $1 AND status = 'available' AND uses < max_uses AND (expires_at IS NULL OR expires_at > NOW()) LIMIT 1",
                product_id,
            )
            if not held:
                return None
            await asyncio.sleep(CLAIM_WAIT_SECONDS)
        return None

    @staticmethod
    async def use_seat(conn: asyncpg.Connection, item_id: int, order_id: int) -> None:
        await conn.execute(
            """
            UPDATE inventory_items SET uses = uses + 1, last_used_at = now(),
                   status = CASE WHEN uses + 1 >= max_uses THEN 'sold' ELSE 'available' END,
                   order_id = COALESCE(order_id, $1), sold_at = COALESCE(sold_at, now())
            WHERE id = $2
            """,
            order_id,
            item_id,
        )
