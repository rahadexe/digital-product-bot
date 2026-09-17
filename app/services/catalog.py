"""Categories and products. The bot, the Mini App and the admin console read the same catalog."""

from __future__ import annotations

import time
from typing import Any

import asyncpg

from app.core.money import money
from app.db import Database, affected
from app.services.audit import record
from app.services.errors import InvalidInputError

# Free seats in local stock (an account for seven customers counts seven) plus, for supplier-linked
# products, the supplier's last reported stock.
STOCK_SQL = """(
    (SELECT COALESCE(SUM(i.max_uses - i.uses), 0) FROM inventory_items i WHERE i.product_id = p.id AND i.status = 'available' AND (i.expires_at IS NULL OR i.expires_at > NOW()))
    + CASE WHEN p.supplier_product_id IS NULL THEN 0 ELSE COALESCE(p.supplier_stock, 0) END
)"""
LISTING_SQL = (
    f"SELECT p.*, c.name AS category_name, {STOCK_SQL} AS stock FROM products p LEFT JOIN categories c ON c.id = p.category_id"
)

PRODUCT_FIELDS = ("category_id", "title", "description", "price", "icon", "duration_label", "sort_order", "is_active")


class CatalogService:
    CACHE_SECONDS = 30.0

    def __init__(self, db: Database):
        self.db = db
        self._active_categories: tuple[float, list[dict[str, Any]]] | None = None

    @staticmethod
    async def _require_category(conn: asyncpg.Connection, category_id: int | None) -> None:
        if category_id is not None and not await conn.fetchval("SELECT 1 FROM categories WHERE id = $1", category_id):
            raise InvalidInputError("The selected category does not exist.")

    async def categories(self, active_only: bool = True) -> list[dict[str, Any]]:
        now = time.monotonic()
        cached = self._active_categories
        if active_only and cached and now - cached[0] < self.CACHE_SECONDS:
            return [dict(row) for row in cached[1]]
        query = "SELECT * FROM categories" + (" WHERE is_active = 1" if active_only else "") + " ORDER BY sort_order, id"
        async with self.db.connect() as conn:
            rows = [dict(row) for row in await conn.fetch(query)]
        if active_only:
            self._active_categories = (now, rows)
        return [dict(row) for row in rows]

    async def create_category(self, name: str, icon: str = "📦", sort_order: int = 0) -> int:
        async with self.db.transaction() as conn:
            category_id = await conn.fetchval(
                "INSERT INTO categories (name, icon, sort_order) VALUES ($1, $2, $3) RETURNING id",
                name,
                icon,
                sort_order,
            )
            await record(conn, "category_created", f"Category #{category_id}: {name}")
        self._active_categories = None
        return category_id

    async def update_category(self, category_id: int, *, name: str, icon: str, sort_order: int, is_active: int) -> bool:
        async with self.db.transaction() as conn:
            status = await conn.execute(
                "UPDATE categories SET name = $1, icon = $2, sort_order = $3, is_active = $4 WHERE id = $5",
                name,
                icon,
                sort_order,
                is_active,
                category_id,
            )
            if affected(status):
                await record(conn, "category_updated", f"Category #{category_id}: {name}")
        self._active_categories = None
        return bool(affected(status))

    async def delete_category(self, category_id: int) -> None:
        async with self.db.transaction() as conn:
            if affected(await conn.execute("DELETE FROM categories WHERE id = $1", category_id)):
                await record(conn, "category_deleted", f"Category #{category_id}")
        self._active_categories = None

    async def products(
        self,
        category_id: int | None = None,
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
        *,
        in_stock_first: bool = False,
    ) -> list[dict[str, Any]]:
        """Products in admin order; customer listings pass ``in_stock_first`` so buyable items lead."""
        where, params = "", []
        if category_id is not None:
            params.append(category_id)
            where += f" AND p.category_id = ${len(params)}"
        if active_only:
            where += " AND p.is_active = 1"
        order = "(stock > 0) DESC, sort_order, id" if in_stock_first else "sort_order, id"
        query = (
            f"SELECT * FROM ({LISTING_SQL} WHERE 1=1{where}) AS listing "
            f"ORDER BY {order} LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        )
        async with self.db.connect() as conn:
            return [dict(row) for row in await conn.fetch(query, *params, limit, offset)]

    async def product(self, product_id: int) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow(f"{LISTING_SQL} WHERE p.id = $1", product_id)
            return dict(row) if row else None

    async def create_product(
        self,
        category_id: int | None,
        title: str,
        description: str = "",
        price: float = 0.0,
        icon: str = "⚡",
        duration_label: str = "",
        sort_order: int = 0,
        is_active: int = 1,
    ) -> int:
        price = money(price, positive=True)
        async with self.db.transaction() as conn:
            await self._require_category(conn, category_id)
            product_id = await conn.fetchval(
                """
                INSERT INTO products (category_id, title, description, price, icon, duration_label, sort_order, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id
                """,
                category_id,
                title,
                description,
                price,
                icon,
                duration_label,
                sort_order,
                is_active,
            )
            await record(conn, "product_created", f"Product #{product_id}: {title} at {price:.2f}")
        return product_id

    async def update_product(self, product_id: int, **fields: Any) -> float | None:
        """Apply the given fields. Returns the previous price, or None when the product does not exist."""
        updates = {key: value for key, value in fields.items() if key in PRODUCT_FIELDS}
        if "price" in updates:
            updates["price"] = money(updates["price"], positive=True)
        async with self.db.transaction() as conn:
            current = await conn.fetchrow("SELECT price FROM products WHERE id = $1 FOR UPDATE", product_id)
            if not current:
                return None
            if not updates:
                return current["price"]
            if "category_id" in updates:
                await self._require_category(conn, updates["category_id"])
            columns = ", ".join(f"{key} = ${index}" for index, key in enumerate(updates, start=1))
            await conn.execute(f"UPDATE products SET {columns} WHERE id = ${len(updates) + 1}", *updates.values(), product_id)
            details = f"Product #{product_id}: {', '.join(sorted(updates))}"
            if "price" in updates and updates["price"] != current["price"]:
                details += f"; price {current['price']:.2f} -> {updates['price']:.2f}"
            await record(conn, "product_updated", details)
        return current["price"]

    async def archive_product(self, product_id: int) -> None:
        async with self.db.transaction() as conn:
            if affected(await conn.execute("UPDATE products SET is_active = 0 WHERE id = $1", product_id)):
                await record(conn, "product_archived", f"Product #{product_id}")
