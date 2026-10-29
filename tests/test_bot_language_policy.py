from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.users import UserService


def users_with_preference(currency, language):
    context = AsyncMock()
    context.__aenter__.return_value = SimpleNamespace(fetchrow=AsyncMock(return_value={
        "currency": currency, "language": language,
    }))
    return UserService(SimpleNamespace(connect=lambda: context), MagicMock(), MagicMock())


@pytest.mark.parametrize("stored", ["bn", "en", "FR", None])
@pytest.mark.parametrize("currency,expected", [("BDT", "en-BD"), ("USD", "en")])
@pytest.mark.asyncio
async def test_locale_uses_currency_regardless_of_legacy_language(stored, currency, expected):
    users = users_with_preference(currency, stored)
    assert await users.get_language(123) == expected


@pytest.mark.asyncio
async def test_language_ignores_stale_preferences_from_another_worker():
    users = users_with_preference("USD", "en")
    users._lang_cache[123] = (monotonic(), "en-BD")
    users._user_cache[123] = (monotonic(), {"language": "en-BD", "currency": "BDT"})
    assert await users.get_language(123) == "en"
    assert await users.get_currency(123) == "USD"
