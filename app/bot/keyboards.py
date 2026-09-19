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

from app.bot.icons import Icons


def get_persistent_reply_keyboard(
    pinned_categories: List[Dict[str, Any]] | None = None,
    has_unpinned: bool = False,
) -> ReplyKeyboardMarkup:
    """
    Fully dynamic persistent reply keyboard:
    - Pinned categories are rendered with their names and custom emojis from database.
    - If unpinned categories exist (or no categories are pinned), an 'Other Products' button is included.
    - Standard system action rows below.
    """
    rows: List[List[KeyboardButton]] = []
    cat_buttons: List[KeyboardButton] = []

    if pinned_categories:
        for c in pinned_categories:
            name = c["name"].strip()
            custom_emoji_id = c.get("custom_emoji_id")
            kwargs: Dict[str, Any] = {
                "text": name,
                "style": "primary",
            }
            if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
                kwargs["icon_custom_emoji_id"] = str(custom_emoji_id).strip()
            cat_buttons.append(KeyboardButton(**kwargs))

    # Add "Other Products" if unpinned categories exist OR if no pinned categories exist
    if has_unpinned or not pinned_categories:
        cat_buttons.append(
            KeyboardButton(text="Other Products", style="success", icon_custom_emoji_id=Icons.VIP)
        )

    # Chunk category buttons 2 per row
    for i in range(0, len(cat_buttons), 2):
        rows.append(cat_buttons[i : i + 2])

    # System rows
    rows.append([
        KeyboardButton(text="Add Balance", style="primary", icon_custom_emoji_id=Icons.DEPOSIT),
        KeyboardButton(text="Refer & Earn", style="success", icon_custom_emoji_id=Icons.REFER),
    ])
    rows.append([
        KeyboardButton(text="My Profile", style="primary", icon_custom_emoji_id=Icons.ACCOUNT),
        KeyboardButton(text="Support", style="primary", icon_custom_emoji_id=Icons.SUPPORT),
    ])
    rows.append([
        KeyboardButton(text="Apply as a Reseller", style="success", icon_custom_emoji_id=Icons.RESELLER),
    ])

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
        kwargs: Dict[str, Any] = {
            "text": name[:64],
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
                    text="Prev",
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
                    text="Next",
                    callback_data=f"catpage_{page + 1}",
                    style="primary",
                    icon_custom_emoji_id=Icons.NEXT,
                )
            )
        buttons.append(nav_row)

    if show_all_option:
        buttons.append([
            InlineKeyboardButton(
                text="All Products",
                callback_data="shop_all",
                style="success",
                icon_custom_emoji_id=Icons.PRODUCTS,
            ),
            InlineKeyboardButton(
                text="Uncategorized",
                callback_data="shop_uncat",
                style="primary",
                icon_custom_emoji_id=Icons.NOTE,
            ),
        ])

    buttons.append([
        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_validity_selector_keyboard(
    category_id: int,
    validities: List[str],
    show_all_option: bool = True,
    back_target: str = "close_menu",
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
                text="All Products",
                callback_data=f"catval_all_{category_id}",
                style="success",
                icon_custom_emoji_id=Icons.PRODUCTS,
            )
        ])

    nav_row: List[InlineKeyboardButton] = []
    if back_target and back_target not in ("close_menu", "back_to_main"):
        nav_row.append(
            InlineKeyboardButton(
                text="Back",
                callback_data=back_target,
                style="primary",
                icon_custom_emoji_id=Icons.BACK,
            )
        )
    nav_row.append(
        InlineKeyboardButton(
            text="Close",
            callback_data="close_menu",
            style="danger",
            icon_custom_emoji_id=Icons.CLOSE,
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
            text="Joined",
            callback_data="gate_verify",
            style="success",
            icon_custom_emoji_id=Icons.CHECK,
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_main_inline_dashboard(channel_url: str | None = None) -> InlineKeyboardMarkup:
    """Inline dashboard — 9 core action buttons matching the PremiumHaven banner."""
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
                InlineKeyboardButton(text="Apply as a Reseller", callback_data="open_reseller", style="success", icon_custom_emoji_id=Icons.RESELLER),
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


def get_account_keyboard() -> InlineKeyboardMarkup:
    """Account actions: view order history or balance history."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Order History", callback_data="open_orders", style="primary", icon_custom_emoji_id=Icons.ORDERS),
            ],
            [
                InlineKeyboardButton(text="Balance History", callback_data="open_deposits", style="primary", icon_custom_emoji_id=Icons.STATS),
            ],
            [
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ],
        ]
    )



def get_support_keyboard(
    support_handle: str = "",
    channels: List[Dict[str, Any]] | None = None,
) -> InlineKeyboardMarkup:
    """Keyboard for Support with direct chat button, active channels, and close button."""
    rows = []
    if support_handle:
        handle = support_handle.lstrip("@")
        rows.append([
            InlineKeyboardButton(
                text="Contact Support",
                url=f"https://t.me/{handle}",
                style="primary",
                icon_custom_emoji_id=Icons.SUPPORT,
            )
        ])
    if channels:
        for ch in channels:
            title = (ch.get("title") or "Channel").strip()
            url = ch.get("url") or ""
            if url:
                rows.append([
                    InlineKeyboardButton(
                        text=title,
                        url=url,
                        style="success",
                        icon_custom_emoji_id=Icons.CHANNEL,
                    )
                ])
    rows.append([
        InlineKeyboardButton(
            text="Close",
            callback_data="close_menu",
            style="danger",
            icon_custom_emoji_id=Icons.CLOSE,
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_products_keyboard(
    products: List[Dict[str, Any]],
    page: int = 1,
    total_pages: int = 1,
    currency_symbol: str = "৳",
    category_id: int | str | None = None,
    back_target: str = "back_to_main",
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
        price_formatted = f"{price_num:g} {currency_symbol}" if price_num == int(price_num) else f"{price_num:.1f} {currency_symbol}"

        custom_emoji_id = p.get("custom_emoji_id")
        clean_title = title
        if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
            for em in ["🌐", "🛡️", "🛡", "⚡", "📱", "🚀", "🤖", "🧠", "🎨", "💻", "✨", "🍿", "🎵", "📺", "⭐", "🎬", "❌", "💎"]:
                if clean_title.startswith(em):
                    clean_title = clean_title[len(em):].strip()
                    break

        is_manual = p.get("delivery_type") == "manual"
        if is_manual:
            btn_text = f"{clean_title} - {price_formatted} (Manual)"
            btn_style = "primary"
        elif stock > 0:
            btn_text = f"{clean_title} - {price_formatted} (Stock: {stock})"
            btn_style = "primary"
        else:
            btn_text = f"{clean_title} - {price_formatted} (Stock: 0)"
            btn_style = "danger"

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
    if back_target and back_target not in ("back_to_main", "none"):
        buttons.append([
            InlineKeyboardButton(text="Back", callback_data=back_target, style="primary", icon_custom_emoji_id=Icons.BACK),
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_quantity_selector_keyboard(
    product_id: int,
    quantity: int,
    unit_price: float,
    max_stock: int,
    user_balance: float,
    currency_symbol: str = "৳",
    is_manual: bool = False,
    back_target: str = "open_shop",
) -> InlineKeyboardMarkup:
    """
    Interactive Quantity Selector keyboard matching reference UI:
    [-] [Qty] [+]
    [❓ Enter quantity]
    [✅ Confirm (Total)] or [💳 Deposit]
    [🔙 Back] [❌ Close]
    """
    total_price = round(unit_price * quantity, 2)
    price_formatted = f"{total_price:g} {currency_symbol}" if total_price == int(total_price) else f"{total_price:.2f} {currency_symbol}"
    buttons = []

    dec_qty = max(1, quantity - 1)
    upper_bound = max_stock if not is_manual and max_stock > 0 else 999
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
    if not is_manual and max_stock <= 0:
        buttons.append([
            InlineKeyboardButton(text="Out of Stock", callback_data="noop", style="danger", icon_custom_emoji_id=Icons.CROSS)
        ])
    elif user_balance >= total_price:
        buttons.append([
            InlineKeyboardButton(
                text=f"Confirm ({price_formatted})",
                callback_data=f"buy_qty_{product_id}_{quantity}_{uuid4().hex[:12]}",
                style="success",
                icon_custom_emoji_id=Icons.CONFIRM,
            )
        ])
    else:
        short = round(total_price - user_balance, 2)
        short_formatted = f"{short:g} {currency_symbol}" if short == int(short) else f"{short:.2f} {currency_symbol}"
        buttons.append([
            InlineKeyboardButton(
                text=f"Deposit (Need {short_formatted} more)",
                callback_data="open_deposit",
                style="primary",
                icon_custom_emoji_id=Icons.DEPOSIT,
            )
        ])

    # Row 4: Back & Close
    buttons.append([
        InlineKeyboardButton(text="Back", callback_data=back_target, style="primary", icon_custom_emoji_id=Icons.BACK),
        InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
    ])

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
) -> InlineKeyboardMarkup:
    """Fallback simple product keyboard."""
    return get_quantity_selector_keyboard(
        product_id=product_id,
        quantity=1,
        unit_price=price,
        max_stock=999 if has_stock else 0,
        user_balance=999999.0 if user_has_enough_balance else 0.0,
        currency_symbol=currency_symbol,
    )


def get_deposit_methods_keyboard(
    methods: List[Dict[str, Any]],
    instant_label: str | None = None,
    back_target: str | None = None,
) -> InlineKeyboardMarkup:
    """Wallet top-up methods: clean buttons displaying the exact configured method name."""
    buttons = []
    if instant_label:
        buttons.append([
            InlineKeyboardButton(
                text=str(instant_label).strip(),
                callback_data="dep_instant",
                style="success",
                icon_custom_emoji_id=Icons.LIGHTNING,
            )
        ])

    for m in methods:
        name = m.get("name", "Method").strip()
        custom_emoji_id = m.get("custom_emoji_id")
        auto_verify = m.get("auto_verify")
        kwargs: dict[str, Any] = {
            "text": name,
            "callback_data": f"dep_method_{m['id']}",
            "style": "primary",
        }
        if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
            kwargs["icon_custom_emoji_id"] = str(custom_emoji_id).strip()
        elif auto_verify == "binance_pay" or "binance" in name.lower():
            kwargs["icon_custom_emoji_id"] = Icons.COIN
        else:
            kwargs["icon_custom_emoji_id"] = Icons.DEPOSIT
        buttons.append([InlineKeyboardButton(**kwargs)])

    if back_target:
        buttons.append([
            InlineKeyboardButton(
                text="Back",
                callback_data=back_target,
                style="danger",
                icon_custom_emoji_id=Icons.BACK,
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_manual_deposit_invoice_keyboard(account_info: str) -> InlineKeyboardMarkup:
    """Actions shown for a deposit method: copy number, I've paid, change method."""
    destination = str(account_info or "").strip()
    buttons = []
    if destination.startswith("https://"):
        buttons.append([
            InlineKeyboardButton(
                text="Open Payment Page",
                url=destination,
                style="primary",
                icon_custom_emoji_id=Icons.GLOBE,
            )
        ])
    elif destination:
        buttons.append([
            InlineKeyboardButton(
                text="Copy Number",
                copy_text=CopyTextButton(text=destination[:256]),
                style="primary",
                icon_custom_emoji_id=Icons.NOTE,
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="Payment Done",
            callback_data="dep_confirm_paid",
            style="success",
            icon_custom_emoji_id=Icons.CHECK,
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="Back",
            callback_data="open_deposit",
            style="danger",
            icon_custom_emoji_id=Icons.BACK,
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Cancel", callback_data="cancel_deposit", style="danger", icon_custom_emoji_id=Icons.CROSS)]]
    )
