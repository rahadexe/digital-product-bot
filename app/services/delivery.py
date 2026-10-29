"""Durable Telegram outbox for order receipts and broadcasts.

Rows are claimed with a lease, so an interrupted send is retried after restart.
Delivery is at least once: a crash right after Telegram accepts a message can
send it again, but never charges the customer again.
"""

from __future__ import annotations

import re
import time
import uuid
from html import escape
from typing import Any

import asyncpg

from app.bot.formatting import format_dual_price
from app.core.identifiers import format_order_id
from app.db import Database
from app.services.audit import record
from app.services.errors import NotFoundError

LEASE_SECONDS = 120
_LABELED_CRED_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /\-_]{1,24}):\s+(.+)$")


def format_credential_lines(raw_content: str) -> str:
    """Format credential lines so labeled values (e.g. 'Email: x') wrap only the value in <code>."""
    stripped = (raw_content or "").strip()
    raw_lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not raw_lines:
        return f"<code>{escape(stripped)}</code>"
    formatted: list[str] = []
    for line in raw_lines:
        match = _LABELED_CRED_RE.match(line)
        if match and not match.group(1).lower().startswith(("http", "ftp")):
            label, value = match.group(1), match.group(2)
            formatted.append(f"{escape(label)}: <code>{escape(value)}</code>")
        else:
            formatted.append(f"<code>{escape(line)}</code>")
    return "\n".join(formatted)


def waiting_notice(order: dict[str, Any], lang: str = "en") -> str:
    order_id = int(order.get('order_id', order.get('id')) or 0)
    title = escape(str(order.get('product_title', 'Purchase')))
    return (
        f"⏳ <b>Preparing delivery · {format_order_id(order_id)}</b>\n\n"
        f"<b>Product:</b> {title}\n"
        "Payment received. Details will arrive here shortly."
    )



def receipt(order: dict[str, Any], lang: str = "en") -> str:
    order_id = int(order.get('order_id', order.get('id')) or 0)
    title = escape(str(order.get('product_title', 'Purchase')))
    price_val = order.get('price', 0)
    symbol = order.get('currency_symbol', '৳')
    usd_rate = order.get('usd_rate')
    price_str = format_dual_price(price_val, symbol=symbol, usd_rate=usd_rate, show_usd=False, lang=lang)

    raw_content = str(order.get('delivered_item', '')).strip()
    lines = [
        f"✅ <b>Delivered · {format_order_id(order_id)}</b>\n",
        f"<b>Product:</b> {title}",
        f"<b>Paid:</b> <code>{price_str}</code>\n",
        "<b>Delivery:</b>",
        format_credential_lines(raw_content),
    ]

    return "\n".join(lines)



class DeliveryService:
    def __init__(self, db: Database):
        self.db = db

    async def enqueue_order(self, tg_user_id: int, order: dict[str, Any], *, conn: asyncpg.Connection | None = None) -> None:
        sql = "INSERT INTO outbox (tg_user_id, text, order_id) VALUES ($1, $2, $3) ON CONFLICT (order_id) DO NOTHING"
        # Customer-facing bot copy is English, including accounts with old saved languages.
        text = receipt(order, lang="en")
        if conn is not None:
            await conn.execute(sql, tg_user_id, text, order['order_id'])
            return
        async with self.db.connect() as connection:
            await connection.execute(sql, tg_user_id, text, order['order_id'])

    async def enqueue_waiting_notice(self, tg_user_id: int, order: dict[str, Any], *, conn: asyncpg.Connection) -> None:
        """Tells a customer whose order is waiting that it was paid. Not the receipt, which follows on delivery."""
        text = waiting_notice(order, lang="en")
        await conn.execute(
            "INSERT INTO outbox (tg_user_id, text, about_order_id) VALUES ($1, $2, $3)",
            tg_user_id,
            text,
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
                "INSERT INTO outbox (tg_user_id, text, broadcast_id) "
                "SELECT u.tg_user_id, $1, $2 FROM users u "
                "LEFT JOIN user_notification_preferences p ON p.tg_user_id=u.tg_user_id "
                "WHERE u.is_banned = 0 AND COALESCE(p.notify_news, TRUE)",
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
            return await conn.fetchval(
                "SELECT COUNT(*) FROM users u "
                "LEFT JOIN user_notification_preferences p ON p.tg_user_id=u.tg_user_id "
                "WHERE u.is_banned = 0 AND COALESCE(p.notify_news, TRUE)"
            ) or 0

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
            # A customer can opt out after a broadcast was queued. Never suppress receipts.
            await conn.execute(
                "UPDATE outbox o SET status='cancelled' "
                "WHERE broadcast_id IS NOT NULL AND order_id IS NULL AND about_order_id IS NULL "
                "AND (status IN ('pending','failed') OR (status='sending' AND next_attempt <= $1)) "
                "AND EXISTS (SELECT 1 FROM user_notification_preferences p "
                "WHERE p.tg_user_id=o.tg_user_id AND NOT p.notify_news)",
                now,
            )
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

    async def news_allowed(self, tg_user_id: int) -> bool:
        """Recheck optional broadcasts just before sending, not just when queued."""
        async with self.db.connect() as conn:
            preference = await conn.fetchval(
                "SELECT notify_news FROM user_notification_preferences WHERE tg_user_id=$1",
                tg_user_id,
            )
        return preference is not False

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
