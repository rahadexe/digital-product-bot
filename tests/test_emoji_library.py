from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.admin.emojis import SYSTEM_EMOJIS, delete_emoji, list_emojis


class FakeConnection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def fetch(self, query):
        return [
            {
                "id": 7,
                "name": "Custom payment",
                "emoji_id": "1234567890",
                "created_at": None,
            }
        ]


@pytest.mark.asyncio
async def test_emoji_library_contains_only_locked_vpn_and_payment_presets():
    expected_names = {
        "NordVPN", "ExpressVPN", "Surfshark", "Proton VPN", "CyberGhost",
        "HMA VPN", "Bitdefender", "Windscribe", "PureVPN", "Turbo VPN",
        "PotatoVPN", "PandaVPN", "IPVanish", "X VPN", "bKash", "Nagad",
        "Rocket", "Binance", "Bybit",
    }
    services = SimpleNamespace(db=SimpleNamespace(connect=FakeConnection))

    response = await list_emojis(services)

    assert {item["name"] for item in response["system"]} == expected_names
    assert all(item["is_system"] for item in response["system"])
    assert all("category" not in item for item in response["all"])
    assert response["custom"][0]["name"] == "Custom payment"
    assert response["custom"][0]["is_system"] is False


@pytest.mark.asyncio
async def test_system_emoji_cannot_be_deleted():
    with pytest.raises(HTTPException) as error:
        await delete_emoji(SYSTEM_EMOJIS[0]["emoji_id"], SimpleNamespace())

    assert error.value.status_code == 400
