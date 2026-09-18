"""Channel announcements for restocks, price drops and promotions."""

from __future__ import annotations

import logging
from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.catalog import CatalogService
from app.services.notifications import Notifier
from app.services.settings import SettingsService
from app.bot.icons import (
    ICON_CHECK,
    ICON_FIRE,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_PLUS,
    ICON_ROCKET,
    ICON_SHOP,
    ICON_SPARKLES,
    ICON_SPENT,
    ICON_VIP,
    Icons,
)

logger = logging.getLogger("app.services.announcements")


class AnnouncementService:
    def __init__(self, settings: SettingsService, catalog: CatalogService, notifier: Notifier):
        self.settings = settings
        self.catalog = catalog
        self.notifier = notifier

    async def _buy_button(self, product: dict[str, Any], label: str) -> InlineKeyboardMarkup:
        link = f"https://t.me/{await self.notifier.bot_username()}?start=prod_{product['id']}"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=label[:64],
                        url=link,
                        icon_custom_emoji_id=Icons.CART,
                    )
                ]
            ]
        )

    async def _active_product(self, product_id: int) -> dict[str, Any] | None:
        if not self.notifier.bot:
            return None
        product = await self.catalog.product(product_id)
        return product if product and product["is_active"] else None

    async def restock(self, product_id: int, added_count: int) -> bool:
        product = await self._active_product(product_id)
        if not product:
            return False
        values = await self.settings.values()
        symbol = escape(values["currency_symbol"])
        icon, title = escape(product.get("icon") or "⚡"), escape(product["title"])
        await self.notifier.send_admin(
            f"{ICON_ORDERS} <b>Stock Added (Restock Alert)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_VIP} <b>Product:</b> {icon} {title}\n"
            f"{ICON_PLUS} <b>Added Stock:</b> <code>{added_count}</code> item(s)\n"
            f"{ICON_SHOP} <b>Total Stock:</b> <code>{product['stock']}</code> units\n"
            f"{ICON_MONEY} <b>Price:</b> <code>{product['price']:.2f} {symbol}</code>",
            event="restock",
        )
        channel = values["announcement_channel"]
        if not channel or values["auto_restock_alerts"] == "0":
            return True
        return await self.notifier.send(
            channel,
            f"{ICON_ORDERS} <b>Fresh Restock Alert!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_VIP} <b>Product:</b> {icon} <b>{title}</b>\n"
            f"{ICON_SPARKLES} <b>Fresh Stock:</b> <code>{added_count} units</code>\n"
            f"{ICON_SHOP} <b>Available:</b> <code>{product['stock']} accounts</code>\n"
            f"{ICON_MONEY} <b>Price:</b> <code>{product['price']:.2f} {symbol}</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant Automatic Delivery",
            await self._buy_button(product, f"Buy {product['title']}"),
        )

    async def price_drop(self, product_id: int, old_price: float, new_price: float) -> bool:
        if old_price <= new_price:
            return False
        values = await self.settings.values()
        channel = values["announcement_channel"]
        if not channel or values["auto_price_drop_alerts"] == "0":
            return False
        product = await self._active_product(product_id)
        if not product:
            return False
        symbol = escape(values["currency_symbol"])
        return await self.notifier.send(
            channel,
            f"{ICON_FIRE} <b>Special Price Drop!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_VIP} <b>Product:</b> {escape(product.get('icon') or '⚡')} <b>{escape(product['title'])}</b>\n"
            f"{ICON_SPENT} <b>Previous Price:</b> <s>{old_price:.2f} {symbol}</s>\n"
            f"{ICON_MONEY} <b>Discounted Price:</b> <code>{new_price:.2f} {symbol}</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant Automatic Delivery",
            await self._buy_button(product, f"Buy {product['title']}"),
        )

    async def promote(self, product_id: int) -> bool:
        values = await self.settings.values()
        channel = values["announcement_channel"]
        product = await self._active_product(product_id)
        if not channel or not product:
            return False
        symbol = escape(values["currency_symbol"])
        desc = f"\n{ICON_NOTE} {escape(product.get('description'))}\n" if product.get("description") else ""
        return await self.notifier.send(
            channel,
            f"{ICON_FIRE} <b>Featured Product</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_VIP} <b>Product:</b> {escape(product.get('icon') or '⚡')} <b>{escape(product['title'])}</b>{desc}\n"
            f"{ICON_SHOP} <b>Available Stock:</b> <code>{product['stock']} units</code>\n"
            f"{ICON_MONEY} <b>Price:</b> <code>{product['price']:.2f} {symbol}</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant Automatic Delivery",
            await self._buy_button(product, f"Order {product['title']}"),
        )
