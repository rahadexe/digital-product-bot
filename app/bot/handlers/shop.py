from __future__ import annotations

import asyncio
import math
import re
import time
from contextlib import suppress
from html import escape
from typing import Any
from uuid import uuid4

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.bot.formatting import callback_int, forget_menu_message, format_dual_price, resolve_user_currency, respond
from app.core.identifiers import format_order_id
from app.bot.handlers import search
from app.bot.handlers.navigation import is_navigation, navigate
from app.bot.icons import (
    ICON_CHECK,
    ICON_CROSS,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_SHOP,
    ICON_TIMER,
    ICON_WARNING,
    tg_icon,
)
from app.bot.keyboards import (
    extract_emoji_and_name,
    get_categories_keyboard,
    get_custom_quantity_keypad,
    get_products_keyboard,
    get_quantity_selector_keyboard,
    get_validity_selector_keyboard,
    product_display_labels,
)
from app.core.i18n import t
from app.services import Services

router = Router(name="shop_router")


# How long the banner a purchase leaves behind stays. The receipt follows seconds later
# through the outbox, and once it has arrived the banner is a signpost pointing at a
# message already on screen. A minute covers a slow worker without leaving it there.
PURCHASE_BANNER_SECONDS = 60


async def _clear_banner(message: Message, seconds: int) -> None:
    """Take away the "your order is below" note once the order really is below."""
    await asyncio.sleep(seconds)
    with suppress(Exception):
        await message.delete()

PAGE_SIZE = 16


class ShopQuantityStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_customer_input = State()


