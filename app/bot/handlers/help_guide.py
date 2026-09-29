from __future__ import annotations

from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.formatting import respond, send_operator_html
from app.bot.icons import (
    ICON_CHANNEL,
    ICON_CHECK,
    ICON_DEPOSIT,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_REFER,
    ICON_SHOP,
    ICON_SUPPORT,
    Icons,
)
from app.bot.keyboards import get_support_keyboard, get_update_channels_keyboard
from app.core.i18n import t
from app.services import Services

router = Router(name="help_guide_router")


@router.message(Command("support"))
@router.message(F.text.in_({
    "🎧 Support", "💬 Support", "Support", "support",
    "🎧 সাপোর্ট", "সাপোর্ট",
    "🎧 सहायता", "सहायता",
    "🎧 سپورٹ", "سپورٹ",
}))
@router.callback_query(F.data == "open_support")
async def show_support_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    tg_user = event.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    handle = (await services.settings.get("support_username")).lstrip("@")
    channels = await services.update_channels.channels(active_only=True)
    if handle:
        text = (
            f"{t('support_title', lang, icon_support=ICON_SUPPORT)}\n\n"
            f"{t('support_text', lang)}"
        )
    else:
        text = (
            f"{t('support_title', lang, icon_support=ICON_SUPPORT)}\n\n"
            f"{t('support_unavailable', lang)}"
        )
    await respond(event, text, get_support_keyboard(handle, channels, lang=lang))


GUIDE_TEXT_EN = (
    f"{ICON_NOTE} <b>How to use this bot</b>\n\n"
    f"{ICON_DEPOSIT} <b>1. Add money</b>\n"
    f"Tap <b>Add Balance</b> and pick how you want to pay. Send the amount, submit the"
    f" transaction ID, and your wallet is topped up.\n\n"
    f"{ICON_SHOP} <b>2. Pick a product</b>\n"
    f"The buttons at the top of the keyboard are the categories. Tap one, choose a"
    f" product, and set how many you want with <b>−</b> and <b>+</b>.\n\n"
    f"{ICON_CHECK} <b>3. Buy it</b>\n"
    f"Tap <b>Confirm</b>. The price comes out of your wallet and the account details"
    f" arrive here in the chat straight away. Some products are delivered by hand;"
    f" those say so, and they reach you shortly after.\n\n"
    f"{ICON_ORDERS} <b>4. Find them again</b>\n"
    f"Everything you have bought is under <b>My Profile</b>, so you never have to"
    f" search the chat for an old order.\n\n"
    f"{ICON_REFER} <b>Earn while you are here</b>\n"
    f"<b>Refer & Earn</b> gives you your own link. When a friend joins with it, a bonus"
    f" lands in your wallet.\n\n"
    f"{ICON_SUPPORT} Stuck on anything? Tap <b>Back</b> to reach Support."
)


def get_guide_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Guide keyboard with side-by-side Back + Close buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_back", lang),
                    callback_data="open_support",
                    style="primary",
                    icon_custom_emoji_id=Icons.BACK,
                ),
                InlineKeyboardButton(
                    text=t("btn_close", lang),
                    callback_data="close_menu",
                    style="danger",
                    icon_custom_emoji_id=Icons.CLOSE,
                ),
            ],
        ]
    )


@router.callback_query(F.data == "open_guide")
@router.callback_query(F.data == "guide_lang_en")
async def show_guide_en(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Render English guide."""
    await state.clear()
    tg_user = event.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    keyboard = get_guide_keyboard(lang=lang)
    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()
        if event.message:
            with suppress(TelegramBadRequest):
                await send_operator_html(event.message.edit_text, GUIDE_TEXT_EN, reply_markup=keyboard)
    else:
        await send_operator_html(event.answer, GUIDE_TEXT_EN, reply_markup=keyboard)

@router.message(Command("channel"))
@router.message(Command("updates"))
@router.message(F.text == "📢 Channel")
@router.message(F.text == "📢 Updates")
@router.message(F.text == "📢 Update Channel")
@router.message(F.text.casefold() == "channel")
@router.message(F.text.casefold() == "updates")
@router.callback_query(F.data == "open_channel")
async def show_channel_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    channels = await services.update_channels.channels()
    if channels:
        text = (
            f"{ICON_CHANNEL} <b>Our Channels</b>\n\n"
            "Stay updated with new products, restocks, and exclusive deals below 👇"
        )
        keyboard = get_update_channels_keyboard(channels)
    else:
        text = f"{ICON_CHANNEL} <b>Our Channels</b>\n\nNo official channels added yet."
        keyboard = None
    await respond(event, text, keyboard)


@router.message(F.entities.func(lambda entities: any(getattr(e, "type", None) == "custom_emoji" for e in entities or [])))
async def detect_custom_emoji(message: Message, services: Services):
    """When an admin sends custom emojis, extract and return their IDs for easy copying."""
    admin_ids = await services.settings.admin_chat_ids()
    if not message.from_user or message.from_user.id not in admin_ids:
        return

    found_ids: list[str] = []
    for e in message.entities or []:
        if getattr(e, "type", None) == "custom_emoji" and getattr(e, "custom_emoji_id", None):
            found_ids.append(str(e.custom_emoji_id))

    if found_ids:
        unique_ids = list(dict.fromkeys(found_ids))
        items = "\n".join(f"• <code>{eid}</code>" for eid in unique_ids)
        await message.reply(
            f"💎 <b>Custom Emoji ID Detected:</b>\n\n"
            f"{items}\n\n"
            f"<i>💡 Copy this ID and paste it into the Console product form to use as a 3D icon!</i>",
            parse_mode="HTML",
        )


