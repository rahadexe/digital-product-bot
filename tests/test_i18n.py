from string import Formatter

import pytest

from app.bot.handlers.help_guide import GUIDE_TEXTS, get_guide_keyboard
from app.bot.handlers.navigation import COMMAND_ACTIONS, NAVIGATION_TEXTS
from app.bot.keyboards import (
    get_main_inline_keyboard,
    get_more_inline_keyboard,
    get_persistent_reply_keyboard,
)
from app.core.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TRANSLATIONS, t

def test_supported_languages():
    assert SUPPORTED_LANGUAGES == {
        "en": {"name": "English", "native": "English", "flag": "🇬🇧"},
    }

def test_i18n_translation_and_fallback():
    # English
    assert t("btn_add_balance", "en") == "Top Up"
    # Legacy saved preferences still resolve to English.
    assert t("btn_add_balance", "bn") == "Top Up"
    
    # Missing key fallback
    assert t("non_existent_key_xyz", "bn") == "non_existent_key_xyz"
    # Missing language fallback to English
    assert t("btn_add_balance", "fr") == "Top Up"

def test_i18n_interpolation():
    assert "500 BDT" in t("btn_pay", "en", amount="500 BDT")
    assert "500 BDT" in t("btn_pay", "bn", amount="500 BDT")

def test_translations_preserve_placeholders_across_languages():
    for key, english in TRANSLATIONS["en"].items():
        bengali = TRANSLATIONS["bn"].get(key)
        assert bengali is not None, f"Missing Bengali translation: {key}"
        english_fields = {
            field for _, field, _, _ in Formatter().parse(english) if field is not None
        }
        bengali_fields = {
            field for _, field, _, _ in Formatter().parse(bengali) if field is not None
        }
        assert bengali_fields == english_fields, f"Placeholder mismatch: {key}"

def test_guide_copy_and_support_action_are_english():
    assert "How to use the bot" in GUIDE_TEXTS["en"]
    button = get_guide_keyboard("en").inline_keyboard[0][0]
    assert button.text.endswith(t("btn_support", "en").split(" ", 1)[-1])
    assert button.callback_data == "open_support"

def test_language_specific_currency_formatting():
    from app.bot.formatting import format_dual_price, price
    # Bengali shows the local equivalent and the canonical USD wallet amount.
    assert format_dual_price(44.0, "৳", usd_rate=125.0, lang="bn") == "৳5,500 (≈$44)"
    assert price("৳", 44.0, usd_rate=125.0, lang="bn") == "৳5,500 (≈$44)"

    # English uses the canonical USD amount directly; exchange-rate settings do not rescale it.
    assert format_dual_price(125.0, "৳", usd_rate=125.0, lang="en") == "$125"
    assert price("৳", 125.0, usd_rate=125.0, lang="en") == "$125"
    assert "≈" not in format_dual_price(125.0, "৳", usd_rate=125.0, lang="en")

def test_customer_keyboards_are_english_and_secondary_menu_is_small():
    main_kb = get_main_inline_keyboard(lang="bn", is_admin=False)
    assert len(main_kb.inline_keyboard) == 3
    assert [button.text for row in main_kb.inline_keyboard for button in row] == [
        "🛍 Shop", "💰 Wallet", "📦 Orders", "🎁 Referral", "💬 Support",
    ]

    admin_kb = get_main_inline_keyboard(lang="bn", is_admin=True)
    assert len(admin_kb.inline_keyboard) == 4
    assert admin_kb.inline_keyboard[-1][0].text == "🛡 Admin Panel"
    more_kb = get_more_inline_keyboard(lang="bn", is_admin=True, is_reseller=True)
    assert [btn.callback_data for row in more_kb.inline_keyboard for btn in row] == [
        "open_api_hub", "open_reseller_hub",
    ]
    kb = get_persistent_reply_keyboard(is_reseller=False, is_admin=False, lang="bn")
    assert len(kb.keyboard) == 3
    assert kb.is_persistent is False
    assert kb.resize_keyboard is True
    kb_admin = get_persistent_reply_keyboard(is_reseller=False, is_admin=True, lang="bn")
    assert len(kb_admin.keyboard) == 4
    assert kb_admin.keyboard[-1][0].text == "🛡 Admin Panel"
    kb_cats = get_persistent_reply_keyboard(pinned_categories=[{"name": "VPN", "icon": "🛡️"}], lang="bn")
    assert len(kb_cats.keyboard) == 3

