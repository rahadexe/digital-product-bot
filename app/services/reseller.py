"""Reseller API keys, authentication, catalog rates, and order tracking."""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

from app.db import Database
from app.services.catalog import CatalogService
from app.services.errors import InvalidInputError, NotFoundError, PermissionDeniedError
from app.services.settings import SettingsService
from app.services.users import UserService

logger = logging.getLogger("app.services.reseller")


class ResellerService:
    def __init__(
        self,
        db: Database,
        settings: SettingsService,
        catalog: CatalogService,
        users: UserService,
    ):
        self.db = db
        self.settings = settings
        self.catalog = catalog
        self.users = users

    async def generate_key(self, tg_user_id: int, name: str = "Default Key") -> tuple[str, dict[str, Any]]:
        """
        Generate a cryptographically secure API key for an authorized reseller.
        Revokes previous active keys for this user and returns (raw_key, record).
        """
        user = await self.users.get(tg_user_id)
        if not user:
            raise NotFoundError("User not found.")
        if user.get("is_banned"):
            raise PermissionDeniedError("Account is banned.")

        rank = (user.get("rank") or "").strip().lower()
        if rank != "reseller":
            raise PermissionDeniedError("Only authorized Resellers can generate an API key.")

        # Cryptographically strong token
        raw_key = f"rk_live_{secrets.token_hex(24)}"
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key_prefix = f"{raw_key[:12]}...{raw_key[-4:]}"

        async with self.db.transaction() as conn:
            # Revoke previous active keys for this user
            await conn.execute(
                "UPDATE reseller_api_keys SET is_active = 0 WHERE tg_user_id = $1 AND is_active = 1",
                tg_user_id,
            )
            # Insert newly minted key
            row = await conn.fetchrow(
                """
                INSERT INTO reseller_api_keys (user_id, tg_user_id, key_prefix, key_hash, name, is_active)
                VALUES ($1, $2, $3, $4, $5, 1)
                RETURNING id, user_id, tg_user_id, key_prefix, name, is_active, created_at, last_used_at
                """,
                user["id"],
                tg_user_id,
                key_prefix,
                key_hash,
                name[:64],
            )

        logger.info("Generated new Reseller API key for tg_user_id=%d prefix=%s", tg_user_id, key_prefix)
        return raw_key, dict(row)

    async def get_active_key(self, tg_user_id: int) -> dict[str, Any] | None:
        """Fetch metadata for the active API key of a reseller (raw key is never stored)."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, tg_user_id, key_prefix, name, is_active, created_at, last_used_at
                FROM reseller_api_keys
                WHERE tg_user_id = $1 AND is_active = 1
                LIMIT 1
                """,
                tg_user_id,
            )
            return dict(row) if row else None

    async def revoke_key(self, tg_user_id: int) -> bool:
        """Deactivate all active keys for a reseller."""
        async with self.db.transaction() as conn:
            result = await conn.execute(
                "UPDATE reseller_api_keys SET is_active = 0 WHERE tg_user_id = $1 AND is_active = 1",
                tg_user_id,
            )
            # Result is e.g. "UPDATE 1"
            count = int(result.split(" ")[-1]) if " " in result else 0
            return count > 0

    async def authenticate_key(self, raw_key: str) -> dict[str, Any] | None:
        """
        Authenticate an API request by raw key.
        Returns a dictionary containing the reseller user and key metadata if valid, else None.
        """
        if not raw_key or not isinstance(raw_key, str):
            return None
        raw_key = raw_key.strip()
        if not raw_key.startswith("rk_"):
            return None

        key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                SELECT k.id AS key_id, k.key_prefix, k.created_at AS key_created_at, k.last_used_at,
                       u.id AS user_id, u.tg_user_id, u.username, u.first_name, u.last_name,
                       u.balance, u.total_spent, u.rank, u.is_banned
                FROM reseller_api_keys k
                JOIN users u ON u.id = k.user_id
                WHERE k.key_hash = $1 AND k.is_active = 1
                """,
                key_hash,
            )
            if not row:
                return None
            if row["is_banned"]:
                return None
            if (row["rank"] or "").strip().lower() != "reseller":
                return None

            # Update last_used_at timestamp asynchronously
            try:
                await conn.execute(
                    "UPDATE reseller_api_keys SET last_used_at = now() WHERE id = $1",
                    row["key_id"],
                )
            except Exception:
                pass

            return dict(row)

    def format_reseller_product(self, product: dict[str, Any]) -> dict[str, Any]:
        """Transform an internal catalog product row into a clean Reseller API schema."""
        reg_price = float(product.get("price") or 0.0)
        reseller_p = product.get("reseller_price")
        if reseller_p is not None and float(reseller_p) > 0:
            effective_price = float(reseller_p)
            has_discount = effective_price < reg_price
        else:
            effective_price = reg_price
            has_discount = False

        discount_pct = round(((reg_price - effective_price) / reg_price) * 100) if (has_discount and reg_price > 0) else 0
        delivery_type = product.get("delivery_type") or "instant"
        stock = int(product.get("stock") or 0) if delivery_type != "manual" else 999
        in_stock = (delivery_type == "manual") or (stock > 0)

        return {
            "id": product["id"],
            "title": product["title"],
            "category_id": product.get("category_id"),
            "category_name": product.get("category_name") or "Uncategorized",
            "description": product.get("description") or "",
            "regular_price": reg_price,
            "reseller_price": effective_price,
            "has_discount": has_discount,
            "discount_percent": discount_pct,
            "stock": stock,
            "in_stock": in_stock,
            "delivery_type": delivery_type,
            "duration": (product.get("duration_label") or "").strip(),
            "icon": product.get("icon") or "⚡",
        }

    async def get_reseller_products(self, category_id: int | None = None) -> list[dict[str, Any]]:
        """Return all active products formatted with reseller rates and live inventory."""
        products = await self.catalog.products(category_id=category_id, active_only=True, limit=500)
        return [self.format_reseller_product(p) for p in products]

    async def get_reseller_product(self, product_id: int) -> dict[str, Any] | None:
        """Fetch a specific product formatted with reseller rate and live inventory."""
        p = await self.catalog.product(product_id)
        if not p or not p.get("is_active"):
            return None
        return self.format_reseller_product(p)

    async def get_reseller_orders(self, tg_user_id: int, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """List orders placed by this reseller."""
        limit = min(max(1, limit), 100)
        offset = max(0, offset)
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                """
                SELECT id, product_id, product_title, price, quantity, unit_price,
                       fulfillment, status, delivered_item, created_at, fulfilled_at
                FROM orders
                WHERE tg_user_id = $1
                ORDER BY id DESC
                LIMIT $2 OFFSET $3
                """,
                tg_user_id,
                limit,
                offset,
            )
            return [
                {
                    "order_id": r["id"],
                    "product_id": r["product_id"],
                    "product_title": r["product_title"],
                    "quantity": r.get("quantity") or 1,
                    "unit_price": float(r.get("unit_price") or r["price"]),
                    "total_price": float(r["price"]),
                    "fulfillment": r["fulfillment"],
                    "status": r["status"],
                    "credentials": r["delivered_item"] if r["fulfillment"] == "delivered" else None,
                    "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                    "fulfilled_at": r["fulfilled_at"].isoformat() if r.get("fulfilled_at") else None,
                }
                for r in rows
            ]

    async def get_reseller_order(self, tg_user_id: int, order_id: int) -> dict[str, Any] | None:
        """Query details and credentials of a single order belonging to this reseller."""
        async with self.db.connect() as conn:
            r = await conn.fetchrow(
                """
                SELECT id, product_id, product_title, price, quantity, unit_price,
                       fulfillment, status, delivered_item, created_at, fulfilled_at
                FROM orders
                WHERE tg_user_id = $1 AND id = $2
                """,
                tg_user_id,
                order_id,
            )
            if not r:
                return None
            return {
                "order_id": r["id"],
                "product_id": r["product_id"],
                "product_title": r["product_title"],
                "quantity": r.get("quantity") or 1,
                "unit_price": float(r.get("unit_price") or r["price"]),
                "total_price": float(r["price"]),
                "fulfillment": r["fulfillment"],
                "status": r["status"],
                "credentials": r["delivered_item"] if r["fulfillment"] == "delivered" else None,
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                "fulfilled_at": r["fulfilled_at"].isoformat() if r.get("fulfilled_at") else None,
            }
