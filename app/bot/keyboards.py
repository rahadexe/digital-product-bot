from __future__ import annotations

import re
from typing import Any, Dict, List
from uuid import uuid4

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.bot.formatting import format_dual_price, resolve_support_url
from app.core.i18n import t

ADMIN_PANEL_TEXT = "Admin Panel"
_TRAILING_VALIDITY = re.compile(
    r"(?:[\s|·\-–—(]+)(\d+\s*(?:days?|weeks?|months?|years?|hours?|mo|m|yr|y|d))(?:\s+validity)?\)?$",
    re.IGNORECASE,
)
_TRAILING_WARRANTY = re.compile(
    r"(?:[\s|·\-–—(]+)((?:full\s+warranty)|(?:\d+\s*[- ]?\s*(?:days?|weeks?|months?)\s+warranty)|(?:fw|sdw|sww|\d+dw|\d+d))\)?$",
    re.IGNORECASE,
)


def extract_emoji_and_name(text: str) -> tuple[str, str]:
    """Extract leading emoji (if any) and remaining text."""
    if not text:
        return "", ""
    s = str(text).strip()
    m = re.match(r"^([^\w\s]+)\s*(.*)$", s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", s


def strip_leading_emoji(text: str) -> str:
    """Strip leading emojis and extra space if text contains them."""
    if not text:
        return text
    cleaned = re.sub(r'^[^\w\s]+\s*', '', str(text))
    return cleaned if cleaned else str(text)


def get_category_icon(name: str, custom_icon: str = "") -> str:
    """Return the explicitly selected basic category icon, if any."""
    if custom_icon and custom_icon.strip():
        return custom_icon.strip()
    return ""


def _catalog_icon(item: Dict[str, Any]) -> tuple[str, str]:
    custom_id = str(item.get("custom_emoji_id") or "").strip()
    if custom_id.isdigit():
        return "", custom_id
    return str(item.get("icon") or "").strip(), ""


def _catalog_button_name(name: str, icon: str, custom_id: str) -> str:
    if icon or custom_id:
        leading_emoji, remainder = extract_emoji_and_name(name)
        if leading_emoji and remainder:
            return remainder
    return name


def _customer_menu(lang: str = "en", show_icons: bool = True) -> list[tuple[str, str]]:
    """Four customer actions in a symmetric 2x2 primary menu."""
    items = [
        ("🛍", "Shop", "open_categories"),
        ("💰", "Balance", "open_deposit"),
        ("💬", "Help", "open_help"),
        ("👤", "Account", "open_account"),
    ]
    return [
        (f"{icon} {label}" if show_icons else label, callback)
        for icon, label, callback in items
    ]


def _admin_panel_label(lang: str = "en", show_icons: bool = True) -> str:
    return f"⚙️ {ADMIN_PANEL_TEXT}" if show_icons else ADMIN_PANEL_TEXT


def get_main_inline_keyboard(
    pinned_categories: List[Dict[str, Any]] | None = None,
    featured_products: List[Dict[str, Any]] | None = None,
    has_unpinned: bool = False,
    is_reseller: bool = False,
    is_admin: bool = False,
    lang: str = "en",
    currency_symbol: str = "$",
    usd_rate: float | None = None,
    show_usd: bool = False,
    currency: str = "BDT",
) -> InlineKeyboardMarkup:
    """Home screen quick utilities: 1-tap currency toggle & referral."""
    curr_label = "💱 Currency: ৳ BDT" if currency == "BDT" else "💱 Currency: $ USD"
    refer_label = "🎁 Referral"
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=curr_label, callback_data="home_toggle_currency"),
            InlineKeyboardButton(text=refer_label, callback_data="home_referral"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_persistent_reply_keyboard(
    pinned_categories: List[Dict[str, Any]] | None = None,
    has_unpinned: bool = False,
    is_reseller: bool = False,
    is_admin: bool = False,
    lang: str = "en",
    show_icons: bool = True,
) -> ReplyKeyboardMarkup:
    """2+3 customer actions; admins additionally get a private shortcut."""
    menu = _customer_menu(lang, show_icons)
    customer_buttons = [KeyboardButton(text=label) for label, _ in menu]
    rows = [customer_buttons[:2], customer_buttons[2:]]
    if is_admin:
        rows.append([KeyboardButton(text=_admin_panel_label(lang, show_icons))])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=False,
    )


