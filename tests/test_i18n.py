from string import Formatter

import pytest

from app.bot.handlers.help_guide import GUIDE_TEXTS, get_guide_keyboard
from app.bot.handlers.navigation import COMMAND_ACTIONS, NAVIGATION_TEXTS
from app.bot.keyboards import (
    get_account_keyboard,
    get_language_selection_keyboard,
    get_main_inline_keyboard,
    get_more_inline_keyboard,
    get_persistent_reply_keyboard,
)
from app.core.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, TRANSLATIONS, t

def test_supported_languages():
    assert "en" in SUPPORTED_LANGUAGES
    assert "bn" in SUPPORTED_LANGUAGES
    assert len(SUPPORTED_LANGUAGES) == 2

def test_i18n_translation_and_fallback():
    # English
    assert t("btn_add_balance", "en") == "Top Up"
    # Bengali
    assert t("btn_add_balance", "bn") == "💳 ডিপোজিট"
    
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

def test_guide_copy_and_support_action_match_each_language():
    for lang, phrase in (("en", "How to use the bot"), ("bn", "বট ব্যবহার")):
        assert phrase in GUIDE_TEXTS[lang]
        button = get_guide_keyboard(lang).inline_keyboard[0][0]
        assert button.text.endswith(t("btn_support", lang).split(" ", 1)[-1])
        assert button.callback_data == "open_support"

def test_language_specific_currency_formatting():
    from app.bot.formatting import format_dual_price, price
    # Bengali should show Tk (৳), never dual price
    assert format_dual_price(44.0, "৳", usd_rate=125.0, show_usd=True, lang="bn") == "44 ৳"
    assert price("৳", 44.0, usd_rate=125.0, show_usd=True, lang="bn") == "44 ৳"
    assert "≈" not in format_dual_price(44.0, "৳", usd_rate=125.0, show_usd=True, lang="bn")

    # English should show $ cleanly, converted using usd_rate
    assert format_dual_price(125.0, "৳", usd_rate=125.0, show_usd=True, lang="en") == "$1"
    assert price("৳", 125.0, usd_rate=125.0, show_usd=True, lang="en") == "$1"
    assert "≈" not in format_dual_price(125.0, "৳", usd_rate=125.0, show_usd=True, lang="en")

def test_keyboards_all_languages():
    for lang in ["en", "bn"]:
        main_kb = get_main_inline_keyboard(lang=lang, is_admin=False)
        assert len(main_kb.inline_keyboard) == 3
        admin_kb = get_main_inline_keyboard(lang=lang, is_admin=True)
        assert len(admin_kb.inline_keyboard) == 4
        admin_callbacks = [btn.callback_data for row in admin_kb.inline_keyboard for btn in row]
        assert "adm_dashboard" in admin_callbacks
        more_kb = get_more_inline_keyboard(lang=lang, is_admin=True, is_reseller=True)
        more_callbacks = [btn.callback_data for row in more_kb.inline_keyboard for btn in row]
        assert "adm_dashboard" not in more_callbacks
        assert "open_reseller_hub" in more_callbacks
        kb = get_persistent_reply_keyboard(is_reseller=False, is_admin=False, lang=lang)
        assert len(kb.keyboard) == 3
        assert kb.is_persistent is False
        assert kb.resize_keyboard is True
        kb_admin = get_persistent_reply_keyboard(is_reseller=False, is_admin=True, lang=lang)
        assert len(kb_admin.keyboard) == 4
        assert kb_admin.keyboard[-1][0].text == ("🛡 অ্যাডমিন প্যানেল" if lang == "bn" else "🛡 Admin Panel")
        kb_cats = get_persistent_reply_keyboard(pinned_categories=[{"name": "VPN", "icon": "🛡️"}], lang=lang)
        assert len(kb_cats.keyboard) == 3
        account_kb = get_account_keyboard(lang=lang, is_admin=False)
        assert len(account_kb.inline_keyboard) > 0
        assert any(
            btn.callback_data == "open_language_menu"
            for row in account_kb.inline_keyboard for btn in row
        )
        assert len(t("select_language_title", lang)) > 0
        assert len(t("select_language_prompt", lang)) > 0

def test_language_selection_keyboard():
    for current_lang, selected_code in (("en", "set_lang_en"), ("bn", "set_lang_bn")):
        kb = get_language_selection_keyboard(current_lang=current_lang)
        language_buttons = [
            btn for row in kb.inline_keyboard for btn in row
            if btn.callback_data in {"set_lang_en", "set_lang_bn"}
        ]
        assert [btn.callback_data for btn in language_buttons] == ["set_lang_en", "set_lang_bn"]
        selected = [btn for btn in language_buttons if btn.text.endswith("✓")]
        assert len(selected) == 1
        assert selected[0].callback_data == selected_code

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

    # Check commands
    assert COMMAND_ACTIONS["/language"] == "language"
    assert COMMAND_ACTIONS["/lang"] == "language"
    assert COMMAND_ACTIONS["/en"] == "set_en"
    assert COMMAND_ACTIONS["/bn"] == "set_bn"
    assert NAVIGATION_TEXTS["en"] == "set_en"
    assert NAVIGATION_TEXTS["bn"] == "set_bn"

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
