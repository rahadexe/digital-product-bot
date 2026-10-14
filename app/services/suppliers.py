"""Multi-supplier integration hub supporting Digital Mart, Safwan Tiger Shop, and future providers."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import Settings
from app.db import Database

logger = logging.getLogger("app.services.suppliers")


class BaseSupplier(ABC):
    code: str
    name: str
    currency: str

    def __init__(self, db: Database, settings: Any = None):
        self.db = db
        self.settings = settings

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        pass

    @abstractmethod
    async def get_balance(self) -> dict[str, Any] | None:
        pass

    @abstractmethod
    async def get_products(self) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    async def purchase(self, product_id: int, quantity: int = 1, custom_id: str = "") -> dict[str, Any]:
        pass

    @abstractmethod
    async def sync_catalog(self, filter_ids: list[int] | None = None, force_active: bool | None = None, target_category_id: int | None = None) -> tuple[int, int]:
        pass


    @abstractmethod
    async def check_low_balance(self, notifier: Any = None) -> bool:
        pass


class DigitalMartClient(BaseSupplier):
    code = "digital_mart"
    name = "Digital Mart"
    currency = "BDT"

    def __init__(self, db: Database, config: Settings, settings: Any = None):
        super().__init__(db, settings)
        self.config = config
        self.base_url = (config.upstream_reseller_url or "https://dmb.bmdigital.bd/api/v1/reseller").rstrip("/")
        self.api_key = config.upstream_reseller_key or ""
        self._balance_cache: tuple[float, dict[str, Any]] | None = None

    async def _ensure_config(self) -> None:
        if self.settings:
            try:
                db_url = await self.settings.get("upstream_reseller_url")
                db_key = await self.settings.get("upstream_reseller_key")
                next_key = db_key or self.config.upstream_reseller_key or ""
                if next_key != self.api_key or (db_url and db_url.rstrip('/') != self.base_url):
                    self._balance_cache = None
                if db_url:
                    self.base_url = db_url.rstrip("/")
                self.api_key = next_key
            except Exception:
                pass

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "SubsMarket-DigitalMart/1.0",
        }

    async def get_balance(self, force: bool = False) -> dict[str, Any] | None:
        now = time.monotonic()
        if not force and self._balance_cache and (now - self._balance_cache[0] < 30.0):
            return self._balance_cache[1]
        await self._ensure_config()
        if not self.is_configured:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/me", headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    user = data.get("user", {})
                    res = {
                        "ok": True,
                        "balance": float(user.get("balance", 0.0)),
                        "currency": "BDT",
                        "raw": data,
                    }
                    self._balance_cache = (now, res)
                    return res
                logger.warning("Digital Mart /me returned %d: %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("Failed to connect to Digital Mart /me")
        return None

    async def get_products(self) -> list[dict[str, Any]]:
        await self._ensure_config()
        if not self.is_configured:
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/products", headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("products", [])
                logger.warning("Digital Mart /products returned %d: %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("Failed to fetch products from Digital Mart")
        return []

    async def purchase(self, product_id: int, quantity: int = 1, custom_id: str = "") -> dict[str, Any]:
        await self._ensure_config()
        if not self.is_configured:
            return {"success": False, "detail": "Digital Mart API not configured."}
        payload = {
            "product_id": product_id,
            "quantity": quantity,
            "custom_id": custom_id or f"dm_{product_id}_{int(time.time())}",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.base_url}/orders", json=payload, headers=self._headers())
                try:
                    data = resp.json()
                except Exception:
                    data = {"detail": resp.text}
                if resp.status_code in (200, 201) and data.get("success"):
                    creds = data.get("credentials") or data.get("delivered_item") or data.get("message") or ""
                    return {
                        "success": True,
                        "credentials": creds,
                        "delivered_item": creds,
                        "order_id": data.get("order_id") or data.get("id"),
                        "unit_price": float(data.get("unit_price") or 0.0),
                        "total_price": float(data.get("total_price") or 0.0),
                        "fulfillment": data.get("fulfillment") or ("delivered" if creds else "waiting"),
                    }
                error_msg = data.get("detail") or data.get("message") or f"Digital Mart error ({resp.status_code})"
                is_low_balance = resp.status_code == 402 or "balance" in error_msg.lower()
                return {"success": False, "detail": error_msg, "insufficient_balance": is_low_balance,
                        "outcome_unknown": resp.status_code >= 500 or resp.status_code == 408 or 200 <= resp.status_code < 300}
        except Exception as exc:
            logger.exception("Failed to purchase from Digital Mart")
            return {"success": False, "detail": str(exc), "insufficient_balance": False, "outcome_unknown": True}

    async def sync_catalog(
        self,
        filter_ids: list[int] | None = None,
        force_active: bool | None = None,
        target_category_id: int | None = None,
    ) -> tuple[int, int]:
        await self._ensure_config()
        if not self.is_configured:
            return 0, 0
        products = await self.get_products()
        if not products:
            return 0, 0

        if filter_ids:
            filter_set = {int(x) for x in filter_ids}
            products = [p for p in products if int(p.get("id") or 0) in filter_set]
            if not products:
                return 0, 0

        cats_synced, prods_synced = 0, 0
        async with self.db.transaction() as conn:
            for p in products:
                existing = await conn.fetchrow(
                    "SELECT id, price, is_active FROM products WHERE supplier_code = 'digital_mart' AND upstream_product_id = $1",
                    p["id"]
                )
                if not existing:
                    existing = await conn.fetchrow(
                        "SELECT id, price, is_active FROM products WHERE upstream_product_id = $1 AND (supplier_code IS NULL OR supplier_code = 'digital_mart')",
                        p["id"]
                    )

                # Selective listing policy: On general catalog sync (filter_ids is None), only update already-imported products!
                # Do NOT auto-import unlisted remote products into the shop.
                if not existing and not filter_ids:
                    continue

                if target_category_id:
                    cat_id = target_category_id
                else:
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
                    final_price = existing_price if existing_price >= min_selling_price else min_selling_price
                    new_active = (1 if force_active else 0) if force_active is not None else existing.get("is_active", 0)
                    if target_category_id:
                        await conn.execute(
                            """
                            UPDATE products
                            SET reseller_price = $1, price = $2, supplier_code = 'digital_mart', upstream_product_id = $3, is_active = $4, category_id = $5
                            WHERE id = $6
                            """,
                            reseller_rate, final_price, p["id"], new_active, target_category_id, existing["id"]
                        )
                    else:
                        await conn.execute(
                            """
                            UPDATE products
                            SET reseller_price = $1, price = $2, supplier_code = 'digital_mart', upstream_product_id = $3, is_active = $4
                            WHERE id = $5
                            """,
                            reseller_rate, final_price, p["id"], new_active, existing["id"]
                        )
                else:
                    title = p["title"].strip()
                    # If same title already exists locally, disambiguate to prevent confusion
                    same_title = await conn.fetchval("SELECT 1 FROM products WHERE LOWER(TRIM(title)) = LOWER(TRIM($1))", title)
                    final_title = f"{title} [DM]" if same_title else title
                    active_val = 1 if force_active else 0
                    await conn.execute(
                        """
                        INSERT INTO products (category_id, title, description, price, reseller_price, icon, duration_label,
                                              supplier_code, upstream_product_id, is_active, upstream_devices, upstream_share_hours)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, 'digital_mart', $8, $9, 1, 24)
                        """,
                        cat_id, final_title, p.get("description") or "", computed_price, reseller_rate,
                        (p.get("icon") or "").strip(), p.get("duration") or "", p["id"], active_val
                    )
                prods_synced += 1

        return cats_synced, prods_synced


    async def check_low_balance(self, notifier: Any = None) -> bool:
        account = await self.get_balance()
        if not account or not account.get("ok"):
            return False
        balance = account.get("balance", 0.0)
        threshold = 50.0
        if self.settings:
            try:
                threshold = float(await self.settings.get("upstream_low_balance_alert"))
            except Exception:
                threshold = 50.0
        if balance < threshold and notifier:
            admin_ids = await self.settings.admin_chat_ids()
            msg = (
                f"⚠️ <b>Digital Mart Wallet Balance Alert!</b>\n\n"
                f"Your Digital Mart supplier wallet balance is running low.\n"
                f"• Current Balance: <code>৳{balance:.2f} BDT</code>\n"
                f"• Alert Threshold: <code>৳{threshold:.2f} BDT</code>\n\n"
                f"Please recharge your wallet balance to ensure uninterrupted instant customer order fulfillment."
            )
            for aid in admin_ids:
                notifier.in_background(notifier.send(aid, msg))
            return True
        return False


class SafwanTigerClient(BaseSupplier):
    code = "safwan_tiger"
    name = "Safwan Tiger Shop"
    currency = "USDT"

    def __init__(self, db: Database, settings: Any = None):
        super().__init__(db, settings)
        self.base_url = "https://safwantigershopbot-production.up.railway.app/api"
        self.api_key = ""
        self._balance_cache: tuple[float, dict[str, Any]] | None = None

    async def _ensure_config(self) -> None:
        if self.settings:
            try:
                db_url = await self.settings.get("safwan_tiger_url")
                db_key = await self.settings.get("safwan_tiger_key")
                if (db_key or '') != self.api_key or (db_url and db_url.rstrip('/') != self.base_url):
                    self._balance_cache = None
                if db_url:
                    self.base_url = db_url.rstrip("/")
                self.api_key = db_key or ""
            except Exception:
                pass

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "SubsMarket-SafwanTiger/1.0",
        }

    async def get_balance(self, force: bool = False) -> dict[str, Any] | None:
        now = time.monotonic()
        if not force and self._balance_cache and (now - self._balance_cache[0] < 30.0):
            return self._balance_cache[1]
        await self._ensure_config()
        if not self.is_configured:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/balance", headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    res = {
                        "ok": True,
                        "balance": float(data.get("balance", 0.0)),
                        "currency": "USDT",
                        "raw": data,
                    }
                    self._balance_cache = (now, res)
                    return res
                logger.warning("Safwan Tiger /balance returned %d: %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("Failed to connect to Safwan Tiger /balance")
        return None

    async def get_products(self) -> list[dict[str, Any]]:
        await self._ensure_config()
        if not self.is_configured:
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/products", headers=self._headers())
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("products", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                logger.warning("Safwan Tiger /products returned %d: %s", resp.status_code, resp.text)
        except Exception:
            logger.exception("Failed to fetch products from Safwan Tiger")
        return []

    async def purchase(self, product_id: int, quantity: int = 1, custom_id: str = "") -> dict[str, Any]:
        await self._ensure_config()
        if not self.is_configured:
            return {"success": False, "detail": "Safwan Tiger API not configured."}
        payload = {
            "product_id": product_id,
            "quantity": quantity,
            "request_id": custom_id or f"st_{product_id}_{int(time.time())}",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.base_url}/order", json=payload, headers=self._headers())
                try:
                    data = resp.json()
                except Exception:
                    data = {"message": resp.text}

                if resp.status_code in (200, 201) and (data.get("ok") or data.get("success")):
                    creds = (
                        data.get("credentials")
                        or data.get("delivered_items")
                        or data.get("delivered_item")
                        or data.get("item")
                        or data.get("message")
                        or ""
                    )
                    if isinstance(creds, list):
                        creds = "\n".join(str(c) for c in creds)
                    return {
                        "success": True,
                        "credentials": str(creds),
                        "delivered_item": str(creds),
                        "order_id": data.get("order_id") or data.get("id"),
                        "unit_price": float(data.get("price") or data.get("unit_price") or 0.0),
                        "total_price": float(data.get("total_price") or data.get("price") or 0.0),
                        "fulfillment": "delivered" if creds else "waiting",
                    }

                error_msg = data.get("message") or data.get("error") or data.get("detail") or f"Error ({resp.status_code})"
                is_low_balance = (
                    resp.status_code == 402
                    or data.get("error") == "insufficient_balance"
                    or "balance" in error_msg.lower()
                )
                return {
                    "success": False,
                    "detail": error_msg,
                    "insufficient_balance": is_low_balance,
                    "outcome_unknown": resp.status_code >= 500 or resp.status_code == 408 or 200 <= resp.status_code < 300,
                }
        except Exception as exc:
            logger.exception("Failed to purchase from Safwan Tiger")
            return {"success": False, "detail": str(exc), "insufficient_balance": False, "outcome_unknown": True}

    async def sync_catalog(
        self,
        filter_ids: list[int] | None = None,
        force_active: bool | None = None,
        target_category_id: int | None = None,
    ) -> tuple[int, int]:
        await self._ensure_config()
        if not self.is_configured:
            return 0, 0
        products = await self.get_products()
        if not products:
            return 0, 0

        if filter_ids:
            filter_set = {int(x) for x in filter_ids}
            products = [p for p in products if int(p.get("id") or 0) in filter_set]
            if not products:
                return 0, 0

        usd_rate = 125.0
        if self.settings:
            try:
                usd_rate = float(await self.settings.get("usd_rate") or 125.0)
            except Exception:
                usd_rate = 125.0

        markup = 15.0
        if self.settings:
            try:
                markup = float(await self.settings.get("safwan_tiger_markup_percent") or 15.0)
            except Exception:
                markup = 15.0

        cats_synced, prods_synced = 0, 0
        async with self.db.transaction() as conn:
            # Default or ensure general category if target_category_id is not specified
            if target_category_id:
                default_cat_id = target_category_id
            else:
                cat_row = await conn.fetchrow("SELECT id FROM categories WHERE LOWER(name) = 'ai tools' OR LOWER(name) = 'general' ORDER BY id LIMIT 1")
                default_cat_id = cat_row["id"] if cat_row else await conn.fetchval(
                    "INSERT INTO categories (name, icon, sort_order) VALUES ('AI Tools', '🤖', 99) RETURNING id"
                )

            for p in products:
                supplier_prod_id = int(p["id"])
                existing = await conn.fetchrow(
                    "SELECT id, price, is_active FROM products WHERE supplier_code = 'safwan_tiger' AND upstream_product_id = $1",
                    supplier_prod_id
                )

                # Selective listing policy: On general catalog sync (filter_ids is None), only update already-imported products!
                if not existing and not filter_ids:
                    continue

                cat_id = target_category_id if target_category_id else default_cat_id
                prod_name = (p.get("name") or p.get("title") or "Unnamed Product").strip()
                usd_price = float(p.get("price") or 0.0)
                # Convert USD to BDT
                reseller_rate_bdt = round(usd_price * usd_rate, 2)
                computed_price_bdt = round(reseller_rate_bdt * (1 + markup / 100), 2) if reseller_rate_bdt > 0 else 0.0

                desc = (p.get("description") or "").strip()
                if p.get("warranty"):
                    desc = f"{desc}\n\nWarranty: {p['warranty']}".strip()

                if existing:
                    existing_price = float(existing.get("price") or 0.0)
                    min_selling_price = round(reseller_rate_bdt * (1 + markup / 100), 2)
                    final_price = existing_price if existing_price >= min_selling_price else min_selling_price
                    new_active = (1 if force_active else 0) if force_active is not None else existing.get("is_active", 0)
                    if target_category_id:
                        await conn.execute(
                            """
                            UPDATE products
                            SET reseller_price = $1, price = $2, supplier_code = 'safwan_tiger', upstream_product_id = $3, is_active = $4, category_id = $5
                            WHERE id = $6
                            """,
                            reseller_rate_bdt, final_price, supplier_prod_id, new_active, target_category_id, existing["id"]
                        )
                    else:
                        await conn.execute(
                            """
                            UPDATE products
                            SET reseller_price = $1, price = $2, supplier_code = 'safwan_tiger', upstream_product_id = $3, is_active = $4
                            WHERE id = $5
                            """,
                            reseller_rate_bdt, final_price, supplier_prod_id, new_active, existing["id"]
                        )
                else:
                    # Deduplication: check if same title already exists in store
                    same_title = await conn.fetchval(
                        "SELECT 1 FROM products WHERE LOWER(TRIM(title)) = LOWER(TRIM($1))", prod_name
                    )
                    final_title = f"{prod_name} [Tiger]" if same_title else prod_name
                    active_val = 1 if force_active else 0

                    await conn.execute(
                        """
                        INSERT INTO products (category_id, title, description, price, reseller_price, icon, duration_label,
                                              supplier_code, upstream_product_id, is_active, upstream_devices, upstream_share_hours)
                        VALUES ($1, $2, $3, $4, $5, '', '1 Month', 'safwan_tiger', $6, $7, 1, 24)
                        """,
                        cat_id, final_title, desc, computed_price_bdt, reseller_rate_bdt, supplier_prod_id, active_val
                    )
                prods_synced += 1

        return cats_synced, prods_synced


    async def check_low_balance(self, notifier: Any = None) -> bool:
        account = await self.get_balance()
        if not account or not account.get("ok"):
            return False
        balance = account.get("balance", 0.0)
        threshold = 5.0
        if self.settings:
            try:
                threshold = float(await self.settings.get("safwan_tiger_low_balance_alert") or 5.0)
            except Exception:
                threshold = 5.0
        if balance < threshold and notifier:
            admin_ids = await self.settings.admin_chat_ids()
            msg = (
                f"⚠️ <b>Safwan Tiger Shop ব্যালেন্স অ্যালার্ট!</b>\n\n"
                f"আপনার Safwan Tiger Shop API ওয়ালেটে ব্যালেন্স কম রয়েছে।\n"
                f"• বর্তমান ব্যালেন্স: <code>${balance:.2f} USDT</code>\n"
                f"• অ্যালার্ট লিমিট: <code>${threshold:.2f} USDT</code>\n\n"
                f"কাস্টমারদের অর্ডার তাৎক্ষণিক ফুলফিলমেন্ট চালু রাখতে ব্যালেন্স রিচার্জ করুন।"
            )
            for aid in admin_ids:
                notifier.in_background(notifier.send(aid, msg))
            return True
        return False


class SupplierManager:
    """Manages all external wholesale suppliers and routes fulfillment requests."""

    def __init__(self, db: Database, config: Settings, settings: Any = None):
        self.db = db
        self.config = config
        self.settings = settings
        self.suppliers: dict[str, BaseSupplier] = {
            "digital_mart": DigitalMartClient(db, config, settings),
            "safwan_tiger": SafwanTigerClient(db, settings),
        }

    def get(self, code: str | None) -> BaseSupplier | None:
        if not code:
            return self.suppliers.get("digital_mart")
        return self.suppliers.get(code.lower().strip())

    def list_all(self) -> list[BaseSupplier]:
        return list(self.suppliers.values())

    async def load_config(self) -> None:
        for supplier in self.suppliers.values():
            await supplier._ensure_config()

    async def sync_all(self) -> dict[str, tuple[int, int]]:
        results = {}
        for code, sup in self.suppliers.items():
            if sup.is_configured:
                try:
                    results[code] = await sup.sync_catalog()
                except Exception as exc:
                    logger.exception("Failed to sync supplier %s: %s", code, exc)
                    results[code] = (0, 0)
        return results

    async def check_all_low_balances(self, notifier: Any = None) -> None:
        for sup in self.suppliers.values():
            if sup.is_configured:
                try:
                    await sup.check_low_balance(notifier)
                except Exception:
                    logger.exception("Failed checking low balance for %s", sup.code)
