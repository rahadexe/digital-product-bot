import pytest
from unittest.mock import AsyncMock, patch
from app.api.admin.schemas import DepositMethodPayload
from app.services.deposits import DepositService


def test_deposit_method_payload_zinipay():
    payload = DepositMethodPayload(
        name="bKash Personal",
        account_info="01712345678",
        min_deposit=50.0,
        sort_order=1,
        auto_verify="zinipay",
        account_type="personal",
    )
    assert payload.auto_verify == "zinipay"
    assert payload.sort_order == 1


def test_deposit_method_payload_manual():
    payload = DepositMethodPayload(
        name="Nagad Personal",
        account_info="01812345678",
        min_deposit=50.0,
        sort_order=2,
        auto_verify="none",
        account_type="personal",
    )
    assert payload.auto_verify == "none"
    assert payload.sort_order == 2


@pytest.mark.asyncio
async def test_instant_payment_text_filter_with_and_without_emojis():
    from app.bot.handlers.deposit import InstantPaymentTextFilter
    from unittest.mock import MagicMock

    filt = InstantPaymentTextFilter()
    services = MagicMock()

    # Case 1: When DB has emoji
    services.payments.instant_options = AsyncMock(return_value={"label": "⚡ ZiniPay - bKash/Nagad/Rocket", "min_amount": 50})
    msg1 = MagicMock(text="⚡ ZiniPay - bKash/Nagad/Rocket")
    res1 = await filt(msg1, services)
    assert res1 is not False
    assert "instant" in res1

    msg2 = MagicMock(text="ZiniPay - bKash/Nagad/Rocket")
    res2 = await filt(msg2, services)
    assert res2 is not False

    # Case 2: When DB has NO emoji
    services.payments.instant_options = AsyncMock(return_value={"label": "ZiniPay - bKash/Nagad/Rocket", "min_amount": 50})
    msg3 = MagicMock(text="⚡ ZiniPay - bKash/Nagad/Rocket")
    res3 = await filt(msg3, services)
    assert res3 is not False

    msg4 = MagicMock(text="ZiniPay - bKash/Nagad/Rocket")
    res4 = await filt(msg4, services)
    assert res4 is not False


@pytest.mark.asyncio
async def test_method_text_filter_with_and_without_emojis():
    from app.bot.handlers.deposit import MethodTextFilter
    from unittest.mock import MagicMock

    filt = MethodTextFilter()
    services = MagicMock()

    services.deposits.methods = AsyncMock(return_value=[
        {"id": 1, "name": "bKash", "icon": "💳"},
        {"id": 2, "name": "Nagad", "icon": "💳"},
        {"id": 3, "name": "Binance", "icon": "🟡"},
    ])

    # Message with emoji
    msg1 = MagicMock(text="💳 bKash")
    res1 = await filt(msg1, services)
    assert res1 is not False
    assert res1["method"]["name"] == "bKash"

    # Message without emoji
    msg2 = MagicMock(text="bKash")
    res2 = await filt(msg2, services)
    assert res2 is not False

    # DB stored with emoji
    services.deposits.methods = AsyncMock(return_value=[
        {"id": 1, "name": "💳 bKash", "icon": "💳"},
    ])
    msg3 = MagicMock(text="bKash")
    res3 = await filt(msg3, services)
    assert res3 is not False

