"""
Script to send live previews of every single notification type in the bot
to the admin/user Telegram account (6775546602) for visual inspection.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.config import Settings
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BALANCE,
    ICON_CHANNEL,
    ICON_CHECK,
    ICON_COIN,
    ICON_DEPOSIT,
    ICON_FIRE,
    ICON_ID,
    ICON_KEY,
    ICON_MONEY,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_RESELLER,
    ICON_SHOP,
    ICON_SPARKLES,
    ICON_SUPPORT,
    ICON_TIMER,
    ICON_VIP,
    ICON_WARNING,
    Icons,
)

TARGET_TG_ID = 6775546602


async def send_all():
    cfg = Settings()
    bot = Bot(token=cfg.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    me = await bot.get_me()
    print(f"Connected as @{me.username} (ID: {me.id})")
    print(f"Sending sample notifications to Telegram ID: {TARGET_TG_ID}...")

    # Intro message
    await bot.send_message(
        chat_id=TARGET_TG_ID,
        text=(
            "🚀 <b>Live Notification Preview Test</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "বটের মধ্যে যত ধরনের নোটিফিকেশন (অ্যাডমিন অ্যালার্ট, কাস্টমার রিসিট, ডিপোজিট, পেমেন্ট, রেফারেল, চ্যানেল পোস্ট ও এরর) রয়েছে—সবগুলোর লাইভ প্রিভিউ নিচে পাঠানো হচ্ছে যাতে আপনি সবগুলো পরীক্ষা করতে পারেন।\n"
            "━━━━━━━━━━━━━━━━━━"
        ),
    )
    await asyncio.sleep(1.5)

    notifications = []

    # 1. Admin Alert: New Order (Instant Delivery)
    notifications.append((
        "1️⃣ [Admin Alert] New Order Received (Instant Delivered)",
        (
            f"{ICON_SHOP} <b>New Order Received</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ORDERS} <b>Order ID:</b> <code>#1042</code>\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @rahadhasanrafi (<code>{TARGET_TG_ID}</code>)\n"
            f"{ICON_VIP} <b>Product:</b> NordVPN 1 Month Premium\n"
            f"{ICON_MONEY} <b>Price Paid:</b> <code>150.00 ৳</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant (Delivered)"
        ),
        None
    ))

    # 2. Admin Alert: Manual Order Action Required
    order_link = f"{cfg.webhook_base_url or 'http://localhost:3000'}/#orders/1043"
    kb_manual = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Deliver Order #1043", url=order_link, icon_custom_emoji_id=Icons.ORDERS)]
        ]
    )
    notifications.append((
        "2️⃣ [Admin Alert] Manual Order Action Required (Direct Fulfillment Button)",
        (
            f"{ICON_TIMER} <b>Manual Order Action Required</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ORDERS} <b>Order ID:</b> <code>#1043</code>\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @rahadhasanrafi (<code>{TARGET_TG_ID}</code>)\n"
            f"{ICON_VIP} <b>Product:</b> Canva Pro Lifetime (Manual Invite)\n"
            f"{ICON_MONEY} <b>Price Paid:</b> <code>250.00 ৳</code>\n"
            f"{ICON_WARNING} <b>Delivery:</b> Manual Fulfillment Required"
        ),
        kb_manual
    ))

    # 3. Customer Notice: Order Waiting Notice (Pending Manual Delivery)
    notifications.append((
        "3️⃣ [Customer Notice] Order Waiting Notice (Under Preparation)",
        (
            f"{ICON_TIMER} <b>Order #1043: Canva Pro Lifetime</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_CHECK} <b>Payment Received!</b>\n\n"
            f"Your order is being prepared and will be delivered directly here shortly."
        ),
        None
    ))

    # 4. Customer Notice: Delivered Credentials / Order Receipt
    notifications.append((
        "4️⃣ [Customer Notice] Completed Delivery Receipt (Credentials Delivered)",
        (
            f"{ICON_ORDERS} <b>Order #1042 Details</b>\n\n"
            f"{ICON_VIP} <b>Product:</b> NordVPN 1 Month Premium\n"
            f"{ICON_MONEY} <b>Price Paid:</b> <code>150 ৳</code>\n"
            f"{ICON_TIMER} <b>Date:</b> 2026-09-18 15:10 UTC\n"
            f"{ICON_CHECK} <b>Status:</b> <code>COMPLETED</code>\n\n"
            f"{ICON_KEY} <b>Delivered Credentials:</b>\n"
            f"<code>user: nord_vip_user@haven.com\npass: SecretNord2026!\nexpiry: 30 Days</code>\n\n"
            f"<i>(Tap the code above to copy credentials)</i>"
        ),
        None
    ))

    # 5. Admin Alert: New Deposit Request (Manual Method)
    deposit_link = f"{cfg.webhook_base_url or 'http://localhost:3000'}/#deposits"
    kb_deposit = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Review Deposit #205", url=deposit_link, icon_custom_emoji_id=Icons.DEPOSIT)]
        ]
    )
    notifications.append((
        "5️⃣ [Admin Alert] New Deposit Request (Manual bKash/Nagad)",
        (
            f"{ICON_DEPOSIT} <b>New Deposit Request #205</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> @rahadhasanrafi (<code>{TARGET_TG_ID}</code>)\n"
            f"{ICON_DEPOSIT} <b>Method:</b> bKash Personal\n"
            f"{ICON_MONEY} <b>Credit Amount:</b> <code>500.00 ৳</code>\n"
            f"{ICON_KEY} <b>Transaction ID:</b> <code>9X87K2L1P0</code>"
        ),
        kb_deposit
    ))

    # 6. Customer Notice: Deposit Approved
    notifications.append((
        "6️⃣ [Customer Notice] Deposit Request Approved",
        (
            f"{ICON_CHECK} <b>Deposit Approved!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_MONEY} <b>Amount Credited:</b> <code>500.00 ৳</code>\n"
            f"{ICON_DEPOSIT} <b>Payment Method:</b> bKash Personal\n"
            f"{ICON_BALANCE} <b>Updated Balance:</b> <code>4930.00 ৳</code>"
        ),
        None
    ))

    # 7. Customer Notice: Deposit Rejected
    notifications.append((
        "7️⃣ [Customer Notice] Deposit Request Rejected",
        (
            f"{ICON_WARNING} <b>Deposit Request Rejected</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_MONEY} <b>Requested Amount:</b> <code>500.00 ৳</code>\n"
            f"{ICON_NOTE} <b>Reason:</b> Transaction ID could not be found in bKash statement.\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>ভুল মনে হলে পেমেন্ট প্রুফসহ সাপোর্টে যোগাযোগ করুন।</i>"
        ),
        None
    ))

    # 8. Customer Notice: Auto Payment Successful (ZiniPay / Binance)
    notifications.append((
        "8️⃣ [Customer Notice] Automatic Payment Successful (ZiniPay / Binance)",
        (
            f"{ICON_CHECK} <b>Payment Successful!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_MONEY} <b>Credited:</b> <code>1000.00 ৳</code>\n"
            f"{ICON_BALANCE} <b>New Balance:</b> <code>5430.00 ৳</code>"
        ),
        None
    ))

    # 9. Admin Alert: Automatic Deposit Received (ZiniPay / Binance)
    notifications.append((
        "9️⃣ [Admin Alert] Automatic Deposit Received",
        (
            f"{ICON_DEPOSIT} <b>Automatic Deposit #301</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> <code>{TARGET_TG_ID}</code>\n"
            f"{ICON_MONEY} <b>Credit:</b> <code>1000.00 ৳</code> (Paid 1000.00 BDT)\n"
            f"{ICON_DEPOSIT} <b>Gateway:</b> bKash Auto (ZiniPay)\n"
            f"{ICON_KEY} <b>TrxID:</b> <code>ZINI_98471209</code>"
        ),
        None
    ))

    # 10. Admin Alert: New Customer Joined
    notifications.append((
        "🔟 [Admin Alert] New Customer Joined Bot",
        (
            f"{ICON_ACCOUNT} <b>New Customer Joined</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ACCOUNT} <b>Name:</b> Rahad Hasan\n"
            f"💬 <b>Username:</b> @rahadhasanrafi\n"
            f"{ICON_ID} <b>Telegram ID:</b> <code>{TARGET_TG_ID}</code>"
        ),
        None
    ))

    # 11. Customer Notice: Referral Bonus Received!
    notifications.append((
        "1️⃣1️⃣ [Customer Notice] Referral Bonus Received (Referrer Alert)",
        (
            f"{ICON_ORDERS} <b>Referral Bonus Received!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_ACCOUNT} <b>Friend:</b> Tanvir Ahmed\n"
            f"{ICON_COIN} <b>Bonus Credited:</b> <code>+3.00 ৳</code>"
        ),
        None
    ))

    # 12. Customer Notice: Wallet Balance Adjusted by Admin
    notifications.append((
        "1️⃣2️⃣ [Customer Notice] Wallet Balance Adjusted by Admin Console",
        (
            f"{ICON_DEPOSIT} <b>Wallet Balance Updated</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_COIN} <b>Credit Added:</b> <code>+100.00 ৳</code>\n"
            f"{ICON_BALANCE} <b>Current Balance:</b> <code>4530.00 ৳</code>\n"
            f"{ICON_NOTE} <b>Reason:</b> Promotional Referral Cashback"
        ),
        None
    ))

    # 13. Admin Alert: Stock Added (Restock Alert)
    notifications.append((
        "1️⃣3️⃣ [Admin Alert] Stock Added to Catalog",
        (
            f"{ICON_ORDERS} <b>Stock Added (Restock Alert)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_VIP} <b>Product:</b> 💎 Spotify 1 Month Family Member\n"
            f"➕ <b>Added Stock:</b> <code>50</code> item(s)\n"
            f"📦 <b>Total Stock:</b> <code>75</code> units\n"
            f"{ICON_MONEY} <b>Price:</b> <code>99.00 ৳</code>"
        ),
        None
    ))

    # 14. Channel Post: Fresh Product Restock Alert
    kb_buy = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Buy Spotify 1 Month", url=f"https://t.me/{me.username}?start=prod_1", icon_custom_emoji_id=Icons.CART)]
        ]
    )
    notifications.append((
        "1️⃣4️⃣ [Channel / Subscriber Alert] Fresh Stock Broadcast Announcement",
        (
            f"{ICON_ORDERS} <b>Fresh Restock Alert!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_VIP} <b>Product:</b> 💎 <b>Spotify 1 Month Family Member</b>\n"
            f"{ICON_SPARKLES} <b>Fresh Stock:</b> <code>50 units</code>\n"
            f"📦 <b>Available:</b> <code>75 accounts</code>\n"
            f"{ICON_MONEY} <b>Price:</b> <code>99.00 ৳</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant Automatic Delivery"
        ),
        kb_buy
    ))

    # 15. Channel Post: Special Price Drop
    notifications.append((
        "1️⃣5️⃣ [Channel / Subscriber Alert] Price Drop Announcement",
        (
            f"{ICON_FIRE} <b>Special Price Drop!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_VIP} <b>Product:</b> ⚡ <b>ChatGPT Plus 1 Month Private</b>\n"
            f"💸 <b>Previous Price:</b> <s>2500.00 ৳</s>\n"
            f"{ICON_MONEY} <b>Discounted Price:</b> <code>2100.00 ৳</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant Automatic Delivery"
        ),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Buy ChatGPT Plus", url=f"https://t.me/{me.username}?start=prod_2", icon_custom_emoji_id=Icons.CART)]
            ]
        )
    ))

    # 16. Channel Post: Featured Product Promotion
    notifications.append((
        "1️⃣6️⃣ [Channel / Subscriber Alert] Featured Product Promotion",
        (
            f"{ICON_FIRE} <b>Featured Product</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_VIP} <b>Product:</b> ⚡ <b>ExpressVPN 1 Year Premium Key</b>\n"
            f"📝 Ultra-fast servers in 94 countries, unlimited bandwidth, high privacy.\n"
            f"📦 <b>Available Stock:</b> <code>12 units</code>\n"
            f"{ICON_MONEY} <b>Price:</b> <code>1200.00 ৳</code>\n"
            f"{ICON_CHECK} <b>Delivery:</b> Instant Automatic Delivery"
        ),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Order ExpressVPN", url=f"https://t.me/{me.username}?start=prod_3", icon_custom_emoji_id=Icons.CART)]
            ]
        )
    ))

    # 17. Customer Notice: Force Join Channel Gate
    notifications.append((
        "1️⃣7️⃣ [Customer Gate] Mandatory Force Join Channel Verification",
        (
            f"{ICON_CHANNEL} <b>Join Our Channels to Continue</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"To access <b>Premium Haven</b>, browse products, and receive referral bonuses, please join our official update channels below:"
        ),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Join Official Channel 1",
                        url="https://t.me/telegram",
                        icon_custom_emoji_id=Icons.CHANNEL,
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Verify & Start Bot",
                        callback_data="gate_verify",
                        icon_custom_emoji_id=Icons.CHECK,
                        style="success",
                    )
                ],
            ]
        )
    ))

    # Send each one with a small delay
    total = len(notifications)
    for idx, (label, text, kb) in enumerate(notifications, 1):
        header = f"<b>PREVIEW {idx}/{total}:</b> {label}\n"
        full_text = f"{header}\n{text}"
        try:
            await bot.send_message(
                chat_id=TARGET_TG_ID,
                text=full_text,
                reply_markup=kb,
            )
            print(f"Sent [{idx}/{total}]")
            await asyncio.sleep(1.2)
        except Exception as e:
            print(f"Error sending [{idx}/{total}]: {e}")

    await bot.send_message(
        chat_id=TARGET_TG_ID,
        text=(
            "✅ <b>সকল নোটিফিকেশন সফলভাবে আপডেট করে পাঠানো সম্পন্ন হয়েছে!</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "• ম্যানুয়াল অর্ডার ও ডিপোজিট নোটিফিকেশন থেকে টেক্সট লিংক রিমুভ করে সরাসরি কাস্টম ইমোজি যুক্ত বাটন দেওয়া হয়েছে।\n"
            "• চ্যানেল রিস্টক ও অফার পোস্টগুলোতে সাধারণ কার্টের বদলে প্রিমিয়াম থ্রিডি কার্ট ইমোজি ও সরাসরি বাই ডিপলিংক যুক্ত করা হয়েছে।\n"
            "• অপ্রয়োজনীয় টেক্সটগুলো সম্পূর্ণ রিমুভ করে কার্ডগুলোকে ক্লিন ও আধুনিক করা হয়েছে।\n"
            "• কোনো সাপ্লায়ার নোটিফিকেশন রাখা হয়নি।"
        ),
    )
    print("Done sending all notifications!")
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(send_all())