class CategoryTextFilter(BaseFilter):
    """Dynamically matches any active category name from the database, whether pinned or unpinned."""

    _cached_map: tuple[float, dict[str, dict[str, Any]]] | None = None
    _EMOJIS = ("📁", "🛡️", "🛡", "🌐", "✉️", "📦", "💎", "⚡", "📱", "🚀", "🤖", "🧠", "🎨", "💻", "✨", "🍿", "🎵", "📺", "⭐", "🎬", "❌")

    @classmethod
    def _build_map(cls, categories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        lookup: dict[str, dict[str, Any]] = {}
        for c in categories:
            name = c.get("name", "").strip().casefold()
            if not name:
                continue
            lookup[name] = c
            clean = name
            for em in cls._EMOJIS:
                if clean.startswith(em):
                    clean = clean[len(em):].strip()
                    break
            if clean:
                lookup[clean] = c
            regex_clean = re.sub(r'^[^\w\s]+\s*', '', name).strip()
            if regex_clean:
                lookup[regex_clean] = c
            icon = (c.get("icon") or "").strip().casefold()
            if icon:
                lookup[f"{icon} {name}"] = c
                lookup[f"{icon} {clean}"] = c
        return lookup

    async def __call__(self, message: Message, services: Services) -> bool | dict[str, Any]:
        text = (message.text or "").strip()
        if not text or text.startswith("/"):
            return False

        # Exclude reserved system button titles
        ignored = {
            "add balance", "refer & earn", "my profile", "support", "apply as a reseller",
            "become reseller", "reseller panel", "admin panel",
            "premium products", "all products",
            "cancel", "shop", "store", "products", "deposit", "account", "orders", "guide", "channel",
            "updates", "search", "search products", "wallet", "referral", "reseller", "settings",
            # Bengali
            "অ্যাড ব্যালেন্স", "সার্চ", "রেফার ও ইনকাম", "আমার প্রোফাইল", "সাপোর্ট",
            "রিসেলার হন", "রিসেলার প্যানেল", "অ্যাডমিন প্যানেল",
            "ওয়ালেট", "অর্ডার", "অর্ডারস", "একাউন্ট", "অ্যাকাউন্ট", "রেফারেল", "রেফার", "রিসেলার", "সকল প্রোডাক্ট",
            "স্টোর", "শপ",
        }
        clean_text = text.casefold()
        for em in self._EMOJIS:
            if clean_text.startswith(em):
                clean_text = clean_text[len(em):].strip()
                break
        regex_clean = re.sub(r'^[^\w\s]+\s*', '', text.casefold()).strip()

        if clean_text in ignored or regex_clean in ignored:
            return False

        now = time.monotonic()
        if not self._cached_map or now - self._cached_map[0] > 60.0:
            categories = await services.catalog.categories(active_only=True, with_products=False)
            self.__class__._cached_map = (now, self._build_map(categories))

        lookup = self._cached_map[1]
        c = lookup.get(text.casefold()) or lookup.get(clean_text) or lookup.get(regex_clean)
        if c:
            return {"category": c}

        # Fallback suffix check
        for name, cat in lookup.items():
            if text.casefold().endswith(name) or clean_text.endswith(name):
                return {"category": cat}

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
        if validities and len(validities) > 1:
            kb = get_validity_selector_keyboard(
                category_id=cat_id,
                validities=validities,
                show_all_option=True,
                back_target=back_target,
            )
            title = "<b>Select Validity:</b>"
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


class ProductTextFilter(BaseFilter):
    """Matches product names clicked from the reply keyboard."""
    _cached_products: tuple[float, dict[str, dict[str, Any]]] = (0.0, {})

    async def __call__(self, message: Message, services: Services) -> bool | dict[str, Any]:
        text = (message.text or "").strip()
        if not text or len(text) < 2:
            return False

        ignored = {
            "search", "wallet", "orders", "account", "support", "admin panel",
            "all catalog", "all products", "back to main", "main menu", "back to catalog",
            "back to products", "back", "cancel", "refresh", "price list", "balance history",
            "refer & earn", "refer", "language", "reseller panel", "become reseller",
            "stats", "products", "deposits", "users", "settings", "guide", "store", "shop",
            "সার্চ", "ওয়ালেট", "অর্ডার", "একাউন্ট", "সাপোর্ট", "অ্যাডমিন প্যানেল",
            "সকল প্রোডাক্ট", "মেইন মেনু", "ব্যাক", "বাতিল", "রিফ্রেশ", "প্রাইস লিস্ট",
            "ব্যালেন্স হিস্ট্রি", "রেফার", "ভাষা", "রিসেলার", "গাইড", "স্টোর", "শপ",
        }
        clean_text = text.casefold()
        regex_clean = re.sub(r'^[^\w\s]+\s*', '', clean_text).strip()
        title_only = re.split(r'\s*[·—\-]\s*', regex_clean)[0].strip()
        title_with_emoji = re.split(r'\s*[·—\-]\s*', clean_text)[0].strip()

        if clean_text in ignored or regex_clean in ignored or title_only in ignored:
            return False

        if title_only.startswith("buy now") or title_only.startswith("কিনুন") or title_only.startswith("buy"):
            return False

        now = time.monotonic()
        if not self._cached_products or now - self._cached_products[0] > 30.0:
            all_prods = await services.catalog.products(active_only=True, limit=200)
            prod_map = {}
            for p in all_prods:
                t_lower = p["title"].strip().casefold()
                prod_map[t_lower] = p
                p_clean = re.sub(r'^[^\w\s]+\s*', '', t_lower).strip()
                prod_map[p_clean] = p
                custom_icon = (p.get("icon") or "").strip().casefold()
                if custom_icon:
                    prod_map[f"{custom_icon} {t_lower}"] = p
                    prod_map[f"{custom_icon} {p_clean}"] = p
            self.__class__._cached_products = (now, prod_map)

        lookup = self._cached_products[1]
        p = (
            lookup.get(title_only)
            or lookup.get(title_with_emoji)
            or lookup.get(regex_clean)
            or lookup.get(clean_text)
        )
        if p:
            return {"product": p}

        for name, prod in lookup.items():
            if len(name) >= 3 and (name == title_only or title_only.startswith(name)):
                return {"product": prod}

        return False


@router.message(ProductTextFilter())
async def handle_product_by_text(message: Message, state: FSMContext, services: Services, product: dict[str, Any]):
    """Dynamic handler when a customer taps a product button from the reply keyboard."""
    await state.clear()
    await state.update_data(active_product_id=product["id"])
    text, keyboard = await product_view(services, product, message.from_user.id)
    await respond(message, text, keyboard)


@router.message(F.text.func(lambda text: bool(text and (
    text.strip().startswith("⚡ BUY NOW")
    or text.strip().startswith("BUY NOW")
    or text.strip().startswith("⚡ Buy Now")
    or text.strip().startswith("Buy Now")
    or text.strip().startswith("⚡ কিনুন")
    or text.strip().startswith("কিনুন")
))))
async def handle_buy_now_by_text(message: Message, state: FSMContext, services: Services):
    """Executes instant purchase when customer taps BUY NOW in reply keyboard."""
    buyer_id = message.from_user.id
    lang = await services.users.get_language(buyer_id)
    data = await state.get_data()
    product_id = data.get("active_product_id")
    if not product_id:
        not_selected = "অনুগ্রহ করে প্রথমে ক্যাটালগ থেকে প্রোডাক্ট সিলেক্ট করুন।" if lang == "bn" else "Please select a product from catalog first."
        await message.answer(not_selected)
        return

    token = uuid4().hex[:12]
    product = await services.catalog.product(product_id)
    if not product or not product.get("is_active"):
        unavail = "❌ এই প্রোডাক্টটি বর্তমানে পাওয়া যাচ্ছে না।" if lang == "bn" else "❌ Product unavailable."
        await message.answer(unavail)
        return

    if product.get("requires_customer_input"):
        prompt_custom = (product.get("customer_input_prompt") or "").strip()
        if lang == "bn":
            header = "📝 <b>অর্ডার সম্পন্ন করতে তথ্য প্রদান করুন:</b>"
            default_prompt = "দয়া করে আপনার জিমেইল এড্রেস বা প্রয়োজনীয় তথ্য লিখে রিপ্লাই দিন:"
            hint = f"📌 {escape(prompt_custom)}" if prompt_custom else f"📌 {default_prompt}"
            instr = f"{header}\n\n{hint}\n\n<i>নিচে মেসেজ বক্সে লিখে সেন্ড করুন 👇</i>"
            cancel_btn = "❌ বাতিল করুন"
        else:
            header = "📝 <b>Required Information:</b>"
            default_prompt = "Please reply with your Gmail address or account details:"
            hint = f"📌 {escape(prompt_custom)}" if prompt_custom else f"📌 {default_prompt}"
            instr = f"{header}\n\n{hint}\n\n<i>Type your info below and send 👇</i>"
            cancel_btn = "❌ Cancel"

        await state.set_state(ShopQuantityStates.waiting_for_customer_input)
        await state.update_data(product_id=product_id, quantity=1, token=token)
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=cancel_btn, callback_data=f"prod_{product_id}")
        ]])
        await message.answer(instr, reply_markup=cancel_kb)
        return

    success, result_msg, order = await services.purchases.purchase(
        buyer_id, product_id, quantity=1, request_id=f"bot-{token}"
    )
    if not success or not order:
        wallet_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="💰 Balance" if lang != "bn" else "💳 ওয়ালেট",
                callback_data="open_deposit",
            )
        ]])
        add_bal_hint = "👇 <i>অনুগ্রহ করে ওয়ালেটে ব্যালেন্স যোগ করুন:</i>" if lang == "bn" else "👇 <i>Please add funds to your balance:</i>"
        await message.answer(f"⚠️ {result_msg}\n\n{add_bal_hint}", reply_markup=wallet_kb)
        return

    orders_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="View order", callback_data=f"vord_{order.get('order_id', order.get('id'))}_1")
    ]])
    order_id = order.get("order_id", order.get("id"))
    creds = order.get("delivered_item") or order.get("credentials_delivered") or ""
    symbol = await services.settings.get("currency_symbol")
    paid_val = order.get("price") if order.get("price") is not None else order.get("price_paid", 0)
    paid_txt = f"{paid_val} {symbol}"

    if lang == "bn":
        delivered_txt = f"\n\n🔑 <b>ডেলিভারি:</b>\n<code>{escape(creds)}</code>" if creds else ""
        msg_text = (
            f"🎉 <b>ক্রয় সফল হয়েছে!</b>\n\n"
            f"📦 <b>অর্ডার আইডি:</b> {format_order_id(order_id)}\n"
            f"💰 <b>পরিশোধিত মূল্য:</b> {paid_txt}"
            f"{delivered_txt}\n\n"
            f"<i>আমাদের সাথে থাকার জন্য ধন্যবাদ!</i>"
        )
    else:
        delivered_txt = f"\n\n🔑 <b>Delivered Item:</b>\n<code>{escape(creds)}</code>" if creds else ""
        msg_text = (
            f"🎉 <b>Order placed</b>\n\n"
            f"📦 <b>Order ID:</b> {format_order_id(order_id)}\n"
            f"💰 <b>Total Paid:</b> {paid_txt}"
            f"{delivered_txt}\n\n"
            f"<i>Thank you for your purchase!</i>"
        )
    await message.answer(msg_text, reply_markup=orders_kb)


