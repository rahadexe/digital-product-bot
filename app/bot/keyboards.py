from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)


def get_persistent_reply_keyboard() -> ReplyKeyboardMarkup:
    """Persistent reply keyboard — 6 core actions with Telegram 9.4+ button styles."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛍️ Products", style="success"),
                KeyboardButton(text="💳 Deposit", style="primary"),
            ],
            [
                KeyboardButton(text="📦 Orders", style="success"),
                KeyboardButton(text="👤 Account", style="primary"),
            ],
            [
                KeyboardButton(text="📢 Channel", style="success"),
                KeyboardButton(text="🎧 Support", style="primary"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


def get_gate_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Keyboard for mandatory force-join verification."""
    buttons = []
    for ch in channels:
        label = ch.get("title") or ch.get("channel_username") or "Join Channel"
        url = ch.get("invite_link") or f"https://t.me/{ch.get('channel_username', '').lstrip('@')}"
        buttons.append([InlineKeyboardButton(text=f"📢 {label}", url=url)])

    buttons.append([InlineKeyboardButton(text="✅ Joined", callback_data="gate_verify")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_inline_dashboard(channel_url: str | None = None) -> InlineKeyboardMarkup:
    """Inline dashboard — 6 core action buttons with matching colors."""
    channel_btn = (
        InlineKeyboardButton(text="📢 Channel", url=channel_url, style="success")
        if channel_url
        else InlineKeyboardButton(text="📢 Channel", callback_data="open_channel", style="success")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🛍️ Products", callback_data="open_shop", style="success"),
                InlineKeyboardButton(text="💳 Deposit", callback_data="open_deposit", style="primary"),
            ],
            [
                InlineKeyboardButton(text="👤 Account", callback_data="open_account", style="primary"),
                InlineKeyboardButton(text="📦 Orders", callback_data="open_orders", style="success"),
            ],
            [
                InlineKeyboardButton(text="🎧 Support", callback_data="open_support", style="primary"),
                channel_btn,
            ],
        ]
    )


def get_update_channels_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """One full-width link button per channel, in the order the admin set."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch["url"], style="success")] for ch in channels
        ]
    )


def get_account_keyboard() -> InlineKeyboardMarkup:
    """Account actions: add funds or see past deposits."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Deposit", callback_data="open_deposit_from_account", style="primary"),
                InlineKeyboardButton(text="📜 Deposit History", callback_data="open_deposits", style="primary"),
            ],
        ]
    )


