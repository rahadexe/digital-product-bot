from __future__ import annotations

import math
import re
from contextlib import suppress
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.formatting import callback_int, format_dual_price, respond
from app.bot.handlers.navigation import is_navigation, navigate
from app.bot.icons import (
    ICON_BALANCE,
    ICON_CART,
    ICON_CHECK,
    ICON_CROSS,
    ICON_DEPOSIT,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_SHOP,
    ICON_STATS,
    ICON_TIMER,
    ICON_VIP,
    ICON_WARNING,
    Icons,
    tg_icon,
)
from app.bot.keyboards import (
    get_categories_keyboard,
    get_custom_quantity_keypad,
    get_products_keyboard,
    get_quantity_selector_keyboard,
    get_validity_selector_keyboard,
)
from app.services import Services

router = Router(name="shop_router")

PAGE_SIZE = 10


class ShopQuantityStates(StatesGroup):
    waiting_for_quantity = State()


class CategoryTextFilter(BaseFilter):
    """Dynamically matches any active category name from the database, whether pinned or unpinned."""

    async def __call__(self, message: Message, services: Services) -> bool | dict[str, Any]:
        text = (message.text or "").strip()
        if not text or text.startswith("/"):
            return False

        # Exclude reserved system button titles
        ignored = {
            "add balance", "refer & earn", "my profile", "support", "apply as a reseller",
            "other products", "other product", "others", "premium products", "all products",
            "cancel", "shop", "products", "deposit", "account", "orders", "guide", "channel",
            "updates", "পণ্য কিনুন", "ডিপোজিট করুন", "কাস্টমার সাপোর্ট",
        }
        if text.casefold() in ignored:
            return False

        categories = await services.catalog.categories(active_only=True)
        # 1. Exact match
        for c in categories:
            if text.casefold() == c["name"].strip().casefold():
                return {"category": c}

        # 2. Match without leading emojis
        clean = text
        for em in ["🛡️", "🛡", "🌐", "✉️", "📦", "💎", "⚡", "📱", "🚀", "🤖", "🧠", "🎨", "💻", "✨", "🍿", "🎵", "📺", "⭐", "🎬", "❌"]:
            if clean.startswith(em):
                clean = clean[len(em):].strip()
                break

        for c in categories:
            c_name = c["name"].strip()
            if clean.casefold() == c_name.casefold():
                return {"category": c}
            if clean.casefold().startswith("buy ") and clean[4:].strip().casefold() == c_name.casefold():
                return {"category": c}
            if c_name.casefold().startswith("buy ") and c_name[4:].strip().casefold() == clean.casefold():
                return {"category": c}

        return False


async def show_category_or_validity(
    event: Message | CallbackQuery,
    state: FSMContext,
    services: Services,
    category: dict[str, Any],
    back_target: str = "back_to_main",
):
    """
    Renders validity selection if category has has_validity_filter enabled.
    Otherwise directly shows the product list.
    """
    cat_id = category["id"]
    if category.get("has_validity_filter") == 1:
        validities = await services.catalog.category_validities(cat_id)
        if validities:
            cat_emoji_id = category.get("custom_emoji_id")
            cat_icon = category.get("icon") or "📁"
            if cat_emoji_id and str(cat_emoji_id).strip().isdigit():
                icon_display = f"{tg_icon(str(cat_emoji_id).strip(), cat_icon)} "
            else:
                icon_display = f"{cat_icon} "

            kb = get_validity_selector_keyboard(
                category_id=cat_id,
                validities=validities,
                show_all_option=True,
                back_target=back_target,
            )
            title = f"{icon_display}<b>Select Validity:</b>"
            await respond(event, title, kb)
            return

    await show_products_list(
        event,
        state,
        services,
        category_id=cat_id,
        back_target=back_target,
    )


@router.message(CategoryTextFilter())
async def handle_category_by_text(message: Message, state: FSMContext, services: Services, category: dict[str, Any]):
    """Dynamic handler for any category selected via reply keyboard button."""
    await state.clear()
    await show_category_or_validity(
        message,
        state,
        services,
        category=category,
        back_target="back_to_main",
    )


@router.callback_query(F.data.in_({"open_cat_vpn", "open_cat_proxy", "open_cat_mailbox"}))
async def handle_legacy_cat_callbacks(query: CallbackQuery, state: FSMContext, services: Services):
    """Graceful fallback for legacy callback buttons."""
    await state.clear()
    categories = await services.catalog.categories(active_only=True)
    slug = query.data.replace("open_cat_", "").lower()
    cat = next((c for c in categories if slug in c["name"].lower()), None)
    cat = cat or (categories[0] if categories else None)
    if cat:
        await show_category_or_validity(query, state, services, category=cat, back_target="back_to_main")


