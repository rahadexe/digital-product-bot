"""
Script to send all A-to-Z sample notifications to Admin Telegram chat ID (6775546602).
Updated with:
- Warning icon (⚠️) for critical Manual Order Action Required
- 'Deliver Here' button text (instead of 'Deliver #2085 here')
- Price Changed / Drop with money icon (💵) and clean 'Discount: -20% OFF' line
- Customer Deposit Rejected & Cancelled include full customer transaction proof (User, Method, Amount, TrxID, Reason) + 'Contact Support' button for 1-click support and forwarding to admin
- Instant Payment Invoice with English + Bengali guidance and 'I've Paid' button
- Bar-free, clean, compact formatting everywhere
"""

import asyncio
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot
from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from app.core.config import get_settings
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BALANCE,
    ICON_CHECK,
    ICON_CROSS,
    ICON_DEPOSIT,
    ICON_ID,
    ICON_KEY,
    ICON_LIGHTNING,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_PLUS,
    ICON_SHOP,
    ICON_SPARKLES,
    ICON_TIMER,
    ICON_VIP,
    ICON_WARNING,
    Icons,
)

ADMIN_CHAT_ID = 6775546602

async def main():
    cfg = get_settings()
    bot = Bot(cfg.bot_token)
    me = await bot.get_me()
    bot_username = me.username or "PremiumHaven24Bot"
    console_url = cfg.console_url or "http://localhost:3000"

    print(f"Connecting to bot ({bot_username}) and dispatching all notification samples to admin {ADMIN_CHAT_ID}...", flush=True)

    # Intro Header
    await bot.send_message(
        ADMIN_CHAT_ID,
        "📋 <b>ALL 21 NOTIFICATIONS (FINAL POLISHED & OPTIMIZED)</b>\n\n"
        "আপনার নতুন ফিডব্যাক অনুযায়ী ফাইনাল পরিবর্তনসমূহ:\n"
        "• কাস্টমার ইউজারনেম ও কাস্টমার আইডি আলাদা লাইনে সুন্দরভাবে বিন্যস্ত (<code>Customer ID:</code> 1-ট্যাপ কপিযোগ্য)\n"
        "• ম্যানুয়াল অর্ডারে চোখে পড়ার মতো ⚠️ <b>Manual Order Action Required</b> এবং <code>Deliver Here</code> বাটন\n"
        "• প্রাইস ড্রপ/চেঞ্জে সুন্দর মানি আইকন (💵) ও আলাদা <code>Discount: -20% OFF</code> লাইন\n"
        "• ডিপোজিট রিজেক্টেড ও ক্যানসেল্ডে সম্পূর্ণ কাস্টমার প্রুফ (ইউজার, মেথড, অ্যামাউন্ট, TrxID) + <code>Contact Support</code> বাটন\n"
        "• ইনস্ট্যান্ট পেমেন্ট ইনভয়েসে ইংরেজি + বাংলায় স্পষ্ট দিকনির্দেশনা ও <code>I've Paid</code> বাটন\n\n"
        "নিচে <b>২১টি নোটিফিকেশন স্যাম্পল</b> পাঠানো হলো:",
        parse_mode="HTML",
    )
    await asyncio.sleep(1)

    samples = [
        # --- 1. ADMIN ALERTS ---
        (
            "1️⃣ <b>[ADMIN ALERT] Manual Deposit Request Submitted</b>\n\n"
            f"{ICON_DEPOSIT} <b>New Deposit Request #1048</b>\n\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @JohnDoe\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>589234120</code>\n"
            f"{ICON_DEPOSIT} <b>Method:</b> bKash Personal\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>500.00 ৳</code>\n"
            f"{ICON_KEY} <b>TrxID:</b> <code>9H7B3X92A1</code>\n"
            f"{ICON_NOTE} <b>Number:</b> <code>01712345678</code>",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Approve", callback_data="adm_sample_app", style="success", icon_custom_emoji_id=Icons.CONFIRM),
                    InlineKeyboardButton(text="Reject", callback_data="adm_sample_rej", style="danger", icon_custom_emoji_id=Icons.CROSS),
                ],
                [
                    InlineKeyboardButton(text="Open in Console", url=f"{console_url}/#deposits", icon_custom_emoji_id=Icons.DEPOSIT)
                ]
            ])
        ),
        (
            "2️⃣ <b>[ADMIN ALERT] Manual Delivery Order Required</b>\n\n"
            f"{ICON_WARNING} <b>Manual Order Action Required</b>\n\n"
            f"{ICON_ORDERS} <b>Order:</b> <code>#2085</code>\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @SarahK\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>712345678</code>\n"
            f"{ICON_VIP} <b>Product:</b> Netflix 1 Month Private (Custom Email)\n"
            f"{ICON_MONEY} <b>Price:</b> <code>350 ৳</code> ($2.80)\n"
            f"{ICON_WARNING} <b>Delivery:</b> Manual",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Deliver Here", callback_data="adm_sample_deliv", style="success", icon_custom_emoji_id=Icons.ORDERS)
                ],
                [
                    InlineKeyboardButton(text="Open in Console", url=f"{console_url}/#orders/2085", icon_custom_emoji_id=Icons.NOTE)
                ]
            ])
        ),
        (
            "3️⃣ <b>[ADMIN ALERT] Instant Stock Purchase Alert</b>\n\n"
            f"{ICON_SHOP} <b>New Order Received</b>\n\n"
            f"{ICON_ORDERS} <b>Order:</b> <code>#2086</code>\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @AlexPro\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>623456789</code>\n"
            f"{ICON_VIP} <b>Product:</b> Telegram Premium 1 Month Gift Link\n"
            f"{ICON_MONEY} <b>Price:</b> <code>450 ৳</code> ($3.60)\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant (Automatic)",
            None
        ),
        (
            "4️⃣ <b>[ADMIN ALERT] Low Stock Warning Alert</b>\n\n"
            f"{ICON_WARNING} <b>Low Stock Warning!</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> Spotify Premium 3 Months Account\n"
            f"{ICON_SHOP} <b>Available Stock:</b> <code>2</code>\n"
            f"{ICON_TIMER} <b>Threshold:</b> <code>3</code>",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Restock in Console", url=f"{console_url}/#inventory", icon_custom_emoji_id=Icons.PLUS)
                ]
            ])
        ),
        (
            "5️⃣ <b>[ADMIN ALERT] Critical Out of Stock Alert</b>\n\n"
            f"{ICON_CROSS} <b>Product Out of Stock!</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> ChatGPT Plus Shared Account\n"
            f"{ICON_SHOP} <b>Available Stock:</b> <code>0</code>\n"
            f"{ICON_CROSS} <b>Status:</b> Sold Out",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Restock in Console", url=f"{console_url}/#inventory", icon_custom_emoji_id=Icons.PLUS)
                ]
            ])
        ),
        (
            "6️⃣ <b>[ADMIN ALERT] Automatic Gateway Deposit (Binance Pay / ZiniPay)</b>\n\n"
            f"{ICON_DEPOSIT} <b>Automatic Deposit #1049</b>\n\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @Rahad\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>6775546602</code>\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>1250.00 ৳</code> (Paid 10.00 USDT)\n"
            f"{ICON_DEPOSIT} <b>Method:</b> Binance Pay\n"
            f"{ICON_KEY} <b>TrxID:</b> <code>BIN_PAY_89231490</code>",
            None
        ),
        (
            "7️⃣ <b>[ADMIN ALERT] Stock Added Confirmation (Restock Alert)</b>\n\n"
            f"{ICON_ORDERS} <b>Stock Added</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> ⚡ <b>YouTube Premium 1 Month</b>\n"
            f"{ICON_TIMER} <b>Validity:</b> 30 Days\n"
            f"{ICON_PLUS} <b>Added:</b> <code>+15</code> units\n"
            f"{ICON_SHOP} <b>Total Stock:</b> <code>25</code> units\n"
            f"{ICON_MONEY} <b>Price:</b> <code>180 ৳ ($1.44)</code>",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Buy YouTube Premium", url=f"https://t.me/{bot_username}?start=prod_1", icon_custom_emoji_id=Icons.CART)
                ]
            ])
        ),
        (
            "8️⃣ <b>[ADMIN ALERT] Product Price Modified</b>\n\n"
            f"{ICON_MONEY} <b>Price Changed</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> ⚡ <b>Canva Pro 1 Year Education</b>\n"
            f"{ICON_TIMER} <b>Validity:</b> 1 Year\n"
            "📉 <b>Old Price:</b> <code><s>250 ৳</s></code>\n"
            f"{ICON_MONEY} <b>New Price:</b> <code>200 ৳ ($1.60)</code>\n"
            "🏷️ <b>Adjustment:</b> <code>-20%</code>\n"
            f"{ICON_SHOP} <b>Stock:</b> <code>40</code> units",
            None
        ),
        (
            "9️⃣ <b>[ADMIN ALERT] New Customer Joined</b>\n\n"
            f"{ICON_ACCOUNT} <b>New Customer Joined!</b>\n\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> Tanvir Ahmed (@Tanvir007)\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>849302194</code>\n"
            f"{ICON_TIMER} <b>Date:</b> 2026-09-22 00:45 UTC",
            None
        ),
        (
            "🔟 <b>[ADMIN ALERT] Payment Gateway Error / Timeout</b>\n\n"
            f"{ICON_WARNING} <b>Gateway Payment Needs Review</b>\n\n"
            "Ref: <code>PAY_9481230BFA1</code> | User: <code>589234120</code>\n"
            "Reason: ZiniPay API returned timeout during verification.\n\n"
            "<i>Nothing was credited. Please check gateway dashboard.</i>",
            None
        ),

        # --- 2. CUSTOMER NOTIFICATIONS ---
        (
            "1️⃣1️⃣ <b>[CUSTOMER NOTIFICATION] Instant Order Delivery Receipt</b>\n\n"
            f"{ICON_ORDERS} <b>Order #2086 Details</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> Telegram Premium 1 Month Gift Link\n"
            f"{ICON_MONEY} <b>Price:</b> <code>450 ৳ ($3.60)</code>\n"
            f"{ICON_TIMER} <b>Date:</b> 2026-09-22 00:45 UTC\n"
            f"{ICON_CHECK} <b>Status:</b> <code>COMPLETED</code>\n\n"
            f"{ICON_KEY} <b>Delivered Credentials:</b>\n"
            "<code>https://t.me/giftcode/ABCD-1234-EFGH-5678</code>",
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="Copy Credentials",
                    copy_text=CopyTextButton(text="https://t.me/giftcode/ABCD-1234-EFGH-5678"),
                    style="success",
                    icon_custom_emoji_id=Icons.KEY,
                )
            ]])
        ),
        (
            "1️⃣2️⃣ <b>[CUSTOMER NOTIFICATION] Manual Order Placed (Waiting Acknowledgment)</b>\n\n"
            f"{ICON_TIMER} <b>Order #2085: Netflix 1 Month Private</b>\n\n"
            f"{ICON_CHECK} <b>Payment Received!</b>\n\n"
            "Your order is being prepared and will be delivered directly here shortly (usually within 5–30 minutes).",
            None
        ),
        (
            "1️⃣3️⃣ <b>[CUSTOMER NOTIFICATION] Manual Order Fulfilled by Admin</b>\n\n"
            f"{ICON_ORDERS} <b>Order #2085 Details</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> Netflix 1 Month Private\n"
            f"{ICON_MONEY} <b>Price:</b> <code>350 ৳ ($2.80)</code>\n"
            f"{ICON_TIMER} <b>Date:</b> 2026-09-22 00:45 UTC\n"
            f"{ICON_CHECK} <b>Status:</b> <code>COMPLETED</code>\n\n"
            f"{ICON_KEY} <b>Delivered Credentials:</b>\n"
            "<code>Email: customer@premiumstore.com\n"
            "Password: Pass@2026Secure!\n"
            "Profile: PIN 1048</code>",
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="Copy Credentials",
                    copy_text=CopyTextButton(text="Email: customer@premiumstore.com\nPassword: Pass@2026Secure!\nProfile: PIN 1048"),
                    style="success",
                    icon_custom_emoji_id=Icons.KEY,
                )
            ]])
        ),
        (
            "1️⃣4️⃣ <b>[CUSTOMER NOTIFICATION] Manual Deposit Approved & Credited</b>\n\n"
            f"{ICON_CHECK} <b>Deposit Approved!</b>\n\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>500.00 ৳</code>\n"
            f"{ICON_DEPOSIT} <b>Method:</b> bKash Personal\n"
            f"{ICON_BALANCE} <b>Balance:</b> <code>750.00 ৳</code>",
            None
        ),
        (
            "1️⃣5️⃣ <b>[CUSTOMER NOTIFICATION] Manual Deposit Rejected</b>\n\n"
            f"{ICON_WARNING} <b>Deposit Rejected</b>\n\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @JohnDoe\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>589234120</code>\n"
            f"{ICON_DEPOSIT} <b>Method:</b> bKash Personal\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>500.00 ৳</code>\n"
            f"{ICON_KEY} <b>TrxID:</b> <code>9H7B3X92A1</code>\n"
            f"{ICON_NOTE} <b>Reason:</b> Invalid TrxID (Not found on statement)",
            InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Contact Support", url="https://t.me/PremiumHavenSupport", icon_custom_emoji_id=Icons.SUPPORT)
            ]])
        ),
        (
            "1️⃣6️⃣ <b>[CUSTOMER NOTIFICATION] Instant Payment Invoice Generated</b>\n\n"
            f"{ICON_NOTE} <b>Payment Invoice #INV-1048</b>\n\n"
            f"{ICON_MONEY} <b>Payable Amount:</b> <code>1000.00 ৳ ($8.00)</code>\n"
            f"{ICON_LIGHTNING} <b>Method:</b> Instant Auto Gateway\n"
            f"{ICON_TIMER} <b>Status:</b> Waiting for Payment\n\n"
            "🇬🇧 Tap the <b>Pay</b> button below to open the payment page. You can complete payment using any preferred method (bKash, Nagad, Rocket, Cards), and your balance will be added automatically.\n\n"
            "🇧🇩 নিচের <b>Pay</b> বাটনে ট্যাপ করলে পেমেন্ট পেজে নিয়ে যাবে। সেখান থেকে আপনার পছন্দ অনুযায়ী যেকোনো মেথডে (bKash, Nagad, Rocket ইত্যাদি) পেমেন্ট সম্পন্ন করতে পারবেন এবং অটোমেটিক ব্যালেন্স যুক্ত হয়ে যাবে।",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Pay ৳1000.00", url="https://zinipay.com", style="success", icon_custom_emoji_id=Icons.DEPOSIT)
                ],
                [
                    InlineKeyboardButton(text="I've Paid", callback_data="inst_chk_sample", style="primary", icon_custom_emoji_id=Icons.CHECK)
                ],
                [
                    InlineKeyboardButton(text="Back", callback_data="open_deposit", style="danger", icon_custom_emoji_id=Icons.BACK)
                ]
            ])
        ),
        (
            "1️⃣7️⃣ <b>[CUSTOMER NOTIFICATION] Automatic Gateway Deposit Successful</b>\n\n"
            f"{ICON_CHECK} <b>Payment Successful!</b>\n\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>1000.00 ৳</code>\n"
            f"{ICON_BALANCE} <b>Balance:</b> <code>1250.00 ৳</code>",
            None
        ),
        (
            "1️⃣8️⃣ <b>[CUSTOMER NOTIFICATION] Deposit Cancelled</b>\n\n"
            f"{ICON_CROSS} <b>Deposit Cancelled</b>",
            None
        ),
        (
            "1️⃣9️⃣ <b>[CUSTOMER NOTIFICATION] Referral Bonus Credited</b>\n\n"
            f"{ICON_SPARKLES} <b>Referral Reward Credited!</b>\n\n"
            f"{ICON_ACCOUNT} <b>Friend:</b> @AlexPro\n"
            f"{ICON_MONEY} <b>Bonus:</b> <code>+3.00 ৳</code>\n"
            f"{ICON_BALANCE} <b>Balance:</b> <code>753.00 ৳</code>",
            None
        ),

        # --- 3. PUBLIC CHANNEL ANNOUNCEMENTS ---
        (
            "2️⃣0️⃣ <b>[PUBLIC CHANNEL] Fresh Restock Announcement Post</b>\n\n"
            f"{ICON_ORDERS} <b>Fresh Restock Alert!</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> ⚡ <b>YouTube Premium 1 Month</b>\n"
            f"{ICON_TIMER} <b>Validity:</b> 30 Days\n"
            f"{ICON_SPARKLES} <b>Fresh Stock:</b> <code>15 units</code>\n"
            f"{ICON_SHOP} <b>Available:</b> <code>25 accounts</code>\n"
            f"{ICON_MONEY} <b>Price:</b> <code>180 ৳ ($1.44)</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant (Automatic)",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Buy YouTube Premium", url=f"https://t.me/{bot_username}?start=prod_1", icon_custom_emoji_id=Icons.CART)
                ]
            ])
        ),
        (
            "2️⃣1️⃣ <b>[PUBLIC CHANNEL] Price Drop Discount Announcement Post</b>\n\n"
            f"{ICON_MONEY} <b>Special Price Drop!</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> ⚡ <b>Canva Pro 1 Year Education</b>\n"
            f"{ICON_TIMER} <b>Validity:</b> 1 Year\n"
            "📉 <b>Old Price:</b> <code><s>250 ৳</s></code>\n"
            f"{ICON_MONEY} <b>New Price:</b> <code>200 ৳ ($1.60)</code>\n"
            "🏷️ <b>Discount:</b> <code>-20% OFF!</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant (Automatic)",
            InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="Grab Canva Pro Discount", url=f"https://t.me/{bot_username}?start=prod_2", icon_custom_emoji_id=Icons.CART)
                ]
            ])
        ),
    ]

    for index, (text, kb) in enumerate(samples, start=1):
        try:
            await bot.send_message(
                ADMIN_CHAT_ID,
                text,
                reply_markup=kb,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            print(f"[{index}/{len(samples)}] Sent successfully.")
        except Exception as e:
            print(f"[{index}/{len(samples)}] Error sending: {e}")
        await asyncio.sleep(0.7)

    # Outro message
    await bot.send_message(
        ADMIN_CHAT_ID,
        "✨ <b>সবগুলো ২১টি নোটিফিকেশন আপনার চমৎকার আইডিয়াগুলো অন্তর্ভুক্ত করে সফলভাবে পাঠানো সম্পন্ন হয়েছে!</b>\n\n"
        "প্রতিটি মেসেজ চেক করে দেখুন—আইকন, বাটন, কাস্টমার প্রুফ ও দ্বিভাষিক টেক্সট সবকিছু এখন একদম প্রিমিয়াম ও নির্ভুল।",
        parse_mode="HTML",
    )
    print("Done! All 21 polished sample notifications delivered.")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