def get_support_keyboard(support_handle: str) -> InlineKeyboardMarkup:
    """Keyboard for Support with direct chat button."""
    rows = []
    if support_handle:
        handle = support_handle.lstrip("@")
        rows.append([InlineKeyboardButton(text="💬 Contact Support", url=f"https://t.me/{handle}", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_products_keyboard(
    products: List[Dict[str, Any]],
    page: int = 1,
    total_pages: int = 1,
    currency_symbol: str = "৳",
    category_id: int | None = None,
) -> InlineKeyboardMarkup:
    """
    Vibrant colorful product list keyboard.
    In-stock products are green (style="success").
    Out-of-stock products are red (style="danger") and sorted to the bottom.
    Each item format matches: [icon] [title] | [price] ৳ | স্টক: [stock] টি
    """
    buttons = []
    prefix = f"shop_p_{category_id}_" if category_id else "shop_p_all_"

    for p in products:
        stock = p.get("stock", 0)
        title = p["title"].strip()
        price_num = p["price"]
        price_formatted = f"{price_num:g} {currency_symbol}" if price_num == int(price_num) else f"{price_num:.1f} {currency_symbol}"
        icon = p.get("icon") or ""
        icon_str = f"{icon} " if icon else ""

        if stock > 0:
            btn_text = f"{icon_str}{title} | {price_formatted} | Stock: {stock}"
            btn_style = "success"
        else:
            btn_text = f"{icon_str}{title} | {price_formatted} | Stock: 0"
            btn_style = "danger"

        buttons.append([
            InlineKeyboardButton(
                text=btn_text[:64],
                callback_data=f"prod_{p['id']}",
                style=btn_style,
            )
        ])

    nav_row = []
    if total_pages > 1:
        if page == 1:
            nav_row = [
                InlineKeyboardButton(text="🔄 Refresh", callback_data=f"{prefix}1", style="success"),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data=f"{prefix}{page}"),
                InlineKeyboardButton(text="▶ Next", callback_data=f"{prefix}{page + 1}", style="primary"),
            ]
        elif page == total_pages:
            nav_row = [
                InlineKeyboardButton(text="◀ Prev", callback_data=f"{prefix}{page - 1}", style="primary"),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data=f"{prefix}{page}"),
                InlineKeyboardButton(text="🔄 Refresh", callback_data=f"{prefix}{page}", style="success"),
            ]
        else:
            nav_row = [
                InlineKeyboardButton(text="◀ Prev", callback_data=f"{prefix}{page - 1}", style="primary"),
                InlineKeyboardButton(text=f"🔄 {page}/{total_pages}", callback_data=f"{prefix}{page}", style="success"),
                InlineKeyboardButton(text="▶ Next", callback_data=f"{prefix}{page + 1}", style="primary"),
            ]
    else:
        nav_row = [
            InlineKeyboardButton(text="🔄 Refresh", callback_data=f"{prefix}1", style="success"),
            InlineKeyboardButton(text="1/1", callback_data=f"{prefix}1"),
        ]

    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀ Back", callback_data="back_to_main", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_product_detail_keyboard(
    product_id: int,
    category_id: int,
    has_stock: bool,
    user_has_enough_balance: bool,
    price: float,
    currency_symbol: str = "৳",
) -> InlineKeyboardMarkup:
    """Product purchase confirmation screen keyboard with Telegram button styles."""
    buttons = []
    price_formatted = f"{price:g} {currency_symbol}" if price == int(price) else f"{price:.1f} {currency_symbol}"

    if not has_stock:
        buttons.append([InlineKeyboardButton(text="❌ Out of Stock", callback_data="noop", style="danger")])
    elif user_has_enough_balance:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Confirm Purchase ({price_formatted})",
                    callback_data=f"buy_{product_id}_{uuid4().hex}",
                    style="success",
                )
            ]
        )
    else:
        buttons.append(
            [InlineKeyboardButton(text="💳 Deposit", callback_data="open_deposit", style="primary")]
        )

    buttons.append([InlineKeyboardButton(text="◀ Back", callback_data="open_shop", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_deposit_methods_keyboard(
    methods: List[Dict[str, Any]],
    instant_label: str | None = None,
    back_target: str | None = None,
) -> InlineKeyboardMarkup:
    """Wallet top-up methods: clean buttons displaying the exact configured method name."""
    buttons = []
    if instant_label:
        buttons.append([InlineKeyboardButton(text=str(instant_label).strip(), callback_data="dep_instant")])

    for m in methods:
        name = m.get("name", "Method").strip()
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"dep_method_{m['id']}")])

    if back_target:
        buttons.append([InlineKeyboardButton(text="◀ Back", callback_data=back_target, style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_manual_deposit_invoice_keyboard(account_info: str) -> InlineKeyboardMarkup:
    """Actions shown for a deposit method: copy number, I've paid, change method."""
    destination = str(account_info or "").strip()
    buttons = []
    if destination.startswith("https://"):
        buttons.append([InlineKeyboardButton(text="🔗 Open Payment Page", url=destination)])
    elif destination:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="📋 Copy Number",
                    copy_text=CopyTextButton(text=destination[:256]),
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="✅ Payment Done", callback_data="dep_confirm_paid")])
    buttons.append([InlineKeyboardButton(text="◀ Back", callback_data="open_deposit", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_deposit", style="danger")]]
    )
