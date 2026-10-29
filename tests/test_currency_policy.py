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


def test_store_currency_defaults_to_usd():
    assert SPECS["currency"].default == "USD"
    assert SPECS["currency_symbol"].default == "$"
    assert SPECS["binance_pay_rate"].default == "1"


def test_store_currency_settings_are_locked_to_usd():
    settings = SettingsService.__new__(SettingsService)
    assert settings._validate("currency", "USD") == "USD"
    assert settings._validate("currency_symbol", "$") == "$"
    assert settings._validate("binance_pay_rate", "1") == "1"
    with pytest.raises(ValueError, match="must remain USD"):
        settings._validate("currency", "BDT")
    with pytest.raises(ValueError, match=r"must remain \$"):
        settings._validate("currency_symbol", "৳")
    with pytest.raises(ValueError, match="must remain 1"):
        settings._validate("binance_pay_rate", "125")


class LegacyCurrencySettingsDatabase(EmptySettingsDatabase):
    async def fetch(self, _query):
        return [
            {"key": "currency", "value": "BDT"},
            {"key": "currency_symbol", "value": "৳"},
        ]


@pytest.mark.asyncio
async def test_legacy_currency_settings_are_read_as_usd():
    settings = SettingsService(LegacyCurrencySettingsDatabase(), SimpleNamespace(admin_tg_id=0))
    values = await settings.values()
    assert values["currency"] == "USD"
    assert values["currency_symbol"] == "$"


def test_default_price_format_is_usd_and_bangla_shows_equivalent():
    assert format_dual_price(125) == "$125"
    assert format_dual_price(0.8, usd_rate=125, lang="bn") == "100 ৳ (≈$0.8)"
    assert format_dual_price(0.8, usd_rate=125, lang="en-BD") == "100 ৳ (≈$0.8)"
    assert format_dual_price(0.8, lang="en") == "$0.8"


@pytest.mark.asyncio
async def test_missing_usd_display_setting_is_off():
    settings = SettingsService(EmptySettingsDatabase(), SimpleNamespace(admin_tg_id=0))
    assert await settings.get("show_usd_price") == "0"
    assert not await settings.flag("show_usd_price")
