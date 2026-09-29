import pytest
from app.core.i18n import SUPPORTED_LANGUAGES, t, DEFAULT_LANGUAGE
from app.bot.keyboards import get_main_inline_keyboard, get_persistent_reply_keyboard, get_account_keyboard, get_language_selection_keyboard
from app.bot.handlers.navigation import NAVIGATION_TEXTS, COMMAND_ACTIONS

def test_supported_languages():
    assert "en" in SUPPORTED_LANGUAGES
    assert "bn" in SUPPORTED_LANGUAGES
    assert "hi" in SUPPORTED_LANGUAGES
    assert "ur" in SUPPORTED_LANGUAGES

def test_i18n_translation_and_fallback():
    # English
    assert t("btn_add_balance", "en") == "💳 Add Balance"
    # Bengali
    assert t("btn_add_balance", "bn") == "💳 অ্যাড ব্যালেন্স"
    # Hindi
    assert t("btn_add_balance", "hi") == "💳 बैलेंस जोड़ें"
    # Urdu
    assert t("btn_add_balance", "ur") == "💳 بیلنس شامل کریں"
    
    # Missing key fallback
    assert t("non_existent_key_xyz", "bn") == "non_existent_key_xyz"
    # Missing language fallback to English
    assert t("btn_add_balance", "fr") == "💳 Add Balance"

def test_i18n_interpolation():
    assert "500 BDT" in t("btn_pay", "en", amount="500 BDT")
    assert "500 BDT" in t("btn_pay", "bn", amount="500 BDT")

def test_keyboards_all_languages():
    for lang in ["en", "bn", "hi", "ur"]:
        main_kb = get_main_inline_keyboard(lang=lang, is_admin=False)
        assert len(main_kb.inline_keyboard) >= 4
        admin_kb = get_main_inline_keyboard(lang=lang, is_admin=True)
        assert len(admin_kb.inline_keyboard) >= 5
        kb = get_persistent_reply_keyboard(is_reseller=False, is_admin=False, lang=lang)
        assert len(kb.keyboard) > 0
        account_kb = get_account_keyboard(lang=lang, is_admin=False)
        assert len(account_kb.inline_keyboard) > 0
        assert len(t("select_language_title", lang)) > 0
        assert len(t("select_language_prompt", lang)) > 0

def test_language_selection_keyboard():
    kb = get_language_selection_keyboard(current_lang="en")
    codes = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data.startswith("set_lang_")]
    assert set(codes) == {"set_lang_en", "set_lang_bn", "set_lang_hi", "set_lang_ur"}

def test_navigation_texts_include_all_languages():
    # Check English
    assert NAVIGATION_TEXTS["💳 Add Balance"] == "deposit"
    # Check Bengali
    assert NAVIGATION_TEXTS["💳 অ্যাড ব্যালেন্স"] == "deposit"
    # Check Hindi
    assert NAVIGATION_TEXTS["💳 बैलेंस जोड़ें"] == "deposit"
    # Check Urdu
    assert NAVIGATION_TEXTS["💳 بیلنس شامل کریں"] == "deposit"

    # Check commands
    assert COMMAND_ACTIONS["/language"] == "language"
    assert COMMAND_ACTIONS["/lang"] == "language"

def test_history_translations():
    for lang in ["en", "bn", "hi", "ur"]:
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
        {"id": 3, "name": "Uncategorized", "icon": "⚡"},
    ]
    for lang in ["en", "bn", "hi", "ur"]:
        kb = get_categories_keyboard(sample_categories, show_all_option=True, lang=lang)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        # shop_uncat should not exist anymore
        assert "shop_uncat" not in callbacks
        assert "shop_all" in callbacks
        assert "close_menu" in callbacks

def test_profile_translations():
    for lang in ["en", "bn", "hi", "ur"]:
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

    for lang in ["en", "bn", "hi", "ur"]:
        # Refer & Earn title has no "Program" and contains icon_refer
        ref_title = t("referral_title", lang, icon_refer=ICON_REFER)
        assert "Program" not in ref_title
        assert "প্রোগ্রাম" not in ref_title
        assert "प्रोग्राम" not in ref_title
        assert "پروگرام" not in ref_title

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




