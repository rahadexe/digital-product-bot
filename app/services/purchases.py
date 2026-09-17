"""Wallet purchases: stock claim or supplier fulfillment, referral reward, receipt queueing, later fulfillment and refunds.

A paid order is never lost. When the supplier cannot deliver (no balance, an error, a timeout) the customer is
still charged and the order waits; the admin sends it later by hand or through the supplier again, or refunds it.
"""

from __future__ import annotations

import logging
import uuid
from html import escape
from typing import Any

from app.core.money import money
from app.db import Database
from app.services.audit import record
from app.services.delivery import DeliveryService
from app.services.errors import InvalidInputError, NotFoundError
from app.services.inventory import InventoryService
from app.services.notifications import Notifier
from app.services.settings import SettingsService
from app.services.supplier import SupplierService

logger = logging.getLogger("app.services.purchases")

PurchaseResult = tuple[bool, str, dict[str, Any] | None]
MAX_DELIVERY_LENGTH = 20_000


def _receipt_fields(row: Any, balance: float) -> dict[str, Any]:
    return {
        "order_id": row["id"],
        "product_title": row["product_title"],
        "price": row["price"],
        "delivered_item": row["delivered_item"],
        "fulfillment": row["fulfillment"],
        "remaining_balance": balance,
        "created_at": row.get("created_at") if hasattr(row, "get") else (row["created_at"] if "created_at" in row else None),
    }


