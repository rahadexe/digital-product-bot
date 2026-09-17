"""Channel announcements for restocks, price drops and promotions."""

from __future__ import annotations

import logging
from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.catalog import CatalogService
from app.services.notifications import Notifier
from app.services.settings import SettingsService

logger = logging.getLogger("app.services.announcements")


class AnnouncementService:
    def __init__(self, settings: SettingsService, catalog: CatalogService, notifier: Notifier):
        self.settings = settings
        self.catalog = catalog
        self.notifier = notifier

    async def _buy_button(self, product: dict[str, Any], label: str) -> InlineKeyboardMarkup:
        link = f"https://t.me/{await self.notifier.bot_username()}?start=prod_{product['id']}"
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label[:64], url=link, style="success")]])

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
            "📦 <b>Stock Added (Restock Alert)</b>\n\n"
            f"🏷️ <b>Product:</b> {icon} {title}\n"
            f"➕ <b>Added:</b> <code>{added_count}</code> item(s)\n"
            f"📊 <b>Total Live Stock:</b> <code>{product['stock']}</code> units\n"
            f"💵 <b>Price:</b> <code>{symbol}{product['price']:.2f}</code>\n"
        )
        channel = values["announcement_channel"]
        if not channel or values["auto_restock_alerts"] == "0":
            return True
        return await self.notifier.send(
            channel,
            f"⭐ <b>{added_count} Restocked {icon} {title}</b>\n\n"
            f"✨ <b>Fresh batch:</b> <code>{added_count} accounts</code>\n"
            f"📦 <b>Available:</b> <code>{product['stock']} accounts</code>\n"
            f"🏷️ <b>Price:</b> <code>{symbol}{product['price']:.2f}</code>\n"
            "⭐ <b>Delivery:</b> Instant automatic delivery\n\n"
            "<i>❗ Fresh stock is live now! Grab yours before it runs out.</i>",
            await self._buy_button(product, f"🛒 Buy {product['title']}"),
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
            "📉 <b>Price Drop!</b>\n\n"
            f"{escape(product.get('icon') or '⚡')} <b>{escape(product['title'])}</b>\n"
            f"💸 <b>Was:</b> <s>{symbol}{old_price:.2f}</s>\n"
            f"🆙 <b>Now:</b> <b>{symbol}{new_price:.2f}</b>\n\n"
            "<i>⚡ Grab it before gone, buy now!</i>",
            await self._buy_button(product, f"🛒 Buy {product['title']} ↗"),
        )

    async def promote(self, product_id: int) -> bool:
        values = await self.settings.values()
        channel = values["announcement_channel"]
        product = await self._active_product(product_id)
        if not channel or not product:
            return False
        symbol = escape(values["currency_symbol"])
        return await self.notifier.send(
            channel,
            f"🔥 <b>Featured: {escape(product.get('icon') or '⚡')} {escape(product['title'])}</b>\n\n"
            f"📝 {escape(product.get('description') or '')}\n\n"
            f"📦 <b>In Stock:</b> <code>{product['stock']} available</code>\n"
            f"💰 <b>Price:</b> <code>{symbol}{product['price']:.2f}</code>\n"
            "⚡ <b>Delivery:</b> Instant automatic delivery\n\n"
            "<i>Tap below to order directly in the bot.</i>",
            await self._buy_button(product, f"🛒 Order {product['title']}"),
        )
