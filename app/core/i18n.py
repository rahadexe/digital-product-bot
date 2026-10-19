"""Centralized Internationalization (i18n) Engine.

Supports 2 languages:
  - English ('en') - Default fallback
  - Bengali ('bn') - বাংলা

Features:
  - Dynamic variable interpolation with kwargs
  - Automatic fallback to English if a key or language is missing
  - Extensible: adding or modifying any key updates all languages in one place
"""

from __future__ import annotations

from typing import Any

SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native": "English", "flag": "🇬🇧"},
    "bn": {"name": "Bengali", "native": "বাংলা", "flag": "🇧🇩"},
}

DEFAULT_LANGUAGE = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Buttons
        "btn_shop": "Products",
        "btn_wallet": "💳 Wallet",
        "btn_deposit": "Top Up",
        "btn_add_balance": "Top Up",
        "btn_search": "🔍 Search",
        "btn_refer_earn": "Refer",
        "btn_account": "Profile",
        "btn_profile": "Profile",
        "btn_support": "Contact Support",
        "btn_help": "💬 Help",
        "btn_become_reseller": "💼 Become Reseller",
        "btn_reseller_panel": "💼 Reseller Panel",
        "btn_reseller": "💼 Reseller",
        "btn_developer_api": "🔑 API",
        "btn_notifications": "🔔 Notifications",
        "btn_reseller_api": "🔑 API & Reseller",
        "btn_admin_panel": "Admin Panel",
        "btn_other_products": "Products",
        "btn_all_products": "Products",
        "btn_my_orders": "📦 Orders",
        "btn_my_balance": "Wallet",
        "btn_order_history": "Orders",
        "btn_balance_history": "History",
        "btn_deposit_history": "History",
        "btn_change_language": "🌐 Language",
        "btn_price_list": "📊 Price List",
        "btn_back": "Back",
        "btn_close": "Close",
        "btn_confirm": "Confirm",
        "btn_cancel": "Cancel",
        "btn_copy_format": "📋 Copy Format",
        "btn_contact_management": "Contact Support",
        "btn_deposit_menu": "Wallet",
        "btn_main_menu": "Menu",
        "btn_share_referral": "Share",
        "btn_copy_link": "Copy Link",
        "btn_view_terms": "📜 Terms & Conditions",
        "btn_pay": "💳 Pay {amount}",
        "btn_ive_paid": "Payment Done",
        "btn_cancel_invoice": "Cancel Payment",
        "btn_keep": "Keep Payment",

        # Language Selection
        "select_language_title": "🌐 <b>Language</b>",
        "select_language_prompt": (
            "🌐 <b>Language</b>\n\n"
            "Choose your preferred language below."
        ),
        "lang_switched_toast": "✅ Language set to English.",

        # Compact product card
        "product_available": "In stock",
        "product_unavailable": "Out of stock",
        "product_manual": "Manual delivery",
        "product_automatic": "Automatic delivery",
        "product_validity": "Validity",
        "product_warranty": "Warranty",
        "product_price": "Price",
        "product_quantity": "Quantity",
        "product_total": "Total",
        "product_shortfall": "Add <b>{amount}</b> to buy.",

        # Welcome / Start
        "welcome_default": "{icon_sparkles} <b>{store_name}</b>",
        "maintenance_notice": "{icon_warning} <b>Maintenance:</b> {notice}\n\n",

        # Profile / Wallet
        "wallet_title": "My Wallet",
        "wallet_current_balance": "Available Balance",
        "account_title": "{icon_account} <b>My Account</b>",
        "profile_title": "{icon_account} <b>My Profile</b>",
        "account_info_title": "Account Info",
        "wallet_orders_title": "Wallet & Orders",
        "profile_name": "Name",
        "profile_username": "Username",
        "profile_user_id": "User ID",
        "profile_account_type": "Rank",
        "profile_current_balance": "Balance",
        "profile_total_orders": "Orders",
        "profile_total_spent": "Spent",
        "profile_referrals": "Referrals",
        "profile_referral_link": "Referral Link",
        "rank_standard": "Member",
        "rank_reseller": "Reseller",

        # Refer & Earn
        "referral_title": "{icon_refer} <b>Refer & Earn</b>",
        "referral_step_1": "1️⃣ Share your invite link",
        "referral_step_2": "2️⃣ Friend joins via link",
        "referral_step_3": "3️⃣ Get <b>{reward}</b> bonus!",
        "referral_stats_header": "{icon_stats} <b>Your Stats:</b>",
        "stats_title": "Stats",
        "referral_tagline": "Share your link. Earn a bonus when a friend joins.",
        "referral_link_label": "Your Referral Link",
        "referral_reward_notice": "Friend joins with your link: <b>{reward}</b> bonus.",
        "referral_stat_total": "Referrals",
        "referral_stat_earned": "Total Earned",

        # Support & Help
        "support_title": "{icon_support} <b>Support</b>",
        "help_title": "<b>Most common questions:</b>",
        "support_text": "Need help with an order or wallet? Message us.",
        "support_unavailable": "No support contact is configured. Check Help or the update channels.",
        "channel_list_title": "Our channels",
        "channel_list_intro": "Join for new products and offers.",
        "channel_list_empty": "No channels yet.",

        # Reseller
        "reseller_apply_title": "{icon_reseller} <b>Become Reseller</b>",
        "reseller_panel_title": "{icon_reseller} <b>Reseller Panel</b>",
        "reseller_apply_text": "Complete the form below to apply as a reseller.",

        # Search
        "search_title": "🔍 <b>Search</b>",
        "search_prompt": "Enter a product name.",
        "search_try": "Try",
        "reseller_format_label": "Application Format",
        "reseller_benefits_title": "Reseller Benefits",
        "reseller_b1": "Bulk discounts & wholesale reseller rates",
        "reseller_b2": "REST API Key to integrate your bot or website",
        "reseller_b3": "Rapid delivery & instant automatic credentials",
        "reseller_b4": "Contact Support for assistance",

        # Deposit
        "deposit_select_method": (
            "{icon_coin} <b>Balance:</b> <code>{balance}</code>\n"
            "Choose a method to top up."
        ),
        "deposit_pending_warning": (
            "{icon_timer} <b>Pending Deposit Request</b>\n\n"
            "A <b>{price}</b> deposit via <b>{method}</b> is pending.\n"
            "Wait for it to finish before starting another."
        ),
        "deposit_closed": "{icon_warning} <b>Deposits Temporarily Closed</b>\n\n{notice}",
        "deposit_unavailable": "{icon_warning} <b>Deposits unavailable</b>\n\nNo payment methods are available.",
        "deposit_enter_amount": "Enter the amount in BDT, e.g. 100.",
        # Navigation & Pagination Buttons
        "btn_refresh": "Refresh",
        "btn_next": "Next",
        "btn_prev": "Previous",
        "btn_copy_credentials": "Copy Credentials",
        "btn_copy_trxid": "Copy TrxID",
        "btn_copy_number": "Copy Number",
        "btn_copy_uid": "Copy Binance UID",
        "btn_payment_done": "Payment Done",
        "btn_change_amount": "Change Amount",
        "btn_change_method": "Change Method",
        "btn_open_payment_page": "Pay Now",
        "btn_support_chat": "Contact Support",
        "btn_guide": "Guide",
        "btn_cancel_deposit": "Cancel Top-up",
        "btn_browse_products": "Browse Products",
        "btn_back": "Back",

        # Order History & Details
        "order_history_title": "<b>Orders</b>",
        "order_history_empty": (
            "No orders yet.\n"
            "Browse products to get started."
        ),
        "order_history_page": "<b>Orders</b> · {page}/{total_pages}",
        "order_not_found": "Order not found.",
        "order_preparing": "Paid. Preparing your order for delivery.",
        "order_detail_title": "<b>Order {id}</b>",
        "order_product": "Product",
        "order_price_paid": "Price Paid",
        "order_date": "Date",
        "order_status": "Status",
        "order_credentials": "Delivered Credentials",

        # Balance / Deposit History & Details
        "balance_history_title": "<b>Top-up History</b>",
        "balance_history_hint": "",
        "balance_history_empty": (
            "No top-ups yet.\n"
            "Choose a payment method in Wallet to get started."
        ),
        "balance_history_page": "<b>Top-up History</b>",
        "deposit_not_found": "Top-up not found. Open Wallet to check History.",
        "deposit_detail_title": "<b>Top-up {id}</b>",
        "status_approved_msg": "Payment verified. Your balance is updated.",
        "status_rejected_msg": "Top-up not approved. Contact Support if you have already paid.",
        "status_pending_msg": "Your payment details are awaiting verification. Do not pay again.",
        "deposit_amount": "Amount",
        "deposit_method": "Method",
        "deposit_trxid": "Transaction ID",
        "deposit_submitted_at": "Submitted",
        "deposit_reviewed_at": "Reviewed",
        "deposit_admin_note": "Note",
        "status_approved": "Approved",
        "status_rejected": "Rejected",
        "status_pending": "Pending Review",
        "status_completed": "Delivered",
        "status_refunded": "Refunded",
        "status_waiting": "Preparing",
        "status_completed_msg": "Order delivered.",
        "status_refunded_msg": "Order cancelled. Funds returned to your wallet.",
        "status_waiting_msg": "Preparing your order for delivery.",

        "deposit_choose_method": (
            "💰 <b>Balance:</b> <code>{balance}</code>\n\n"
            "Choose a method to top up."
        ),
        "deposit_paused_title": "{icon_warning} <b>Deposits Temporarily Paused</b>",
        "deposit_pending_summary": (
            "💰 <b>Balance:</b> <code>{balance}</code>\n\n"
            "{icon_timer} <b>Pending Deposit</b>\n\n"
            "<b>Method:</b> {method}\n"
            "<b>Amount:</b> {amount}\n"
            "<b>TrxID:</b> <code>{trxid}</code>\n\n"
            "<i>Balance is added after verification.</i>"
        ),
        "deposit_enter_amount_prompt": "Enter the amount in BDT, e.g. 100.",
        "deposit_enter_txid_prompt": "Send the TrxID from your payment receipt.",
        "deposit_trxid_used": "{icon_cross} This TrxID was already used.",
        "deposit_amount_mismatch": "{icon_cross} Amount doesn't match. Select Change Amount to update it.",
        "deposit_invalid_trxid": "{icon_cross} Invalid TrxID. Check your receipt and try again.",
        "deposit_tries_left": "Tries left: {tries}",
        "deposit_submitted_notice": (
            "<b>Payment details submitted</b>\n"
            "Method: {method}\n"
            "Amount: {amount}\n"
            "Balance is added after verification. Do not pay again."
        ),
        "deposit_pending_still": (
            "{icon_timer} <b>You already have a pending deposit.</b>\n\n"
            "Please wait for your previous request to be reviewed before submitting another."
        ),
    },

    "bn": {
        # Buttons
        "btn_shop": "🛍️ স্টোর",
        "btn_wallet": "💳 ওয়ালেট",
        "btn_deposit": "💳 ডিপোজিট",
        "btn_add_balance": "💳 ডিপোজিট",
        "btn_search": "🔍 সার্চ",
        "btn_refer_earn": "🎁 রেফার",
        "btn_account": "👤 একাউন্ট",
        "btn_profile": "👤 আমার প্রোফাইল",
        "btn_support": "🎧 সাপোর্ট",
        "btn_help": "💬 হেল্প",
        "btn_become_reseller": "💼 রিসেলার হন",
        "btn_reseller_panel": "💼 রিসেলার প্যানেল",
        "btn_reseller": "💼 রিসেলার",
        "btn_developer_api": "🔑 এপিআই",
        "btn_notifications": "🔔 নোটিফিকেশন",
        "btn_reseller_api": "🔑 এপিআই ও রিসেলার",
        "btn_admin_panel": "অ্যাডমিন প্যানেল",
        "btn_other_products": "🛍️ স্টোর",
        "btn_all_products": "🛍️ স্টোর",
        "btn_my_orders": "📦 অর্ডার",
        "btn_my_balance": "💰 আমার ব্যালেন্স",
        "btn_order_history": "📦 অর্ডার হিস্ট্রি",
        "btn_balance_history": "📊 ডিপোজিট হিস্ট্রি",
        "btn_deposit_history": "📊 ডিপোজিট হিস্ট্রি",
        "btn_change_language": "🌐 ভাষা",
        "btn_price_list": "📊 প্রাইস লিস্ট",
        "btn_back": "🔙 ব্যাক",
        "btn_close": "❌ বন্ধ",
        "btn_confirm": "✅ নিশ্চিত করুন",
        "btn_cancel": "❌ বাতিল",
        "btn_copy_format": "📋 ফরম্যাট কপি করুন",
        "btn_contact_management": "📞 ম্যানেজমেন্ট যোগাযোগ",
        "btn_deposit_menu": "💳 ডিপোজিট মেনু",
        "btn_main_menu": "🏠 মেইন মেনু",
        "btn_share_referral": "🚀 লিংক শেয়ার",
        "btn_copy_link": "📋 লিংক কপি",
        "btn_view_terms": "📜 শর্তাবলী দেখুন",
        "btn_pay": "💳 পেমেন্ট করুন {amount}",
        "btn_ive_paid": "✅ টাকা পাঠিয়েছি",
        "btn_cancel_invoice": "❌ ইনভয়েস বাতিল",
        "btn_keep": "🔙 রাখুন",

        # Language Selection
        "select_language_title": "🌐 <b>ভাষা</b>",
        "select_language_prompt": (
            "🌐 <b>ভাষা</b>\n\n"
            "নিচে আপনার পছন্দের ভাষা বেছে নিন।"
        ),
        "lang_switched_toast": "✅ ভাষা সেট: বাংলা",

        # Compact product card
        "product_available": "স্টক আছে",
        "product_unavailable": "স্টক শেষ",
        "product_manual": "ম্যানুয়াল ডেলিভারি",
        "product_automatic": "অটো ডেলিভারি",
        "product_validity": "মেয়াদ",
        "product_warranty": "ওয়ারেন্টি",
        "product_price": "দাম",
        "product_quantity": "পরিমাণ",
        "product_total": "মোট",
        "product_shortfall": "কিনতে <b>{amount}</b> যোগ করুন।",

        # Welcome / Start
        "welcome_default": "{icon_sparkles} <b>{store_name}</b>",
        "maintenance_notice": "{icon_warning} <b>রক্ষণাবেক্ষণ:</b> {notice}\n\n",

        # Profile / Wallet
        "wallet_title": "আপনার ওয়ালেট",
        "wallet_current_balance": "বর্তমান ব্যালেন্স",
        "account_title": "{icon_account} <b>আমার একাউন্ট</b>",
        "profile_title": "{icon_account} <b>আমার প্রোফাইল</b>",
        "account_info_title": "অ্যাকাউন্ট তথ্য",
        "wallet_orders_title": "ওয়ালেট ও অর্ডার",
        "profile_name": "নাম",
        "profile_username": "ইউজারনেম",
        "profile_user_id": "ইউজার আইডি",
        "profile_account_type": "র‍্যাংক",
        "profile_current_balance": "ব্যালেন্স",
        "profile_total_orders": "অর্ডার",
        "profile_total_spent": "খরচ",
        "profile_referrals": "রেফার",
        "profile_referral_link": "রেফারেল লিংক",
        "rank_standard": "সদস্য",
        "rank_reseller": "রিসেলার",

        # Refer & Earn
        "referral_title": "{icon_refer} <b>রেফার ও ইনকাম</b>",
        "referral_step_1": "1️⃣ ইনভাইট লিংক শেয়ার করুন",
        "referral_step_2": "2️⃣ বন্ধু লিংকে জয়েন করবে",
        "referral_step_3": "3️⃣ পেয়ে যাবেন <b>{reward}</b> বোনাস!",
        "referral_stats_header": "{icon_stats} <b>আপনার পরিসংখ্যান:</b>",
        "stats_title": "পরিসংখ্যান",
        "referral_tagline": "লিংক শেয়ার করুন। বন্ধু যোগ দিলেই বোনাস পান।",
        "referral_link_label": "আপনার রেফারেল লিংক",
        "referral_reward_notice": "লিংকে বন্ধু যোগ দিলে <b>{reward}</b> বোনাস পাবেন।",
        "referral_stat_total": "মোট রেফার",
        "referral_stat_earned": "মোট আয়",

        # Support & Help
        "support_title": "{icon_support} <b>সাপোর্ট</b>",
        "help_title": "<b>সাধারণ প্রশ্নসমূহ:</b>",
        "support_text": "অর্ডার বা ওয়ালেটে সাহায্য লাগলে মেসেজ করুন।",
        "support_unavailable": "সাপোর্ট বন্ধ। গাইড বা চ্যানেল দেখুন।",
        "channel_list_title": "আমাদের চ্যানেল",
        "channel_list_intro": "নতুন প্রোডাক্ট ও অফার পেতে যুক্ত থাকুন।",
        "channel_list_empty": "এখনও কোনো চ্যানেল নেই।",

        # Reseller
        "reseller_apply_title": "{icon_reseller} <b>রিসেলার হন</b>",
        "reseller_panel_title": "{icon_reseller} <b>রিসেলার প্যানেল</b>",
        "reseller_apply_text": "রিসেলার হতে নিচের ফর্ম পূরণ করে আবেদন করুন।",

        # Search
        "search_title": "🔍 <b>সার্চ</b>",
        "search_prompt": "প্রোডাক্টের নাম লিখুন।",
        "search_try": "যেমন",
        "reseller_format_label": "আবেদন ফরম্যাট",
        "reseller_benefits_title": "রিসেলার সুবিধাসমূহ",
        "reseller_b1": "হোলসেল রেট ও বিশেষ ডিসকাউন্ট",
        "reseller_b2": "বট বা ওয়েবসাইটে ইন্টিগ্রেশনের জন্য REST API Key",
        "reseller_b3": "স্বয়ংক্রিয় ও তাত্ক্ষণিক ডেলিভারি",
        "reseller_b4": "২৪/৭ সরাসরি ম্যানেজমেন্ট সহায়তা",

        # Deposit
        "deposit_select_method": (
            "{icon_coin} <b>ব্যালেন্স:</b> <code>{balance}</code>\n"
            "👇 <i>পেমেন্ট মেথড বেছে নিন।</i>"
        ),
        "deposit_pending_warning": (
            "{icon_timer} <b>পেন্ডিং ডিপোজিট রিকোয়েস্ট</b>\n\n"
            "<b>{method}</b>-এ <b>{price}</b> ডিপোজিট পেন্ডিং।\n"
            "এটি শেষ হলে নতুন ডিপোজিট করুন।"
        ),
        "deposit_closed": "{icon_warning} <b>ডিপোজিট সাময়িকভাবে বন্ধ আছে</b>\n\n{notice}",
        "deposit_unavailable": "{icon_warning} <b>ডিপোজিট বন্ধ</b>\n\nকোনো পেমেন্ট মেথড নেই।",
        "deposit_enter_amount": "টাকার পরিমাণ লিখুন, যেমন: 100।",
        # Navigation & Pagination Buttons
        "btn_refresh": "রিফ্রেশ",
        "btn_next": "পরবর্তী",
        "btn_prev": "পূর্ববর্তী",
        "btn_copy_credentials": "📋 ক্রেডেনশিয়াল কপি",
        "btn_copy_trxid": "📋 TrxID কপি",
        "btn_copy_number": "📋 নম্বর কপি",
        "btn_copy_uid": "📋 Binance UID কপি",
        "btn_payment_done": "✅ পেমেন্ট সম্পন্ন",
        "btn_change_amount": "✏️ টাকা পরিবর্তন",
        "btn_change_method": "🔄 মেথড পরিবর্তন",
        "btn_open_payment_page": "🌐 পেমেন্ট পেজ",
        "btn_support_chat": "💬 সাপোর্ট ইনবক্স",
        "btn_guide": "📖 গাইড",
        "btn_cancel_deposit": "❌ ডিপোজিট বাতিল",
        "btn_browse_products": "🛍️ প্রোডাক্ট ব্রাউজ করুন",
        "btn_back": "🔙 ব্যাক",

        # Order History & Details
        "order_history_title": "<b>অর্ডার</b>",
        "order_history_empty": (
            "🛒 কোনো অর্ডার নেই।\n"
            "কিনতে প্রোডাক্ট দেখুন।"
        ),
        "order_history_page": "<b>অর্ডার</b> · {page}/{total_pages}",
        "order_not_found": "অর্ডার খুঁজে পাওয়া যায়নি।",
        "order_preparing": "পেমেন্ট হয়েছে। অর্ডার প্রস্তুত হচ্ছে।",
        "order_detail_title": "<b>অর্ডার {id}</b>",
        "order_product": "প্রোডাক্ট",
        "order_price_paid": "মূল্য পরিশোধিত",
        "order_date": "তারিখ",
        "order_status": "স্ট্যাটাস",
        "order_credentials": "ডেলিভারিকৃত ক্রেডেনশিয়াল",

        # Balance / Deposit History & Details
        "balance_history_title": "<b>টপ-আপ হিস্ট্রি</b>",
        "balance_history_hint": "",
        "balance_history_empty": (
            "💳 কোনো লেনদেন নেই\n"
            "⚡ ব্যালেন্স যোগ করুন"
        ),
        "balance_history_page": "<b>টপ-আপ হিস্ট্রি</b>",
        "deposit_not_found": "ডিপোজিট রেকর্ড পাওয়া যায়নি।",
        "deposit_detail_title": "<b>ডিপোজিট {id}</b>",
        "status_approved_msg": "পেমেন্ট যাচাই হয়েছে। ব্যালেন্স যোগ হয়েছে।",
        "status_rejected_msg": "ডিপোজিট বাতিল হয়েছে।",
        "status_pending_msg": "পেমেন্ট যাচাই হচ্ছে।",
        "deposit_amount": "পরিমাণ",
        "deposit_method": "মেথড",
        "deposit_trxid": "ট্রানজ্যাকশন আইডি",
        "deposit_submitted_at": "জমা দেওয়ার সময়",
        "deposit_reviewed_at": "যাচাইয়ের সময়",
        "deposit_admin_note": "অ্যাডমিন নোট",
        "status_approved": "অনুমোদিত",
        "status_rejected": "বাতিল",
        "status_pending": "পর্যালোচনাধীন",
        "status_completed": "ডেলিভার্ড",
        "status_refunded": "রিফান্ডেড",
        "status_waiting": "প্রস্তুত হচ্ছে",
        "status_completed_msg": "অর্ডার ডেলিভারি হয়েছে।",
        "status_refunded_msg": "অর্ডার বাতিল। টাকা ওয়ালেটে ফেরত গেছে।",
        "status_waiting_msg": "অর্ডার প্রস্তুত হচ্ছে।",

        "deposit_choose_method": (
            "💰 <b>ব্যালেন্স:</b> <code>{balance}</code>\n\n"
            "<b>পেমেন্ট মেথড সিলেক্ট করুন</b>"
        ),
        "deposit_paused_title": "{icon_warning} <b>ডিপোজিট সাময়িকভাবে বন্ধ আছে</b>",
        "deposit_pending_summary": (
            "💰 <b>ব্যালেন্স:</b> <code>{balance}</code>\n\n"
            "{icon_timer} <b>পেন্ডিং ডিপোজিট</b>\n\n"
            "<b>মেথড:</b> {method}\n"
            "<b>পরিমাণ:</b> {amount}\n"
            "<b>TrxID:</b> <code>{trxid}</code>\n\n"
            "<i>যাচাই হলে ব্যালেন্স যোগ হবে।</i>"
        ),
        "deposit_enter_amount_prompt": "টাকার পরিমাণ লিখুন, যেমন: 100।",
        "deposit_enter_txid_prompt": "আপনার পেমেন্টের রসিদ থেকে TrxID পাঠান।",
        "deposit_trxid_used": "{icon_cross} এই TrxID আগেই ব্যবহার হয়েছে।",
        "deposit_amount_mismatch": "{icon_cross} টাকার অঙ্ক মেলেনি। ঠিক করতে টাকা পরিবর্তন করুন।",
        "deposit_invalid_trxid": "{icon_cross} TrxID ভুল। রসিদ দেখে আবার দিন।",
        "deposit_tries_left": "বাকি চেষ্টা: {tries}",
        "deposit_submitted_notice": (
            "<b>পেমেন্টের তথ্য জমা হয়েছে।</b>\n"
            "মেথড: {method}\n"
            "পরিমাণ: {amount}\n"
            "যাচাই শেষে ব্যালেন্স যোগ হবে।"
        ),
        "deposit_pending_still": (
            "{icon_timer} <b>আপনার একটি ডিপোজিট রিকোয়েস্ট পেন্ডিং রয়েছে।</b>\n\n"
            "পূর্বের রিকোয়েস্টটি যাচাই শেষ হওয়া পর্যন্ত অপেক্ষা করুন।"
        ),
    },

}



def t(key: str, lang: str | None = "en", **kwargs: Any) -> str:
    """
    Get localized string by key and language code.
    Gracefully falls back to English ('en') if key or language is not found.
    Interpolates kwargs safely.
    """
    code = (lang or DEFAULT_LANGUAGE).strip().lower()
    if code not in TRANSLATIONS:
        code = DEFAULT_LANGUAGE

    tmpl = TRANSLATIONS[code].get(key)
    if tmpl is None:
        # Fallback to English
        tmpl = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)

    if kwargs:
        try:
            return tmpl.format(**kwargs)
        except Exception:
            return tmpl
    return tmpl


def normalize_language(lang: str | None) -> str:
    """Normalize language code to one of ('en', 'bn')."""
    code = (lang or "").strip().lower()
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
