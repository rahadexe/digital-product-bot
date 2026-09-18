from __future__ import annotations

from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.formatting import respond, send_operator_html
from app.bot.icons import ICON_CHANNEL, ICON_SUPPORT
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
            f"{ICON_SUPPORT} <b>Support</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"For any questions, order assistance, or deposit issues, reach out to our support team.\n\n"
            f"যেকোনো প্রশ্ন, অর্ডার সহায়তা বা ডিপোজিট সমস্যার জন্য আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন।"
        )
    else:
        text = (
            f"{ICON_SUPPORT} <b>Support</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Our support team will be available here shortly.\n\n"
            f"আমাদের সাপোর্ট টিম শীঘ্রই এখানে উপলব্ধ হবে।"
        )
    await respond(event, text, get_support_keyboard(handle, channels))


@router.message(F.text == "📚 Guide")
@router.message(F.text.casefold() == "guide")
@router.callback_query(F.data == "open_guide")
async def show_guide_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    guide = await services.settings.get("guide_text")
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎧 Contact Support", callback_data="open_support", style="primary")],
        ]
    )

    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()
        if event.message:
            with suppress(TelegramBadRequest):
                await send_operator_html(event.message.edit_text, guide, reply_markup=keyboard)
    else:
        await send_operator_html(event.answer, guide, reply_markup=keyboard)


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


