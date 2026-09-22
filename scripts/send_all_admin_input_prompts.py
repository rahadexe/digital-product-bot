"""
Send all Optimized & Polished Admin Input Prompts and Action Dialogues to Admin Telegram (6775546602).
Audited from the entire bot:
1. Find Customer Input Prompt + Customer Result Card
2. Set Welcome Message Input Prompt
3. Manual Order Delivery Input Prompt + Delivered Result
4. Find Product Input Prompt + Product Management Card
5. Product Rename Input Prompt
6. Change Price Input Prompt + Confirmation Dialog
7. Add Stock Input Prompt + Restock Success Report
8. Deposit Approve / Reject Confirmation Dialogs
9. Order Refund Confirmation Dialog
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.core.config import get_settings
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_CHECK,
    ICON_CROSS,
    ICON_CROWN,
    ICON_ID,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_PLUS,
    ICON_SHOP,
    ICON_SPARKLES,
    ICON_SPENT,
    ICON_TIMER,
    ICON_WARNING,
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
            "✨ <b>[OPTIMIZED ADMIN INPUTS & ACTIONS]</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "সবগুলো মেসেজ সুন্দরভাবে ছোট, প্রফেশনাল এবং অপ্টিমাইজ করা হয়েছে। নিচে সবগুলো আপডেটেড লাইভ স্যাম্পল পাঠানো হচ্ছে:",
            parse_mode="HTML"
        )
        await asyncio.sleep(1.0)

        # 1. Find Customer Prompt
        msg_1 = (
            "1️⃣ <b>[CUSTOMER LOOKUP: INPUT PROMPT]</b>\n"
            "<i>(ড্যাশবোর্ডে Find Customer চাপলে বা /find দিলে আসে)</i>\n\n"
            f"{ICON_ACCOUNT} <b>Find Customer</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Send customer Telegram ID or @username.\n\n"
            "Send /cancel to abort."
        )
        markup_1 = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_1, reply_markup=markup_1, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 1b. Customer Result Card
        msg_1b = (
            "1️⃣ (খ) <b>[CUSTOMER LOOKUP: RESULT CARD]</b>\n"
            "<i>(কাস্টমার খোঁজার পর বিস্তারিত প্রোফাইল কার্ড)</i>\n\n"
            f"{ICON_ACCOUNT} <b>Rahad Hossain</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>6775546602</code>\n"
            f"{ICON_ACCOUNT} <b>Username:</b> @rahadalways\n"
            f"{ICON_CROWN} <b>Rank:</b> Standard\n"
            f"{ICON_CHECK} <b>Balance:</b> <code>1,250.00 ৳</code>\n"
            f"{ICON_ORDERS} <b>Orders:</b> <code>14</code> · <b>Spent:</b> <code>4,800.00 ৳</code>"
        )
        markup_1b = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ban Customer", callback_data="adm_ban_ask_6775546602", style="danger", icon_custom_emoji_id=Icons.CROSS)],
            [
                InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_1b, reply_markup=markup_1b, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 2. Set Welcome Message
        msg_2 = (
            "2️⃣ <b>[SET WELCOME: INPUT PROMPT]</b>\n"
            "<i>(Set Welcome চাপলে বা /sw দিলে কাস্টম গ্রিটিং টেক্সট চায়)</i>\n\n"
            f"{ICON_NOTE} <b>Welcome Message</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<b>Status:</b> <i>Using default ('Welcome to Premium Haven')</i>\n\n"
            "Send the new greeting message for /start.\n"
            "• Supports HTML formatting (bold, italic, links)\n"
            "• Use <code>{store_name}</code> for auto store name\n\n"
            "Send /cancel to abort."
        )
        markup_2 = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Use Default", callback_data="adm_reset_welcome", icon_custom_emoji_id=Icons.REFRESH),
                InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_2, reply_markup=markup_2, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 3. Manual Order Delivery Prompt
        msg_3 = (
            "3️⃣ <b>[MANUAL DELIVERY: INPUT PROMPT]</b>\n"
            "<i>(ম্যানুয়াল অর্ডারে Deliver Here বাটনে চাপলে ডেলিভারি ডাটা চায়)</i>\n\n"
            f"{ICON_NOTE} <b>Deliver Order #2085</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<b>Product:</b> Netflix Premium 1 Month Ultra HD\n\n"
            "Send delivery items/credentials to send to customer.\n\n"
            "Send /cancel to abort."
        )
        markup_3 = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_3, reply_markup=markup_3, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 3b. Delivery Sent
        msg_3b = (
            "3️⃣ (খ) <b>[MANUAL DELIVERY: SUCCESS REPORT]</b>\n"
            "<i>(ক্রেডেনশিয়াল পাঠিয়ে দিলে তাৎক্ষণিক কনফার্মেশন)</i>\n\n"
            f"{ICON_CHECK} <b>Order #2085 Delivered</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Customer has received their order items in chat."
        )
        markup_3b = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Needs you", callback_data="adm_queue", icon_custom_emoji_id=Icons.TIMER),
                InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_3b, reply_markup=markup_3b, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 4. Product Search Prompt
        msg_4 = (
            "4️⃣ <b>[PRODUCT SEARCH: INPUT PROMPT]</b>\n"
            "<i>(প্রোডাক্ট সার্চ করতে চাইলে)</i>\n\n"
            f"{ICON_SHOP} <b>Find Product</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Send part of the product name to manage or toggle sale status.\n\n"
            "Send /cancel to abort."
        )
        markup_4 = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_4, reply_markup=markup_4, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 4b. Product Card
        msg_4b = (
            "4️⃣ (খ) <b>[PRODUCT MANAGEMENT CARD]</b>\n"
            "<i>(প্রোডাক্ট ওপেন করলে কম্প্যাক্ট ম্যানেজমেন্ট কার্ড)</i>\n\n"
            f"{ICON_SHOP} <b>Spotify Premium 1 Year</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_MONEY} <b>Price:</b> <code>450.00 ৳</code>\n"
            f"{ICON_SHOP} <b>Stock:</b> <code>8</code>\n"
            f"{ICON_ORDERS} <b>Sold:</b> <code>35</code> · <code>15,750.00 ৳</code>\n"
            f"<b>Status:</b> {ICON_CHECK} On sale"
        )
        markup_4b = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Rename", callback_data="adm_prod_name_101", icon_custom_emoji_id=Icons.NOTE),
                InlineKeyboardButton(text="Change Price", callback_data="adm_prod_price_101", icon_custom_emoji_id=Icons.MONEY),
            ],
            [
                InlineKeyboardButton(text="Add Stock", callback_data="adm_stock_101", style="success", icon_custom_emoji_id=Icons.PLUS),
                InlineKeyboardButton(text="Hide Product", callback_data="adm_prod_toggle_101", style="danger", icon_custom_emoji_id=Icons.CROSS),
            ],
            [
                InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_4b, reply_markup=markup_4b, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 5. Rename Product Prompt
        msg_5 = (
            "5️⃣ <b>[RENAME PRODUCT: INPUT PROMPT]</b>\n"
            "<i>(Rename বাটনে চাপলে নতুন নাম চায়)</i>\n\n"
            f"{ICON_NOTE} <b>Rename Product</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Product: <b>Spotify Premium 1 Year</b>\n\n"
            "Send the new product name.\n"
            "<i>Custom emoji in text will be saved as its icon.</i>\n\n"
            "Send /cancel to abort."
        )
        markup_5 = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_5, reply_markup=markup_5, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 6. Change Price Prompt & Confirmation
        msg_6 = (
            "6️⃣ <b>[CHANGE PRICE: INPUT PROMPT]</b>\n"
            "<i>(Change Price বাটনে চাপলে নতুন মূল্য ইনপুট চায়)</i>\n\n"
            f"{ICON_MONEY} <b>Change Price</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Product: <b>Spotify Premium 1 Year</b>\n"
            "Current: <code>450.00 ৳</code>\n\n"
            "Send the new price (e.g. <code>85</code>).\n\n"
            "Send /cancel to abort."
        )
        markup_6 = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_6, reply_markup=markup_6, parse_mode="HTML")
        await asyncio.sleep(1.0)

        msg_6b = (
            "6️⃣ (খ) <b>[CHANGE PRICE: CONFIRMATION DIALOG]</b>\n"
            "<i>(ভুল এড়াতে প্রাইস পরিবর্তন কনফার্মেশন)</i>\n\n"
            f"{ICON_WARNING} <b>Confirm Price Change</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_SHOP} <b>Spotify Premium 1 Year</b>\n"
            "Price: <code>450.00 ৳</code> ➔ <code>399.00 ৳</code>\n\n"
            "<i>Customers will see the new price immediately.</i>"
        )
        markup_6b = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm (399.00 ৳)", callback_data="adm_prod_setp_101_39900", style="danger", icon_custom_emoji_id=Icons.CROSS),
                InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="primary", icon_custom_emoji_id=Icons.BACK),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_6b, reply_markup=markup_6b, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 7. Add Stock Prompt & Success
        msg_7 = (
            "7️⃣ <b>[ADD STOCK: INPUT PROMPT]</b>\n"
            "<i>(স্টক যোগ করার সময় ইনপুট চায়)</i>\n\n"
            f"{ICON_PLUS} <b>Add Stock</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Product: <b>Netflix Premium 1 Month</b>\n\n"
            "Send items to add, one item per line.\n"
            "<i>Duplicates already in stock will be skipped automatically.</i>\n\n"
            "Send /cancel to abort."
        )
        markup_7 = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE)]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_7, reply_markup=markup_7, parse_mode="HTML")
        await asyncio.sleep(1.0)

        msg_7b = (
            "7️⃣ (খ) <b>[ADD STOCK: SUCCESS REPORT]</b>\n"
            "<i>(স্টক সেভ হওয়ার পর সাকসেস রিপোর্ট)</i>\n\n"
            f"{ICON_CHECK} <b>Stock Updated</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Product: <b>Netflix Premium 1 Month</b>\n"
            "Added: <code>+5</code> · Skipped: <code>1</code>\n"
            f"Current Stock: <code>12</code> items"
        )
        markup_7b = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Admin Menu", callback_data="adm_dashboard", icon_custom_emoji_id=Icons.BACK),
                InlineKeyboardButton(text="Close", callback_data="close_menu", style="danger", icon_custom_emoji_id=Icons.CLOSE),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_7b, reply_markup=markup_7b, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 8. Deposit Confirmation Dialogs
        msg_8a = (
            "8️⃣ (ক) <b>[DEPOSIT APPROVE: CONFIRMATION DIALOG]</b>\n"
            "<i>(ডিপোজিটে Approve চাপলে চূড়ান্ত অনুমোদন ডায়ালগ)</i>\n\n"
            f"{ICON_WARNING} <b>Approve Deposit?</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @JohnDoe\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>589234120</code>\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>500.00 ৳</code>\n"
            f"{ICON_NOTE} <b>Trx ID:</b> <code>9H7B3X92A1</code>\n\n"
            "<i>Check payment receipt before confirming.</i>"
        )
        markup_8a = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm (500.00 ৳)", callback_data="adm_dep_do_approve_1048", style="success", icon_custom_emoji_id=Icons.CONFIRM),
                InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="primary", icon_custom_emoji_id=Icons.BACK),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_8a, reply_markup=markup_8a, parse_mode="HTML")
        await asyncio.sleep(1.0)

        msg_8b = (
            "8️⃣ (খ) <b>[DEPOSIT REJECT: CONFIRMATION DIALOG]</b>\n"
            "<i>(ডিপোজিট Reject চাপলে নিশ্চিতকরণ ডায়ালগ)</i>\n\n"
            f"{ICON_WARNING} <b>Reject Deposit?</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @JohnDoe\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>589234120</code>\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>500.00 ৳</code>\n\n"
            "<i>Customer will be notified that payment was unverified.</i>"
        )
        markup_8b = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm Reject", callback_data="adm_dep_do_reject_1048", style="danger", icon_custom_emoji_id=Icons.CROSS),
                InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="primary", icon_custom_emoji_id=Icons.BACK),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_8b, reply_markup=markup_8b, parse_mode="HTML")
        await asyncio.sleep(1.0)

        # 9. Order Refund Confirmation Dialog
        msg_9 = (
            "9️⃣ <b>[ORDER REFUND: CONFIRMATION DIALOG]</b>\n"
            "<i>(অর্ডার রিফান্ড নিশ্চিতকরণ ডায়ালগ)</i>\n\n"
            f"{ICON_WARNING} <b>Refund Order #2085?</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<b>Product:</b> Netflix Premium 1 Month Ultra HD\n"
            f"<b>Amount:</b> <code>350.00 ৳</code>\n\n"
            "<i>Refund will be credited to customer wallet instantly.</i>"
        )
        markup_9 = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm Refund (350.00 ৳)", callback_data="adm_ord_ref_do_2085", style="danger", icon_custom_emoji_id=Icons.CROSS),
                InlineKeyboardButton(text="Cancel", callback_data="adm_cancel", style="primary", icon_custom_emoji_id=Icons.BACK),
            ]
        ])
        await bot.send_message(ADMIN_CHAT_ID, msg_9, reply_markup=markup_9, parse_mode="HTML")

        print("SUCCESS: All optimized admin input prompts and action dialogs sent to Telegram!")

    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
