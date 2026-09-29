"""Transactional wallet purchases, instant stock delivery, manual fulfillment and refunds."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import time
from collections import Counter
from decimal import Decimal
from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.formatting import price
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_CHECK,
    ICON_CROSS,
    ICON_ID,
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
from app.services.admin_jobs import enqueue as enqueue_admin_job
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
        upstream_reseller: Any = None,
        suppliers: Any = None,
    ):
        self.db = db
        self.settings = settings
        self.delivery = delivery
        self.notifier = notifier
        self.upstream_reseller = upstream_reseller
        self.suppliers = suppliers
        # Stock warnings fire on the way down, once per sale. Without a quiet period
        # a product falling from three to nothing sends four separate messages, and
        # a catalogue of thirty buries the owner. Set by build_services.
        self.rate_limits = None

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

                # 3. Check delivery type & supplier routing
                is_manual = product.get("delivery_type") == "manual"
                upstream_prod_id = product.get("upstream_product_id")
                stock_item_ids: list[int] = []
                supplier_code = product.get("supplier_code") or "digital_mart"
                supplier_order_id = None
                supplier_error = None

                supplier = None
                if upstream_prod_id:
                    if self.suppliers:
                        supplier = self.suppliers.get(supplier_code)
                    if not supplier and self.upstream_reseller and self.upstream_reseller.is_configured:
                        supplier = self.upstream_reseller

                if upstream_prod_id and supplier and supplier.is_configured:
                    upstream_devices = int(product.get("upstream_devices") or 1)
                    upstream_share_hours = int(product.get("upstream_share_hours") or 24)

                    # Step 1: If multi-device sharing is enabled, check if an existing shared account has free seats
                    claimed_seats = None
                    if upstream_devices > 1:
                        claimed_seats = await InventoryService.claim_seats(db, product_id, tg_user_id, count=quantity)

                    if claimed_seats and len(claimed_seats) >= quantity:
                        # Reusing existing shared account from pool - 0 extra supplier charge!
                        delivered_content = "\n".join(item["content"] for item in claimed_seats)
                        source = "stock"
                        fulfillment = "delivered"
                        stock_item_ids = [item["id"] for item in claimed_seats]
                    else:
                        # Instant pre-check: ensure our unit_price is not lower than known wholesale rate
                        known_wholesale = float(product.get("reseller_price") or 0.0)
                        supplier_order_qty = 1 if upstream_devices > 1 else quantity
                        if known_wholesale > 0 and (known_wholesale * supplier_order_qty) > float(total_price):
                            await db.execute("ROLLBACK")
                            return False, "⚠️ The wholesale price for this product has recently updated. Please re-open the product to purchase at the current price.", None

                        # Instant fulfillment via upstream supplier API
                        custom_id = f"ord_{tg_user_id}_{product_id}_{int(time.time())}"
                        upstream_resp = await supplier.purchase(
                            product_id=int(upstream_prod_id),
                            quantity=supplier_order_qty,
                            custom_id=custom_id,
                        )

                        fallback_enabled = await self.settings.flag("supplier_fallback_to_waiting")
                        if not upstream_resp.get("success"):
                            err_msg = upstream_resp.get("detail") or "Failed to purchase from supplier"
                            is_low_balance = upstream_resp.get("insufficient_balance", False)

                            # Graceful fallback: do NOT fail customer order if supplier is low on balance or temporarily down
                            if fallback_enabled or is_low_balance:
                                delivered_content = ""
                                source = "supplier_pending"
                                fulfillment = "waiting"
                                supplier_error = str(err_msg)
                                waiting_reason = f"Supplier fulfillment pending: {err_msg}"
                                if hasattr(supplier, "check_low_balance"):
                                    self.notifier.in_background(supplier.check_low_balance(self.notifier))
                            else:
                                await db.execute("ROLLBACK")
                                return False, f"⚠️ Provider notice: {err_msg}", None
                        else:
                            supplier_order_id = str(upstream_resp.get("order_id") or "")
                            charged_cost = float(upstream_resp.get("total_price") or upstream_resp.get("unit_price") or 0.0)
                            if getattr(supplier, "currency", "BDT") == "USDT":
                                charged_cost_bdt = round(charged_cost * usd_rate, 2)
                            else:
                                charged_cost_bdt = charged_cost

                            # Post-purchase Loss Shield: verify actual deducted cost
                            if upstream_devices <= 1 and charged_cost_bdt > float(total_price):
                                admin_ids = await self.settings.admin_chat_ids()
                                alert_text = (
                                    f"⚠️ <b>Loss Shield Alert: Price Jump Detected!</b>\n\n"
                                    f"Product: <b>{product['title']}</b> (Supplier: {getattr(supplier, 'name', supplier_code)} #{upstream_prod_id})\n"
                                    f"Customer Paid: <code>৳{float(total_price):.2f}</code>\n"
                                    f"Supplier Deducted: <code>৳{charged_cost_bdt:.2f}</code>\n"
                                    f"Difference: <code>-৳{charged_cost_bdt - float(total_price):.2f} BDT</code>\n\n"
                                    f"The supplier has increased their wholesale rate. Please check and adjust retail pricing in the admin console."
                                )
                                for aid in admin_ids:
                                    self.notifier.in_background(self.notifier.send(aid, alert_text))

                            delivered_content = upstream_resp.get("credentials") or upstream_resp.get("delivered_item") or upstream_resp.get("message") or ""
                            source = "upstream_reseller"
                            fulfillment = upstream_resp.get("fulfillment") or ("delivered" if delivered_content else "waiting")
                            if fulfillment == "waiting":
                                waiting_reason = "Supplier processing order"
                            elif upstream_devices > 1 and delivered_content:
                                # Save fresh multi-device account to local inventory pool!
                                exp_dt = datetime.now(timezone.utc) + timedelta(hours=upstream_share_hours) if upstream_share_hours > 0 else None
                                new_inv_id = await db.fetchval(
                                    """
                                    INSERT INTO inventory_items (product_id, content, max_uses, uses, status, expires_at)
                                    VALUES ($1, $2, $3, 0, 'available', $4)
                                    RETURNING id
                                    """,
                                    product_id,
                                    delivered_content,
                                    upstream_devices,
                                    exp_dt,
                                )
                                stock_item_ids = [new_inv_id] * quantity
                elif is_manual:
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
                                        fulfilled_at, quantity, unit_price, supplier_code, supplier_order_id, supplier_error)
                    VALUES ($1, $2, $3, $4, $5, $6, 'completed', $7, 'pending', $8, $9, $10, CASE WHEN $8 = 'delivered' THEN now() ELSE NULL END, $11, $12, $13, $14, $15)
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
                    supplier_code if (upstream_prod_id and supplier) else None,
                    supplier_order_id,
                    supplier_error,
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
                order["supplier_code"] = order_row.get("supplier_code")
                order["supplier_error"] = order_row.get("supplier_error")
                if fulfillment == "waiting":
                    await self.delivery.enqueue_waiting_notice(tg_user_id, order, conn=db)
                else:
                    await self.delivery.enqueue_order(tg_user_id, order, conn=db)
                await enqueue_admin_job(db, "order", order_id, {
                    "user": {k: user[k] for k in ("username", "tg_user_id")},
                    "order": {k: order[k] for k in ("order_id", "product_id", "product_title", "price")},
                    "reason": waiting_reason,
                    "supplier_code": order_row.get("supplier_code"),
                    "supplier_error": order_row.get("supplier_error"),
                })
                await db.execute("COMMIT")
            except Exception as exc:
                if db.is_in_transaction():
                    await db.execute("ROLLBACK")
                logger.exception("Purchase error: %s", exc)
                return False, "Purchase could not be completed. Please contact support before retrying.", None

        # The customer gets the result now; the admin alert must not add a Telegram round trip.
        # The admin job committed with the order; the worker delivers it.
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
            is_supplier = bool(order.get("supplier_code") or order.get("supplier_error") or "Supplier" in waiting_reason)
            if is_supplier:
                heading = f"{ICON_WARNING} <b>Supplier Fulfillment Pending</b>"
                delivery = f"{ICON_WARNING} <b>Fulfillment:</b> Pending Supplier"
                if order.get("supplier_error"):
                    delivery += f"\n⚠️ <b>Issue:</b> <code>{escape(str(order['supplier_error']))}</code>"
            else:
                heading = f"{ICON_WARNING} <b>Manual Order Action Required</b>"
                delivery = f"{ICON_WARNING} <b>Delivery:</b> Manual"

            rows = []
            if is_supplier:
                rows.append([
                    InlineKeyboardButton(
                        text="⚡ Retry Supplier Delivery",
                        callback_data=f"adm_ord_sup_retry_{order_id}",
                        style="primary",
                        icon_custom_emoji_id=Icons.REFRESH,
                    )
                ])
            rows.append([
                InlineKeyboardButton(
                    text="📦 Deliver Manually",
                    callback_data=f"adm_ord_deliver_{order_id}",
                    style="success",
                    icon_custom_emoji_id=Icons.ORDERS,
                ),
                InlineKeyboardButton(
                    text="🔄 Refund",
                    callback_data=f"adm_ord_ref_ask_{order_id}",
                    style="danger",
                    icon_custom_emoji_id=Icons.SPENT,
                ),
            ])
            if console:
                rows.append([
                    InlineKeyboardButton(
                        text="Open in Console",
                        url=f"{console}/#orders/{order_id}",
                        icon_custom_emoji_id=Icons.NOTE,
                    )
                ])
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        else:
            heading = f"{ICON_SHOP} <b>New Order Received</b>"
            delivery = f"{ICON_CHECK} <b>Delivery:</b> Instant"

        stock_warning = ""
        rem_stock = None
        threshold = 3
        prod_id = order.get("product_id")
        if prod_id and not waiting_reason:
            try:
                threshold = int(await self.settings.number("low_stock_threshold"))
            except Exception:
                threshold = 3
            try:
                async with self.db.connect() as conn:
                    rem_stock = await conn.fetchval(
                        "SELECT COUNT(*) FROM inventory_items WHERE product_id = $1 AND status = 'available' AND (expires_at IS NULL OR expires_at > now())",
                        prod_id,
                    )
                if rem_stock is not None:
                    if rem_stock == 0:
                        stock_warning = f"\n{ICON_WARNING} <b>Stock Alert:</b> Product is now <b>OUT OF STOCK!</b> (<code>0</code> left)"
                    elif rem_stock <= threshold:
                        stock_warning = f"\n{ICON_WARNING} <b>Stock Alert:</b> Low stock (<code>{rem_stock}</code> left)"
            except Exception:
                pass

        msg_text = (
            f"{heading}\n\n"
            f"{ICON_ORDERS} <b>Order:</b> <code>#{order_id}</code>\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> {customer}\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>{user['tg_user_id']}</code>\n"
            f"{ICON_VIP} <b>Product:</b> {escape(order['product_title'])}\n"
            f"{ICON_MONEY} <b>Price:</b> <code>{price(symbol, order['price'], usd_rate=usd_rate, show_usd=show_usd)}</code>\n"
            f"{delivery}{stock_warning}"
        )
        await self.notifier.send_admin(
            msg_text,
            event="waiting_order" if waiting_reason else "order",
            keyboard=keyboard,
        )

        # Dedicated Low Stock & Out of Stock Alert for store administrators
        # Ask the budget only when there is actually something to say, or a sale that
        # leaves plenty of stock would spend the quiet period and silence the warning
        # that matters a few sales later.
        worth_saying = rem_stock is not None and (rem_stock == 0 or rem_stock <= threshold)
        if worth_saying and await self._stock_alert_is_due(prod_id, rem_stock):
            if rem_stock == 0:
                # The alert is the moment stock is on the owner's mind, so the fix
                # belongs on it rather than behind a browser and a login.
                rows = [[InlineKeyboardButton(
                    text="Add stock here",
                    callback_data=f"adm_stock_{prod_id}",
                    style="success",
                    icon_custom_emoji_id=Icons.PLUS,
                )]]
                if console:
                    rows.append([InlineKeyboardButton(
                        text="Open in console",
                        url=f"{console}/#inventory",
                        icon_custom_emoji_id=Icons.PRODUCTS,
                    )])
                low_stock_kb = InlineKeyboardMarkup(inline_keyboard=rows)
                alert_text = (
                    f"{ICON_CROSS} <b>Product Out of Stock!</b>\n\n"
                    f"{ICON_VIP} <b>Product:</b> {escape(order['product_title'])}\n"
                    f"{ICON_SHOP} <b>Available Stock:</b> <code>0</code>\n"
                    f"{ICON_CROSS} <b>Status:</b> Sold Out"
                )
                await self.notifier.send_admin(
                    alert_text,
                    event="low_stock",
                    keyboard=low_stock_kb,
                )
            elif rem_stock <= threshold:
                # The alert is the moment stock is on the owner's mind, so the fix
                # belongs on it rather than behind a browser and a login.
                rows = [[InlineKeyboardButton(
                    text="Add stock here",
                    callback_data=f"adm_stock_{prod_id}",
                    style="success",
                    icon_custom_emoji_id=Icons.PLUS,
                )]]
                if console:
                    rows.append([InlineKeyboardButton(
                        text="Open in console",
                        url=f"{console}/#inventory",
                        icon_custom_emoji_id=Icons.PRODUCTS,
                    )])
                low_stock_kb = InlineKeyboardMarkup(inline_keyboard=rows)
                alert_text = (
                    f"{ICON_WARNING} <b>Low Stock Warning!</b>\n\n"
                    f"{ICON_VIP} <b>Product:</b> {escape(order['product_title'])}\n"
                    f"{ICON_SHOP} <b>Available Stock:</b> <code>{rem_stock}</code>\n"
                    f"{ICON_TIMER} <b>Threshold:</b> <code>{threshold}</code>"
                )
                await self.notifier.send_admin(
                    alert_text,
                    event="low_stock",
                    keyboard=low_stock_kb,
                )

    STOCK_ALERT_QUIET_SECONDS = 6 * 60 * 60

    async def _stock_alert_is_due(self, product_id: Any, remaining: int) -> bool:
        """One warning per product per quiet period, and one more when it hits zero.

        The warning fires on every sale while stock sits at or below the threshold, so a
        product falling from three to nothing used to send four messages. Selling out is
        counted separately, because that is a different thing to know and must not be
        swallowed by the warning that came before it."""
        if self.rate_limits is None:
            return True
        scope = "stock-empty" if remaining == 0 else "stock-low"
        try:
            return not await self.rate_limits.consume(
                scope, str(product_id), 1, self.STOCK_ALERT_QUIET_SECONDS)
        except Exception:
            logger.exception("Could not check the stock alert budget; alerting anyway")
            return True

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

    async def retry_supplier_fulfillment(self, order_id: int) -> tuple[bool, str, dict[str, Any] | None]:
        """Retry ordering an upstream product from the supplier when balance or error is resolved."""
        symbol = await self.settings.get("currency_symbol")
        usd_rate = await self.settings.number("usd_rate")
        show_usd = await self.settings.flag("show_usd_price")

        async with self.db.transaction() as conn:
            order = await conn.fetchrow("SELECT * FROM orders WHERE id = $1 FOR UPDATE", order_id)
            if not order:
                return False, "Order not found.", None
            if order["status"] != "completed" or order["fulfillment"] != "waiting":
                return False, f"Order is not in waiting state (status: {order['status']}, fulfillment: {order['fulfillment']}).", None

            product = await conn.fetchrow("SELECT * FROM products WHERE id = $1", order["product_id"])
            if not product:
                return False, "Product no longer exists in database.", None

            upstream_prod_id = product.get("upstream_product_id")
            if not upstream_prod_id:
                return False, "This product is not linked to any upstream supplier.", None

            supplier_code = order.get("supplier_code") or product.get("supplier_code") or "digital_mart"
            supplier = self.suppliers.get(supplier_code) if self.suppliers else self.upstream_reseller
            if not supplier or not supplier.is_configured:
                return False, f"Supplier '{supplier_code}' is not configured.", None

            upstream_devices = int(product.get("upstream_devices") or 1)
            upstream_share_hours = int(product.get("upstream_share_hours") or 24)
            quantity = int(order.get("quantity") or 1)
            supplier_order_qty = 1 if upstream_devices > 1 else quantity

            custom_id = f"ord_retry_{order['tg_user_id']}_{order['id']}_{int(time.time())}"
            upstream_resp = await supplier.purchase(
                product_id=int(upstream_prod_id),
                quantity=supplier_order_qty,
                custom_id=custom_id,
            )

            if not upstream_resp.get("success"):
                err_msg = upstream_resp.get("detail") or "Supplier error"
                await conn.execute("UPDATE orders SET supplier_error = $1 WHERE id = $2", str(err_msg), order_id)
                return False, f"Supplier error: {err_msg}", None

            # Success!
            delivered_content = upstream_resp.get("credentials") or upstream_resp.get("delivered_item") or upstream_resp.get("message") or ""
            supplier_order_id = str(upstream_resp.get("order_id") or "")
            fulfillment = upstream_resp.get("fulfillment") or ("delivered" if delivered_content else "waiting")

            updated_row = await conn.fetchrow(
                """
                UPDATE orders
                SET delivered_item = $1,
                    fulfillment = $2,
                    source = 'upstream_reseller',
                    supplier_order_id = $3,
                    supplier_error = NULL,
                    fulfilled_at = CASE WHEN $2 = 'delivered' THEN now() ELSE NULL END,
                    delivery_status = 'pending'
                WHERE id = $4
                RETURNING *
                """,
                delivered_content,
                fulfillment,
                supplier_order_id,
                order_id,
            )

            if upstream_devices > 1 and delivered_content:
                exp_dt = datetime.now(timezone.utc) + timedelta(hours=upstream_share_hours) if upstream_share_hours > 0 else None
                new_inv_id = await conn.fetchval(
                    """
                    INSERT INTO inventory_items (product_id, content, max_uses, uses, status, expires_at)
                    VALUES ($1, $2, $3, $4, 'available', $5)
                    RETURNING id
                    """,
                    order["product_id"],
                    delivered_content,
                    upstream_devices,
                    quantity,
                    exp_dt,
                )
                await conn.execute("UPDATE orders SET inventory_item_id = $1 WHERE id = $2", new_inv_id, order_id)

            if fulfillment == "delivered":
                delivered_order = _receipt_fields(updated_row, 0)
                delivered_order["currency_symbol"] = symbol
                delivered_order["usd_rate"] = usd_rate
                delivered_order["show_usd"] = show_usd
                await self.delivery.enqueue_order(order["tg_user_id"], delivered_order, conn=conn)

            await record(conn, "supplier_order_retried", f"Order #{order_id} fulfilled via supplier {supplier_code}")

        return True, f"Supplier fulfillment successful! Status: {fulfillment}", dict(updated_row)

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
        refund_customer_msg = (
            f"{ICON_CHECK} <b>Order Refunded</b>\n\n"
            f"{ICON_ORDERS} <b>Order ID:</b> <code>#{order_id}</code>\n"
            f"{ICON_VIP} <b>Product:</b> {escape(order['product_title'])}\n"
            f"{ICON_MONEY} <b>Refunded to Wallet:</b> <code>+{order['price']:.2f} {symbol}</code>\n\n"
            f"<i>Amount has been refunded to your wallet balance.</i>"
        )
        self.notifier.in_background(
            self.notifier.send(order["tg_user_id"], refund_customer_msg)
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

