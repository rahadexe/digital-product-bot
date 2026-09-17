"""Supplier (wholesaler) API: destination checks, HTTP client, catalog sync and payment reconciliation."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import uuid
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings, get_settings
from app.core.money import money
from app.db import Database, affected
from app.services.audit import record
from app.services.errors import InvalidInputError, NotFoundError

if TYPE_CHECKING:
    from app.services.settings import SettingsService

logger = logging.getLogger("app.services.supplier")

DEFAULT_API_URL = "https://safwantigershopbot-production.up.railway.app/api"


def validate_supplier_url(value: str, config: Settings | None = None) -> str:
    config = config or get_settings()
    parsed = urlsplit(value)
    allowed = {host.lower() for host in Settings.split(config.supplier_allowed_hosts)}
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (
        parsed.scheme != 'https'
        or (parsed.hostname or '').lower() not in allowed
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError('Supplier URL must be HTTPS on an explicitly configured SUPPLIER_ALLOWED_HOSTS host.')
    return value.rstrip('/')


async def validate_supplier_dns(value: str, config: Settings | None = None) -> None:
    host = urlsplit(validate_supplier_url(value, config)).hostname
    addresses = await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Supplier must resolve to public network addresses.')


def _disconnected(error: str) -> dict[str, Any]:
    return {
        "connected": False,
        "balance": 0.0,
        "currency": "USDT",
        "orders": 0,
        "total_spent": 0.0,
        "recent_spent": 0.0,
        "error": error,
    }


def _reported_stock(item: dict[str, Any]) -> int:
    if item.get("available") is False:
        return 0
    try:
        return max(0, min(int(item.get("stock") or 0), 1_000_000))
    except (TypeError, ValueError):
        return 0


class SupplierClient:
    """One supplier endpoint. After a failed order, ``order_outcome`` says whether it may have charged."""

    def __init__(self, api_url: str, api_key: str, config: Settings | None = None):
        self.config = config
        self.api_url = validate_supplier_url(api_url, config)
        self.api_key = api_key or ""
        self.order_outcome = "not_charged"

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get_balance(self) -> dict[str, Any]:
        if not self.api_key:
            return _disconnected("Supplier API key is not configured.")
        try:
            await validate_supplier_dns(self.api_url, self.config)
            async with httpx.AsyncClient(timeout=12.0) as client:
                response = await client.get(f"{self.api_url}/balance", headers=self._headers())
            if response.status_code != 200:
                return _disconnected(f"Supplier request failed (HTTP {response.status_code}).")
            data = response.json()
            return {
                "connected": True,
                "balance": money(data.get("balance", 0.0)),
                "currency": str(data.get("currency", "USDT"))[:10],
                "orders": int(data.get("orders", 0)),
                "total_spent": money(data.get("total_spent", 0.0)),
                "recent_spent": money(data.get("recent_spent", 0.0)),
                "error": None,
            }
        except Exception as exc:
            logger.error("Error fetching supplier balance: %s", type(exc).__name__)
            return _disconnected("Supplier connection failed.")

    async def get_products(self) -> list[dict[str, Any]]:
        if not self.api_key:
            logger.warning("Supplier products requested without a configured API key.")
            return []
        try:
            await validate_supplier_dns(self.api_url, self.config)
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{self.api_url}/products", headers=self._headers())
            if response.status_code != 200:
                logger.warning("Supplier products returned status %d", response.status_code)
                return []
            products = response.json().get("products", [])
            return [item for item in products if isinstance(item, dict) and str(item.get("id", "")).isdigit()]
        except Exception as exc:
            logger.error("Error fetching supplier products: %s", type(exc).__name__)
            return []

    async def place_order(
        self, supplier_product_id: int, quantity: int = 1, request_id: str | None = None
    ) -> tuple[bool, str, str | None]:
        """Returns (success, message, delivered item)."""
        self.order_outcome = "not_charged"
        if not self.api_key:
            return False, "Supplier API key is not configured.", None
        payload = {
            "product_id": int(supplier_product_id),
            "quantity": int(quantity),
            "request_id": request_id or f"ord-{uuid.uuid4().hex[:12]}",
        }
        try:
            await validate_supplier_dns(self.api_url, self.config)
            async with httpx.AsyncClient(timeout=30.0) as client:
                self.order_outcome = "unknown"
                response = await client.post(f"{self.api_url}/order", json=payload, headers=self._headers())
            if response.status_code == 200:
                data = response.json()
                delivered = (
                    data.get("delivered")
                    or data.get("item")
                    or data.get("delivered_item")
                    or data.get("items")
                    or data.get("credentials")
                    or data.get("code")
                )
                if isinstance(delivered, list):
                    text = "\n".join(str(item) for item in delivered)
                elif isinstance(delivered, dict):
                    text = "\n".join(f"{key}: {value}" for key, value in delivered.items())
                else:
                    text = str(delivered or "")
                if not text:
                    return False, "Supplier response is incomplete. Contact support before retrying.", None
                self.order_outcome = "fulfilled"
                return True, "Supplier order fulfilled successfully.", text
            if response.status_code == 402:
                self.order_outcome = "not_charged"
                return False, "Insufficient supplier API balance. Please contact administrator.", None
            return False, f"Supplier could not complete the request (HTTP {response.status_code}).", None
        except Exception as exc:
            logger.error("Exception placing order with supplier: %s", type(exc).__name__)
            return False, "Supplier connection failed. Contact support before retrying.", None


def _category_for(title: str, categories: dict[str, int]) -> int | None:
    text = title.lower()
    for keywords, name in (
        (("gpt", "gemini", "claude", "ai", "grok", "elevenlabs", "lovable", "manus"), "ai"),
        (("vpn", "surfshark", "nord"), "vpn"),
        (("youtube", "netflix", "spotify", "duolingo", "coursera", "stream"), "streaming"),
        (("capcut", "canva", "figma", "adobe", "quillbot"), "software"),
    ):
        if any(keyword in text for keyword in keywords):
            return categories.get(name)
    return categories.get("tools")


def _icon_for(title: str) -> str:
    text = title.lower()
    for keywords, icon in (
        (("gpt",), "🤖"),
        (("gemini",), "✨"),
        (("claude",), "🧠"),
        (("vpn",), "🛡️"),
        (("youtube",), "▶️"),
        (("canva", "figma", "adobe"), "🎨"),
        (("capcut",), "🎬"),
    ):
        if any(keyword in text for keyword in keywords):
            return icon
    return "⚡"


def _initial_price(cost: float, markup_percent: float, fixed_markup: float) -> float:
    if markup_percent == 25.0 and fixed_markup == 0.0:
        # Default tiers give cheap items a usable margin and expensive items a modest one.
        if cost <= 0.20:
            retail = cost + 0.20
        elif cost <= 1.50:
            retail = cost * 1.60
        elif cost <= 10.0:
            retail = cost * 1.30
        else:
            retail = cost * 1.15
    else:
        retail = cost * (1 + markup_percent / 100.0) + fixed_markup
    retail = round(retail, 2)
    return money(0.50 if retail <= 0.05 else retail, positive=True)


class SupplierService:
    def __init__(self, db: Database, settings: "SettingsService", config: Settings):
        self.db = db
        self.settings = settings
        self.config = config

    async def client(self) -> SupplierClient:
        url, key = await self.settings.supplier_credentials()
        return SupplierClient(url or DEFAULT_API_URL, key, self.config)

    async def status(self) -> dict[str, Any]:
        client = await self.client()
        balance = await client.get_balance()
        async with self.db.connect() as conn:
            synced = await conn.fetchval("SELECT COUNT(*) FROM products WHERE supplier_product_id IS NOT NULL")
        return {**balance, "synced_products_count": synced, "api_url": client.api_url}

    async def catalog(self) -> dict[str, Any]:
        remote = await (await self.client()).get_products()
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                "SELECT id, title, price, is_active, supplier_product_id FROM products WHERE supplier_product_id IS NOT NULL"
            )
        local = {row["supplier_product_id"]: dict(row) for row in rows}
        products = []
        for item in remote:
            match = local.get(int(item["id"]))
            products.append(
                {
                    **item,
                    "local_product_id": match["id"] if match else None,
                    "local_price": match["price"] if match else None,
                    "is_in_shop": bool(match and match["is_active"]),
                }
            )
        return {"products": products, "total": len(products)}

    async def set_retail_price(self, supplier_product_id: int, price: float) -> None:
        price = money(price, positive=True)
        async with self.db.transaction() as conn:
            status = await conn.execute(
                "UPDATE products SET price = $1 WHERE supplier_product_id = $2", price, supplier_product_id
            )
            if not affected(status):
                raise NotFoundError("Product not found in local store.")
            await record(conn, "supplier_price_set", f"Supplier product #{supplier_product_id} retail price {price:.2f}")

    async def sync(
        self, markup_percent: float = 25.0, fixed_markup: float = 0.0, overwrite_prices: bool = False
    ) -> dict[str, Any]:
        """Import the supplier catalog. Custom prices survive unless ``overwrite_prices`` is set."""
        markup_percent = money(markup_percent)
        fixed_markup = money(fixed_markup)
        if not 0 <= markup_percent <= 1000 or fixed_markup < 0:
            raise InvalidInputError("Supplier markup is outside the supported range.")
        remote = await (await self.client()).get_products()
        if not remote:
            return {"success": False, "message": "No products returned from supplier API.", "synced": 0}

        created = updated = 0
        async with self.db.transaction() as conn:
            categories = {row["lname"]: row["id"] for row in await conn.fetch("SELECT id, lower(name) AS lname FROM categories")}
            for item in remote:
                supplier_id = int(item["id"])
                title = str(item.get("name") or f"Supplier Product #{supplier_id}")[:200]
                cost = money(item.get("price", 1.0), positive=True)
                description = str(
                    item.get("description") or item.get("warranty") or "Instant delivery via automated supplier API."
                )[:4000]
                stock = _reported_stock(item)
                existing = await conn.fetchrow(
                    # A product of your own with the same name is linked, never one already tied to another supplier item.
                    "SELECT id, price FROM products WHERE supplier_product_id = $1 "
                    "OR (supplier_product_id IS NULL AND lower(title) = lower($2)) ORDER BY supplier_product_id NULLS LAST LIMIT 1",
                    supplier_id,
                    title,
                )
                if existing:
                    retail = (
                        money(round(cost * (1 + markup_percent / 100.0) + fixed_markup, 2), positive=True)
                        if overwrite_prices
                        else existing["price"]
                    )
                    await conn.execute(
                        """
                        UPDATE products SET supplier_product_id = $1, supplier_price = $2, supplier_stock = $3,
                               price = $4, description = $5
                        WHERE id = $6
                        """,
                        supplier_id,
                        cost,
                        stock,
                        retail,
                        description,
                        existing["id"],
                    )
                    updated += 1
                else:
                    await conn.execute(
                        """
                        INSERT INTO products (category_id, title, description, price, icon, duration_label, sort_order,
                                              is_active, supplier_product_id, supplier_price, supplier_stock)
                        VALUES ($1, $2, $3, $4, $5, 'Instant', 0, 1, $6, $7, $8)
                        """,
                        _category_for(title, categories),
                        title,
                        description,
                        _initial_price(cost, markup_percent, fixed_markup),
                        _icon_for(title),
                        supplier_id,
                        cost,
                        stock,
                    )
                    created += 1
            # What the supplier no longer lists cannot be bought from it; an archived product stays archived.
            await conn.execute(
                "UPDATE products SET supplier_stock = 0 WHERE supplier_product_id IS NOT NULL AND NOT (supplier_product_id = ANY($1::bigint[]))",
                [int(item["id"]) for item in remote],
            )
            await record(conn, "supplier_sync", f"Created {created}, updated {updated}; overwrite prices: {overwrite_prices}")
        return {
            "success": True,
            "total_supplier_products": len(remote),
            "created": created,
            "updated": updated,
            "synced": created + updated,
        }

    async def unresolved_attempts(self) -> list[dict[str, Any]]:
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                "SELECT * FROM supplier_purchase_attempts WHERE status IN ('pending', 'review') ORDER BY id DESC LIMIT 200"
            )
        return [dict(row) for row in rows]

    async def release_attempt(self, attempt_id: int, reason: str) -> None:
        async with self.db.transaction() as conn:
            status = await conn.execute(
                "UPDATE supplier_purchase_attempts SET status = 'failed' WHERE id = $1 AND status IN ('pending', 'review')",
                attempt_id,
            )
            if not affected(status):
                raise NotFoundError("Unresolved supplier attempt not found.")
            await record(
                conn, "supplier_retry_released", f"Attempt #{attempt_id}; admin verified no fulfillment or charge. {reason}"
            )
