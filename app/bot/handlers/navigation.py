"""Menu buttons and commands sent while the bot is waiting for typed text (an amount or a transaction ID)."""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.icons import ICON_CROSS
from app.services import Services

logger = logging.getLogger("app.bot.navigation")

router = Router(name="navigation_router")


NAVIGATION_TEXTS = {
    "Back": "cancel",
    "back": "cancel",
    "Cancel": "cancel",
    "cancel": "cancel",
    "❌ Cancel": "cancel",
    "🛍 Shop": "other_products",
    "Shop": "other_products",
    "💰 Balance": "deposit",
    "Balance": "deposit",
    "Add Balance": "deposit",
    "💰 Add Balance": "deposit",
    "📦 Orders": "orders",
    "Orders": "orders",
    "🎁 Referral": "referral",
    "Referral": "referral",
    "💬 Support": "support",
    "Support": "support",
    "Search": "search",
    "🔍 Search": "search",
    "🛡 Admin Panel": "admin",
    "Admin Panel": "admin",
}

COMMAND_ACTIONS = {
    "/start": "start",
    "/api": "api",
    "/reseller": "reseller",
}


def _norm(t: str) -> str:
    return t.replace("\ufe0f", "").strip()


def _strip_emojis(text: str) -> str:
    return re.sub(
        r"[\U00010000-\U0010FFFF\u2600-\u27BF\u2300-\u23FF\u2B50\u200D\uFE0E\uFE0F]+",
        "",
        text,
    ).strip()


def is_navigation(text: str) -> bool:
    if not text:
        return False
    clean = text.strip()
    norm = _norm(clean)
    stripped = _strip_emojis(clean)
    if clean.startswith("/"):
        command = clean.split()[0].split("@")[0].casefold()
        return command in COMMAND_ACTIONS
    return (
        clean in NAVIGATION_TEXTS
        or clean.upper() in NAVIGATION_TEXTS
        or norm in NAVIGATION_TEXTS
        or norm.upper() in NAVIGATION_TEXTS
        or stripped in NAVIGATION_TEXTS
        or stripped.upper() in NAVIGATION_TEXTS
    )

async def navigate(text: str, message: Message, state: FSMContext, services: Services) -> None:
    """Run a current menu action or one of the three supported customer commands."""
    from app.bot.handlers import admin, deposit, help_guide, profile, search, shop, start

    clean = (text or "").strip()
    command = clean.split()[0].split("@")[0].casefold() if clean.startswith("/") else ""
    command_action = COMMAND_ACTIONS.get(command)
    if clean.startswith("/") and command_action is None:
        return

    current_state = await state.get_state()
    if clean in {"🔙 Back", "Back", "Cancel", "❌ Cancel", "back", "cancel"}:
        if current_state and ("DepositStates" in str(current_state) or "deposit" in str(current_state).lower() or "waiting_for_" in str(current_state)):
            await state.clear()
            await deposit.show_deposit_methods(message, state, services)
            return

    await state.clear()
    norm = _norm(clean)
    stripped = _strip_emojis(clean)
    action = (
        NAVIGATION_TEXTS.get(clean)
        or NAVIGATION_TEXTS.get(clean.upper())
        or NAVIGATION_TEXTS.get(norm)
        or NAVIGATION_TEXTS.get(norm.upper())
        or NAVIGATION_TEXTS.get(stripped)
        or NAVIGATION_TEXTS.get(stripped.upper())
        or command_action
    )
    if action == "cancel":
        await message.answer(f"{ICON_CROSS} Current operation cancelled.")
        return
    if action == "start":
        await start.render_main_dashboard(message, services, message.from_user.id)
        return

    handlers = {
        "admin": "admin.cmd_admin_help",
        "api": "profile.show_api_hub",
        "reseller": "profile.show_reseller_hub",
        "other_products": "shop.show_other_products_hub",
        "referral": "profile.show_referral_info",
        "deposit": "deposit.show_deposit_methods",
        "orders": "profile.show_order_history",
        "support": "help_guide.show_support_info",
        "search": "search.prompt_search",
    }
    modules = {"admin": admin, "shop": shop, "profile": profile, "deposit": deposit,
               "help_guide": help_guide, "search": search, "start": start}
    target = handlers.get(action)
    if target:
        module_name, _, func_name = target.partition(".")
        handler = getattr(modules[module_name], func_name, None)
        if handler is not None:
            await handler(message, state, services)
            return
        logger.error("Navigation target %s no longer exists", target)

    matched = await shop.CategoryTextFilter()(message, services)
    if matched:
        await shop.show_category_or_validity(
            message, state, services, category=matched["category"], back_target="back_to_main"
        )
        return

    await start.render_main_dashboard(message, services, message.from_user.id)

@router.message(F.text.func(is_navigation))
async def handle_navigation_message(message: Message, state: FSMContext, services: Services):
    text = (message.text or "").strip()
    await navigate(text, message, state, services)
