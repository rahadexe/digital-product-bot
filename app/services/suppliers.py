"""Multi-supplier integration hub supporting Digital Mart, Safwan Tiger Shop, and future providers."""

from __future__ import annotations

import logging
import math
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import Settings
from app.db import Database

logger = logging.getLogger("app.services.suppliers")

class SupplierError(Exception):
    """Safe, actionable failure without upstream bodies, credentials or headers."""


def setting_number(value: Any, default: float) -> float:
    return float(value) if value not in (None, "") else default


def purchase_response(data: Any, status: int, name: str, *, tiger: bool = False) -> dict[str, Any]:
    """Never mistake a success message for purchased credentials."""
    if not isinstance(data, dict):
        return {"success": False, "detail": f"{name} returned an invalid order response.", "outcome_unknown": True}
    accepted = data.get("success") is True or (tiger and data.get("ok") is True)
    if 200 <= status < 300 and accepted:
        credentials = data.get("credentials") or data.get("delivered_item") or ""
        if tiger:
            credentials = credentials or data.get("delivered_items") or data.get("item") or ""
        if isinstance(credentials, list) and all(isinstance(item, str) for item in credentials):
            credentials = "\n".join(credentials)
        if not isinstance(credentials, str):
            credentials = ""
        fulfillment = "delivered" if credentials.strip() and data.get("fulfillment") not in ("waiting", "pending") else "waiting"
        cost = setting_number(data.get("unit_price", data.get("price")), 0)
        total = setting_number(data.get("total_price"), cost)
        if not all(math.isfinite(value) and 0 <= value <= 1_000_000_000 for value in (cost, total)):
            return {"success": False, "detail": f"{name} returned an invalid order response.", "outcome_unknown": True}
        return {
            "success": True, "credentials": credentials if fulfillment == "delivered" else "",
            "delivered_item": credentials if fulfillment == "delivered" else "",
            "order_id": data.get("order_id") or data.get("id"),
            "unit_price": cost, "total_price": total, "fulfillment": fulfillment,
        }
    raw_error = data.get("error") or data.get("detail") or data.get("message") or ""
    # Only classify text. Never return an untrusted response body to the console or logs.
    low_balance = status == 402 or (isinstance(raw_error, str) and (
        "insufficient_balance" in raw_error.lower() or "insufficient balance" in raw_error.lower()
    ))
    message = ("Supplier balance is too low." if low_balance else
               "Supplier rejected the API key." if status in (401, 403) else
               "Supplier product is unavailable." if status == 404 else
               f"{name} could not complete the order (HTTP {status}).")
    return {"success": False, "detail": message, "insufficient_balance": low_balance,
            "outcome_unknown": status >= 500 or status == 408 or 200 <= status < 300}


