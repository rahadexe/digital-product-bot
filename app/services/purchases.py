"""Transactional wallet purchases, instant stock delivery, manual fulfillment and refunds."""

from __future__ import annotations

import logging
from collections import Counter
from decimal import Decimal
from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.formatting import price
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_CHECK,
    ICON_MONEY,
    ICON_ORDERS,
    ICON_SHOP,
    ICON_TIMER,
    ICON_VIP,
    ICON_WARNING,
    Icons,
)
from app.core.config import get_settings
from app.core.money import money
from app.db import Database
from app.services.audit import record
from app.services.delivery import DeliveryService
from app.services.errors import InvalidInputError, NotFoundError
from app.services.inventory import InventoryService
from app.services.notifications import Notifier
from app.services.settings import SettingsService

logger = logging.getLogger("app.services.purchases")

PurchaseResult = tuple[bool, str, dict[str, Any] | None]
MAX_DELIVERY_LENGTH = 20_000


def _receipt_fields(row: Any, balance: float) -> dict[str, Any]:
    return {
        "order_id": row["id"],
        "product_title": row["product_title"],
        "price": row["price"],
        "unit_price": row.get('unit_price'),
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
        delivery: DeliveryService,
        notifier: Notifier,
    ):
        self.db = db
        self.settings = settings
        self.delivery = delivery
        self.notifier = notifier

    async def purchase(self, tg_user_id: int, product_id: int, quantity: int = 1, request_id: str | None = None, *, require_reseller: bool = False, reseller_key_id: int | None = None) -> PurchaseResult:
        """
        Charge the wallet, take stock seats (or fulfil through manual delivery), record the order,
        and queue the customer's message, all in one transaction.
        The price always comes from the database, never from the caller.
        """
        if not 1 <= quantity <= 1000:
            return False, "Choose a quantity from 1 to 1000.", None
        # Paused applies to every way in (bot, Mini App), so it is checked here rather than in each of them.
        paused = await self.settings.paused_message()
        if paused:
            return False, paused, None
        waiting_reason = ""
        symbol = await self.settings.get("currency_symbol")
        usd_rate = await self.settings.number('usd_rate')
        show_usd = await self.settings.flag('show_usd_price')
        is_manual = False
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
                if require_reseller and (user['rank'] or '').strip().lower() != 'reseller':
                    await db.execute('ROLLBACK')
                    return False, 'Reseller access is no longer active.', None
                if require_reseller and not await db.fetchval(
                    'SELECT id FROM reseller_api_keys WHERE id=$1 AND user_id=$2 AND tg_user_id=$3 AND is_active=1 FOR SHARE',
                    reseller_key_id,user['id'],tg_user_id,
                ):
                    await db.execute('ROLLBACK')
                    return False, 'API key is no longer active.', None

                if request_id:
                    previous = await db.fetchrow(
                        "SELECT * FROM orders WHERE tg_user_id = $1 AND request_id = $2", tg_user_id, request_id
                    )
                    if previous:
                        await db.execute("ROLLBACK")
                        if previous["product_id"] != product_id or previous["status"] != "completed" or (previous.get("quantity") or 1) != quantity:
                            return False, "This purchase request has already been used.", None
                        return True, "Success", _receipt_fields(previous, user["balance"])

                # 2. Product and price
                product = await db.fetchrow("SELECT * FROM products WHERE id = $1 AND is_active = 1 FOR SHARE", product_id)
                if not product:
                    await db.execute("ROLLBACK")
                    return False, "Product is currently unavailable.", None

                is_reseller = (user.get("rank") or "").strip().lower() == "reseller"
                reseller_price = product.get("reseller_price")
                if is_reseller and reseller_price is not None and float(reseller_price) > 0:
                    unit_price = money(reseller_price, positive=True)
                else:
                    unit_price = money(product["price"], positive=True)

                total_price = Decimal(str(unit_price)) * quantity
                if not await db.fetchval('SELECT balance >= $1 FROM users WHERE id=$2', total_price, user['id']):
                    await db.execute("ROLLBACK")
                    short = round(total_price - Decimal(str(user["balance"])), 2)
                    return False, f"Insufficient balance. You need {short:.2f} more to purchase this item.", None

                # 3. Check delivery type
                is_manual = product.get("delivery_type") == "manual"
                stock_item_ids: list[int] = []
                if is_manual:
                    delivered_content = ""
                    source = "manual"
                    fulfillment = "waiting"
                    waiting_reason = f"Manual delivery product (Quantity: {quantity})" if quantity > 1 else "Manual delivery product"
                else:
                    # Seats in local stock
                    stock_items = await InventoryService.claim_seats(db, product_id, tg_user_id, count=quantity)
                    if not stock_items or len(stock_items) < quantity:
                        await db.execute("ROLLBACK")
                        return False, f"Sorry, this item currently does not have {quantity} in stock!", None

                    delivered_content = "\n".join(item["content"] for item in stock_items)
                    source = "stock"
                    fulfillment = "delivered"
                    stock_item_ids = [item["id"] for item in stock_items]

                # 4. Charge the wallet
                await db.execute("SELECT set_config('app.wallet_reason', $1, true)", f"purchase:{request_id or product_id}")
                new_balance = await db.fetchval(
                    "UPDATE users SET balance = balance - $1, total_spent = total_spent + $1, updated_at = now() WHERE id = $2 RETURNING balance",
                    total_price,
                    user["id"],
                )

                # 5. Record order and mark stock seats used if applicable
                order_title = f"{product['title']} (x{quantity})" if quantity > 1 else product["title"]
                primary_stock_id = stock_item_ids[0] if stock_item_ids else None
                order_row = await db.fetchrow(
                    """
                    INSERT INTO orders (user_id, tg_user_id, product_id, product_title, price, delivered_item,
                                        status, request_id, delivery_status, fulfillment, source, inventory_item_id,
                                        fulfilled_at, quantity, unit_price)
                    VALUES ($1, $2, $3, $4, $5, $6, 'completed', $7, 'pending', $8, $9, $10, CASE WHEN $8 = 'delivered' THEN now() ELSE NULL END, $11, $12)
                    RETURNING *
                    """,
                    user["id"],
                    tg_user_id,
                    product_id,
                    order_title,
                    total_price,
                    delivered_content,
                    request_id,
                    fulfillment,
                    source,
                    primary_stock_id,
                    quantity,
                    unit_price,
                )
                order_id = order_row["id"]
                for sid in stock_item_ids:
                    await InventoryService.use_seat(db, sid, order_id)
                if stock_item_ids:
                    await db.executemany(
                        "INSERT INTO order_inventory_allocations(order_id,inventory_item_id,allocated_units) VALUES($1,$2,$3)",
                        [(order_id, sid, units) for sid, units in Counter(stock_item_ids).items()],
                    )

                order = _receipt_fields(order_row, new_balance)
                order["product_id"] = order_row["product_id"]
                order["currency_symbol"] = symbol
                order["usd_rate"] = usd_rate
                order["show_usd"] = show_usd
                if is_manual:
                    await self.delivery.enqueue_waiting_notice(tg_user_id, order, conn=db)
                else:
                    await self.delivery.enqueue_order(tg_user_id, order, conn=db)
                await db.execute("COMMIT")
            except Exception as exc:
                if db.is_in_transaction():
                    await db.execute("ROLLBACK")
                logger.exception("Purchase error: %s", exc)
                return False, "Purchase could not be completed. Please contact support before retrying.", None

        # The customer gets the result now; the admin alert must not add a Telegram round trip.
        self.notifier.in_background(self._notify_admin(user, order, waiting_reason if is_manual else ""))
        return True, "Success", order

    async def _notify_admin(self, user: Any, order: dict[str, Any], waiting_reason: str = "") -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        usd_rate = await self.settings.number("usd_rate")
        show_usd = await self.settings.flag("show_usd_price")
        customer = f"@{escape(user['username'])}" if user.get("username") else "No username"
        order_id = order.get("order_id", order.get("id"))

        console = get_settings().console_url

        keyboard = None
        if waiting_reason:
            heading = f"{ICON_TIMER} <b>Manual Order Action Required</b>"
            delivery = f"{ICON_WARNING} <b>Delivery:</b> Manual Fulfillment Required"
            if console:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=f"Deliver Order #{order_id}",
                                url=f"{console}/#orders/{order_id}",
                                icon_custom_emoji_id=Icons.ORDERS,
                            )
                        ]
                    ]
                )
        else:
            heading = f"{ICON_SHOP} <b>New Order Received</b>"
            delivery = f"{ICON_CHECK} <b>Delivery:</b> Instant (Delivered)"

        stock_warning = ""
        prod_id = order.get("product_id")
        if prod_id and not waiting_reason:
            try:
                async with self.db.connect() as conn:
                    rem_stock = await conn.fetchval(
                        "SELECT COUNT(*) FROM inventory_items WHERE product_id = $1 AND status = 'available' AND (expires_at IS NULL OR expires_at > now())",
                        prod_id,
                    )
                if rem_stock == 0:
                    stock_warning = f"\n{ICON_WARNING} <b>Stock Alert:</b> Product is now <b>OUT OF STOCK!</b> (<code>0</code> left)"
                elif rem_stock <= 2:
                    stock_warning = f"\n{ICON_WARNING} <b>Stock Alert:</b> Low stock warning (only <code>{rem_stock}</code> left)"
            except Exception:
                pass

        await self.notifier.send_admin(
            f"{heading}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ORDERS} <b>Order ID:</b> <code>#{order_id}</code>\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> {customer} (<code>{user['tg_user_id']}</code>)\n"
            f"{ICON_VIP} <b>Product:</b> {escape(order['product_title'])}\n"
            f"{ICON_MONEY} <b>Price Paid:</b> <code>{price(symbol, order['price'], usd_rate=usd_rate, show_usd=show_usd)}</code>\n"
            f"{delivery}{stock_warning}",
            event="waiting_order" if waiting_reason else "order",
            keyboard=keyboard,
        )

    # --- orders that are paid but not delivered ---

    async def fulfill_manually(self, order_id: int, content: str) -> dict[str, Any]:
        """The admin provides the credentials for a paid manual order."""
        content = content.strip()
        if not content:
            raise InvalidInputError("Type what the customer should receive.")
        if len(content) > MAX_DELIVERY_LENGTH:
            raise InvalidInputError("That is too long to deliver.")
        symbol = await self.settings.get("currency_symbol")
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
            manual_order = _receipt_fields(row, 0)
            manual_order["currency_symbol"] = symbol
            manual_order["usd_rate"] = await self.settings.number("usd_rate")
            manual_order["show_usd"] = await self.settings.flag("show_usd_price")
            await self.delivery.enqueue_order(order["tg_user_id"], manual_order, conn=conn)
            await record(conn, "order_delivered_manually", f"Order #{order_id} delivered by the admin")
        return dict(row)

    async def order_detail(self, order_id: int) -> dict[str, Any]:
        """Everything about one order: what was delivered, where it came from, and every message sent about it."""
        async with self.db.connect() as conn:
            order = await conn.fetchrow(
                "SELECT o.*, u.username, u.first_name, u.last_name, u.balance AS customer_balance, "
                "p.duration_label, p.icon AS product_icon, p.title AS base_product_title FROM orders o "
                "LEFT JOIN users u ON (u.id = o.user_id OR (o.user_id IS NULL AND u.tg_user_id = o.tg_user_id)) "
                "LEFT JOIN products p ON p.id = o.product_id "
                "WHERE o.id = $1",
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
                await conn.fetch(
                    "SELECT id FROM users WHERE tg_user_id=ANY($1::bigint[]) ORDER BY tg_user_id FOR UPDATE",
                    sorted({order['tg_user_id'], order['referral_user_id'] or order['tg_user_id']}),
                )
                await conn.execute("SELECT set_config('app.wallet_reason',$1,true)", f"refund:{order_id}")
                await conn.execute(
                    "UPDATE users SET balance = balance + $1, total_spent = GREATEST(0, total_spent - $1) WHERE tg_user_id = $2",
                    order["price"],
                    order["tg_user_id"],
                )
                if order["referral_user_id"] and order["referral_bonus"]:
                    balance = await conn.fetchval("SELECT balance FROM users WHERE tg_user_id=$1", order['referral_user_id'])
                    recovered = min(balance or 0, order['referral_bonus'])
                    await conn.execute(
                        "UPDATE users SET balance = balance - $1 WHERE tg_user_id = $2",
                        recovered,
                        order["referral_user_id"],
                    )
                    remaining = round(order['referral_bonus'] - recovered, 4)
                    if remaining > 0:
                        await conn.execute(
                            "INSERT INTO referral_recoveries(order_id,tg_user_id,outstanding) VALUES($1,$2,$3)",
                            order_id, order['referral_user_id'], remaining,
                        )
                        await record(conn, 'referral_recovery_needed', f"Order #{order_id}: {remaining:.4f} remains to recover")
                await conn.execute("UPDATE orders SET status = 'refunded', delivery_status = 'cancelled' WHERE id = $1", order_id)
                await conn.execute(
                    "UPDATE outbox SET status='cancelled' WHERE (order_id=$1 OR about_order_id=$1) AND status IN ('pending','failed')", order_id
                )
                await record(
                    conn,
                    "refund_order",
                    f"Refunded Order #{order_id} ({order['product_title']}) for {order['price']:.2f} to user {order['tg_user_id']}",
                )
        except Exception as exc:
            logger.exception("Refund of order %s failed", order_id)
            return False, f"Refund failed: {type(exc).__name__}"

        symbol = escape(await self.settings.get("currency_symbol"))
        self.notifier.in_background(
            self.notifier.send(
                order["tg_user_id"],
                f"{ICON_CHECK} <b>Order Refunded</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ICON_ORDERS} <b>Order ID:</b> <code>#{order_id}</code>\n"
                f"{ICON_VIP} <b>Product:</b> {escape(order['product_title'])}\n"
                f"{ICON_MONEY} <b>Refunded to Wallet:</b> <code>+{order['price']:.2f} {symbol}</code>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<i>টাকা আপনার ওয়ালেট ব্যালেন্সে ফেরত দেওয়া হয়েছে।</i>",
            )
        )
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

