"""Durable Telegram outbox for order receipts and broadcasts.

Rows are claimed with a lease, so an interrupted send is retried after restart.
Delivery is at least once: a crash right after Telegram accepts a message can
send it again, but never charges the customer again.
"""

from __future__ import annotations

import time
from datetime import datetime
from html import escape
from typing import Any

import asyncpg

from app.db import Database
from app.services.audit import record
from app.services.errors import NotFoundError

LEASE_SECONDS = 120


def waiting_notice(order: dict[str, Any]) -> str:
    order_id = order.get('order_id', order.get('id'))
    title = escape(order.get('product_title', 'Purchase'))
    return (
        f"⏳ <b>Order #{order_id}: {title}</b>\n\n"
        "Payment successful. Your item is being prepared and will be delivered here shortly."
    )


def receipt(order: dict[str, Any]) -> str:
    order_id = order.get('order_id', order.get('id'))
    title = escape(str(order.get('product_title', 'Purchase')))
    price_val = order.get('price', 0)
    symbol = order.get('currency_symbol', '৳')
    try:
        price_num = float(price_val)
        price_str = f"{price_num:g} {symbol}" if price_num == int(price_num) else f"{price_num:.2f} {symbol}"
    except (ValueError, TypeError):
        price_str = f"{price_val} {symbol}"

    created = order.get('created_at')
    date_str = ""
    if created:
        if isinstance(created, datetime):
            date_str = created.strftime("%Y-%m-%d %H:%M UTC")
        else:
            date_str = str(created)[:16]

    content = escape(str(order.get('delivered_item', '')).strip())

    lines = [
        f"📦 <b>Order #{order_id} Details</b>\n",
        f"🏷️ <b>Product:</b> {title}",
        f"💵 <b>Price Paid:</b> {price_str}",
    ]
    if date_str:
        lines.append(f"📅 <b>Date:</b> {date_str}")
    lines.append("🔖 <b>Status:</b> COMPLETED\n")
    lines.append("🔑 <b>Delivered Credentials:</b>")
    lines.append(f"<code>{content}</code>\n")
    lines.append("<i>(Tap the button below or tap the code to copy)</i>")

    return "\n".join(lines)



class DeliveryService:
    def __init__(self, db: Database):
        self.db = db

    async def enqueue_order(self, tg_user_id: int, order: dict[str, Any], *, conn: asyncpg.Connection | None = None) -> None:
        sql = "INSERT INTO outbox (tg_user_id, text, order_id) VALUES ($1, $2, $3) ON CONFLICT (order_id) DO NOTHING"
        if conn is not None:
            await conn.execute(sql, tg_user_id, receipt(order), order['order_id'])
            return
        async with self.db.connect() as connection:
            await connection.execute(sql, tg_user_id, receipt(order), order['order_id'])

    async def enqueue_waiting_notice(self, tg_user_id: int, order: dict[str, Any], *, conn: asyncpg.Connection) -> None:
        """Tells a customer whose order is waiting that it was paid. Not the receipt, which follows on delivery."""
        await conn.execute(
            "INSERT INTO outbox (tg_user_id, text, about_order_id) VALUES ($1, $2, $3)",
            tg_user_id,
            waiting_notice(order),
            order['order_id'],
        )

    async def recover_missing_receipts(self) -> int:
        """Queue receipts for pending orders that have none (orders imported before the outbox existed)."""
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                "SELECT * FROM orders o WHERE o.status = 'completed' AND o.fulfillment = 'delivered' AND o.delivery_status = 'pending' "
                "AND NOT EXISTS (SELECT 1 FROM outbox x WHERE x.order_id = o.id)"
            )
            if rows:
                await conn.executemany(
                    "INSERT INTO outbox (tg_user_id, text, order_id) VALUES ($1, $2, $3) ON CONFLICT (order_id) DO NOTHING",
                    [(row['tg_user_id'], receipt(dict(row)), row['id']) for row in rows],
                )
        return len(rows)

    async def enqueue_broadcast(self, text: str) -> dict[str, int]:
        async with self.db.transaction() as conn:
            job_id = await conn.fetchval("INSERT INTO broadcasts DEFAULT VALUES RETURNING id")
            await conn.execute(
                "INSERT INTO outbox (tg_user_id, text, broadcast_id) SELECT tg_user_id, $1, $2 FROM users WHERE is_banned = 0",
                text,
                job_id,
            )
            await record(conn, "broadcast_queued", f"Broadcast #{job_id} ({len(text)} characters)")
        return await self.broadcast_status(job_id)

    async def broadcast_status(self, job_id: int) -> dict[str, int]:
        async with self.db.connect() as conn:
            rows = await conn.fetch("SELECT status, COUNT(*) AS n FROM outbox WHERE broadcast_id = $1 GROUP BY status", job_id)
        counts = {row['status']: row['n'] for row in rows}
        return {
            'id': job_id,
            'success': counts.get('sent', 0),
            'failed': counts.get('failed', 0),
            'pending': counts.get('pending', 0) + counts.get('sending', 0),
            'total': sum(counts.values()),
        }

    async def retry_order(self, order_id: int) -> None:
        async with self.db.transaction() as conn:
            order = await conn.fetchrow("SELECT * FROM orders WHERE id = $1 AND status = 'completed' FOR UPDATE", order_id)
            if not order:
                raise NotFoundError("Completed order not found.")
            if order['fulfillment'] == 'waiting':
                raise NotFoundError("This order has nothing to send yet. Deliver it first.")
            await conn.execute(
                "INSERT INTO outbox (tg_user_id, text, order_id) VALUES ($1, $2, $3) ON CONFLICT (order_id) DO NOTHING",
                order['tg_user_id'],
                receipt(dict(order)),
                order_id,
            )
            await conn.execute(
                "UPDATE outbox SET status = 'pending', attempts = 0, next_attempt = 0, error = '' "
                "WHERE order_id = $1 AND status = 'failed'",
                order_id,
            )
            await conn.execute(
                "UPDATE orders SET delivery_status = 'pending' WHERE id = $1 AND delivery_status IN ('failed', 'legacy')",
                order_id,
            )

    async def claim_next(self) -> dict[str, Any] | None:
        now = time.time()
        async with self.db.connect() as conn:
            # SKIP LOCKED lets concurrent workers claim different rows.
            row = await conn.fetchrow(
                "UPDATE outbox SET status = 'sending', next_attempt = $1, attempts = attempts + 1 "
                "WHERE id = (SELECT id FROM outbox WHERE status IN ('pending', 'sending') AND next_attempt <= $2 "
                "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *",
                now + LEASE_SECONDS,
                now,
            )
        return dict(row) if row else None

    async def order_for(self, message: dict[str, Any]) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM orders WHERE id = $1 AND tg_user_id = $2", message['order_id'], message['tg_user_id']
            )
            return dict(row) if row else None

    async def cancel(self, message_id: int) -> None:
        async with self.db.connect() as conn:
            await conn.execute("UPDATE outbox SET status = 'cancelled' WHERE id = $1", message_id)

    async def finish(self, message: dict[str, Any], status: str, delay: float, error: str) -> None:
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE outbox SET status = $1, next_attempt = $2, error = $3 WHERE id = $4",
                status,
                time.time() + delay,
                error,
                message['id'],
            )
            if message['order_id']:
                await conn.execute(
                    "UPDATE orders SET delivery_status = $1 WHERE id = $2 AND status = 'completed'",
                    status,
                    message['order_id'],
                )