@router.callback_query(F.data.in_({"open_cat_vpn", "open_cat_proxy", "open_cat_mailbox"}))
async def handle_legacy_cat_callbacks(query: CallbackQuery, state: FSMContext, services: Services):
    """Graceful fallback for legacy callback buttons."""
    await state.clear()
    categories = await services.catalog.categories(active_only=True, with_products=False)
    slug = query.data.replace("open_cat_", "").lower()
    cat = next((c for c in categories if slug in c["name"].lower()), None)
    cat = cat or (categories[0] if categories else None)
    if cat:
        await show_category_or_validity(query, state, services, category=cat, back_target="back_to_main")


@router.callback_query(F.data.in_({"open_other_products", "open_premium_products", "open_categories"}))
async def show_other_products_hub(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Dynamic showcase displaying products directly with category filter chips."""
    await state.clear()
    await show_products_list(event, state, services, category_id=None, back_target="back_to_main")


@router.callback_query(F.data.startswith("catpage_"))
async def paginate_categories(query: CallbackQuery, state: FSMContext, services: Services):
    """Handle pagination for category list."""
    try:
        page = int(query.data.split("_")[1])
    except (IndexError, ValueError):
        page = 1

    tg_user = query.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"

    categories = await services.catalog.categories(active_only=True, with_products=False)
    kb = get_categories_keyboard(categories, show_all_option=True, page=page, lang=lang, back_target="shop_p_all_1")
    title = t("btn_all_products", lang).replace("🛍️ ", "").strip()
    text = f"{ICON_SHOP} <b>{title}:</b>"
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


def unit_price_for(product: dict[str, Any], user: dict[str, Any] | None) -> float:
    """What this customer pays for one: the reseller rate when they have one, else the price.

    The product screen, the quantity buttons and the check that the price has not moved
    since the screen was drawn all have to agree. They did not: the check compared the
    price on the button with the shop price, so a reseller with a rate of their own was
    told "Price changed" on every attempt and could never buy.
    """
    is_reseller = (user.get("rank") or "").strip().lower() == "reseller" if user else False
    reseller_price = product.get("reseller_price")
    if is_reseller and reseller_price is not None and float(reseller_price) > 0:
        return float(reseller_price)
    return float(product["price"])


async def product_view(
    services: Services,
    product: dict[str, Any],
    tg_user_id: int,
    quantity: int = 1,
    back_target: str | None = None,
    show_helper: bool = True,
) -> tuple[str, InlineKeyboardMarkup]:
    user = await services.users.get(tg_user_id)
    balance = user["balance"] if user else 0.0
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")
    stock = product.get("stock", 0)
    display_title, duration_label, warranty_label = product_display_labels(product)
    title = escape(display_title)
    duration = escape(duration_label)
    warranty = escape(warranty_label)

    lang = await services.users.get_language(tg_user_id)
    is_manual = product.get("delivery_type") == "manual"
    is_upstream = bool(product.get("upstream_product_id"))
    available = is_manual or is_upstream or stock > 0
    stock_text = t("product_available", lang) if available else t("product_unavailable", lang)
    delivery_text = t("product_manual", lang) if is_manual else t("product_automatic", lang)
    cat_id = product.get("category_id")

    custom_emoji_id = product.get("custom_emoji_id")
    clean_title = title
    if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
        leading_emoji, remaining_title = extract_emoji_and_name(clean_title)
        if leading_emoji and remaining_title:
            clean_title = remaining_title
        prod_icon_display = tg_icon(str(custom_emoji_id).strip(), "")
    else:
        prod_icon_display = tg_icon(None, product.get("icon") or "")

    is_reseller = (user.get("rank") or "").strip().lower() == "reseller" if user else False
    reseller_price = product.get("reseller_price")
    has_reseller_rate = is_reseller and reseller_price is not None and float(reseller_price) > 0

    curr = await resolve_user_currency(services, tg_user_id)

    unit_price = unit_price_for(product, user)
    total_price = round(unit_price * quantity, 2)

    unit_price_str = format_dual_price(unit_price, symbol, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)
    total_price_str = format_dual_price(total_price, symbol, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)
    user_balance_str = format_dual_price(balance, symbol, usd_rate=usd_rate, lang=lang, currency=curr, show_usd=False)
    bal_label = "Your Balance"

    lines = [
        f"{prod_icon_display + ' ' if prod_icon_display else ''}<b>{clean_title}</b>",
        "",
    ]
    if duration and duration.lower() not in {"instant", "none", "n/a", ""}:
        lines.append(f"• Validity: {duration}")
    if warranty and warranty.lower() not in {"instant", "none", "n/a"}:
        lines.append(f"• Warranty: {warranty}")
    lines.append(f"• Status: {stock_text}")

    lines.append("")
    if quantity > 1:
        lines.append(f"💵 Price: {unit_price_str} × {quantity} = <b>{total_price_str}</b>")
    else:
        price_line = f"💵 Price: <b>{unit_price_str}</b>"
        if has_reseller_rate:
            price_line += " · <i>Reseller</i>"
        lines.append(price_line)

    lines.append(f"💰 {bal_label}: <b>{user_balance_str}</b>")

    # The description lives behind its own button rather than in the card, so a
    # long one does not push the price and the quantity controls off the screen.
    desc = (product.get("description") or "").strip()
    has_description = bool(
        desc
        and desc.lower() not in {"n/a", "none", "no description", "null"}
        and not is_redundant_description(product["title"], desc)
    )

    if show_helper:
        lines.append("")
        lines.append("<i>Use ➕/➖ or Set Custom Quantity\nto choose your desired amount.</i>")

    text = "\n".join(lines)

    if not back_target:
        back_target = f"cat_{cat_id}" if cat_id else "shop_uncat"
        # Opened from search results: Back returns to them. Every redraw of this screen
        # (the +/- buttons, a typed quantity) comes through here, so it stays that way.
        if search.opened_from_search(tg_user_id, product["id"]):
            back_target = f"sback_{product['id']}"

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
        is_upstream=is_upstream,
        back_target=back_target,
        usd_rate=usd_rate,
        product_link=product_link,
        has_description=has_description,
        lang=lang,
        product_icon_custom_emoji_id=(
            str(custom_emoji_id).strip()
            if custom_emoji_id and str(custom_emoji_id).strip().isdigit()
            else None
        ),
    )
    return text, keyboard


@router.callback_query(F.data == "open_shop")
async def show_shop_entry(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Shop entry point displaying all active categories."""
    return await show_other_products_hub(event, state, services)


@router.callback_query(F.data == "shop_all")
async def show_all_products(query: CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    await show_products_list(query, state, services, category_id=None, back_target="open_categories")


@router.callback_query(F.data.in_({"shop_uncat", "shop_uncategorized", "shop_others"}))
async def show_uncat_products(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    await show_products_list(event, state, services, category_id="others", back_target="open_categories")


@router.callback_query(F.data.startswith("cat_"))
@router.callback_query(F.data.startswith("mcat_"))
async def show_category_products(query: CallbackQuery, state: FSMContext, services: Services):
    """Show products or validity selector for a specific selected category."""
    await state.clear()
    is_main = bool(query.data and query.data.startswith("mcat_"))
    cat_id = callback_int(query.data, "mcat_" if is_main else "cat_")
    if cat_id is None:
        with suppress(TelegramBadRequest):
            await query.answer("Category unavailable.", show_alert=True)
        return
    cat = await services.catalog.category(cat_id)
    if not cat:
        with suppress(TelegramBadRequest):
            await query.answer("Category not found.", show_alert=True)
        return
    back_target = "shop_p_all_1"
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
    back_target = "shop_p_all_1"
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

    category_name = ""
    category_icon_display = ""
    cat = None

    tg_user = event.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    user_row = await services.users.get(tg_user.id) if tg_user else None
    is_reseller = (user_row.get("rank") or "").strip().lower() == "reseller" if user_row else False

    if category_id == "uncategorized":
        category_name = "Others" if lang != "bn" else "আদার্স"
    elif isinstance(category_id, int):
        cat = await services.catalog.category(category_id)
        if cat:
            category_name = cat["name"]
            cat_emoji_id = cat.get("custom_emoji_id")
            cat_icon = cat.get("icon") or ""
            if cat_emoji_id and str(cat_emoji_id).strip().isdigit():
                category_icon = tg_icon(str(cat_emoji_id).strip(), "")
            elif cat_icon:
                category_icon = tg_icon(None, cat_icon)
            else:
                category_icon = ""
            if category_icon:
                category_icon_display = f"{category_icon} "

    if cat and cat.get("has_validity_filter") == 1:
        effective_back_target = f"catval_menu_{cat['id']}"
    elif back_target and back_target.startswith("catval_menu_"):
        effective_back_target = back_target
    else:
        effective_back_target = back_target if back_target and back_target != "none" else "back_to_main"

    if not products:
        if category_name and duration_label:
            header = f"{category_icon_display}<b>{escape(category_name)} ({escape(duration_label)}):</b>"
        elif category_name:
            header = f"{category_icon_display}<b>{escape(category_name)}:</b>"
        else:
            header = f"{ICON_SHOP} <b>Available Products:</b>"
        msg = f"{header}\n\n{ICON_SHOP} <b>No products available right now.</b>"
        effective_back = effective_back_target if effective_back_target != "none" else "back_to_main"
        nav_btns = [InlineKeyboardButton(text=t("btn_back", lang), callback_data=effective_back)]
        await respond(event, msg, InlineKeyboardMarkup(inline_keyboard=[nav_btns]))
        return

    categories = None
    if hasattr(services.catalog, "categories"):
        try:
            categories = await services.catalog.categories(active_only=True, with_products=False)
        except Exception:
            categories = None

    total_pages = max(1, math.ceil(len(products) / PAGE_SIZE))
    page = 1
    page_products = products[0:PAGE_SIZE]

    keyboard = get_products_keyboard(
        products=page_products,
        page=page,
        total_pages=total_pages,
        currency_symbol=symbol,
        category_id=category_id,
        back_target=effective_back_target,
        is_reseller=is_reseller,
        usd_rate=usd_rate,
        lang=lang,
        categories=categories,
    )
    if category_name and duration_label:
        title = f"{category_icon_display}<b>{escape(category_name)} ({escape(duration_label)}):</b>"
    elif category_name:
        title = f"{category_icon_display}<b>{escape(category_name)}:</b>"
    else:
        title = f"{ICON_SHOP} <b>Available Products:</b>" if lang != "bn" else f"{ICON_SHOP} <b>প্রোডাক্টসমূহ:</b>"

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
        forget_menu_message(query.message.chat.id)
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
        await query.answer("Refreshed")

    products = await services.catalog.products(category_id=category_id, active_only=True, limit=100, in_stock_first=True)
    symbol = await services.settings.get("currency_symbol")
    usd_rate = await services.settings.number("usd_rate")

    category_name = ""
    category_icon_display = ""
    cat = None

    tg_user = query.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    user_row = await services.users.get(tg_user.id) if tg_user else None
    is_reseller = (user_row.get("rank") or "").strip().lower() == "reseller" if user_row else False

    if category_id == "uncategorized":
        category_name = "Others" if lang != "bn" else "আদার্স"
    elif isinstance(category_id, int):
        cat = await services.catalog.category(category_id)
        if cat:
            category_name = cat["name"]
            cat_emoji_id = cat.get("custom_emoji_id")
            cat_icon = cat.get("icon") or ""
            if cat_emoji_id and str(cat_emoji_id).strip().isdigit():
                category_icon = tg_icon(str(cat_emoji_id).strip(), "")
            elif cat_icon:
                category_icon = tg_icon(None, cat_icon)
            else:
                category_icon = ""
            if category_icon:
                category_icon_display = f"{category_icon} "

    if cat and cat.get("has_validity_filter") == 1:
        back_target = f"catval_menu_{cat['id']}"
    elif category_id is not None:
        back_target = "shop_p_all_1"
    else:
        back_target = "back_to_main"

    if not products:
        header = (
            f"{category_icon_display}<b>{escape(category_name)}:</b>"
            if category_name
            else f"{ICON_SHOP} <b>Available Products:</b>"
        )
        msg = f"{header}\n\n{ICON_SHOP} <b>No products available right now.</b>"
        effective_back = back_target if back_target and back_target != "none" else "back_to_main"
        nav_btns = [InlineKeyboardButton(text=t("btn_back", lang), callback_data=effective_back)]
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=[nav_btns]))
        return

    categories = None
    if hasattr(services.catalog, "categories"):
        try:
            categories = await services.catalog.categories(active_only=True, with_products=False)
        except Exception:
            categories = None

    total_pages = max(1, math.ceil(len(products) / PAGE_SIZE))
    page = min(max(requested_page, 1), total_pages)
    page_products = products[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

    keyboard = get_products_keyboard(
        products=page_products,
        page=page,
        total_pages=total_pages,
        currency_symbol=symbol,
        category_id=category_id,
        back_target=back_target,
        is_reseller=is_reseller,
        usd_rate=usd_rate,
        lang=lang,
        categories=categories,
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
    product_id = callback_int(query.data, "prod_")
    await show_product(query, state, services, product_id, category_back=True)


@router.callback_query(F.data.regexp(r"^prod_p_\d+_\d+_\w+$"))
async def show_product_detail_paginated(query: CallbackQuery, state: FSMContext, services: Services):
    parts = query.data.split("_")
    product_id = int(parts[2])
    page = int(parts[3])
    cat_key = parts[4]

    if cat_key == "all":
        back_target = f"shop_p_all_{page}"
    elif cat_key == "uncat":
        back_target = f"shop_p_uncat_{page}"
    elif cat_key.isdigit():
        cat_id = int(cat_key)
        cat = await services.catalog.category(cat_id)
        if cat and cat.get("has_validity_filter") == 1:
            back_target = f"catval_menu_{cat_id}"
        else:
            back_target = f"shop_p_{cat_id}_{page}"
    else:
        back_target = "back_to_main"

    await show_product(query, state, services, product_id, back_target=back_target)


@router.callback_query(F.data.regexp(r"^prod_m_\d+$"))
async def show_main_product_detail(query: CallbackQuery, state: FSMContext, services: Services):
    product_id = callback_int(query.data, "prod_m_")
    await show_product(query, state, services, product_id, back_target="back_to_main")


@router.callback_query(F.data.regexp(r"^prod_bo_\d+_\d+_\d+$"))
async def show_order_buy_again(query: CallbackQuery, state: FSMContext, services: Services):
    parts = query.data.split("_")
    product_id = int(parts[2])
    order_id = int(parts[3])
    page = int(parts[4])
    back_target = f"vord_{order_id}_{page}"
    await show_product(query, state, services, product_id, back_target=back_target)


async def show_product(query: CallbackQuery, state: FSMContext, services: Services,
                       product_id: int | None, *, category_back: bool = False,
                       back_target: str | None = None) -> None:
    """Draw one product. category_back: reached from a category, so Back goes there."""
    await state.clear()
    if category_back and product_id is not None:
        search.forget_search_origin(query.from_user.id, product_id)
    if product_id is not None:
        upd = {"active_product_id": product_id}
        if back_target:
            upd[f"back_target_{product_id}"] = back_target
        await state.update_data(**upd)
    product = await services.catalog.product(product_id) if product_id is not None else None
    if not product or not product["is_active"]:
        with suppress(TelegramBadRequest):
            await query.answer("Product not found or currently unavailable.", show_alert=True)
        return
    text, keyboard = await product_view(services, product, query.from_user.id, quantity=1, back_target=back_target)
    is_from_tall_catalog = bool(
        back_target and (
            back_target.startswith("shop_p_")
            or back_target.startswith("catval_menu_")
            or back_target == "open_categories"
            or category_back
        )
    )
    await respond(query, text, keyboard, new_message=is_from_tall_catalog)


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
            await query.answer("No details available for this product.", show_alert=False)
        return

    data = await state.get_data()
    quantity = max(1, int(data.get(f"qty_{product_id}", 1) or 1))
    icon = product.get("icon") or ""
    custom_emoji_id = product.get("custom_emoji_id")
    if custom_emoji_id and str(custom_emoji_id).strip().isdigit():
        icon = tg_icon(str(custom_emoji_id).strip(), "")
    else:
        icon = tg_icon(None, icon)
    description_title, _, _ = product_display_labels(product)

    lines = [
        f"{ICON_NOTE} <b>Product Details</b>",
        "",
        f"{icon + ' ' if icon else ''}<b>{escape(description_title)}</b>",
        "",
        f"{escape(desc)}",
    ]
    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🔙 Back to Product",
                callback_data=f"qty_set_{product_id}_{quantity}",
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
    is_upstream = bool(product.get("upstream_product_id"))
    stock = product.get("stock", 0)
    if not is_manual and not is_upstream and stock > 0 and quantity > stock:
        quantity = stock
        with suppress(TelegramBadRequest):
            await query.answer(f"Only {stock} available in stock!", show_alert=True)
        return

    with suppress(TelegramBadRequest):
        await query.answer()

    # Remember it, so leaving the product for its description and coming back
    # does not quietly reset the quantity the customer chose.
    await state.update_data(**{f"qty_{product_id}": quantity})

    data = await state.get_data()
    back_target = data.get(f"back_target_{product_id}")

    text, keyboard = await product_view(services, product, query.from_user.id, quantity=quantity, back_target=back_target)
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=keyboard)


async def get_keypad_view_text(
    services: Services,
    product: dict[str, Any],
    tg_user_id: int,
    buffer: str = "1",
) -> str:
    qty_val = int(buffer) if buffer.isdigit() and int(buffer) > 0 else 1
    text, _ = await product_view(services, product, tg_user_id, quantity=qty_val, show_helper=False)
    return (
        f"{text}\n\n"
        f"Quantity: <code>{escape(buffer)}</code>\n"
        "Enter a quantity, then select Confirm."
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
    is_upstream = bool(product.get("upstream_product_id"))
    stock = product.get("stock", 0)
    upper_bound = stock if not is_manual and not is_upstream and stock > 0 else 999

    data = await state.get_data()
    buffer = str(data.get("buffer") or "1")
    has_typed = bool(data.get("has_typed", False))

    if action == "back":
        back_target = data.get(f"back_target_{product_id}")
        await state.set_state(None)
        qty = int(buffer) if buffer.isdigit() and int(buffer) >= 1 else 1
        qty = min(max(1, qty), upper_bound)
        await state.update_data({
            f"qty_{product_id}": qty,
            f"back_target_{product_id}": back_target,
            "active_product_id": product_id,
        })
        with suppress(TelegramBadRequest):
            await query.answer()
        text, kb = await product_view(services, product, query.from_user.id, quantity=qty, back_target=back_target)
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(text, reply_markup=kb)
        return

    if action == "confirm":
        back_target = data.get(f"back_target_{product_id}")
        await state.set_state(None)
        qty = int(buffer) if buffer.isdigit() and int(buffer) >= 1 else 1
        qty = min(max(1, qty), upper_bound)
        await state.update_data({
            f"qty_{product_id}": qty,
            f"back_target_{product_id}": back_target,
            "active_product_id": product_id,
        })
        with suppress(TelegramBadRequest):
            await query.answer()
        text, kb = await product_view(services, product, query.from_user.id, quantity=qty, back_target=back_target)
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(text, reply_markup=kb)
        return

    if action == "del":
        if len(buffer) > 1:
            buffer = buffer[:-1]
        else:
            buffer = "1"
            has_typed = False
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
    back_target = data.get(f"back_target_{product_id}")
    await state.clear()

    product = await services.catalog.product(product_id) if product_id else None
    if not product or not product["is_active"]:
        await message.answer(f"{ICON_CROSS} Product unavailable.")
        return

    is_manual = product.get("delivery_type") == "manual"
    is_upstream = bool(product.get("upstream_product_id"))
    stock = product.get("stock", 0)
    if not is_manual and not is_upstream and stock > 0 and qty > stock:
        qty = stock
        await message.answer(f"{ICON_WARNING} Quantity adjusted to available stock: {stock}")

    view_text, keyboard = await product_view(services, product, message.from_user.id, quantity=qty, back_target=back_target)
    await message.answer(view_text, reply_markup=keyboard)


@router.message(F.text.func(lambda text: bool(text and text.strip().isdigit() and 1 <= int(text.strip()) <= 1000)))
async def handle_direct_quantity_input(message: Message, state: FSMContext, services: Services):
    """Allows user to simply type a number (e.g. '5' or '25') while viewing a product to change quantity."""
    cur_state = await state.get_state()
    if cur_state is not None:
        return
    data = await state.get_data()
    product_id = data.get("active_product_id") or data.get("product_id")
    if not product_id:
        return
    product = await services.catalog.product(product_id)
    if not product or not product.get("is_active"):
        return
    qty = int(message.text.strip())
    is_manual = product.get("delivery_type") == "manual"
    is_upstream = bool(product.get("upstream_product_id"))
    stock = product.get("stock", 0)
    if not is_manual and not is_upstream and stock > 0 and qty > stock:
        qty = stock
    back_target = data.get(f"back_target_{product_id}")
    await state.update_data(**{f"qty_{product_id}": qty, "active_product_id": product_id})
    view_text, keyboard = await product_view(services, product, message.from_user.id, quantity=qty, back_target=back_target)
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

    product = await services.catalog.product(product_id)
    if not product or not product.get("is_active"):
        with suppress(TelegramBadRequest):
            await query.answer("Product unavailable.", show_alert=True)
        return

    # Scrolling back to an older message shows an older price, and the charge always
    # comes from the database. Rather than quietly take a different amount than the one
    # on screen, show the product again at today's price and let them decide.
    shown_cents = int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else None
    if shown_cents is not None:
        buyer = await services.users.get(query.from_user.id)
        now = unit_price_for(product, buyer) if product else 0.0
        if product and round(now * 100) != shown_cents:
            symbol = await services.settings.get("currency_symbol")
            was = shown_cents / 100
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

    # Check if this product requires customer input (e.g. Gmail for Gemini)
    if product.get("requires_customer_input"):
        lang = await services.users.get_language(query.from_user.id)
        prompt_custom = (product.get("customer_input_prompt") or "").strip()
        if lang == "bn":
            header = "📝 <b>অর্ডার সম্পন্ন করতে তথ্য প্রদান করুন:</b>"
            default_prompt = "দয়া করে আপনার জিমেইল এড্রেস বা প্রয়োজনীয় তথ্য লিখে মেসেজ পাঠান:"
            hint = f"📌 {escape(prompt_custom)}" if prompt_custom else f"📌 {default_prompt}"
            instr = f"{header}\n\n{hint}\n\n<i>নিচে মেসেজ বক্সে লিখে সেন্ড করুন 👇</i>"
            cancel_btn = "❌ বাতিল করুন"
        else:
            header = "📝 <b>Required Information:</b>"
            default_prompt = "Please reply with your Gmail address or account details:"
            hint = f"📌 {escape(prompt_custom)}" if prompt_custom else f"📌 {default_prompt}"
            instr = f"{header}\n\n{hint}\n\n<i>Type your info below and send 👇</i>"
            cancel_btn = "❌ Cancel"

        await state.set_state(ShopQuantityStates.waiting_for_customer_input)
        await state.update_data(
            product_id=product_id,
            quantity=quantity,
            token=token,
            shown_cents=shown_cents,
        )
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=cancel_btn, callback_data=f"prod_{product_id}")
        ]])
        with suppress(TelegramBadRequest):
            await query.answer()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(instr, reply_markup=cancel_kb)
        return

    success, message, order = await services.purchases.purchase(
        query.from_user.id, product_id, quantity=quantity, request_id=f"bot-{token}"
    )
    if not success or not order:
        clean_msg = str(message or "").lstrip("⚠️ ").strip()
        with suppress(TelegramBadRequest):
            await query.answer(f"⚠️ {clean_msg}", show_alert=True)
        return

    lang = await services.users.get_language(query.from_user.id)
    with suppress(TelegramBadRequest):
        toast_success = "ক্রয় সফল হয়েছে!" if lang == "bn" else "Order placed successfully"
        await query.answer(toast_success, show_alert=False)

    if query.message:
        is_waiting = order.get("fulfillment") == "waiting"
        if lang == "bn":
            success_title = "⏳ <b>অর্ডার প্রসেসিং</b>" if is_waiting else "✅ <b>ক্রয় সফল হয়েছে</b>"
            below_text = "" if is_waiting else "<i>আপনার অর্ডার বিবরণ এবং ডেলিভারি নিচে পাঠানো হয়েছে।</i>"
        else:
            success_title = "⏳ <b>Order Processing</b>" if is_waiting else "✅ <b>Order Placed</b>"
            below_text = "" if is_waiting else "<i>Your order details and delivery are below.</i>"
        if not is_waiting:
            services.notifier.in_background(
                _clear_banner(query.message, PURCHASE_BANNER_SECONDS))
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{success_title}\n\n"
                f"<b>{escape(order.get('product_title', 'Product'))}</b>"
                + (f"\n\n{below_text}" if below_text else ""),
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

    prod_id = int(parts[1])
    product = await services.catalog.product(prod_id)
    if not product or not product.get("is_active"):
        with suppress(TelegramBadRequest):
            await query.answer("Product unavailable.", show_alert=True)
        return

    if product.get("requires_customer_input"):
        lang = await services.users.get_language(query.from_user.id)
        prompt_custom = (product.get("customer_input_prompt") or "").strip()
        if lang == "bn":
            header = "📝 <b>অর্ডার সম্পন্ন করতে তথ্য প্রদান করুন:</b>"
            default_prompt = "দয়া করে আপনার জিমেইল এড্রেস বা প্রয়োজনীয় তথ্য লিখে মেসেজ পাঠান:"
            hint = f"📌 {escape(prompt_custom)}" if prompt_custom else f"📌 {default_prompt}"
            instr = f"{header}\n\n{hint}\n\n<i>নিচে মেসেজ বক্সে লিখে সেন্ড করুন 👇</i>"
            cancel_btn = "❌ বাতিল করুন"
        else:
            header = "📝 <b>Required Information:</b>"
            default_prompt = "Please reply with your Gmail address or account details:"
            hint = f"📌 {escape(prompt_custom)}" if prompt_custom else f"📌 {default_prompt}"
            instr = f"{header}\n\n{hint}\n\n<i>Type your info below and send 👇</i>"
            cancel_btn = "❌ Cancel"

        await state.set_state(ShopQuantityStates.waiting_for_customer_input)
        await state.update_data(
            product_id=prod_id,
            quantity=1,
            token=parts[2],
        )
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=cancel_btn, callback_data=f"prod_{prod_id}")
        ]])
        with suppress(TelegramBadRequest):
            await query.answer()
        if query.message:
            with suppress(TelegramBadRequest):
                await query.message.edit_text(instr, reply_markup=cancel_kb)
        return

    success, message, order = await services.purchases.purchase(
        query.from_user.id, prod_id, quantity=1, request_id=f"bot-{parts[2]}"
    )
    if not success or not order:
        clean_msg = str(message or "").lstrip("⚠️ ").strip()
        with suppress(TelegramBadRequest):
            await query.answer(f"⚠️ {clean_msg}", show_alert=True)
        return

    lang = await services.users.get_language(query.from_user.id)
    with suppress(TelegramBadRequest):
        toast_success = "🎉 ক্রয় সফল হয়েছে!" if lang == "bn" else "Order placed"
        await query.answer(toast_success, show_alert=False)

    if query.message:
        is_waiting = order.get("fulfillment") == "waiting"
        if lang == "bn":
            success_title = f"{ICON_TIMER} <b>অর্ডার সম্পন্ন হয়েছে!</b>" if is_waiting else f"{ICON_CHECK} <b>ক্রয় সফল হয়েছে!</b>"
            below_text = "" if is_waiting else "<i>আপনার অর্ডার বিবরণ এবং ডেলিভারি নিচে রয়েছে 👇</i>"
        else:
            success_title = f"{ICON_TIMER} <b>Order placed</b>" if is_waiting else f"{ICON_CHECK} <b>Order placed</b>"
            below_text = "" if is_waiting else "<i>Your order details and delivery are below 👇</i>"
        if not is_waiting:
            services.notifier.in_background(
                _clear_banner(query.message, PURCHASE_BANNER_SECONDS))
        with suppress(TelegramBadRequest):
            await query.message.edit_text(
                f"{success_title}\n\n"
                f"{ICON_ORDERS} <b>{escape(order.get('product_title', 'Product'))}</b>"
                + (f"\n\n{below_text}" if below_text else ""),
                reply_markup=None,
            )


