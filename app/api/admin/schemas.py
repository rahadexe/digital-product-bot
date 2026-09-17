"""Admin request bodies. Every field is bounded so a request cannot store oversized or malformed data."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Flag = Literal[0, 1]
AMOUNT_LIMIT = 1_000_000_000


class Payload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)


def _empty_if_none(value):
    return "" if value is None else value


class LoginPayload(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class CategoryPayload(Payload):
    name: str = Field(min_length=1, max_length=100)
    icon: str = Field(default="📦", max_length=16)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_active: Flag = 1


class ProductPayload(Payload):
    category_id: Optional[int] = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=300)
    price: float = Field(gt=0, le=AMOUNT_LIMIT)
    icon: str = Field(default="⚡", max_length=16)
    duration_label: str = Field(default="", max_length=64)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_active: Flag = 1

    _empty_text = field_validator("description", "duration_label", "icon", mode="before")(_empty_if_none)


class BulkStockPayload(Payload):
    product_id: int = Field(gt=0)
    items_text: str = Field(max_length=1_000_000)
    # How many customers each line can be sold to: 7 for an account shared by seven devices.
    max_uses: int = Field(1, ge=1, le=1000)
    expires_at: Optional[datetime] = None


class StockItemPayload(Payload):
    content: str = Field(min_length=1, max_length=20_000)
    max_uses: int = Field(ge=1, le=1000)
    expires_at: Optional[datetime] = None


class ManualDeliveryPayload(Payload):
    content: str = Field(min_length=1, max_length=20_000)


class DepositMethodPayload(Payload):
    name: str = Field(min_length=1, max_length=100)
    # Telegram's copy button holds at most 256 characters.
    account_info: str = Field(min_length=1, max_length=256)
    instructions: str = Field(default="", max_length=2000)
    min_deposit: float = Field(default=1.0, gt=0, le=AMOUNT_LIMIT)
    rate_to_currency: float = Field(default=1.0, gt=0, le=AMOUNT_LIMIT)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_active: Flag = 1
    # Who can confirm a payment for us, and the only network accepted when one is named (e.g. TRX, BSC).
    auto_verify: Literal["none", "binance", "binance_pay"] = "none"
    auto_verify_network: str = Field(default="", pattern=r"^[A-Za-z0-9]{0,16}$")

    _empty_text = field_validator("instructions", "auto_verify_network", mode="before")(_empty_if_none)


class BalanceAdjustPayload(Payload):
    delta: float = Field(ge=-AMOUNT_LIMIT, le=AMOUNT_LIMIT)
    reason: str = Field(default="", max_length=500)


class GateChannelPayload(Payload):
    channel_username: str = Field(pattern=r"^(@[A-Za-z0-9_]{3,64}|-?\d{5,20})$")
    chat_id: str = Field(default="", pattern=r"^(-?\d{5,20})?$")
    title: str = Field(min_length=1, max_length=128)
    invite_link: str = Field(pattern=r"^https://(t|telegram)\.me/\S{1,200}$")
    is_active: Flag = 1

    _empty_text = field_validator("chat_id", mode="before")(_empty_if_none)


class UpdateChannelPayload(Payload):
    title: str = Field(min_length=1, max_length=64)
    url: str = Field(pattern=r"^(@[A-Za-z0-9_]{3,64}|(https://)?(t|telegram)\.me/\S{1,200})$")
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_active: Flag = 1


class BroadcastPayload(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class DepositReviewPayload(Payload):
    admin_note: str = Field(default="", max_length=500)


class BanPayload(BaseModel):
    banned: bool


class SupplierAttemptReview(Payload):
    verified_no_charge: bool
    reason: str = Field(min_length=10, max_length=1000)


class SupplierSyncPayload(Payload):
    markup_percent: float = Field(25.0, ge=0.0, le=500.0)
    fixed_markup: float = Field(0.0, ge=0.0, le=AMOUNT_LIMIT)
    overwrite_prices: bool = False


class SupplierItemPricePayload(Payload):
    price: float = Field(gt=0.0, le=AMOUNT_LIMIT)
