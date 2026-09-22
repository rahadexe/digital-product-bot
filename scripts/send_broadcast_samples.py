"""
Send all Broadcast lifecycle and reply message samples to Admin Telegram (6775546602).
Includes:
1. Broadcast Input Prompt
2. Broadcast Preview & Confirmation (with Send Now & Cancel buttons)
3. Broadcast Queued (with BC Status & Admin Menu buttons)
4. Broadcast In Progress Status (with Refresh & Admin Menu buttons)
5. Broadcast Completed Status (with Refresh & Admin Menu buttons)
6. Broadcast Cancelled notification
7. Customer View (what customers receive)
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.core.config import get_settings
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_CHANNEL,
    ICON_CHECK,
    ICON_CROSS,
    ICON_DEPOSIT,
    ICON_ID,
    ICON_NOTE,
    ICON_SHOP,
    ICON_TIMER,
    Icons,
)

ADMIN_CHAT_ID = 6775546602

async def main():
    cfg = get_settings()
    bot = Bot(cfg.bot_token)

    try:
        # Header banner
        await bot.send_message(
            ADMIN_CHAT_ID,
            "📢 <b>[TELEGRAM BROADCAST SAMPLES]</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "নিচে ব্রডকাস্টের শুরু থেকে শেষ পর্যন্ত যত ধরনের রিপ্লাই মেসেজ ও অ্যাকশন বাটন আসে, সবগুলোর লাইভ ডেমো পাঠানো হচ্ছে:",
            parse_mode="HTML"
        )
        await asyncio.sleep(1)

        # 1. Input Prompt
        msg_1 = (
            f"1️⃣ <b>[STAGE 1: INPUT PROMPT]</b>\n"
            f"<i>(/bc কমান্ড দিলে বা ড্যাশবোর্ডে Broadcast বাটনে চাপলে আসে)</i>\n\n"
            f"{ICON_NOTE} <b>Send Broadcast Message</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Type or forward the message you want to broadcast.\n"
            f"<i>HTML formatting (bold, italic, links) is supported.</i>\n\n"
            f"Send /cancel to abort."
        )
        markup_1 = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Cancel", callback_data="bc_cancel", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_1, reply_markup=markup_1, parse_mode="HTML")
        await asyncio.sleep(1)

        # 2. Preview & Confirmation
        msg_2 = (
            f"2️⃣ <b>[STAGE 2: PREVIEW & CONFIRMATION]</b>\n"
            f"<i>(মেসেজ লিখে পাঠানোর সাথে সাথে অ্যাডমিনকে প্রিভিউ দেখায়)</i>\n\n"
            f"{ICON_CHANNEL} <b>Broadcast Preview</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔥 <b>Special Flash Sale Alert!</b>\n\n"
            f"Get up to <b>20% bonus balance</b> on all bKash and Nagad deposits today until midnight!\n\n"
            f"• Fast Automated Delivery\n"
            f"• 24/7 Dedicated Support\n\n"
            f"<i>Use coupon code: FLASH20</i>\n\n"
            f"{ICON_ACCOUNT} Recipients: <b>154</b>"
        )
        markup_2 = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Send Now", callback_data="bc_confirm", style="success", icon_custom_emoji_id=Icons.ROCKET),
                InlineKeyboardButton(text="Cancel", callback_data="bc_cancel", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_2, reply_markup=markup_2, parse_mode="HTML")
        await asyncio.sleep(1)

        # 3. Queued / Sending initiated
        msg_3 = (
            f"3️⃣ <b>[STAGE 3: BROADCAST QUEUED]</b>\n"
            f"<i>(Send Now বাটনে চাপলে মেসেজটি সাথে সাথে এই স্ট্যাটাসে রূপান্তর হয়)</i>\n\n"
            f"{ICON_CHECK} <b>Broadcast Queued</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ID} Job ID: <code>#42</code>\n"
            f"{ICON_ACCOUNT} Recipients: <b>154</b>\n\n"
            f"<i>Sending in the background. Tap below to track progress:</i>"
        )
        markup_3 = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="BC Status", callback_data="adm_view_bcstatus", icon_custom_emoji_id=Icons.TIMER),
                InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
            ],
            [
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ],
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_3, reply_markup=markup_3, parse_mode="HTML")
        await asyncio.sleep(1)

        # 4. Status (In Progress)
        msg_4 = (
            f"4️⃣ <b>[STAGE 4: PROGRESS MONITORING]</b>\n"
            f"<i>(ডেলিভারি চলার সময় BC Status চাপলে বা /bcstatus দিলে দেখায়)</i>\n\n"
            f"{ICON_TIMER} <b>Broadcast #42 · Sending</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Special Flash Sale Alert! Get up to 20% bonus balance...</i>\n\n"
            f"{ICON_ACCOUNT} Total: <b>154</b>\n"
            f"{ICON_CHECK} Delivered: <b>89</b>\n"
            f"{ICON_CROSS} Failed: <b>2</b>\n"
            f"{ICON_TIMER} Pending: <b>63</b>"
        )
        markup_4 = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Refresh", callback_data="adm_view_bcstatus", icon_custom_emoji_id=Icons.REFRESH),
                InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
            ],
            [
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ],
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_4, reply_markup=markup_4, parse_mode="HTML")
        await asyncio.sleep(1)

        # 5. Status (Completed)
        msg_5 = (
            f"5️⃣ <b>[STAGE 5: BROADCAST COMPLETED]</b>\n"
            f"<i>(সব গ্রাহকের কাছে পাঠানো শেষ হলে যা দেখায়)</i>\n\n"
            f"{ICON_CHECK} <b>Broadcast #42 · Completed</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Special Flash Sale Alert! Get up to 20% bonus balance...</i>\n\n"
            f"{ICON_ACCOUNT} Total: <b>154</b>\n"
            f"{ICON_CHECK} Delivered: <b>151</b>\n"
            f"{ICON_CROSS} Failed: <b>3</b>\n"
            f"{ICON_TIMER} Pending: <b>0</b>"
        )
        markup_5 = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Refresh", callback_data="adm_view_bcstatus", icon_custom_emoji_id=Icons.REFRESH),
                InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
            ],
            [
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ],
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_5, reply_markup=markup_5, parse_mode="HTML")
        await asyncio.sleep(1)

        # 6. Cancelled
        msg_6 = (
            f"6️⃣ <b>[STAGE 6: CANCELLED]</b>\n"
            f"<i>(প্রিভিউতে Cancel চাপলে বা /cancel দিলে দেখায়)</i>\n\n"
            f"{ICON_CROSS} <b>Broadcast cancelled.</b>"
        )
        await bot.send_message(ADMIN_CHAT_ID, msg_6, parse_mode="HTML")
        await asyncio.sleep(1)

        # 7. Customer View
        msg_7 = (
            f"7️⃣ <b>[STAGE 7: CUSTOMER INBOX VIEW]</b>\n"
            f"<i>(সাধারণ গ্রাহকরা বটের ইনবক্সে ব্রডকাস্ট মেসেজ যেভাবে দেখতে পায়)</i>\n\n"
            f"📢 <b>Special Flash Sale Alert!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Get up to <b>20% bonus balance</b> on all bKash and Nagad deposits today until midnight!\n\n"
            f"• Fast Automated Delivery\n"
            f"• 24/7 Dedicated Support\n\n"
            f"<i>Use coupon code: FLASH20</i>"
        )
        markup_7 = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Shop Now", callback_data="category_view", icon_custom_emoji_id=Icons.PRODUCTS),
                InlineKeyboardButton(text="Add Balance", callback_data="deposit_start", icon_custom_emoji_id=Icons.DEPOSIT),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_7, reply_markup=markup_7, parse_mode="HTML")

        print("SUCCESS: All 7 broadcast lifecycle samples sent to Telegram!")

    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
