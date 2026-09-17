from __future__ import annotations

from contextlib import suppress
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.formatting import respond, send_operator_html
from app.bot.keyboards import get_support_keyboard, get_update_channels_keyboard
from app.services import Services

router = Router(name="help_guide_router")


@router.message(Command("support"))
@router.message(F.text == "🎧 Support")
@router.message(F.text == "💬 Support")
@router.message(F.text == "কাস্টমার সাপোর্ট")
@router.message(F.text.casefold() == "support")
@router.callback_query(F.data == "open_support")
async def show_support_info(event: Message | CallbackQuery, state: FSMContext, services: Services):
    await state.clear()
    handle = (await services.settings.get("support_username")).lstrip("@")
    if handle:
        text = (
            "🎧 <b>Support</b>\n\n"
            "For any questions, order assistance, or deposit issues, reach out to our support team."
        )
    else:
        text = "🎧 <b>Support</b>\n\nOur support team will be available here shortly."
    await respond(event, text, get_support_keyboard(handle))


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
            "📢 <b>Our Channels</b>\n\n"
            "Stay updated with new products, restocks, and exclusive deals below 👇"
        )
        keyboard = get_update_channels_keyboard(channels)
    else:
        text = "📢 <b>Our Channels</b>\n\nNo official channels added yet."
        keyboard = None
    await respond(event, text, keyboard)

