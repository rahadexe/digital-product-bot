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
from app.services import Services

router = Router(name="help_guide_router")


@router.message(Command("support"))
@router.message(F.text == "🎧 Support")
@router.message(F.text == "💬 Support")
@router.message(F.text == "কাস্টমার সাপোর্ট")
@router.message(F.text == "সাপোর্ট")
@router.message(F.text.casefold() == "support")
@router.callback_query(F.data == "open_support")
async def show_support_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    handle = (await services.settings.get("support_username")).lstrip("@")
    channels = await services.update_channels.channels(active_only=True)
    if handle:
        text = (
            f"{ICON_SUPPORT} <b>Support</b>\n\n"
            f"🇬🇧 For any questions, order assistance, or deposit issues, reach out to our support team.\n\n"
            f"🇧🇩 যেকোনো প্রশ্ন, অর্ডার সহায়তা বা ডিপোজিট সমস্যার জন্য আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন।"
        )
    else:
        text = (
            f"{ICON_SUPPORT} <b>Support</b>\n\n"
            f"🇬🇧 Our support team will be available here shortly.\n\n"
            f"🇧🇩 আমাদের সাপোর্ট টিম শীঘ্রই এখানে উপলব্ধ হবে।"
        )
    await respond(event, text, get_support_keyboard(handle, channels))


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

GUIDE_TEXT_BN = (
    f"{ICON_NOTE} <b>বট ব্যবহারের নিয়মাবলী</b>\n\n"
    f"{ICON_DEPOSIT} <b>১. ব্যালেন্স যোগ করুন</b>\n"
    f"কীবোর্ড থেকে <b>Add Balance</b> চাপুন এবং পেমেন্ট মেথড বেছে নিন। টাকা পাঠিয়ে Transaction ID বা প্রমাণ দিলে স্বয়ংক্রিয়ভাবে ওয়ালেটে ব্যালেন্স যুক্ত হয়ে যাবে।\n\n"
    f"{ICON_SHOP} <b>২. পছন্দের প্রোডাক্ট নির্বাচন</b>\n"
    f"কীবোর্ডের উপরের ক্যাটাগরিগুলো থেকে আপনার পছন্দের প্রোডাক্ট সিলেক্ট করুন। <b>−</b> এবং <b>+</b> বাটন চেপে সংখ্যা নির্ধারণ করুন।\n\n"
    f"{ICON_CHECK} <b>৩. অর্ডার সম্পন্ন করুন</b>\n"
    f"<b>Confirm</b> বাটনে চাপ দিলে ওয়ালেট থেকে ব্যালেন্স কেটে নিয়ে সাথে সাথে চ্যাটে ইনস্ট্যান্ট ডেলিভারি পেয়ে যাবেন (ম্যানুয়াল প্রোডাক্ট হলে অপারেটর শীঘ্রই ডেলিভারি দেবে)।\n\n"
    f"{ICON_ORDERS} <b>৪. কেনা প্রোডাক্ট হিস্টোরি</b>\n"
    f"আপনার কেনা সমস্ত প্রোডাক্ট এবং অর্ডারের বিবরণ <b>My Profile</b> সেকশনে সংরক্ষিত থাকে।\n\n"
    f"{ICON_REFER} <b>রেফার করে আয় করুন</b>\n"
    f"<b>Refer & Earn</b> অপশন থেকে আপনার রেফারেল লিংক শেয়ার করে প্রতি রেফারে আকর্ষণীয় বোনাস ব্যালেন্স আয় করুন।\n\n"
    f"{ICON_SUPPORT} যেকোনো সমস্যায় নিচে <b>Back</b> চেপে সরাসরি সাপোর্টে যোগাযোগ করুন।"
)


def get_guide_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Guide keyboard with language toggle and side-by-side Back + Close buttons."""
    if lang == "bn":
        toggle_btn = InlineKeyboardButton(
            text="English (Global)",
            callback_data="guide_lang_en",
            style="primary",
            icon_custom_emoji_id=Icons.GLOBE,
        )
    else:
        toggle_btn = InlineKeyboardButton(
            text="🇧🇩 বাংলায় দেখুন",
            callback_data="guide_lang_bn",
            style="primary",
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [toggle_btn],
            [
                InlineKeyboardButton(
                    text="Back",
                    callback_data="open_support",
                    style="primary",
                    icon_custom_emoji_id=Icons.BACK,
                ),
                InlineKeyboardButton(
                    text="Close",
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
    keyboard = get_guide_keyboard("en")
    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()
        if event.message:
            with suppress(TelegramBadRequest):
                await send_operator_html(event.message.edit_text, GUIDE_TEXT_EN, reply_markup=keyboard)
    else:
        await send_operator_html(event.answer, GUIDE_TEXT_EN, reply_markup=keyboard)


@router.callback_query(F.data == "guide_lang_bn")
async def show_guide_bn(event: CallbackQuery, state: FSMContext, services: Services):
    """Render Bengali guide."""
    await state.clear()
    keyboard = get_guide_keyboard("bn")
    with suppress(TelegramBadRequest):
        await event.answer()
    if event.message:
        with suppress(TelegramBadRequest):
            await send_operator_html(event.message.edit_text, GUIDE_TEXT_BN, reply_markup=keyboard)

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


