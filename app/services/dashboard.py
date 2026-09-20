"""Admin overview metrics."""

from __future__ import annotations

from typing import Any

from app.db import Database
from app.services.catalog import STOCK_SQL

TOTALS_SQL = """
SELECT
    (SELECT COUNT(*) FROM users) AS total_users,
    (SELECT COUNT(*) FROM orders WHERE status = 'completed') AS total_orders,
    (SELECT COALESCE(SUM(price), 0) FROM orders WHERE status = 'completed') AS total_revenue,
    (SELECT COUNT(*) FROM orders WHERE status = 'completed' AND fulfillment = 'delivered') AS delivered_orders,
    (SELECT COALESCE(SUM(max_uses - uses), 0) FROM inventory_items WHERE status = 'available'
       AND (expires_at IS NULL OR expires_at > now())) AS available_stock,
    (SELECT COUNT(*) FROM deposits WHERE status = 'pending') AS pending_deposits,
    (SELECT COUNT(*) FROM orders WHERE status = 'completed' AND fulfillment = 'waiting') AS waiting_orders
"""
RECENT_ORDERS_SQL = """
SELECT o.id, o.tg_user_id, o.product_title, o.price, o.status, o.fulfillment, o.source, o.created_at,
       u.username, u.first_name, u.last_name
FROM orders o
LEFT JOIN users u ON u.id = o.user_id
ORDER BY o.id DESC LIMIT 8
"""
LOW_STOCK_SQL = (
    f"SELECT p.id, p.title, p.price, {STOCK_SQL} AS stock FROM products p WHERE p.is_active = 1 ORDER BY stock, p.id LIMIT 6"
)

CHART_SQL = """
WITH days AS (
    SELECT generate_series(
        CURRENT_DATE - INTERVAL '13 days',
        CURRENT_DATE,
        '1 day'::interval
    )::date AS day
)
SELECT 
    to_char(d.day, 'YYYY-MM-DD') AS date,
    to_char(d.day, 'DD Mon') AS label,
    COALESCE(SUM(o.price), 0)::float AS revenue,
    COUNT(o.id)::int AS orders
FROM days d
LEFT JOIN orders o ON o.created_at >= d.day AND o.created_at < d.day + interval '1 day' AND o.status = 'completed'
GROUP BY d.day
ORDER BY d.day ASC
"""


class DashboardService:
    def __init__(self, db: Database):
        self.db = db

    async def stats(self) -> dict[str, Any]:
        # All four reads share one connection so the dashboard never saturates the pool.
        async with self.db.connect() as conn:
            totals = [dict(r) for r in await conn.fetch(TOTALS_SQL)]
            recent_orders = [dict(r) for r in await conn.fetch(RECENT_ORDERS_SQL)]
            stock_summary = [dict(r) for r in await conn.fetch(LOW_STOCK_SQL)]
            chart_data = [dict(r) for r in await conn.fetch(CHART_SQL)]
        return {
            **totals[0],
            "total_revenue": round(totals[0]["total_revenue"], 2),
            "recent_orders": recent_orders,
            "stock_summary": stock_summary,
            "chart_data": chart_data,
        }
