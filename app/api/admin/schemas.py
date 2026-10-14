"""Admin request bodies. Every field is bounded so a request cannot store oversized or malformed data."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Flag = Literal[0, 1]
AMOUNT_LIMIT = 1_000_000_000


class Payload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)


def _empty_if_none(value):
    return "" if value is None else value


def _is_single_emoji(value: str) -> bool:
    if not value or any(char.isspace() for char in value):
        return False
    codepoints = [ord(char) for char in value]
    has_keycap = 0x20E3 in codepoints
    has_joiner = 0x200D in codepoints
    regional_indicators = [cp for cp in codepoints if 0x1F1E6 <= cp <= 0x1F1FF]
    bases = [
        cp for cp in codepoints
        if unicodedata.category(chr(cp)) in {"So", "Sk"}
        and not 0x1F3FB <= cp <= 0x1F3FF
        and not 0x1F1E6 <= cp <= 0x1F1FF
    ]
    if has_keycap:
        return (
            len(codepoints) in {2, 3}
            and codepoints[0] in [ord("#"), ord("*"), *range(ord("0"), ord("9") + 1)]
            and all(cp in {codepoints[0], 0xFE0F, 0x20E3} for cp in codepoints)
        )
    allowed = all(
        unicodedata.category(chr(cp)) in {"So", "Sk", "Mn", "Me", "Cf"}
        or cp in {0x200D, 0xFE0E, 0xFE0F}
        for cp in codepoints
    )
    return allowed and (
        len(bases) == 1
        or has_joiner and len(bases) >= 2
        or len(regional_indicators) == 2 and len(regional_indicators) == len(codepoints)
    )


def _validate_icon(value: str) -> str:
    if value and not _is_single_emoji(value):
        raise ValueError("Icon must be one standard emoji.")
    return value


class LoginPayload(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class CategoryPayload(Payload):
    name: str = Field(min_length=1, max_length=100)
    icon: str = Field(default="", max_length=16)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_active: Flag = 1
    is_pinned: Flag = 0
    has_validity_filter: Flag = 0
    custom_emoji_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^\d*$")

    _empty_text = field_validator("icon", "custom_emoji_id", mode="before")(_empty_if_none)
    _single_emoji = field_validator("icon")(_validate_icon)

    @model_validator(mode="after")
    def _check_icon_selection(self):
        if self.icon and self.custom_emoji_id:
            raise ValueError("Choose either a standard emoji or a Telegram custom emoji, not both.")
        return self



class ProductPayload(Payload):
    category_id: Optional[int] = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=300)
    price: float = Field(gt=0, le=AMOUNT_LIMIT)
    reseller_price: Optional[float] = Field(default=None, ge=0, le=AMOUNT_LIMIT)
    icon: str = Field(default="", max_length=16)
    duration_label: str = Field(default="", max_length=64)
    warranty_label: str = Field(default="", max_length=64)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_pinned: Flag = 0
    is_active: Flag = 1
    delivery_type: str = Field(default="stock", max_length=16)
    custom_emoji_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^\d*$")
    upstream_devices: int = Field(default=1, ge=1, le=100)
    upstream_share_hours: int = Field(default=24, ge=1, le=8760)
    upstream_product_id: Optional[int] = Field(default=None)
    supplier_code: Optional[str] = Field(default=None, max_length=64)
    requires_customer_input: Flag = 0
    customer_input_prompt: str = Field(default="", max_length=200)

    _empty_text = field_validator("description", "duration_label", "warranty_label", "icon", "custom_emoji_id", "customer_input_prompt", mode="before")(_empty_if_none)
    _single_emoji = field_validator("icon")(_validate_icon)

    @model_validator(mode="after")
    def _check_icon_selection(self):
        if self.icon and self.custom_emoji_id:
            raise ValueError("Choose either a standard emoji or a Telegram custom emoji, not both.")
        return self

    @field_validator("delivery_type")
    @classmethod
    def _check_delivery_type(cls, v: str) -> str:
        return v if v in ("stock", "manual") else "stock"


class ProductUpdatePayload(Payload):
    category_id: Optional[int] = Field(default=None, gt=0)
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=300)
    price: Optional[float] = Field(default=None, gt=0, le=AMOUNT_LIMIT)
    reseller_price: Optional[float] = Field(default=None, ge=0, le=AMOUNT_LIMIT)
    icon: Optional[str] = Field(default=None, max_length=16)
    duration_label: Optional[str] = Field(default=None, max_length=64)
    warranty_label: Optional[str] = Field(default=None, max_length=64)
    sort_order: Optional[int] = Field(default=None, ge=-100_000, le=100_000)
    is_pinned: Optional[Flag] = None
    is_active: Optional[Flag] = None
    delivery_type: Optional[str] = Field(default=None, max_length=16)
    custom_emoji_id: Optional[str] = Field(default=None, max_length=64, pattern=r"^\d*$")
    upstream_devices: Optional[int] = Field(default=None, ge=1, le=100)
    upstream_share_hours: Optional[int] = Field(default=None, ge=1, le=8760)
    upstream_product_id: Optional[int] = Field(default=None)
    supplier_code: Optional[str] = Field(default=None, max_length=64)
    requires_customer_input: Optional[Flag] = None
    customer_input_prompt: Optional[str] = Field(default=None, max_length=200)

    _empty_text = field_validator("description", "duration_label", "warranty_label", "icon", "custom_emoji_id", "customer_input_prompt", mode="before")(_empty_if_none)
    _single_emoji = field_validator("icon")(_validate_icon)

    @model_validator(mode="after")
    def _check_icon_selection(self):
        if self.icon and self.custom_emoji_id:
            raise ValueError("Choose either a standard emoji or a Telegram custom emoji, not both.")
        return self

    @field_validator("delivery_type")
    @classmethod
    def _check_delivery_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v if v in ("stock", "manual") else "stock"


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
    name: str = Field(default="", max_length=100)
    # Telegram's copy button holds at most 256 characters.
    account_info: str = Field(min_length=1, max_length=256)
    instructions: str = Field(default="", max_length=2000)
    min_deposit: float = Field(default=1.0, gt=0, le=AMOUNT_LIMIT)
    rate_to_currency: float = Field(default=1.0, gt=0, le=AMOUNT_LIMIT)
    sort_order: int = Field(default=0, ge=-100_000, le=100_000)
    is_active: Flag = 1
    # Who can confirm a payment for us, and the only network accepted when one is named (e.g. TRX, BSC).
    auto_verify: Literal["none", "binance", "binance_pay", "zinipay"] = "none"
    auto_verify_network: str = Field(default="", pattern=r"^[A-Za-z0-9]{0,16}$")
    custom_emoji_id: Optional[str] = Field(default=None, max_length=64)
    account_type: Literal["personal", "agent", "merchant", "crypto"] = "personal"
    api_key: Optional[str] = Field(default=None, max_length=256)
    api_secret: Optional[str] = Field(default=None, max_length=256)
    clear_api_credentials: bool = False

    _empty_text = field_validator("instructions", "auto_verify_network", "custom_emoji_id", "api_key", "api_secret", mode="before")(_empty_if_none)


class BalanceAdjustPayload(Payload):
    operation_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
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


class UserRankPayload(Payload):
    rank: str = Field(min_length=1, max_length=50)


class ResellerApplicationReviewPayload(Payload):
    admin_note: str = Field(default="", max_length=500)
