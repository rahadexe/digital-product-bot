"""Centralized Internationalization (i18n) Engine.

Supports 4 languages:
  - English ('en') - Default fallback
  - Bengali ('bn') - বাংলা
  - Hindi ('hi') - हिन्दी
  - Urdu ('ur') - اردو

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
    "hi": {"name": "Hindi", "native": "हिन्दी", "flag": "🇮🇳"},
    "ur": {"name": "Urdu", "native": "اردو", "flag": "🇵🇰"},
}

DEFAULT_LANGUAGE = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Buttons
        "btn_add_balance": "💳 Add Balance",
        "btn_search": "🔍 Search",
        "btn_refer_earn": "🎁 Refer & Earn",
        "btn_profile": "👤 My Profile",
        "btn_support": "🎧 Support",
        "btn_become_reseller": "💼 Become Reseller",
        "btn_reseller_panel": "💼 Reseller Panel",
        "btn_admin_panel": "👑 Admin Panel",
        "btn_other_products": "🛍️ Other Products",
        "btn_all_products": "🛍️ All Products",
        "btn_my_orders": "📦 My Orders",
        "btn_my_balance": "💰 My Balance",
        "btn_order_history": "📦 Order History",
        "btn_balance_history": "📊 Balance History",
        "btn_change_language": "🌐 Language",
        "btn_back": "🔙 Back",
        "btn_close": "❌ Close",
        "btn_confirm": "Confirm",
        "btn_cancel": "Cancel",
        "btn_copy_format": "Copy Format",
        "btn_contact_management": "Contact Management",
        "btn_deposit_menu": "Deposit Menu",
        "btn_main_menu": "Main Menu",
        "btn_share_referral": "🚀 Share Link",
        "btn_copy_link": "📋 Copy Link",
        "btn_view_terms": "Terms & Conditions",
        "btn_pay": "Pay {amount}",
        "btn_ive_paid": "I've Paid",
        "btn_cancel_invoice": "Cancel Invoice",
        "btn_keep": "Keep",

        # Language Selection
        "select_language_title": "🌐 <b>Language</b>",
        "select_language_prompt": (
            "🌐 <b>Language</b>\n\n"
            "<b>Current:</b> 🇬🇧 English\n"
            "🔄 Tap below to switch language"
        ),
        "lang_switched_toast": "✅ Language changed to English!",

        # Welcome / Start
        "welcome_default": "{icon_sparkles} Welcome to <b>{store_name}</b>!",
        "maintenance_notice": "{icon_warning} <b>Maintenance Notice:</b> {notice}\n\n",

        # Profile / Wallet
        "wallet_title": "My Wallet",
        "wallet_current_balance": "Available Balance",
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
        "rank_standard": "Normal",
        "rank_reseller": "Reseller",

        # Refer & Earn
        "referral_title": "{icon_refer} <b>Refer & Earn</b>",
        "referral_step_1": "1️⃣ Share your invite link",
        "referral_step_2": "2️⃣ Friend joins via link",
        "referral_step_3": "3️⃣ Get <b>{reward}</b> bonus!",
        "referral_stats_header": "{icon_stats} <b>Your Stats:</b>",
        "stats_title": "Stats",
        "referral_tagline": "Share your referral link with friends and earn cash rewards!",
        "referral_link_label": "Your Referral Link",
        "referral_reward_notice": "• Earn <b>{reward}</b> bonus when your friend joins using your link.",
        "referral_stat_total": "Referrals",
        "referral_stat_earned": "Total Earned",

        # Support
        "support_title": "{icon_support} <b>Support</b>",
        "support_text": (
            "Contact our official team for quick help with your orders or wallet:\n\n"
            "⏰ 24/7 Live Support\n"
            "⚡ Fast Response"
        ),
        "support_unavailable": (
            "Support chat is currently offline. Please check our guide or channels:\n\n"
            "⏰ 24/7 Live Support\n"
            "⚡ Fast Response"
        ),

        # Reseller
        "reseller_apply_title": "{icon_reseller} <b>Become Reseller</b>",
        "reseller_panel_title": "{icon_reseller} <b>Reseller Panel</b>",
        "reseller_apply_text": (
            "If you want to become a reseller in our bot, fill out the application details below and message our <b>Contact Management</b>."
        ),

        # Search
        "search_title": "🔍 <b>Search</b>",
        "search_prompt": "Type what you are looking for:",
        "search_try": "Try",
        "reseller_format_label": "Application Format",
        "reseller_benefits_title": "Reseller Benefits",
        "reseller_b1": "Bulk discounts & wholesale reseller rates",
        "reseller_b2": "REST API Key to integrate your bot or website",
        "reseller_b3": "Rapid delivery & instant automatic credentials",
        "reseller_b4": "24/7 direct management access",

        # Deposit
        "deposit_select_method": (
            "{icon_deposit} <b>Add Balance</b>\n\n"
            "Select a payment method below to top up your wallet.\n"
            "Current balance: <b>{balance}</b>"
        ),
        "deposit_pending_warning": (
            "{icon_timer} <b>Pending Deposit Request</b>\n\n"
            "You already have a pending deposit of <b>{price}</b> via <b>{method}</b>.\n\n"
            "Please wait for it to be processed before creating a new one."
        ),
        "deposit_closed": "{icon_warning} <b>Deposits Temporarily Closed</b>\n\n{notice}",
        "deposit_unavailable": "{icon_warning} <b>Deposit Unavailable</b>\n\nNo deposit methods are currently available.",
        "deposit_enter_amount": "{icon_money} <b>Enter deposit amount:</b>\n\n💡 <i>(e.g. 100)</i>",
        # Navigation & Pagination Buttons
        "btn_refresh": "Refresh",
        "btn_next": "Next",
        "btn_prev": "Prev",
        "btn_copy_credentials": "Copy Credentials",
        "btn_copy_trxid": "Copy TrxID",
        "btn_copy_number": "Copy Number",
        "btn_copy_uid": "Copy Binance UID",
        "btn_payment_done": "Payment Done",
        "btn_change_amount": "Change Amount",
        "btn_change_method": "Change Method",
        "btn_open_payment_page": "Open Payment Page",
        "btn_support_chat": "💬 Chat with Support",
        "btn_guide": "📖 Guide",
        "btn_cancel_deposit": "Cancel Deposit",
        "btn_browse_products": "🛍️ Browse Products",

        # Order History & Details
        "order_history_title": "{icon_orders} <b>Order History</b>",
        "order_history_empty": (
            "🛒 No orders yet\n"
            "🛍️ Browse shop to purchase"
        ),
        "order_history_page": "{icon_orders} <b>Order History (Page {page}/{total_pages})</b>",
        "order_not_found": "Order not found.",
        "order_preparing": "Paid. Your item is being prepared and will be delivered here shortly.",
        "order_detail_title": "{icon_orders} <b>Order #{id} Details</b>",
        "order_product": "Product",
        "order_price_paid": "Price Paid",
        "order_date": "Date",
        "order_status": "Status",
        "order_credentials": "Delivered Credentials",

        # Balance / Deposit History & Details
        "balance_history_title": "{icon_stats} <b>Balance History</b>",
        "balance_history_empty": (
            "💳 No transactions yet\n"
            "⚡ Top up wallet to buy"
        ),
        "balance_history_page": "{icon_stats} <b>Balance History (Page {page}/{total_pages})</b>",
        "deposit_not_found": "Deposit record not found.",
        "deposit_detail_title": "{icon_stats} <b>Deposit #{id} Details</b>",
        "status_approved_msg": "Your payment was verified and balance was added to your account.",
        "status_rejected_msg": "This deposit request was rejected.",
        "status_pending_msg": "Your payment submission is being reviewed by our team.",
        "deposit_amount": "Amount",
        "deposit_method": "Method",
        "deposit_trxid": "Transaction ID",
        "deposit_submitted_at": "Submitted",
        "deposit_reviewed_at": "Reviewed",
        "deposit_admin_note": "Admin Note",
        "status_approved": "APPROVED",
        "status_rejected": "REJECTED",
        "status_pending": "PENDING REVIEW",
        "status_completed": "DELIVERED",
        "status_refunded": "REFUNDED",
        "status_waiting": "PREPARING",
        "status_completed_msg": "Your order was delivered successfully.",
        "status_refunded_msg": "This order was cancelled and refunded to your wallet.",
        "status_waiting_msg": "Your item is being prepared and will be delivered shortly.",

        "deposit_choose_method": (
            "{icon_deposit} <b>Add Balance</b>\n\n"
            "{icon_coin} <b>Balance:</b> {balance}\n\n"
            "{icon_lightning} <b>Select Method:</b>"
        ),
        "deposit_paused_title": "{icon_warning} <b>Deposits Temporarily Paused</b>",
        "deposit_pending_summary": (
            "{icon_timer} <b>Deposit #{id} Pending Review</b>\n\n"
            "Method: {method}\n"
            "Amount: {amount}\n"
            "TrxID: <code>{trxid}</code>\n\n"
            "<i>Balance will be credited once verified by an admin.</i>"
        ),
        "deposit_enter_amount_prompt": "{icon_money} <b>Enter deposit amount:</b>\n\n💡 <i>(e.g. 100)</i>",
        "deposit_enter_txid_prompt": "{icon_next} <b>Please enter the correct TrxID:</b>\n\n💡 <i>e.g. <code>BLA7X8Y9Z0</code></i>",
        "deposit_trxid_used": "{icon_cross} This TrxID has already been used.",
        "deposit_amount_mismatch": "{icon_cross} Payment amount does not match. Tap 'Change Amount' to fix.",
        "deposit_invalid_trxid": "{icon_cross} Invalid TrxID. Please check your SMS / receipt and enter the correct TrxID.",
        "deposit_tries_left": "Tries left: {tries}",
        "deposit_submitted_notice": (
            "{icon_check} <b>Deposit request submitted!</b>\n"
            "Method: {method}\n"
            "Amount: {amount}\n"
            "An admin will review it and add your balance."
        ),
    },

    "bn": {
        # Buttons
        "btn_add_balance": "💳 অ্যাড ব্যালেন্স",
        "btn_search": "🔍 সার্চ",
        "btn_refer_earn": "🎁 রেফার ও ইনকাম",
        "btn_profile": "👤 আমার প্রোফাইল",
        "btn_support": "🎧 সাপোর্ট",
        "btn_become_reseller": "💼 রিসেলার হন",
        "btn_reseller_panel": "💼 রিসেলার প্যানেল",
        "btn_admin_panel": "👑 অ্যাডমিন প্যানেল",
        "btn_other_products": "🛍️ অন্যান্য প্রোডাক্ট",
        "btn_all_products": "🛍️ সকল প্রোডাক্ট",
        "btn_my_orders": "📦 আমার অর্ডার",
        "btn_my_balance": "💰 আমার ব্যালেন্স",
        "btn_order_history": "📦 অর্ডার হিস্ট্রি",
        "btn_balance_history": "📊 ব্যালেন্স হিস্ট্রি",
        "btn_change_language": "🌐 ভাষা",
        "btn_back": "🔙 পিছনে",
        "btn_close": "❌ বন্ধ",
        "btn_confirm": "নিশ্চিত করুন",
        "btn_cancel": "বাতিল",
        "btn_copy_format": "ফরম্যাট কপি করুন",
        "btn_contact_management": "ম্যানেজমেন্ট যোগাযোগ",
        "btn_deposit_menu": "ডিপোজিট মেনু",
        "btn_main_menu": "মেইন মেনু",
        "btn_share_referral": "🚀 লিংক শেয়ার",
        "btn_copy_link": "📋 লিংক কপি",
        "btn_view_terms": "শর্তাবলী দেখুন",
        "btn_pay": "পেমেন্ট করুন {amount}",
        "btn_ive_paid": "টাকা পাঠিয়েছি",
        "btn_cancel_invoice": "ইনভয়েস বাতিল",
        "btn_keep": "রাখুন",

        # Language Selection
        "select_language_title": "🌐 <b>ভাষা</b>",
        "select_language_prompt": (
            "🌐 <b>ভাষা</b>\n\n"
            "<b>বর্তমান:</b> 🇧🇩 বাংলা\n"
            "🔄 পরিবর্তন করতে নিচে চাপুন"
        ),
        "lang_switched_toast": "✅ ভাষা সফলভাবে পরিবর্তন করে বাংলা করা হয়েছে!",

        # Welcome / Start
        "welcome_default": "{icon_sparkles} <b>{store_name}</b>-এ আপনাকে স্বাগতম!",
        "maintenance_notice": "{icon_warning} <b>রক্ষণাবেক্ষণ নোটিশ:</b> {notice}\n\n",

        # Profile / Wallet
        "wallet_title": "আপনার ওয়ালেট",
        "wallet_current_balance": "বর্তমান ব্যালেন্স",
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
        "rank_standard": "সাধারণ",
        "rank_reseller": "রিসেলার",

        # Refer & Earn
        "referral_title": "{icon_refer} <b>রেফার ও ইনকাম</b>",
        "referral_step_1": "1️⃣ ইনভাইট লিংক শেয়ার করুন",
        "referral_step_2": "2️⃣ বন্ধু লিংকে জয়েন করবে",
        "referral_step_3": "3️⃣ পেয়ে যাবেন <b>{reward}</b> বোনাস!",
        "referral_stats_header": "{icon_stats} <b>আপনার পরিসংখ্যান:</b>",
        "stats_title": "পরিসংখ্যান",
        "referral_tagline": "বন্ধুদের সাথে আপনার রেফারেল লিংক শেয়ার করুন এবং আকর্ষণীয় বোনাস আয় করুন!",
        "referral_link_label": "আপনার রেফারেল লিংক",
        "referral_reward_notice": "• আপনার লিংকে বন্ধু জয়েন করলেই পাবেন <b>{reward}</b> ইনস্ট্যান্ট বোনাস।",
        "referral_stat_total": "মোট রেফার",
        "referral_stat_earned": "মোট আয়",

        # Support
        "support_title": "{icon_support} <b>সাপোর্ট</b>",
        "support_text": (
            "অর্ডার বা ওয়ালেট সংক্রান্ত দ্রুত সহায়তার জন্য আমাদের ইনবক্স করুন:\n\n"
            "⏰ ২৪/৭ লাইভ সাপোর্ট\n"
            "⚡ দ্রুত রেসপন্স"
        ),
        "support_unavailable": (
            "সাপোর্ট চ্যাট বর্তমানে বন্ধ আছে। অনুগ্রহ করে আমাদের গাইড বা চ্যানেল দেখুন:\n\n"
            "⏰ ২৪/৭ লাইভ সাপোর্ট\n"
            "⚡ দ্রুত রেসপন্স"
        ),

        # Reseller
        "reseller_apply_title": "{icon_reseller} <b>রিসেলার হন</b>",
        "reseller_panel_title": "{icon_reseller} <b>রিসেলার প্যানেল</b>",
        "reseller_apply_text": (
            "আমাদের বটে রিসেলার হতে চাইলে নিচের তথ্যগুলো পূরণ করে আমাদের <b>Contact Management</b> এ মেসেজ পাঠান।"
        ),

        # Search
        "search_title": "🔍 <b>সার্চ</b>",
        "search_prompt": "আপনি যে প্রোডাক্টটি খুঁজছেন তার নাম লিখুন:",
        "search_try": "যেমন",
        "reseller_format_label": "আবেদন ফরম্যাট",
        "reseller_benefits_title": "রিসেলার সুবিধাসমূহ",
        "reseller_b1": "হোলসেল রেট ও বিশেষ ডিসকাউন্ট",
        "reseller_b2": "বট বা ওয়েবসাইটে ইন্টিগ্রেশনের জন্য REST API Key",
        "reseller_b3": "স্বয়ংক্রিয় ও তাত্ক্ষণিক ডেলিভারি",
        "reseller_b4": "২৪/৭ সরাসরি ম্যানেজমেন্ট সহায়তা",

        # Deposit
        "deposit_select_method": (
            "{icon_deposit} <b>ব্যালেন্স অ্যাড করুন</b>\n\n"
            "ওয়ালেটে টাকা যোগ করতে নিচের যেকোনো পেমেন্ট মেথড বেছে নিন।\n"
            "বর্তমান ব্যালেন্স: <b>{balance}</b>"
        ),
        "deposit_pending_warning": (
            "{icon_timer} <b>পেন্ডিং ডিপোজিট রিকোয়েস্ট</b>\n\n"
            "আপনার ইতিমধ্যে <b>{method}</b> মেথডে <b>{price}</b> এর একটি ডিপোজিট প্রক্রিয়াধীন রয়েছে।\n\n"
            "নতুন ডিপোজিট করার আগে অনুগ্রহ করে আগেরটি সম্পন্ন হওয়া পর্যন্ত অপেক্ষা করুন।"
        ),
        "deposit_closed": "{icon_warning} <b>ডিপোজিট সাময়িকভাবে বন্ধ আছে</b>\n\n{notice}",
        "deposit_unavailable": "{icon_warning} <b>ডিপোজিট অনুপলব্ধ</b>\n\nবর্তমানে কোনো পেমেন্ট মেথড উপলব্ধ নেই।",
        "deposit_enter_amount": "{icon_money} <b>কত টাকা অ্যাড করবেন তা লিখুন:</b>\n\n💡 <i>(যেমন: 100)</i>",
        # Navigation & Pagination Buttons
        "btn_refresh": "রিফ্রেশ",
        "btn_next": "পরবর্তী",
        "btn_prev": "পূর্ববর্তী",
        "btn_copy_credentials": "ক্রেডেনশিয়াল কপি",
        "btn_copy_trxid": "TrxID কপি",
        "btn_copy_number": "নম্বর কপি করুন",
        "btn_copy_uid": "Binance UID কপি",
        "btn_payment_done": "পেমেন্ট সম্পন্ন",
        "btn_change_amount": "টাকা পরিবর্তন",
        "btn_change_method": "মেথড পরিবর্তন",
        "btn_open_payment_page": "পেমেন্ট পেজ খুলুন",
        "btn_support_chat": "💬 সাপোর্ট ইনবক্স",
        "btn_guide": "📖 গাইড",
        "btn_cancel_deposit": "ডিপোজিট বাতিল",
        "btn_browse_products": "🛍️ প্রোডাক্ট ব্রাউজ করুন",

        # Order History & Details
        "order_history_title": "{icon_orders} <b>অর্ডার হিস্ট্রি</b>",
        "order_history_empty": (
            "🛒 কোনো অর্ডার নেই\n"
            "🛍️ কিনতে শপ ব্রাউজ করুন"
        ),
        "order_history_page": "{icon_orders} <b>অর্ডার হিস্ট্রি (পৃষ্ঠা {page}/{total_pages})</b>",
        "order_not_found": "অর্ডার খুঁজে পাওয়া যায়নি।",
        "order_preparing": "পেইড। আপনার প্রোডাক্ট প্রস্তুত হচ্ছে এবং শীঘ্রই ডেলিভারি দেওয়া হবে।",
        "order_detail_title": "{icon_orders} <b>অর্ডার #{id} বিবরণ</b>",
        "order_product": "প্রোডাক্ট",
        "order_price_paid": "মূল্য পরিশোধিত",
        "order_date": "তারিখ",
        "order_status": "স্ট্যাটাস",
        "order_credentials": "ডেলিভারিকৃত ক্রেডেনশিয়াল",

        # Balance / Deposit History & Details
        "balance_history_title": "{icon_stats} <b>ব্যালেন্স হিস্ট্রি</b>",
        "balance_history_empty": (
            "💳 কোনো লেনদেন নেই\n"
            "⚡ ব্যালেন্স যোগ করুন"
        ),
        "balance_history_page": "{icon_stats} <b>ব্যালেন্স হিস্ট্রি (পৃষ্ঠা {page}/{total_pages})</b>",
        "deposit_not_found": "ডিপোজিট রেকর্ড পাওয়া যায়নি।",
        "deposit_detail_title": "{icon_stats} <b>ডিপোজিট #{id} বিবরণ</b>",
        "status_approved_msg": "আপনার পেমেন্ট সফলভাবে যাচাই হয়েছে এবং ব্যালেন্স যোগ হয়েছে।",
        "status_rejected_msg": "এই ডিপোজিট রিকোয়েস্টটি বাতিল করা হয়েছে।",
        "status_pending_msg": "আপনার পেমেন্ট বর্তমানে অ্যাডমিন রিভিউয়ের অধীনে রয়েছে।",
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
        "status_completed_msg": "আপনার অর্ডারটি সফলভাবে ডেলিভারি করা হয়েছে।",
        "status_refunded_msg": "এই অর্ডারটি বাতিল করে ব্যালেন্স ওয়ালেটে ফেরত দেওয়া হয়েছে।",
        "status_waiting_msg": "আপনার আইটেম প্রস্তুত করা হচ্ছে, শীঘ্রই ডেলিভারি করা হবে।",

        "deposit_choose_method": (
            "{icon_deposit} <b>অ্যাড ব্যালেন্স</b>\n\n"
            "{icon_coin} <b>ব্যালেন্স:</b> {balance}\n\n"
            "{icon_lightning} <b>মেথড বেছে নিন:</b>"
        ),
        "deposit_paused_title": "{icon_warning} <b>ডিপোজিট সাময়িকভাবে বন্ধ আছে</b>",
        "deposit_pending_summary": (
            "{icon_timer} <b>ডিপোজিট #{id} পর্যালোচনাধীন</b>\n\n"
            "মেথড: {method}\n"
            "পরিমাণ: {amount}\n"
            "TrxID: <code>{trxid}</code>\n\n"
            "<i>অ্যাডমিন যাচাই করার পর আপনার একাউন্টে ব্যালেন্স যোগ হবে।</i>"
        ),
        "deposit_enter_amount_prompt": "{icon_money} <b>কত টাকা অ্যাড করবেন তা লিখুন:</b>\n\n💡 <i>(যেমন: 100)</i>",
        "deposit_enter_txid_prompt": "{icon_next} <b>সঠিক TrxID প্রদান করুন:</b>\n\n💡 <i>যেমন: <code>BLA7X8Y9Z0</code></i>",
        "deposit_trxid_used": "{icon_cross} এই TrxID আগেই ব্যবহার করা হয়েছে।",
        "deposit_amount_mismatch": "{icon_cross} টাকার পরিমাণ মিলেনি। ঠিক করতে 'টাকা পরিবর্তন' বাটনে ক্লিক করুন।",
        "deposit_invalid_trxid": "{icon_cross} ভুল TrxID। SMS বা রিসিট দেখে সঠিক TrxID দিন।",
        "deposit_tries_left": "বাকি চেষ্টা: {tries}",
        "deposit_submitted_notice": (
            "{icon_check} <b>ডিপোজিট রিকোয়েস্ট জমা হয়েছে!</b>\n"
            "মেথড: {method}\n"
            "পরিমাণ: {amount}\n"
            "অ্যাডমিন চেক করে ব্যালেন্স যোগ করবেন।"
        ),
    },

    "hi": {
        # Buttons
        "btn_add_balance": "💳 बैलेंस जोड़ें",
        "btn_search": "🔍 खोजें",
        "btn_refer_earn": "🎁 रेफर और कमाएं",
        "btn_profile": "👤 मेरी प्रोफाइल",
        "btn_support": "🎧 सहायता",
        "btn_become_reseller": "💼 रीसेलर बनें",
        "btn_reseller_panel": "💼 रीसेलर पैनल",
        "btn_admin_panel": "👑 एडमिन पैनल",
        "btn_other_products": "🛍️ अन्य उत्पाद",
        "btn_all_products": "🛍️ सभी उत्पाद",
        "btn_my_orders": "📦 मेरे ऑर्डर",
        "btn_my_balance": "💰 मेरा बैलेंस",
        "btn_order_history": "📦 ऑर्डर इतिहास",
        "btn_balance_history": "📊 बैलेंस इतिहास",
        "btn_change_language": "🌐 भाषा",
        "btn_back": "🔙 वापस",
        "btn_close": "❌ बंद करें",
        "btn_confirm": "पुष्टि करें",
        "btn_cancel": "रद्द करें",
        "btn_copy_format": "फॉर्मेट कॉपी करें",
        "btn_contact_management": "प्रबंधन से संपर्क करें",
        "btn_deposit_menu": "डिपॉजिट मेनू",
        "btn_main_menu": "मुख्य मेनू",
        "btn_share_referral": "🚀 लिंक शेयर",
        "btn_copy_link": "📋 लिंक कॉपी",
        "btn_view_terms": "नियम व शर्तें",
        "btn_pay": "भुगतान करें {amount}",
        "btn_ive_paid": "मैंने भुगतान कर दिया",
        "btn_cancel_invoice": "इनवॉइस रद्द करें",
        "btn_keep": "रखें",

        # Language Selection
        "select_language_title": "🌐 <b>भाषा</b>",
        "select_language_prompt": (
            "🌐 <b>भाषा</b>\n\n"
            "<b>वर्तमान:</b> 🇮🇳 हिन्दी\n"
            "🔄 बदलने के लिए नीचे टैप करें"
        ),
        "lang_switched_toast": "✅ भाषा सफलतापूर्वक बदलकर हिन्दी कर दी गई है!",

        # Welcome / Start
        "welcome_default": "{icon_sparkles} <b>{store_name}</b> में आपका स्वागत है!",
        "maintenance_notice": "{icon_warning} <b>रखरखाव सूचना:</b> {notice}\n\n",

        # Profile / Wallet
        "wallet_title": "आपका वॉलेट",
        "wallet_current_balance": "उपलब्ध बैलेंस",
        "profile_title": "{icon_account} <b>मेरी प्रोफाइल</b>",
        "account_info_title": "खाता जानकारी",
        "wallet_orders_title": "वॉलेट और ऑर्डर्स",
        "profile_name": "नाम",
        "profile_username": "यूज़रनेम",
        "profile_user_id": "यूज़र आईडी",
        "profile_account_type": "रैंक",
        "profile_current_balance": "बैलेंस",
        "profile_total_orders": "ऑर्डर्स",
        "profile_total_spent": "खर्च",
        "profile_referrals": "रेफरल",
        "profile_referral_link": "रेफरल लिंक",
        "rank_standard": "सामान्य",
        "rank_reseller": "रीसेलर",

        # Refer & Earn
        "referral_title": "{icon_refer} <b>रेफर और कमाएं</b>",
        "referral_step_1": "1️⃣ इनवाइट लिंक साझा करें",
        "referral_step_2": "2️⃣ दोस्त लिंक से जुड़ेगा",
        "referral_step_3": "3️⃣ पाएं <b>{reward}</b> बोनस!",
        "referral_stats_header": "{icon_stats} <b>आपके आंकड़े:</b>",
        "stats_title": "आंकड़े",
        "referral_tagline": "दोस्तों के साथ अपना रेफरल लिंक साझा करें और नकद पुरस्कार कमाएं!",
        "referral_link_label": "आपका रेफरल लिंक",
        "referral_reward_notice": "• आपके लिंक से दोस्त के जुड़ते ही पाएं <b>{reward}</b> बोनस।",
        "referral_stat_total": "कुल रेफरल",
        "referral_stat_earned": "कुल कमाई",

        # Support
        "support_title": "{icon_support} <b>सहायता</b>",
        "support_text": (
            "अपने ऑर्डर या वॉलेट से संबंधित त्वरित सहायता के लिए हमें संदेश भेजें:\n\n"
            "⏰ 24/7 लाइव सहायता\n"
            "⚡ त्वरित प्रतिक्रिया"
        ),
        "support_unavailable": (
            "सहायता चैट वर्तमान में ऑफलाइन है। कृपया हमारी गाइड या चैनल देखें:\n\n"
            "⏰ 24/7 लाइव सहायता\n"
            "⚡ त्वरित प्रतिक्रिया"
        ),

        # Reseller
        "reseller_apply_title": "{icon_reseller} <b>रीसेलर बनें</b>",
        "reseller_panel_title": "{icon_reseller} <b>रीसेलर पैनल</b>",
        "reseller_apply_text": (
            "यदि आप हमारे बॉट में रीसेलर बनना चाहते हैं, तो नीचे दिए गए विवरण भरकर हमारे <b>Contact Management</b> को संदेश भेजें।"
        ),

        # Search
        "search_title": "🔍 <b>खोजें</b>",
        "search_prompt": "आप जो प्रोडक्ट खोज रहे हैं उसका नाम लिखें:",
        "search_try": "उदाहरण",
        "reseller_format_label": "आवेदन प्रारूप",
        "reseller_benefits_title": "रीसेलर लाभ",
        "reseller_b1": "थोक छूट और विशेष रीसेलर दरें",
        "reseller_b2": "बॉट या वेबसाइट को जोड़ने के लिए REST API Key",
        "reseller_b3": "त्वरित और स्वचालित क्रेडेंशियल्स डिलीवरी",
        "reseller_b4": "24/7 सीधा प्रबंधन संपर्क",

        # Deposit
        "deposit_select_method": (
            "{icon_deposit} <b>बैलेंस जोड़ें</b>\n\n"
            "अपने वॉलेट को टॉप-अप करने के लिए नीचे दी गई भुगतान विधि चुनें।\n"
            "वर्तमान बैलेंस: <b>{balance}</b>"
        ),
        "deposit_pending_warning": (
            "{icon_timer} <b>लंबित डिपॉजिट अनुरोध</b>\n\n"
            "आपके पास पहले से ही <b>{method}</b> के माध्यम से <b>{price}</b> का एक डिपॉजिट लंबित है।\n\n"
            "कृपया नया अनुरोध बनाने से पहले इसके पूरा होने की प्रतीक्षा करें।"
        ),
        "deposit_closed": "{icon_warning} <b>डिपॉजिट अस्थायी रूप से बंद है</b>\n\n{notice}",
        "deposit_unavailable": "{icon_warning} <b>डिपॉजिट अनुपलब्ध</b>\n\nवर्तमान में कोई भुगतान विधि उपलब्ध नहीं है।",
        "deposit_enter_amount": "{icon_money} <b>डिपॉजिट राशि दर्ज करें:</b>\n\n💡 <i>(उदा. 100)</i>",
        # Navigation & Pagination Buttons
        "btn_refresh": "रिफ्रेश",
        "btn_next": "आगे",
        "btn_prev": "पीछे",
        "btn_copy_credentials": "क्रेडेंशियल कॉपी",
        "btn_copy_trxid": "TrxID कॉपी",
        "btn_copy_number": "नंबर कॉपी करें",
        "btn_copy_uid": "Binance UID कॉपी",
        "btn_payment_done": "भुगतान हो गया",
        "btn_change_amount": "राशि बदलें",
        "btn_change_method": "तरीका बदलें",
        "btn_open_payment_page": "भुगतान पेज खोलें",
        "btn_support_chat": "💬 सहायता इनबॉक्स",
        "btn_guide": "📖 गाइड",
        "btn_cancel_deposit": "डिपॉजिट रद्द करें",
        "btn_browse_products": "🛍️ उत्पाद ब्राउज़ करें",

        # Order History & Details
        "order_history_title": "{icon_orders} <b>ऑर्डर इतिहास</b>",
        "order_history_empty": (
            "🛒 कोई ऑर्डर नहीं है\n"
            "🛍️ खरीदने के लिए दुकान देखें"
        ),
        "order_history_page": "{icon_orders} <b>ऑर्डर इतिहास (पृष्ठ {page}/{total_pages})</b>",
        "order_not_found": "ऑर्डर नहीं मिला।",
        "order_preparing": "भुगतान किया गया। आपका आइटम तैयार किया जा रहा है और जल्द ही दिया जाएगा।",
        "order_detail_title": "{icon_orders} <b>ऑर्डर #{id} विवरण</b>",
        "order_product": "उत्पाद",
        "order_price_paid": "भुगतान की गई राशि",
        "order_date": "दिनांक",
        "order_status": "स्थिति",
        "order_credentials": "डिलीवर किए गए क्रेडेंशियल्स",

        # Balance / Deposit History & Details
        "balance_history_title": "{icon_stats} <b>बैलेंस इतिहास</b>",
        "balance_history_empty": (
            "💳 कोई लेनदेन नहीं है\n"
            "⚡ वॉलेट में बैलेंस जोड़ें"
        ),
        "balance_history_page": "{icon_stats} <b>बैलेंस इतिहास (पृष्ठ {page}/{total_pages})</b>",
        "deposit_not_found": "डिपॉजिट रिकॉर्ड नहीं मिला।",
        "deposit_detail_title": "{icon_stats} <b>डिपॉजिट #{id} विवरण</b>",
        "status_approved_msg": "आपका भुगतान सत्यापित हो गया है और बैलेंस खाते में जोड़ दिया गया है।",
        "status_rejected_msg": "यह डिपॉजिट अनुरोध अस्वीकार कर दिया गया था।",
        "status_pending_msg": "आपका भुगतान वर्तमान में हमारी टीम द्वारा समीक्षाधीन है।",
        "deposit_amount": "राशि",
        "deposit_method": "विधि",
        "deposit_trxid": "ट्रांजेक्शन आईडी",
        "deposit_submitted_at": "जमा किया गया",
        "deposit_reviewed_at": "समीक्षा की गई",
        "deposit_admin_note": "एडमिन नोट",
        "status_approved": "स्वीकृत",
        "status_rejected": "अस्वीकृत",
        "status_pending": "समीक्षाधीन",
        "status_completed": "डिलीवर किया गया",
        "status_refunded": "रिफंड",
        "status_waiting": "तैयार किया जा रहा है",
        "status_completed_msg": "आपका ऑर्डर सफलतापूर्वक डिलीवर कर दिया गया है।",
        "status_refunded_msg": "यह ऑर्डर रद्द कर दिया गया है और बैलेंस वापस कर दिया गया है।",
        "status_waiting_msg": "आपका आइटम तैयार किया जा रहा है, जल्द ही डिलीवर होगा।",

        "deposit_choose_method": (
            "{icon_deposit} <b>बैलेंस जोड़ें</b>\n\n"
            "{icon_coin} <b>बैलेंस:</b> {balance}\n\n"
            "{icon_lightning} <b>विधि चुनें:</b>"
        ),
        "deposit_paused_title": "{icon_warning} <b>डिपॉजिट अस्थायी रूप से बंद है</b>",
        "deposit_pending_summary": (
            "{icon_timer} <b>डिपॉजिट #{id} समीक्षाधीन</b>\n\n"
            "विधि: {method}\n"
            "राशि: {amount}\n"
            "TrxID: <code>{trxid}</code>\n\n"
            "<i>एडमिन द्वारा जांच के बाद बैलेंस खाते में जोड़ दिया जाएगा।</i>"
        ),
        "deposit_enter_amount_prompt": "{icon_money} <b>डिपॉजिट राशि दर्ज करें:</b>\n\n💡 <i>(उदा. 100)</i>",
        "deposit_enter_txid_prompt": "{icon_next} <b>कृपया सही TrxID दर्ज करें:</b>\n\n💡 <i>उदा. <code>BLA7X8Y9Z0</code></i>",
        "deposit_trxid_used": "{icon_cross} यह TrxID पहले ही उपयोग किया जा चुका है।",
        "deposit_amount_mismatch": "{icon_cross} भुगतान राशि मेल नहीं खाती। ठीक करने के लिए 'राशि बदलें' दबाएं।",
        "deposit_invalid_trxid": "{icon_cross} अमान्य TrxID। SMS या रसीद जांचें और सही TrxID दर्ज करें।",
        "deposit_tries_left": "शेष प्रयास: {tries}",
        "deposit_submitted_notice": (
            "{icon_check} <b>डिपॉजिट अनुरोध सबमिट हो गया!</b>\n"
            "विधि: {method}\n"
            "राशि: {amount}\n"
            "एडमिन जांच के बाद बैलेंस जोड़ देंगे।"
        ),
    },

    "ur": {
        # Buttons
        "btn_add_balance": "💳 بیلنس شامل کریں",
        "btn_search": "🔍 تلاش کریں",
        "btn_refer_earn": "🎁 ریفر اور کمائیں",
        "btn_profile": "👤 میری پروفائل",
        "btn_support": "🎧 سپورٹ",
        "btn_become_reseller": "💼 ری سیلر بنیں",
        "btn_reseller_panel": "💼 ری سیلر پینل",
        "btn_admin_panel": "👑 ایڈمن پینل",
        "btn_other_products": "🛍️ دیگر مصنوعات",
        "btn_all_products": "🛍️ تمام مصنوعات",
        "btn_my_orders": "📦 میرے آرڈرز",
        "btn_my_balance": "💰 میرا بیلنس",
        "btn_order_history": "📦 آرڈر ہسٹری",
        "btn_balance_history": "📊 بیلنس ہسٹری",
        "btn_change_language": "🌐 زبان",
        "btn_back": "🔙 واپس",
        "btn_close": "❌ بند کریں",
        "btn_confirm": "تصدیق کریں",
        "btn_cancel": "منسوخ کریں",
        "btn_copy_format": "فارمیٹ کاپی کریں",
        "btn_contact_management": "انتظامیہ سے رابطہ",
        "btn_deposit_menu": "ڈپازٹ مینو",
        "btn_main_menu": "مین مینو",
        "btn_share_referral": "🚀 لنک شیئر",
        "btn_copy_link": "📋 لنک کاپی",
        "btn_view_terms": "شرائط و ضوابط",
        "btn_pay": "ادائیگی کریں {amount}",
        "btn_ive_paid": "میں نے ادائیگی کر دی ہے",
        "btn_cancel_invoice": "انوائس منسوخ کریں",
        "btn_keep": "رکھیں",

        # Language Selection
        "select_language_title": "🌐 <b>زبان</b>",
        "select_language_prompt": (
            "🌐 <b>زبان</b>\n\n"
            "<b>موجودہ:</b> 🇵🇰 اردو\n"
            "🔄 تبدیل کرنے کے لیے نیچے ٹیپ کریں"
        ),
        "lang_switched_toast": "✅ زبان کامیابی کے ساتھ اردو میں تبدیل کر دی گئی ہے!",

        # Welcome / Start
        "welcome_default": "{icon_sparkles} <b>{store_name}</b> میں خوش آمدید!",
        "maintenance_notice": "{icon_warning} <b>مینٹیننس نوٹس:</b> {notice}\n\n",

        # Profile / Wallet
        "wallet_title": "آپ کا والٹ",
        "wallet_current_balance": "دستیاب بیلنس",
        "profile_title": "{icon_account} <b>میری پروفائل</b>",
        "account_info_title": "اکاؤنٹ کی معلومات",
        "wallet_orders_title": "والٹ اور آرڈرز",
        "profile_name": "نام",
        "profile_username": "یوزر نیم",
        "profile_user_id": "صارف شناختی",
        "profile_account_type": "رینک",
        "profile_current_balance": "بیلنس",
        "profile_total_orders": "آرڈرز",
        "profile_total_spent": "خرچ",
        "profile_referrals": "ریفرلز",
        "profile_referral_link": "ریفرل لنک",
        "rank_standard": "عام",
        "rank_reseller": "ری سیلر",

        # Refer & Earn
        "referral_title": "{icon_refer} <b>ریفر اور کمائیں</b>",
        "referral_step_1": "1️⃣ انوائٹ لنک شیئر کریں",
        "referral_step_2": "2️⃣ دوست لنک سے جوائن کرے گا",
        "referral_step_3": "3️⃣ پائیں <b>{reward}</b> بونس!",
        "referral_stats_header": "{icon_stats} <b>آپ کے اعداد و شمار:</b>",
        "stats_title": "اعداد و شمار",
        "referral_tagline": "اپنے ریفرل لنک کو دوستوں کے ساتھ شیئر کریں اور نقد بونس حاصل کریں!",
        "referral_link_label": "آپ کا ریفرل لنک",
        "referral_reward_notice": "• آپ کے لنک سے دوست کے جوائن کرتے ہی پائیں <b>{reward}</b> بونس۔",
        "referral_stat_total": "کل ریفرلز",
        "referral_stat_earned": "کل کمائی",

        # Support
        "support_title": "{icon_support} <b>سپورٹ</b>",
        "support_text": (
            "اپنے آرڈرز یا والٹ سے متعلق فوری مدد کے لیے ہمیں میسج کریں:\n\n"
            "⏰ 24/7 لائیو سپورٹ\n"
            "⚡ فوری جواب"
        ),
        "support_unavailable": (
            "سپورٹ چیٹ فی الحال آف لائن ہے۔ براہ کرم ہماری گائیڈ یا چینلز دیکھیں:\n\n"
            "⏰ 24/7 لائیو سپورٹ\n"
            "⚡ فوری جواب"
        ),

        # Reseller
        "reseller_apply_title": "{icon_reseller} <b>ری سیلر بنیں</b>",
        "reseller_panel_title": "{icon_reseller} <b>ری سیلر پینل</b>",
        "reseller_apply_text": (
            "اگر آپ ہمارے بوٹ میں ری سیلر بننا چاہتے ہیں تو نیچے دی گئی تفصیلات پر کر کے ہمارے <b>Contact Management</b> کو میسج بھیجیں۔"
        ),

        # Search
        "search_title": "🔍 <b>تلاش</b>",
        "search_prompt": "جو پروڈکٹ آپ تلاش کر رہے ہیں اس کا نام لکھیں:",
        "search_try": "مثال",
        "reseller_format_label": "درخواست کا فارمیٹ",
        "reseller_benefits_title": "ری سیلر فوائد",
        "reseller_b1": "ہول سیل ڈسکاؤنٹ اور خصوصی ری سیلر ریٹس",
        "reseller_b2": "بوٹ یا ویب سائٹ کے ساتھ جوڑنے کے لیے REST API Key",
        "reseller_b3": "فوری اور خودکار ڈیلیوری",
        "reseller_b4": "24/7 انتظامیہ تک براہ راست رسائی",

        # Deposit
        "deposit_select_method": (
            "{icon_deposit} <b>بیلنس شامل کریں</b>\n\n"
            "اپنے والٹ میں بیلنس شامل کرنے کے لیے نیچے دیے گئے ادائیگی کے طریقوں میں سے انتخاب کریں۔\n"
            "موجودہ بیلنس: <b>{balance}</b>"
        ),
        "deposit_pending_warning": (
            "{icon_timer} <b>زیر التواء ڈپازٹ درخواست</b>\n\n"
            "آپ کی پہلے ہی <b>{method}</b> کے ذریعے <b>{price}</b> کی ڈپازٹ درخواست زیر التواء ہے۔\n\n"
            "براہ کرم نیا ڈپازٹ کرنے سے پہلے پچھلی درخواست کے مکمل ہونے کا انتظار کریں۔"
        ),
        "deposit_closed": "{icon_warning} <b>ڈپازٹ عارضی طور پر بند ہے</b>\n\n{notice}",
        "deposit_unavailable": "{icon_warning} <b>ڈپازٹ دستیاب نہیں</b>\n\nفی الحال کوئی طریقہ ادائیگی دستیاب نہیں ہے۔",
        "deposit_enter_amount": "{icon_money} <b>ڈپازٹ کی رقم درج کریں:</b>\n\n💡 <i>(مثال: 100)</i>",
        # Navigation & Pagination Buttons
        "btn_refresh": "تازہ کریں",
        "btn_next": "اگلا",
        "btn_prev": "پچھلا",
        "btn_copy_credentials": "معلومات کاپی کریں",
        "btn_copy_trxid": "TrxID کاپی کریں",
        "btn_copy_number": "نمبر کاپی کریں",
        "btn_copy_uid": "Binance UID کاپی کریں",
        "btn_payment_done": "ادائیگی ہو گئی",
        "btn_change_amount": "رقم تبدیل کریں",
        "btn_change_method": "طریقہ تبدیل کریں",
        "btn_open_payment_page": "ادائیگی کا صفحہ کھولیں",
        "btn_support_chat": "💬 سپورٹ ان باکس",
        "btn_guide": "📖 گائیڈ",
        "btn_cancel_deposit": "ڈپازٹ منسوخ کریں",
        "btn_browse_products": "🛍️ مصنوعات براؤز کریں",

        # Order History & Details
        "order_history_title": "{icon_orders} <b>آرڈر ہسٹری</b>",
        "order_history_empty": (
            "🛒 کوئی آرڈر نہیں ہے\n"
            "🛍️ خریدنے کے لیے شاپ دیکھیں"
        ),
        "order_history_page": "{icon_orders} <b>آرڈر ہسٹری (صفحہ {page}/{total_pages})</b>",
        "order_not_found": "آرڈر نہیں ملا۔",
        "order_preparing": "ادائیگی ہو گئی۔ آپ کا آئٹم تیار کیا جا رہا ہے اور جلد ہی پہنچا دیا جائے گا۔",
        "order_detail_title": "{icon_orders} <b>آرڈر #{id} تفصیلات</b>",
        "order_product": "پروڈکٹ",
        "order_price_paid": "ادا شدہ رقم",
        "order_date": "تاریخ",
        "order_status": "حیثیت",
        "order_credentials": "فراہم کردہ تفصیلات",

        # Balance / Deposit History & Details
        "balance_history_title": "{icon_stats} <b>بیلنس ہسٹری</b>",
        "balance_history_empty": (
            "💳 کوئی لین دین نہیں ہے\n"
            "⚡ والٹ میں بیلنس شامل کریں"
        ),
        "balance_history_page": "{icon_stats} <b>بیلنس ہسٹری (صفحہ {page}/{total_pages})</b>",
        "deposit_not_found": "ڈپازٹ ریکارڈ نہیں ملا۔",
        "deposit_detail_title": "{icon_stats} <b>ڈپازٹ #{id} تفصیلات</b>",
        "status_approved_msg": "آپ کی ادائیگی کی تصدیق ہو گئی ہے اور بیلنس شامل کر دیا گیا ہے۔",
        "status_rejected_msg": "یہ ڈپازٹ درخواست مسترد کر دی گئی ہے۔",
        "status_pending_msg": "آپ کی ادائیگی اس وقت ہماری ٹیم کے زیر جائزہ ہے۔",
        "deposit_amount": "رقم",
        "deposit_method": "طریقہ",
        "deposit_trxid": "ٹرانزیکشن آئی ڈی",
        "deposit_submitted_at": "جمع کرایا گیا",
        "deposit_reviewed_at": "جائزہ لیا گیا",
        "deposit_admin_note": "ایڈمن نوٹ",
        "status_approved": "منظور شدہ",
        "status_rejected": "مسترد شدہ",
        "status_pending": "زیر جائزہ",
        "status_completed": "ڈیلیور شدہ",
        "status_refunded": "ریفنڈ شدہ",
        "status_waiting": "تیار کیا جا رہا ہے",
        "status_completed_msg": "آپ کا آرڈر کامیابی سے ڈیلیور کر دیا گیا ہے۔",
        "status_refunded_msg": "یہ آرڈر منسوخ کر دیا گیا ہے اور بیلنس واپس کر دیا گیا ہے۔",
        "status_waiting_msg": "آپ کا آئٹم تیار کیا جا رہا ہے، جلد ہی ڈیلیور ہو جائے گا۔",

        "deposit_choose_method": (
            "{icon_deposit} <b>بیلنس شامل کریں</b>\n\n"
            "{icon_coin} <b>بیلنس:</b> {balance}\n\n"
            "{icon_lightning} <b>طریقہ منتخب کریں:</b>"
        ),
        "deposit_paused_title": "{icon_warning} <b>ڈپازٹ عارضی طور پر بند ہے</b>",
        "deposit_pending_summary": (
            "{icon_timer} <b>ڈپازٹ #{id} زیر جائزہ</b>\n\n"
            "طریقہ: {method}\n"
            "رقم: {amount}\n"
            "TrxID: <code>{trxid}</code>\n\n"
            "<i>ایڈمن کی تصدیق کے بعد بیلنس شامل کر دیا جائے گا۔</i>"
        ),
        "deposit_enter_amount_prompt": "{icon_money} <b>ڈپازٹ کی رقم درج کریں:</b>\n\n💡 <i>(مثال: 100)</i>",
        "deposit_enter_txid_prompt": "{icon_next} <b>براہ کرم درست TrxID درج کریں:</b>\n\n💡 <i>مثال: <code>BLA7X8Y9Z0</code></i>",
        "deposit_trxid_used": "{icon_cross} یہ TrxID پہلے ہی استعمال ہو چکی ہے۔",
        "deposit_amount_mismatch": "{icon_cross} ادائیگی کی رقم مطابقت نہیں رکھتی۔ ٹھیک کرنے کے لیے 'رقم تبدیل کریں' پر کلک کریں۔",
        "deposit_invalid_trxid": "{icon_cross} غلط TrxID۔ براہ کرم رسید چیک کر کے درست TrxID درج کریں۔",
        "deposit_tries_left": "باقی کوششیں: {tries}",
        "deposit_submitted_notice": (
            "{icon_check} <b>ڈپازٹ درخواست جمع ہو گئی!</b>\n"
            "طریقہ: {method}\n"
            "رقم: {amount}\n"
            "ایڈمن تصدیق کے بعد بیلنس شامل کر دیں گے۔"
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
    """Normalize language code to one of ('en', 'bn', 'hi', 'ur')."""
    code = (lang or "").strip().lower()
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
