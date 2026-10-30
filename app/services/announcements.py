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


def format_customer_short_name(first_name: str | None, last_name: str | None, username: str | None = None) -> str:
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    if fn and ln:
        return f"{fn} {ln[0].upper()}."
    if fn:
        return fn
    if ln:
        return ln
    if username:
        u = username.strip().lstrip("@")
        if len(u) <= 3:
            return f"@{u}"
        return f"@{u[:2]}***{u[-1]}"
    return "Verified Buyer"


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
            f"Price: <code>{format_dual_price(product['price'], symbol, show_usd=False)}</code></blockquote>",
            event="restock",
            keyboard=button,
        )
        raw_channels = values.get("announcement_channel", "")
        channels = self._channels(raw_channels)
        if not channels or values.get("auto_restock_alerts", "1") == "0":
            return admin_delivered

        channel_delivered = False
        bot_uname = await self.notifier.bot_username()
        ch_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Buy Now", url=f"https://t.me/{bot_uname}?start=prod_{product['id']}")],
        ])
        for ch in channels:
            deliv = await self.notifier.send(
                ch,
                f"✅ <b>Product Restocked</b>\n\n"
                f"<blockquote>Product: {icon_prefix}<b>{title}</b>\n"
                f"{duration_line}"
                f"Price: <code>{format_dual_price(product['price'], symbol, show_usd=False)}</code>\n"
                f"Status: In Stock ✅</blockquote>",
                ch_kb,
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

    async def broadcast_order_proof(
        self,
        product_id: int | None,
        product_title: str,
        price_str: str,
        quantity: int = 1,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
    ) -> bool:
        values = await self.settings.values()
        raw_channels = values.get("announcement_channel", "")
        channels = self._channels(raw_channels)
        if not channels:
            return False

        qty_suffix = f" (x{quantity})" if quantity > 1 else ""
        cust_name = escape(format_customer_short_name(first_name, last_name, username))
        title = escape(product_title)

        text = (
            "🛍️ <b>New Order Delivered!</b>\n\n"
            f"<blockquote>Product: <b>{title}{qty_suffix}</b>\n"
            f"Customer: <b>{cust_name}</b>\n"
            f"Paid: <code>{price_str}</code>\n"
            "Status: Delivered ✅</blockquote>"
        )
        bot_uname = await self.notifier.bot_username()
        buy_url = f"https://t.me/{bot_uname}?start=prod_{product_id}" if product_id else f"https://t.me/{bot_uname}?start=shop"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Buy This Item", url=buy_url)]
        ])
        for ch in channels:
            await self.notifier.send(ch, text, keyboard=kb)
        return True

    async def broadcast_referral_proof(
        self,
        reward_str: str,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
    ) -> bool:
        values = await self.settings.values()
        raw_channels = values.get("announcement_channel", "")
        channels = self._channels(raw_channels)
        if not channels:
            return False

        inviter_name = escape(format_customer_short_name(first_name, last_name, username))
        text = (
            "🎁 <b>Referral Bonus Credited!</b>\n\n"
            f"<blockquote>Inviter: <b>{inviter_name}</b>\n"
            f"Bonus: <code>+{reward_str}</code>\n"
            "Status: Added to Wallet ✅</blockquote>"
        )
        bot_uname = await self.notifier.bot_username()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Invite & Earn", url=f"https://t.me/{bot_uname}?start=ref")]
        ])
        for ch in channels:
            await self.notifier.send(ch, text, keyboard=kb)
        return True

    async def broadcast_deposit_proof(
        self,
        method_name: str,
        amount_str: str,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
    ) -> bool:
        values = await self.settings.values()
        raw_channels = values.get("announcement_channel", "")
        channels = self._channels(raw_channels)
        if not channels:
            return False

        cust_name = escape(format_customer_short_name(first_name, last_name, username))
        text = (
            "💰 <b>Wallet Deposit Confirmed!</b>\n\n"
            f"<blockquote>Customer: <b>{cust_name}</b>\n"
            f"Method: <b>{escape(method_name)}</b>\n"
            f"Amount: <code>{amount_str}</code>\n"
            "Status: Balance Added ✅</blockquote>"
        )
        bot_uname = await self.notifier.bot_username()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Add Balance", url=f"https://t.me/{bot_uname}?start=wallet")]
        ])
        for ch in channels:
            await self.notifier.send(ch, text, keyboard=kb)
        return True

    async def broadcast_reseller_proof(
        self,
        first_name: str | None = None,
        last_name: str | None = None,
        username: str | None = None,
    ) -> bool:
        values = await self.settings.values()
        raw_channels = values.get("announcement_channel", "")
        channels = self._channels(raw_channels)
        if not channels:
            return False

        partner_name = escape(format_customer_short_name(first_name, last_name, username))
        text = (
            "💼 <b>New Reseller Partner Joined!</b>\n\n"
            f"<blockquote>Partner: <b>{partner_name}</b>\n"
            "Tier: <b>Official Reseller</b>\n"
            "Status: Wholesale API Activated ⚡</blockquote>"
        )
        bot_uname = await self.notifier.bot_username()
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Reseller Program", url=f"https://t.me/{bot_uname}?start=reseller")]
        ])
        for ch in channels:
            await self.notifier.send(ch, text, keyboard=kb)
        return True
