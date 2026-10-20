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

from app.bot.formatting import format_dual_price
from app.core.i18n import t

ADMIN_PANEL_TEXT = "Admin Panel"
_TRAILING_VALIDITY = re.compile(
    r"(?:[\s|·\-–—(]+)(\d+\s*(?:days?|weeks?|months?|years?|hours?))(?:\s+validity)?\)?$",
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
    """Keep the four primary actions aligned across keyboard types."""
    items = [
        ("🛍", "Products", "প্রোডাক্টস", "open_categories"),
        ("💰", "Wallet", "ওয়ালেট", "open_wallet"),
        ("📦", "Orders", "অর্ডারস", "open_orders"),
        ("✨", "More", "আরও", "open_more"),
    ]
    return [
        (f"{icon} {bn if lang == 'bn' else en}" if show_icons else (bn if lang == "bn" else en), callback)
        for icon, en, bn, callback in items
    ]


def get_main_inline_keyboard(
    pinned_categories: List[Dict[str, Any]] | None = None,
    featured_products: List[Dict[str, Any]] | None = None,
    has_unpinned: bool = False,
    is_reseller: bool = False,
    is_admin: bool = False,
    lang: str = "en",
    currency_symbol: str = "৳",
    usd_rate: float | None = None,
    show_usd: bool = False,
) -> InlineKeyboardMarkup:
    """Four primary customer actions; profile and operator tools live under More."""
    customer_buttons = [
        InlineKeyboardButton(text=label, callback_data=callback)
        for label, callback in _customer_menu(lang)
    ]
    rows = [customer_buttons[i:i + 2] for i in range(0, len(customer_buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_more_inline_keyboard(
    lang: str = "en",
    is_reseller: bool = False,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    """Secondary actions intentionally kept off the four-button home menu."""
    if lang == "bn":
        profile_label, referral_label = "👤 প্রোফাইল", "🎁 রেফারেল"
        help_label, language_label = "💬 সাহায্য", "🌐 ভাষা"
        reseller_label, admin_label = "💼 রিসেলার প্যানেল", "🛡 অ্যাডমিন প্যানেল"
        back_label = "🏠 মূল মেনু"
    else:
        profile_label, referral_label = "👤 Profile", "🎁 Referral"
        help_label, language_label = "💬 Help", "🌐 Language"
        reseller_label, admin_label = "💼 Reseller Panel", "🛡 Admin Panel"
        back_label = "🏠 Main menu"

    rows = [
        [
            InlineKeyboardButton(text=profile_label, callback_data="open_account"),
            InlineKeyboardButton(text=referral_label, callback_data="open_referral"),
        ],
        [
            InlineKeyboardButton(text=help_label, callback_data="open_help"),
            InlineKeyboardButton(text=language_label, callback_data="open_language_menu"),
        ],
    ]
    if is_reseller:
        rows.append([InlineKeyboardButton(text=reseller_label, callback_data="open_reseller_hub")])
    if is_admin:
        rows.append([InlineKeyboardButton(text=admin_label, callback_data="adm_dashboard")])
    rows.append([InlineKeyboardButton(text=back_label, callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_persistent_reply_keyboard(
    pinned_categories: List[Dict[str, Any]] | None = None,
    has_unpinned: bool = False,
    is_reseller: bool = False,
    is_admin: bool = False,
    lang: str = "en",
    show_icons: bool = True,
) -> ReplyKeyboardMarkup:
    """Four primary customer actions; operator tools are available under More."""
    customer_buttons = [KeyboardButton(text=label) for label, _ in _customer_menu(lang, show_icons)]
    rows = [customer_buttons[i:i + 2] for i in range(0, len(customer_buttons), 2)]
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
    """Pure Reply Keyboard displaying all active categories in a 2-column grid."""
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

    for i in range(0, len(cat_buttons), 2):
        rows.append(cat_buttons[i : i + 2])

    back_label = "Back" if lang != "bn" else "ব্যাক"

    rows.append([
        KeyboardButton(text=back_label),
    ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=False)


def get_products_reply_keyboard(
    products: List[Dict[str, Any]],
    currency_symbol: str = "৳",
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
        add_text = "Add to Wallet" if lang != "bn" else "অ্যাড ব্যালেন্স"
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


def get_account_reply_keyboard(
    is_reseller: bool = False,
    lang: str = "en",
    show_icons: bool = False,
) -> ReplyKeyboardMarkup:
    """Pure Reply Keyboard for Account screen (Clean 2x2 grid without unnecessary icons)."""
    if lang != "bn":
        orders_label = "Orders"
        refer_label = "Referral"
        prices_label = "Prices"
        back_label = "Back"
    else:
        orders_label = "অর্ডার"
        refer_label = "রেফারেল"
        prices_label = "প্রাইস"
        back_label = "ব্যাক"

    rows = [
        [
            KeyboardButton(text=orders_label),
            KeyboardButton(text=refer_label),
        ],
        [
            KeyboardButton(text=prices_label),
            KeyboardButton(text=back_label),
        ],
    ]
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

    for i in range(0, len(cat_buttons), 2):
        buttons.append(cat_buttons[i : i + 2])

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


def get_gate_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
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

    buttons.append([
        InlineKeyboardButton(
            text="✅ I've Joined",
            callback_data="gate_verify",
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


def get_account_keyboard(
    lang: str = "en",
    is_admin: bool = False,
    ref_link: str | None = None,
    is_reseller: bool = False,
    order_count: int = 0,
    include_referral: bool = False,
    share_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Show profile actions directly, without duplicating the main menu.

    Legacy arguments remain accepted so older callers cannot restore removed
    Orders/Referral shortcuts or break when opening the profile.
    """
    if lang != "bn":
        reseller_label = "Reseller"
        api_label = "API"
        notifications_label = "Notifications"
        back_label = "Back"
    else:
        reseller_label = "রিসেলার"
        api_label = "এপিআই"
        notifications_label = "নোটিফিকেশন"
        back_label = "ব্যাক"
    language_label = t("btn_change_language", lang)

    rows = [
        [InlineKeyboardButton(text=language_label, callback_data="open_language_menu")],
        [
            InlineKeyboardButton(text=notifications_label, callback_data="open_notifications_hub"),
        ],
        [
            InlineKeyboardButton(text=api_label, callback_data="open_api_hub"),
            InlineKeyboardButton(
                text=reseller_label,
                callback_data="open_reseller_hub" if is_reseller else "open_reseller",
            ),
        ],
        [InlineKeyboardButton(text=back_label, callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_notification_settings_keyboard(prefs: dict[str, bool], lang: str = "en") -> InlineKeyboardMarkup:
    """Interactive toggle keyboard for customer notification preferences."""
    news_on = prefs.get("notify_news", True)

    if lang != "bn":
        news_btn = f"News & Offers: {'On' if news_on else 'Off'}"
        back_btn = "Back"
    else:
        news_btn = f"অফার ও নোটিশ: {'চালু' if news_on else 'বন্ধ'}"
        back_btn = "ব্যাক"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=news_btn, callback_data="notif_toggle_notify_news")],
            [InlineKeyboardButton(text=back_btn, callback_data="open_account")],
        ]
    )



def get_language_selection_keyboard(current_lang: str = "en", back_target: str | None = "open_account") -> InlineKeyboardMarkup:
    """Offer both supported languages and mark the user's current choice."""
    active_lang = current_lang if current_lang in {"en", "bn"} else "en"
    en_label = "🇬🇧 English ✓" if active_lang == "en" else "🇬🇧 English"
    bn_label = "🇧🇩 বাংলা ✓" if active_lang == "bn" else "🇧🇩 বাংলা"
    rows = [
        [InlineKeyboardButton(text=en_label, callback_data="set_lang_en")],
        [InlineKeyboardButton(text=bn_label, callback_data="set_lang_bn")],
    ]

    if back_target:
        back_text = t("btn_back", active_lang)
        rows.append([InlineKeyboardButton(text=back_text, callback_data=back_target)])
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

    if lang == "bn":
        faq_buttons = [
            ("faq_buy", "কীভাবে প্রোডাক্ট কিনবেন?"),
            ("faq_deposit", "কীভাবে ব্যালেন্স যোগ করবেন?"),
            ("faq_delivery", "ডেলিভারি কীভাবে কাজ করে?"),
            ("faq_referral", "রেফারেল থেকে কীভাবে আয় করবেন?"),
        ]
        tech_label = "টেকনিক্যাল সাপোর্ট"
        chan_label = "আপডেট চ্যানেল"
    else:
        faq_buttons = [
            ("faq_buy", "Buying"),
            ("faq_deposit", "Payments"),
            ("faq_delivery", "Delivery"),
            ("faq_referral", "Referrals"),
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
    currency_symbol: str = "৳",
    category_id: int | str | None = None,
    back_target: str = "back_to_main",
    is_reseller: bool = False,
    usd_rate: float | None = None,
    show_usd: bool = False,
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """
    Product rows show the clean name, validity, optional warranty and price.
    Bottom rows provide refresh, pagination and the relevant back navigation.
    """
    buttons = []
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
        }
        if custom_id:
            btn_kwargs["icon_custom_emoji_id"] = custom_id

        buttons.append([InlineKeyboardButton(**btn_kwargs)])

    btn_refresh = t("btn_refresh", lang) or "Refresh"
    btn_next = t("btn_next", lang) or "Next"
    btn_prev = t("btn_prev", lang) or "Prev"

    effective_back = back_target or "back_to_main"
    if effective_back.startswith("catval_menu_"):
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
    show_usd: bool = False,
    product_link: str = "",
    has_description: bool = False,
    lang: str = "en",
    product_icon_custom_emoji_id: str | None = None,
) -> InlineKeyboardMarkup:
    """
    Interactive Quantity Selector keyboard matching reference UI:
    [-] [Qty] [+]
    [⚡ Buy Now · Price] or [💳 Add ৳XX to Wallet]
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
                callback_data="noop",
            ),
            InlineKeyboardButton(
                text="➕",
                callback_data=f"qty_set_{product_id}_{inc_qty}",
            ),
        ]
        buttons.append(row1)

    # Row 2: Instant 1-Click Buy / Add Shortfall to Wallet / Out of Stock
    if not is_manual and not is_upstream and max_stock <= 0:
        out_of_stock_text = "❌ Out of Stock" if lang != "bn" else "❌ স্টক শেষ"
        buttons.append([
            InlineKeyboardButton(text=out_of_stock_text, callback_data="noop", style="danger")
        ])
    elif user_balance >= total_price:
        if lang == "bn":
            buy_text = f"⚡ কিনুন · {price_formatted}" if quantity == 1 else f"⚡ {quantity}টি কিনুন · {price_formatted}"
        else:
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
        add_text = f"💳 Add {short_formatted} to Wallet" if lang != "bn" else f"💳 {short_formatted} ওয়ালেটে যোগ করুন"
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
        desc_btn_text = "Details" if lang != "bn" else "📝 বিবরণ"
        extras.append(
            InlineKeyboardButton(
                text=desc_btn_text,
                callback_data=f"prod_desc_{product_id}",
            )
        )
    if product_link:
        copy_btn_text = "📋 Copy Link" if lang != "bn" else "📋 লিংক কপি"
        extras.append(
            InlineKeyboardButton(
                text=copy_btn_text,
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
    currency_symbol: str = "৳",
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

    # Payment methods first, followed by the hosted instant option.
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

    for i in range(0, len(method_btns), 2):
        buttons.append(method_btns[i : i + 2])

    if instant_label:
        inst_text = str(instant_label).strip()
        _, clean_inst = extract_emoji_and_name(inst_text)
        btn_label = clean_inst or strip_leading_emoji(inst_text).strip()
        if btn_label:
            buttons.append([
                InlineKeyboardButton(
                    text=btn_label,
                    callback_data="dep_instant",
                )
            ])

    if show_history:
        history_text = "History" if lang != "bn" else "📊 ডিপোজিট হিস্ট্রি"
        buttons.append([
            InlineKeyboardButton(
                text=history_text,
                callback_data="open_deposits",
            )
        ])

    if back_target and back_target != "back_to_main":
        back_text = "🔙 Back" if lang != "bn" else "🔙 ব্যাক"
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
) -> InlineKeyboardMarkup:
    """Quick amount chip buttons for deposit (Plan 1)."""
    if is_binance:
        chips = [
            [
                InlineKeyboardButton(text="1 USDT", callback_data="dep_amt_1"),
                InlineKeyboardButton(text="5 USDT", callback_data="dep_amt_5"),
                InlineKeyboardButton(text="10 USDT", callback_data="dep_amt_10"),
            ],
            [
                InlineKeyboardButton(text="20 USDT", callback_data="dep_amt_20"),
                InlineKeyboardButton(text="50 USDT", callback_data="dep_amt_50"),
            ],
        ]
    else:
        chips = [
            [
                InlineKeyboardButton(text="৳100", callback_data="dep_amt_100"),
                InlineKeyboardButton(text="৳200", callback_data="dep_amt_200"),
                InlineKeyboardButton(text="৳500", callback_data="dep_amt_500"),
            ],
            [
                InlineKeyboardButton(text="৳1000", callback_data="dep_amt_1000"),
                InlineKeyboardButton(text="৳2000", callback_data="dep_amt_2000"),
            ],
        ]
    back_label = "Back" if lang != "bn" else "ব্যাক"
    chips.append([InlineKeyboardButton(text=back_label, callback_data=back_target)])
    return InlineKeyboardMarkup(inline_keyboard=chips)


def get_deposit_trxid_prompt_keyboard(
    lang: str = "en",
) -> InlineKeyboardMarkup:
    """Action buttons shown during TrxID prompt (Change amount, Cancel)."""
    change_text = "Change Amount" if lang != "bn" else "অ্যামাউন্ট পরিবর্তন"
    cancel_text = "Cancel" if lang != "bn" else "বাতিল"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=change_text, callback_data="dep_change_amt"),
                InlineKeyboardButton(text=cancel_text, callback_data="dep_methods"),
            ],
        ]
    )


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
        ref_text = "🔄 Refresh" if lang != "bn" else "🔄 রিফ্রেশ"
        buttons.append([InlineKeyboardButton(text=ref_text, callback_data=f"dep_refresh_{dep_id}")])
        if can_fix_trx and dep_id:
            fix_text = "✏️ Fix TrxID" if lang != "bn" else "✏️ TrxID পরিবর্তন"
            buttons.append([InlineKeyboardButton(text=fix_text, callback_data=f"dep_fix_trx_{dep_id}")])
        wallet_text = "🔙 Back to Wallet" if lang != "bn" else "🔙 ওয়ালেট"
        buttons.append([InlineKeyboardButton(text=wallet_text, callback_data="open_deposit")])
    elif st in ("approved", "completed"):
        shop_text = "🛍️ All Products" if lang != "bn" else "🛍️ সকল প্রোডাক্ট"
        wallet_text = "🔙 Back to Wallet" if lang != "bn" else "🔙 ওয়ালেট"
        buttons.append([InlineKeyboardButton(text=shop_text, callback_data="open_shop")])
        buttons.append([InlineKeyboardButton(text=wallet_text, callback_data="open_deposit")])
    else:  # rejected, failed, cancelled
        if support_username:
            clean_sup = support_username.lstrip("@")
            sup_text = "💬 Support" if lang != "bn" else "💬 সাপোর্ট"
            buttons.append([InlineKeyboardButton(text=sup_text, url=f"https://t.me/{clean_sup}")])
        wallet_text = "🔙 Back to Wallet" if lang != "bn" else "🔙 ওয়ালেট"
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
        pay_text = "Open Payment" if lang != "bn" else "🌐 পেমেন্ট পেজ খুলুন"
        buttons.append([InlineKeyboardButton(text=pay_text, url=destination)])
    elif destination:
        copy_label = "Copy ID" if is_binance else "Copy Number"
        buttons.append([InlineKeyboardButton(
            text=copy_label if lang != "bn" else "নম্বর কপি",
            copy_text=CopyTextButton(text=destination[:256]),
        )])
    paid_text = "Payment Done" if lang != "bn" else "পেমেন্ট করেছি"
    back_text = "Back" if lang != "bn" else "ফিরে যান"
    buttons.append([
        InlineKeyboardButton(text=paid_text, callback_data=f"dep_paid_{method_id}" if method_id else "dep_paid"),
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
        if lang != "bn":
            label = "📋 Copy Binance ID" if is_bin else "📋 Copy payment details"
        else:
            label = "📋 Binance ID কপি করুন" if is_bin else "📋 পেমেন্ট নম্বর কপি করুন"
        buttons.append([
            InlineKeyboardButton(
                text=label,
                copy_text=CopyTextButton(text=destination[:256]),
            )
        ])
    if change_amount:
        ch_text = "✏️ Change amount" if lang != "bn" else "✏️ অ্যামাউন্ট পরিবর্তন"
        buttons.append([InlineKeyboardButton(text=ch_text, callback_data="dep_paid")])
    back_text = "🔙 Payment details" if lang != "bn" else "🔙 পেমেন্ট ডিটেইলস"
    buttons.append([InlineKeyboardButton(text=back_text, callback_data="dep_invoice")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard(back_target: str | None = "open_deposit", lang: str = "en") -> InlineKeyboardMarkup:
    effective_back = back_target or "back_to_main"
    back_text = "🔙 Back" if lang != "bn" else "🔙 ব্যাক"
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
    back_label = "🔙 Back" if lang != "bn" else "🔙 ব্যাক"
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
    confirm_text = "✅ Confirm" if lang != "bn" else "✅ কনফার্ম"
    cancel_text = "❌ Cancel" if lang != "bn" else "❌ বাতিল"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=confirm_text, callback_data="d_conf_yes"),
                InlineKeyboardButton(text=cancel_text, callback_data="d_conf_cancel"),
            ],
        ]
    )