@router.message(ShopQuantityStates.waiting_for_customer_input)
async def process_customer_input_purchase(message: Message, state: FSMContext, services: Services):
    """Processes customer text input (e.g. Gmail for Gemini) to complete the purchase."""
    text = (message.text or "").strip()
    if is_navigation(text):
        await navigate(text, message, state, services)
        return

    lang = await services.users.get_language(message.from_user.id)
    if text.lower() in ("/cancel", "cancel", "বাতিল"):
        await state.clear()
        cancel_msg = "❌ অর্ডার বাতিল করা হয়েছে।" if lang == "bn" else "❌ Order cancelled."
        await message.answer(cancel_msg)
        return

    if len(text) < 2 or len(text) > 300:
        err_msg = "দয়া করে সঠিক তথ্য দিন (২-৩০০ অক্ষরের মধ্যে):" if lang == "bn" else "Please enter valid info (2-300 characters):"
        await message.answer(f"{ICON_WARNING} {err_msg}")
        return

    data = await state.get_data()
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)
    token = data.get("token") or uuid4().hex[:12]
    await state.clear()

    product = await services.catalog.product(product_id) if product_id else None
    if not product or not product.get("is_active"):
        unavail = "❌ এই প্রোডাক্টটি বর্তমানে পাওয়া যাচ্ছে না।" if lang == "bn" else "❌ Product is currently unavailable."
        await message.answer(unavail)
        return

    success, result_message, order = await services.purchases.purchase(
        message.from_user.id,
        product_id,
        quantity=quantity,
        request_id=f"bot-{token}",
        customer_input=text,
    )
    if not success or not order:
        await message.answer(f"⚠️ {result_message}")
        return

    is_waiting = order.get("fulfillment") == "waiting"
    if lang == "bn":
        success_title = "⏳ <b>অর্ডার গ্রহণ করা হয়েছে</b>" if is_waiting else "✅ <b>ক্রয় সফল হয়েছে</b>"
        info_line = f"\n<b>প্রদত্ত তথ্য:</b> <code>{escape(text)}</code>"
        below_text = "<i>এডমিন আপনার প্রদত্ত তথ্য যাচাই করে শীঘ্রই ডেলিভারি করবেন।</i>" if is_waiting else "<i>আপনার অর্ডার বিবরণ নিচে দেওয়া হলো।</i>"
    else:
        success_title = "⏳ <b>Order Received</b>" if is_waiting else "✅ <b>Purchase Successful</b>"
        info_line = f"\n<b>Provided Info:</b> <code>{escape(text)}</code>"
        below_text = "<i>The admin will review your information and deliver shortly.</i>" if is_waiting else "<i>Your order details are below.</i>"

    order_id = order.get("order_id", order.get("id"))
    orders_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="My Orders" if lang != "bn" else "আমার অর্ডার", callback_data=f"vord_{order_id}_1")
    ]])
    await message.answer(
        f"{success_title}\n\n"
        f"<b>{escape(order.get('product_title', 'Product'))}</b>"
        f"{info_line}\n\n"
        f"{below_text}",
        reply_markup=orders_kb,
    )
