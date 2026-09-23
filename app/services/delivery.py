"""Durable Telegram outbox for order receipts and broadcasts.

Rows are claimed with a lease, so an interrupted send is retried after restart.
Delivery is at least once: a crash right after Telegram accepts a message can
send it again, but never charges the customer again.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from html import escape
from typing import Any

import asyncpg

from app.bot.formatting import format_dual_price
from app.bot.icons import (
    ICON_CHECK,
    ICON_KEY,
    ICON_MONEY,
    ICON_ORDERS,
    ICON_TIMER,
    ICON_VIP,
)
from app.db import Database
from app.services.audit import record
from app.services.errors import NotFoundError

LEASE_SECONDS = 120


def waiting_notice(order: dict[str, Any]) -> str:
    order_id = order.get('order_id', order.get('id'))
    title = escape(order.get('product_title', 'Purchase'))
    return (
        f"{ICON_TIMER} <b>Order #{order_id}: {title}</b>\n\n"
        f"{ICON_CHECK} <b>Payment Received!</b>\n\n"
        f"Your order is being prepared and will be delivered directly here when it is ready. Contact support if you need an update."
    )


def receipt(order: dict[str, Any]) -> str:
    order_id = order.get('order_id', order.get('id'))
    title = escape(str(order.get('product_title', 'Purchase')))
    price_val = order.get('price', 0)
    symbol = order.get('currency_symbol', '৳')
    usd_rate = order.get('usd_rate')
    show_usd = order.get('show_usd')
    price_str = format_dual_price(price_val, symbol=symbol, usd_rate=usd_rate, show_usd=show_usd)

    created = order.get('created_at')
    date_str = ""
    if created:
        if isinstance(created, datetime):
            date_str = created.strftime("%Y-%m-%d %H:%M UTC")
        else:
            date_str = str(created)[:16]

    raw_content = str(order.get('delivered_item', '')).strip()

    lines = [
        f"{ICON_ORDERS} <b>Order #{order_id} Details</b>\n",
        f"{ICON_VIP} <b>Product:</b> {title}",
        f"{ICON_MONEY} <b>Price:</b> <code>{price_str}</code>",
    ]
    if date_str:
        lines.append(f"{ICON_TIMER} <b>Date:</b> {date_str}")
    lines.append(f"{ICON_CHECK} <b>Status:</b> <code>COMPLETED</code>\n")
    lines.append(f"{ICON_KEY} <b>Delivered Credentials:</b>")

    cred_items = [escape(it.strip()) for it in raw_content.splitlines() if it.strip()]
    if cred_items:
        for it in cred_items:
            lines.append(f"<code>{it}</code>")
    else:
        lines.append(f"<code>{escape(raw_content)}</code>")

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
            job_id = await conn.fetchval("INSERT INTO broadcasts (text) VALUES ($1) RETURNING id", text)
            await conn.execute(
                "INSERT INTO outbox (tg_user_id, text, broadcast_id) SELECT tg_user_id, $1, $2 FROM users WHERE is_banned = 0",
                text,
                job_id,
            )
            await record(conn, "broadcast_queued", f"Broadcast #{job_id} ({len(text)} characters)")
            # Auto-prune old broadcasts exceeding the retention limit (30)
            await conn.execute(
                """
                DELETE FROM broadcasts
                WHERE id NOT IN (
                    SELECT id FROM broadcasts ORDER BY id DESC LIMIT 30
                )
                AND NOT EXISTS (
                    SELECT 1 FROM outbox WHERE broadcast_id = broadcasts.id AND status IN ('pending', 'sending')
                )
                """
            )
        return await self.broadcast_status(job_id)

    async def delete_broadcast(self, job_id: int) -> bool:
        async with self.db.transaction() as conn:
            result = await conn.execute("DELETE FROM broadcasts WHERE id = $1", job_id)
            await record(conn, "broadcast_deleted", f"Broadcast #{job_id} deleted")
        return result.endswith("1")

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

    async def recipient_count(self) -> int:
        async with self.db.connect() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned = 0") or 0

    async def recent_broadcasts(self, limit: int = 30) -> list[dict]:
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                """
                SELECT b.id, b.created_at,
                       COALESCE(NULLIF(b.text, ''), (SELECT o.text FROM outbox o WHERE o.broadcast_id = b.id LIMIT 1), '') AS text,
                       COUNT(o.id) AS total,
                       COUNT(o.id) FILTER (WHERE o.status = 'sent') AS success,
                       COUNT(o.id) FILTER (WHERE o.status = 'failed') AS failed,
                       COUNT(o.id) FILTER (WHERE o.status IN ('pending', 'sending')) AS pending
                FROM broadcasts b
                LEFT JOIN outbox o ON o.broadcast_id = b.id
                GROUP BY b.id, b.created_at, b.text
                ORDER BY b.id DESC
                LIMIT $1
                """,
                limit,
            )
        return [
            {
                'id': row['id'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else '',
                'text': row['text'],
                'total': row['total'],
                'success': row['success'],
                'failed': row['failed'],
                'pending': row['pending'],
            }
            for row in rows
        ]

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
            # Order receipts are prioritised over broadcasts so a bulk send never delays a purchase delivery.
            row = await conn.fetchrow(
                "UPDATE outbox SET status = 'sending', next_attempt = $1, attempts = attempts + 1, lease_token = $3 "
                "WHERE id = (SELECT id FROM outbox WHERE status IN ('pending', 'sending') AND next_attempt <= $2 "
                "ORDER BY CASE WHEN order_id IS NOT NULL OR about_order_id IS NOT NULL THEN 0 ELSE 1 END, id "
                "LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING *",
                now + LEASE_SECONDS,
                now,
                uuid.uuid4().hex,
            )
        return dict(row) if row else None

    async def order_for(self, message: dict[str, Any]) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM orders WHERE id = $1 AND tg_user_id = $2", message['order_id'], message['tg_user_id']
            )
            return dict(row) if row else None

    async def cancel(self, message: dict[str, Any]) -> None:
        async with self.db.connect() as conn:
            await conn.execute("UPDATE outbox SET status = 'cancelled' WHERE id = $1 AND lease_token=$2", message["id"], message["lease_token"])

    async def finish(self, message: dict[str, Any], status: str, delay: float, error: str) -> None:
        async with self.db.transaction() as conn:
            changed = await conn.fetchval(
                "UPDATE outbox SET status = $1, next_attempt = $2, error = $3 WHERE id = $4 AND lease_token=$5 AND status='sending' RETURNING id",
                status,
                time.time() + delay,
                error,
                message['id'],
                message['lease_token'],
            )
            if changed is None:
                return
            if error == 'Telegram rate limit':
                await conn.execute(
                    "UPDATE outbox SET next_attempt=GREATEST(next_attempt,$1) WHERE tg_user_id=$2 AND status='pending'",
                    time.time() + delay, message['tg_user_id'])
            if message['order_id']:
                await conn.execute(
                    "UPDATE orders SET delivery_status = $1 WHERE id = $2 AND status = 'completed'",
                    status,
                    message['order_id'],
                )