def test_navigation_texts_include_all_languages():
    # Check English
    assert NAVIGATION_TEXTS["💳 Add Balance"] == "deposit"
    assert NAVIGATION_TEXTS["💳 Wallet"] == "deposit"
    assert NAVIGATION_TEXTS["🛍️ Shop"] == "other_products"
    assert NAVIGATION_TEXTS["Shop"] == "other_products"
    assert NAVIGATION_TEXTS["🛍 Shop"] == "other_products"
    assert NAVIGATION_TEXTS["🛍 কেনাকাটা"] == "other_products"
    assert NAVIGATION_TEXTS["📦 Orders"] == "orders"
    assert NAVIGATION_TEXTS["🎧 Support"] == "support"
    # Check Bengali
    assert NAVIGATION_TEXTS["💳 অ্যাড ব্যালেন্স"] == "deposit"
    assert NAVIGATION_TEXTS["💳 ওয়ালেট"] == "deposit"
    assert NAVIGATION_TEXTS["🛍️ শপ"] == "shop"
    assert NAVIGATION_TEXTS["📦 আমার অর্ডার"] == "orders"
    assert NAVIGATION_TEXTS["🎧 সাপোর্ট"] == "support"

    # No language-switch commands remain.
    assert "/language" not in COMMAND_ACTIONS
    assert "/lang" not in COMMAND_ACTIONS
    assert "/bn" not in COMMAND_ACTIONS
    assert "/en" not in COMMAND_ACTIONS
    assert COMMAND_ACTIONS["/more"] == "more"

def test_history_translations():
    for lang in ["en", "bn"]:
        assert len(t("order_history_title", lang, icon_orders="📦")) > 0
        assert len(t("balance_history_title", lang, icon_stats="📊")) > 0
        assert len(t("order_history_empty", lang)) > 0
        assert len(t("balance_history_empty", lang)) > 0
        assert len(t("btn_browse_products", lang)) > 0
        assert len(t("btn_refresh", lang)) > 0
        assert len(t("btn_next", lang)) > 0
        assert len(t("btn_prev", lang)) > 0
        assert len(t("btn_back", lang)) > 0
        assert len(t("btn_close", lang)) > 0
        assert len(t("btn_copy_trxid", lang)) > 0
        assert len(t("btn_all_products", lang)) > 0
        assert len(t("account_info_title", lang)) > 0
        assert len(t("wallet_orders_title", lang)) > 0
        assert len(t("stats_title", lang)) > 0
        assert len(t("deposit_choose_method", lang, icon_deposit="💳", icon_coin="🪙", icon_lightning="⚡", balance="100 ৳")) > 0
        assert len(t("deposit_submitted_notice", lang, icon_check="✅", method="bKash", amount="100 BDT")) > 0

def test_categories_keyboard_no_duplicate_uncat():
    from app.bot.keyboards import get_categories_keyboard
    sample_categories = [
        {"id": 1, "name": "Streaming", "icon": "🎬"},
        {"id": 2, "name": "VPN", "icon": "🛡️"},
        {"id": 3, "name": "Others", "icon": "⚡"},
    ]
    for lang in ["en", "bn"]:
        kb = get_categories_keyboard(sample_categories, show_all_option=True, lang=lang)
        assert [[btn.callback_data for btn in row] for row in kb.inline_keyboard[:3]] == [
            ["cat_1"], ["cat_2"], ["cat_3"],
        ]
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        # shop_uncat should not exist anymore
        assert "shop_uncat" not in callbacks
        assert "shop_all" in callbacks
        assert "back_to_main" not in callbacks
        assert "close_menu" not in callbacks

def test_profile_translations():
    for lang in ["en", "bn"]:
        assert len(t("profile_username", lang)) > 0
        assert len(t("profile_account_type", lang)) > 0
        assert len(t("profile_current_balance", lang)) > 0
        assert len(t("profile_total_orders", lang)) > 0
        assert len(t("profile_total_spent", lang)) > 0
        assert len(t("profile_referrals", lang)) > 0
        assert len(t("profile_referral_link", lang)) > 0
        assert len(t("rank_standard", lang)) > 0
        assert len(t("rank_reseller", lang)) > 0


def test_screen_and_button_consistency():
    from app.bot.icons import Icons, ICON_REFER, ICON_SUPPORT, ICON_DEPOSIT, ICON_RESELLER
    assert Icons.REFER == Icons.ORDERS
    assert "🎁" in ICON_REFER

    for lang in ["en", "bn"]:
        # Refer & Earn title has no "Program" and contains icon_refer
        ref_title = t("referral_title", lang, icon_refer=ICON_REFER)
        assert "Program" not in ref_title
        assert "প্রোগ্রাম" not in ref_title

        # Support title matches support button
        sup_title = t("support_title", lang, icon_support=ICON_SUPPORT)
        assert len(sup_title) > 0
        assert len(t("support_text", lang)) > 0
        assert len(t("support_unavailable", lang)) > 0
        assert len(t("btn_guide", lang)) > 0

        # Reseller titles
        assert len(t("reseller_apply_title", lang, icon_reseller=ICON_RESELLER)) > 0
        assert len(t("reseller_panel_title", lang, icon_reseller=ICON_RESELLER)) > 0

        # Search titles
        assert len(t("search_title", lang)) > 0
        assert len(t("search_prompt", lang)) > 0
        assert len(t("search_try", lang)) > 0

        # Referral steps and buttons
        assert len(t("referral_step_1", lang)) > 0
        assert len(t("referral_step_2", lang)) > 0
        assert len(t("referral_step_3", lang, reward="5 ৳")) > 0
        assert len(t("referral_stats_header", lang, icon_stats="📊")) > 0
        assert len(t("btn_share_referral", lang)) > 0
        assert len(t("btn_copy_link", lang)) > 0
