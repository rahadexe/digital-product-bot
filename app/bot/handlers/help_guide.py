from __future__ import annotations

from contextlib import suppress
from typing import Any

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
    ICON_SHOP,
    ICON_SUPPORT,
    Icons,
)
from app.bot.keyboards import (
    get_help_faq_keyboard,
    get_update_channels_keyboard,
)
from app.core.i18n import t
from app.services import Services

router = Router(name="help_guide_router")


FAQ_ITEMS: dict[str, dict[str, Any]] = {
    "buy": {
        "answer": {
            "en": (
                "<b>How to buy</b>\n\n"
                "1. Open Products and choose a category.\n"
                "2. Choose a product, select validity if shown, and set the quantity.\n"
                "3. Check the total, then select Buy to pay from your wallet balance.\n"
                "4. If your balance is low, add funds anytime from Wallet."
            ),
        },
    },
    "deposit": {
        "answer": {
            "en": (
                "<b>Top up your wallet</b>\n\n"
                "1. Open Wallet and choose a payment method.\n"
                "2. Pay the displayed account, then tap Payment Done.\n"
                "3. Reply with your TrxID or Binance Order ID, then the amount sent.\n"
                "Hosted checkout has its own payment steps.\n\n"
                "Balance is added after verification. Open History for status."
            ),
        },
    },
    "delivery": {
        "answer": {
            "en": (
                "<b>How delivery works</b>\n\n"
                "• Automatic items: Credentials/keys are delivered instantly in this chat right after purchase.\n"
                "• Manual items: The bot confirms the order is being prepared, and the delivery arrives in a separate message when ready.\n"
                "• Order history: Open Orders to find past orders and delivered details."
            ),
        },
    },
    "referral": {
        "answer": {
            "en": (
                "<b>How referrals work</b>\n\n"
                "Open Refer and share your link.\n"
                "A new friend must start the bot through your link and complete any required channel check.\n\n"
                "When rewards are enabled, you earn once per eligible friend. "
                "Rewards are for eligible friends, not for link clicks. "
                "Successful invites counts rewarded friends."
            ),
        },
    },
}