def get_categories_reply_keyboard(
    categories: List[Dict[str, Any]],
    lang: str = "en",
    show_icons: bool = True,
) -> ReplyKeyboardMarkup:
    """Pure Reply Keyboard displaying each active category on its own row."""
    rows: List[List[KeyboardButton]] = []
    cat_buttons: List[KeyboardButton] = []
    for c in categories:
        raw_name = c["name"].strip()
        custom_icon, custom_id = _catalog_icon(c)
        raw_name = _catalog_button_name(raw_name, custom_icon, custom_id)
        btn_text = f"{custom_icon} {raw_name}".strip() if custom_icon and show_icons else raw_name
        cat_buttons.append(
            KeyboardButton(
                text=btn_text,
                **(
                    {"icon_custom_emoji_id": custom_id}
                    if custom_id and show_icons
                    else {}
                ),
            )
        )

    rows.extend([[button] for button in cat_buttons])

    back_label = "Back" if lang != "bn" else "ব্যাক"

    rows.append([
        KeyboardButton(text=back_label),
    ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=False)


def get_products_reply_keyboard(
    products: List[Dict[str, Any]],
    currency_symbol: str = "$",
    usd_rate: float | None = None,
    show_usd: bool = False,
    is_reseller: bool = False,
    lang: str = "en",
    show_icons: bool = True,
) -> ReplyKeyboardMarkup:
    """Pure Reply Keyboard listing products in a category."""
    rows: List[List[KeyboardButton]] = []
    prod_buttons: List[KeyboardButton] = []
    for p in products:
        stock = p.get("stock", 0)
        title = p["title"].strip()
        price_num = p["price"]
        reseller_price = p.get("reseller_price")
        if is_reseller and reseller_price is not None and float(reseller_price) > 0:
            price_num = float(reseller_price)

        price_formatted = format_dual_price(price_num, currency_symbol, usd_rate=usd_rate, show_usd=show_usd, lang=lang)
        custom_icon, custom_id = _catalog_icon(p)
        display_title = _catalog_button_name(title, custom_icon, custom_id)
        if custom_icon and show_icons:
            display_title = f"{custom_icon} {display_title}".strip()

        is_manual = p.get("delivery_type") == "manual"
        if is_manual or stock > 0:
            suffix = f" · {price_formatted}"
        else:
            suffix = f" · {price_formatted} [0]"

        btn_text = f"{display_title}{suffix}"
        if len(btn_text) > 40:
            btn_text = f"{display_title[:30]}…{suffix}"

        prod_buttons.append(
            KeyboardButton(
                text=btn_text[:64],
                **(
                    {"icon_custom_emoji_id": custom_id}
                    if custom_id and show_icons
                    else {}
                ),
            )
        )

    for b in prod_buttons:
        rows.append([b])

    back_catalog_label = "Back to Catalog" if lang != "bn" else "ক্যাটালগ"
    main_menu_label = "Main Menu" if lang != "bn" else "মেইন মেনু"
    if show_icons:
        back_catalog_label = f"🔙 {back_catalog_label}"
        main_menu_label = f"🏠 {main_menu_label}"

    rows.append([
        KeyboardButton(text=back_catalog_label),
        KeyboardButton(text=main_menu_label),
    ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_product_detail_reply_keyboard(
    product_id: int,
    price_formatted: str,
    has_stock: bool,
    user_has_enough_balance: bool,
    lang: str = "en",
    show_icons: bool = True,
) -> ReplyKeyboardMarkup:
    """Pure Reply Keyboard for product detail view."""
    rows: List[List[KeyboardButton]] = []
    if not has_stock:
        out_of_stock_text = "Out of Stock" if lang != "bn" else "স্টক শেষ"
        if show_icons:
            out_of_stock_text = f"❌ {out_of_stock_text}"
        rows.append([KeyboardButton(text=out_of_stock_text, style="danger")])
    elif user_has_enough_balance:
        buy_text = f"Buy Now · {price_formatted}" if lang != "bn" else f"কিনুন · {price_formatted}"
        if show_icons:
            buy_text = f"⚡ {buy_text}"
        rows.append([KeyboardButton(text=buy_text, style="success")])
    else:
        add_text = "Add to Balance" if lang != "bn" else "অ্যাড ব্যালেন্স"
        buy_text = f"Buy Now · {price_formatted}" if lang != "bn" else f"কিনুন · {price_formatted}"
        if show_icons:
            add_text = f"💳 {add_text}"
            buy_text = f"⚡ {buy_text}"
        rows.append([
            KeyboardButton(text=add_text),
            KeyboardButton(text=buy_text, style="success"),
        ])

    back_products_label = "Back to Products" if lang != "bn" else "প্রোডাক্ট তালিকা"
    main_menu_label = "Main Menu" if lang != "bn" else "মেইন মেনু"
    if show_icons:
        back_products_label = f"🔙 {back_products_label}"
        main_menu_label = f"🏠 {main_menu_label}"
    rows.append([
        KeyboardButton(text=back_products_label),
        KeyboardButton(text=main_menu_label),
    ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def get_orders_reply_keyboard(lang: str = "en", show_icons: bool = True) -> ReplyKeyboardMarkup:
    """Pure Reply Keyboard for Order History."""
    refresh_label = "Refresh" if lang != "bn" else "রিফ্রেশ"
    catalog_label = "All Catalog" if lang != "bn" else "সকল প্রোডাক্ট"
    back_label = "Back to Main" if lang != "bn" else "ব্যাক"
    if show_icons:
        refresh_label = f"🔄 {refresh_label}"
        catalog_label = f"🛍️ {catalog_label}"
        back_label = f"🔙 {back_label}"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=refresh_label), KeyboardButton(text=catalog_label)],
            [KeyboardButton(text=back_label)],
        ],
        resize_keyboard=True,
    )


def get_support_reply_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Pure Reply Keyboard for Support screen."""
    guide_label = "Guide" if lang != "bn" else "গাইড"
    back_label = "Back to Main" if lang != "bn" else "ব্যাক"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=guide_label)],
            [KeyboardButton(text=back_label)],
        ],
        resize_keyboard=True,
    )


def get_cancel_reply_keyboard(lang: str = "en", show_icons: bool = True) -> ReplyKeyboardMarkup:
    """Pure Reply Keyboard with Cancel button."""
    if lang != "bn":
        cancel_label = "❌ Cancel" if show_icons else "Cancel"
    else:
        cancel_label = "❌ বাতিল" if show_icons else "বাতিল"
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=cancel_label, style="danger")]],
        resize_keyboard=True,
    )



def get_categories_keyboard(
    categories: List[Dict[str, Any]],
    show_all_option: bool = True,
    page: int = 1,
    page_size: int = 8,
    lang: str = "en",
    back_target: str | None = None,
) -> InlineKeyboardMarkup:
    """Inline keyboard listing unpinned categories one per row with pagination."""
    buttons = []
    total_categories = len(categories)
    total_pages = max(1, (total_categories + page_size - 1) // page_size) if total_categories > 0 else 1
    page = max(1, min(page, total_pages))

    start = (page - 1) * page_size
    end = start + page_size
    current_page_categories = categories[start:end]

    cat_buttons = []
    for c in current_page_categories:
        raw_name = c["name"].strip()
        custom_icon, custom_id = _catalog_icon(c)
        raw_name = _catalog_button_name(raw_name, custom_icon, custom_id)
        btn_text = f"{custom_icon} {raw_name}".strip() if custom_icon else raw_name
        cat_buttons.append(
            InlineKeyboardButton(
                text=btn_text[:64],
                callback_data=f"cat_{c['id']}",
                **({"icon_custom_emoji_id": custom_id} if custom_id else {}),
            )
        )

    buttons.extend([[button] for button in cat_buttons])

    if total_pages > 1:
        prev_text = t("btn_prev", lang) or "Prev"
        next_text = t("btn_next", lang) or "Next"
        nav_row = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text=prev_text,
                    callback_data=f"catpage_{page - 1}",
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data=f"catpage_{page}",
            )
        )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text=next_text,
                    callback_data=f"catpage_{page + 1}",
                )
            )
        buttons.append(nav_row)

    if show_all_option:
        all_text = "🛍️ All Products" if lang != "bn" else "🛍️ সকল প্রোডাক্ট"
        buttons.append([
            InlineKeyboardButton(
                text=all_text,
                callback_data="shop_all",
            ),
        ])

    nav_bottom = []
    if back_target:
        back_text = "🔙 Back" if lang != "bn" else "🔙 ব্যাক"
        nav_bottom.append(InlineKeyboardButton(text=back_text, callback_data=back_target))
    if nav_bottom:
        buttons.append(nav_bottom)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_validity_selector_keyboard(
    category_id: int,
    validities: List[str],
    show_all_option: bool = True,
    back_target: str = "open_categories",
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """
    Renders validity durations (e.g. '3 Days Validity', '7 Days Validity') in a 2-column grid.
    Followed by an 'All Products' option and navigation buttons.
    """
    buttons: List[List[InlineKeyboardButton]] = []
    val_buttons: List[InlineKeyboardButton] = []

    for idx, v in enumerate(validities):
        label = v.strip()
        display_label = f"⏱️ {label}" if not label.startswith(("⏱️", "⏳", "🕐")) else label
        val_buttons.append(
            InlineKeyboardButton(
                text=display_label[:64],
                callback_data=f"catval_{category_id}_{idx}",
            )
        )

    for i in range(0, len(val_buttons), 2):
        buttons.append(val_buttons[i : i + 2])

    if show_all_option:
        all_text = "🛍️ All" if lang != "bn" else "🛍️ সকল"
        buttons.append([
            InlineKeyboardButton(
                text=all_text,
                callback_data=f"catval_all_{category_id}",
            )
        ])

    nav_row: List[InlineKeyboardButton] = []
    if back_target and back_target != "close_menu":
        back_text = "🔙 Back" if lang != "bn" else t("btn_back", lang)
        nav_row.append(
            InlineKeyboardButton(
                text=back_text,
                callback_data=back_target,
            )
        )
    if nav_row:
        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_gate_keyboard(channels: List[Dict[str, Any]], product_id: int | None = None) -> InlineKeyboardMarkup:
    """Keyboard for mandatory force-join verification with standard icons."""
    buttons = []
    for ch in channels:
        label = (ch.get("title") or ch.get("channel_username") or "Join Channel").strip()
        url = ch.get("invite_link") or f"https://t.me/{ch.get('channel_username', '').lstrip('@')}"
        clean_label = f"📢 {label}" if not label.startswith("📢") else label
        buttons.append([
            InlineKeyboardButton(
                text=clean_label[:40],
                url=url,
            )
        ])

    verify_callback = f"gate_verify_prod_{product_id}" if product_id else "gate_verify"
    buttons.append([
        InlineKeyboardButton(
            text="✅ I've Joined",
            callback_data=verify_callback,
            style="success",
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)




def get_update_channels_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """One full-width link button per channel, in the order the admin set."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ch["title"], url=ch["url"])] for ch in channels
        ]
    )


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
        chat_text = "Contact support" if lang != "bn" else "সাপোর্টে যোগাযোগ"
        rows.append([
            InlineKeyboardButton(
                text=chat_text,
                url=f"https://t.me/{handle}",
            )
        ])

    guide_text = "Guide" if lang != "bn" else "গাইড"
    guide_btn = InlineKeyboardButton(
        text=guide_text,
        callback_data="open_guide",
    )
    nav_btns = []
    if back_target:
        back_text = "Back" if lang != "bn" else "ফিরে যান"
        nav_btns.append(
            InlineKeyboardButton(
                text=back_text,
                callback_data=back_target,
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
                    )
                )

    if channel_btns:
        if len(channel_btns) == 1:
            rows.append([guide_btn, channel_btns[0]])
        else:
            rows.append([guide_btn])
            for i in range(0, len(channel_btns), 2):
                rows.append(channel_btns[i : i + 2])
        if nav_btns:
            rows.append(nav_btns)
    else:
        rows.append([guide_btn])
        if nav_btns:
            rows.append(nav_btns)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_help_faq_keyboard(
    support_handle: str = "",
    channels: List[Dict[str, Any]] | None = None,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """
    Inline keyboard for Help / FAQ Hub:
    - Stacked common question buttons:
      - How to buy products?
      - How to add balance?
      - How does delivery work?
      - How to earn from referral?
      - Technical support
      - Update Channel
    """
    rows: List[List[InlineKeyboardButton]] = []

    faq_buttons = [
        ("faq_deposit", "How to deposit balance?"),
        ("faq_buy", "How to buy products?"),
        ("faq_delivery", "How does delivery work?"),
        ("faq_referral", "How does referral work?"),
    ]
    tech_label = "Support"
    chan_label = "Updates"

    for callback, label in faq_buttons:
        rows.append([InlineKeyboardButton(text=label, callback_data=callback)])

    clean_handle = (support_handle or "").lstrip("@").strip()
    if clean_handle:
        rows.append([
            InlineKeyboardButton(
                text=tech_label,
                url=f"https://t.me/{clean_handle}",
            )
        ])

    active_channels = [ch for ch in (channels or []) if ch.get("url")]
    if active_channels:
        if len(active_channels) == 1:
            rows.append([
                InlineKeyboardButton(
                    text=chan_label,
                    url=active_channels[0]["url"],
                )
            ])
        else:
            for ch in active_channels:
                label = ch.get("title") or chan_label
                rows.append([
                    InlineKeyboardButton(
                        text=label,
                        url=ch["url"],
                    )
                ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_display_labels(product: Dict[str, Any]) -> tuple[str, str, str]:
    """Return a clean name, validity and warranty without repeating suffixes in the name."""
    title = str(product.get("title") or "").strip()
    icon, custom_id = _catalog_icon(product)
    if icon or custom_id:
        title = _catalog_button_name(title, icon, custom_id)

    duration = str(product.get("duration_label") or "").strip()
    warranty = str(product.get("warranty_label") or "").strip()

    warranty_match = _TRAILING_WARRANTY.search(title)
    if warranty_match:
        if not warranty:
            warranty = warranty_match.group(1).strip()
        title = title[:warranty_match.start()].rstrip()

    if duration and duration.lower() not in {"instant", "none", "n/a"}:
        title = re.sub(
            rf"(?:[\s|·\-–—(]+){re.escape(duration)}\)?$",
            "",
            title,
            flags=re.IGNORECASE,
        ).rstrip()

    validity_match = _TRAILING_VALIDITY.search(title)
    if validity_match:
        if not duration or duration.lower() in {"instant", "none", "n/a"}:
            duration = validity_match.group(1).strip()
        title = title[:validity_match.start()].rstrip()

    warranty = warranty.strip("()").strip()
    return title, duration, warranty


def _compact_duration(label: str) -> str:
    match = re.fullmatch(r"(\d+)\s*(days?|weeks?|months?|years?|hours?)(?:\s+validity)?", label, re.IGNORECASE)
    if not match:
        return label
    units = {"day": "d", "week": "w", "month": "mo", "year": "y", "hour": "h"}
    return match[1] + units[match[2].lower().rstrip("s")]


def get_products_keyboard(
    products: List[Dict[str, Any]],
    page: int = 1,
    total_pages: int = 1,
    currency_symbol: str = "$",
    category_id: int | str | None = None,
    back_target: str = "back_to_main",
    is_reseller: bool = False,
    usd_rate: float | None = None,
    show_usd: bool = False,
    lang: str = "en",
    categories: List[Dict[str, Any]] | None = None,
) -> InlineKeyboardMarkup:
    """
    Product rows show the clean name, validity, optional warranty and price.
    Top rows provide quick category filter chips when categories are supplied.
    Bottom rows provide refresh, pagination and the relevant back navigation.
    """
    buttons = []
    cat_rows: List[List[InlineKeyboardButton]] = []
    if categories:
        top_chips: List[InlineKeyboardButton] = []
        is_all_active = category_id is None or str(category_id).lower() in ("all", "none")
        all_name = "All" if lang != "bn" else "সকল"
        all_label = f"✅ {all_name}" if is_all_active else all_name
        top_chips.append(InlineKeyboardButton(text=all_label, callback_data="shop_p_all_1"))

        visible_cats = [c for c in categories if c.get("id")]
        has_overflow = len(visible_cats) > 5
        shown_cats = visible_cats[:4] if has_overflow else visible_cats[:5]
        if has_overflow and category_id and not any(str(c.get("id")) == str(category_id) for c in shown_cats):
            active_match = next((c for c in visible_cats[4:] if str(c.get("id")) == str(category_id)), None)
            if active_match and shown_cats:
                shown_cats = shown_cats[:3] + [active_match]

        for c in shown_cats:
            c_id = c.get("id")
            is_active_cat = str(category_id) == str(c_id)
            name = (c.get("name") or "").strip()
            icon = (c.get("icon") or "").strip()
            if is_active_cat:
                label = f"✅ {name}"
            else:
                label = f"{icon} {name}".strip() if icon and not name.startswith(icon) else name
            top_chips.append(InlineKeyboardButton(text=label[:18], callback_data=f"cat_{c_id}"))

        if has_overflow:
            more_label = "📂 More" if lang != "bn" else "📂 আরও"
            top_chips.append(InlineKeyboardButton(text=more_label, callback_data="catpage_1"))

        cat_rows = [top_chips[i:i + 3] for i in range(0, len(top_chips), 3)]
    if category_id == "uncategorized":
        prefix = "shop_p_uncat_"
    elif category_id:
        prefix = f"shop_p_{category_id}_"
    else:
        prefix = "shop_p_all_"

    for p in products:
        price_num = p["price"]
        reseller_price = p.get("reseller_price")
        if is_reseller and reseller_price is not None and float(reseller_price) > 0:
            price_num = float(reseller_price)

        price_formatted = format_dual_price(price_num, currency_symbol, usd_rate=usd_rate, show_usd=show_usd, lang=lang)

        clean_title, duration_label, warranty_label = product_display_labels(p)
        duration_label = _compact_duration(duration_label)
        icon, custom_id = _catalog_icon(p)
        if not icon and p.get("is_pinned"):
            icon = "🔥"
        display_title = f"{icon} {clean_title}".strip() if icon else clean_title

        if duration_label and duration_label.lower() not in {"instant", "none", "n/a", ""}:
            btn_text = f"{display_title} · {duration_label}"
        else:
            btn_text = display_title
        if warranty_label and warranty_label.lower() not in {"none", "n/a"}:
            btn_text += f" ({warranty_label})"
        btn_text += f" · {price_formatted}"

        if len(btn_text) > 64:
            price_part = f" · {price_formatted}"
            duration_part = (
                f" · {duration_label}"
                if duration_label and duration_label.lower() not in {"instant", "none", "n/a", ""}
                else ""
            )
            warranty_part = (
                f" ({warranty_label})"
                if warranty_label and warranty_label.lower() not in {"none", "n/a"}
                else ""
            )
            title_reserve = min(12, len(display_title)) + (1 if display_title else 0)
            metadata_limit = max(0, 64 - len(price_part) - title_reserve)
            warranty_limit = max(0, metadata_limit - len(duration_part))
            if len(warranty_part) > warranty_limit:
                warranty_part = (
                    f" · {warranty_label[:max(0, warranty_limit - 4)].rstrip()}…"
                    if warranty_limit >= 4
                    else ""
                )
            if len(duration_part) + len(warranty_part) > metadata_limit:
                duration_part = (
                    f" {duration_label[:max(0, metadata_limit - 2)].rstrip()}…"
                    if metadata_limit >= 3
                    else ""
                )
                warranty_part = ""
            suffix = f"{duration_part}{warranty_part}{price_part}"
            title_limit = max(0, 64 - len(suffix) - 1)
            if title_limit >= len(display_title):
                btn_text = f"{display_title}{suffix}"
            else:
                btn_text = f"{display_title[:title_limit].rstrip()}…{suffix}" if title_limit else suffix.strip()

        if category_id == "uncategorized":
            cat_key = "uncat"
        elif category_id:
            cat_key = str(category_id)
        else:
            cat_key = "all"

        btn_kwargs: dict[str, Any] = {
            "text": btn_text[:64],
            "callback_data": f"prod_p_{p['id']}_{page}_{cat_key}",
            "style": "success",
        }
        if custom_id:
            btn_kwargs["icon_custom_emoji_id"] = custom_id

        buttons.append([InlineKeyboardButton(**btn_kwargs)])

    btn_refresh = t("btn_refresh", lang) or "Refresh"
    btn_next = t("btn_next", lang) or "Next"
    btn_prev = t("btn_prev", lang) or "Prev"

    effective_back = (
        back_target
        if (back_target and back_target not in {"back_to_main", "none"})
        else None
    )
    if effective_back and effective_back.startswith("catval_menu_"):
        back_text = "⏱️ Filter" if lang != "bn" else "⏱️ ফিল্টার"
    else:
        back_text = "Back" if lang != "bn" else "ব্যাক"

    if total_pages > 1:
        if page == 1:
            nav_row = [
                InlineKeyboardButton(text=btn_refresh, callback_data=f"{prefix}1"),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                InlineKeyboardButton(text=btn_next, callback_data=f"{prefix}2"),
            ]
        elif page == total_pages:
            nav_row = [
                InlineKeyboardButton(text=btn_prev, callback_data=f"{prefix}{page - 1}"),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                InlineKeyboardButton(text=btn_refresh, callback_data=f"{prefix}{page}"),
            ]
        else:
            nav_row = [
                InlineKeyboardButton(text=btn_prev, callback_data=f"{prefix}{page - 1}"),
                InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"),
                InlineKeyboardButton(text=btn_next, callback_data=f"{prefix}{page + 1}"),
            ]
        buttons.append(nav_row)
        if effective_back:
            buttons.append([
                InlineKeyboardButton(text=back_text, callback_data=effective_back),
            ])
    else:
        # Single page: Refresh and Back
        if effective_back:
            buttons.append([
                InlineKeyboardButton(text=btn_refresh, callback_data=f"{prefix}1"),
                InlineKeyboardButton(text=back_text, callback_data=effective_back),
            ])
        else:
            buttons.append([
                InlineKeyboardButton(text=btn_refresh, callback_data=f"{prefix}1"),
            ])
    return InlineKeyboardMarkup(inline_keyboard=cat_rows + buttons)


def get_quantity_selector_keyboard(
    product_id: int,
    quantity: int,
    unit_price: float,
    max_stock: int,
    user_balance: float,
    currency_symbol: str = "$",
    is_manual: bool = False,
    is_upstream: bool = False,
    back_target: str = "open_shop",
    usd_rate: float | None = None,
    show_usd: bool = False,
    product_link: str = "",
    has_description: bool = False,
    lang: str = "en",
    product_icon_custom_emoji_id: str | None = None,
) -> InlineKeyboardMarkup:
    """
    Interactive Quantity Selector keyboard matching reference UI:
    [-] [Qty] [+]
    [⚡ Buy Now · Price] or [💳 Add $XX to Wallet]
    [📝 Description] [📋 Copy Link]
    [🔙 Back] [🏠 Main Menu]
    """
    total_price = round(unit_price * quantity, 2)
    price_formatted = format_dual_price(total_price, currency_symbol, usd_rate=usd_rate, show_usd=show_usd, lang=lang)
    buttons = []

    dec_qty = max(1, quantity - 1)
    upper_bound = max_stock if not is_manual and not is_upstream and max_stock > 0 else 999
    inc_qty = min(upper_bound, quantity + 1)

    # Interactive stepper [-]  [ Qty ]  [+] (shown whenever stock > 1 or quantity > 1)
    if (is_manual or is_upstream or max_stock > 1) or quantity > 1:
        row1 = [
            InlineKeyboardButton(
                text="➖",
                callback_data=f"qty_set_{product_id}_{dec_qty}",
            ),
            InlineKeyboardButton(
                text=f"{quantity}",
                callback_data=f"qty_custom_{product_id}",
            ),
            InlineKeyboardButton(
                text="➕",
                callback_data=f"qty_set_{product_id}_{inc_qty}",
            ),
        ]
        buttons.append(row1)
        buttons.append([
            InlineKeyboardButton(
                text="✏️ Set Custom Quantity",
                callback_data=f"qty_custom_{product_id}",
            )
        ])

    # Row 2: Instant 1-Click Buy / Add Shortfall to Wallet / Out of Stock
    if not is_manual and not is_upstream and max_stock <= 0:
        out_of_stock_text = "❌ Out of Stock"
        buttons.append([
            InlineKeyboardButton(text=out_of_stock_text, callback_data="noop", style="danger")
        ])
    elif user_balance >= total_price:
        buy_text = f"Buy · {price_formatted}" if quantity == 1 else f"Buy {quantity} · {price_formatted}"
        buttons.append([
            InlineKeyboardButton(
                text=buy_text[:64],
                callback_data=f"buy_qty_{product_id}_{quantity}_{uuid4().hex[:12]}_{round(unit_price * 100)}",
                style="success",
                icon_custom_emoji_id=(
                    product_icon_custom_emoji_id
                    if product_icon_custom_emoji_id
                    and product_icon_custom_emoji_id.strip().isdigit()
                    else None
                ),
            )
        ])
    else:
        short = round(total_price - user_balance, 2)
        short_formatted = format_dual_price(short, currency_symbol, usd_rate=usd_rate, show_usd=show_usd, lang=lang)
        add_text = f"💳 Add {short_formatted} to Balance"
        buttons.append([
            InlineKeyboardButton(
                text=add_text[:64],
                callback_data=f"open_deposit_prod_{product_id}",
                style="primary",
            )
        ])

    # Row 3: Description and shareable link
    extras = []
    if has_description:
        extras.append(
            InlineKeyboardButton(
                text="📖 Details",
                callback_data=f"prod_desc_{product_id}",
            )
        )
    if product_link:
        extras.append(
            InlineKeyboardButton(
                text="📋 Copy Link",
                copy_text=CopyTextButton(text=product_link[:256]),
            )
        )
    if extras:
        buttons.append(extras)

    # Row 4: Back & Main Menu
    # Row 4: Back to catalog / product list
    effective_back = back_target if back_target and back_target != "close_menu" else "open_categories"
    back_btn_text = "🔙 Back" if lang != "bn" else t("btn_back", lang)
    buttons.append([
        InlineKeyboardButton(text=back_btn_text, callback_data=effective_back),
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
    ⚡ Max     ✅ Confirm
    🔙 Back
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
                InlineKeyboardButton(text="⌫", callback_data=f"qpad_{product_id}_del"),
                InlineKeyboardButton(text="0", callback_data=f"qpad_{product_id}_0"),
                InlineKeyboardButton(text="🗑️ Clear", callback_data=f"qpad_{product_id}_clr", style="danger"),
            ],
            [
                InlineKeyboardButton(text="25", callback_data=f"qpad_{product_id}_set_25"),
                InlineKeyboardButton(text="50", callback_data=f"qpad_{product_id}_set_50"),
                InlineKeyboardButton(text="100", callback_data=f"qpad_{product_id}_set_100"),
            ],
            [
                InlineKeyboardButton(text="⚡ Max", callback_data=f"qpad_{product_id}_max"),
                InlineKeyboardButton(text="✅ Confirm", callback_data=f"qpad_{product_id}_confirm", style="success"),
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data=f"qpad_{product_id}_back"),
            ],
        ]
    )


def get_product_detail_keyboard(
    product_id: int,
    category_id: int,
    has_stock: bool,
    user_has_enough_balance: bool,
    price: float,
    currency_symbol: str = "$",
    usd_rate: float | None = None,
    show_usd: bool = False,
    product_icon_custom_emoji_id: str | None = None,
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
        product_icon_custom_emoji_id=product_icon_custom_emoji_id,
    )


def get_deposit_methods_keyboard(
    methods: List[Dict[str, Any]],
    instant_label: str | None = None,
    lang: str = "en",
    show_history: bool = True,
    back_target: str = "back_to_main",
) -> InlineKeyboardMarkup:
    """Inline keyboard for choosing a deposit method or opening wallet history."""
    buttons: List[List[InlineKeyboardButton]] = []

    # Featured instant payment gateway at the top
    if instant_label:
        inst_text = str(instant_label).strip()
        _, clean_inst = extract_emoji_and_name(inst_text)
        btn_label = clean_inst or strip_leading_emoji(inst_text).strip()
        if btn_label:
            if "zinipay" in btn_label.lower():
                display_label = "⚡ Instant Pay · ZiniPay"
            elif not btn_label.startswith("⚡"):
                display_label = f"⚡ {btn_label}"
            else:
                display_label = btn_label
            buttons.append([
                InlineKeyboardButton(
                    text=display_label,
                    callback_data="dep_instant",
                )
            ])

    # Payment methods grouped 2-per-row
    method_btns: List[InlineKeyboardButton] = []
    for m in methods:
        name = str(m.get("name") or "Method").strip()
        _, clean_name = extract_emoji_and_name(name)
        cleaned_name = clean_name or strip_leading_emoji(name).strip()
        method_btns.append(
            InlineKeyboardButton(
                text=cleaned_name,
                callback_data=f"dep_method_{m['id']}",
                icon_custom_emoji_id=(
                    str(m.get("custom_emoji_id")).strip()
                    if str(m.get("custom_emoji_id") or "").strip().isdigit()
                    else None
                ),
            )
        )

    for index in range(0, len(method_btns), 2):
        buttons.append(method_btns[index : index + 2])

    if show_history:
        history_text = "📜 Deposit History"
        buttons.append([
            InlineKeyboardButton(
                text=history_text,
                callback_data="open_deposits",
            )
        ])

    if back_target and back_target != "back_to_main":
        back_text = "🔙 Back"
        buttons.append([
            InlineKeyboardButton(
                text=back_text,
                callback_data=back_target,
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_deposit_quick_amount_keyboard(
    is_binance: bool = False,
    lang: str = "en",
    back_target: str = "dep_methods",
    show_change_trxid: bool = False,
) -> InlineKeyboardMarkup:
    """Quick amount chip buttons for deposit (Plan 1)."""
    if is_binance:
        chips = [
            [
                InlineKeyboardButton(text="1 USDT", callback_data="dep_amt_1"),
                InlineKeyboardButton(text="2 USDT", callback_data="dep_amt_2"),
            ],
            [
                InlineKeyboardButton(text="5 USDT", callback_data="dep_amt_5"),
                InlineKeyboardButton(text="10 USDT", callback_data="dep_amt_10"),
            ],
            [
                InlineKeyboardButton(text="15 USDT", callback_data="dep_amt_15"),
                InlineKeyboardButton(text="20 USDT", callback_data="dep_amt_20"),
            ],
            [
                InlineKeyboardButton(text="30 USDT", callback_data="dep_amt_30"),
                InlineKeyboardButton(text="50 USDT", callback_data="dep_amt_50"),
            ],
            [
                InlineKeyboardButton(text="75 USDT", callback_data="dep_amt_75"),
                InlineKeyboardButton(text="100 USDT", callback_data="dep_amt_100"),
            ],
        ]
    else:
        chips = [
            [
                InlineKeyboardButton(text="৳50", callback_data="dep_amt_50"),
                InlineKeyboardButton(text="৳100", callback_data="dep_amt_100"),
            ],
            [
                InlineKeyboardButton(text="৳150", callback_data="dep_amt_150"),
                InlineKeyboardButton(text="৳200", callback_data="dep_amt_200"),
            ],
            [
                InlineKeyboardButton(text="৳300", callback_data="dep_amt_300"),
                InlineKeyboardButton(text="৳500", callback_data="dep_amt_500"),
            ],
            [
                InlineKeyboardButton(text="৳750", callback_data="dep_amt_750"),
                InlineKeyboardButton(text="৳1000", callback_data="dep_amt_1000"),
            ],
            [
                InlineKeyboardButton(text="৳1500", callback_data="dep_amt_1500"),
                InlineKeyboardButton(text="৳2000", callback_data="dep_amt_2000"),
            ],
        ]
    if show_change_trxid:
        chips.append([InlineKeyboardButton(text="✏️ Change TrxID", callback_data="dep_change_trxid")])
    chips.append([InlineKeyboardButton(text="Back", callback_data=back_target)])
    return InlineKeyboardMarkup(inline_keyboard=chips)


def get_deposit_trxid_prompt_keyboard(
    lang: str = "en",
    *,
    has_amount: bool = True,
    back_target: str = "dep_methods",
) -> InlineKeyboardMarkup:
    """Action buttons shown during TrxID prompt."""
    buttons = []
    if has_amount:
        buttons.append(InlineKeyboardButton(text="Change Amount", callback_data="dep_change_amt"))
    buttons.append(InlineKeyboardButton(text="Cancel", callback_data=back_target))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def get_deposit_status_keyboard(
    dep_id: int,
    status: str = "pending",
    can_fix_trx: bool = False,
    support_username: str | None = None,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Action buttons on deposit status card."""
    buttons: List[List[InlineKeyboardButton]] = []
    st = (status or "").lower()

    if st in ("pending", "in_review", "processing", "verifying"):
        ref_text = "🔄 Refresh"
        buttons.append([InlineKeyboardButton(text=ref_text, callback_data=f"dep_refresh_{dep_id}")])
        if can_fix_trx and dep_id:
            fix_text = "✏️ Fix TrxID"
            buttons.append([InlineKeyboardButton(text=fix_text, callback_data=f"dep_fix_trx_{dep_id}")])
    elif st in ("approved", "completed"):
        # No inline navigation buttons (no back/shop buttons) so that the deposit success
        # receipt remains permanently as a standalone receipt in chat history without being overwritten.
        return InlineKeyboardMarkup(inline_keyboard=[])
    else:  # rejected, failed, cancelled
        sup_url = resolve_support_url(support_username)
        if sup_url:
            sup_text = "💬 Contact Support"
            buttons.append([InlineKeyboardButton(text=sup_text, url=sup_url)])
        wallet_text = "🔙 Back to Balance"
        buttons.append([InlineKeyboardButton(text=wallet_text, callback_data="open_deposit")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_manual_deposit_invoice_keyboard(
    account_info: str,
    lang: str = "en",
    method_id: int | None = None,
    is_binance: bool = False,
) -> InlineKeyboardMarkup:
    """Actions shown under manual payment instructions."""
    destination = str(account_info or "").strip()
    buttons = []
    if destination.startswith("https://"):
        buttons.append([InlineKeyboardButton(text="Open Payment", url=destination)])
    paid_text = "✅ Payment Done"
    back_text = "🔙 Back"
    buttons.append([
        InlineKeyboardButton(text=paid_text, callback_data=f"dep_paid_{method_id}" if method_id else "dep_paid", style="success"),
    ])
    buttons.append([
        InlineKeyboardButton(text=back_text, callback_data="dep_methods"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_deposit_input_inline_keyboard(
    account_info: str = "",
    method_name: str = "",
    is_binance: bool = False,
    *,
    change_amount: bool = False,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Inline keyboard for amount and TrxID entry matching task-bot deposit_input_inline_keyboard."""
    destination = str(account_info or "").strip()
    buttons = []
    if destination and not destination.startswith("https://"):
        is_bin = is_binance or "binance" in method_name.lower()
        label = "📋 Copy Binance ID" if is_bin else "📋 Copy payment details"
        buttons.append([
            InlineKeyboardButton(
                text=label,
                copy_text=CopyTextButton(text=destination[:256]),
            )
        ])
    if change_amount:
        buttons.append([InlineKeyboardButton(text="✏️ Change amount", callback_data="dep_paid")])
    buttons.append([InlineKeyboardButton(text="🔙 Payment details", callback_data="dep_invoice")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard(back_target: str | None = "open_deposit", lang: str = "en") -> InlineKeyboardMarkup:
    effective_back = back_target or "back_to_main"
    back_text = "🔙 Back"
    buttons = []
    if effective_back:
        buttons.append([
            InlineKeyboardButton(
                text=back_text,
                callback_data=effective_back,
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_reply_keyboard(lang: str = "en") -> ReplyKeyboardMarkup:
    """Pure Reply Keyboard with only [ 🔙 Back ] button during user input."""
    back_label = "🔙 Back"
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=back_label)]],
        resize_keyboard=True,
    )


def get_deposit_amount_keyboard(
    account_info: str = "",
    method_id: int | None = None,
    method_name: str = "",
    is_binance: bool = False,
    lang: str = "en",
    show_back: bool = False,
) -> InlineKeyboardMarkup:
    """Buttons on the Enter Amount screen."""
    return get_deposit_input_inline_keyboard(
        account_info=account_info,
        method_name=method_name,
        is_binance=is_binance,
        change_amount=False,
        lang=lang,
    )


def get_deposit_txid_keyboard(
    account_info: str = "",
    method_id: int | None = None,
    method_name: str = "",
    is_binance: bool = False,
    lang: str = "en",
    show_change_and_back: bool = False,
) -> InlineKeyboardMarkup:
    """Buttons on the Enter TrxID screen: copy number/UID, change amount, back to payment details."""
    return get_deposit_input_inline_keyboard(
        account_info=account_info,
        method_name=method_name,
        is_binance=is_binance,
        change_amount=show_change_and_back,
        lang=lang,
    )


def get_deposit_confirm_keyboard(lang: str = "en", method_id: int | None = None) -> InlineKeyboardMarkup:
    """Buttons on the Confirm Deposit screen matching task-bot."""
    confirm_text = "✅ Confirm"
    cancel_text = "❌ Cancel"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=confirm_text, callback_data="d_conf_yes"),
                InlineKeyboardButton(text=cancel_text, callback_data="d_conf_cancel"),
            ],
        ]
    )
