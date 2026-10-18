from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.bot.formatting import format_dual_price
from app.services.settings import SPECS, SettingsService


class EmptySettingsDatabase:
    @asynccontextmanager
    async def connect(self):
        yield self

    async def fetch(self, _query):
        return []


def test_store_currency_defaults_to_bdt():
    assert SPECS["currency"].default == "BDT"
    assert SPECS["currency_symbol"].default == "৳"


def test_store_currency_settings_are_locked_to_bdt():
    settings = SettingsService.__new__(SettingsService)
    assert settings._validate("currency", "USD") == "BDT"
    assert settings._validate("currency_symbol", "$") == "৳"


def test_default_price_format_is_bdt():
    assert format_dual_price(125) == "125 ৳"


@pytest.mark.asyncio
async def test_missing_usd_display_setting_is_off():
    settings = SettingsService(EmptySettingsDatabase(), SimpleNamespace(admin_tg_id=0))
    assert await settings.get("show_usd_price") == "0"
    assert not await settings.flag("show_usd_price")