class PurchaseService:
    def __init__(
        self,
        db: Database,
        settings: SettingsService,
        supplier: SupplierService,
        delivery: DeliveryService,
        notifier: Notifier,
    ):
        self.db = db
        self.settings = settings
        self.supplier = supplier
        self.delivery = delivery
        self.notifier = notifier

    async def purchase(self, tg_user_id: int, product_id: int, request_id: str | None = None) -> PurchaseResult:
        """
        Charge the wallet, take a stock seat (or fulfil through the supplier), record the order, credit the
        referrer and queue the customer's message, all in one transaction.
        The price always comes from the database, never from the caller.
        """
        # Paused applies to every way in (bot, Mini App), so it is checked here rather than in each of them.
        paused = await self.settings.paused_message()
        if paused:
            return False, paused, None
        referral_percent = await self.settings.number("referral_bonus_percent")
        waiting_reason = ""
        async with self.db.connect() as db:
            await db.execute("BEGIN")
            try:
                # 1. Lock the customer; purchases by the same customer queue here.
                user = await db.fetchrow("SELECT * FROM users WHERE tg_user_id = $1 FOR UPDATE", tg_user_id)
                if not user:
                    await db.execute("ROLLBACK")
                    return False, "User not found.", None
                if user["is_banned"]:
                    await db.execute("ROLLBACK")
                    return False, "Account is banned.", None

                if request_id:
                    previous = await db.fetchrow(
                        "SELECT * FROM orders WHERE tg_user_id = $1 AND request_id = $2", tg_user_id, request_id
                    )
                    if previous:
                        await db.execute("ROLLBACK")
                        if previous["product_id"] != product_id or previous["status"] != "completed":
                            return False, "This purchase request has already been used.", None
                        return True, "Success", _receipt_fields(previous, user["balance"])

                # 2. Product and price
                product = await db.fetchrow("SELECT * FROM products WHERE id = $1 AND is_active = 1", product_id)
                if not product:
                    await db.execute("ROLLBACK")
                    return False, "Product is currently unavailable.", None
                price = money(product["price"], positive=True)
                if user["balance"] < price:
                    await db.execute("ROLLBACK")
                    short = round(price - user["balance"], 2)
                    return False, f"Insufficient balance. You need {short:.2f} more to purchase this item.", None

                # 3. A seat in local stock
                stock_item = await InventoryService.claim_seat(db, product_id, tg_user_id)
                if not stock_item:
                    await db.execute("ROLLBACK")
                    return False, "Sorry, this item is currently out of stock!", None

                delivered_content = stock_item["content"]
                source = "stock"

                # 4. Charge the wallet
                new_balance = round(user["balance"] - price, 4)
                await db.execute(
                    "UPDATE users SET balance = $1, total_spent = $2, updated_at = now() WHERE id = $3",
                    new_balance,
                    round(user["total_spent"] + price, 4),
                    user["id"],
                )

                # 5. Record order and mark stock seat used
                order_row = await db.fetchrow(
                    """
                    INSERT INTO orders (user_id, tg_user_id, product_id, product_title, price, delivered_item,
                                        status, request_id, delivery_status, fulfillment, source, inventory_item_id,
                                        fulfilled_at)
                    VALUES ($1, $2, $3, $4, $5, $6, 'completed', $7, 'pending', 'delivered', $8, $9, now())
                    RETURNING *
                    """,
                    user["id"],
                    tg_user_id,
                    product_id,
                    product["title"],
                    price,
                    delivered_content,
                    request_id,
                    source,
                    stock_item["id"],
                )
                order_id = order_row["id"]
                await InventoryService.use_seat(db, stock_item["id"], order_id)

                order = _receipt_fields(order_row, new_balance)
                order["currency_symbol"] = await self.settings.get("currency_symbol")
                await self.delivery.enqueue_order(tg_user_id, order, conn=db)
                await db.execute("COMMIT")
            except Exception as exc:
                if db.is_in_transaction():
                    await db.execute("ROLLBACK")
                logger.exception("Purchase error: %s", exc)
                return False, "Purchase could not be completed. Please contact support before retrying.", None

        # The customer gets the result now; the admin alert must not add a Telegram round trip.
        self.notifier.in_background(self._notify_admin(user, order, waiting_reason if waiting else ""))
        return True, "Success", order

    async def _notify_admin(self, user: Any, order: dict[str, Any], waiting_reason: str = "") -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        customer = f"@{escape(user['username'])}" if user["username"] else "No username"
        heading = "⏳ <b>Order waiting for you</b>" if waiting_reason else "🛒 <b>New order</b>"
        delivery = (
            f"⚠️ <b>Not delivered:</b> {escape(waiting_reason)}\nSend it from the console → Orders."
            if waiting_reason
            else "📬 <b>Delivery:</b> Queued"
        )
        await self.notifier.send_admin(
            f"{heading}\n\n"
            f"📦 <b>Order ID:</b> #{order['order_id']}\n"
            f"👤 <b>Customer:</b> {customer} (<code>{user['tg_user_id']}</code>)\n"
            f"🏷️ <b>Product:</b> {escape(order['product_title'])}\n"
            f"💵 <b>Price:</b> {symbol}{order['price']:.2f}\n"
            f"{delivery}"
        )

    # --- orders that are paid but not delivered ---

    async def fulfill_manually(self, order_id: int, content: str) -> dict[str, Any]:
        """The admin types what the customer gets (from the supplier's site, another stock, anywhere)."""
        content = content.strip()
        if not content:
            raise InvalidInputError("Type what the customer should receive.")
        if len(content) > MAX_DELIVERY_LENGTH:
            raise InvalidInputError("That is too long to deliver.")
        async with self.db.transaction() as conn:
            order = await conn.fetchrow("SELECT * FROM orders WHERE id = $1 FOR UPDATE", order_id)
            if not order:
                raise NotFoundError("Order not found.")
            if order["status"] != "completed" or order["fulfillment"] != "waiting":
                raise InvalidInputError("Only a paid order that is still waiting can be delivered.")
            row = await conn.fetchrow(
                "UPDATE orders SET delivered_item = $1, fulfillment = 'delivered', source = 'manual', fulfilled_at = now(), "
                "delivery_status = 'pending' WHERE id = $2 RETURNING *",
                content,
                order_id,
            )
            closed = await conn.fetch(
                "UPDATE supplier_purchase_attempts SET status = 'failed' WHERE order_id = $1 AND status IN ('pending', 'review') "
                "RETURNING id",
                order_id,
            )
            manual_order = _receipt_fields(row, 0)
            manual_order["currency_symbol"] = await self.settings.get("currency_symbol")
            await self.delivery.enqueue_order(order["tg_user_id"], manual_order, conn=conn)
            note = f"; closed supplier attempt(s) {', '.join(f'#{r['id']}' for r in closed)}" if closed else ""
            await record(conn, "order_delivered_manually", f"Order #{order_id} delivered by the admin{note}")
        return dict(row)

    async def order_detail(self, order_id: int) -> dict[str, Any]:
        """Everything about one order: what was delivered, where it came from, and every message sent about it."""
        async with self.db.connect() as conn:
            order = await conn.fetchrow(
                "SELECT o.*, u.username, u.first_name, u.balance AS customer_balance FROM orders o "
                "LEFT JOIN users u ON u.id = o.user_id WHERE o.id = $1",
                order_id,
            )
            if not order:
                raise NotFoundError("Order not found.")
            item = (
                await conn.fetchrow("SELECT id, max_uses, uses, status FROM inventory_items WHERE id = $1", order["inventory_item_id"])
                if order["inventory_item_id"]
                else None
            )
            messages = await conn.fetch(
                "SELECT id, text, status, attempts, error, order_id IS NOT NULL AS is_receipt FROM outbox "
                "WHERE order_id = $1 OR about_order_id = $1 ORDER BY id",
                order_id,
            )
        return {
            "order": dict(order),
            "stock_item": dict(item) if item else None,
            "supplier_attempts": [],
            "messages": [dict(row) for row in messages],
        }

    async def refund(self, order_id: int) -> tuple[bool, str]:
        try:
            async with self.db.transaction() as conn:
                order = await conn.fetchrow("SELECT * FROM orders WHERE id = $1 FOR UPDATE", order_id)
                if not order:
                    return False, "Order not found."
                if order["status"] == "refunded":
                    return False, "Order has already been refunded."
                await conn.execute(
                    "UPDATE users SET balance = balance + $1, total_spent = GREATEST(0, total_spent - $1) WHERE tg_user_id = $2",
                    order["price"],
                    order["tg_user_id"],
                )
                if order["referral_user_id"] and order["referral_bonus"]:
                    # Debt is retained if a referrer already spent the reward.
                    await conn.execute(
                        "UPDATE users SET balance = balance - $1 WHERE tg_user_id = $2",
                        order["referral_bonus"],
                        order["referral_user_id"],
                    )
                await conn.execute("UPDATE orders SET status = 'refunded', delivery_status = 'cancelled' WHERE id = $1", order_id)
                await record(
                    conn,
                    "refund_order",
                    f"Refunded Order #{order_id} ({order['product_title']}) for {order['price']:.2f} to user {order['tg_user_id']}",
                )
        except Exception as exc:
            logger.exception("Refund of order %s failed", order_id)
            return False, f"Refund failed: {type(exc).__name__}"
        return True, f"Successfully refunded {order['price']:.2f} to user."

    async def order_for_customer(self, tg_user_id: int, order_id: int) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow("SELECT * FROM orders WHERE id = $1 AND tg_user_id = $2", order_id, tg_user_id)
            return dict(row) if row else None

    async def customer_orders(self, tg_user_id: int, limit: int = 10, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        async with self.db.connect() as conn:
            # The page and the total in one round trip.
            rows = await conn.fetch(
                "SELECT o.*, COUNT(*) OVER () AS total_count FROM orders o WHERE o.tg_user_id = $1 "
                "ORDER BY o.id DESC LIMIT $2 OFFSET $3",
                tg_user_id,
                limit,
                offset,
            )
            if rows:
                total = rows[0]["total_count"]
            else:
                total = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE tg_user_id = $1", tg_user_id) if offset else 0
        orders = [{key: value for key, value in row.items() if key != "total_count"} for row in rows]
        return orders, total

    async def all_orders(
        self,
        search: str = "",
        limit: int = 50,
        offset: int = 0,
        waiting_only: bool = False,
        tg_user_id: int | None = None,
        days: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        summary_where, summary_params = "", []
        if search:
            summary_params.append(f"%{search}%")
            summary_where += (
                f" AND (CAST(o.id AS TEXT) LIKE ${len(summary_params)} OR o.product_title ILIKE ${len(summary_params)} "
                f"OR CAST(o.tg_user_id AS TEXT) LIKE ${len(summary_params)} OR u.username ILIKE ${len(summary_params)})"
            )
        if tg_user_id:
            summary_params.append(tg_user_id)
            summary_where += f" AND o.tg_user_id = ${len(summary_params)}"
        if days == 1:
            summary_where += " AND o.created_at >= CURRENT_DATE"
        elif days and days > 1:
            summary_params.append(days)
            summary_where += f" AND o.created_at >= (NOW() - (${len(summary_params)} * INTERVAL '1 day'))"
        if date_from:
            summary_params.append(date_from)
            summary_where += f" AND o.created_at >= ${len(summary_params)}::timestamptz"
        if date_to:
            summary_params.append(date_to)
            summary_where += f" AND o.created_at < (${len(summary_params)}::date + INTERVAL '1 day')::timestamptz"

        table_where, table_params = summary_where, list(summary_params)
        if waiting_only:
            table_where += " AND o.status = 'completed' AND o.fulfillment = 'waiting'"

        async with self.db.connect() as conn:
            rows = await conn.fetch(
                f"""
                SELECT o.*, u.username, u.first_name, COUNT(*) OVER () AS total_count
                FROM orders o LEFT JOIN users u ON u.id = o.user_id
                WHERE 1=1{table_where}
                ORDER BY o.id DESC LIMIT ${len(table_params) + 1} OFFSET ${len(table_params) + 2}
                """,
                *table_params,
                limit,
                offset,
            )
            summary_row = await conn.fetchrow(
                f"""
                SELECT 
                    COUNT(*) AS total_orders,
                    COALESCE(SUM(CASE WHEN o.status = 'completed' THEN o.price ELSE 0 END), 0)::float AS total_revenue,
                    COUNT(CASE WHEN o.status = 'completed' AND o.fulfillment = 'delivered' THEN 1 END) AS delivered_orders,
                    COUNT(CASE WHEN o.status = 'completed' AND o.fulfillment = 'waiting' THEN 1 END) AS waiting_orders
                FROM orders o LEFT JOIN users u ON u.id = o.user_id
                WHERE 1=1{summary_where}
                """,
                *summary_params,
            )

        total = rows[0]["total_count"] if rows else 0
        summary = {
            "total_orders": int(summary_row["total_orders"] or 0) if summary_row else 0,
            "total_revenue": round(float(summary_row["total_revenue"] or 0.0), 2) if summary_row else 0.0,
            "delivered_orders": int(summary_row["delivered_orders"] or 0) if summary_row else 0,
            "waiting_orders": int(summary_row["waiting_orders"] or 0) if summary_row else 0,
        }
        return [{key: value for key, value in row.items() if key != "total_count"} for row in rows], total, summary

    async def waiting_count(self) -> int:
        async with self.db.connect() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'completed' AND fulfillment = 'waiting'")

