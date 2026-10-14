from unittest.mock import MagicMock

import pytest

from app.services.users import UserService


@pytest.mark.asyncio
async def test_bot_language_is_always_english():
    users = UserService(MagicMock(), MagicMock(), MagicMock())
    users._lang_cache[123] = "bn"
    users._user_cache[123] = (0.0, {"language": "bn"})

    assert await users.get_language(123) == "en"
