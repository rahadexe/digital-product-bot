from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import quote
from uuid import uuid4

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot.formatting import format_dual_price
from app.bot.icons import Icons
from app.core.i18n import t

ADMIN_PANEL_TEXT = "👑 Admin Panel"


def get_main_inline_keyboard(
    pinned_categories: List[Dict[str, Any]] | None = None,
    has_unpinned: bool = False,
    is_admin: bool = False,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """
    Optimized inline dashboard matching the rich keyboard layout:
    - Pinned categories at top (2 per row), with custom icons & emojis.
    - Other Products / All Products button.
    - Action Rows:
      - [ 💳 Add Balance ]  [ 👤 My Profile ]
      - [ 📦 My Orders ]    [ 🎁 Refer & Earn ]
      - [ 🎧 Support ]      [ 🌐 Language ]
      - [ 👑 Admin Panel ] (if admin)
    """
    rows: List[List[InlineKeyboardButton]] = []
    cat_buttons: List[InlineKeyboardButton] = []

    if pinned_categories:
        for c in pinned_categories:
            name = c["name"].strip()
            custom_emoji_id = c.get("custom_emoji_id")
            icon = (c.get("icon") or "").strip()
            btn_text = f"{icon} {name}".strip() if icon and not name.startswith(icon) else name
            kwargs: Dict[str, Any] = {
                "text": btn_text[:64],
                "callback_data": f"cat_{c['id']}",
                "style": "primary",
            }
            if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
                kwargs["icon_custom_emoji_id"] = str(custom_emoji_id).strip()
            cat_buttons.append(InlineKeyboardButton(**kwargs))

    # Add "Other Products" if unpinned categories exist OR "All Products" if no categories are pinned
    if has_unpinned or not pinned_categories:
        other_label = t("btn_other_products", lang) if pinned_categories else t("btn_all_products", lang)
        cat_buttons.append(
            InlineKeyboardButton(
                text=other_label,
                callback_data="open_categories",
                style="primary",
                icon_custom_emoji_id=Icons.PRODUCTS,
            )
        )

    # Chunk category buttons 2 per row
    for i in range(0, len(cat_buttons), 2):
        rows.append(cat_buttons[i : i + 2])

    # Core action buttons (clean layout: Wallet & Profile, Support below)
    rows.append([
        InlineKeyboardButton(
            text=t("btn_wallet", lang),
            callback_data="open_deposit",
            style="primary",
            icon_custom_emoji_id=Icons.BALANCE,
        ),
        InlineKeyboardButton(
            text=t("btn_profile", lang),
            callback_data="open_account",
            style="primary",
            icon_custom_emoji_id=Icons.ACCOUNT,
        ),
    ])
    rows.append([
        InlineKeyboardButton(
            text=t("btn_refer_earn", lang),
            callback_data="open_referral",
            style="primary",
            icon_custom_emoji_id=Icons.REFER,
        ),
        InlineKeyboardButton(
            text=t("btn_support", lang),
            callback_data="open_support",
            style="primary",
            icon_custom_emoji_id=Icons.SUPPORT,
        ),
    ])

    if is_admin:
        rows.append([
            InlineKeyboardButton(
                text=t("btn_admin_panel", lang),
                callback_data="adm_dashboard",
                style="success",
                icon_custom_emoji_id=Icons.CROWN,
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_persistent_reply_keyboard(
    pinned_categories: List[Dict[str, Any]] | None = None,
    has_unpinned: bool = False,
    is_reseller: bool = False,
    is_admin: bool = False,
    lang: str = "en",
) -> ReplyKeyboardMarkup:
    """
    Fully dynamic persistent reply keyboard:
    - Pinned categories are rendered with their names and custom emojis from database.
    - If unpinned categories exist (or no categories are pinned), an 'Other Products' button is included.
    - Standard system action rows below with unicode icons so non-Premium users also see icons.
    - Localized according to user's preferred language.
    """
    rows: List[List[KeyboardButton]] = []
    cat_buttons: List[KeyboardButton] = []

    if pinned_categories:
        for c in pinned_categories:
            name = c["name"].strip()
            custom_emoji_id = c.get("custom_emoji_id")
            icon = (c.get("icon") or "").strip()
            btn_text = f"{icon} {name}".strip() if icon and not name.startswith(icon) else name
            kwargs: Dict[str, Any] = {
                "text": btn_text,
            }
            if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
                kwargs["icon_custom_emoji_id"] = str(custom_emoji_id).strip()
            cat_buttons.append(KeyboardButton(**kwargs))

    # Add "Other Products" if unpinned categories exist OR if no pinned categories exist
    if has_unpinned or not pinned_categories:
        other_kwargs: Dict[str, Any] = {
            "text": t("btn_other_products", lang),
            "icon_custom_emoji_id": Icons.PRODUCTS,
        }
        cat_buttons.append(KeyboardButton(**other_kwargs))

    # Chunk category buttons 2 per row
    for i in range(0, len(cat_buttons), 2):
        rows.append(cat_buttons[i : i + 2])

    rows.append([
        KeyboardButton(text=t("btn_all_products", lang), icon_custom_emoji_id=Icons.PRODUCTS),
        KeyboardButton(text=t("btn_add_balance", lang), icon_custom_emoji_id=Icons.DEPOSIT),
    ])
    rows.append([
        KeyboardButton(text=t("btn_my_orders", lang), icon_custom_emoji_id=Icons.ORDERS),
        KeyboardButton(text=t("btn_my_balance", lang), icon_custom_emoji_id=Icons.BALANCE),
    ])
    rows.append([
        KeyboardButton(text=t("btn_support", lang), icon_custom_emoji_id=Icons.SUPPORT),
    ])

    if is_admin:
        rows.append([KeyboardButton(text=t("btn_admin_panel", lang), icon_custom_emoji_id=Icons.CROWN)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
    )


def get_categories_keyboard(
    categories: List[Dict[str, Any]],
    show_all_option: bool = True,
    page: int = 1,
    page_size: int = 8,
    lang: str = "en",
    back_target: str | None = "back_to_main",
) -> InlineKeyboardMarkup:
    """Inline keyboard listing unpinned categories with grid layout and pagination."""
    buttons = []
    total_categories = len(categories)
    total_pages = max(1, (total_categories + page_size - 1) // page_size) if total_categories > 0 else 1
    page = max(1, min(page, total_pages))

    start = (page - 1) * page_size
    end = start + page_size
    current_page_categories = categories[start:end]

    cat_buttons = []
    for c in current_page_categories:
        name = c["name"].strip()
        custom_emoji_id = c.get("custom_emoji_id")
        icon = (c.get("icon") or "").strip()
        btn_text = f"{icon} {name}".strip() if icon and not name.startswith(icon) else name
        kwargs: Dict[str, Any] = {
            "text": btn_text[:64],
            "callback_data": f"cat_{c['id']}",
            "style": "primary",
        }
        if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
            kwargs["icon_custom_emoji_id"] = str(custom_emoji_id).strip()
        cat_buttons.append(InlineKeyboardButton(**kwargs))

    for i in range(0, len(cat_buttons), 2):
        buttons.append(cat_buttons[i : i + 2])

    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text=t("btn_prev", lang),
                    callback_data=f"catpage_{page - 1}",
                    style="primary",
                    icon_custom_emoji_id=Icons.BACK,
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data=f"catpage_{page}",
                style="primary",
                icon_custom_emoji_id=Icons.REFRESH,
            )
        )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text=t("btn_next", lang),
                    callback_data=f"catpage_{page + 1}",
                    style="primary",
                    icon_custom_emoji_id=Icons.NEXT,
                )
            )
        buttons.append(nav_row)

    if show_all_option:
        buttons.append([
            InlineKeyboardButton(
                text=t("btn_all_products", lang),
                callback_data="shop_all",
                style="success",
                icon_custom_emoji_id=Icons.PRODUCTS,
            ),
        ])

    nav_bottom = []
    if back_target:
        nav_bottom.append(InlineKeyboardButton(text=t("btn_back", lang), callback_data=back_target, style="primary", icon_custom_emoji_id=Icons.BACK))
        if back_target != "back_to_main":
            nav_bottom.append(InlineKeyboardButton(text=t("btn_main_menu", lang), callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.HOME))
    if nav_bottom:
        buttons.append(nav_bottom)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_validity_selector_keyboard(
    category_id: int,
    validities: List[str],
    show_all_option: bool = True,
    back_target: str = "open_categories",
) -> InlineKeyboardMarkup:
    """
    Renders validity durations (e.g. '3 Days Validity', '7 Days Validity') in a 2-column grid.
    Followed by an 'All Products' option and navigation buttons.
    """
    buttons: List[List[InlineKeyboardButton]] = []
    val_buttons: List[InlineKeyboardButton] = []

    for idx, v in enumerate(validities):
        label = v.strip()
        val_buttons.append(
            InlineKeyboardButton(
                text=label[:64],
                callback_data=f"catval_{category_id}_{idx}",
                style="primary",
                icon_custom_emoji_id=Icons.TIMER,
            )
        )

    for i in range(0, len(val_buttons), 2):
        buttons.append(val_buttons[i : i + 2])

    if show_all_option:
        buttons.append([
            InlineKeyboardButton(
                text="All",
                callback_data=f"catval_all_{category_id}",
                style="success",
                icon_custom_emoji_id=Icons.PRODUCTS,
            )
        ])

    nav_row: List[InlineKeyboardButton] = []
    effective_back = back_target if back_target and back_target != "close_menu" else "open_categories"
    nav_row.append(
        InlineKeyboardButton(
            text="Back",
            callback_data=effective_back,
            style="primary",
            icon_custom_emoji_id=Icons.BACK,
        )
    )
    if effective_back != "back_to_main":
        nav_row.append(
            InlineKeyboardButton(
                text="Main Menu",
                callback_data="back_to_main",
                style="primary",
                icon_custom_emoji_id=Icons.HOME,
            )
        )
    buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_gate_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Keyboard for mandatory force-join verification with premium icons."""
    buttons = []
    for ch in channels:
        label = ch.get("title") or ch.get("channel_username") or "Join Channel"
        url = ch.get("invite_link") or f"https://t.me/{ch.get('channel_username', '').lstrip('@')}"
        clean_label = label.lstrip("📢 ").strip()
        buttons.append([
            InlineKeyboardButton(
                text=clean_label[:40],
                url=url,
                style="primary",
                icon_custom_emoji_id=Icons.CHANNEL,
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="I've Joined",
            callback_data="gate_verify",
            style="success",
            icon_custom_emoji_id=Icons.CONFIRM,
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_inline_dashboard(channel_url: str | None = None, is_reseller: bool = False) -> InlineKeyboardMarkup:
    """Inline dashboard — 9 core action buttons matching the PremiumHaven banner."""
    reseller_btn_text = "Reseller Panel" if is_reseller else "Apply as a Reseller"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Buy VPN", callback_data="open_cat_vpn", style="primary", icon_custom_emoji_id=Icons.SHIELD),
                InlineKeyboardButton(text="Proxy Hub", callback_data="open_cat_proxy", style="primary", icon_custom_emoji_id=Icons.GLOBE),
            ],
            [
                InlineKeyboardButton(text="Premium Products", callback_data="open_premium_products", style="success", icon_custom_emoji_id=Icons.CROWN),
                InlineKeyboardButton(text="Mail Box", callback_data="open_cat_mailbox", style="primary", icon_custom_emoji_id=Icons.MAIL),
            ],
            [
                InlineKeyboardButton(text="Add Balance", callback_data="open_deposit", style="primary", icon_custom_emoji_id=Icons.DEPOSIT),
                InlineKeyboardButton(text="Refer & Earn", callback_data="open_referral", style="success", icon_custom_emoji_id=Icons.REFER),
            ],
            [
                InlineKeyboardButton(text="My Profile", callback_data="open_account", style="primary", icon_custom_emoji_id=Icons.ACCOUNT),
                InlineKeyboardButton(text="Support", callback_data="open_support", style="primary", icon_custom_emoji_id=Icons.SUPPORT),
            ],
            [
                InlineKeyboardButton(text=reseller_btn_text, callback_data="open_reseller", style="success", icon_custom_emoji_id=Icons.RESELLER),
            ],
            [
                InlineKeyboardButton(text="How to use this bot", callback_data="open_guide", style="primary", icon_custom_emoji_id=Icons.NOTE),
            ],
        ]
    )


def get_update_channels_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """One full-width link button per channel, in the order the admin set."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ch["title"], url=ch["url"], style="success", icon_custom_emoji_id=Icons.CHANNEL)] for ch in channels
        ]
    )