@router.message(Command("help"))
@router.message(Command("support"))
@router.message(F.text.in_({
    "💬 Help", "Help", "help", "HELP", "💬 HELP",
    "💬 হেল্প", "হেল্প",
    "🎧 Support", "💬 Support", "Support", "support",
    "🎧 SUPPORT", "SUPPORT",
    "🎧 সাপোর্ট", "সাপোর্ট",
}))
@router.callback_query(F.data == "open_help")
@router.callback_query(F.data == "open_support")
async def show_help_faq_hub(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Show the interactive Most common questions FAQ hub with Technical Support & Channel links."""
    await state.clear()
    tg_user = event.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    settings_map = await services.settings.values()
    handle = (settings_map.get("support_username") or "").lstrip("@")
    channels = await services.update_channels.channels(active_only=True)

    text = "Choose a topic."
    kb = get_help_faq_keyboard(support_handle=handle, channels=channels, lang=lang)

    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()
        if event.message:
            with suppress(TelegramBadRequest):
                await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
                return

    if isinstance(event, Message):
        await event.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    await respond(event, text, kb)


show_support_info = show_help_faq_hub


@router.callback_query(F.data.startswith("faq_"))
async def show_faq_answer(query: CallbackQuery, state: FSMContext, services: Services):
    """Show answer or short description for a specific question, support, or channel with a back button."""
    faq_key = query.data.removeprefix("faq_")
    tg_user = query.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    rows: list[list[InlineKeyboardButton]] = []

    if faq_key == "support":
        settings_map = await services.settings.values()
        handle = (settings_map.get("support_username") or "").lstrip("@")
        text = (
            "<b>Support</b>\n\n"
            "Send your order or top-up reference and a short description of the issue.\n\n"
            + (f"Telegram: @{handle}" if handle else "No support contact is configured. Check the update channels.")
        )
        if handle:
            chat_btn_text = "Message support"
            rows.append([InlineKeyboardButton(text=chat_btn_text, url=f"https://t.me/{handle}")])

    elif faq_key == "channel":
        channels = await services.update_channels.channels(active_only=True)
        primary_url = channels[0].get("url") if channels and channels[0].get("url") else None
        text = (
            "<b>Update channel</b>\n\n"
            "Join our official channel for restock alerts, discounts, announcements, and service updates."
        )
        if primary_url:
            join_btn_text = "Join channel"
            rows.append([InlineKeyboardButton(text=join_btn_text, url=primary_url)])

    else:
        item = FAQ_ITEMS.get(faq_key)
        if not item:
            await query.answer("FAQ not found.", show_alert=True)
            return

        text = item["answer"].get(lang, item["answer"]["en"])

        # Check if a video tutorial is configured for this FAQ in settings
        settings_map = await services.settings.values()
        video_url = settings_map.get(f"faq_video_{faq_key}") or settings_map.get(f"faq_video_url_{faq_key}")
        if video_url and str(video_url).strip():
            video_btn_text = "Watch video tutorial"
            rows.append([
                InlineKeyboardButton(
                    text=video_btn_text,
                    url=str(video_url).strip(),
                )
            ])

    # Back button to return to Most common questions list
    back_label = "Back to help"
    rows.append([
        InlineKeyboardButton(
            text=back_label,
            callback_data="open_help",
        )
    ])

    with suppress(TelegramBadRequest):
        await query.answer()
    if query.message:
        with suppress(TelegramBadRequest):
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")


@router.callback_query(F.data == "open_tech_support")
async def handle_tech_support_fallback(query: CallbackQuery, services: Services):
    handle = (await services.settings.get("support_username")).lstrip("@")
    if handle:
        await query.answer(url=f"https://t.me/{handle}")
    else:
        await query.answer("Technical support is offline. Check our channel for updates.", show_alert=True)


@router.message(Command("setvideo"))
@router.message(Command("setfaqvideo"))
async def set_faq_video_command(message: Message, services: Services):
    """Admin command to set or clear a tutorial video URL for any FAQ (e.g. /setvideo buy https://youtu.be/xyz)."""
    admin_ids = await services.settings.admin_chat_ids()
    if not message.from_user or message.from_user.id not in admin_ids:
        return

    parts = (message.text or "").strip().split(maxsplit=2)
    if len(parts) < 2:
        keys_list = ", ".join(FAQ_ITEMS.keys())
        await message.reply(
            f"ℹ️ <b>Usage:</b> <code>/setvideo &lt;faq_id&gt; &lt;url&gt;</code>\n"
            f"<b>Available FAQ IDs:</b> <code>{keys_list}</code>\n\n"
            f"<i>Example:</i> <code>/setvideo buy https://youtu.be/xyz</code>\n"
            f"<i>To remove:</i> <code>/setvideo buy clear</code>",
            parse_mode="HTML",
        )
        return

    faq_key = parts[1].strip().lower()
    if faq_key not in FAQ_ITEMS:
        keys_list = ", ".join(FAQ_ITEMS.keys())
        await message.reply(f"❌ Unknown FAQ ID: <code>{faq_key}</code>\nAllowed: <code>{keys_list}</code>", parse_mode="HTML")
        return

    url = parts[2].strip() if len(parts) > 2 else ""
    if not url or url.lower() in {"clear", "none", "remove", "delete"}:
        await services.settings.set(f"faq_video_{faq_key}", "")
        await message.reply(f"✅ Video tutorial for FAQ <b>{faq_key}</b> cleared.", parse_mode="HTML")
    else:
        await services.settings.set(f"faq_video_{faq_key}", url)
        await message.reply(f"✅ Video tutorial for FAQ <b>{faq_key}</b> set to:\n{url}", parse_mode="HTML")


GUIDE_TEXTS = {
    "en": (
        f"{ICON_NOTE} <b>How to use the bot</b>\n\n"
        f"{ICON_DEPOSIT} <b>1. Add balance</b>\n"
        f"Open Wallet, choose a method, pay, then tap Payment Done. Send the reference and amount.\n\n"
        f"{ICON_SHOP} <b>2. Choose a product</b>\n"
        f"Browse a category and set the quantity.\n\n"
        f"{ICON_CHECK} <b>3. Confirm</b>\n"
        f"Pay from your wallet. Automatic orders arrive here; manual orders follow.\n\n"
        f"{ICON_ORDERS} Open <b>Orders</b> for purchases or <b>Refer</b> for your invite link.\n"
        f"{ICON_SUPPORT} Need help? Open Help below."
    ),
}


def get_guide_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """Guide keyboard with a direct support action."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("btn_support", lang),
                    callback_data="open_support",
                ),
            ],
        ]
    )


@router.callback_query(F.data == "open_guide")
async def show_guide(event: Message | CallbackQuery, state: FSMContext, services: Services):
    """Show a concise guide in English."""
    await state.clear()
    tg_user = event.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    keyboard = get_guide_keyboard(lang=lang)
    if isinstance(event, CallbackQuery):
        with suppress(TelegramBadRequest):
            await event.answer()
        if event.message:
            with suppress(TelegramBadRequest):
                await send_operator_html(event.message.edit_text, GUIDE_TEXTS.get(lang, GUIDE_TEXTS["en"]), reply_markup=keyboard)
    else:
        await send_operator_html(event.answer, GUIDE_TEXTS.get(lang, GUIDE_TEXTS["en"]), reply_markup=keyboard)

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
    tg_user = event.from_user
    lang = await services.users.get_language(tg_user.id) if tg_user else "en"
    if channels:
        text = (
            f"{ICON_CHANNEL} <b>{t('channel_list_title', lang)}</b>\n\n"
            f"{t('channel_list_intro', lang)} 👇"
        )
        keyboard = get_update_channels_keyboard(channels)
    else:
        text = f"{ICON_CHANNEL} <b>{t('channel_list_title', lang)}</b>\n\n{t('channel_list_empty', lang)}"
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