class BaseSupplier(ABC):
    code: str
    name: str
    currency: str

    def __init__(self, db: Database, settings: Any = None):
        self.db = db
        self.settings = settings

    async def _get_json(self, endpoint: str) -> Any:
        await self._ensure_config()
        if not self.is_configured:
            raise SupplierError(f"{self.name} is not configured.")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(f"{self.base_url}/{endpoint}", headers=self._headers())
            if response.status_code in (401, 403):
                raise SupplierError(f"{self.name}: check the API key and reseller access.")
            if response.status_code == 404:
                raise SupplierError(f"{self.name}: check the API base URL.")
            if response.status_code == 429:
                raise SupplierError(f"{self.name}: rate limit reached. Try again later.")
            if response.status_code != 200:
                raise SupplierError(f"{self.name} is unavailable (HTTP {response.status_code}).")
            data = response.json()
            if isinstance(data, dict) and (data.get("success") is False or data.get("ok") is False):
                raise SupplierError(f"{self.name} rejected the request. Check the API settings.")
            return data
        except SupplierError:
            raise
        except (httpx.HTTPError, ValueError):
            raise SupplierError(f"{self.name} could not be reached or returned an invalid response.") from None

    async def _catalog(self) -> list[dict[str, Any]]:
        data = await self._get_json("products")
        products = data.get("products") if isinstance(data, dict) else data
        if not isinstance(products, list):
            raise SupplierError(f"{self.name} returned an invalid catalog.")
        seen = set()
        for product in products:
            try:
                if not isinstance(product, dict):
                    raise ValueError
                pid = product["id"]
                if isinstance(pid, bool) or int(pid) <= 0 or str(int(pid)) != str(pid) or int(pid) in seen:
                    raise ValueError
                seen.add(int(pid))
                product["id"] = int(pid)
                if not isinstance(product.get("title") or product.get("name"), str):
                    raise ValueError
                if not (product.get("title") or product.get("name")).strip():
                    raise ValueError
                for key in ("price", "reseller_price", "regular_price"):
                    if product.get(key) is not None:
                        value = float(product[key])
                        if not 0 <= value <= 1_000_000_000:
                            raise ValueError
                for key in ("category_name", "duration", "duration_label", "icon", "description", "warranty"):
                    if product.get(key) is not None and not isinstance(product[key], str):
                        raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError):
                raise SupplierError(f"{self.name} returned an invalid product. No products were imported.") from None
        return products

    def _select_products(self, products: list[dict[str, Any]], filter_ids: list[int] | None) -> list[dict[str, Any]]:
        if filter_ids is None:
            return products
        selected = set(filter_ids)
        found = {int(product["id"]) for product in products}
        if not selected or not selected <= found:
            raise SupplierError("Selected products are no longer available. Refresh the catalog.")
        return [product for product in products if product["id"] in selected]

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
        await self._ensure_config()
        now = time.monotonic()
        if not force and self._balance_cache and (now - self._balance_cache[0] < 30.0):
            return self._balance_cache[1]
        self._balance_cache = None
        if not self.is_configured:
            return None
        try:
            data = await self._get_json("me")
            user = data["user"]
            balance = float(user["balance"])
            if not 0 <= balance < float("inf"):
                raise ValueError
            res = {"ok": True, "balance": balance, "currency": "BDT"}
            self._balance_cache = (now, res)
            return res
        except (SupplierError, KeyError, TypeError, ValueError):
            logger.warning("Digital Mart balance check failed.")
        return None

    async def get_products(self) -> list[dict[str, Any]]:
        return await self._catalog()

    async def purchase(self, product_id: int, quantity: int = 1, custom_id: str = "") -> dict[str, Any]:
        await self._ensure_config()
        if not self.is_configured:
            return {"success": False, "detail": "Digital Mart API not configured."}
        payload = {
            "product_id": product_id,
            "quantity": quantity,
            "custom_id": custom_id or uuid.uuid4().hex,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.base_url}/orders", json=payload, headers=self._headers())
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                self._balance_cache = None
                return purchase_response(data, resp.status_code, self.name)
        except Exception:
            logger.warning("Digital Mart purchase outcome could not be confirmed.")
            return {"success": False, "detail": "Supplier order could not be confirmed.", "insufficient_balance": False, "outcome_unknown": True}

    async def sync_catalog(
        self,
        filter_ids: list[int] | None = None,
        force_active: bool | None = None,
        target_category_id: int | None = None,
    ) -> tuple[int, int]:
        await self._ensure_config()
        products = self._select_products(await self.get_products(), filter_ids)
        if not products:
            return 0, 0

        cats_synced, prods_synced = 0, 0
        async with self.db.transaction() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"supplier-sync:{self.code}")
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

                if existing and not target_category_id:
                    cat_id = None
                elif target_category_id:
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

                reseller_rate = float(p.get("reseller_price") or p.get("price") or 0.0)
                raw_regular = float(p.get("regular_price") or 0.0)
                computed_price = max(raw_regular, round(reseller_rate * (1 + markup / 100), 2))

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
                    title = (p.get("title") or p["name"]).strip()
                    if computed_price <= 0:
                        raise SupplierError("Supplier price is unavailable. No products were imported.")
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
                f"<b>Digital Mart balance is low</b>\n"
                f"<code>৳{balance:.2f} BDT</code>\n"
                "Top up the supplier wallet to keep orders running."
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
        await self._ensure_config()
        now = time.monotonic()
        if not force and self._balance_cache and (now - self._balance_cache[0] < 30.0):
            return self._balance_cache[1]
        self._balance_cache = None
        if not self.is_configured:
            return None
        try:
            data = await self._get_json("balance")
            balance = float(data["balance"])
            if not 0 <= balance < float("inf"):
                raise ValueError
            res = {"ok": True, "balance": balance, "currency": "USDT"}
            self._balance_cache = (now, res)
            return res
        except (SupplierError, KeyError, TypeError, ValueError):
            logger.warning("Safwan Tiger balance check failed.")
        return None

    async def get_products(self) -> list[dict[str, Any]]:
        return await self._catalog()

    async def purchase(self, product_id: int, quantity: int = 1, custom_id: str = "") -> dict[str, Any]:
        await self._ensure_config()
        if not self.is_configured:
            return {"success": False, "detail": "Safwan Tiger API not configured."}
        payload = {
            "product_id": product_id,
            "quantity": quantity,
            "request_id": custom_id or uuid.uuid4().hex,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.base_url}/order", json=payload, headers=self._headers())
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                self._balance_cache = None
                return purchase_response(data, resp.status_code, self.name, tiger=True)
        except Exception:
            logger.warning("Safwan Tiger purchase outcome could not be confirmed.")
            return {"success": False, "detail": "Supplier order could not be confirmed.", "insufficient_balance": False, "outcome_unknown": True}

    async def sync_catalog(
        self,
        filter_ids: list[int] | None = None,
        force_active: bool | None = None,
        target_category_id: int | None = None,
    ) -> tuple[int, int]:
        await self._ensure_config()
        products = self._select_products(await self.get_products(), filter_ids)
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
                markup = setting_number(await self.settings.get("safwan_tiger_markup_percent"), 15.0)
            except Exception:
                markup = 15.0

        cats_synced, prods_synced = 0, 0
        async with self.db.transaction() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"supplier-sync:{self.code}")
            for p in products:
                supplier_prod_id = int(p["id"])
                existing = await conn.fetchrow(
                    "SELECT id, price, is_active FROM products WHERE supplier_code = 'safwan_tiger' AND upstream_product_id = $1",
                    supplier_prod_id
                )

                # Selective listing policy: On general catalog sync (filter_ids is None), only update already-imported products!
                if not existing and not filter_ids:
                    continue

                cat_id = target_category_id
                if not existing and not cat_id:
                    cat_name = (p.get("category_name") or "General").strip() or "General"
                    cat_row = await conn.fetchrow("SELECT id FROM categories WHERE LOWER(name) = LOWER($1)", cat_name)
                    cat_id = cat_row["id"] if cat_row else await conn.fetchval(
                        "INSERT INTO categories (name, icon, sort_order) VALUES ($1, '', 99) RETURNING id", cat_name
                    )
                    if not cat_row:
                        cats_synced += 1
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
                    if computed_price_bdt <= 0:
                        raise SupplierError("Supplier price is unavailable. No products were imported.")
                    # Deduplication: check if same title already exists in store
                    same_title = await conn.fetchval(
                        "SELECT 1 FROM products WHERE LOWER(TRIM(title)) = LOWER(TRIM($1))", prod_name
                    )
                    final_title = f"{prod_name} [Tiger]" if same_title else prod_name
                    active_val = 1 if force_active else 0

                    await conn.execute(
                        """
                        INSERT INTO products (category_id, title, description, price, reseller_price, icon, duration_label, warranty_label,
                                              supplier_code, upstream_product_id, is_active, upstream_devices, upstream_share_hours)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'safwan_tiger', $9, $10, 1, 24)
                        """,
                        cat_id, final_title, desc, computed_price_bdt, reseller_rate_bdt,
                        p.get("icon") or "", p.get("duration") or p.get("duration_label") or "",
                        p.get("warranty") or "", supplier_prod_id, active_val
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
                f"<b>Safwan Tiger balance is low</b>\n"
                f"<code>${balance:.2f} USDT</code>\n"
                "Top up the supplier wallet to keep orders running."
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
            await sup._ensure_config()
            if sup.is_configured:
                results[code] = await sup.sync_catalog()
        return results

    async def check_all_low_balances(self, notifier: Any = None) -> None:
        for sup in self.suppliers.values():
            if sup.is_configured:
                try:
                    await sup.check_low_balance(notifier)
                except Exception:
                    logger.exception("Failed checking low balance for %s", sup.code)