@router.message(F.text.in_({"Other Products", "other products", "Other Product", "other product", "👑 Other Products", "💎 Other Products", "Others", "others", "Premium Products", "premium products", "👑 Premium Products", "আদার প্রোডাক্টস"}))
@router.callback_query(F.data.in_({"open_other_products", "open_premium_products", "open_categories"}))
async def show_other_products_hub(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Dynamic hub for unpinned categories."""
    await state.clear()
    unpinned = await services.catalog.unpinned_categories(active_only=True)
    if not unpinned:
        all_cats = await services.catalog.categories(active_only=True)
        pinned_ids = {c["id"] for c in await services.catalog.pinned_categories(active_only=True)}
        unpinned = [c for c in all_cats if c["id"] not in pinned_ids] or all_cats
    kb = get_categories_keyboard(unpinned, show_all_option=True)
    await respond(
        event,
        f"{ICON_VIP} <b>Other Products:</b>",
        kb,
    )


@router.callback_query(F.data.startswith("catpage_"))
async def paginate_categories(query: CallbackQuery, state: FSMContext, services: Services):
    """Handle pagination for category list."""
    try:
        page = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        page = 1

    unpinned = await services.catalog.unpinned_categories(active_only=True)
    if not unpinned:
        all_cats = await services.catalog.categories(active_only=True)
        pinned_ids = {c["id"] for c in await services.catalog.pinned_categories(active_only=True)}
        unpinned = [c for c in all_cats if c["id"] not in pinned_ids] or all_cats

    kb = get_categories_keyboard(unpinned, show_all_option=True, page=page)
    text = f"{ICON_VIP} <b>Other Products:</b>"
    try:
        if query.message:
            await query.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await query.answer()



def is_redundant_description(title: str, description: str) -> bool:
    if not description or not description.strip():
        return True
    t = re.sub(r"[^a-zA-Z0-9]", "", title).lower()
    d = re.sub(r"[^a-zA-Z0-9]", "", description).lower()
    if not d or t == d:
        return True
    t_no_vpn = t.replace("vpn", "")
    d_no_vpn = d.replace("vpn", "")
    if t_no_vpn == d_no_vpn or t_no_vpn in d_no_vpn or d_no_vpn in t_no_vpn:
        if abs(len(d) - len(t)) < 8:
            return True
    return False


async def product_view(
    services: Services,
    product: dict[str, Any],
    tg_user_id: int,
    quantity: int = 1,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await services.users.get(tg_user_id)
    balance = user["balance"] if user else 0.0
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    stock = product.get("stock", 0)
    title = escape(product["title"])
    duration = escape(product.get("duration_label") or "")

    is_manual = product.get("delivery_type") == "manual"
    if is_manual:
        stock_text = f"<b>Available (Manual Delivery) {ICON_TIMER}</b>"
    elif stock > 0:
        stock_text = f"<b>{stock}</b> Available"
    else:
        stock_text = f"<b>Out of Stock {ICON_CROSS}</b>"

    cat_id = product.get("category_id")
    cat = await services.catalog.category(cat_id) if cat_id else None
    category_name = cat["name"] if cat else "Uncategorized"
    cat_emoji_id = cat.get("custom_emoji_id") if cat else None
    cat_icon = cat.get("icon") or "📁" if cat else "📝"
    if not cat:
        cat_icon_display = f"{ICON_NOTE} "
    elif cat_emoji_id and str(cat_emoji_id).strip().isdigit():
        cat_icon_display = tg_icon(str(cat_emoji_id).strip(), cat_icon)
    else:
        cat_icon_display = cat_icon

    custom_emoji_id = product.get("custom_emoji_id")
    clean_title = title
    if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
        for em in ["🌐", "🛡️", "🛡", "⚡", "📱", "🚀", "🤖", "🧠", "🎨", "💻", "✨", "🍿", "🎵", "📺", "⭐", "🎬", "❌", "💎", "📦"]:
            if clean_title.startswith(em):
                clean_title = clean_title[len(em):].strip()
                break
        prod_icon_display = tg_icon(str(custom_emoji_id).strip(), product.get("icon") or "📦")
    else:
        prod_icon_display = product.get("icon") or "📦"

    if cat_emoji_id and custom_emoji_id and str(cat_emoji_id).strip() == str(custom_emoji_id).strip():
        prod_icon_display = "📦"

    is_reseller = (user.get("rank") or "").strip().lower() == "reseller" if user else False
    reseller_price = product.get("reseller_price")
    has_reseller_rate = is_reseller and reseller_price is not None and float(reseller_price) > 0

    if has_reseller_rate:
        unit_price = float(reseller_price)
    else:
        unit_price = float(product["price"])
    total_price = round(unit_price * quantity, 2)

    unit_price_str = format_dual_price(unit_price, symbol, usd_rate=usd_rate, show_usd=show_usd)
    total_price_str = format_dual_price(total_price, symbol, usd_rate=usd_rate, show_usd=show_usd)
    balance_str = format_dual_price(balance, symbol, usd_rate=usd_rate, show_usd=show_usd)

    if has_reseller_rate:
        reg_price = float(product["price"])
        reg_price_str = format_dual_price(reg_price, symbol, usd_rate=usd_rate, show_usd=show_usd)
        price_rate_line = f"{ICON_MONEY} <b>Price Rate:</b> <code>{unit_price_str}</code> (🔥 <i>Reseller Price</i> · <s>{reg_price_str}</s>)\n"
    else:
        price_rate_line = f"{ICON_MONEY} <b>Price Rate:</b> <code>{unit_price_str}</code>\n"

    text = (
        f"{ICON_BALANCE} <b>Your Balance:</b> <code>{balance_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{cat_icon_display} <b>Category:</b> {escape(category_name)}\n"
        f"{prod_icon_display} <b>Package:</b> <b>{clean_title}</b>\n"
        f"{price_rate_line}"
        f"{ICON_STATS} <b>Available Stock:</b> {stock_text}\n"
    )
    if duration and duration.lower() not in {"instant", "none", "n/a", ""}:
        text += f"{ICON_TIMER} <b>Validity:</b> {duration}\n"

    # The description lives behind its own button rather than in the card, so a
    # long one does not push the price and the quantity controls off the screen.
    desc = (product.get("description") or "").strip()
    has_description = bool(
        desc
        and desc.lower() not in {"n/a", "none", "no description", "null"}
        and not is_redundant_description(product["title"], desc)
    )

    text += (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ICON_CART} <b>Quantity:</b> <code>{quantity}</code>\n"
        f"{ICON_DEPOSIT} <b>Total Price:</b> <code>{total_price_str}</code>"
    )

    back_target = f"cat_{cat_id}" if cat_id else "shop_uncat"

    bot_username = await services.notifier.bot_username()
    product_link = f"https://t.me/{bot_username}?start=prod_{product['id']}" if bot_username else ""

    keyboard = get_quantity_selector_keyboard(
        product_id=product["id"],
        quantity=quantity,
        unit_price=unit_price,
        max_stock=stock,
        user_balance=balance,
        currency_symbol=symbol,
        is_manual=is_manual,
        back_target=back_target,
        usd_rate=usd_rate,
        show_usd=show_usd,
        product_link=product_link,
        has_description=has_description,
    )
    return text, keyboard


@router.message(Command("products"))
@router.message(Command("shop"))
@router.message(Command("buy"))
@router.message(F.text == "🛍️ Products")
@router.message(F.text == "💎 Other Products")
@router.message(F.text == "🛒 Products")
@router.message(F.text == "🛍️ Buy Products")
@router.message(F.text == "🛒 Buy Products")
@router.message(F.text == "🛍️ Shop")
@router.message(F.text == "🛒 Shop")
@router.message(F.text == "🔥 Shop 🔥")
@router.message(F.text.casefold() == "products")
@router.message(F.text.casefold() == "shop")
@router.message(F.text == "পণ্য কিনুন")
@router.callback_query(F.data == "open_shop")
@router.callback_query(F.data == "open_categories")
async def show_shop_entry(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """
    Shop entry point.
    If unpinned categories exist, displays the Category Selection Menu.
    If no unpinned categories exist, directly displays the product catalog list.
    """
    await state.clear()
    paused_msg = await services.settings.paused_message()
    if paused_msg:
        await respond(event, f"{ICON_WARNING} <b>Shop Temporarily Closed</b>\n\n{escape(paused_msg)}")
        return

    unpinned = await services.catalog.unpinned_categories(active_only=True)
    if unpinned:
        keyboard = get_categories_keyboard(unpinned, show_all_option=True)
        await respond(
            event,
            f"{ICON_VIP} <b>Other Products:</b>",
            keyboard,
        )
        return

    await show_products_list(event, state, services, category_id=None)


@router.callback_query(F.data == "shop_all")
async def show_all_products(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    await show_products_list(query, state, services, category_id=None, back_target="open_categories")


@router.callback_query(F.data.in_({"shop_uncat", "shop_uncategorized"}))
@router.message(F.text.in_({"Uncategorized", "uncategorized", "আনক্যাটাগরাইজড"}))
async def show_uncat_products(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    await show_products_list(event, state, services, category_id="uncategorized", back_target="open_categories")


@router.callback_query(F.data.startswith("cat_"))
async def show_category_products(query: CallbackQuery, state: FSMContext, services: Services):
    """Show products or validity selector for a specific selected category."""
    await state.clear()
    cat_id = callback_int(query.data, "cat_")
    if cat_id is None:
        return
    cat = await services.catalog.category(cat_id)
    if not cat:
        return
    is_other = not cat.get("is_pinned")
    back_target = "open_categories" if is_other else "back_to_main"
    await show_category_or_validity(query, state, services, category=cat, back_target=back_target)


@router.callback_query(F.data.startswith("catval_menu_"))
async def handle_validity_menu_back(query: CallbackQuery, state: FSMContext, services: Services):
    """Returns to the validity selector menu for this category."""
    await state.clear()
    cat_id = callback_int(query.data, "catval_menu_")
    if cat_id is None:
        return
    cat = await services.catalog.category(cat_id)
    if not cat:
        return
    is_other = not cat.get("is_pinned")
    back_target = "open_categories" if is_other else "back_to_main"
    await show_category_or_validity(query, state, services, category=cat, back_target=back_target)


@router.callback_query(F.data.startswith("catval_all_"))
async def handle_validity_show_all(query: CallbackQuery, state: FSMContext, services: Services):
    """Show all products under this validity-filtered category."""
    await state.clear()
    cat_id = callback_int(query.data, "catval_all_")
    if cat_id is None:
        return
    await show_products_list(
        query,
        state,
        services,
        category_id=cat_id,
        back_target=f"catval_menu_{cat_id}",
    )


@router.callback_query(F.data.startswith("catval_"))
async def handle_validity_choice(query: CallbackQuery, state: FSMContext, services: Services):
    """Handle clicking on a specific validity button (e.g. catval_1_0)."""
    await state.clear()
    parts = query.data.split("_")
    if len(parts) < 3:
        return
    try:
        cat_id = int(parts[1])
        val_idx = int(parts[2])
    except ValueError:
        return

    validities = await services.catalog.category_validities(cat_id)
    if not validities or val_idx >= len(validities):
        await show_products_list(query, state, services, category_id=cat_id, back_target=f"catval_menu_{cat_id}")
        return

    chosen_label = validities[val_idx]
    await show_products_list(
        query,
        state,
        services,
        category_id=cat_id,
        back_target=f"catval_menu_{cat_id}",
        duration_label=chosen_label,
    )


async def show_products_list(
    event: Message | CallbackQuery,
    state: FSMContext,
    services: Services,
    category_id: int | str | None = None,
    back_target: str = "back_to_main",
    duration_label: str | None = None,
):
    products = await services.catalog.products(
        category_id=category_id,
        active_only=True,
        limit=100,
        in_stock_first=True,
        duration_label=duration_label,
    )
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")

    category_name = ""
    category_icon_display = ""
    cat = None
    if category_id == "uncategorized":
        category_name = "Uncategorized"
        category_icon_display = f"{ICON_NOTE} "
    elif isinstance(category_id, int):
        cat = await services.catalog.category(category_id)
        if cat:
            category_name = cat["name"]
            cat_emoji_id = cat.get("custom_emoji_id")
            cat_icon = cat.get("icon") or "🏷️"
            if cat_emoji_id and str(cat_emoji_id).strip().isdigit():
                category_icon_display = f"{tg_icon(str(cat_emoji_id).strip(), cat_icon)} "
            elif cat_icon:
                category_icon_display = f"{cat_icon} "

    is_other_products = (back_target == "open_categories") or (category_id is None) or (category_id == "uncategorized") or bool(cat is not None and not cat.get("is_pinned"))

    if cat and cat.get("has_validity_filter") == 1:
        effective_back_target = f"catval_menu_{cat['id']}"
    elif back_target and (back_target.startswith("catval_menu_") or back_target == "open_categories"):
        effective_back_target = back_target
    else:
        effective_back_target = "open_categories" if is_other_products else "back_to_main"

    if not products:
        if category_name and duration_label:
            header = f"{category_icon_display}<b>{escape(category_name)} ({escape(duration_label)}):</b>"
        elif category_name:
            header = f"{category_icon_display}<b>{escape(category_name)}:</b>"
        else:
            header = f"{ICON_SHOP} <b>Available Products:</b>"
        msg = f"{header}\n\n{ICON_SHOP} <b>No products available right now.</b>"
        nav_btns = []
        if effective_back_target not in ("back_to_main", "none"):
            nav_btns.append(InlineKeyboardButton(text="Back", callback_data=effective_back_target, style="primary", icon_custom_emoji_id=Icons.BACK))
        nav_btns.append(InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE))
        await respond(event, msg, InlineKeyboardMarkup(inline_keyboard=[nav_btns]))
        return

    total_pages = max(1, math.ceil(len(products) / PAGE_SIZE))
    page = 1
    page_products = products[0:PAGE_SIZE]

    tg_user = event.from_user
    user_row = await services.users.get(tg_user.id) if tg_user else None
    is_reseller = (user_row.get("rank") or "").strip().lower() == "reseller" if user_row else False

    keyboard = get_products_keyboard(
        products=page_products,
        page=page,
        total_pages=total_pages,
        currency_symbol=symbol,
        category_id=category_id,
        back_target=effective_back_target,
        is_reseller=is_reseller,
        usd_rate=usd_rate,
        show_usd=show_usd,
    )
    if category_name and duration_label:
        title = f"{category_icon_display}<b>{escape(category_name)} ({escape(duration_label)}):</b>"
    elif category_name:
        title = f"{category_icon_display}<b>{escape(category_name)}:</b>"
    else:
        title = f"{ICON_SHOP} <b>Available Products:</b>"
    await respond(event, title, keyboard)


@router.callback_query(F.data == "noop")
async def handle_noop(query: CallbackQuery):
    with suppress(TelegramBadRequest):
        await query.answer()


@router.callback_query(F.data == "close_menu")
async def handle_close_menu(query: CallbackQuery, state: FSMContext):
    await state.clear()
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.delete()


@router.callback_query(F.data.startswith("shop_p_"))
async def paginate_products(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    if (query.data or "").endswith("_last"):
        with suppress(TelegramBadRequest):
            await query.answer("You are on the last page! 📄")
        return

    parts = query.data.split("_")
    category_id: int | str | None = None
    if len(parts) >= 4:
        if parts[2] == "uncat":
            category_id = "uncategorized"
        elif parts[2] != "all" and parts[2].isdigit():
            category_id = int(parts[2])
    requested_page = int(parts[-1]) if parts[-1].isdigit() else 1

    with suppress(TelegramBadRequest):
        await query.answer("Refreshed! 🔄")

    products = await services.catalog.products(category_id=category_id, active_only=True, limit=100, in_stock_first=True)
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")

    category_name = ""
    category_icon_display = ""
    cat = None
    if category_id == "uncategorized":
        category_name = "Uncategorized"
        category_icon_display = f"{ICON_NOTE} "
    elif isinstance(category_id, int):
        cat = await services.catalog.category(category_id)
        if cat:
            category_name = cat["name"]
            cat_emoji_id = cat.get("custom_emoji_id")
            cat_icon = cat.get("icon") or "🏷️"
            if cat_emoji_id and str(cat_emoji_id).strip().isdigit():
                category_icon_display = f"{tg_icon(str(cat_emoji_id).strip(), cat_icon)} "
            elif cat_icon:
                category_icon_display = f"{cat_icon} "

    is_other_products = (category_id is None) or (category_id == "uncategorized") or bool(cat is not None and not cat.get("is_pinned"))

    if cat and cat.get("has_validity_filter") == 1:
        back_target = f"catval_menu_{cat['id']}"
    else:
        back_target = "open_categories" if is_other_products else "back_to_main"

    if not products:
        header = (
            f"{category_icon_display}<b>{escape(category_name)}:</b>"
            if category_name
            else f"{ICON_SHOP} <b>Available Products:</b>"
        )
        msg = f"{header}\n\n{ICON_SHOP} <b>No products available right now.</b>"
        nav_btns = []
        if back_target and back_target not in ("back_to_main", "none"):
            nav_btns.append(InlineKeyboardButton(text="Back", callback_data=back_target, style="primary", icon_custom_emoji_id=Icons.BACK))
        nav_btns.append(InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE))
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[nav_btns]))
        return

    total_pages = max(1, math.ceil(len(products) / PAGE_SIZE))
    page = min(max(requested_page, 1), total_pages)
    page_products = products[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    tg_user = query.from_user
    user_row = await services.users.get(tg_user.id) if tg_user else None
    is_reseller = (user_row.get("rank") or "").strip().lower() == "reseller" if user_row else False

    keyboard = get_products_keyboard(
        products=page_products,
        page=page,
        total_pages=total_pages,
        currency_symbol=symbol,
        category_id=category_id,
        back_target=back_target,
        is_reseller=is_reseller,
        usd_rate=usd_rate,
        show_usd=show_usd,
    )
    title = (
        f"{category_icon_display}<b>{escape(category_name)}:</b>"
        if category_name
        else f"{ICON_SHOP} <b>Available Products:</b>"
    )
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(title, reply_markup=keyboard)


# Matches prod_<id> only. A startswith("prod_") filter also swallowed
# prod_desc_<id>, because the first handler registered for a callback wins,
# and that one answered "Product not found" after failing to read "desc_12"
# as a number.
@router.callback_query(F.data.regexp(r"^prod_\d+$"))
async def show_product_detail(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    product_id = callback_int(query.data, "prod_")
    product = await services.catalog.product(product_id) if product_id is not None else None
    if not product or not product["is_active"]:
        with suppress(TelegramBadRequest):
            await query.answer("Product not found or currently unavailable.", show_alert=True)
        return
    text, keyboard = await product_view(services, product, query.from_user.id, quantity=1)
    await respond(query, text, keyboard)


@router.callback_query(F.data.startswith("prod_desc_"))
async def show_product_description(query: CallbackQuery, state: FSMContext, services: Services):
    """The Description button. Shown as its own panel so the whole text fits,
    however long it is, with a way back to the product it belongs to."""
    product_id = callback_int(query.data, "prod_desc_")
    if product_id is None:
        with suppress(TelegramBadRequest):
            await query.answer("Please reopen the product.", show_alert=True)
        return

    product = await services.catalog.product(product_id)
    if not product or not product.get("is_active"):
        with suppress(TelegramBadRequest):
            await query.answer("This product is no longer available.", show_alert=True)
        return

    desc = (product.get("description") or "").strip()
    if not desc:
        with suppress(TelegramBadRequest):
            await query.answer("No description for this product.", show_alert=True)
        return

    data = await state.get_data()
    quantity = max(1, int(data.get(f"qty_{product_id}", 1) or 1))
    icon = product.get("icon") or "📦"
    custom_emoji_id = product.get("custom_emoji_id")
    if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
        icon = tg_icon(str(custom_emoji_id).strip(), icon)

    text = (
        f"{ICON_NOTE} <b>Description</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{icon} <b>{escape(product['title'])}</b>\n\n"
        f"{escape(desc)}"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="Back to product",
                callback_data=f"qty_set_{product_id}_{quantity}",
                style="primary",
                icon_custom_emoji_id=Icons.BACK,
            )
        ]]
    )
    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("qty_set_"))
async def adjust_quantity(query: CallbackQuery, state: FSMContext, services: Services):
    """Handles [-] and [+] button taps to adjust quantity dynamically in real-time."""
    parts = query.data.split("_")
    if len(parts) < 4:
        return
    product_id = int(parts[2]) if parts[2].isdigit() else 0
    quantity = int(parts[3]) if parts[3].isdigit() else 1
    quantity = max(1, quantity)

    product = await services.catalog.product(product_id)
    if not product or not product["is_active"]:
        with suppress(TelegramBadRequest):
            await query.answer("Product unavailable.", show_alert=True)
        return

    is_manual = product.get("delivery_type") == "manual"
    stock = product.get("stock", 0)
    if not is_manual and stock > 0 and quantity > stock:
        quantity = stock
        with suppress(TelegramBadRequest):
            await query.answer(f"Only {stock} available in stock!", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer()

    # Remember it, so leaving the product for its description and coming back
    # does not quietly reset the quantity the customer chose.
    await state.update_data(**{f"qty_{product_id}": quantity})

    text, keyboard = await product_view(services, product, query.from_user.id, quantity=quantity)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


async def get_keypad_view_text(
    services: Services,
    product: dict[str, Any],
    tg_user_id: int,
    buffer: str = "1",
) -> str:
    user = await services.users.get(tg_user_id)
    balance = user["balance"] if user else 0.0
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    show_usd = await services.settings.flag("show_usd_price")
    stock = product.get("stock", 0)
    is_manual = product.get("delivery_type") == "manual"
    title = escape(product["title"])

    cat_id = product.get("category_id")
    cat = await services.catalog.category(cat_id) if cat_id else None
    category_name = cat["name"] if cat else "General"
    cat_emoji_id = cat.get("custom_emoji_id") if cat else None
    cat_icon = cat.get("icon") or "📁" if cat else "📁"
    if cat_emoji_id and str(cat_emoji_id).strip().isdigit():
        cat_icon_display = tg_icon(str(cat_emoji_id).strip(), cat_icon)
    else:
        cat_icon_display = cat_icon

    custom_emoji_id = product.get("custom_emoji_id")
    clean_title = title
    if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
        for em in ["🌐", "🛡️", "🛡", "⚡", "📱", "🚀", "🤖", "🧠", "🎨", "💻", "✨", "🍿", "🎵", "📺", "⭐", "🎬", "❌", "💎", "📦"]:
            if clean_title.startswith(em):
                clean_title = clean_title[len(em):].strip()
                break
        prod_icon_display = tg_icon(str(custom_emoji_id).strip(), product.get("icon") or "📦")
    else:
        prod_icon_display = product.get("icon") or "📦"

    if cat_emoji_id and custom_emoji_id and str(cat_emoji_id).strip() == str(custom_emoji_id).strip():
        prod_icon_display = "📦"

    if is_manual:
        stock_text = f"<b>Available (Manual Delivery) {ICON_TIMER}</b>"
    elif stock > 0:
        stock_text = f"<b>{stock}</b> Available"
    else:
        stock_text = f"<b>Out of Stock {ICON_CROSS}</b>"

    is_reseller = (user.get("rank") or "").strip().lower() == "reseller" if user else False
    reseller_price = product.get("reseller_price")
    if is_reseller and reseller_price is not None and float(reseller_price) > 0:
        unit_price = float(reseller_price)
    else:
        unit_price = float(product["price"])
    unit_price_str = format_dual_price(unit_price, symbol, usd_rate=usd_rate, show_usd=show_usd)
    balance_str = format_dual_price(balance, symbol, usd_rate=usd_rate, show_usd=show_usd)

    duration = escape(product.get("duration_label") or "")
    duration_line = ""
    if duration and duration.lower() not in {"instant", "none", "n/a", ""}:
        duration_line = f"{ICON_TIMER} <b>Validity:</b> {duration}\n"

    desc = (product.get("description") or "").strip()
    desc_line = ""
    if desc and desc.lower() not in {"n/a", "none", "no description", "null"} and not is_redundant_description(product["title"], desc):
        desc_line = f"{ICON_NOTE} <b>Description:</b> {escape(desc)}\n"

    return (
        f"{ICON_BALANCE} <b>Your Balance:</b> <code>{balance_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{cat_icon_display} <b>Category:</b> {escape(category_name)}\n"
        f"{prod_icon_display} <b>Package:</b> <b>{clean_title}</b>\n"
        f"{ICON_MONEY} <b>Price Rate:</b> <code>{unit_price_str}</code>\n"
        f"{ICON_STATS} <b>Available Stock:</b> {stock_text}\n"
        f"{duration_line}"
        f"{desc_line}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💡 <b>How to use:</b> tap the digits below or send a number, then tap <b>Confirm</b>.\n\n"
        f"🔢 <b>Current Quantity:</b> <code>{buffer}</code>"
    )


@router.callback_query(F.data.startswith("qty_custom_"))
async def prompt_custom_quantity(query: CallbackQuery, state: FSMContext, services: Services):
    """User wants to enter a custom quantity manually."""
    product_id = callback_int(query.data, "qty_custom_")
    if product_id is None:
        return
    product = await services.catalog.product(product_id)
    if not product or not product["is_active"]:
        with suppress(TelegramBadRequest):
            await query.answer("Product unavailable.", show_alert=True)
        return

    buffer = "1"
    await state.set_state(ShopQuantityStates.waiting_for_quantity)
    await state.update_data(product_id=product_id, buffer=buffer, has_typed=False)

    with suppress(TelegramBadRequest):
        await query.answer()

    text = await get_keypad_view_text(services, product, query.from_user.id, buffer=buffer)
    keypad = get_custom_quantity_keypad(product_id)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keypad)


@router.callback_query(F.data.startswith("qpad_"))
async def handle_keypad_action(query: CallbackQuery, state: FSMContext, services: Services):
    """Handles digit taps and actions from the numeric keypad."""
    parts = query.data.split("_")
    if len(parts) < 3:
        return
    product_id = int(parts[1]) if parts[1].isdigit() else 0
    action = "_".join(parts[2:])

    product = await services.catalog.product(product_id)
    if not product or not product["is_active"]:
        with suppress(TelegramBadRequest):
            await query.answer("Product unavailable.", show_alert=True)
        return

    is_manual = product.get("delivery_type") == "manual"
    stock = product.get("stock", 0)
    upper_bound = stock if not is_manual and stock > 0 else 999

    data = await state.get_data()
    buffer = str(data.get("buffer") or "1")
    has_typed = bool(data.get("has_typed", False))

    if action == "back":
        await state.clear()
        with suppress(TelegramBadRequest):
            await query.answer()
        qty = int(buffer) if buffer.isdigit() and int(buffer) >= 1 else 1
        text, kb = await product_view(services, product, query.from_user.id, quantity=qty)
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(text, reply_markup=kb)
        return

    if action == "confirm":
        await state.clear()
        with suppress(TelegramBadRequest):
            await query.answer()
        qty = int(buffer) if buffer.isdigit() and int(buffer) >= 1 else 1
        qty = min(max(1, qty), upper_bound)
        text, kb = await product_view(services, product, query.from_user.id, quantity=qty)
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(text, reply_markup=kb)
        return

    if action == "del":
        buffer = buffer[:-1] if len(buffer) > 1 else "1"
    elif action == "clr":
        buffer = "1"
        has_typed = False
    elif action == "max":
        max_val = stock if not is_manual and stock > 0 else 100
        buffer = str(max(1, max_val))
        has_typed = True
    elif action.startswith("set_"):
        target_val = int(action.replace("set_", ""))
        buffer = str(min(target_val, upper_bound))
        has_typed = True
    elif action.isdigit():
        if not has_typed:
            buffer = action if action != "0" else "1"
            has_typed = True
        else:
            new_buf = (buffer + action).lstrip("0") or "1"
            if len(new_buf) <= 4:
                if int(new_buf) > upper_bound:
                    buffer = str(upper_bound)
                    with suppress(TelegramBadRequest):
                        await query.answer(f"Stock limit: {upper_bound}", show_alert=False)
                else:
                    buffer = new_buf
            else:
                with suppress(TelegramBadRequest):
                    await query.answer("Maximum 4 digits allowed", show_alert=False)

    await state.update_data(product_id=product_id, buffer=buffer, has_typed=has_typed)
    with suppress(TelegramBadRequest):
        await query.answer()

    text = await get_keypad_view_text(services, product, query.from_user.id, buffer=buffer)
    keypad = get_custom_quantity_keypad(product_id)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keypad)


@router.message(ShopQuantityStates.waiting_for_quantity)
async def process_custom_quantity(message: Message, state: FSMContext, services: Services):
    """Processes user text input for custom quantity."""
    text = (message.text or "").strip()
    # The menu buttons send plain text, so without this a customer who reached this prompt
    # is trapped: every button they press is read as a quantity, fails, and prints the same
    # complaint. Tapping a menu button means they want to leave, so let them.
    if is_navigation(text):
        await navigate(text, message, state, services)
        return

    if not text.isdigit() or int(text) < 1:
        await message.answer(f"{ICON_WARNING} Please enter a valid positive number:")
        return

    qty = int(text)
    data = await state.get_data()
    product_id = data.get("product_id")
    await state.clear()

    product = await services.catalog.product(product_id) if product_id else None
    if not product or not product["is_active"]:
        await message.answer(f"{ICON_CROSS} Product unavailable.")
        return

    is_manual = product.get("delivery_type") == "manual"
    stock = product.get("stock", 0)
    if not is_manual and stock > 0 and qty > stock:
        qty = stock
        await message.answer(f"{ICON_WARNING} Quantity adjusted to available stock: {stock}")

    view_text, keyboard = await product_view(services, product, message.from_user.id, quantity=qty)
    await message.answer(view_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("buy_qty_"))
async def execute_quantity_purchase(query: CallbackQuery, state: FSMContext, services: Services):
    """Executes a purchase with the specified quantity."""
    await state.clear()
    parts = (query.data or "").split("_")
    if len(parts) < 5 or not parts[2].isdigit() or not parts[3].isdigit():
        await query.answer("Please reopen the product to confirm your purchase.", show_alert=True)
        return

    product_id = int(parts[2])
    quantity = int(parts[3])
    token = parts[4]

    # Scrolling back to an older message shows an older price, and the charge always
    # comes from the database. Rather than quietly take a different amount than the one
    # on screen, show the product again at today's price and let them decide.
    shown_cents = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else None
    if shown_cents is not None:
        product = await services.catalog.product(product_id)
        if product and round(float(product["price"]) * 100) != shown_cents:
            symbol = await services.settings.get("currency_symbol")
            was = shown_cents / 100
            now = float(product["price"])
            with suppress(TelegramBadRequest):
                await query.answer(
                    f"Price changed: {was:.2f} -> {now:.2f} {symbol}. Nothing was charged.",
                    show_alert=True,
                )
            view_text, keyboard = await product_view(services, product, query.from_user.id, quantity=quantity)
            if query.message:
                with suppress(TelegramBadRequest):
                    await query.message.edit_text(view_text, reply_markup=keyboard)
            return

    success, message, order = await services.purchases.purchase(
        query.from_user.id, product_id, quantity=quantity, request_id=f"bot-{token}"
    )
    if not success or not order:
        with suppress(TelegramBadRequest):
            await query.answer(f"⚠️ {message}", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer("🎉 Purchase Successful!", show_alert=False)

    if query.message:
        is_waiting = order.get("fulfillment") == "waiting"
        success_title = f"{ICON_TIMER} <b>Order Placed!</b>" if is_waiting else f"{ICON_CHECK} <b>Purchase Successful!</b>"
        below_text = (
            "<i>Payment successful! Your order is being prepared and will be delivered shortly.</i>"
            if is_waiting
            else "<i>Your order details and delivery are below 👇</i>"
        )
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{success_title}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ICON_ORDERS} <b>{escape(order.get('product_title', 'Product'))}</b>\n\n"
                f"{below_text}",
                reply_markup=None,
            )


@router.callback_query(F.data.startswith("buy_"))
async def execute_legacy_purchase(query: CallbackQuery, state: FSMContext, services: Services):
    """Legacy 1-item purchase compatibility."""
    await state.clear()
    parts = (query.data or "").split("_")
    if len(parts) != 3 or not parts[1].isdigit() or not re.fullmatch(r"[0-9a-f]{32}", parts[2]):
        await query.answer("Please reopen the product to confirm your purchase.", show_alert=True)
        return

    success, message, order = await services.purchases.purchase(
        query.from_user.id, int(parts[1]), quantity=1, request_id=f"bot-{parts[2]}"
    )
    if not success or not order:
        with suppress(TelegramBadRequest):
            await query.answer(f"⚠️ {message}", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer("🎉 Purchase Successful!", show_alert=False)

    if query.message:
        is_waiting = order.get("fulfillment") == "waiting"
        success_title = f"{ICON_TIMER} <b>Order Placed!</b>" if is_waiting else f"{ICON_CHECK} <b>Purchase Successful!</b>"
        below_text = (
            "<i>Payment successful! Your order is being prepared and will be delivered shortly.</i>"
            if is_waiting
            else "<i>Your order details and delivery are below 👇</i>"
        )
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{success_title}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ICON_ORDERS} <b>{escape(order.get('product_title', 'Product'))}</b>\n\n"
                f"{below_text}",
                reply_markup=None,
            )

