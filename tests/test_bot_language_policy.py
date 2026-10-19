from time import monotonic
from unittest.mock import MagicMock

import pytest

from app.services.users import UserService


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("bn", "bn"), ("en", "en"), ("FR", "en"), (None, "en")],
)
@pytest.mark.asyncio
async def test_get_language_uses_saved_preference_or_english_fallback(stored, expected):
    users = UserService(MagicMock(), MagicMock(), MagicMock())
    users._user_cache[123] = (monotonic(), {"language": stored})

    assert await users.get_language(123) == expected


@pytest.mark.asyncio
async def test_get_language_uses_fresh_preference_cache():
    users = UserService(MagicMock(), MagicMock(), MagicMock())
    users._lang_cache[123] = (monotonic(), "bn")
    users._user_cache[123] = (monotonic(), {"language": "en"})

    assert await users.get_language(123) == "bn"
