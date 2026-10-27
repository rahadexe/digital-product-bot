"""English-only customer-bot copy catalog.

Features:
  - Dynamic variable interpolation with kwargs
  - Legacy language codes resolve to English
"""

from __future__ import annotations

from typing import Any

SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native": "English", "flag": "🇬🇧"},
}

DEFAULT_LANGUAGE = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Buttons
        "btn_shop": "Products",
        "btn_wallet": "💰 Balance",
        "btn_deposit": "Top Up",
        "btn_add_balance": "Top Up",
        "btn_search": "🔍 Search",
        "btn_refer_earn": "Refer",
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
        "btn_my_balance": "Balance",
        "btn_order_history": "Orders",
        "btn_balance_history": "History",
        "btn_deposit_history": "History",
        "btn_change_language": "🌐 Language",
        "btn_back": "Back",
        "btn_close": "Close",
        "btn_confirm": "Confirm",
        "btn_cancel": "Cancel",
        "btn_copy_format": "📋 Copy Format",
        "btn_contact_management": "Contact Support",
        "btn_deposit_menu": "Balance",
        "btn_main_menu": "Menu",
        "btn_share_referral": "Share",
        "btn_copy_link": "Copy Link",
        "btn_view_terms": "📜 Terms & Conditions",
        "btn_pay": "💳 Pay {amount}",
        "btn_ive_paid": "Payment Done",
        "btn_cancel_invoice": "Cancel Payment",
        "btn_keep": "Keep Payment",

        # Language Selection
        "select_language_title": "Language",
        "select_language_prompt": "Select language:",
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
        "wallet_title": "Balance",
        "wallet_current_balance": "Available Balance",
        "account_title": "{icon_account} <b>My Account</b>",
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
        "support_text": "Need help with an order or your balance? Message us.",
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
        "balance_history_title": "<b>Deposit History</b>",
        "balance_history_hint": "",
        "balance_history_empty": "📜 No deposits yet.",
        "balance_history_page": "<b>Deposit History</b>",
        "deposit_not_found": "Top-up not found. Open Balance to check History.",
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
        "status_refunded_msg": "Order cancelled. Funds returned to your balance.",
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
}


def t(key: str, lang: str | None = "en", **kwargs: Any) -> str:
    """
    Get localized string by key and language code.
    Gracefully falls back to English ('en') if key or language is not found.
    Interpolates kwargs safely.
    """
    code = normalize_language(lang)

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
    """The customer bot currently supports English only."""
    code = (lang or "").strip().lower()
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
