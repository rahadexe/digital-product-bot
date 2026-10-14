"""Client for upstream Digital Mart Reseller API (https://dmb.bmdigital.bd/api/v1/reseller)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.db import Database

logger = logging.getLogger("app.services.upstream_reseller")


class UpstreamResellerService:
    def __init__(self, db: Database, config: Settings, settings: Any = None):
        self.db = db
        self.config = config
        self.settings = settings
        self.base_url = (config.upstream_reseller_url or "https://dmb.bmdigital.bd/api/v1/reseller").rstrip("/")
        self.api_key = config.upstream_reseller_key or ""

    async def _ensure_config(self) -> None:
        if self.settings:
            try:
                db_url = await self.settings.get("upstream_reseller_url")
                db_key = await self.settings.get("upstream_reseller_key")
                if db_url:
                    self.base_url = db_url.rstrip("/")
                self.api_key = db_key or self.config.upstream_reseller_key or ""
            except Exception:
                pass

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "SubsMarket-Reseller-Client/1.0",
        }

    async def get_account(self) -> dict[str, Any] | None:
        """Fetch live reseller account information and wallet balance."""
        await self._ensure_config()
        if not self.is_configured:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/me", headers=self._headers())
                if resp.status_code == 200:
                    return resp.json()
                logger.warning("Upstream reseller /me returned %d: %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("Failed to connect to upstream reseller /me")
        return None

    async def get_products(self) -> list[dict[str, Any]]:
        """Fetch list of products from upstream reseller."""
        await self._ensure_config()
        if not self.is_configured:
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/products", headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("products", [])
                logger.warning("Upstream reseller /products returned %d: %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("Failed to fetch products from upstream reseller")
        return []

    async def purchase(self, product_id: int, quantity: int = 1, custom_id: str = "") -> dict[str, Any]:
        """Purchase product from upstream reseller with instant delivery credentials."""
        await self._ensure_config()
        if not self.is_configured:
            return {"success": False, "detail": "Upstream reseller API not configured."}
        payload = {
            "product_id": product_id,
            "quantity": quantity,
            "custom_id": custom_id or f"order_{product_id}",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.base_url}/orders", json=payload, headers=self._headers())
                try:
                    data = resp.json()
                except Exception:
                    data = {"detail": resp.text}
                if resp.status_code in (200, 201) and data.get("success"):
                    return data
                error_msg = data.get("detail") or data.get("message") or f"Upstream error ({resp.status_code})"
                return {"success": False, "detail": error_msg,
                        "outcome_unknown": resp.status_code >= 500 or resp.status_code == 408 or 200 <= resp.status_code < 300}
        except Exception as exc:
            logger.exception("Failed to purchase from upstream reseller")
            return {"success": False, "detail": str(exc), "outcome_unknown": True}

    async def sync_catalog(self) -> tuple[int, int]:
        """Sync products and categories from upstream reseller to local database.
        Returns (categories_synced, products_synced).
        """
        products = await self.get_products()
        if not products:
            return 0, 0

        cats_synced = 0
        prods_synced = 0

        async with self.db.transaction() as conn:
            for p in products:
                cat_name = (p.get("category_name") or "Others").strip()
                if cat_name.lower() in ("uncategorized", "uncat", "none"):
                    cat_name = "Others"
                cat_row = await conn.fetchrow("SELECT id FROM categories WHERE LOWER(name) = LOWER($1)", cat_name)
                if cat_row:
                    cat_id = cat_row["id"]
                else:
                    cat_id = await conn.fetchval(
                        "INSERT INTO categories (name, icon, sort_order) VALUES ($1, $2, 99) RETURNING id",
                        cat_name, (p.get("icon") or "").strip()
                    )
                    cats_synced += 1

                existing = await conn.fetchrow(
                    "SELECT id FROM products WHERE upstream_product_id = $1 OR (upstream_product_id IS NULL AND LOWER(title) = LOWER($2))",
                    p["id"], p["title"]
                )

                markup = 15.0
                if self.settings:
                    try:
                        markup = float(await self.settings.get("upstream_markup_percent"))
                    except Exception:
                        markup = 15.0

                reseller_rate = float(p.get("reseller_price") or 0.0)
                raw_regular = float(p.get("regular_price") or 0.0)

                if raw_regular > reseller_rate:
                    computed_price = raw_regular
                elif reseller_rate > 0:
                    computed_price = round(reseller_rate * (1 + markup / 100), 2)
                else:
                    computed_price = raw_regular

                if existing:
                    existing_price = float(existing.get("price") or 0.0)
                    min_selling_price = round(reseller_rate * (1 + markup / 100), 2) if reseller_rate > 0 else computed_price
                    # If existing product has a custom price higher than minimum margin, keep it!
                    # If supplier price increased making old price unprofitable, elevate to min_selling_price.
                    final_price = existing_price if existing_price >= min_selling_price else min_selling_price

                    # Preserve admin customizations: custom title, custom icon, duration, and active/hidden status
                    await conn.execute(
                        """
                        UPDATE products
                        SET reseller_price = $1, price = $2, upstream_product_id = $3
                        WHERE id = $4
                        """,
                        reseller_rate, final_price, p["id"], existing["id"]
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO products (category_id, title, description, price, reseller_price, icon, duration_label, upstream_product_id, is_active, upstream_devices, upstream_share_hours)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0, 1, 24)
                        """,
                        cat_id, p["title"], p.get("description") or "", computed_price, reseller_rate,
                        (p.get("icon") or "").strip(), p.get("duration") or "", p["id"]
                    )
                prods_synced += 1

        return cats_synced, prods_synced

    async def check_low_balance(self, notifier: Any = None) -> bool:
        """Checks if supplier balance is below configured threshold and alerts admins."""
        account = await self.get_account()
        if not account or not account.get("success"):
            return False

        balance = float(account.get("user", {}).get("balance", 0.0))
        threshold = 50.0
        if self.settings:
            try:
                threshold = float(await self.settings.get("upstream_low_balance_alert"))
            except Exception:
                threshold = 50.0

        if balance < threshold and notifier:
            admin_ids = await self.settings.admin_chat_ids()
            msg = (
                f"⚠️ <b>Supplier Wallet Balance Alert!</b>\n\n"
                f"Your Upstream Reseller (Digital Mart) wallet balance is running low.\n"
                f"• Current Balance: <code>৳{balance:.2f} BDT</code>\n"
                f"• Alert Threshold: <code>৳{threshold:.2f} BDT</code>\n\n"
                f"Please recharge your wallet balance to ensure uninterrupted instant customer order fulfillment."
            )
            for aid in admin_ids:
                await notifier.send(aid, msg)
            return True
        return False