def get_account_keyboard(
    lang: str = "en",
    is_admin: bool = False,
    ref_link: str | None = None,
) -> InlineKeyboardMarkup:
    """Wallet / Profile actions: order history, balance history, language, back."""
    buttons = [
        [
            InlineKeyboardButton(text=t("btn_my_orders", lang), callback_data="open_orders", style="primary", icon_custom_emoji_id=Icons.ORDERS),
        ],
        [
            InlineKeyboardButton(text=t("btn_change_language", lang), callback_data="open_language_menu", style="primary", icon_custom_emoji_id=Icons.GLOBE),
        ],
        [
            InlineKeyboardButton(text=t("btn_back", lang), callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.BACK),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_language_selection_keyboard(current_lang: str = "en", back_target: str | None = "open_account") -> InlineKeyboardMarkup:
    """Language selection keyboard with English, Bengali, Hindi, and Urdu."""
    langs = [
        ("en", "🇬🇧 English", Icons.GLOBE),
        ("bn", "🇧🇩 বাংলা", Icons.GLOBE),
        ("hi", "🇮🇳 हिन्दी", Icons.GLOBE),
        ("ur", "🇵🇰 اردو", Icons.GLOBE),
    ]
    rows = []
    row = []
    for code, label, icon in langs:
        display_label = f"✓ {label}" if code == current_lang else label
        row.append(
            InlineKeyboardButton(
                text=display_label,
                callback_data=f"set_lang_{code}",
                style="success" if code == current_lang else "primary",
                icon_custom_emoji_id=icon,
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    nav_row = []
    if back_target:
        nav_row.append(
            InlineKeyboardButton(text=t("btn_back", current_lang), callback_data=back_target, style="primary", icon_custom_emoji_id=Icons.BACK)
        )
        if back_target != "back_to_main":
            nav_row.append(
                InlineKeyboardButton(text=t("btn_main_menu", current_lang), callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.HOME)
            )
    if nav_row:
        rows.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)



def get_support_keyboard(
    support_handle: str = "",
    channels: List[Dict[str, Any]] | None = None,
    lang: str = "en",
    back_target: str | None = "back_to_main",
) -> InlineKeyboardMarkup:
    """
    Keyboard for Support:
    - Top: Support direct chat button (full width, highlighted).
    - Middle: Guide and Channel side-by-side in one row.
    - Bottom: Back button.
    """
    rows = []
    if support_handle:
        handle = support_handle.lstrip("@")
        rows.append([
            InlineKeyboardButton(
                text=t("btn_support_chat", lang),
                url=f"https://t.me/{handle}",
                style="success",
                icon_custom_emoji_id=Icons.SUPPORT,
            )
        ])

    guide_btn = InlineKeyboardButton(
        text=t("btn_guide", lang),
        callback_data="open_guide",
        style="primary",
        icon_custom_emoji_id=Icons.NOTE,
    )
    nav_btns = []
    effective_back = back_target or "back_to_main"
    nav_btns.append(
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=effective_back,
            style="primary",
            icon_custom_emoji_id=Icons.BACK,
        )
    )

    channel_btns = []
    if channels:
        for ch in channels:
            title = (ch.get("title") or "Official Channel").strip()
            url = ch.get("url") or ""
            if url:
                channel_btns.append(
                    InlineKeyboardButton(
                        text=title,
                        url=url,
                        style="primary",
                        icon_custom_emoji_id=Icons.CHANNEL,
                    )
                )

    if channel_btns:
        if len(channel_btns) == 1:
            rows.append([guide_btn, channel_btns[0]])
        else:
            rows.append([guide_btn])
            for i in range(0, len(channel_btns), 2):
                rows.append(channel_btns[i : i + 2])
        rows.append(nav_btns)
    else:
        rows.append([guide_btn])
        rows.append(nav_btns)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_products_keyboard(
    products: List[Dict[str, Any]],
    page: int = 1,
    total_pages: int = 1,
    currency_symbol: str = "৳",
    category_id: int | str | None = None,
    back_target: str = "back_to_main",
    is_reseller: bool = False,
    usd_rate: float | None = None,
    show_usd: bool = True,
) -> InlineKeyboardMarkup:
    """
    Vibrant colorful product list keyboard matching user reference:
    In-stock products are blue (style="primary").
    Out-of-stock products are red (style="danger").
    Format: [icon] [title] - [price] (Stock: [stock])
    Bottom nav: [Refresh] [Page] [Next/Prev]
    Bottom row: [Back] [Close]
    """
    buttons = []
    if category_id == "uncategorized":
        prefix = "shop_p_uncat_"
    elif category_id:
        prefix = f"shop_p_{category_id}_"
    else:
        prefix = "shop_p_all_"

    for p in products:
        stock = p.get("stock", 0)
        title = p["title"].strip()
        price_num = p["price"]
        reseller_price = p.get("reseller_price")
        if is_reseller and reseller_price is not None and float(reseller_price) > 0:
            price_num = float(reseller_price)

        price_formatted = format_dual_price(price_num, currency_symbol, usd_rate=usd_rate, show_usd=show_usd)

        custom_emoji_id = p.get("custom_emoji_id")
        clean_title = title
        if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
            for em in ["🌐", "🛡️", "🛡", "⚡", "📱", "🚀", "🤖", "🧠", "🎨", "💻", "✨", "🍿", "🎵", "📺", "⭐", "🎬", "❌", "💎"]:
                if clean_title.startswith(em):
                    clean_title = clean_title[len(em):].strip()
                    break

        # If product has a duration_label set in admin panel and not in title, append it
        duration_label = (p.get("duration_label") or "").strip()
        if duration_label and duration_label.lower() not in {"instant", "none", "n/a", ""}:
            if not re.search(rf"\b{re.escape(duration_label)}\b", clean_title, re.IGNORECASE):
                clean_title = f"{clean_title} {duration_label}"

        # Product icon: if custom emoji is not set, use custom icon if specified
        prod_icon = (p.get("icon") or "").strip()
        has_custom_emoji = bool(custom_emoji_id and str(custom_emoji_id).strip().isdigit())
        if prod_icon and not has_custom_emoji and not clean_title.startswith(prod_icon):
            clean_title = f"{prod_icon} {clean_title}"

        is_manual = p.get("delivery_type") == "manual"
        if is_manual:
            suffix = f" · {price_formatted} [Manual]"
            btn_style = "primary"
        elif stock > 0:
            suffix = f" · {price_formatted} [{stock}]"
            btn_style = "primary"
        else:
            suffix = f" · {price_formatted} [0]"
            btn_style = "danger"

        btn_text = f"{clean_title}{suffix}"
        if len(btn_text) > 64:
            if duration_label and clean_title.lower().endswith(duration_label.lower()):
                base = clean_title[:-len(duration_label)].rstrip()
                avail = max(4, 64 - len(suffix) - len(duration_label) - 2)
                btn_text = f"{base[:avail]}… {duration_label}{suffix}"
            else:
                avail = max(6, 64 - len(suffix) - 1)
                btn_text = f"{clean_title[:avail]}…{suffix}"

        btn_kwargs: dict[str, Any] = {
            "text": btn_text[:64],
            "callback_data": f"prod_{p['id']}",
            "style": btn_style,
        }
        if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
            btn_kwargs["icon_custom_emoji_id"] = str(custom_emoji_id).strip()

        buttons.append([InlineKeyboardButton(**btn_kwargs)])

    nav_row = []
    if total_pages > 1:
        if page == 1:
            nav_row = [
                InlineKeyboardButton(text="Refresh", callback_data=f"{prefix}1", style="success", icon_custom_emoji_id=Icons.REFRESH),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                InlineKeyboardButton(text="Next", callback_data=f"{prefix}2", style="primary", icon_custom_emoji_id=Icons.NEXT),
            ]
        elif page == total_pages:
            nav_row = [
                InlineKeyboardButton(text="Prev", callback_data=f"{prefix}{page - 1}", style="primary", icon_custom_emoji_id=Icons.BACK),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                InlineKeyboardButton(text="Refresh", callback_data=f"{prefix}{page}", style="success", icon_custom_emoji_id=Icons.REFRESH),
            ]
        else:
            nav_row = [
                InlineKeyboardButton(text="Prev", callback_data=f"{prefix}{page - 1}", style="primary", icon_custom_emoji_id=Icons.BACK),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                InlineKeyboardButton(text="Next", callback_data=f"{prefix}{page + 1}", style="primary", icon_custom_emoji_id=Icons.NEXT),
            ]
    else:
        nav_row = [
            InlineKeyboardButton(text="Refresh", callback_data=f"{prefix}1", style="success", icon_custom_emoji_id=Icons.REFRESH),
            InlineKeyboardButton(text="1/1", callback_data="noop"),
            InlineKeyboardButton(text="Next", callback_data=f"{prefix}1_last", style="primary", icon_custom_emoji_id=Icons.NEXT),
        ]

    buttons.append(nav_row)
    effective_back = back_target if back_target and back_target != "none" else "open_categories"
    nav_row = [
        InlineKeyboardButton(text="Back", callback_data=effective_back, style="primary", icon_custom_emoji_id=Icons.BACK),
    ]
    if effective_back != "back_to_main":
        nav_row.append(
            InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.HOME),
        )
    buttons.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_quantity_selector_keyboard(
    product_id: int,
    quantity: int,
    unit_price: float,
    max_stock: int,
    user_balance: float,
    currency_symbol: str = "৳",
    is_manual: bool = False,
    is_upstream: bool = False,
    back_target: str = "open_shop",
    usd_rate: float | None = None,
    show_usd: bool = True,
    product_link: str = "",
    has_description: bool = False,
) -> InlineKeyboardMarkup:
    """
    Interactive Quantity Selector keyboard matching reference UI:
    [-] [Qty] [+]
    [❓ Enter quantity]
    [✅ Confirm (Total)] or [💳 Deposit]
    [🔙 Back]
    """
    total_price = round(unit_price * quantity, 2)
    price_formatted = format_dual_price(total_price, currency_symbol, usd_rate=usd_rate, show_usd=show_usd)
    buttons = []

    dec_qty = max(1, quantity - 1)
    upper_bound = max_stock if not is_manual and not is_upstream and max_stock > 0 else 999
    inc_qty = min(upper_bound, quantity + 1)

    # Row 1: [-]  [ Qty ]  [+]
    row1 = [
        InlineKeyboardButton(
            text="-",
            callback_data=f"qty_set_{product_id}_{dec_qty}",
            style="danger",
            icon_custom_emoji_id=Icons.MINUS,
        ),
        InlineKeyboardButton(
            text=f"{quantity}",
            callback_data="noop",
            style="primary",
        ),
        InlineKeyboardButton(
            text="+",
            callback_data=f"qty_set_{product_id}_{inc_qty}",
            style="success",
            icon_custom_emoji_id=Icons.PLUS,
        ),
    ]
    buttons.append(row1)

    # Row 2: Enter quantity
    buttons.append([
        InlineKeyboardButton(
            text="Enter quantity",
            callback_data=f"qty_custom_{product_id}",
            style="primary",
            icon_custom_emoji_id=Icons.QUESTION,
        )
    ])

    # Row 3: Confirm Purchase / Deposit / Out of Stock
    if not is_manual and not is_upstream and max_stock <= 0:
        buttons.append([
            InlineKeyboardButton(text="Out of Stock", callback_data="noop", style="danger", icon_custom_emoji_id=Icons.CROSS)
        ])
    elif user_balance >= total_price:
        buttons.append([
            InlineKeyboardButton(
                text=f"Confirm ({price_formatted})",
                # The unit price this button was drawn with, in whole cents. An old message
                # still shows the old price; the handler compares before charging.
                callback_data=f"buy_qty_{product_id}_{quantity}_{uuid4().hex[:12]}_{round(unit_price * 100)}",
                style="success",
                icon_custom_emoji_id=Icons.CONFIRM,
            )
        ])
    else:
        short = round(total_price - user_balance, 2)
        short_formatted = format_dual_price(short, currency_symbol, usd_rate=usd_rate, show_usd=show_usd)
        buttons.append([
            InlineKeyboardButton(
                text=f"Deposit (Need {short_formatted} more)",
                callback_data="open_deposit",
                style="primary",
                icon_custom_emoji_id=Icons.DEPOSIT,
            )
        ])

    # Row 4: Description and the shareable link. Both are optional, so a product
    # without a description does not get a button that shows nothing.
    extras = []
    if has_description:
        extras.append(
            InlineKeyboardButton(
                text="Description",
                callback_data=f"prod_desc_{product_id}",
                style="primary",
                icon_custom_emoji_id=Icons.NOTE,
            )
        )
    if product_link:
        # copy_text puts it on the clipboard without a round trip to the bot.
        extras.append(
            InlineKeyboardButton(
                text="Copy Link",
                copy_text=CopyTextButton(text=product_link[:256]),
                style="primary",
                icon_custom_emoji_id=Icons.GLOBE,
            )
        )
    if extras:
        buttons.append(extras)

    # Row 5: Back & Main Menu
    effective_back = back_target if back_target and back_target != "close_menu" else "open_categories"
    nav_row = [
        InlineKeyboardButton(text="Back", callback_data=effective_back, style="primary", icon_custom_emoji_id=Icons.BACK),
    ]
    if effective_back != "back_to_main":
        nav_row.append(
            InlineKeyboardButton(text="Main Menu", callback_data="back_to_main", style="primary", icon_custom_emoji_id=Icons.HOME),
        )
    buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_custom_quantity_keypad(product_id: int) -> InlineKeyboardMarkup:
    """
    Numeric keypad matching reference UI:
    1   2   3
    4   5   6
    7   8   9
    ⌫   0   🗑️ Clear
    25  50  100
    Max     Confirm
    Back
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1", callback_data=f"qpad_{product_id}_1"),
                InlineKeyboardButton(text="2", callback_data=f"qpad_{product_id}_2"),
                InlineKeyboardButton(text="3", callback_data=f"qpad_{product_id}_3"),
            ],
            [
                InlineKeyboardButton(text="4", callback_data=f"qpad_{product_id}_4"),
                InlineKeyboardButton(text="5", callback_data=f"qpad_{product_id}_5"),
                InlineKeyboardButton(text="6", callback_data=f"qpad_{product_id}_6"),
            ],
            [
                InlineKeyboardButton(text="7", callback_data=f"qpad_{product_id}_7"),
                InlineKeyboardButton(text="8", callback_data=f"qpad_{product_id}_8"),
                InlineKeyboardButton(text="9", callback_data=f"qpad_{product_id}_9"),
            ],
            [
                InlineKeyboardButton(text="⌫", callback_data=f"qpad_{product_id}_del", style="primary"),
                InlineKeyboardButton(text="0", callback_data=f"qpad_{product_id}_0"),
                InlineKeyboardButton(text="Clear", callback_data=f"qpad_{product_id}_clr", style="danger", icon_custom_emoji_id=Icons.CLEAR),
            ],
            [
                InlineKeyboardButton(text="25", callback_data=f"qpad_{product_id}_set_25"),
                InlineKeyboardButton(text="50", callback_data=f"qpad_{product_id}_set_50"),
                InlineKeyboardButton(text="100", callback_data=f"qpad_{product_id}_set_100"),
            ],
            [
                InlineKeyboardButton(text="Max", callback_data=f"qpad_{product_id}_max", style="primary"),
                InlineKeyboardButton(text="Confirm", callback_data=f"qpad_{product_id}_confirm", style="success", icon_custom_emoji_id=Icons.CONFIRM),
            ],
            [
                InlineKeyboardButton(text="Back", callback_data=f"qpad_{product_id}_back", style="danger", icon_custom_emoji_id=Icons.BACK),
            ],
        ]
    )


def get_product_detail_keyboard(
    product_id: int,
    category_id: int,
    has_stock: bool,
    user_has_enough_balance: bool,
    price: float,
    currency_symbol: str = "৳",
    usd_rate: float | None = None,
    show_usd: bool = True,
) -> InlineKeyboardMarkup:
    """Fallback simple product keyboard."""
    return get_quantity_selector_keyboard(
        product_id=product_id,
        quantity=1,
        unit_price=price,
        max_stock=999 if has_stock else 0,
        user_balance=999999.0 if user_has_enough_balance else 0.0,
        currency_symbol=currency_symbol,
        usd_rate=usd_rate,
        show_usd=show_usd,
    )


def get_deposit_methods_keyboard(
    methods: List[Dict[str, Any]],
    instant_label: str | None = None,
    back_target: str | None = None,
    lang: str = "en",
    show_history: bool = True,
) -> InlineKeyboardMarkup:
    """Wallet top-up methods with Balance History and Back button."""
    buttons = []

    method_buttons: List[InlineKeyboardButton] = []
    for m in methods:
        name = m.get("name", "Method").strip()
        custom_emoji_id = m.get("custom_emoji_id")
        auto_verify = m.get("auto_verify")
        kwargs: dict[str, Any] = {
            "text": name,
            "callback_data": f"dep_method_{m['id']}",
            "style": "primary",
        }
        name_lower = name.lower()
        # For known BD payment methods, always use the premium icons (override DB value)
        if "bkash" in name_lower:
            kwargs["icon_custom_emoji_id"] = Icons.BKASH
        elif "nagad" in name_lower:
            kwargs["icon_custom_emoji_id"] = Icons.NAGAD
        elif "rocket" in name_lower and auto_verify != "binance_pay":
            kwargs["icon_custom_emoji_id"] = Icons.ROCKET_METHOD
        elif auto_verify == "binance_pay" or "binance" in name_lower:
            kwargs["icon_custom_emoji_id"] = Icons.BINANCE
        elif custom_emoji_id and str(custom_emoji_id).strip().isdigit():
            kwargs["icon_custom_emoji_id"] = str(custom_emoji_id).strip()
        else:
            kwargs["icon_custom_emoji_id"] = Icons.DEPOSIT
        method_buttons.append(InlineKeyboardButton(**kwargs))

    total = len(method_buttons)
    if total == 4:
        # 2x2 grid: 2 on top row, 2 on bottom row
        buttons.append([method_buttons[0], method_buttons[1]])
        buttons.append([method_buttons[2], method_buttons[3]])
    elif total == 3:
        # 3 methods: if first is Binance, place it on top row, 2 local methods on bottom row
        first_is_binance = (
            methods[0].get("auto_verify") == "binance_pay"
            or "binance" in str(methods[0].get("name", "")).lower()
        )
        if first_is_binance:
            buttons.append([method_buttons[0]])
            buttons.append([method_buttons[1], method_buttons[2]])
        else:
            buttons.append([method_buttons[0], method_buttons[1]])
            buttons.append([method_buttons[2]])
    elif total == 2:
        # 2 side-by-side in one row
        buttons.append([method_buttons[0], method_buttons[1]])
    elif total == 1:
        # 1 full width button
        buttons.append([method_buttons[0]])
    elif total > 4:
        # Rows of 2
        for i in range(0, total, 2):
            buttons.append(method_buttons[i : i + 2])

    if instant_label:
        buttons.append([
            InlineKeyboardButton(
                text=str(instant_label).strip(),
                callback_data="dep_instant",
                style="success",
                icon_custom_emoji_id=Icons.LIGHTNING,
            )
        ])

    if show_history:
        buttons.append([
            InlineKeyboardButton(
                text=t("btn_balance_history", lang),
                callback_data="open_deposits_from_wallet",
                style="primary",
                icon_custom_emoji_id=Icons.STATS,
            )
        ])

    nav_row = []
    effective_back = back_target if back_target else "back_to_main"
    nav_row.append(
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=effective_back,
            style="primary",
            icon_custom_emoji_id=Icons.BACK,
        )
    )
    if effective_back != "back_to_main":
        nav_row.append(
            InlineKeyboardButton(
                text=t("btn_main_menu", lang),
                callback_data="back_to_main",
                style="primary",
                icon_custom_emoji_id=Icons.HOME,
            )
        )
    buttons.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_manual_deposit_invoice_keyboard(account_info: str, is_binance: bool = False, lang: str = "en") -> InlineKeyboardMarkup:
    """Actions shown for a deposit method: copy number/UID, I've paid, change method."""
    destination = str(account_info or "").strip()
    buttons = []
    if destination.startswith("https://"):
        buttons.append([
            InlineKeyboardButton(
                text=t("btn_open_payment_page", lang),
                url=destination,
                style="primary",
                icon_custom_emoji_id=Icons.GLOBE,
            )
        ])
    elif destination:
        btn_label = t("btn_copy_uid", lang) if is_binance else t("btn_copy_number", lang)
        btn_icon = Icons.BINANCE if is_binance else Icons.NOTE
        buttons.append([
            InlineKeyboardButton(
                text=btn_label,
                copy_text=CopyTextButton(text=destination[:256]),
                style="primary",
                icon_custom_emoji_id=btn_icon,
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text=t("btn_payment_done", lang),
            callback_data="dep_confirm_paid",
            style="success",
            icon_custom_emoji_id=Icons.CHECK,
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data="open_deposit",
            style="primary",
            icon_custom_emoji_id=Icons.BACK,
        ),
        InlineKeyboardButton(
            text=t("btn_main_menu", lang),
            callback_data="back_to_main",
            style="primary",
            icon_custom_emoji_id=Icons.HOME,
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard(back_target: str | None = "open_deposit", lang: str = "en") -> InlineKeyboardMarkup:
    effective_back = back_target or "back_to_main"
    nav_row = [
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=effective_back,
            style="primary",
            icon_custom_emoji_id=Icons.BACK,
        )
    ]
    if effective_back != "back_to_main":
        nav_row.append(
            InlineKeyboardButton(
                text=t("btn_main_menu", lang),
                callback_data="back_to_main",
                style="primary",
                icon_custom_emoji_id=Icons.HOME,
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[nav_row])


def get_deposit_amount_keyboard(account_info: str, method_id: int, is_binance: bool = False, lang: str = "en") -> InlineKeyboardMarkup:
    """Buttons on the Enter Amount screen: copy number/UID, Back to invoice."""
    destination = str(account_info or "").strip()
    buttons = []
    if destination:
        btn_label = t("btn_copy_uid", lang) if is_binance else t("btn_copy_number", lang)
        btn_icon = Icons.BINANCE if is_binance else Icons.NOTE
        buttons.append([
            InlineKeyboardButton(
                text=btn_label,
                copy_text=CopyTextButton(text=destination[:256]),
                style="primary",
                icon_custom_emoji_id=btn_icon,
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text=t("btn_back", lang),
            callback_data=f"dep_method_{method_id}",
            style="primary",
            icon_custom_emoji_id=Icons.BACK,
        ),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_deposit_txid_keyboard(is_bangla: bool = False, lang: str = "en") -> InlineKeyboardMarkup:
    """Buttons on the Enter TrxID screen: Back to change amount."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_change_amount", lang),
                    callback_data="dep_confirm_paid",
                    style="primary",
                    icon_custom_emoji_id=Icons.BACK,
                ),
            ],
        ]
    )
