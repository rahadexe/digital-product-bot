"""Channel announcements for restocks, price drops and promotions."""

from __future__ import annotations

import logging
import re
from html import escape
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.formatting import format_dual_price
from app.bot.icons import (
    ICON_CHECK,
    ICON_FIRE,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_PLUS,
    ICON_SHOP,
    ICON_SPARKLES,
    ICON_STATS,
    ICON_TIMER,
    ICON_VIP,
)
from app.services.catalog import CatalogService
from app.services.notifications import Notifier
from app.services.settings import SettingsService

logger = logging.getLogger("app.services.announcements")


class AnnouncementService:
    def __init__(self, settings: SettingsService, catalog: CatalogService, notifier: Notifier):
        self.settings = settings
        self.catalog = catalog
        self.notifier = notifier

    def _product_icon(self, product: dict[str, Any]) -> str:
        raw_icon = product.get("icon") or ""
        return escape(raw_icon)

    async def _buy_button(self, product: dict[str, Any], label: str) -> InlineKeyboardMarkup:
        link = f"https://t.me/{await self.notifier.bot_username()}?start=prod_{product['id']}"
        btn_kwargs: dict[str, Any] = {
            "text": label[:64],
            "url": link,
        }
        custom_emoji_id = str(product.get("custom_emoji_id") or "").strip()
        if custom_emoji_id.isdigit():
            btn_kwargs["icon_custom_emoji_id"] = custom_emoji_id
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(**btn_kwargs)]]
        )

    async def _active_product(self, product_id: int) -> dict[str, Any] | None:
        if not self.notifier.bot:
            return None
        product = await self.catalog.product(product_id)
        return product if product and product["is_active"] else None

    def _channels(self, raw: str) -> list[str]:
        if not raw:
            return []
        return [c.strip() for c in re.split(r"[\s,;]+", raw) if c.strip()]

    async def restock(self, product_id: int, added_count: int) -> bool:
        product = await self._active_product(product_id)
        if not product:
            return False
        values = await self.settings.values()
        symbol = escape(values["currency_symbol"])
        icon, title = self._product_icon(product), escape(product["title"])
        icon_prefix = f"{icon} " if icon else ""
        duration = (product.get("duration_label") or "").strip()
        duration_line = f"<b>Validity:</b> {escape(duration)}\n" if duration and duration.lower() not in {"instant", "none", "n/a", ""} else ""
        button = await self._buy_button(product, f"Buy {product['title']}")

        admin_delivered = await self.notifier.send_admin(
            f"✅ <b>Product Restocked</b>\n\n"
            f"<blockquote>Product: {icon_prefix}<b>{title}</b>\n"
            f"{duration_line}"
            f"Fresh Stock: <code>+{added_count} units</code>\n"
            f"Available: <code>{product['stock']}</code>\n"
            f"Price: <code>{format_dual_price(product['price'], symbol, show_usd=False)}</code></blockquote>",
            event="restock",
            keyboard=button,
        )
        raw_channels = values.get("announcement_channel", "")
        channels = self._channels(raw_channels)
        if not channels or values.get("auto_restock_alerts", "1") == "0":
            return admin_delivered

        channel_delivered = False
        for ch in channels:
            deliv = await self.notifier.send(
                ch,
                f"✅ <b>Product Restocked</b>\n\n"
                f"<blockquote>Product: {icon_prefix}<b>{title}</b>\n"
                f"{duration_line}"
                f"Fresh Stock: <code>+{added_count} units</code>\n"
                f"Available: <code>{product['stock']}</code>\n"
                f"Price: <code>{format_dual_price(product['price'], symbol, show_usd=False)}</code>\n"
                f"Delivery: Instant</blockquote>",
                button,
            )
            if deliv:
                channel_delivered = True
        return admin_delivered or channel_delivered

    async def price_change(self, product_id: int, old_price: float, new_price: float) -> bool:
        if old_price == new_price:
            return False
        product = await self._active_product(product_id)
        if not product:
            return False

        values = await self.settings.values()
        symbol = escape(values["currency_symbol"])
        icon = self._product_icon(product)
        icon_prefix = f"{icon} " if icon else ""
        title = escape(product["title"])
        diff = abs(new_price - old_price)
        pct = round((diff / old_price) * 100) if old_price > 0 else 0
        duration = (product.get("duration_label") or "").strip()
        duration_line = f"<b>Validity:</b> {escape(duration)}\n" if duration and duration.lower() not in {"instant", "none", "n/a", ""} else ""
        is_manual = product.get("delivery_type") == "manual"
        delivery_line = "<b>Delivery:</b> Manual" if is_manual else "<b>Delivery:</b> Instant (Automatic)"

        is_drop = new_price < old_price

        if is_drop:
            heading = "📉 <b>Price Drop Alert</b>"
            diff_line = f"<b>Old Price:</b> <code><s>{format_dual_price(old_price, symbol, show_usd=False)}</s></code>\n"
            price_line = f"<b>Price:</b> <code>{format_dual_price(new_price, symbol, show_usd=False)}</code> (-{pct}% OFF)\n"
            btn_text = f"Buy {product['title']}"
        else:
            heading = "📈 <b>Price Update Alert</b>"
            diff_line = f"<b>Old Price:</b> <code><s>{format_dual_price(old_price, symbol, show_usd=False)}</s></code>\n"
            price_line = f"<b>Price:</b> <code>{format_dual_price(new_price, symbol, show_usd=False)}</code> (+{pct}%)\n"
            btn_text = f"View {product['title']}"

        button = await self._buy_button(product, btn_text)

        msg_body = (
            f"{heading}\n\n"
            f"<b>Product:</b> {icon_prefix}<b>{title}</b>\n"
            f"{duration_line}"
            f"{diff_line}"
            f"{price_line}"
            f"{delivery_line}"
        )

        # 1. Deliver to Telegram Bot Admins
        admin_delivered = await self.notifier.send_admin(
            msg_body,
            event="price_change",
            keyboard=button,
        )

        # 2. Deliver to Channels if configured and auto_price_drop_alerts is enabled
        raw_channels = values.get("announcement_channel", "")
        channels = self._channels(raw_channels)
        channel_delivered = False
        if channels and values.get("auto_price_drop_alerts", "1") != "0":
            for ch in channels:
                deliv = await self.notifier.send(
                    ch,
                    msg_body,
                    button,
                )
                if deliv:
                    channel_delivered = True

        return admin_delivered or channel_delivered

    async def price_drop(self, product_id: int, old_price: float, new_price: float) -> bool:
        """Backward-compatible method for price drop."""
        return await self.price_change(product_id, old_price, new_price)

    async def promote(self, product_id: int) -> bool:
        values = await self.settings.values()
        product = await self._active_product(product_id)
        if not product:
            return False
        symbol = escape(values["currency_symbol"])
        icon = self._product_icon(product)
        icon_prefix = f"{icon} " if icon else ""
        title = escape(product["title"])
        desc = f"\n{escape(product.get('description'))}\n" if product.get("description") else ""
        duration = (product.get("duration_label") or "").strip()
        duration_line = f"<b>Validity:</b> {escape(duration)}\n" if duration and duration.lower() not in {"instant", "none", "n/a", ""} else ""
        is_manual = product.get("delivery_type") == "manual"
        delivery_line = "<b>Delivery:</b> Manual" if is_manual else "<b>Delivery:</b> Instant (Automatic)"

        button = await self._buy_button(product, f"Order {product['title']}")
        text = (
            f"⭐ <b>Featured Product</b>\n\n"
            f"<b>Product:</b> {icon_prefix}<b>{title}</b>\n"
            f"{duration_line}"
            f"{desc}"
            f"<b>Available Stock:</b> <code>{product['stock']} units</code>\n"
            f"<b>Price:</b> <code>{format_dual_price(product['price'], symbol, show_usd=False)}</code>\n"
            f"{delivery_line}"
        )

        # 1. Send to Bot Admin
        admin_delivered = await self.notifier.send_admin(
            text,
            event="general",
            keyboard=button,
        )

        # 2. Post to channels if configured
        raw_channels = values.get("announcement_channel", "")
        channels = self._channels(raw_channels)
        channel_delivered = False
        if channels:
            for ch in channels:
                deliv = await self.notifier.send(
                    ch,
                    text,
                    button,
                )
                if deliv:
                    channel_delivered = True

        return admin_delivered or channel_delivered
